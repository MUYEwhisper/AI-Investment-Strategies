import os
import uuid

import requests
from dotenv import load_dotenv

load_dotenv()

MCP_URL = "https://data-api.investoday.net/data/mcp/preset"
API_KEY = os.environ.get('STOCK_MCP_API_KEY')


class McpError(RuntimeError):
    """MCP 调用失败。"""

    def __init__(self, message: str, *, code=None, status_code=None, data=None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.data = data


class McpResourcePackageError(McpError):
    """账号没有可用资源包时抛出。"""


def _build_mcp_error(response: requests.Response, data):
    error = data.get("error") if isinstance(data, dict) else None
    message = None
    code = None

    if isinstance(error, dict):
        message = error.get("message")
        code = error.get("code")

    if not message:
        message = response.text or f"MCP request failed: HTTP {response.status_code}"

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

    response = requests.post(
        f"{MCP_URL}?apiKey={API_KEY}",
        json=payload,
        headers=headers,
        timeout=60
    )

    try:
        data = response.json()
    except ValueError:
        response.raise_for_status()
        raise

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
