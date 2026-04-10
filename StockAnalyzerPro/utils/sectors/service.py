from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import utils.mcp.init as mcp
from utils.models.availability import ensure_model_available
from utils.stocks.service import (
    ANALYSIS_CLIENT,
    ANALYSIS_MODEL,
    PROJECT_ROOT,
    _collect_records,
    _find_value,
    _join_notes,
    _normalize_key,
    _parse_json_text,
    _read_json_file,
    _to_float,
    _unpack_mcp_result,
    _write_json_file,
)

DEFAULT_PROBE_CODES = ["600519", "300750", "300308"]
MAX_PROBE_CODES = 12
MAX_MODEL_SECTORS = 12
MAX_RETURN_SECTORS = 7
SECTOR_CACHE_TTL_SECONDS = 300
SECTOR_CACHE_VERSION = "v3"

CACHE_DIR = PROJECT_ROOT / "cache" / "sector_service"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class SectorServiceError(RuntimeError):
    """板块分析服务错误。"""


def _model_gate_reason() -> str | None:
    try:
        ensure_model_available()
        return None
    except Exception as exc:
        return f"AI 模型当前不可用，已跳过 MCP 市场数据拉取以避免额度浪费：{exc}"


def _cache_path(stock_codes: list[str]) -> Path:
    key = f"{SECTOR_CACHE_VERSION}:{','.join(sorted(stock_codes))}"
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def _load_cache(stock_codes: list[str]) -> dict[str, Any] | None:
    return _read_json_file(_cache_path(stock_codes), None)


def _save_cache(stock_codes: list[str], payload: dict[str, Any]) -> None:
    cache_entry = {
        "cachedAt": int(time.time()),
        "payload": payload,
    }
    _write_json_file(_cache_path(stock_codes), cache_entry)


def _cache_is_fresh(cache_entry: dict[str, Any] | None) -> bool:
    if not cache_entry:
        return False
    cached_at = cache_entry.get("cachedAt")
    return isinstance(cached_at, (int, float)) and time.time() - cached_at <= SECTOR_CACHE_TTL_SECONDS


def _normalize_probe_codes(stock_codes: list[Any] | None) -> list[str]:
    unique_codes: list[str] = []
    for code in stock_codes or []:
        text = str(code).strip()
        if not re.fullmatch(r"\d{6}", text):
            continue
        if text in unique_codes:
            continue
        unique_codes.append(text)

    if unique_codes:
        return unique_codes[:MAX_PROBE_CODES]
    return DEFAULT_PROBE_CODES[:]


def _collect_records_with_paths(node: Any, path: str = "") -> list[tuple[str, dict[str, Any]]]:
    records: list[tuple[str, dict[str, Any]]] = []
    if isinstance(node, dict):
        records.append((path, node))
        for key, value in node.items():
            next_path = f"{path}.{key}" if path else str(key)
            records.extend(_collect_records_with_paths(value, next_path))
    elif isinstance(node, list):
        for item in node:
            records.extend(_collect_records_with_paths(item, path))
    return records


def _infer_sector_kind(path: str, record: dict[str, Any]) -> str:
    combined = _normalize_key(f"{path} {' '.join(record.keys())}")
    if any(token in combined for token in ("concept", "gn", "概念")):
        return "concept"
    if any(token in combined for token in ("industry", "hy", "行业")):
        return "industry"

    sector_type = _find_value(record, ["sectorType", "boardType", "type", "板块类型"])
    type_text = _normalize_key(str(sector_type or ""))
    if any(token in type_text for token in ("concept", "gn", "概念")):
        return "concept"
    if any(token in type_text for token in ("industry", "hy", "行业")):
        return "industry"
    return "unknown"


def _ratio_to_percent(value: Any) -> float | None:
    number = _to_float(value)
    if number is None:
        return None
    if abs(number) <= 1:
        return round(number * 100, 2)
    return round(number, 2)


