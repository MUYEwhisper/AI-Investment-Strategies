from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from utils.db.mysql import mysql_conn

RECENT_MESSAGE_LIMIT = 12
MAX_SESSION_SUMMARY_CHARS = 800
MAX_LIST_ITEMS = 8

SHARED_CONTEXT_KEYS = (
    'confirmed_profile',
    'investment_preferences',
    'watch_targets',
    'open_questions',
    'recent_conclusions',
)

QUESTION_PATTERN = re.compile(r'[?？]|如何|怎么|怎样|是否|能否|可否|需不需要|要不要|有没有')
FOLLOWUP_PATTERN = re.compile(r'需要补充|请提供|请告诉我|欢迎补充|如果你能提供|若你补充|先告诉我|还需要')
STOCK_CODE_PATTERN = re.compile(r'\b\d{6}\b')
CAPITAL_PATTERN = re.compile(r'(\d+(?:\.\d+)?\s*(?:元|万元|w|W|k|K|亿))')
TRANSIENT_MARKET_PATTERN = re.compile(
    r'今日|当前|实时|盘中|收盘|开盘|截至|分钟|涨跌|成交额|换手率|资金流向|资金净流入|\d{4}[-/]\d{1,2}[-/]\d{1,2}'
)
TRANSIENT_MESSAGE_PATTERN = re.compile(r'^\[(?:错误|连接失败)\]')
GREETING_PATTERN = re.compile(r'^你好.{0,20}(?:我是|这里是).{0,30}$')


@dataclass
class PreparedChatMemory:
    normalized_messages: list[dict[str, str]]
    recent_messages: list[dict[str, str]]
    session_summary_text: str
    shared_context: dict[str, list[str]]
    shared_context_text: str
    shared_memory_loaded: bool
    shared_memory_hit: bool
    chat_summary_used: bool
    recent_message_count: int
    memory_build_ms: int
    shared_context_size: int


def empty_shared_context() -> dict[str, list[str]]:
    return {key: [] for key in SHARED_CONTEXT_KEYS}


def _normalize_text(value: Any) -> str:
    text = str(value or '')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _truncate_text(text: str, limit: int) -> str:
    value = _normalize_text(text)
    if len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    return value[: limit - 3].rstrip() + '...'


def _unique_extend(target: list[str], values: list[str], limit: int = MAX_LIST_ITEMS) -> None:
    existing = {item.lower(): item for item in target}
    for value in values:
        normalized = _normalize_text(value)
        if not normalized:
            continue
        key = normalized.lower()
        if key in existing:
            continue
        target.append(normalized)
        existing[key] = normalized
        if len(target) >= limit:
            break


def _split_sentences(text: str) -> list[str]:
    value = _normalize_text(text)
    if not value:
        return []

    segments = re.split(r'[。！？?!\n]+', value)
    return [_truncate_text(segment, 140) for segment in segments if _normalize_text(segment)]


def _is_transient_assistant_message(text: str) -> bool:
    value = _normalize_text(text)
    if not value:
        return True
    if TRANSIENT_MESSAGE_PATTERN.search(value):
        return True
    if GREETING_PATTERN.search(value) and len(value) <= 80:
        return True
    return False


def normalize_chat_messages(messages: Any, original_prompt: str = '') -> list[dict[str, str]]:
    normalized_messages: list[dict[str, str]] = []

    if isinstance(messages, list):
        for raw_message in messages:
            if not isinstance(raw_message, dict):
                continue

            role_raw = str(raw_message.get('role') or '').strip().lower()
            if role_raw == 'user':
                role = 'user'
            elif role_raw in {'assistant', 'ai'}:
                role = 'assistant'
            else:
                continue

            content = _normalize_text(raw_message.get('content'))
            if not content:
                continue
            if role == 'assistant' and _is_transient_assistant_message(content):
                continue

            normalized_messages.append({'role': role, 'content': content})

    prompt = _normalize_text(original_prompt)
    if prompt:
        if not normalized_messages or normalized_messages[-1]['role'] != 'user' or normalized_messages[-1]['content'] != prompt:
            normalized_messages.append({'role': 'user', 'content': prompt})

    return normalized_messages


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _extract_confirmed_profile(text: str) -> list[str]:
    value = _normalize_text(text)
    results: list[str] = []

    if _contains_any(value, ('新手', '小白', '刚入门')):
        results.append('投资经验: 偏新手')
    if _contains_any(value, ('有经验', '做了多年', '老股民', '长期投资')):
        results.append('投资经验: 已有一定经验')

    capital_match = CAPITAL_PATTERN.search(value)
    if capital_match:
        results.append(f"资金规模: {capital_match.group(1).replace(' ', '')}")

    return results


