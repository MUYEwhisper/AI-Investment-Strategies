"""Exercise real MCP transport/extraction with isolated provider responses."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import utils.mcp.init as mcp
from utils.models import availability
from utils.sectors import service


def quote_response(code: str):
    response = Mock(ok=True, status_code=200)
    response.json.return_value = {"result": {"structuredContent": {"data": {
        "industryRealQuote": {"industryName": f"行业{code}", "industryCode": code,
                              "changeRatio": 0.01, "totalValue": 100},
    }}}}
    return response


class SectorResilienceTests(unittest.TestCase):
    def setUp(self):
        self.no_network = patch("socket.socket", side_effect=AssertionError("Network is disabled"))
        self.no_network.start()
        self.addCleanup(self.no_network.stop)
        self.no_sleep = patch.object(service.time, "sleep")
        self.no_sleep.start()
        self.addCleanup(self.no_sleep.stop)
        self.retry_setting = patch.object(service, "SECTOR_MCP_RETRY_COUNT", 1)
        self.retry_setting.start()
        self.addCleanup(self.retry_setting.stop)

    def test_slow_quote_recovers_once_with_longer_read_budget(self):
        with patch.object(mcp.requests, "post", side_effect=[requests.ReadTimeout(), quote_response("000969")]) as post:
            candidates = service._fetch_sector_candidates_for_code("000969")
        self.assertEqual([item["sourceStockCode"] for item in candidates], ["000969"])
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args.kwargs["timeout"], (5, service.SECTOR_MCP_READ_TIMEOUT_SECONDS))

    def test_retry_is_bounded_and_timeout_remains_actionable(self):
        with patch.object(mcp.requests, "post", side_effect=requests.ReadTimeout()) as post:
            with self.assertRaisesRegex(mcp.McpTimeoutError, "超时"):
                service._fetch_sector_candidates_for_code("000969")
        self.assertEqual(post.call_count, 2)

    def test_other_mcp_callers_keep_their_timeout_and_are_not_retried(self):
        with patch.object(mcp.requests, "post", side_effect=requests.ReadTimeout()) as post:
            with self.assertRaises(mcp.McpTimeoutError):
                mcp.tool_call("get_stock_quote_realtime", {"stockCode": "000969"})
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs["timeout"], mcp.MCP_TIMEOUT_SECONDS)

    def test_resource_package_failure_is_not_retried(self):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {"error": {"code": -32000, "message": "无可用的资源包"}}
        with patch.object(mcp.requests, "post", return_value=response) as post:
            with self.assertRaises(mcp.McpResourcePackageError):
                service._fetch_sector_candidates_for_code("000969")
        self.assertEqual(post.call_count, 1)

    def test_expired_shared_data_budget_does_not_start_another_provider_call(self):
        with patch.object(service.time, "monotonic", return_value=46), \
             patch.object(mcp.requests, "post") as post:
            with self.assertRaisesRegex(mcp.McpTimeoutError, "刷新时限"):
                service._fetch_sector_candidates_for_code("000969", deadline=45)
        post.assert_not_called()

    def test_retry_uses_only_remaining_shared_budget(self):
        clock = Mock(return_value=0)
        attempts = 0

        def provider(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                clock.return_value = 44
                raise requests.ReadTimeout()
            return quote_response("000969")

        with patch.object(service.time, "monotonic", clock), \
             patch.object(mcp.requests, "post", side_effect=provider) as post:
            result = service._fetch_sector_candidates_for_code("000969", deadline=45)
        self.assertTrue(result)
        self.assertEqual(post.call_args_list[0].kwargs["timeout"], (5, 30))
        self.assertEqual(sum(post.call_args_list[1].kwargs["timeout"]), 1)

    def test_expired_model_budget_returns_quantitative_fallback_without_provider_call(self):
        client = Mock()
        with patch.object(service, "ANALYSIS_CLIENT", client), \
             patch.object(service.time, "monotonic", return_value=86):
            result = service._analyze_sector_overview_with_model([], {}, [], "测试", deadline=85)
        self.assertIn("刷新时限", result["error"])
        client.with_options.assert_not_called()

    def test_short_model_probe_does_not_wait_for_another_unbounded_probe(self):
        lock = Mock()
        lock.acquire.return_value = False
        client = Mock()
        with patch.object(availability, "_probe_lock", lock), \
             patch.object(availability, "ANALYSIS_CLIENT", client), \
             patch.dict(availability._probe_cache, {"checkedAt": 0}):
            result = availability.get_model_availability(timeout_seconds=1)
        self.assertFalse(result["available"])
        lock.acquire.assert_called_once_with(timeout=1)
        client.with_options.assert_not_called()

    def test_short_model_timeout_does_not_poison_shared_availability_cache(self):
        client = Mock()
        client.with_options.return_value.chat.completions.create.side_effect = TimeoutError("short probe timeout")
        previous = {"checkedAt": 0.0, "available": False, "reason": "未完成检测"}
        with patch.object(availability, "ANALYSIS_CLIENT", client), \
             patch.dict(availability._probe_cache, previous, clear=True):
            short_result = availability.get_model_availability(timeout_seconds=0.1)
            self.assertFalse(short_result["available"])
            self.assertEqual(availability._probe_cache, previous)
            full_result = availability.get_model_availability()
            self.assertTrue(full_result["available"])
            client.chat.completions.create.assert_called_once()

    def test_real_provider_auth_error_still_updates_shared_negative_cache(self):
        client = Mock()
        client.with_options.return_value.chat.completions.create.side_effect = RuntimeError("invalid API key")
        with patch.object(availability, "ANALYSIS_CLIENT", client), \
             patch.dict(availability._probe_cache, {"checkedAt": 0.0}, clear=True):
            result = availability.get_model_availability(timeout_seconds=1)
            self.assertFalse(result["available"])
            self.assertEqual(availability._probe_cache, result)

    def test_executor_exit_and_queued_requests_respect_shared_deadline(self):
        observed_budgets: list[float] = []
        lock = threading.Lock()

        def slow_provider(*args, **kwargs):
            budget = sum(kwargs["timeout"])
            with lock:
                observed_budgets.append(budget)
            threading.Event().wait(min(budget, 0.1))
            raise requests.ReadTimeout()

        started = time.monotonic()
        with patch.object(service, "_load_cache", return_value=None), \
             patch.object(service, "_model_gate_reason", return_value=None), \
             patch.object(service, "SECTOR_MCP_TOTAL_TIMEOUT_SECONDS", 0.08), \
             patch.object(service, "SECTOR_TOTAL_TIMEOUT_SECONDS", 0.12), \
             patch.object(mcp.requests, "post", side_effect=slow_provider), \
             patch.object(service, "_save_cache"):
            result = service.get_sector_overview([f"{index:06d}" for index in range(12)])
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 1, "executor waited past the bounded network phase")
        self.assertTrue(observed_budgets)
        self.assertLessEqual(max(observed_budgets), 0.08)
        self.assertTrue(all(budget < 0.02 for budget in observed_budgets[6:]),
                        "queued jobs restarted a fresh timeout window")
        self.assertEqual(result["meta"]["mcpStatus"], "partial")

    def test_five_concurrent_stocks_retry_only_the_failed_stock(self):
        calls: dict[str, int] = {}
        lock = threading.Lock()
        codes = ["601138", "000969", "300308", "002636", "600105"]

        def provider(*args, **kwargs):
            code = kwargs["json"]["params"]["arguments"]["stockCode"]
            with lock:
                calls[code] = calls.get(code, 0) + 1
                first = calls[code] == 1
            if code == "000969" and first:
                raise requests.ReadTimeout()
            return quote_response(code)

        with patch.object(mcp.requests, "post", side_effect=provider):
            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(service._fetch_sector_candidates_for_code, codes))
        self.assertEqual({group[0]["sourceStockCode"] for group in results}, set(codes))
        self.assertEqual(calls, {code: 2 if code == "000969" else 1 for code in codes})

    def test_partial_refresh_preserves_complete_cache_without_overwriting_it(self):
        cached = {"overview": {"sectors": [{"name": "完整缓存"}], "insights": ["上次解读"]},
                  "meta": {"timestamp": 123, "mcpStatus": "ready"}}
        with patch.object(service, "_load_cache", return_value={"cachedAt": 0, "payload": cached}), \
             patch.object(service, "_model_gate_reason", return_value=None), \
             patch.object(service, "_fetch_market_summary", return_value={}), \
             patch.object(service, "_fetch_recent_news_items", return_value=[]), \
             patch.object(service, "_fetch_sector_candidates_for_code", side_effect=mcp.McpTimeoutError("超时")), \
             patch.object(service, "_save_cache") as save, \
             patch.object(service, "_analyze_sector_overview_with_model") as model:
            result = service.get_sector_overview(["000969"])
        self.assertEqual(result["overview"]["sectors"], cached["overview"]["sectors"])
        self.assertIn("最近一次完整分析", result["overview"]["statusNote"])
        self.assertEqual(result["meta"]["mcpStatus"], "cache_stale")
        self.assertEqual(result["meta"]["failedStockCodes"], ["000969"])
        self.assertEqual(cached["meta"]["mcpStatus"], "ready")
        save.assert_not_called()
        model.assert_not_called()

    def test_failed_initial_refresh_is_not_cached_as_success(self):
        with patch.object(service, "_load_cache", return_value=None), \
             patch.object(service, "_model_gate_reason", return_value=None), \
             patch.object(service, "_fetch_market_summary", return_value={}), \
             patch.object(service, "_fetch_recent_news_items", return_value=[]), \
             patch.object(service, "_fetch_sector_candidates_for_code", side_effect=mcp.McpTimeoutError("超时")), \
             patch.object(service, "_save_cache") as save:
            result = service.get_sector_overview(["000969"])
        self.assertEqual(result["meta"]["mcpStatus"], "partial")
        self.assertEqual(result["overview"]["sectors"], [])
        save.assert_not_called()

    def test_quota_failure_from_concurrent_worker_reaches_quota_response(self):
        with patch.object(service, "_load_cache", return_value=None), \
             patch.object(service, "_model_gate_reason", return_value=None), \
             patch.object(service, "_fetch_market_summary", return_value={}), \
             patch.object(service, "_fetch_recent_news_items", return_value=[]), \
             patch.object(service, "_fetch_sector_candidates_for_code", side_effect=mcp.McpResourcePackageError("无可用的资源包")), \
             patch.object(service, "_save_cache") as save:
            result = service.get_sector_overview(["000969"])
        self.assertEqual(result["meta"]["mcpStatus"], "quota_blocked")
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
