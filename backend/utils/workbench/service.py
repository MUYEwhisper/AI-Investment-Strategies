from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from utils.auth.context import get_current_user_id
from utils.db.mysql import ensure_mysql_schema, get_mysql_connection
from utils.models.availability import ANALYSIS_CLIENT, ANALYSIS_MODEL
from utils.sectors.service import _extract_sector_candidates
from utils.stocks.service import (
    PLACEHOLDER,
    PROJECT_ROOT,
    _call_tool_parsed,
    _find_value,
    _history_window,
    _join_notes,
    _parse_json_text,
    _to_float,
    get_stock_detail,
    get_watchlist_stock,
    resolve_stock_query,
)

LEGACY_SQLITE_PATH = PROJECT_ROOT / "data" / "app.db"

DEFAULT_PROFILE_ANSWERS = {
    "experience": "newbie",
    "lossTolerance": "medium",
    "horizon": "medium",
    "objective": "growth",
    "style": "balanced",
    "tradingFrequency": "weekly",
    "decisionStyle": "research",
    "positionStyle": "balanced",
    "supplementDescription": "",
}

PROFILE_SCORE_MAP = {
    "experience": {
        "newbie": 20,
        "starter": 36,
        "experienced": 64,
        "advanced": 82,
        "systematic": 94,
    },
    "lossTolerance": {
        "very_low": 8,
        "low": 20,
        "medium": 38,
        "high": 68,
        "very_high": 92,
    },
    "horizon": {
        "ultra_short": 12,
        "short": 24,
        "medium": 48,
        "long": 72,
        "very_long": 88,
    },
    "objective": {
        "capital_preserve": 16,
        "income": 28,
        "steady": 40,
        "growth": 68,
        "aggressive": 92,
    },
    "style": {
        "income": 18,
        "value": 32,
        "balanced": 48,
        "growth": 72,
        "theme": 88,
    },
    "tradingFrequency": {"daily": 88, "weekly": 62, "monthly": 42, "event_driven": 74},
    "decisionStyle": {"research": 46, "technical": 66, "news": 74, "blended": 58},
    "positionStyle": {"light": 24, "balanced": 48, "concentrated": 76, "aggressive": 90},
}

PROFILE_WEIGHT_MAP = {
    "experience": 0.14,
    "lossTolerance": 0.24,
    "horizon": 0.16,
    "objective": 0.12,
    "style": 0.10,
    "tradingFrequency": 0.08,
    "decisionStyle": 0.08,
    "positionStyle": 0.08,
}

RISK_LEVEL_CONFIG = [
    ("保守型", 25, 0.12, 0.24, "更适合低波动、分散化、偏防守的组合"),
    ("稳健型", 45, 0.18, 0.30, "适合均衡配置，控制热点集中暴露"),
    ("平衡型", 65, 0.25, 0.38, "可接受适度波动，适合行业分散布局"),
    ("成长型", 82, 0.32, 0.46, "可接受较高波动，适合成长风格配置"),
    ("进取型", 101, 0.40, 0.54, "可承受高波动，但仍需控制极端集中"),
]

SENTIMENT_SCORE_MAP = {
    "强势": 88,
    "偏强": 74,
    "震荡": 58,
    "中性": 52,
    "偏弱": 38,
    "转弱": 24,
}

HOT_TAGS = {"放量活跃", "涨势明显", "情绪回暖", "技术偏强", "强势"}
UNKNOWN_SECTOR_NAME = "未识别行业"


class WorkbenchServiceError(RuntimeError):
    """综合工作台服务错误。"""


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _connect():
    ensure_mysql_schema()
    return get_mysql_connection()


def _init_db() -> None:
    ensure_mysql_schema()


def _resolve_user_id(user_id: int | None = None) -> int:
    if user_id is not None:
        return int(user_id)
    return int(get_current_user_id())


def _read_legacy_profile() -> dict[str, Any] | None:
    if not LEGACY_SQLITE_PATH.exists():
        return None
    try:
        with sqlite3.connect(LEGACY_SQLITE_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM investor_profile WHERE id = 1").fetchone()
            return dict(row) if row else None
    except Exception:
        return None


def _read_legacy_simulation() -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if not LEGACY_SQLITE_PATH.exists():
        return None, []
    try:
        with sqlite3.connect(LEGACY_SQLITE_PATH) as conn:
            conn.row_factory = sqlite3.Row
            account = conn.execute("SELECT * FROM sim_account WHERE id = 1").fetchone()
            trades = conn.execute("SELECT * FROM sim_trades ORDER BY id ASC").fetchall()
            return (dict(account) if account else None), [dict(item) for item in trades]
    except Exception:
        return None, []


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _safe_json_loads(text: str | None, default: Any) -> Any:
    if not text:
        return default
    parsed = _parse_json_text(text)
    return default if parsed is None else parsed


def _build_rule_profile(answers: dict[str, Any]) -> dict[str, Any]:
    normalized = {**DEFAULT_PROFILE_ANSWERS, **(answers or {})}
    total_score = 0.0
    for key, weight in PROFILE_WEIGHT_MAP.items():
        options = PROFILE_SCORE_MAP.get(key, {})
        total_score += float(options.get(str(normalized.get(key)), 50)) * weight

    risk_score = int(round(_clamp(total_score, 0, 100)))
    risk_level = "平衡型"
    max_stock_weight = 0.25
    max_sector_weight = 0.38
    recommendation = "适合行业分散的均衡组合。"
    for level, upper_bound, stock_weight, sector_weight, desc in RISK_LEVEL_CONFIG:
        if risk_score < upper_bound:
            risk_level = level
            max_stock_weight = stock_weight
            max_sector_weight = sector_weight
            recommendation = desc
            break

    basis = [
        f"经验水平识别为 {normalized.get('experience')}",
        f"可承受回撤倾向 {normalized.get('lossTolerance')}",
        f"投资周期偏好 {normalized.get('horizon')}",
    ]
    return {
        "riskScore": risk_score,
        "riskLevel": risk_level,
        "maxSingleStockWeight": round(max_stock_weight, 2),
        "maxSingleSectorWeight": round(max_sector_weight, 2),
        "recommendation": recommendation,
        "summary": recommendation,
        "analysisBasis": basis,
        "analysisSource": "规则评分（AI 不可用时回退）",
        "answers": normalized,
        "updatedAt": _now_text(),
    }


def _analyze_profile_with_ai(answers: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    if ANALYSIS_CLIENT is None:
        return fallback

    prompt_payload = {
        "answers": answers,
        "fallback": {
            "riskScore": fallback["riskScore"],
            "riskLevel": fallback["riskLevel"],
            "maxSingleStockWeight": fallback["maxSingleStockWeight"],
            "maxSingleSectorWeight": fallback["maxSingleSectorWeight"],
        },
    }
    system_prompt = (
        "你是大学生投资者画像分析助手。"
        "请根据用户选择和补充描述，生成客观、谨慎、可解释的投资画像。"
        "严格只返回 JSON，字段为 riskScore、riskLevel、maxSingleStockWeight、"
        "maxSingleSectorWeight、summary、recommendation、analysisBasis。"
        "riskScore 为 0-100 整数；riskLevel 只能是 保守型、稳健型、平衡型、成长型、进取型；"
        "maxSingleStockWeight 与 maxSingleSectorWeight 为 0 到 1 之间的小数；"
        "summary 和 recommendation 用中文简洁表达；analysisBasis 为 3 到 5 条中文短句。"
        "不得承诺收益，不得给出具体买卖推荐。"
    )

    try:
        response = ANALYSIS_CLIENT.chat.completions.create(
            model=ANALYSIS_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False)},
            ],
            temperature=0.25,
            response_format={"type": "json_object"},
        )
        parsed = _parse_json_text(response.choices[0].message.content or "{}")
        if not isinstance(parsed, dict):
            return fallback

        score = int(round(_clamp(float(parsed.get("riskScore") or fallback["riskScore"]), 0, 100)))
        level = str(parsed.get("riskLevel") or fallback["riskLevel"]).strip()
        if level not in {item[0] for item in RISK_LEVEL_CONFIG}:
            level = fallback["riskLevel"]

        basis = [str(item).strip() for item in list(parsed.get("analysisBasis") or []) if str(item).strip()]
        return {
            "riskScore": score,
            "riskLevel": level,
            "maxSingleStockWeight": round(_clamp(float(parsed.get("maxSingleStockWeight") or fallback["maxSingleStockWeight"]), 0.08, 0.5), 2),
            "maxSingleSectorWeight": round(_clamp(float(parsed.get("maxSingleSectorWeight") or fallback["maxSingleSectorWeight"]), 0.18, 0.65), 2),
            "recommendation": str(parsed.get("recommendation") or fallback["recommendation"]).strip() or fallback["recommendation"],
            "summary": str(parsed.get("summary") or fallback["summary"]).strip() or fallback["summary"],
            "analysisBasis": basis[:5] or fallback["analysisBasis"],
            "analysisSource": "AI 画像分析",
            "answers": {**DEFAULT_PROFILE_ANSWERS, **(answers or {})},
            "updatedAt": _now_text(),
        }
    except Exception:
        return fallback


