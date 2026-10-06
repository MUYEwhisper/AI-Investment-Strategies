from __future__ import annotations

import base64
import hashlib
import os
import secrets
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode, urlparse

import requests
from flask import Blueprint, has_request_context, jsonify, redirect, request

from utils.auth.context import get_current_session_id, get_current_user, require_auth
from utils.auth.session import (
    create_oauth_pending,
    create_session,
    consume_oauth_pending,
    list_active_sessions,
    revoke_other_sessions,
    revoke_session,
    upsert_user_from_userinfo,
)
from utils.db.mysql import ensure_mysql_schema


auth_page = Blueprint("auth", __name__)


def _clean(input_text: str | None) -> str:
    return str(input_text or "").strip()


def _get_env(primary: str, fallback: str = "") -> str:
    return _clean(os.getenv(primary) or fallback)


def _auth_base() -> str:
    return _get_env("KSUSER_AUTH_BASE", _get_env("VITE_KSUSER_AUTH_BASE", "https://auth.ksuser.cn")).rstrip("/")


def _api_base() -> str:
    return _get_env("KSUSER_API_BASE", _get_env("VITE_KSUSER_API_BASE", "https://api.ksuser.cn")).rstrip("/")


def _client_id() -> str:
    return _get_env("KSUSER_CLIENT_ID", _get_env("VITE_KSUSER_CLIENT_ID"))


def _client_secret() -> str:
    return _get_env("KSUSER_CLIENT_SECRET", _get_env("VITE_KSUSER_CLIENT_SECRET"))


def _request_origin() -> str:
    if not has_request_context():
        return ""

    forwarded_proto = _clean(request.headers.get("X-Forwarded-Proto")).split(",")[0].strip()
    forwarded_host = _clean(request.headers.get("X-Forwarded-Host")).split(",")[0].strip()
    host_header = _clean(request.headers.get("Host")).split(",")[0].strip()

    proto = forwarded_proto or _clean(request.scheme) or "https"
    host = forwarded_host or host_header or _clean(request.host).split(",")[0].strip()
    if not host:
        return ""

    return f"{proto}://{host}".rstrip("/")


def _base_redirect_uri() -> str:
    configured = _get_env("KSUSER_REDIRECT_URI", _get_env("VITE_KSUSER_REDIRECT_URI"))
    if configured:
        return configured

    host = _request_origin() or _get_env("APP_PUBLIC_ORIGIN", "http://localhost:5173").rstrip("/")
    return f"{host}/auth/callback"


def _scope_text() -> str:
    scope = _get_env("KSUSER_SCOPE", _get_env("VITE_KSUSER_SCOPE", "profile email"))
    normalized: list[str] = []
    for part in scope.split():
        item = part.strip().lower()
        if not item or item == "openid":
            continue
        if item not in normalized:
            normalized.append(item)

    if not normalized:
        normalized = ["profile", "email"]

    return " ".join(normalized)


def _swap_www_redirect_uri(redirect_uri: str) -> str | None:
    parsed = urlparse(redirect_uri)
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        return None

    if hostname.startswith("www."):
        swapped_host = hostname[4:]
    elif "." in hostname:
        swapped_host = f"www.{hostname}"
    else:
        return None

    netloc = swapped_host
    if parsed.port:
        netloc = f"{swapped_host}:{parsed.port}"

    return parsed._replace(netloc=netloc).geturl()


def _extra_redirect_uri_candidates() -> list[str]:
    raw = _get_env("KSUSER_REDIRECT_URI_FALLBACKS")
    if not raw:
        return []

    candidates = []
    for item in raw.replace("\n", ",").split(","):
        value = item.strip()
        if value:
            candidates.append(value)

    return candidates


def _is_redirect_uri_mismatch_message(message: str) -> bool:
    normalized = message.strip().lower()
    return "redirect_uri" in normalized and ("不一致" in message or "mismatch" in normalized)