def _extract_sector_candidates(merge_payload: Any, stock_code: str) -> list[dict[str, Any]]:
    data = merge_payload.get("data") if isinstance(merge_payload, dict) else None
    if isinstance(data, dict):
        direct_candidates: list[dict[str, Any]] = []
        industry_quote = data.get("industryRealQuote")
        if isinstance(industry_quote, dict):
            industry_name = str(industry_quote.get("industryName") or "").strip()
            if industry_name:
                direct_candidates.append(
                    {
                        "name": industry_name,
                        "code": str(industry_quote.get("industryCode") or "").strip(),
                        "kind": "industry",
                        "change": _ratio_to_percent(industry_quote.get("changeRatio")),
                        "amount": _to_float(industry_quote.get("totalValue")),
                        "volume": _to_float(industry_quote.get("volume")),
                        "latestPrice": _to_float(industry_quote.get("price") or industry_quote.get("currentPrice")),
                        "sourceStockCode": stock_code,
                    }
                )

        concept_quotes = data.get("conceptRealQuotes")
        if isinstance(concept_quotes, list):
            for quote in concept_quotes:
                if not isinstance(quote, dict):
                    continue
                concept_name = str(quote.get("conceptName") or "").strip()
                if not concept_name:
                    continue
                direct_candidates.append(
                    {
                        "name": concept_name,
                        "code": str(quote.get("conceptCode") or "").strip(),
                        "kind": "concept",
                        "change": _ratio_to_percent(quote.get("changeRatio")),
                        "amount": _to_float(quote.get("totalValue")),
                        "volume": _to_float(quote.get("conceptAmount")),
                        "latestPrice": None,
                        "sourceStockCode": stock_code,
                    }
                )

        if direct_candidates:
            return direct_candidates

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    for path, record in _collect_records_with_paths(merge_payload):
        combined = _normalize_key(f"{path} {' '.join(record.keys())}")
        if not any(token in combined for token in ("concept", "industry", "sector", "board", "plate", "block", "概念", "行业", "板块")):
            continue

        kind = _infer_sector_kind(path, record)
        name = _find_value(
            record,
            [
                "conceptName",
                "industryName",
                "sectorName",
                "boardName",
                "blockName",
                "indexName",
                "name",
                "概念名称",
                "行业名称",
                "板块名称",
                "名称",
            ],
        )
        code = _find_value(
            record,
            [
                "conceptCode",
                "industryCode",
                "sectorCode",
                "boardCode",
                "blockCode",
                "indexCode",
                "code",
                "概念代码",
                "行业代码",
                "板块代码",
                "代码",
            ],
        )

        name_text = str(name or "").strip()
        code_text = str(code or "").strip()
        if not name_text:
            continue
        if code_text == stock_code and kind == "unknown":
            continue

        unique_key = f"{kind}:{code_text or name_text}"
        if unique_key in seen:
            continue
        seen.add(unique_key)

        candidates.append(
            {
                "name": name_text,
                "code": code_text,
                "kind": kind,
                "change": _to_float(
                    _ratio_to_percent(
                        _find_value(
                            record,
                            [
                                "changePercent",
                                "pctChg",
                                "changeRate",
                                "changeRatio",
                                "涨跌幅",
                                "涨幅",
                            ],
                        )
                    )
                ),
                "amount": _to_float(
                    _find_value(record, ["amount", "成交额", "turnover", "成交金额", "totalValue", "marketValue"])
                ),
                "volume": _to_float(_find_value(record, ["volume", "成交量", "conceptAmount", "stockAmount"])),
                "latestPrice": _to_float(
                    _find_value(record, ["latestPrice", "lastPrice", "price", "currentPrice", "最新价", "指数"])
                ),
                "sourceStockCode": stock_code,
            }
        )

    return candidates