def _extract_investment_preferences(text: str) -> list[str]:
    value = _normalize_text(text)
    results: list[str] = []

    for risk in ('保守', '稳健', '平衡', '积极', '激进'):
        if re.search(rf'(风险偏好|风险承受|风格|偏好).{{0,8}}{risk}', value) or value == risk:
            results.append(f'风险偏好: {risk}')

    if _contains_any(value, ('短线', '短期', '日内', '波段')):
        results.append('投资周期: 偏短线')
    if _contains_any(value, ('中线', '中期')):
        results.append('投资周期: 偏中线')
    if _contains_any(value, ('长线', '长期', '定投')):
        results.append('投资周期: 偏长线')

    if _contains_any(value, ('保值', '资产保全', '稳住本金')):
        results.append('投资目标: 偏保值')
    if _contains_any(value, ('稳健增值', '稳健增长', '控制回撤')):
        results.append('投资目标: 偏稳健增值')
    if _contains_any(value, ('积极增长', '高成长', '追求收益')):
        results.append('投资目标: 偏收益增长')

    return results


def _extract_watch_targets(text: str) -> list[str]:
    value = _normalize_text(text)
    codes = STOCK_CODE_PATTERN.findall(value)
    return [f'关注标的: {code}' for code in codes[:MAX_LIST_ITEMS]]


def _extract_open_question(user_text: str, assistant_text: str) -> list[str]:
    user_value = _normalize_text(user_text)
    assistant_value = _normalize_text(assistant_text)
    if not user_value or not QUESTION_PATTERN.search(user_value):
        return []
    if FOLLOWUP_PATTERN.search(assistant_value):
        return [_truncate_text(user_value, 120)]
    return []


def _extract_recent_conclusions(text: str, agent_id: str = '') -> list[str]:
    value = _normalize_text(text)
    if not value or QUESTION_PATTERN.search(value[:40]):
        return []

    candidate_lines: list[str] = []
    for line in value.split('\n'):
        normalized = _normalize_text(line.lstrip('-*0123456789. '))
        if normalized:
            candidate_lines.append(normalized)

    if not candidate_lines:
        candidate_lines = _split_sentences(value)

    results: list[str] = []
    for line in candidate_lines:
        if not line or QUESTION_PATTERN.search(line):
            continue
        if FOLLOWUP_PATTERN.search(line):
            continue
        if TRANSIENT_MARKET_PATTERN.search(line):
            continue
        if len(line) < 8:
            continue
        summary_line = _truncate_text(line, 140)
        if agent_id:
            results.append(f'[{agent_id}] {summary_line}')
        else:
            results.append(summary_line)
        if len(results) >= 3:
            break

    return results


def extract_fact_buckets(messages: list[dict[str, str]], agent_id: str = '') -> dict[str, list[str]]:
    buckets = empty_shared_context()
    last_user_message = ''

    for message in messages:
        role = message.get('role')
        content = _normalize_text(message.get('content'))
        if not content:
            continue

        if role == 'user':
            _unique_extend(buckets['confirmed_profile'], _extract_confirmed_profile(content))
            _unique_extend(buckets['investment_preferences'], _extract_investment_preferences(content))
            _unique_extend(buckets['watch_targets'], _extract_watch_targets(content))
            last_user_message = content
            continue

        if role == 'assistant':
            _unique_extend(buckets['recent_conclusions'], _extract_recent_conclusions(content, agent_id=agent_id))
            if last_user_message:
                _unique_extend(buckets['open_questions'], _extract_open_question(last_user_message, content))
                last_user_message = ''

    return buckets