def _evaluate_profile(answers: dict[str, Any]) -> dict[str, Any]:
    fallback = _build_rule_profile(answers)
    return _analyze_profile_with_ai(answers, fallback)


def get_investor_profile(user_id: int | None = None) -> dict[str, Any]:
    _init_db()
    uid = _resolve_user_id(user_id)
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM investor_profiles WHERE user_id = %s LIMIT 1", (uid,))
            row = cursor.fetchone()
            if not row:
                legacy = _read_legacy_profile()
                if legacy:
                    row = legacy
                    cursor.execute(
                        """
                        INSERT INTO investor_profiles (
                          user_id, risk_score, risk_level, max_single_stock_weight, max_single_sector_weight,
                          summary_text, recommendation, analysis_basis_json, analysis_source, answers_json, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                          risk_score = VALUES(risk_score),
                          risk_level = VALUES(risk_level),
                          max_single_stock_weight = VALUES(max_single_stock_weight),
                          max_single_sector_weight = VALUES(max_single_sector_weight),
                          summary_text = VALUES(summary_text),
                          recommendation = VALUES(recommendation),
                          analysis_basis_json = VALUES(analysis_basis_json),
                          analysis_source = VALUES(analysis_source),
                          answers_json = VALUES(answers_json),
                          updated_at = VALUES(updated_at)
                        """,
                        (
                            uid,
                            int(legacy.get("risk_score") or 0),
                            str(legacy.get("risk_level") or "平衡型"),
                            float(legacy.get("max_single_stock_weight") or 0.25),
                            float(legacy.get("max_single_sector_weight") or 0.38),
                            str(legacy.get("summary_text") or legacy.get("recommendation") or ""),
                            str(legacy.get("recommendation") or ""),
                            str(legacy.get("analysis_basis_json") or "[]"),
                            str(legacy.get("analysis_source") or ""),
                            str(legacy.get("answers_json") or "{}"),
                            str(legacy.get("updated_at") or _now_text()),
                        ),
                    )
                    conn.commit()
                else:
                    profile = _evaluate_profile(DEFAULT_PROFILE_ANSWERS)
                    save_investor_profile(profile["answers"], uid)
                    return profile

    return {
        "riskScore": int(row["risk_score"]),
        "riskLevel": str(row["risk_level"]),
        "maxSingleStockWeight": float(row["max_single_stock_weight"]),
        "maxSingleSectorWeight": float(row["max_single_sector_weight"]),
        "summary": str(row["summary_text"] or row["recommendation"]),
        "recommendation": str(row["recommendation"]),
        "analysisBasis": _safe_json_loads(row["analysis_basis_json"], []),
        "analysisSource": str(row["analysis_source"] or "AI 综合分析"),
        "answers": _safe_json_loads(row["answers_json"], DEFAULT_PROFILE_ANSWERS),
        "updatedAt": str(row["updated_at"]),
    }


