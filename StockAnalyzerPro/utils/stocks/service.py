from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

import utils.mcp.init as mcp
from utils.models.availability import ANALYSIS_CLIENT, ANALYSIS_MODEL, ensure_model_available

load_dotenv()

SEARCH_TIMEOUT_SECONDS = 20
DETAIL_CACHE_TTL_SECONDS = int(os.environ.get("STOCK_DETAIL_CACHE_TTL_SECONDS", "300"))
STOCK_DETAIL_CACHE_VERSION = "v2"
VOLUME_RATIO_BASE_DAYS = max(3, int(os.environ.get("STOCK_VOLUME_RATIO_BASE_DAYS", "5")))
HISTORY_LOOKBACK_DAYS = max(10, int(os.environ.get("STOCK_HISTORY_LOOKBACK_DAYS", "40")))
HISTORY_PAGE_SIZE = max(VOLUME_RATIO_BASE_DAYS + 1, int(os.environ.get("STOCK_HISTORY_PAGE_SIZE", "8")))
ANALYSIS_TIMEOUT_SECONDS = int(os.environ.get("STOCK_ANALYSIS_TIMEOUT_SECONDS", "45"))
ANALYSIS_SENTIMENTS = {"强势", "偏强", "震荡", "中性", "偏弱", "转弱"}
PLACEHOLDER = "--"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "cache" / "stock_service"
DETAIL_CACHE_DIR = CACHE_DIR / "details" / STOCK_DETAIL_CACHE_VERSION
RESOLVE_CACHE_FILE = CACHE_DIR / "resolve_cache.json"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
DETAIL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

class StockServiceError(RuntimeError):
    """股票服务通用错误。"""


class StockResolveError(StockServiceError):
    """股票解析失败。"""


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip().lower()


def _normalize_key(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value).strip().lower())


def _is_empty(value: Any) -> bool:
    return value in (None, "", [], {})


def _parse_json_text(text: str) -> Any | None:
    candidate = (text or "").strip()
    if not candidate:
        return None

    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?", "", candidate)
        candidate = re.sub(r"```$", "", candidate).strip()

    for attempt in (candidate, candidate.replace("\n", "")):
        try:
            return json.loads(attempt)
        except json.JSONDecodeError:
            pass

    for open_char, close_char in (("{", "}"), ("[", "]")):
        start = candidate.find(open_char)
        end = candidate.rfind(close_char)
        if start == -1 or end == -1 or end <= start:
            continue
        snippet = candidate[start : end + 1]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            continue

    return None


def _unpack_mcp_result(raw: Any) -> Any:
    if not isinstance(raw, dict):
        return raw

    result = raw.get("result", raw)
    if not isinstance(result, dict):
        return result

    structured = result.get("structuredContent")
    if structured not in (None, ""):
        return structured

    content = result.get("content")
    if not isinstance(content, list):
        return result

    json_like: list[Any] = []
    text_like: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if "json" in item and item["json"] not in (None, ""):
            json_like.append(item["json"])
        if item.get("type") == "json" and "value" in item and item["value"] not in (None, ""):
            json_like.append(item["value"])
        if item.get("type") == "text" and item.get("text"):
            text_like.append(str(item["text"]))

    if len(json_like) == 1 and not text_like:
        return json_like[0]
    if json_like:
        return json_like

    if len(text_like) == 1:
        parsed = _parse_json_text(text_like[0])
        return parsed if parsed is not None else {"text": text_like[0]}

    if text_like:
        parsed_items = [_parse_json_text(item) for item in text_like]
        if any(item is not None for item in parsed_items):
            return [item if item is not None else text_like[index] for index, item in enumerate(parsed_items)]
        return {"texts": text_like}

    return result