def _redirect_uri_candidate_is_allowed(redirect_uri: str, scope_text: str) -> bool:
    params = {
        "response_type": "code",
        "client_id": _client_id(),
        "redirect_uri": redirect_uri,
        "scope": scope_text,
    }

    try:
        response = requests.get(
            f"{_api_base()}/oauth2/authorize/context",
            params=params,
            headers={"Accept": "application/json"},
            timeout=8,
        )
    except requests.RequestException:
        return True

    payload: dict[str, Any] = {}
    try:
        parsed = response.json()
        payload = parsed if isinstance(parsed, dict) else {}
    except ValueError:
        payload = {}

    message = _clean(str(payload.get("msg") or payload.get("error") or payload.get("error_description") or ""))
    if response.status_code < 400 or not message:
        return True

    return not _is_redirect_uri_mismatch_message(message)


def _resolve_redirect_uri(scope_text: str) -> str:
    primary = _base_redirect_uri()
    candidates = [primary]

    swapped = _swap_www_redirect_uri(primary)
    if swapped:
        candidates.append(swapped)

    candidates.extend(_extra_redirect_uri_candidates())

    deduped: list[str] = []
    for candidate in candidates:
        if candidate not in deduped:
            deduped.append(candidate)

    for candidate in deduped:
        if _redirect_uri_candidate_is_allowed(candidate, scope_text):
            return candidate

    return primary