def save_investor_profile(answers: dict[str, Any], user_id: int | None = None) -> dict[str, Any]:
    _init_db()
    uid = _resolve_user_id(user_id)
    profile = _evaluate_profile(answers)
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO investor_profiles (
                  user_id, risk_score, risk_level, max_single_stock_weight, max_single_sector_weight,
                  summary_text, recommendation, analysis_basis_json, analysis_source, answers_json, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  risk_score = VALUES(risk_score),
                  risk_level = VALUES(risk_level),
                  max_single_stock_weight = VALUES(max_single_stock_weight),
                  max_single_sector_weight = VALUES(max_single_sector_weight),
                  summary_text = VALUES(summary_text),
                  recommendation = VALUES(recommendation),
                  analysis_basis_json = VALUES(analysis_basis_json),
                  analysis_source = VALUES(analysis_source),
                  answers_json = VALUES(answers_json),
                  updated_at = VALUES(updated_at)
                """,
                (
                    uid,
                    profile["riskScore"],
                    profile["riskLevel"],
                    profile["maxSingleStockWeight"],
                    profile["maxSingleSectorWeight"],
                    profile["summary"],
                    profile["recommendation"],
                    json.dumps(profile["analysisBasis"], ensure_ascii=False),
                    profile["analysisSource"],
                    json.dumps(profile["answers"], ensure_ascii=False),
                    profile["updatedAt"],
                ),
            )
        conn.commit()
    return profile


def _ensure_sim_account(user_id: int | None = None) -> int:
    _init_db()
    uid = _resolve_user_id(user_id)
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM sim_accounts WHERE user_id = %s LIMIT 1", (uid,))
            row = cursor.fetchone()
            if row:
                return uid
            legacy_account, legacy_trades = _read_legacy_simulation()
            now = _now_text()
            initial_cash = float((legacy_account or {}).get("initial_cash") or 100000.0)
            cash = float((legacy_account or {}).get("cash") or initial_cash)
            created_at = str((legacy_account or {}).get("created_at") or now)
            updated_at = str((legacy_account or {}).get("updated_at") or now)
            cursor.execute(
                """
                INSERT INTO sim_accounts (user_id, initial_cash, cash, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (uid, initial_cash, cash, created_at, updated_at),
            )
            for trade in legacy_trades:
                cursor.execute(
                    """
                    INSERT INTO sim_trades (
                      user_id, stock_code, stock_name, side, quantity, price, amount, fees,
                      rationale, plan_horizon, take_profit, stop_loss, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        uid,
                        str(trade.get("stock_code") or ""),
                        str(trade.get("stock_name") or ""),
                        str(trade.get("side") or "buy"),
                        int(trade.get("quantity") or 0),
                        float(trade.get("price") or 0.0),
                        float(trade.get("amount") or 0.0),
                        float(trade.get("fees") or 0.0),
                        str(trade.get("rationale") or ""),
                        str(trade.get("plan_horizon") or ""),
                        str(trade.get("take_profit") or ""),
                        str(trade.get("stop_loss") or ""),
                        str(trade.get("created_at") or now),
                    ),
                )
        conn.commit()
    return uid


def reset_simulation_account(initial_cash: float = 100000.0, user_id: int | None = None) -> dict[str, Any]:
    uid = _ensure_sim_account(user_id)
    amount = round(max(float(initial_cash or 100000.0), 1000.0), 2)
    now = _now_text()
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM sim_trades WHERE user_id = %s", (uid,))
            cursor.execute(
                """
                INSERT INTO sim_accounts (user_id, initial_cash, cash, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  initial_cash = VALUES(initial_cash),
                  cash = VALUES(cash),
                  updated_at = VALUES(updated_at)
                """,
                (uid, amount, amount, now, now),
            )
        conn.commit()
    return get_simulation_account(uid)


def _load_trades_desc(user_id: int | None = None) -> list[dict[str, Any]]:
    uid = _ensure_sim_account(user_id)
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM sim_trades WHERE user_id = %s ORDER BY id DESC", (uid,))
            return list(cursor.fetchall() or [])


def _load_trades_asc(user_id: int | None = None) -> list[dict[str, Any]]:
    uid = _ensure_sim_account(user_id)
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM sim_trades WHERE user_id = %s ORDER BY id ASC", (uid,))
            return list(cursor.fetchall() or [])


def _extract_sector_info(stock_code: str) -> tuple[str, str]:
    try:
        # 优先使用融合行情接口，直接拿到今日投资数据市场返回的行业/概念归属。
        merge_payload = _call_tool_parsed("get_stock_realtime_quote_merge", {"stockCode": stock_code})
        candidates = _extract_sector_candidates(merge_payload, stock_code)

        for candidate in candidates:
            if str(candidate.get("kind") or "").strip() != "industry":
                continue
            sector_name = str(candidate.get("name") or "").strip()
            if sector_name:
                return sector_name, str(candidate.get("code") or "").strip()

        for candidate in candidates:
            sector_name = str(candidate.get("name") or "").strip()
            if sector_name:
                return sector_name, str(candidate.get("code") or "").strip()
    except Exception:
        pass

    try:
        quote = _call_tool_parsed("get_stock_quote_realtime", {"stockCode": stock_code})
        sector_name = str(
            _find_value(quote, ["industryName", "industry", "所属行业", "swLv3Name", "hyName"]) or UNKNOWN_SECTOR_NAME
        ).strip()
        sector_code = str(
            _find_value(quote, ["industryCode", "行业代码", "swLv3Code", "hyCode"]) or ""
        ).strip()
        return sector_name or UNKNOWN_SECTOR_NAME, sector_code
    except Exception:
        return UNKNOWN_SECTOR_NAME, ""


def _refresh_positions_sector_info(positions: list[dict[str, Any]]) -> None:
    sector_cache: dict[str, tuple[str, str]] = {}
    for item in positions:
        code = str(item.get("code") or "").strip()
        if not code:
            item["sectorName"] = str(item.get("sectorName") or UNKNOWN_SECTOR_NAME).strip() or UNKNOWN_SECTOR_NAME
            item["sectorCode"] = str(item.get("sectorCode") or "").strip()
            continue

        if code not in sector_cache:
            sector_cache[code] = _extract_sector_info(code)

        sector_name, sector_code = sector_cache[code]
        item["sectorName"] = sector_name or UNKNOWN_SECTOR_NAME
        item["sectorCode"] = sector_code


def _get_live_snapshot(stock_code: str, stock_name: str = "") -> dict[str, Any]:
    try:
        payload = get_watchlist_stock(stock_code)
        stock = dict(payload.get("stock") or {})
    except Exception as exc:
        resolved = resolve_stock_query(stock_code)
        stock = {
            "name": stock_name or resolved.get("name") or stock_code,
            "code": resolved.get("code") or stock_code,
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
            "statusNote": f"实时行情暂不可用：{exc}",
            "detailLoaded": False,
        }

    sector_name, sector_code = _extract_sector_info(str(stock.get("code") or stock_code))
    stock["sectorName"] = sector_name
    stock["sectorCode"] = sector_code
    if stock_name and not stock.get("name"):
        stock["name"] = stock_name
    return stock


def _compute_positions_with_live_data(user_id: int | None = None) -> dict[str, Any]:
    uid = _ensure_sim_account(user_id)
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM sim_accounts WHERE user_id = %s LIMIT 1", (uid,))
            account_row = cursor.fetchone()

    if not account_row:
        raise WorkbenchServiceError("未找到模拟账户，请先初始化账户。")

    trades = _load_trades_asc(uid)
    position_map: dict[str, dict[str, Any]] = {}
    realized_pnl = 0.0

    for trade in trades:
        code = str(trade["stock_code"])
        item = position_map.setdefault(
            code,
            {
                "code": code,
                "name": str(trade["stock_name"]),
                "quantity": 0,
                "costAmount": 0.0,
                "buyAmount": 0.0,
                "sellAmount": 0.0,
                "tradeCount": 0,
                "lastTradeAt": str(trade["created_at"]),
                "lastRationale": str(trade["rationale"]),
                "planHorizon": str(trade["plan_horizon"]),
                "takeProfit": str(trade["take_profit"]),
                "stopLoss": str(trade["stop_loss"]),
            },
        )

        side = str(trade["side"])
        quantity = int(trade["quantity"])
        amount = float(trade["amount"])
        fees = float(trade["fees"])
        item["tradeCount"] += 1
        item["lastTradeAt"] = str(trade["created_at"])
        item["lastRationale"] = str(trade["rationale"])
        item["planHorizon"] = str(trade["plan_horizon"])
        item["takeProfit"] = str(trade["take_profit"])
        item["stopLoss"] = str(trade["stop_loss"])

        if side == "buy":
            item["quantity"] += quantity
            item["costAmount"] += amount + fees
            item["buyAmount"] += amount + fees
            continue

        if item["quantity"] <= 0:
            continue

        average_cost = item["costAmount"] / item["quantity"]
        sell_cost = average_cost * quantity
        realized_pnl += amount - fees - sell_cost
        item["quantity"] -= quantity
        item["costAmount"] -= sell_cost
        item["sellAmount"] += amount - fees

    open_positions: list[dict[str, Any]] = []
    for item in position_map.values():
        if item["quantity"] <= 0:
            continue
        live = _get_live_snapshot(item["code"], item["name"])
        last_price = _to_float(live.get("price"))
        market_value = (last_price or 0.0) * item["quantity"]
        avg_cost = item["costAmount"] / item["quantity"] if item["quantity"] else 0.0
        unrealized_pnl = market_value - item["costAmount"] if market_value else 0.0
        pnl_ratio = (unrealized_pnl / item["costAmount"] * 100) if item["costAmount"] else 0.0
        open_positions.append(
            {
                "code": item["code"],
                "name": item["name"],
                "quantity": int(item["quantity"]),
                "averageCost": round(avg_cost, 2),
                "costAmount": round(item["costAmount"], 2),
                "marketValue": round(market_value, 2),
                "lastPrice": round(last_price, 2) if last_price is not None else None,
                "unrealizedPnl": round(unrealized_pnl, 2),
                "pnlRatio": round(pnl_ratio, 2),
                "change": live.get("change"),
                "sentiment": live.get("sentiment") or PLACEHOLDER,
                "tags": list(live.get("tags") or []),
                "sectorName": live.get("sectorName") or "未知板块",
                "sectorCode": live.get("sectorCode") or "",
                "turnover": live.get("turnover") or PLACEHOLDER,
                "volumeRatio": live.get("volumeRatio") or PLACEHOLDER,
                "mainFlow": live.get("mainFlow") or PLACEHOLDER,
                "takeProfit": item["takeProfit"],
                "stopLoss": item["stopLoss"],
                "planHorizon": item["planHorizon"],
                "lastRationale": item["lastRationale"],
                "lastTradeAt": item["lastTradeAt"],
            }
        )

    open_positions.sort(key=lambda position: float(position.get("marketValue") or 0), reverse=True)

    cash = float(account_row["cash"])
    equity = cash + sum(float(position.get("marketValue") or 0) for position in open_positions)
    total_pnl = realized_pnl + sum(float(position.get("unrealizedPnl") or 0) for position in open_positions)

    trade_items = [
        {
            "id": int(row["id"]),
            "stockCode": str(row["stock_code"]),
            "stockName": str(row["stock_name"]),
            "side": str(row["side"]),
            "quantity": int(row["quantity"]),
            "price": float(row["price"]),
            "amount": float(row["amount"]),
            "fees": float(row["fees"]),
            "rationale": str(row["rationale"]),
            "planHorizon": str(row["plan_horizon"]),
            "takeProfit": str(row["take_profit"]),
            "stopLoss": str(row["stop_loss"]),
            "createdAt": str(row["created_at"]),
        }
        for row in reversed(trades)
    ]

    return {
        "account": {
            "initialCash": round(float(account_row["initial_cash"]), 2),
            "cash": round(cash, 2),
            "equity": round(equity, 2),
            "positionValue": round(sum(float(position.get("marketValue") or 0) for position in open_positions), 2),
            "realizedPnl": round(realized_pnl, 2),
            "totalPnl": round(total_pnl, 2),
            "positionCount": len(open_positions),
            "tradeCount": len(trade_items),
            "updatedAt": str(account_row["updated_at"]),
        },
        "positions": open_positions,
        "trades": trade_items,
    }


def get_simulation_account(user_id: int | None = None) -> dict[str, Any]:
    uid = _ensure_sim_account(user_id)
    return _compute_positions_with_live_data(uid)


def _estimate_trade_price(stock_code: str, stock_name: str) -> tuple[float, str]:
    snapshot = _get_live_snapshot(stock_code, stock_name)
    price = _to_float(snapshot.get("price"))
    if price is None or price <= 0:
        raise WorkbenchServiceError("当前无法获取该标的有效价格，请稍后重试。")
    return round(price, 2), str(snapshot.get("name") or stock_name or stock_code)


def _calculate_trade_fees(amount: float) -> float:
    # 手续费按万分之一收取，单笔最低 5 元，买卖一致。
    return round(max(float(amount) * 0.0001, 5.0), 2)


def create_sim_trade(payload: dict[str, Any], user_id: int | None = None) -> dict[str, Any]:
    uid = _ensure_sim_account(user_id)

    stock_code = str(payload.get("stockCode") or "").strip()
    stock_name = str(payload.get("stockName") or "").strip()
    side = str(payload.get("side") or "buy").strip().lower()
    quantity = int(payload.get("quantity") or 0)
    rationale = str(payload.get("rationale") or "").strip()
    plan_horizon = str(payload.get("planHorizon") or "中线").strip()
    take_profit = str(payload.get("takeProfit") or "达到目标收益后分批止盈").strip()
    stop_loss = str(payload.get("stopLoss") or "跌破关键位后严格止损").strip()

    if not stock_code:
        raise WorkbenchServiceError("股票代码不能为空。")
    if side not in {"buy", "sell"}:
        raise WorkbenchServiceError("交易方向仅支持 buy 或 sell。")
    if quantity <= 0 or quantity % 100 != 0:
        raise WorkbenchServiceError("A 股交易数量需为正整数，且为 100 的整数倍。")
    if len(rationale) < 4:
        raise WorkbenchServiceError("交易理由至少 4 个字，便于 AI 复盘分析。")

    price, resolved_name = _estimate_trade_price(stock_code, stock_name)
    amount = round(price * quantity, 2)
    fees = _calculate_trade_fees(amount)

    snapshot = _compute_positions_with_live_data(uid)
    account = snapshot["account"]
    holdings = {position["code"]: position for position in snapshot["positions"]}

    if side == "buy" and float(account["cash"]) < amount + fees:
        raise WorkbenchServiceError("账户可用资金不足，无法完成本次买入。")

    existing_position = holdings.get(stock_code)
    if side == "sell" and (not existing_position or int(existing_position["quantity"]) < quantity):
        raise WorkbenchServiceError("当前持仓数量不足，无法完成本次卖出。")

    now = _now_text()
    new_cash = float(account["cash"]) - amount - fees if side == "buy" else float(account["cash"]) + amount - fees
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO sim_trades (
                  user_id, stock_code, stock_name, side, quantity, price, amount, fees,
                  rationale, plan_horizon, take_profit, stop_loss, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    uid,
                    stock_code,
                    resolved_name,
                    side,
                    quantity,
                    price,
                    amount,
                    fees,
                    rationale,
                    plan_horizon,
                    take_profit,
                    stop_loss,
                    now,
                ),
            )
            cursor.execute(
                "UPDATE sim_accounts SET cash = %s, updated_at = %s WHERE user_id = %s",
                (round(new_cash, 2), now, uid),
            )
        conn.commit()

    return get_simulation_account(uid)


def _compute_weights(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total = sum(float(item.get("marketValue") or item.get("weightBase") or 0) for item in items)
    if total <= 0:
        return items
    for item in items:
        base = float(item.get("marketValue") or item.get("weightBase") or 0)
        item["weight"] = round(base / total, 4)
    return items


def _build_watchlist_proxy_positions(watchlist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw in watchlist:
        code = str(raw.get("code") or "").strip()
        if not code:
            continue
        sector_name, sector_code = _extract_sector_info(code)
        items.append(
            {
                "code": code,
                "name": str(raw.get("name") or code),
                "marketValue": 1.0,
                "lastPrice": raw.get("price"),
                "change": raw.get("change"),
                "sentiment": raw.get("sentiment") or PLACEHOLDER,
                "tags": list(raw.get("tags") or []),
                "turnover": raw.get("turnover") or PLACEHOLDER,
                "volumeRatio": raw.get("volumeRatio") or PLACEHOLDER,
                "mainFlow": raw.get("mainFlow") or PLACEHOLDER,
                "pe": raw.get("pe") or PLACEHOLDER,
                "pb": raw.get("pb") or PLACEHOLDER,
                "marketCap": raw.get("marketCap") or PLACEHOLDER,
                "sectorName": sector_name,
                "sectorCode": sector_code,
            }
        )
    return _compute_weights(items)


def _sentiment_score(sentiment: Any) -> float:
    return float(SENTIMENT_SCORE_MAP.get(str(sentiment or "").strip(), 50))


def _info_completeness(item: dict[str, Any]) -> float:
    known = 0
    total = 8
    for key in ("lastPrice", "change", "turnover", "volumeRatio", "mainFlow", "pe", "pb", "marketCap"):
        value = item.get(key)
        if value not in (None, "", PLACEHOLDER):
            known += 1
    return known / total * 100


def get_portfolio_health(watchlist: list[dict[str, Any]] | None = None, user_id: int | None = None) -> dict[str, Any]:
    uid = _resolve_user_id(user_id)
    profile = get_investor_profile(uid)
    sim_state = get_simulation_account(uid)
    positions = [dict(item) for item in sim_state["positions"]]
    source = "模拟持仓"
    if not positions:
        positions = _build_watchlist_proxy_positions(watchlist or [])
        source = "自选股等权体检"
    else:
        positions = _compute_weights(positions)
        for item in positions:
            item["pe"] = PLACEHOLDER
            item["pb"] = PLACEHOLDER
            item["marketCap"] = PLACEHOLDER
    _refresh_positions_sector_info(positions)

    if not positions:
        raise WorkbenchServiceError("请先添加自选股或建立模拟持仓后再进行组合体检。")

    sector_weights: dict[str, float] = {}
    max_stock_weight = 0.0
    total_abs_change = 0.0
    hot_count = 0
    completeness_scores: list[float] = []
    sentiment_scores: list[float] = []
    position_breakdown: list[dict[str, Any]] = []

    for item in positions:
        weight = float(item.get("weight") or 0)
        max_stock_weight = max(max_stock_weight, weight)
        sector_name = str(item.get("sectorName") or UNKNOWN_SECTOR_NAME)
        sector_weights[sector_name] = sector_weights.get(sector_name, 0.0) + weight
        total_abs_change += abs(_to_float(item.get("change")) or 0.0)
        tags = {str(tag).strip() for tag in item.get("tags") or []}
        sentiment = str(item.get("sentiment") or "").strip()
        if tags.intersection(HOT_TAGS) or sentiment in {"强势", "偏强"}:
            hot_count += 1
        completeness_scores.append(_info_completeness(item))
        sentiment_scores.append(_sentiment_score(sentiment))
        position_breakdown.append(
            {
                "code": item["code"],
                "name": item["name"],
                "weight": round(weight * 100, 1),
                "sectorName": sector_name,
                "change": item.get("change"),
                "sentiment": item.get("sentiment") or PLACEHOLDER,
                "tags": list(item.get("tags") or []),
            }
        )

    max_sector_weight = max(sector_weights.values()) if sector_weights else 0.0
    sector_items = sorted(
        (
            {"name": name, "weight": round(weight * 100, 1)}
            for name, weight in sector_weights.items()
        ),
        key=lambda item: item["weight"],
        reverse=True,
    )

    count = len(positions)
    hhi = sum((float(item.get("weight") or 0) ** 2 for item in positions))
    base_hhi = 1 / count if count > 1 else 1
    hhi_penalty = 0.0 if count == 1 else (hhi - base_hhi) / (1 - base_hhi)
    diversification_score = 100 - hhi_penalty * 45
    diversification_score -= max(0.0, (max_stock_weight - profile["maxSingleStockWeight"]) * 220)
    diversification_score -= max(0.0, (max_sector_weight - profile["maxSingleSectorWeight"]) * 180)
    diversification_score = _clamp(diversification_score, 18, 96)

    activity = total_abs_change / count if count else 0
    hot_ratio = hot_count / count if count else 0
    risk_match_score = 100
    risk_match_score -= max(0.0, (max_stock_weight - profile["maxSingleStockWeight"]) * 240)
    risk_match_score -= max(0.0, (max_sector_weight - profile["maxSingleSectorWeight"]) * 210)
    risk_match_score -= max(0.0, activity - 2.2) * 8
    if profile["riskScore"] <= 45:
        risk_match_score -= hot_ratio * 25
    elif profile["riskScore"] >= 82:
        risk_match_score += 6
    risk_match_score = _clamp(risk_match_score, 20, 98)

    quality_score = sum(sentiment_scores) / len(sentiment_scores) * 0.55 + sum(completeness_scores) / len(completeness_scores) * 0.45
    quality_score = _clamp(quality_score, 22, 94)

    heat_score = 100 - activity * 7 - hot_ratio * 34
    if profile["riskScore"] >= 82:
        heat_score += 12
    elif profile["riskScore"] <= 25:
        heat_score -= 10
    heat_score = _clamp(heat_score, 20, 95)

    liquidity_score = sum(completeness_scores) / len(completeness_scores)
    liquidity_score = _clamp(liquidity_score, 30, 96)

    health_score = (
        diversification_score * 0.30
        + risk_match_score * 0.25
        + quality_score * 0.20
        + heat_score * 0.15
        + liquidity_score * 0.10
    )
    health_score = int(round(_clamp(health_score, 0, 100)))

    warnings: list[dict[str, str]] = []
    suggestions: list[str] = []

    if max_stock_weight > profile["maxSingleStockWeight"]:
        warnings.append(
            {
                "level": "high",
                "title": "单只股票集中度偏高",
                "detail": f"当前最大单股权重约 {max_stock_weight * 100:.1f}%，超过 {profile['riskLevel']} 建议上限 {profile['maxSingleStockWeight'] * 100:.0f}%。",
            }
        )
        suggestions.append("优先把头部仓位拆分到 2-3 只相关性更低的标的，降低单点失误对组合的冲击。")

    if max_sector_weight > profile["maxSingleSectorWeight"]:
        warnings.append(
            {
                "level": "high",
                "title": "行业暴露偏集中",
                "detail": f"最大行业暴露约 {max_sector_weight * 100:.1f}%，超过建议上限 {profile['maxSingleSectorWeight'] * 100:.0f}%。",
            }
        )
        suggestions.append("补充低相关行业或宽基 ETF，避免组合过度押注单一赛道。")

    if hot_ratio >= 0.5:
        warnings.append(
            {
                "level": "medium",
                "title": "短线情绪暴露偏高",
                "detail": f"组合中约 {hot_ratio * 100:.0f}% 的标的带有强势/放量特征，容易受情绪回撤影响。",
            }
        )
        suggestions.append("热点仓位宜控制在画像允许范围内，并设置明确止盈止损计划。")

    if quality_score <= 55:
        warnings.append(
            {
                "level": "medium",
                "title": "信息完备度不足",
                "detail": "当前部分持仓缺少完整估值/流动性信号，建议先补齐关键信息后再提高仓位。",
            }
        )

    if not suggestions:
        suggestions.append("当前组合结构整体可控，后续重点跟踪仓位漂移和行业集中变化。")
        suggestions.append("建议每周或每次大幅调仓后重新体检一次，保持画像与组合的一致性。")

    if health_score >= 80:
        summary = f"组合结构整体健康，当前更接近 {profile['riskLevel']} 投资者的承受区间。"
    elif health_score >= 60:
        summary = "组合总体可用，但集中度和情绪暴露仍有优化空间。"
    else:
        summary = "组合存在较明显的结构性风险，建议优先处理集中度与情绪化暴露。"

    return {
        "source": source,
        "healthScore": health_score,
        "summary": summary,
        "riskProfile": profile,
        "radar": [
            {"label": "分散度", "score": int(round(diversification_score))},
            {"label": "画像匹配", "score": int(round(risk_match_score))},
            {"label": "质量", "score": int(round(quality_score))},
            {"label": "情绪温度", "score": int(round(heat_score))},
            {"label": "流动性", "score": int(round(liquidity_score))},
        ],
        "sectorBreakdown": sector_items,
        "positionBreakdown": position_breakdown,
        "warnings": warnings,
        "suggestions": suggestions[:4],
        "metrics": {
            "maxStockWeight": round(max_stock_weight * 100, 1),
            "maxSectorWeight": round(max_sector_weight * 100, 1),
            "hotStockRatio": round(hot_ratio * 100, 1),
            "averageMove": round(activity, 2),
        },
    }


def _extract_recent_news(stock_code: str, sector_code: str = "") -> list[dict[str, str]]:
    now = datetime.now()
    arguments: dict[str, Any] = {
        "beginTime": (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
        "endTime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "pageNum": 1,
        "pageSize": 8,
        "stockCode": stock_code,
    }
    if sector_code:
        arguments["industryCode"] = sector_code

    try:
        news_payload = _call_tool_parsed("list_news", arguments)
    except Exception:
        return []

    records: list[dict[str, str]] = []
    raw_items = news_payload.get("data") if isinstance(news_payload, dict) else news_payload
    if not isinstance(raw_items, list):
        return records
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        title = str(_find_value(item, ["title", "标题"]) or "").strip()
        summary = str(_find_value(item, ["summary", "摘要", "keyPoints", "核心观点"]) or "").strip()
        if not title:
            continue
        records.append({"title": title, "summary": summary})
        if len(records) >= 3:
            break
    return records


def _extract_recent_announcements(stock_code: str) -> list[str]:
    today = datetime.now().strftime("%Y-%m-%d")
    begin = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
    try:
        payload = _call_tool_parsed(
            "list_announcements",
            {"stockCode": stock_code, "beginDate": begin, "endDate": today, "pageNum": 1, "pageSize": 5},
        )
    except Exception:
        return []
    raw_items = payload.get("data") if isinstance(payload, dict) else payload
    titles: list[str] = []
    if not isinstance(raw_items, list):
        return titles
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        title = str(_find_value(item, ["title", "标题"]) or "").strip()
        if title and title not in titles:
            titles.append(title)
    return titles[:2]


def explain_stock_anomaly(stock_code: str) -> dict[str, Any]:
    resolved = resolve_stock_query(stock_code)
    notes: str | None = None
    try:
        # 异动解释优先走轻量摘要入口，避免详情链路在上游抖动时超时。
        detail_payload = get_watchlist_stock(resolved["code"])
        stock = dict(detail_payload.get("stock") or {})
    except Exception as exc:
        stock = {"name": resolved["name"], "code": resolved["code"], "sentiment": PLACEHOLDER}
        notes = _join_notes(notes, f"行情摘要获取失败：{exc}")

    merge_payload = {}
    candidates: list[dict[str, Any]] = []
    history_items: list[dict[str, Any]] = []
    performance_payload = {}
    try:
        merge_payload = _call_tool_parsed("get_stock_realtime_quote_merge", {"stockCode": resolved["code"]})
        candidates = _extract_sector_candidates(merge_payload, resolved["code"])
    except Exception as exc:
        notes = _join_notes(notes, f"板块联动提取失败：{exc}")

    try:
        history_begin, history_end = _history_window()
        history_payload = _call_tool_parsed(
            "list_stock_adjusted_quotes",
            {
                "stockCode": resolved["code"],
                "beginDate": history_begin,
                "endDate": history_end,
                "pageNum": 1,
                "pageSize": 10,
            },
        )
        raw_history = history_payload.get("data") if isinstance(history_payload, dict) else history_payload
        if isinstance(raw_history, list):
            history_items = [item for item in raw_history if isinstance(item, dict)]
    except Exception as exc:
        notes = _join_notes(notes, f"历史行情提取失败：{exc}")

    try:
        performance_payload = _call_tool_parsed(
            "list_stock_performance_metrics",
            {"stockCode": resolved["code"], "pageNum": 1, "pageSize": 2},
        )
    except Exception:
        performance_payload = {}

    sector_name, sector_code = _extract_sector_info(resolved["code"])
    recent_news = _extract_recent_news(resolved["code"], sector_code)
    recent_announcements = _extract_recent_announcements(resolved["code"])

    price = _to_float(stock.get("price"))
    change = _to_float(stock.get("change"))
    volume_ratio = _to_float(stock.get("volumeRatio"))
    main_flow = str(stock.get("mainFlow") or "").strip()
    sentiment = str(stock.get("sentiment") or PLACEHOLDER)

    board_candidates = sorted(
        candidates,
        key=lambda item: abs(_to_float(item.get("change")) or 0),
        reverse=True,
    )
    lead_board = board_candidates[0] if board_candidates else None

    evidence_items: list[str] = []
    signal_type = "常规波动"
    if isinstance(change, (int, float)) and abs(change) >= 5:
        direction = "上涨" if change > 0 else "下跌"
        signal_type = "价格异动"
        evidence_items.append(f"当日涨跌幅约 {change:.2f}%，属于明显的{direction}异动。")

    if isinstance(volume_ratio, (int, float)) and volume_ratio >= 1.8:
        signal_type = "放量异动" if signal_type == "常规波动" else signal_type
        evidence_items.append(f"量比约 {volume_ratio:.2f}，说明短时间内资金关注度明显抬升。")

    if main_flow and main_flow not in {PLACEHOLDER, "--"}:
        evidence_items.append(f"主力资金信号为 {main_flow}，说明资金面正在发生变化。")

    if lead_board and isinstance(_to_float(lead_board.get("change")), (int, float)):
        board_change = _to_float(lead_board.get("change")) or 0.0
        if abs(board_change) >= 2:
            signal_type = "板块联动" if signal_type == "常规波动" else signal_type
            evidence_items.append(
                f"关联板块“{lead_board.get('name')}”同步波动约 {board_change:.2f}%，个股异动与板块共振较明显。"
            )

    if history_items and isinstance(price, (int, float)):
        recent_closes = [
            _to_float(item.get("closePrice") or item.get("latestPrice"))
            for item in history_items
        ]
        recent_closes = [item for item in recent_closes if isinstance(item, (int, float))]
        if recent_closes:
            recent_high = max(recent_closes)
            recent_low = min(recent_closes)
            if price >= recent_high:
                signal_type = "突破异动" if signal_type == "常规波动" else signal_type
                evidence_items.append("当前价格接近或创出近期高点，存在技术突破特征。")
            elif price <= recent_low:
                signal_type = "破位异动" if signal_type == "常规波动" else signal_type
                evidence_items.append("当前价格接近或跌破近期低点，存在破位压力。")

    if recent_news:
        signal_type = "消息驱动" if signal_type == "常规波动" else signal_type
        evidence_items.append(f"近 3 日相关新闻较集中，最新标题如“{recent_news[0]['title']}”。")

    if recent_announcements:
        signal_type = "公告驱动" if signal_type == "常规波动" else signal_type
        evidence_items.append(f"近期公告中出现“{recent_announcements[0]}”，需结合公告内容判断持续性。")

    if not evidence_items:
        evidence_items.append("当前暂未识别到特别强的异动证据，波动更像是常规行情扰动。")

    confidence = round(_clamp(0.35 + len(evidence_items) * 0.12, 0.35, 0.92), 2)
    risk_flags: list[str] = []
    if isinstance(change, (int, float)) and abs(change) >= 7:
        risk_flags.append("单日振幅较大，短线追涨杀跌风险上升。")
    if recent_news and recent_announcements:
        risk_flags.append("消息与公告同时出现时，建议先辨别一次性事件与趋势性变化。")
    if sentiment in {"强势", "偏强"}:
        risk_flags.append("当前情绪偏热，若缺少持续兑现，后续可能出现回吐。")
    if notes:
        risk_flags.append(notes)

    performance_records = performance_payload.get("data") if isinstance(performance_payload, dict) else performance_payload
    if isinstance(performance_records, list) and performance_records:
        record = performance_records[0] if isinstance(performance_records[0], dict) else {}
        new_high_flag = str(_find_value(record, ["isWeekNewHigh", "近一周新高", "isMonthNewHigh", "本月新高"]) or "").strip()
        if new_high_flag in {"1", "true", "True"}:
            risk_flags.append("已出现阶段性新高信号，若量能衰减需警惕冲高回落。")

    summary = (
        f"{resolved['name']}当前更像是“{signal_type}”场景，"
        f"核心线索集中在{'、'.join(evidence_items[:2])}。"
    )

    return {
        "stock": {
            "name": stock.get("name") or resolved["name"],
            "code": stock.get("code") or resolved["code"],
            "price": stock.get("price"),
            "change": stock.get("change"),
            "sentiment": sentiment,
            "sectorName": sector_name,
        },
        "signalType": signal_type,
        "confidence": confidence,
        "summary": summary,
        "evidenceItems": evidence_items[:5],
        "newsItems": recent_news,
        "announcementTitles": recent_announcements,
        "riskFlags": risk_flags[:4],
    }


def _parse_datetime_like(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.replace(tzinfo=None)
        return parsed
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _build_trade_review_payload(
    code: str,
    trades: list[dict[str, Any]],
    position: dict[str, Any] | None,
) -> dict[str, Any]:
    trades_asc = sorted(trades, key=lambda item: int(item.get("id") or 0))
    first_trade = trades_asc[0]
    last_trade = trades_asc[-1]

    stock_name = str(last_trade.get("stockName") or first_trade.get("stockName") or code)
    live = _get_live_snapshot(code, stock_name)
    sentiment = str((position or {}).get("sentiment") or live.get("sentiment") or PLACEHOLDER)
    sector_name = str((position or {}).get("sectorName") or live.get("sectorName") or "未知板块")
    current_price = _to_float((position or {}).get("lastPrice"))
    if current_price is None:
        current_price = _to_float(live.get("price"))

    buy_qty = 0
    sell_qty = 0
    buy_amount_gross = 0.0
    buy_amount_net = 0.0
    sell_amount_gross = 0.0
    sell_amount_net = 0.0
    realized_pnl = 0.0
    realized_cost = 0.0
    inventory_qty = 0
    inventory_cost = 0.0

    best_rationale = ""
    has_take_profit = False
    has_stop_loss = False
    trade_times: list[datetime] = []

    for trade in trades_asc:
        side = str(trade.get("side") or "").strip().lower()
        quantity = int(trade.get("quantity") or 0)
        amount = float(trade.get("amount") or 0.0)
        fees = float(trade.get("fees") or 0.0)
        rationale = str(trade.get("rationale") or "").strip()
        take_profit = str(trade.get("takeProfit") or "").strip()
        stop_loss = str(trade.get("stopLoss") or "").strip()
        trade_at = _parse_datetime_like(trade.get("createdAt"))
        if trade_at:
            trade_times.append(trade_at)

        if len(rationale) > len(best_rationale):
            best_rationale = rationale
        has_take_profit = has_take_profit or bool(take_profit)
        has_stop_loss = has_stop_loss or bool(stop_loss)

        if side == "buy":
            buy_qty += quantity
            buy_amount_gross += amount
            buy_amount_net += amount + fees
            inventory_qty += quantity
            inventory_cost += amount + fees
            continue

        if side != "sell":
            continue

        sell_qty += quantity
        sell_amount_gross += amount
        sell_amount_net += amount - fees
        if inventory_qty <= 0:
            continue

        matched_qty = min(quantity, inventory_qty)
        avg_inventory_cost = inventory_cost / inventory_qty if inventory_qty else 0.0
        matched_cost = avg_inventory_cost * matched_qty
        realized_cost += matched_cost
        realized_pnl += (amount - fees) - matched_cost
        inventory_qty -= matched_qty
        inventory_cost -= matched_cost

    avg_buy_price = (buy_amount_gross / buy_qty) if buy_qty else None
    avg_sell_price = (sell_amount_gross / sell_qty) if sell_qty else None

    open_qty = int((position or {}).get("quantity") or max(inventory_qty, 0))
    average_cost = _to_float((position or {}).get("averageCost"))
    if average_cost is None and open_qty > 0:
        average_cost = round((inventory_cost / open_qty), 2)

    unrealized_pnl = float((position or {}).get("unrealizedPnl") or 0.0)
    pnl_ratio = _to_float((position or {}).get("pnlRatio"))
    if pnl_ratio is None:
        cost_base = buy_amount_net if buy_amount_net > 0 else 1.0
        pnl_ratio = (realized_pnl / cost_base) * 100

    total_pnl = realized_pnl + unrealized_pnl
    total_cost_base = buy_amount_net if buy_amount_net > 0 else 1.0
    total_pnl_ratio = round((total_pnl / total_cost_base) * 100, 2)
    realized_ratio = round((realized_pnl / realized_cost) * 100, 2) if realized_cost > 0 else None

    review_scope = "open_position" if open_qty > 0 else "closed_position"
    if total_pnl_ratio >= 6:
        thesis_status = "原始逻辑成立"
    elif total_pnl_ratio <= -6:
        thesis_status = "原始逻辑不成立"
    else:
        thesis_status = "原始逻辑部分成立"

    first_time = trade_times[0] if trade_times else _parse_datetime_like(first_trade.get("createdAt"))
    last_time = trade_times[-1] if trade_times else _parse_datetime_like(last_trade.get("createdAt"))
    holding_days = (
        round(max((last_time - first_time).total_seconds(), 0.0) / 86400, 1)
        if first_time and last_time
        else 0.0
    )

    min_interval_hours: float | None = None
    if len(trade_times) >= 2:
        diffs = [
            max((trade_times[idx] - trade_times[idx - 1]).total_seconds(), 0.0) / 3600
            for idx in range(1, len(trade_times))
        ]
        if diffs:
            min_interval_hours = min(diffs)

    timing_score = 68.0
    stock_selection_score = 68.0
    if len(trades_asc) >= 4:
        timing_score -= 8
    if min_interval_hours is not None and min_interval_hours <= 24:
        timing_score -= 10
    if total_pnl_ratio < 0 and holding_days <= 5:
        timing_score -= 10
    if total_pnl_ratio < 0 and holding_days >= 20:
        stock_selection_score -= 10
    if avg_sell_price is not None and avg_buy_price is not None:
        if avg_sell_price >= avg_buy_price * 1.04:
            timing_score += 8
        elif avg_sell_price <= avg_buy_price * 0.96:
            timing_score -= 12
    if sentiment in {"偏弱", "转弱"} and total_pnl_ratio < 0:
        stock_selection_score -= 8
    if len(best_rationale) >= 16:
        stock_selection_score += 6
    else:
        stock_selection_score -= 8

    timing_score = float(_clamp(timing_score, 20, 95))
    stock_selection_score = float(_clamp(stock_selection_score, 20, 95))

    if total_pnl_ratio >= 0:
        primary_miss = "none"
        primary_reason = "本次交易总体结果为正，主要问题不是方向错误，而是如何稳定复制。"
    elif timing_score + 8 < stock_selection_score:
        primary_miss = "timing"
        primary_reason = "亏损更集中在入场/出场节奏，说明择时与执行节奏是主要短板。"
    elif stock_selection_score + 8 < timing_score:
        primary_miss = "stock_selection"
        primary_reason = "亏损更集中在标的质量与逻辑验证，说明选股框架需要优先迭代。"
    else:
        primary_miss = "mixed"
        primary_reason = "亏损同时包含择时和选股问题，需要双线改进。"

    discipline_score = 62.0
    discipline_items: list[str] = []
    discipline_misses: list[str] = []
    if len(best_rationale) >= 12:
        discipline_score += 10
        discipline_items.append("交易前有明确理由记录")
    else:
        discipline_misses.append("交易理由记录偏短，复盘证据不足")
    if has_take_profit:
        discipline_score += 8
        discipline_items.append("有止盈计划")
    else:
        discipline_misses.append("缺少止盈计划")
    if has_stop_loss:
        discipline_score += 8
        discipline_items.append("有止损计划")
    else:
        discipline_misses.append("缺少止损计划")
    if len(trades_asc) >= 5:
        discipline_score -= 10
        discipline_misses.append("同一标的交易频次较高，执行可能受波动影响")
    if min_interval_hours is not None and min_interval_hours <= 12:
        discipline_score -= 8
        discipline_misses.append("多笔交易间隔过短，存在情绪化决策迹象")
    discipline_score = float(_clamp(discipline_score, 30, 95))

    emotion_signals: list[str] = []
    if len(trades_asc) >= 5:
        emotion_signals.append("交易频次偏高，容易被短期波动牵引")
    if min_interval_hours is not None and min_interval_hours <= 24:
        emotion_signals.append("买卖决策间隔较短，可能存在追涨杀跌行为")
    if not has_stop_loss:
        emotion_signals.append("缺少止损约束，回撤阶段更容易情绪化持有")
    if total_pnl_ratio < -6:
        emotion_signals.append("亏损放大时未看到明显降频动作")
    if not emotion_signals:
        emotion_signals.append("交易节奏总体稳定，情绪影响可控")

    emotion_risk = "较低"
    if len(emotion_signals) >= 4:
        emotion_risk = "偏高"
    elif len(emotion_signals) >= 2:
        emotion_risk = "中"

    buy_strengths: list[str] = []
    buy_weaknesses: list[str] = []
    buy_point_score = 62.0
    if len(best_rationale) >= 12:
        buy_strengths.append("买入前有成体系的逻辑描述")
        buy_point_score += 8
    else:
        buy_weaknesses.append("买入理由过于简略，难以验证逻辑是否兑现")
        buy_point_score -= 10
    if has_stop_loss:
        buy_strengths.append("买入同时设置风险退出条件")
        buy_point_score += 6
    else:
        buy_weaknesses.append("买入时未设置止损约束")
        buy_point_score -= 8
    if total_pnl_ratio < 0 and holding_days <= 5:
        buy_weaknesses.append("入场后较快进入回撤，买点时机偏早")
        buy_point_score -= 8
    buy_point_score = float(_clamp(buy_point_score, 20, 95))

    sell_strengths: list[str] = []
    sell_weaknesses: list[str] = []
    sell_point_score: float | None = None
    if sell_qty > 0:
        sell_point_score = 62.0
        if avg_sell_price is not None and avg_buy_price is not None and avg_sell_price >= avg_buy_price:
            sell_strengths.append("卖出均价不低于买入均价，兑现能力较好")
            sell_point_score += 10
        elif avg_sell_price is not None and avg_buy_price is not None:
            sell_weaknesses.append("卖出均价低于买入均价，退出节奏有待优化")
            sell_point_score -= 12
        if has_take_profit:
            sell_strengths.append("卖出动作与止盈计划有一定一致性")
            sell_point_score += 6
        else:
            sell_weaknesses.append("卖出缺少明确止盈纪律支持")
            sell_point_score -= 6
        if total_pnl_ratio < 0 and min_interval_hours is not None and min_interval_hours <= 24:
            sell_weaknesses.append("短时反复买卖，卖点可能受情绪驱动")
            sell_point_score -= 8
        sell_point_score = float(_clamp(sell_point_score, 20, 95))
    else:
        sell_weaknesses.append("尚未出现卖出记录，无法验证卖点质量")

    thesis_detail = (
        f"本次围绕 {stock_name} 的交易共 {len(trades_asc)} 笔，"
        f"累计盈亏 {round(total_pnl, 2)} 元（{total_pnl_ratio:+.2f}%）。"
        f"当前判断为“{thesis_status}”，建议继续用同一套触发条件跟踪是否可复现。"
    )
    learning_summary = (
        f"本次复盘显示主要短板在“{primary_reason}”。"
        "下一步应把每次交易拆分为：入场条件、失效条件、退出条件三段，并记录执行偏差。"
    )

    actionable_suggestions = [
        "每次下单前写 3 行交易计划：触发条件、失效条件、退出条件。",
        "把“择时错误”和“选股错误”分开计分，避免只看盈亏不看过程。",
        "若连续两次触发止损，下一笔将仓位下调 30% 并降低交易频率。",
        "盈利单也要复盘：记录为什么卖出、是否过早止盈、是否错过主升段。",
        "将下一次复盘重点放在可执行动作，而不是情绪描述。",
    ]
    if primary_miss == "timing":
        actionable_suggestions.insert(0, "优先优化入场与退出节奏：只在触发条件明确时交易，减少盘中临时决策。")
    elif primary_miss == "stock_selection":
        actionable_suggestions.insert(0, "优先优化选股框架：先筛掉逻辑模糊、业绩验证弱的标的，再考虑择时。")

    next_trade_checklist = [
        "是否能用一句话说明这笔交易的核心逻辑？",
        "若判断失效，具体在哪个价格/信号退出？",
        "该标的在组合中的仓位是否超过个人风险上限？",
        "本次交易是否与上次错误重复？",
        "若行情不及预期，是否有预案而不是临盘拍脑袋？",
    ]

    review = {
        "reviewId": None,
        "createdAt": _now_text(),
        "reviewScope": review_scope,
        "stock": {
            "code": code,
            "name": stock_name,
            "sectorName": sector_name,
            "averageCost": round(average_cost, 2) if average_cost is not None else None,
            "currentPrice": round(current_price, 2) if current_price is not None else None,
            "pnlRatio": round(float(pnl_ratio or 0.0), 2),
            "quantity": open_qty,
            "status": "持仓中" if review_scope == "open_position" else "已卖出",
        },
        "tradeStats": {
            "tradeCount": len(trades_asc),
            "buyCount": buy_qty,
            "sellCount": sell_qty,
            "holdingDays": holding_days,
            "averageBuyPrice": round(avg_buy_price, 2) if avg_buy_price is not None else None,
            "averageSellPrice": round(avg_sell_price, 2) if avg_sell_price is not None else None,
            "realizedPnl": round(realized_pnl, 2),
            "realizedPnlRatio": realized_ratio,
            "totalPnl": round(total_pnl, 2),
            "totalPnlRatio": total_pnl_ratio,
        },
        "thesisStatus": thesis_status,
        "thesisDetail": thesis_detail,
        "errorAttribution": {
            "primary": primary_miss,
            "reasoning": primary_reason,
            "timingScore": round(timing_score, 1),
            "stockSelectionScore": round(stock_selection_score, 1),
        },
        "buyPointAssessment": {
            "score": round(buy_point_score, 1),
            "strengths": buy_strengths[:3],
            "weaknesses": buy_weaknesses[:3],
        },
        "sellPointAssessment": {
            "score": round(sell_point_score, 1) if sell_point_score is not None else None,
            "strengths": sell_strengths[:3],
            "weaknesses": sell_weaknesses[:3],
        },
        "disciplineScore": int(round(discipline_score)),
        "disciplineItems": discipline_items[:4],
        "executionAssessment": {
            "score": int(round(discipline_score)),
            "positives": discipline_items[:4],
            "misses": discipline_misses[:4],
        },
        "emotionRisk": emotion_risk,
        "sentiment": sentiment,
        "emotionAssessment": {
            "level": emotion_risk,
            "signals": emotion_signals[:4],
            "summary": "情绪风险可控" if emotion_risk == "较低" else "存在情绪干扰，需先降频再提胜率",
        },
        "summary": (
            f"{stock_name} 复盘结论：{thesis_status}。"
            f"本次主要问题是{primary_reason}"
        ),
        "learningSummary": learning_summary,
        "improvements": actionable_suggestions[:5],
        "actionableSuggestions": actionable_suggestions[:5],
        "nextTradeChecklist": next_trade_checklist,
    }
    return review


def _save_trade_review(review: dict[str, Any], user_id: int | None = None) -> dict[str, Any]:
    uid = _resolve_user_id(user_id)
    stock = review.get("stock") if isinstance(review.get("stock"), dict) else {}
    stock_code = str(stock.get("code") or "").strip()
    stock_name = str(stock.get("name") or "").strip()
    summary = str(review.get("summary") or "").strip()
    thesis_status = str(review.get("thesisStatus") or "").strip()
    review_scope = str(review.get("reviewScope") or "").strip()
    created_at = str(review.get("createdAt") or _now_text())

    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO sim_trade_reviews (
                  user_id, stock_code, stock_name, summary_text, thesis_status, review_scope, review_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    uid,
                    stock_code[:32],
                    stock_name[:120],
                    summary,
                    thesis_status[:120],
                    review_scope[:32],
                    json.dumps(review, ensure_ascii=False),
                    created_at,
                ),
            )
            review_id = int(cursor.lastrowid)
        conn.commit()

    saved = dict(review)
    saved["reviewId"] = review_id
    saved["createdAt"] = created_at
    return saved


def list_trade_reviews(user_id: int | None = None) -> list[dict[str, Any]]:
    uid = _resolve_user_id(user_id)
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, stock_code, stock_name, summary_text, thesis_status, review_scope, review_json, created_at
                FROM sim_trade_reviews
                WHERE user_id = %s
                ORDER BY id DESC
                """,
                (uid,),
            )
            rows = list(cursor.fetchall() or [])

    items: list[dict[str, Any]] = []
    for row in rows:
        parsed_review = _safe_json_loads(str(row.get("review_json") or ""), {})
        if not isinstance(parsed_review, dict):
            parsed_review = {}
        parsed_review["reviewId"] = int(row["id"])
        parsed_review["createdAt"] = str(row.get("created_at") or "")

        items.append(
            {
                "id": int(row["id"]),
                "stockCode": str(row.get("stock_code") or ""),
                "stockName": str(row.get("stock_name") or ""),
                "summary": str(row.get("summary_text") or ""),
                "thesisStatus": str(row.get("thesis_status") or ""),
                "reviewScope": str(row.get("review_scope") or ""),
                "createdAt": str(row.get("created_at") or ""),
                "review": parsed_review,
            }
        )
    return items


def delete_trade_review(review_id: int, user_id: int | None = None) -> None:
    uid = _resolve_user_id(user_id)
    rid = int(review_id)
    if rid <= 0:
        raise WorkbenchServiceError("复盘记录 ID 无效。")

    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM sim_trade_reviews WHERE id = %s AND user_id = %s",
                (rid, uid),
            )
            affected = int(cursor.rowcount or 0)
        conn.commit()

    if affected <= 0:
        raise WorkbenchServiceError("未找到可删除的复盘记录。")


def create_trade_review(stock_code: str, user_id: int | None = None) -> dict[str, Any]:
    code = str(stock_code or "").strip()
    if not code:
        raise WorkbenchServiceError("复盘股票代码不能为空。")

    uid = _resolve_user_id(user_id)
    sim_state = get_simulation_account(uid)
    positions = {item["code"]: item for item in sim_state["positions"]}
    position = positions.get(code)

    related_trades = [item for item in sim_state["trades"] if item["stockCode"] == code]
    if not related_trades:
        raise WorkbenchServiceError("未找到该股票的交易记录。")

    review = _build_trade_review_payload(code=code, trades=related_trades, position=position)
    return _save_trade_review(review, uid)