def _aggregate_sector_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bucket: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        key = f"{candidate['kind']}:{candidate['code'] or candidate['name']}"
        item = bucket.setdefault(
            key,
            {
                "name": candidate["name"],
                "code": candidate["code"],
                "kind": candidate["kind"],
                "changes": [],
                "amounts": [],
                "volumes": [],
                "prices": [],
                "sourceStockCodes": set(),
            },
        )

        for field, key_name in (("change", "changes"), ("amount", "amounts"), ("volume", "volumes"), ("latestPrice", "prices")):
            value = candidate.get(field)
            if isinstance(value, (int, float)):
                item[key_name].append(float(value))
        source_stock_code = candidate.get("sourceStockCode")
        if source_stock_code:
            item["sourceStockCodes"].add(str(source_stock_code))

    aggregated: list[dict[str, Any]] = []
    for item in bucket.values():
        changes = item["changes"]
        amounts = item["amounts"]
        volumes = item["volumes"]
        prices = item["prices"]
        aggregated.append(
            {
                "name": item["name"],
                "code": item["code"],
                "kind": item["kind"],
                "avgChange": round(sum(changes) / len(changes), 2) if changes else None,
                "maxAbsChange": round(max((abs(value) for value in changes), default=0), 2) if changes else None,
                "totalAmount": round(sum(amounts), 2) if amounts else None,
                "totalVolume": round(sum(volumes), 2) if volumes else None,
                "avgPrice": round(sum(prices) / len(prices), 2) if prices else None,
                "coverageCount": len(item["sourceStockCodes"]),
                "sourceStockCodes": sorted(item["sourceStockCodes"]),
            }
        )

    aggregated.sort(
        key=lambda item: (
            item.get("totalAmount") or 0,
            item.get("coverageCount") or 0,
            item.get("maxAbsChange") or 0,
            item.get("totalVolume") or 0,
        ),
        reverse=True,
    )

    industries = [item for item in aggregated if item.get("kind") == "industry"]
    others = [item for item in aggregated if item.get("kind") != "industry"]

    selected: list[dict[str, Any]] = []
    selected.extend(industries[:4])
    remaining_slots = max(MAX_MODEL_SECTORS - len(selected), 0)
    selected.extend(others[:remaining_slots])
    selected.sort(
        key=lambda item: (
            item.get("totalAmount") or 0,
            item.get("coverageCount") or 0,
            item.get("maxAbsChange") or 0,
            item.get("totalVolume") or 0,
        ),
        reverse=True,
    )
    return selected[:MAX_MODEL_SECTORS]


def _extract_market_summary(payload: Any) -> dict[str, Any]:
    return {
        "upCount": _to_float(_find_value(payload, ["upCount", "upAmount", "riseCount", "上涨家数", "上涨数量"])),
        "downCount": _to_float(_find_value(payload, ["downCount", "downAmount", "fallCount", "下跌家数", "下跌数量"])),
        "flatCount": _to_float(_find_value(payload, ["flatCount", "bxAmount", "平盘家数", "平盘数量"])),
        "limitUpCount": _to_float(_find_value(payload, ["limitUpCount", "upTopAmount", "涨停家数", "涨停数量"])),
        "limitDownCount": _to_float(_find_value(payload, ["limitDownCount", "downTopAmount", "跌停家数", "跌停数量"])),
        "gt8UpCount": _to_float(_find_value(payload, ["gt8UpCount", "upOver8Amount", "涨幅超8数量", "涨幅超过8数量"])),
        "gt8DownCount": _to_float(_find_value(payload, ["gt8DownCount", "downOver8Amount", "跌幅超8数量", "跌幅超过8数量"])),
    }


def _extract_news_items(payload: Any, limit: int = 10) -> list[dict[str, Any]]:
    records = _collect_records(payload)
    items: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    for record in records:
        title = str(_find_value(record, ["title", "标题"]) or "").strip()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)

        summary = str(_find_value(record, ["summary", "摘要", "keyPoints", "核心观点"]) or "").strip()
        sentiment = _to_float(_find_value(record, ["sentimentScore", "情绪得分", "sentiment"]))
        items.append({"title": title, "summary": summary, "sentiment": sentiment})
        if len(items) >= limit:
            break

    return items


def _analyze_sector_overview_with_model(
    sector_candidates: list[dict[str, Any]],
    market_summary: dict[str, Any],
    news_items: list[dict[str, Any]],
    source_note: str,
) -> dict[str, Any]:
    if ANALYSIS_CLIENT is None:
        return {"error": "未配置 DeepSeek API Key", "sectors": [], "insights": []}

    prompt_payload = {
        "sourceNote": source_note,
        "marketSummary": market_summary,
        "sectorCandidates": sector_candidates,
        "latestNews": news_items,
    }

    system_prompt = (
        "你是 A 股板块分析引擎。"
        "请仅基于输入的 MCP 市场数据和新闻输出 JSON。"
        "不要虚构不存在的板块，板块只能从 sectorCandidates 中选择。"
        "请输出字段：sourceNote、sectors、insights。"
        "sourceNote 是一句简短来源说明。"
        "sectors 为数组，元素字段必须包含 name、code、kind、attentionScore、sentimentScore、strengthScore、reason。"
        "三个 score 均为 0 到 100 的整数。"
        "insights 产出 3 到 5 条，每条不超过 40 个字，聚焦市场情绪与政策风向。"
        "如果信息不足，也要只使用提供的板块名称，不得新增。"
    )

    try:
        response = ANALYSIS_CLIENT.chat.completions.create(
            model=ANALYSIS_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False)},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        parsed = _parse_json_text(content)
        if not isinstance(parsed, dict):
            return {"error": "模型未返回有效 JSON", "sectors": [], "insights": []}
        return parsed
    except Exception as exc:
        return {"error": str(exc), "sectors": [], "insights": []}


