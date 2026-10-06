from __future__ import annotations

import json

from flask import Blueprint, Response, jsonify, request

from utils.auth.context import get_current_user_id, try_auth_from_request
from utils.models.deepseek import chat

chat_page = Blueprint("chat", __name__)


def _build_chat_payload() -> tuple[dict[str, object] | None, tuple[dict[str, str], int] | None]:
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return None, ({"error": "请求体必须是 JSON 对象"}, 400)

    legacy_prompt = str(data.get("prompt") or "").strip()
    original_prompt = str(data.get("originalPrompt") or legacy_prompt).strip()
    messages = data.get("messages")
    if not isinstance(messages, list):
        messages = []

    if not original_prompt and not messages:
        return None, ({"error": "问题不能为空"}, 400)

    is_authenticated, auth_error = try_auth_from_request()
    if auth_error:
        return None, ({"error": auth_error}, 401)

    payload: dict[str, object] = {
        "chatId": str(data.get("chatId") or "").strip(),
        "agentId": str(data.get("agentId") or "").strip(),
        "systemPrompt": str(data.get("systemPrompt") or "").strip(),
        "originalPrompt": original_prompt,
        "messages": messages,
        "thinking": bool(data.get("thinking", True)),
        "userId": get_current_user_id() if is_authenticated else None,
    }
    return payload, None


@chat_page.route("/endpoint", methods=["POST"])
def chat_endpoint():
    payload, error_response = _build_chat_payload()
    if error_response:
        body, status = error_response
        return body, status

    thinking = bool(payload.get("thinking", True)) if payload else True

    def generate():
        try:
            for chunk in chat(payload or {}, stream=True, thinking=thinking):
                yield chunk
        except Exception as exc:
            error_message = (
                "event: error\n"
                f"data: {json.dumps({'error': str(exc), 'message': '处理聊天请求时发生错误'}, ensure_ascii=False)}\n\n"
            )
            yield error_message

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@chat_page.route("/endpoint-sync", methods=["POST"])
def chat_sync_endpoint():
    payload, error_response = _build_chat_payload()
    if error_response:
        body, status = error_response
        return body, status

    thinking = bool(payload.get("thinking", True)) if payload else True

    try:
        result = chat(payload or {}, stream=False, thinking=thinking)
        return jsonify({"success": True, "result": result})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500