def _format_bullet_block(title: str, items: list[str]) -> str:
    if not items:
        return ''
    lines = '\n'.join(f'- {item}' for item in items)
    return f'{title}:\n{lines}'


def format_shared_context_text(shared_context: dict[str, list[str]]) -> str:
    sections = [
        _format_bullet_block('已确认用户画像', shared_context.get('confirmed_profile', [])),
        _format_bullet_block('投资偏好', shared_context.get('investment_preferences', [])),
        _format_bullet_block('关注标的', shared_context.get('watch_targets', [])),
        _format_bullet_block('待补充或待继续跟进的问题', shared_context.get('open_questions', [])),
        _format_bullet_block('近期可复用结论', shared_context.get('recent_conclusions', [])),
    ]
    sections = [section for section in sections if section]
    if not sections:
        return ''

    return (
        '以下是同一用户在其他智能体与历史会话中沉淀出的共享记忆。\n'
        '仅在与当前问题相关时复用；若与用户本轮最新输入冲突，以本轮最新输入为准。\n\n'
        + '\n\n'.join(sections)
    )


def build_session_summary_text(messages: list[dict[str, str]]) -> str:
    if not messages:
        return ''

    facts = extract_fact_buckets(messages)
    user_topics = [
        _truncate_text(message['content'], 80)
        for message in messages
        if message.get('role') == 'user'
    ][-4:]

    sections: list[str] = []
    if facts['confirmed_profile']:
        sections.append(f"已确认画像: {'；'.join(facts['confirmed_profile'])}")
    if facts['investment_preferences']:
        sections.append(f"已确认偏好: {'；'.join(facts['investment_preferences'])}")
    if facts['watch_targets']:
        sections.append(f"较早关注标的: {'；'.join(facts['watch_targets'])}")
    if user_topics:
        sections.append('较早讨论主题: ' + '；'.join(user_topics))
    if facts['recent_conclusions']:
        sections.append('较早结论: ' + '；'.join(facts['recent_conclusions']))
    if facts['open_questions']:
        sections.append('仍待继续跟进: ' + '；'.join(facts['open_questions']))

    if not sections:
        fallback = []
        for message in messages[-4:]:
            role_label = '用户' if message.get('role') == 'user' else '助手'
            fallback.append(f"{role_label}: {_truncate_text(message['content'], 100)}")
        sections = fallback

    text = '以下是当前会话较早轮次的压缩摘要，仅用于延续上下文：\n' + '\n'.join(
        f'- {item}' for item in sections
    )
    return _truncate_text(text, MAX_SESSION_SUMMARY_CHARS)


def _parse_shared_context(raw_value: Any) -> dict[str, list[str]]:
    parsed = raw_value
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            parsed = None

    context = empty_shared_context()
    if not isinstance(parsed, dict):
        return context

    for key in SHARED_CONTEXT_KEYS:
        value = parsed.get(key)
        if isinstance(value, list):
            context[key] = [_normalize_text(item) for item in value if _normalize_text(item)]

    return context


def _load_shared_context_row(user_id: int) -> dict[str, list[str]] | None:
    with mysql_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                '''
                SELECT summary_json
                FROM user_shared_context
                WHERE user_id = %s
                LIMIT 1
                ''',
                (user_id,),
            )
            row = cursor.fetchone()

    if not row:
        return None
    return _parse_shared_context(row.get('summary_json'))


def _save_shared_context(user_id: int, shared_context: dict[str, list[str]]) -> None:
    payload = json.dumps(shared_context, ensure_ascii=False)
    with mysql_conn(commit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                '''
                INSERT INTO user_shared_context (user_id, summary_json)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE
                  summary_json = VALUES(summary_json)
                ''',
                (user_id, payload),
            )