def _sector_rank_key(item: dict[str, Any]) -> tuple[float, float, float, float, float]:
    return (
        float(item.get("strengthScore") or 0),
        float(item.get("attentionScore") or 0),
        float(item.get("sentimentScore") or 0),
        float(item.get("avgChange") or 0),
        float(item.get("coverageCount") or 0),
    )


def _build_sector_overview(
    sector_candidates: list[dict[str, Any]],
    analysis_result: dict[str, Any],
    *,
    status_note: str | None,
    source_note: str,
) -> dict[str, Any]:
    analysis_sectors = analysis_result.get("sectors")
    by_key: dict[str, dict[str, Any]] = {}
    if isinstance(analysis_sectors, list):
        for item in analysis_sectors:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            code = str(item.get("code") or "").strip()
            key = code or name
            if not key:
                continue
            by_key[key] = item

    sectors: list[dict[str, Any]] = []
    missing_model_scores = False
    for candidate in sector_candidates:
        key = candidate.get("code") or candidate.get("name")
        analyzed = by_key.get(str(key or "")) or by_key.get(str(candidate.get("name") or ""))

        if not analyzed:
            missing_model_scores = True
            attention = 0
            sentiment = 0
            strength = 0
            reason = ""
        else:
            attention = int(max(0, min(100, round(float(analyzed.get("attentionScore") or 0)))))
            sentiment = int(max(0, min(100, round(float(analyzed.get("sentimentScore") or 0)))))
            strength = int(max(0, min(100, round(float(analyzed.get("strengthScore") or 0)))))
            reason = str(analyzed.get("reason") or "").strip()

        sectors.append(
            {
                "name": candidate["name"],
                "code": candidate["code"],
                "kind": candidate["kind"],
                "attentionScore": attention,
                "sentimentScore": sentiment,
                "strengthScore": strength,
                "reason": reason,
                "avgChange": candidate.get("avgChange"),
                "coverageCount": candidate.get("coverageCount"),
            }
        )

    insights = analysis_result.get("insights")
    clean_insights: list[str] = []
    if isinstance(insights, list):
        for item in insights:
            text = str(item).strip()
            if text and text not in clean_insights:
                clean_insights.append(text)

    analysis_source_note = str(analysis_result.get("sourceNote") or "").strip()
    if analysis_result.get("error"):
        status_note = _join_notes(status_note, f"模型分析暂不可用：{analysis_result['error']}")
    if missing_model_scores:
        status_note = _join_notes(status_note, "模型未覆盖全部板块评分")

    sectors.sort(key=_sector_rank_key, reverse=True)
    sectors = sectors[:MAX_RETURN_SECTORS]

    return {
        "sectors": sectors,
        "insights": clean_insights,
        "statusNote": status_note,
        "sourceNote": analysis_source_note or source_note,
        "detailLoaded": not bool(analysis_result.get("error")),
    }


def _empty_sector_overview(status_note: str | None, source_note: str, stock_codes: list[str]) -> dict[str, Any]:
    return {
        "overview": {
            "sectors": [],
            "insights": [],
            "statusNote": status_note,
            "sourceNote": source_note,
            "detailLoaded": False,
        },
        "meta": {
            "mcpStatus": "quota_blocked",
            "timestamp": int(time.time()),
            "probeStockCodes": stock_codes,
        },
    }


