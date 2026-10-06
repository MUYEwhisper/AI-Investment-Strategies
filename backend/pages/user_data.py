from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from flask import Blueprint, jsonify, request

from utils.auth.context import get_current_user_id, require_auth
from utils.db.mysql import ensure_mysql_schema, mysql_conn

user_data_page = Blueprint("user_data", __name__)


def _to_datetime_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    return str(value or "")


@user_data_page.route("/watchlist", methods=["GET"])
@require_auth
def get_watchlist():
    ensure_mysql_schema()
    user_id = get_current_user_id()
    with mysql_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT payload_json
                FROM user_watchlist
                WHERE user_id = %s
                ORDER BY sort_order ASC, id ASC
                """,
                (user_id,),
            )
            rows = cursor.fetchall() or []

    items: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(str(row.get("payload_json") or "{}"))
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            items.append(payload)

    return jsonify({"success": True, "watchlist": items})


@user_data_page.route("/watchlist", methods=["PUT"])
@require_auth
def put_watchlist():
    ensure_mysql_schema()
    user_id = get_current_user_id()
    payload = request.get_json(silent=True) or {}
    items = payload.get("watchlist") if isinstance(payload, dict) else []
    if not isinstance(items, list):
        return jsonify({"success": False, "error": "watchlist 必须是数组"}), 400

    with mysql_conn(commit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM user_watchlist WHERE user_id = %s", (user_id,))
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                code = str(item.get("code") or "").strip()
                if not code:
                    continue
                cursor.execute(
                    """
                    INSERT INTO user_watchlist (user_id, stock_code, sort_order, payload_json)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (user_id, code[:32], idx, json.dumps(item, ensure_ascii=False)),
                )

    return jsonify({"success": True})


@user_data_page.route("/chats", methods=["GET"])
@require_auth
def get_chats():
    ensure_mysql_schema()
    user_id = get_current_user_id()

    with mysql_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, chat_uid, agent_id, title, created_at
                FROM user_chat_sessions
                WHERE user_id = %s
                ORDER BY sort_order ASC, id ASC
                """,
                (user_id,),
            )
            session_rows = cursor.fetchall() or []

            session_ids = [int(row["id"]) for row in session_rows]
            message_rows: list[dict[str, Any]] = []
            if session_ids:
                placeholders = ",".join(["%s"] * len(session_ids))
                cursor.execute(
                    f"""
                    SELECT session_id, msg_order, role, content
                    FROM user_chat_messages
                    WHERE session_id IN ({placeholders})
                    ORDER BY session_id ASC, msg_order ASC, id ASC
                    """,
                    tuple(session_ids),
                )
                message_rows = cursor.fetchall() or []

    grouped: dict[int, list[dict[str, str]]] = {sid: [] for sid in session_ids}
    for row in message_rows:
        sid = int(row["session_id"])
        grouped.setdefault(sid, []).append(
            {
                "role": str(row.get("role") or "ai"),
                "content": str(row.get("content") or ""),
            }
        )

    chats = [
        {
            "id": str(row["chat_uid"]),
            "agentId": str(row.get("agent_id") or "assistant"),
            "title": str(row.get("title") or "新对话"),
            "createdAt": _to_datetime_text(row.get("created_at")),
            "messages": grouped.get(int(row["id"]), []),
        }
        for row in session_rows
    ]

    return jsonify({"success": True, "chats": chats})


@user_data_page.route("/chats", methods=["PUT"])
@require_auth
def put_chats():
    ensure_mysql_schema()
    user_id = get_current_user_id()

    payload = request.get_json(silent=True) or {}
    chats = payload.get("chats") if isinstance(payload, dict) else []
    if not isinstance(chats, list):
        return jsonify({"success": False, "error": "chats 必须是数组"}), 400

    with mysql_conn(commit=True) as conn:
        with conn.cursor() as cursor:
            keep_ids: list[int] = []

            for idx, chat in enumerate(chats):
                if not isinstance(chat, dict):
                    continue
                chat_uid = str(chat.get("id") or "").strip()
                if not chat_uid:
                    continue

                agent_id = str(chat.get("agentId") or "assistant").strip() or "assistant"
                title = str(chat.get("title") or "新对话")
                created_at_raw = str(chat.get("createdAt") or "").strip()
                created_at_sql = None
                if created_at_raw:
                    try:
                        created_at_sql = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        created_at_sql = None

                if created_at_sql:
                    cursor.execute(
                        """
                        INSERT INTO user_chat_sessions (user_id, chat_uid, agent_id, title, sort_order, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                          id = LAST_INSERT_ID(id),
                          agent_id = VALUES(agent_id),
                          title = VALUES(title),
                          sort_order = VALUES(sort_order)
                        """,
                        (user_id, chat_uid[:64], agent_id[:64], title[:255], idx, created_at_sql),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO user_chat_sessions (user_id, chat_uid, agent_id, title, sort_order, created_at)
                        VALUES (%s, %s, %s, %s, %s, UTC_TIMESTAMP())
                        ON DUPLICATE KEY UPDATE
                          id = LAST_INSERT_ID(id),
                          agent_id = VALUES(agent_id),
                          title = VALUES(title),
                          sort_order = VALUES(sort_order)
                        """,
                        (user_id, chat_uid[:64], agent_id[:64], title[:255], idx),
                    )

                session_id = int(cursor.lastrowid)
                keep_ids.append(session_id)

                cursor.execute("DELETE FROM user_chat_messages WHERE session_id = %s", (session_id,))
                messages = chat.get("messages") if isinstance(chat.get("messages"), list) else []
                for msg_idx, msg in enumerate(messages):
                    if not isinstance(msg, dict):
                        continue
                    role = str(msg.get("role") or "ai").strip() or "ai"
                    content = str(msg.get("content") or "")
                    cursor.execute(
                        """
                        INSERT INTO user_chat_messages (session_id, msg_order, role, content)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (session_id, msg_idx, role[:16], content),
                    )

            if keep_ids:
                placeholders = ",".join(["%s"] * len(keep_ids))
                cursor.execute(
                    f"DELETE FROM user_chat_sessions WHERE user_id = %s AND id NOT IN ({placeholders})",
                    tuple([user_id, *keep_ids]),
                )
            else:
                cursor.execute("DELETE FROM user_chat_sessions WHERE user_id = %s", (user_id,))

    return jsonify({"success": True})
