"""Isolated Flask contract tests; no provider, credentials, database or network."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

from flask import Flask


class LocalContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Load the real route while replacing its import-time external dependencies.
        modules = {}
        for name in ("utils", "utils.auth", "utils.models", "utils.mcp"):
            module = types.ModuleType(name)
            module.__path__ = []
            modules[name] = module
        auth = types.ModuleType("utils.auth.context")
        auth.get_current_user_id = Mock(side_effect=AssertionError("Unexpected auth call"))
        auth.try_auth_from_request = Mock(side_effect=AssertionError("Unexpected auth call"))
        model = types.ModuleType("utils.models.deepseek")
        model.chat = Mock(side_effect=AssertionError("Unexpected cloud model call"))
        cls.provider = types.ModuleType("utils.mcp.init")
        cls.provider.tool_call = Mock()
        modules.update({auth.__name__: auth, model.__name__: model,
                        cls.provider.__name__: cls.provider})
        modules["utils"].mcp = modules["utils.mcp"]
        modules["utils.mcp"].init = cls.provider
        route_path = Path(__file__).resolve().parents[1] / "pages" / "chat.py"
        spec = importlib.util.spec_from_file_location("isolated_chat_routes", route_path)
        route = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(route)
        app = Flask(__name__)
        app.config.update(TESTING=True)
        app.register_blueprint(route.chat_page, url_prefix="/chat")
        cls.client = app.test_client()

    def setUp(self):
        self.provider.tool_call.reset_mock()
        self.provider.tool_call.side_effect = None
        self.provider.tool_call.return_value = {"fixture": "synthetic"}
        # A future route change must not silently add real network I/O to these tests.
        self.no_network = patch("socket.socket", side_effect=AssertionError("Network is disabled"))
        self.no_network.start()
        self.addCleanup(self.no_network.stop)

    def post(self, prompt):
        response = self.client.post("/chat/local-context", json={"prompt": prompt})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/json")
        payload = response.get_json()
        self.assertIs(payload["success"], True)
        self.assertEqual(payload["source"], "今日投资 MCP")
        return payload["records"]

    def test_codes_are_deduplicated_and_limited_to_first_three(self):
        records = self.post("600519 000001 600519 300750 601318")
        self.assertEqual([r["arguments"]["stockCode"] for r in records],
                         ["600519", "000001", "300750"])
        self.assertEqual([r["tool"] for r in records], ["get_stock_realtime_quote"] * 3)
        self.assertEqual(self.provider.tool_call.call_count, 3)

    def test_code_boundaries_and_supported_prefixes(self):
        records = self.post("1600519 6005190 123456 200001 830799 600036")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["arguments"], {"stockCode": "600036"})

    def test_each_market_keyword_requests_market_tool(self):
        for word in ("市场", "大盘", "行情", "指数", "板块", "情绪"):
            with self.subTest(word=word):
                records = self.post(word)
                self.assertEqual([(r["tool"], r["arguments"]) for r in records],
                                 [("get_market_change_ratio_status", {})])

    def test_each_news_keyword_requests_news_tool(self):
        for word in ("新闻", "消息", "公告", "政策", "最近", "今日"):
            with self.subTest(word=word):
                records = self.post(word)
                self.assertEqual([(r["tool"], r["arguments"]) for r in records],
                                 [("list_news", {"pageNum": 1, "pageSize": 10})])

    def test_combined_request_has_stable_order_and_json_results(self):
        self.provider.tool_call.side_effect = [
            {"price": 10.2}, {"up": 100, "down": 80}, [{"title": "测试新闻"}]]
        records = self.post("600036 今日市场行情新闻")
        self.assertEqual([r["tool"] for r in records],
                         ["get_stock_realtime_quote", "get_market_change_ratio_status", "list_news"])
        self.assertEqual(records[0]["result"], {"price": 10.2})
        self.assertEqual(records[2]["result"], [{"title": "测试新闻"}])
        self.assertTrue(all("error" not in r for r in records))

    def test_tool_failure_is_recorded_and_later_tools_continue(self):
        self.provider.tool_call.side_effect = [RuntimeError("synthetic provider failure"),
                                              {"up": 1}, []]
        records = self.post("600036 市场新闻")
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]["error"], "synthetic provider failure")
        self.assertNotIn("result", records[0])
        self.assertEqual(records[1]["result"], {"up": 1})
        self.assertEqual(records[2]["result"], [])
        self.assertEqual(self.provider.tool_call.call_count, 3)

    def test_no_code_or_keyword_does_not_request_provider(self):
        self.assertEqual(self.post("介绍价值投资的基本概念"), [])
        self.provider.tool_call.assert_not_called()

    def test_empty_prompt_does_not_request_provider(self):
        self.assertEqual(self.post(""), [])
        self.provider.tool_call.assert_not_called()

    def test_missing_json_returns_empty_context(self):
        response = self.client.post("/chat/local-context")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["records"], [])
        self.provider.tool_call.assert_not_called()

    def test_get_method_is_not_accepted(self):
        self.assertEqual(self.client.get("/chat/local-context").status_code, 405)
        self.provider.tool_call.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
