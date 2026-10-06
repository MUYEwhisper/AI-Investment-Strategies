import os
import re
import uuid

import requests
from dotenv import load_dotenv

load_dotenv()

MCP_URL = "https://data-api.investoday.net/data/mcp/preset"
API_KEY = os.environ.get('STOCK_MCP_API_KEY')
MCP_TIMEOUT_SECONDS = max(5, int(os.environ.get("STOCK_MCP_TIMEOUT_SECONDS", "8")))


class McpError(RuntimeError):
    """MCP 调用失败。"""

    def __init__(self, message: str, *, code=None, status_code=None, data=None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.data = data


class McpResourcePackageError(McpError):
    """账号没有可用资源包时抛出。"""


HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
URL_PATTERN = re.compile(r"https?://\S+")


def _sanitize_error_message(message: str | None, *, status_code: int | None = None) -> str:
    raw = str(message or "").strip()
    lowered = raw.lower()

    if "<html" in lowered or "<!doctype html" in lowered:
        if status_code == 504 or "504" in lowered or "gateway time-out" in lowered or "gateway timeout" in lowered:
            return "上游行情服务网关超时（HTTP 504），请稍后重试。"
        if status_code == 503 or "503" in lowered or "service unavailable" in lowered:
            return "上游行情服务暂不可用（HTTP 503），请稍后重试。"
        if status_code == 502 or "502" in lowered or "bad gateway" in lowered:
            return "上游行情服务网关异常（HTTP 502），请稍后重试。"
        return "上游行情服务返回了异常页面，请稍后重试。"

    if raw:
        cleaned = HTML_TAG_PATTERN.sub(" ", raw)
        cleaned = URL_PATTERN.sub("上游服务", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            return cleaned[:220]

    if isinstance(status_code, int):
        return f"MCP 请求失败（HTTP {status_code}）"
    return "MCP 请求失败"


def _build_mcp_error(response: requests.Response, data):
    error = data.get("error") if isinstance(data, dict) else None
    message = None
    code = None

    if isinstance(error, dict):
        message = error.get("message")
        code = error.get("code")

    if not message:
        message = response.text or f"MCP request failed: HTTP {response.status_code}"

    message = _sanitize_error_message(message, status_code=response.status_code)

    error_cls = McpResourcePackageError if "无可用的资源包" in message else McpError
    return error_cls(
        message,
        code=code,
        status_code=response.status_code,
        data=data,
    )


def call(method: str, params: dict):
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": method,
        "params": params
    }

    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            f"{MCP_URL}?apiKey={API_KEY}",
            json=payload,
            headers=headers,
            timeout=MCP_TIMEOUT_SECONDS,
        )
    except requests.Timeout as exc:
        raise McpError("连接今日投资 MCP 超时，请稍后重试。") from exc
    except requests.RequestException as exc:
        raise McpError(_sanitize_error_message(str(exc))) from exc

    try:
        data = response.json()
    except ValueError:
        if response.ok:
            raise McpError("MCP 返回了无法解析的数据格式。")
        raise McpError(
            _sanitize_error_message(response.text, status_code=response.status_code),
            status_code=response.status_code,
        )

    if not response.ok or (isinstance(data, dict) and data.get("error")):
        raise _build_mcp_error(response, data)

    return data


def mcp_to_openai_tool(mcp_tool):
    return {
        "type": "function",
        "function": {
            "name": mcp_tool["name"],
            "description": mcp_tool.get("description"),
            "parameters": mcp_tool.get("inputSchema")
        },
    }

def tool_list():
    data = call("tools/list", {})
    mcp_tools = data.get("result", []).get("tools", [])
    return [mcp_to_openai_tool(t) for t in mcp_tools]

def tool_call(name, arguments):
    return call(
        "tools/call",
        {
            "name": name,
            "arguments": arguments
        }
    )

if __name__ == "__main__":
    print(tool_list())
    print(tool_call("get_stock_quote_realtime", {"stockCode": "600519"}))