def get_sector_overview(stock_codes: list[Any] | None) -> dict[str, Any]:
    probe_codes = _normalize_probe_codes(stock_codes)
    source_note = f"基于 {len(probe_codes)} 只自选股关联的 MCP 行业/概念板块聚合"
    cache_entry = _load_cache(probe_codes)
    cached_payload = cache_entry.get("payload") if isinstance(cache_entry, dict) else None

    if _cache_is_fresh(cache_entry) and isinstance(cached_payload, dict):
        cached_copy = dict(cached_payload)
        meta = dict(cached_copy.get("meta") or {})
        meta["mcpStatus"] = "cache"
        cached_copy["meta"] = meta
        return cached_copy

    model_gate_reason = _model_gate_reason()
    if model_gate_reason:
        if isinstance(cached_payload, dict):
            cached_copy = dict(cached_payload)
            overview = dict(cached_copy.get("overview") or {})
            overview["statusNote"] = _join_notes(overview.get("statusNote"), model_gate_reason)
            cached_copy["overview"] = overview
            meta = dict(cached_copy.get("meta") or {})
            meta["mcpStatus"] = "cache_stale"
            cached_copy["meta"] = meta
            return cached_copy
        return _empty_sector_overview(model_gate_reason, source_note, probe_codes)

    try:
        market_payload = _unpack_mcp_result(mcp.tool_call("get_market_change_ratio_status", {}))
        market_summary = _extract_market_summary(market_payload)

        status_note: str | None = None
        sector_candidates: list[dict[str, Any]] = []
        for code in probe_codes:
            try:
                merge_payload = _unpack_mcp_result(mcp.tool_call("get_stock_realtime_quote_merge", {"stockCode": code}))
                sector_candidates.extend(_extract_sector_candidates(merge_payload, code))
            except Exception as exc:
                status_note = _join_notes(status_note, f"股票 {code} 的关联板块提取失败：{exc}")

        aggregated_sectors = _aggregate_sector_candidates(sector_candidates)
        if not aggregated_sectors:
            payload = {
                "overview": {
                    "sectors": [],
                    "insights": [],
                    "statusNote": _join_notes(status_note, "MCP 已返回行情，但暂未识别出可展示的板块结构"),
                    "sourceNote": source_note,
                    "detailLoaded": False,
                },
                "meta": {
                    "mcpStatus": "ready",
                    "timestamp": int(time.time()),
                    "probeStockCodes": probe_codes,
                },
            }
            _save_cache(probe_codes, payload)
            return payload

        now = datetime.now()
        recent_news = _unpack_mcp_result(
            mcp.tool_call(
                "list_news",
                {
                    "beginTime": (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
                    "endTime": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "pageNum": 1,
                    "pageSize": 12,
                },
            )
        )
        news_items = _extract_news_items(recent_news)

        analysis_result = _analyze_sector_overview_with_model(
            aggregated_sectors,
            market_summary,
            news_items,
            source_note,
        )

        payload = {
            "overview": _build_sector_overview(
                aggregated_sectors,
                analysis_result,
                status_note=status_note,
                source_note=source_note,
            ),
            "meta": {
                "mcpStatus": "ready",
                "timestamp": int(time.time()),
                "probeStockCodes": probe_codes,
            },
        }
        _save_cache(probe_codes, payload)
        return payload
    except mcp.McpResourcePackageError:
        quota_note = (
            "今日投资 MCP 已连通，但当前账号没有可用资源包，"
            "板块图表与分析会在资源包恢复后自动切换为真实数据。"
        )
        if isinstance(cached_payload, dict):
            cached_copy = dict(cached_payload)
            overview = dict(cached_copy.get("overview") or {})
            overview["statusNote"] = _join_notes(overview.get("statusNote"), quota_note)
            cached_copy["overview"] = overview
            meta = dict(cached_copy.get("meta") or {})
            meta["mcpStatus"] = "cache_stale"
            cached_copy["meta"] = meta
            return cached_copy
        return _empty_sector_overview(quota_note, source_note, probe_codes)
    except Exception as exc:
        if isinstance(cached_payload, dict):
            cached_copy = dict(cached_payload)
            overview = dict(cached_copy.get("overview") or {})
            overview["statusNote"] = _join_notes(
                overview.get("statusNote"),
                f"板块分析刷新失败，当前展示的是最近一次缓存：{exc}",
            )
            cached_copy["overview"] = overview
            meta = dict(cached_copy.get("meta") or {})
            meta["mcpStatus"] = "cache_stale"
            cached_copy["meta"] = meta
            return cached_copy
        raise SectorServiceError(f"板块分析获取失败：{exc}") from exc
