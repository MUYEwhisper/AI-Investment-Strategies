from __future__ import annotations

import os
import threading
import time
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

ANALYSIS_MODEL = os.environ.get("STOCK_ANALYSIS_MODEL", "deepseek-chat")
ANALYSIS_TIMEOUT_SECONDS = int(os.environ.get("STOCK_ANALYSIS_TIMEOUT_SECONDS", "45"))
MODEL_PROBE_TTL_SECONDS = max(30, int(os.environ.get("STOCK_MODEL_PROBE_TTL_SECONDS", "60")))

ANALYSIS_CLIENT = None
if os.environ.get("DEEPSEEK_API_KEY"):
    ANALYSIS_CLIENT = OpenAI(
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
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


def get_model_availability(force_refresh: bool = False) -> dict[str, Any]:
    if ANALYSIS_CLIENT is None:
        return {
            "checkedAt": time.time(),
            "available": False,
            "reason": "未配置 DeepSeek API Key",
        }

    now = time.time()
    if not force_refresh and now - float(_probe_cache.get("checkedAt") or 0) <= MODEL_PROBE_TTL_SECONDS:
        return dict(_probe_cache)

    with _probe_lock:
        now = time.time()
        if not force_refresh and now - float(_probe_cache.get("checkedAt") or 0) <= MODEL_PROBE_TTL_SECONDS:
            return dict(_probe_cache)

        try:
            ANALYSIS_CLIENT.chat.completions.create(
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

        _probe_cache.update(result)
        return dict(_probe_cache)


def ensure_model_available(force_refresh: bool = False) -> dict[str, Any]:
    availability = get_model_availability(force_refresh=force_refresh)
    if not availability.get("available"):
        reason = str(availability.get("reason") or "模型服务暂不可用")
        raise ModelUnavailableError(reason)
    return availability