def _backfill_shared_context_from_history(user_id: int) -> dict[str, list[str]]:
    with mysql_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                '''
                SELECT s.agent_id, m.role, m.content
                FROM user_chat_sessions s
                JOIN user_chat_messages m ON m.session_id = s.id
                WHERE s.user_id = %s
                ORDER BY s.created_at ASC, s.id ASC, m.msg_order ASC, m.id ASC
                ''',
                (user_id,),
            )
            rows = cursor.fetchall() or []

    shared_context = empty_shared_context()
    last_user_message = ''
    for row in rows:
        normalized = normalize_chat_messages([{'role': row.get('role'), 'content': row.get('content')}], '')
        if not normalized:
            continue

        message = normalized[0]
        content = message['content']
        agent_id = str(row.get('agent_id') or 'assistant')

        if message['role'] == 'user':
            _unique_extend(shared_context['confirmed_profile'], _extract_confirmed_profile(content))
            _unique_extend(shared_context['investment_preferences'], _extract_investment_preferences(content))
            _unique_extend(shared_context['watch_targets'], _extract_watch_targets(content))
            last_user_message = content
            continue

        _unique_extend(shared_context['recent_conclusions'], _extract_recent_conclusions(content, agent_id=agent_id))
        if last_user_message:
            _unique_extend(shared_context['open_questions'], _extract_open_question(last_user_message, content))
            last_user_message = ''

    return shared_context


def load_or_backfill_shared_context(user_id: int) -> tuple[dict[str, list[str]], bool]:
    existing = _load_shared_context_row(user_id)
    if existing is not None:
        return existing, True

    shared_context = _backfill_shared_context_from_history(user_id)
    _save_shared_context(user_id, shared_context)
    return shared_context, True


def merge_turn_into_shared_context(user_id: int, agent_id: str, user_message: str, assistant_message: str) -> None:
    if not _normalize_text(user_message) or not _normalize_text(assistant_message):
        return

    current_context, _ = load_or_backfill_shared_context(user_id)
    turn_messages = normalize_chat_messages(
        [
            {'role': 'user', 'content': user_message},
            {'role': 'assistant', 'content': assistant_message},
        ]
    )
    turn_facts = extract_fact_buckets(turn_messages, agent_id=agent_id)

    for key in SHARED_CONTEXT_KEYS:
        _unique_extend(current_context[key], turn_facts.get(key, []))

    _save_shared_context(user_id, current_context)


def prepare_chat_memory(
    user_id: int | None,
    messages: list[dict[str, str]],
    original_prompt: str = '',
) -> PreparedChatMemory:
    started_at = time.perf_counter()

    normalized_messages = normalize_chat_messages(messages, original_prompt=original_prompt)
    older_messages = normalized_messages[:-RECENT_MESSAGE_LIMIT] if len(normalized_messages) > RECENT_MESSAGE_LIMIT else []
    recent_messages = normalized_messages[-RECENT_MESSAGE_LIMIT:]

    session_summary_text = ''
    chat_summary_used = False
    if older_messages:
        try:
            session_summary_text = build_session_summary_text(older_messages)
            chat_summary_used = bool(session_summary_text)
        except Exception:
            session_summary_text = ''
            chat_summary_used = False

    shared_context = empty_shared_context()
    shared_context_text = ''
    shared_memory_loaded = False
    shared_memory_hit = False

    if user_id:
        try:
            shared_context, shared_memory_loaded = load_or_backfill_shared_context(user_id)
            shared_context_text = format_shared_context_text(shared_context)
            shared_memory_hit = bool(shared_context_text)
        except Exception:
            shared_context = empty_shared_context()
            shared_context_text = ''
            shared_memory_loaded = False
            shared_memory_hit = False

    memory_build_ms = int((time.perf_counter() - started_at) * 1000)

    return PreparedChatMemory(
        normalized_messages=normalized_messages,
        recent_messages=recent_messages,
        session_summary_text=session_summary_text,
        shared_context=shared_context,
        shared_context_text=shared_context_text,
        shared_memory_loaded=shared_memory_loaded,
        shared_memory_hit=shared_memory_hit,
        chat_summary_used=chat_summary_used,
        recent_message_count=len(recent_messages),
        memory_build_ms=memory_build_ms,
        shared_context_size=len(shared_context_text),
    )