def _collect_records(payload: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            records.append(node)
            for value in node.values():
                walk(value)
            return
        if isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return records


def _find_value(payload: Any, aliases: list[str]) -> Any:
    records = _collect_records(payload)
    if not records:
        return None

    normalized_aliases = [_normalize_key(alias) for alias in aliases]

    for alias in normalized_aliases:
        for record in records:
            for key, value in record.items():
                if _is_empty(value):
                    continue
                if _normalize_key(key) == alias:
                    return value

    for alias in normalized_aliases:
        for record in records:
            for key, value in record.items():
                if _is_empty(value):
                    continue
                normalized_key = _normalize_key(key)
                if alias and (alias in normalized_key or normalized_key in alias):
                    return value

    return None


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None

    text = value.strip().replace(",", "")
    if not text:
        return None

    multiplier = 1.0
    for unit, factor in (("万亿", 1e12), ("亿", 1e8), ("万", 1e4), ("元", 1.0)):
        if unit in text:
            multiplier = factor
            text = text.replace(unit, "")
            break

    text = text.replace("%", "")
    text = re.sub(r"[^\d.\-+]", "", text)
    if not text:
        return None

    try:
        return float(text) * multiplier
    except ValueError:
        return None


def _format_number(value: Any, digits: int = 2) -> str:
    if isinstance(value, str) and value.strip():
        stripped = value.strip()
        if re.search(r"[亿万元%]", stripped):
            return stripped

    number = _to_float(value)
    if number is None:
        return PLACEHOLDER
    return f"{number:.{digits}f}"


def _format_percent(value: Any) -> str:
    if isinstance(value, str) and "%" in value:
        number = _to_float(value)
        return PLACEHOLDER if number is None else f"{number:.2f}%"

    number = _to_float(value)
    if number is None:
        return PLACEHOLDER
    return f"{number:.2f}%"


def _format_market_cap(value: Any) -> str:
    if isinstance(value, str) and re.search(r"[亿万]", value):
        return value.strip()

    number = _to_float(value)
    if number is None:
        return PLACEHOLDER
    if abs(number) >= 1e12:
        return f"{number / 1e12:.2f}万亿"
    if abs(number) >= 1e8:
        return f"{number / 1e8:.2f}亿"
    if abs(number) >= 1e4:
        return f"{number / 1e4:.2f}万"
    return f"{number:.0f}"


def _format_money_flow(value: Any) -> str:
    if isinstance(value, str) and re.search(r"[亿万元]", value):
        return value.strip()

    number = _to_float(value)
    if number is None:
        return PLACEHOLDER

    sign = "+" if number > 0 else "-" if number < 0 else ""
    absolute = abs(number)
    if absolute >= 1e12:
        return f"{sign}{absolute / 1e12:.2f}万亿"
    if absolute >= 1e8:
        return f"{sign}{absolute / 1e8:.2f}亿"
    if absolute >= 1e4:
        return f"{sign}{absolute / 1e4:.2f}万"
    return f"{sign}{absolute:.0f}元"


def _read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_resolve_cache() -> dict[str, Any]:
    return _read_json_file(RESOLVE_CACHE_FILE, {})


def _save_resolve_cache(cache: dict[str, Any]) -> None:
    _write_json_file(RESOLVE_CACHE_FILE, cache)


def _detail_cache_path(stock_code: str) -> Path:
    return DETAIL_CACHE_DIR / f"{stock_code}.json"


def _load_detail_cache(stock_code: str) -> dict[str, Any] | None:
    return _read_json_file(_detail_cache_path(stock_code), None)


def _save_detail_cache(stock_code: str, payload: dict[str, Any]) -> None:
    cache_entry = {
        "cachedAt": int(time.time()),
        "payload": payload,
    }
    _write_json_file(_detail_cache_path(stock_code), cache_entry)


def _cache_is_fresh(cache_entry: dict[str, Any] | None) -> bool:
    if not cache_entry:
        return False
    cached_at = cache_entry.get("cachedAt")
    return isinstance(cached_at, (int, float)) and time.time() - cached_at <= DETAIL_CACHE_TTL_SECONDS


def _unwrap_payload_data(payload: Any) -> Any:
    if isinstance(payload, dict):
        data = payload.get("data")
        if data not in (None, ""):
            return data
    return payload


def _first_dict(payload: Any) -> dict[str, Any]:
    data = _unwrap_payload_data(payload)
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                return item
    return {}


def _list_of_dicts(payload: Any) -> list[dict[str, Any]]:
    data = _unwrap_payload_data(payload)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _round_or_none(value: Any, digits: int = 2) -> float | None:
    number = _to_float(value)
    if number is None:
        return None
    return round(number, digits)


def _ratio_to_percent_value(value: Any) -> float | None:
    number = _to_float(value)
    if number is None:
        return None
    if abs(number) <= 1:
        number *= 100
    return round(number, 2)


def _history_window() -> tuple[str, str]:
    now = datetime.now()
    return (
        (now - timedelta(days=HISTORY_LOOKBACK_DAYS)).strftime("%Y-%m-%d"),
        now.strftime("%Y-%m-%d"),
    )


def _sorted_history_items(payload: Any) -> list[dict[str, Any]]:
    items = _list_of_dicts(payload)
    items.sort(key=lambda item: str(item.get("tradeDate") or ""), reverse=True)
    return items


def _average(values: list[float]) -> float | None:
    clean_values = [value for value in values if isinstance(value, (int, float))]
    if not clean_values:
        return None
    return sum(clean_values) / len(clean_values)


def _normalize_realtime_volume(value: Any) -> float | None:
    volume = _to_float(value)
    if volume is None or volume <= 0:
        return None
    return volume * 100 if volume < 1e7 else volume


def _derive_volume_ratio(quote_data: dict[str, Any], history_items: list[dict[str, Any]]) -> float | None:
    latest_history = history_items[0] if history_items else {}
    current_volume = _to_float(latest_history.get("volume")) or _normalize_realtime_volume(quote_data.get("dealStockAmount"))

    baseline_items = history_items[1 : 1 + VOLUME_RATIO_BASE_DAYS] if len(history_items) > 1 else history_items[:VOLUME_RATIO_BASE_DAYS]
    baseline_volumes = [
        float(volume)
        for volume in (_to_float(item.get("volume")) for item in baseline_items)
        if isinstance(volume, (int, float)) and volume > 0
    ]
    average_volume = _average(baseline_volumes)
    if current_volume is None or average_volume in (None, 0):
        return None
    return round(current_volume / average_volume, 2)


def _derive_main_flow(
    quote_data: dict[str, Any],
    latest_history: dict[str, Any],
    volume_ratio: float | None,
) -> float | None:
    amount = _to_float(latest_history.get("amount")) or _to_float(quote_data.get("dealMoney"))
    close_price = _to_float(latest_history.get("closePrice")) or _to_float(quote_data.get("currentPrice"))
    high_price = _to_float(latest_history.get("highPrice")) or _to_float(quote_data.get("highPrice"))
    low_price = _to_float(latest_history.get("lowPrice")) or _to_float(quote_data.get("lowPrice"))
    vwap = _to_float(latest_history.get("vwap"))
    change_ratio = _to_float(latest_history.get("changePct"))
    if change_ratio is None:
        change_ratio = _to_float(quote_data.get("changeRatio"))
    if isinstance(change_ratio, (int, float)) and abs(change_ratio) > 1:
        change_ratio /= 100

    if amount is None or amount == 0:
        return None

    factor = 0.0
    terms = 0
    if close_price is not None and vwap not in (None, 0):
        factor += (close_price - vwap) / vwap * 0.6
        terms += 1
    if (
        close_price is not None
        and high_price is not None
        and low_price is not None
        and high_price > low_price
    ):
        factor += (((close_price - low_price) - (high_price - close_price)) / (high_price - low_price)) * 0.03
        terms += 1
    if change_ratio is not None:
        factor += change_ratio * 0.4
        terms += 1

    if terms == 0:
        return None

    factor = max(-0.12, min(0.12, factor))
    if volume_ratio is not None:
        factor *= max(0.6, min(1.8, volume_ratio))
    return round(amount * factor, 2)


def _score_gap(score_data: dict[str, Any], value_key: str, average_key: str) -> float | None:
    value = _to_float(score_data.get(value_key))
    average = _to_float(score_data.get(average_key))
    if value is None or average is None:
        return None
    return value - average


def _build_fallback_stock_analysis(
    *,
    change: float | None,
    volume_ratio: float | None,
    score_data: dict[str, Any],
    profitability_data: dict[str, Any],
) -> dict[str, Any]:
    total_gap = _score_gap(score_data, "score", "scoreAvg")
    skill_gap = _score_gap(score_data, "skillScore", "skillScoreAvg")
    finance_gap = _score_gap(score_data, "financeScore", "financeScoreAvg")
    industry_gap = _score_gap(score_data, "industryScore", "industryScoreAvg")
    emotion_gap = _score_gap(score_data, "emotionScore", "emotionScoreAvg")
    roe = _to_float(profitability_data.get("f2060"))

    tags: list[str] = []
    if total_gap is not None:
        if total_gap >= 15:
            tags.append("综合占优")
        elif total_gap <= -15:
            tags.append("综合承压")
    if skill_gap is not None:
        if skill_gap >= 10:
            tags.append("技术偏强")
        elif skill_gap <= -10:
            tags.append("技术偏弱")
    if finance_gap is not None:
        if finance_gap >= 10:
            tags.append("财务扎实")
        elif finance_gap <= -10:
            tags.append("财务承压")
    if industry_gap is not None:
        if industry_gap >= 8:
            tags.append("赛道占优")
        elif industry_gap <= -8:
            tags.append("赛道承压")
    if emotion_gap is not None:
        if emotion_gap >= 6:
            tags.append("情绪回暖")
        elif emotion_gap <= -6:
            tags.append("情绪偏冷")
    if volume_ratio is not None:
        if volume_ratio >= 1.5:
            tags.append("放量活跃")
        elif volume_ratio <= 0.8:
            tags.append("量能偏弱")
    if change is not None:
        if change >= 3:
            tags.append("涨势明显")
        elif change <= -3:
            tags.append("回撤明显")
    if roe is not None and roe >= 15:
        tags.append("高ROE")

    signal = 0
    if total_gap is not None:
        signal += 2 if total_gap >= 20 else 1 if total_gap >= 8 else -2 if total_gap <= -20 else -1 if total_gap <= -8 else 0
    if skill_gap is not None:
        signal += 1 if skill_gap >= 10 else -1 if skill_gap <= -10 else 0
    if emotion_gap is not None:
        signal += 1 if emotion_gap >= 6 else -1 if emotion_gap <= -6 else 0
    if change is not None:
        signal += 2 if change >= 3 else 1 if change >= 1 else -2 if change <= -3 else -1 if change <= -1 else 0
    if volume_ratio is not None:
        if volume_ratio >= 1.5 and (change or 0) >= 0:
            signal += 1
        elif volume_ratio <= 0.75 and (change or 0) < 0:
            signal -= 1

    if signal >= 4:
        sentiment = "强势"
    elif signal >= 2:
        sentiment = "偏强"
    elif signal <= -4:
        sentiment = "转弱"
    elif signal <= -2:
        sentiment = "偏弱"
    elif change is not None and abs(change) < 1 and volume_ratio is not None and volume_ratio >= 1.2:
        sentiment = "震荡"
    else:
        sentiment = "中性"

    return {"tags": _dedupe_tags(tags), "sentiment": sentiment}


def _user_agent_headers() -> dict[str, str]:
    return {"User-Agent": "Mozilla/5.0 Codex Stock Resolver"}


def _search_eastmoney(query: str) -> list[dict[str, Any]]:
    response = requests.get(
        "https://searchapi.eastmoney.com/api/suggest/get",
        params={"input": query, "type": 14},
        headers=_user_agent_headers(),
        timeout=SEARCH_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    results = data.get("QuotationCodeTable", {}).get("Data", [])
    return [item for item in results if isinstance(item, dict)]


def _search_sina(query: str) -> list[dict[str, Any]]:
    response = requests.get(
        "https://suggest3.sinajs.cn/suggest/type=11,12,13,14,15",
        params={"key": query},
        headers=_user_agent_headers(),
        timeout=SEARCH_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    match = re.search(r'"(.*)"', response.text)
    if not match:
        return []

    payload = match.group(1).strip()
    if not payload:
        return []

    results: list[dict[str, Any]] = []
    for item in payload.split(";"):
        parts = [part.strip() for part in item.split(",")]
        if len(parts) < 4:
            continue
        name = parts[0]
        code = parts[2]
        symbol = parts[3]
        if not code or not re.fullmatch(r"\d{6}", code):
            continue
        results.append(
            {
                "Code": code,
                "Name": name,
                "Classify": "AStock",
                "SecurityTypeName": symbol[:2].upper(),
                "QuoteID": symbol,
                "resolver": "sina",
            }
        )
    return results


def _score_resolved_candidate(query: str, candidate: dict[str, Any]) -> int:
    normalized_query = _normalize_text(query)
    code = str(candidate.get("Code") or candidate.get("UnifiedCode") or "").strip()
    name = str(candidate.get("Name") or "").strip()
    pinyin = str(candidate.get("PinYin") or "").strip().lower()
    classify = str(candidate.get("Classify") or "").strip()
    security_type = str(candidate.get("SecurityTypeName") or "").strip()

    score = 0
    if classify == "AStock":
        score += 30
    if "A" in security_type.upper():
        score += 10

    if normalized_query == code:
        score += 120
    if normalized_query == _normalize_text(name):
        score += 110
    if normalized_query and normalized_query == pinyin:
        score += 95
    if normalized_query and code.startswith(normalized_query):
        score += 70
    if normalized_query and _normalize_text(name).startswith(normalized_query):
        score += 65
    if normalized_query and normalized_query in _normalize_text(name):
        score += 50

    return score


def _to_resolved_stock(candidate: dict[str, Any], resolver: str) -> dict[str, Any]:
    return {
        "code": str(candidate.get("Code") or candidate.get("UnifiedCode") or "").strip(),
        "name": str(candidate.get("Name") or "").strip(),
        "market": str(candidate.get("SecurityTypeName") or candidate.get("Classify") or "").strip(),
        "quoteId": str(candidate.get("QuoteID") or "").strip(),
        "resolver": resolver,
    }


def resolve_stock_query(query: str) -> dict[str, Any]:
    normalized_query = _normalize_text(query)
    if not normalized_query:
        raise StockResolveError("股票名称或代码不能为空。")

    cache = _load_resolve_cache()
    cached_value = cache.get(normalized_query)
    if isinstance(cached_value, dict) and cached_value.get("code") and cached_value.get("name"):
        return cached_value

    search_strategies = (
        ("eastmoney", _search_eastmoney),
        ("sina", _search_sina),
    )

    best_candidate: dict[str, Any] | None = None
    best_score = -1
    for resolver, search_fn in search_strategies:
        try:
            candidates = search_fn(query)
        except Exception:
            continue

        for candidate in candidates:
            score = _score_resolved_candidate(query, candidate)
            if score <= best_score:
                continue
            best_candidate = _to_resolved_stock(candidate, resolver)
            best_score = score

        if best_score >= 100:
            break

    if not best_candidate or not best_candidate.get("code") or not best_candidate.get("name"):
        raise StockResolveError(f"未能识别“{query}”对应的 A 股股票，请检查输入。")

    cache[normalized_query] = best_candidate
    cache[best_candidate["code"]] = best_candidate
    cache[_normalize_text(best_candidate["name"])] = best_candidate
    _save_resolve_cache(cache)
    return best_candidate


def _empty_stock_payload(resolved: dict[str, Any], *, status_note: str | None = None) -> dict[str, Any]:
    return {
        "name": resolved.get("name") or "",
        "code": resolved.get("code") or "",
        "price": None,
        "change": None,
        "turnover": PLACEHOLDER,
        "pe": PLACEHOLDER,
        "pb": PLACEHOLDER,
        "marketCap": PLACEHOLDER,
        "volumeRatio": PLACEHOLDER,
        "mainFlow": PLACEHOLDER,
        "sentiment": PLACEHOLDER,
        "tags": [],
        "statusNote": status_note,
        "detailLoaded": False,
    }


def _call_tool_parsed(name: str, arguments: dict[str, Any]) -> Any:
    return _unpack_mcp_result(mcp.tool_call(name, arguments))


def _model_gate_reason() -> str | None:
    try:
        ensure_model_available()
        return None
    except Exception as exc:
        return f"AI 模型当前不可用，已跳过 MCP 实时拉取以避免额度浪费：{exc}"


def _build_stock_payload(
    resolved: dict[str, Any],
    bundle: dict[str, Any],
    *,
    include_analysis: bool,
    status_note: str | None = None,
    cached_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    quote_data = _first_dict(bundle.get("quote"))
    valuation_data = _first_dict(bundle.get("valuation"))
    basic_data = _first_dict(bundle.get("basic"))
    profitability_data = _first_dict(bundle.get("profitability"))
    score_data = _first_dict(bundle.get("score"))
    history_items = _sorted_history_items(bundle.get("history"))
    latest_history = history_items[0] if history_items else {}

    name = (
        str(quote_data.get("stockName") or "").strip()
        or str(basic_data.get("STOCKNAME") or basic_data.get("stockName") or "").strip()
        or str(latest_history.get("stockName") or "").strip()
        or str(resolved.get("name") or "").strip()
    )
    price = _round_or_none(quote_data.get("currentPrice") or latest_history.get("closePrice"))

    change = _ratio_to_percent_value(quote_data.get("changeRatio"))
    if change is None:
        change = _ratio_to_percent_value(latest_history.get("changePct"))

    turnover_value = _to_float(quote_data.get("turnOverRate"))
    if turnover_value is None:
        turnover_value = _to_float(latest_history.get("turnover"))

    pe_value = _to_float(valuation_data.get("f2250"))
    if pe_value is None:
        pe_value = _to_float(latest_history.get("peTtm"))

    pb_value = _to_float(valuation_data.get("f2290"))
    if pb_value is None:
        pb_value = _to_float(latest_history.get("pb"))

    market_cap_value = _to_float(quote_data.get("totalValue"))
    if market_cap_value is None:
        market_cap_value = _to_float(latest_history.get("marketCap"))

    volume_ratio_value = _derive_volume_ratio(quote_data, history_items)
    main_flow_value = _derive_main_flow(quote_data, latest_history, volume_ratio_value)
    fallback_analysis = _build_fallback_stock_analysis(
        change=change,
        volume_ratio=volume_ratio_value,
        score_data=score_data,
        profitability_data=profitability_data,
    )

    payload = {
        "name": name,
        "code": str(resolved.get("code") or ""),
        "price": price,
        "change": change,
        "turnover": _format_percent(turnover_value),
        "pe": _format_number(pe_value, digits=1),
        "pb": _format_number(pb_value, digits=1),
        "marketCap": _format_market_cap(market_cap_value),
        "volumeRatio": _format_number(volume_ratio_value, digits=2),
        "mainFlow": _format_money_flow(main_flow_value),
        "sentiment": fallback_analysis.get("sentiment") or PLACEHOLDER,
        "tags": list(fallback_analysis.get("tags") or []),
        "statusNote": status_note,
        "detailLoaded": False,
    }

    if cached_payload:
        cached_sentiment = str(cached_payload.get("sentiment") or "").strip()
        if cached_sentiment and cached_sentiment != PLACEHOLDER:
            payload["sentiment"] = cached_sentiment
        cached_tags = _dedupe_tags(list(cached_payload.get("tags") or []))
        if cached_tags:
            payload["tags"] = cached_tags
        payload["detailLoaded"] = bool(cached_payload.get("detailLoaded"))

    if not include_analysis:
        return payload

    analysis = analyze_stock_for_watchlist(payload, bundle)
    if analysis.get("sentiment") and analysis.get("sentiment") != PLACEHOLDER:
        payload["sentiment"] = analysis["sentiment"]
    if analysis.get("tags"):
        payload["tags"] = analysis["tags"]
    payload["detailLoaded"] = True

    analysis_error = analysis.get("error")
    if analysis_error:
        payload["statusNote"] = _join_notes(status_note, f"智能标签分析暂不可用：{analysis_error}")

    roe_value = profitability_data.get("f2060")
    if roe_value in (None, ""):
        roe_value = _find_value(profitability_data, ["roe", "roeWeighted", "净资产收益率", "roeavg"])
    if payload["tags"] and roe_value not in (None, "") and all("ROE" not in tag for tag in payload["tags"]):
        roe_number = _to_float(roe_value)
        if roe_number is not None and roe_number >= 10:
            payload["tags"].append("高ROE")

    payload["tags"] = _dedupe_tags(payload["tags"])
    return payload


def _join_notes(*parts: str | None) -> str | None:
    values = [part.strip() for part in parts if isinstance(part, str) and part.strip()]
    if not values:
        return None
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return "；".join(deduped)


def _dedupe_tags(tags: list[Any]) -> list[str]:
    cleaned: list[str] = []
    for tag in tags:
        text = str(tag).strip()
        if not text or text == PLACEHOLDER or len(text) > 12:
            continue
        if text not in cleaned:
            cleaned.append(text)
    return cleaned[:4]


def analyze_stock_for_watchlist(stock: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    if ANALYSIS_CLIENT is None:
        return {"tags": [], "sentiment": PLACEHOLDER, "error": "未配置 DeepSeek API Key"}

    if not bundle.get("quote"):
        return {"tags": [], "sentiment": PLACEHOLDER}

    condensed_context = {
        "stock": {
            "name": stock.get("name"),
            "code": stock.get("code"),
            "price": stock.get("price"),
            "change": stock.get("change"),
            "turnover": stock.get("turnover"),
            "pe": stock.get("pe"),
            "pb": stock.get("pb"),
            "marketCap": stock.get("marketCap"),
            "volumeRatio": stock.get("volumeRatio"),
            "mainFlow": stock.get("mainFlow"),
        },
        "sourceData": bundle,
    }

    system_prompt = (
        "你是 A 股个股标签与短线情绪分析引擎。"
        "请仅基于输入数据生成适合 UI 展示的结果，不要给投资建议，不要虚构事实。"
        "必须只返回 JSON，字段为 tags、sentiment、reason。"
        "tags 为 2 到 4 个短标签，每个 2 到 6 个汉字，避免空泛。"
        "sentiment 只能是 强势、偏强、震荡、中性、偏弱、转弱 之一。"
        "若信息不足，请减少标签数量并把 sentiment 设为中性。"
    )

    try:
        response = ANALYSIS_CLIENT.chat.completions.create(
            model=ANALYSIS_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(condensed_context, ensure_ascii=False),
                },
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        parsed = _parse_json_text(content)
        if not isinstance(parsed, dict):
            return {"tags": [], "sentiment": PLACEHOLDER, "error": "模型未返回有效 JSON"}

        tags = _dedupe_tags(list(parsed.get("tags") or []))
        sentiment = str(parsed.get("sentiment") or "").strip()
        if sentiment not in ANALYSIS_SENTIMENTS:
            sentiment = "中性"

        return {
            "tags": tags,
            "sentiment": sentiment,
            "reason": str(parsed.get("reason") or "").strip(),
        }
    except Exception as exc:
        return {"tags": [], "sentiment": PLACEHOLDER, "error": str(exc)}


def _get_live_bundle(stock_code: str, include_analysis: bool) -> tuple[dict[str, Any], str | None]:
    bundle: dict[str, Any] = {}
    note: str | None = None

    quote = _call_tool_parsed("get_stock_quote_realtime", {"stockCode": stock_code})
    bundle["quote"] = quote

    history_begin, history_end = _history_window()
    try:
        bundle["history"] = _call_tool_parsed(
            "list_stock_adjusted_quotes",
            {
                "stockCode": stock_code,
                "beginDate": history_begin,
                "endDate": history_end,
                "pageNum": 1,
                "pageSize": HISTORY_PAGE_SIZE,
            },
        )
    except Exception as exc:
        note = _join_notes(note, f"历史行情获取失败：{exc}")

    try:
        bundle["valuation"] = _call_tool_parsed("get_stock_finance_valuation", {"stockCode": stock_code})
    except Exception as exc:
        note = _join_notes(note, f"估值指标获取失败：{exc}")

    try:
        bundle["score"] = _call_tool_parsed("get_stock_score", {"stockCode": stock_code})
    except Exception as exc:
        note = _join_notes(note, f"综合得分获取失败：{exc}")

    if include_analysis:
        try:
            bundle["basic"] = _call_tool_parsed("get_stock_basic_info", {"stockCode": stock_code})
        except Exception as exc:
            note = _join_notes(note, f"基本信息获取失败：{exc}")

        try:
            bundle["profitability"] = _call_tool_parsed(
                "get_stock_finance_profit_ability",
                {"stockCode": stock_code},
            )
        except Exception as exc:
            note = _join_notes(note, f"盈利能力获取失败：{exc}")

    return bundle, note


def _payload_response(stock: dict[str, Any], *, resolver: str, mcp_status: str) -> dict[str, Any]:
    return {
        "stock": stock,
        "meta": {
            "resolver": resolver,
            "mcpStatus": mcp_status,
            "timestamp": int(time.time()),
        },
    }


def get_watchlist_stock(query: str) -> dict[str, Any]:
    resolved = resolve_stock_query(query)
    cache_entry = _load_detail_cache(resolved["code"])
    cached_payload = cache_entry.get("payload") if isinstance(cache_entry, dict) else None

    if _cache_is_fresh(cache_entry) and isinstance(cached_payload, dict):
        return _payload_response(cached_payload, resolver=resolved["resolver"], mcp_status="cache")

    model_gate_reason = _model_gate_reason()
    if model_gate_reason:
        if isinstance(cached_payload, dict):
            cached_copy = dict(cached_payload)
            cached_copy["statusNote"] = _join_notes(cached_copy.get("statusNote"), model_gate_reason)
            return _payload_response(cached_copy, resolver=resolved["resolver"], mcp_status="cache_stale")
        return _payload_response(
            _empty_stock_payload(resolved, status_note=model_gate_reason),
            resolver=resolved["resolver"],
            mcp_status="model_blocked",
        )

    try:
        bundle, note = _get_live_bundle(resolved["code"], include_analysis=False)
        payload = _build_stock_payload(
            resolved,
            bundle,
            include_analysis=False,
            status_note=note,
            cached_payload=cached_payload if isinstance(cached_payload, dict) else None,
        )
        _save_detail_cache(resolved["code"], payload)
        return _payload_response(payload, resolver=resolved["resolver"], mcp_status="ready")
    except mcp.McpResourcePackageError:
        note = (
            "今日投资 MCP 已连通，但当前账号没有可用资源包，"
            "所以暂时无法拉取实时行情；资源包恢复后即可直接生效。"
        )
        if isinstance(cached_payload, dict):
            cached_copy = dict(cached_payload)
            cached_copy["statusNote"] = _join_notes(cached_copy.get("statusNote"), note)
            return _payload_response(cached_copy, resolver=resolved["resolver"], mcp_status="cache_stale")
        return _payload_response(
            _empty_stock_payload(resolved, status_note=note),
            resolver=resolved["resolver"],
            mcp_status="quota_blocked",
        )
    except Exception as exc:
        if isinstance(cached_payload, dict):
            cached_copy = dict(cached_payload)
            cached_copy["statusNote"] = _join_notes(
                cached_copy.get("statusNote"),
                f"实时行情刷新失败，当前展示的是最近一次缓存数据：{exc}",
            )
            return _payload_response(cached_copy, resolver=resolved["resolver"], mcp_status="cache_stale")
        return _payload_response(
            _empty_stock_payload(resolved, status_note=f"实时行情获取失败：{exc}"),
            resolver=resolved["resolver"],
            mcp_status="error",
        )


def get_stock_detail(stock_code: str) -> dict[str, Any]:
    resolved = resolve_stock_query(stock_code)
    cache_entry = _load_detail_cache(resolved["code"])
    cached_payload = cache_entry.get("payload") if isinstance(cache_entry, dict) else None

    if _cache_is_fresh(cache_entry) and isinstance(cached_payload, dict) and cached_payload.get("detailLoaded"):
        return _payload_response(cached_payload, resolver=resolved["resolver"], mcp_status="cache")

    model_gate_reason = _model_gate_reason()
    if model_gate_reason:
        if isinstance(cached_payload, dict):
            cached_copy = dict(cached_payload)
            cached_copy["statusNote"] = _join_notes(cached_copy.get("statusNote"), model_gate_reason)
            return _payload_response(cached_copy, resolver=resolved["resolver"], mcp_status="cache_stale")
        return _payload_response(
            _empty_stock_payload(resolved, status_note=model_gate_reason),
            resolver=resolved["resolver"],
            mcp_status="model_blocked",
        )

    try:
        bundle, note = _get_live_bundle(resolved["code"], include_analysis=True)
        payload = _build_stock_payload(
            resolved,
            bundle,
            include_analysis=True,
            status_note=note,
            cached_payload=cached_payload if isinstance(cached_payload, dict) else None,
        )
        _save_detail_cache(resolved["code"], payload)
        return _payload_response(payload, resolver=resolved["resolver"], mcp_status="ready")
    except mcp.McpResourcePackageError:
        note = (
            "今日投资 MCP 已连通，但当前账号没有可用资源包，"
            "详情指标和模型分析会在资源包恢复后自动可用。"
        )
        if isinstance(cached_payload, dict):
            cached_copy = dict(cached_payload)
            cached_copy["statusNote"] = _join_notes(cached_copy.get("statusNote"), note)
            return _payload_response(cached_copy, resolver=resolved["resolver"], mcp_status="cache_stale")
        return _payload_response(
            _empty_stock_payload(resolved, status_note=note),
            resolver=resolved["resolver"],
            mcp_status="quota_blocked",
        )
    except Exception as exc:
        if isinstance(cached_payload, dict):
            cached_copy = dict(cached_payload)
            cached_copy["statusNote"] = _join_notes(
                cached_copy.get("statusNote"),
                f"详情刷新失败，当前展示的是最近一次缓存数据：{exc}",
            )
            return _payload_response(cached_copy, resolver=resolved["resolver"], mcp_status="cache_stale")
        return _payload_response(
            _empty_stock_payload(resolved, status_note=f"个股详情获取失败：{exc}"),
            resolver=resolved["resolver"],
            mcp_status="error",
        )
