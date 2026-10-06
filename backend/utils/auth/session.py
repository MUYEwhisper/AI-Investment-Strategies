from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from utils.db.mysql import mysql_conn

ACCESS_TOKEN_TTL_DAYS = 7
OAUTH_PENDING_TTL_MINUTES = 10


@dataclass
class AuthSessionRecord:
    session_id: int
    user_id: int
    token_hash: str
    expires_at: datetime
    revoked_at: datetime | None
    created_at: datetime
    last_seen_at: datetime
    ip: str
    user_agent: str
    user: dict[str, Any]


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_plain_token() -> str:
    return secrets.token_urlsafe(48)


def create_pkce_token(size_bytes: int = 48) -> str:
    return secrets.token_urlsafe(size_bytes)


def create_session(user_id: int, ip: str, user_agent: str) -> dict[str, Any]:
    token = create_plain_token()
    token_hash = hash_token(token)
    with mysql_conn(commit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO auth_sessions (user_id, token_hash, expires_at, ip, user_agent)
                VALUES (%s, %s, DATE_ADD(UTC_TIMESTAMP(), INTERVAL %s DAY), %s, %s)
                """,
                (user_id, token_hash, ACCESS_TOKEN_TTL_DAYS, ip[:64], user_agent[:255]),
            )
            session_id = int(cursor.lastrowid)
            cursor.execute("SELECT expires_at, created_at FROM auth_sessions WHERE id = %s", (session_id,))
            row = cursor.fetchone() or {}

    return {
        "token": token,
        "sessionId": session_id,
        "expiresAt": row.get("expires_at"),
        "createdAt": row.get("created_at"),
    }


def find_session_by_token(token: str) -> AuthSessionRecord | None:
    token_hash = hash_token(token)
    with mysql_conn(commit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                  s.id AS session_id,
                  s.user_id,
                  s.token_hash,
                  s.expires_at,
                  s.revoked_at,
                  s.created_at,
                  s.last_seen_at,
                  s.ip,
                  s.user_agent,
                  u.id AS uid,
                  u.openid,
                  u.unionid,
                  u.nickname,
                  u.email,
                  u.avatar_url
                FROM auth_sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = %s
                  AND s.revoked_at IS NULL
                  AND s.expires_at > UTC_TIMESTAMP()
                LIMIT 1
                """,
                (token_hash,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            cursor.execute(
                "UPDATE auth_sessions SET last_seen_at = UTC_TIMESTAMP() WHERE id = %s",
                (row["session_id"],),
            )

    return AuthSessionRecord(
        session_id=int(row["session_id"]),
        user_id=int(row["user_id"]),
        token_hash=str(row["token_hash"]),
        expires_at=row["expires_at"],
        revoked_at=row.get("revoked_at"),
        created_at=row["created_at"],
        last_seen_at=row["last_seen_at"],
        ip=str(row.get("ip") or ""),
        user_agent=str(row.get("user_agent") or ""),
        user={
            "id": int(row["uid"]),
            "openid": str(row["openid"]),
            "unionid": str(row["unionid"]),
            "nickname": str(row.get("nickname") or ""),
            "email": str(row.get("email") or ""),
            "avatar_url": str(row.get("avatar_url") or ""),
        },
    )


def revoke_session(session_id: int) -> None:
    with mysql_conn(commit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE auth_sessions SET revoked_at = UTC_TIMESTAMP() WHERE id = %s AND revoked_at IS NULL",
                (session_id,),
            )


def revoke_other_sessions(user_id: int, current_session_id: int) -> int:
    with mysql_conn(commit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE auth_sessions
                SET revoked_at = UTC_TIMESTAMP()
                WHERE user_id = %s
                  AND id <> %s
                  AND revoked_at IS NULL
                  AND expires_at > UTC_TIMESTAMP()
                """,
                (user_id, current_session_id),
            )
            return int(cursor.rowcount or 0)


def list_active_sessions(user_id: int, current_session_id: int) -> list[dict[str, Any]]:
    with mysql_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, created_at, last_seen_at, expires_at, ip, user_agent
                FROM auth_sessions
                WHERE user_id = %s
                  AND revoked_at IS NULL
                  AND expires_at > UTC_TIMESTAMP()
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            rows = cursor.fetchall() or []

    return [
        {
            "id": int(row["id"]),
            "createdAt": row["created_at"].isoformat(sep=" "),
            "lastSeenAt": row["last_seen_at"].isoformat(sep=" "),
            "expiresAt": row["expires_at"].isoformat(sep=" "),
            "ip": str(row.get("ip") or ""),
            "userAgent": str(row.get("user_agent") or ""),
            "isCurrent": int(row["id"]) == current_session_id,
        }
        for row in rows
    ]


def create_oauth_pending(state: str, nonce: str, code_verifier: str, scope_text: str, redirect_to: str) -> None:
    with mysql_conn(commit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO oauth_pending (state, nonce, code_verifier, scope_text, redirect_to, expires_at)
                VALUES (%s, %s, %s, %s, %s, DATE_ADD(UTC_TIMESTAMP(), INTERVAL %s MINUTE))
                ON DUPLICATE KEY UPDATE
                  nonce = VALUES(nonce),
                  code_verifier = VALUES(code_verifier),
                  scope_text = VALUES(scope_text),
                  redirect_to = VALUES(redirect_to),
                  expires_at = VALUES(expires_at)
                """,
                (state, nonce, code_verifier, scope_text, redirect_to[:500], OAUTH_PENDING_TTL_MINUTES),
            )


def consume_oauth_pending(state: str) -> dict[str, Any] | None:
    with mysql_conn(commit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT state, nonce, code_verifier, scope_text, redirect_to
                FROM oauth_pending
                WHERE state = %s
                  AND expires_at > UTC_TIMESTAMP()
                LIMIT 1
                """,
                (state,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            cursor.execute("DELETE FROM oauth_pending WHERE state = %s", (state,))
            return {
                "state": str(row["state"]),
                "nonce": str(row["nonce"]),
                "codeVerifier": str(row["code_verifier"]),
                "scopeText": str(row.get("scope_text") or ""),
                "redirectTo": str(row.get("redirect_to") or "/"),
            }


def upsert_user_from_userinfo(userinfo: dict[str, Any]) -> int:
    openid = str(userinfo.get("openid") or "").strip()
    unionid = str(userinfo.get("unionid") or "").strip()
    if not openid or not unionid:
        raise ValueError("userinfo missing openid/unionid")

    nickname = str(userinfo.get("nickname") or "").strip()
    email = str(userinfo.get("email") or "").strip()
    avatar_url = str(userinfo.get("avatar_url") or "").strip()

    with mysql_conn(commit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (openid, unionid, nickname, email, avatar_url, last_login_at)
                VALUES (%s, %s, %s, %s, %s, UTC_TIMESTAMP())
                ON DUPLICATE KEY UPDATE
                  id = LAST_INSERT_ID(id),
                  unionid = VALUES(unionid),
                  nickname = VALUES(nickname),
                  email = VALUES(email),
                  avatar_url = VALUES(avatar_url),
                  last_login_at = UTC_TIMESTAMP()
                """,
                (openid, unionid, nickname, email, avatar_url),
            )
            cursor.execute("SELECT LAST_INSERT_ID() AS id")
            row = cursor.fetchone() or {}
            return int(row.get("id") or 0)
