from __future__ import annotations

import os
import threading
import time
from typing import Any

import httpx
from dotenv import load_dotenv
from openai import APITimeoutError, OpenAI

load_dotenv()

ANALYSIS_BASE_URL = os.environ.get("STOCK_ANALYSIS_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
ANALYSIS_MODEL = os.environ.get("STOCK_ANALYSIS_MODEL", "deepseek-v4-flash")
ANALYSIS_TIMEOUT_SECONDS = int(os.environ.get("STOCK_ANALYSIS_TIMEOUT_SECONDS", "45"))
MODEL_PROBE_TTL_SECONDS = max(30, int(os.environ.get("STOCK_MODEL_PROBE_TTL_SECONDS", "60")))

# Preferred variable: STOCK_ANALYSIS_API_KEY
# Backward compatibility: BIGMODEL_API_KEY / DEEPSEEK_API_KEY
ANALYSIS_API_KEY = (
    os.environ.get("STOCK_ANALYSIS_API_KEY")
    or os.environ.get("BIGMODEL_API_KEY")
    or os.environ.get("DEEPSEEK_API_KEY")
)

ANALYSIS_CLIENT = None
if ANALYSIS_API_KEY:
    ANALYSIS_CLIENT = OpenAI(
        api_key=ANALYSIS_API_KEY,
        base_url=ANALYSIS_BASE_URL,
        timeout=ANALYSIS_TIMEOUT_SECONDS,
    )


class ModelUnavailableError(RuntimeError):
    """AI 模型当前不可用。"""


_probe_lock = threading.Lock()
_probe_cache: dict[str, Any] = {
    "checkedAt": 0.0,
    "available": False,
    "reason": "未完成检测",
}


def bounded_model_timeout(seconds: float) -> httpx.Timeout:
    # httpx's scalar timeout applies separately to each I/O phase. Divide the
    # remaining request budget instead of allowing every phase the full amount.
    connect = min(3, seconds * 0.2)
    write = pool = min(0.5, seconds * 0.025)
    return httpx.Timeout(connect=connect, read=seconds - connect - write - pool, write=write, pool=pool)


def get_model_availability(force_refresh: bool = False, *, timeout_seconds: float | None = None) -> dict[str, Any]:
    if ANALYSIS_CLIENT is None:
        return {
            "checkedAt": time.time(),
            "available": False,
            "reason": "未配置 AI 接口密钥（请设置 STOCK_ANALYSIS_API_KEY）",
        }

    now = time.time()
    if not force_refresh and now - float(_probe_cache.get("checkedAt") or 0) <= MODEL_PROBE_TTL_SECONDS:
        return dict(_probe_cache)

    deadline = time.monotonic() + timeout_seconds if timeout_seconds is not None else None
    acquired = _probe_lock.acquire(timeout=max(0, timeout_seconds)) if deadline is not None else _probe_lock.acquire()
    if not acquired:
        return {"checkedAt": now, "available": False, "reason": "模型可用性检测暂未完成，请稍后重试。"}
    try:
        now = time.time()
        if not force_refresh and now - float(_probe_cache.get("checkedAt") or 0) <= MODEL_PROBE_TTL_SECONDS:
            return dict(_probe_cache)

        try:
            client = ANALYSIS_CLIENT
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return {"checkedAt": now, "available": False, "reason": "模型可用性检测超时，请稍后重试。"}
                client = client.with_options(timeout=bounded_model_timeout(remaining), max_retries=0)
            client.chat.completions.create(
                model=ANALYSIS_MODEL,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
                temperature=0,
            )
            result = {
                "checkedAt": now,
                "available": True,
                "reason": "",
            }
        except Exception as exc:
            result = {
                "checkedAt": now,
                "available": False,
                "reason": str(exc).strip() or "模型服务暂不可用",
            }
            # A caller's short probe budget is not evidence of a provider-wide
            # outage. Do not block other routes for the shared cache TTL.
            if deadline is not None and isinstance(exc, (APITimeoutError, httpx.TimeoutException, TimeoutError)):
                return result

        _probe_cache.update(result)
        return dict(_probe_cache)
    finally:
        _probe_lock.release()


def ensure_model_available(force_refresh: bool = False, *, timeout_seconds: float | None = None) -> dict[str, Any]:
    availability = get_model_availability(force_refresh=force_refresh, timeout_seconds=timeout_seconds)
    if not availability.get("available"):
        reason = str(availability.get("reason") or "模型服务暂不可用")
        raise ModelUnavailableError(reason)
    return availability
