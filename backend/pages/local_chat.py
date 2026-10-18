from __future__ import annotations

import json

from flask import Blueprint, Response, jsonify, request

from utils.models.local import generate, status

LOCAL_SYSTEM_PROMPT = """本地智投必须遵守智投问答输出规范：使用中文，按“### 结论”“### 分析依据”“### 风险提示”分段；不自我介绍、不重复问题、不输出思维过程或 <think> 标签；只引用明确可用的数据，不虚构、不承诺收益，控制篇幅，并在结尾保留投资风险声明。"""

local_chat_page = Blueprint("local_chat", __name__)


@local_chat_page.get("/health")
def local_health():
    return jsonify(status())


@local_chat_page.post("/chat/local/endpoint")
def local_chat_endpoint():
    data = request.get_json(silent=True) or {}
    prompt = str(data.get("originalPrompt") or data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "问题不能为空"}), 400
    system_prompt = LOCAL_SYSTEM_PROMPT + "\n" + str(data.get("systemPrompt") or "")
    history = data.get("messages") if isinstance(data.get("messages"), list) else []
    mcp_context = data.get("mcpContext")

    def stream():
        try:
            yield "event: start\ndata: {\"model\": \"deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B\", \"mode\": \"local\"}\n\n"
            for chunk in generate(prompt, system_prompt, history, mcp_context):
                yield f"event: message\ndata: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
            yield "event: end\ndata: {\"finish_reason\": \"stop\"}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'message': str(exc)}, ensure_ascii=False)}\n\n"
            yield "event: end\ndata: {\"finish_reason\": \"error\"}\n\n"

    return Response(stream(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "Access-Control-Allow-Origin": "*"})
