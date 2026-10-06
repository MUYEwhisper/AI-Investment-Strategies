from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from flask import g, jsonify, request

from utils.auth.session import find_session_by_token


def _extract_bearer_token(header: str) -> str | None:
    value = str(header or "").strip()
    if not value.lower().startswith("bearer "):
        return None
    token = value[7:].strip()
    return token or None


def get_current_user() -> dict[str, Any]:
    user = getattr(g, "current_user", None)
    if not isinstance(user, dict):
        raise RuntimeError("authenticated user is missing")
    return user


def get_current_user_id() -> int:
    user = get_current_user()
    return int(user.get("id") or 0)


def get_current_session_id() -> int:
    session = getattr(g, "current_session", None)
    if not isinstance(session, dict):
        raise RuntimeError("authenticated session is missing")
    return int(session.get("id") or 0)


def _apply_auth_record(record: Any) -> None:
    g.current_user = dict(record.user)
    g.current_session = {
        "id": int(record.session_id),
        "expires_at": record.expires_at,
        "created_at": record.created_at,
    }


def try_auth_from_request() -> tuple[bool, str | None]:
    token = _extract_bearer_token(request.headers.get("Authorization", ""))
    if not token:
        return False, None

    record = find_session_by_token(token)
    if not record:
        return False, "登录会话无效或已过期"

    _apply_auth_record(record)
    return True, None


def require_auth(func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any):
        is_authenticated, error = try_auth_from_request()
        if error:
            return jsonify({"success": False, "error": error}), 401

        if not is_authenticated:
            return jsonify({"success": False, "error": "未登录或令牌缺失"}), 401
        return func(*args, **kwargs)

    return wrapper