def _base64_url_sha256(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def _now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def _dt_to_ms(value: datetime | None, fallback_ms: int) -> int:
    if not value:
        return fallback_ms
    return int(value.replace(tzinfo=UTC).timestamp() * 1000)


def _build_session_payload(token: str, session_row: dict[str, Any], userinfo: dict[str, Any], scope_text: str) -> dict[str, Any]:
    scope_parts = [part for part in scope_text.split() if part]
    created_ms = _dt_to_ms(session_row.get("createdAt"), _now_ms())
    expires_ms = _dt_to_ms(session_row.get("expiresAt"), created_ms + 7 * 24 * 60 * 60 * 1000)

    return {
        "accessToken": token,
        "tokenType": "Bearer",
        "scope": scope_parts,
        "scopeText": " ".join(scope_parts),
        "openid": str(userinfo.get("openid") or ""),
        "unionid": str(userinfo.get("unionid") or ""),
        "idToken": str(session_row.get("idToken") or ""),
        "expiresAt": expires_ms,
        "createdAt": created_ms,
        "clientId": _client_id(),
        "redirectUri": _resolve_redirect_uri(scope_text),
        "authorizeEndpoint": f"{_auth_base()}/oauth/authorize",
        "tokenEndpoint": f"{_api_base()}/oauth2/token",
        "userinfoEndpoint": f"{_api_base()}/oauth2/userinfo",
        "profile": {
            "openid": str(userinfo.get("openid") or ""),
            "unionid": str(userinfo.get("unionid") or ""),
            "sub": str(userinfo.get("sub") or ""),
            "nickname": str(userinfo.get("nickname") or ""),
            "avatar_url": str(userinfo.get("avatar_url") or ""),
            "email": str(userinfo.get("email") or ""),
        },
    }


def _require_oauth_config() -> str | None:
    if not _client_id():
        return "缺少 KSUSER_CLIENT_ID 配置"
    if not _client_secret():
        return "缺少 KSUSER_CLIENT_SECRET 配置"
    return None


@auth_page.route("/start", methods=["GET"])
def start_oauth():
    ensure_mysql_schema()
    config_error = _require_oauth_config()
    if config_error:
        return jsonify({"success": False, "error": config_error}), 500

    redirect_to = _clean(request.args.get("redirect_to") or "/")
    if not redirect_to.startswith("/"):
        redirect_to = "/"

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    scope_text = _scope_text()
    redirect_uri = _resolve_redirect_uri(scope_text)
    code_challenge = _base64_url_sha256(code_verifier)

    create_oauth_pending(
        state=state,
        nonce=nonce,
        code_verifier=code_verifier,
        scope_text=scope_text,
        redirect_to=redirect_to,
    )

    query = {
        "response_type": "code",
        "client_id": _client_id(),
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if scope_text:
        query["scope"] = scope_text
    if "openid" in scope_text.split():
        query["nonce"] = nonce

    authorize_url = f"{_auth_base()}/oauth/authorize?{urlencode(query)}"
    return redirect(authorize_url, code=302)


@auth_page.route("/callback", methods=["GET"])
def finish_oauth():
    ensure_mysql_schema()
    config_error = _require_oauth_config()
    if config_error:
        return jsonify({"success": False, "error": config_error}), 500

    auth_error = _clean(request.args.get("error"))
    if auth_error:
        description = _clean(request.args.get("error_description"))
        return jsonify({"success": False, "error": description or auth_error}), 400

    code = _clean(request.args.get("code"))
    state = _clean(request.args.get("state"))
    if not code or not state:
        return jsonify({"success": False, "error": "回调参数不完整，请重新登录"}), 400

    pending = consume_oauth_pending(state)
    if not pending:
        return jsonify({"success": False, "error": "授权会话已失效，请重新登录"}), 400

    pending_scope = _clean(pending.get("scopeText") or _scope_text())
    redirect_uri = _resolve_redirect_uri(pending_scope)

    token_resp = requests.post(
        f"{_api_base()}/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": _client_id(),
            "client_secret": _client_secret(),
            "redirect_uri": redirect_uri,
            "code_verifier": pending["codeVerifier"],
        },
        timeout=15,
    )
    try:
        token_payload = token_resp.json()
    except ValueError:
        token_payload = {}

    if token_resp.status_code >= 400:
        return jsonify(
            {
                "success": False,
                "error": str(token_payload.get("error_description") or token_payload.get("error") or "Token 交换失败"),
            }
        ), 400

    ks_access_token = _clean(token_payload.get("access_token"))
    if not ks_access_token:
        return jsonify({"success": False, "error": "未获取到 Ksuser access_token"}), 400

    userinfo_resp = requests.get(
        f"{_api_base()}/oauth2/userinfo",
        headers={"Authorization": f"Bearer {ks_access_token}", "Accept": "application/json"},
        timeout=15,
    )
    try:
        userinfo_payload = userinfo_resp.json()
    except ValueError:
        userinfo_payload = {}

    if userinfo_resp.status_code >= 400:
        return jsonify({"success": False, "error": "读取用户信息失败"}), 400

    try:
        user_id = upsert_user_from_userinfo(userinfo_payload)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    local_session = create_session(
        user_id=user_id,
        ip=_clean(request.headers.get("X-Forwarded-For") or request.remote_addr),
        user_agent=_clean(request.headers.get("User-Agent")),
    )

    session_payload = _build_session_payload(
        token=local_session["token"],
        session_row={
            "createdAt": local_session.get("createdAt"),
            "expiresAt": local_session.get("expiresAt"),
            "idToken": token_payload.get("id_token"),
        },
        userinfo=userinfo_payload,
        scope_text=_clean(token_payload.get("scope") or pending.get("scopeText") or _scope_text()),
    )

    return jsonify(
        {
            "success": True,
            "session": session_payload,
            "returnTo": pending.get("redirectTo") or "/",
        }
    )


@auth_page.route("/me", methods=["GET"])
@require_auth
def get_me():
    user = get_current_user()
    return jsonify(
        {
            "success": True,
            "user": {
                "id": int(user["id"]),
                "openid": user["openid"],
                "unionid": user["unionid"],
                "nickname": user.get("nickname") or "",
                "email": user.get("email") or "",
                "avatar_url": user.get("avatar_url") or "",
            },
        }
    )


@auth_page.route("/sessions", methods=["GET"])
@require_auth
def get_sessions():
    user = get_current_user()
    current_session_id = get_current_session_id()
    sessions = list_active_sessions(int(user["id"]), current_session_id)
    return jsonify({"success": True, "sessions": sessions})


@auth_page.route("/revoke", methods=["POST"])
@require_auth
def revoke_access():
    payload = request.get_json(silent=True) or {}
    target = _clean(payload.get("target") or "current").lower()

    user = get_current_user()
    current_session_id = get_current_session_id()

    if target == "others":
        revoked = revoke_other_sessions(int(user["id"]), current_session_id)
        return jsonify({"success": True, "revoked": revoked, "target": "others"})

    revoke_session(current_session_id)
    return jsonify({"success": True, "revoked": 1, "target": "current"})


@auth_page.route("/logout", methods=["POST"])
@require_auth
def logout_access():
    revoke_session(get_current_session_id())
    return jsonify({"success": True})
