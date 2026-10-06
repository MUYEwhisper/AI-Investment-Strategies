from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Iterator

import pymysql
from pymysql.connections import Connection
from pymysql.cursors import DictCursor

_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


def _as_int(value: str | int | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def mysql_config() -> dict[str, object]:
    return {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": _as_int(os.getenv("MYSQL_PORT"), 3306),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "stock_analyzer"),
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "autocommit": False,
    }


def get_mysql_connection() -> Connection:
    return pymysql.connect(**mysql_config())


def ensure_mysql_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return

    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return

        conn = get_mysql_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                      openid VARCHAR(128) NOT NULL,
                      unionid VARCHAR(128) NOT NULL,
                      nickname VARCHAR(120) NOT NULL DEFAULT '',
                      email VARCHAR(255) NOT NULL DEFAULT '',
                      avatar_url VARCHAR(500) NOT NULL DEFAULT '',
                      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP(),
                      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP() ON UPDATE CURRENT_TIMESTAMP(),
                      last_login_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP(),
                      PRIMARY KEY (id),
                      UNIQUE KEY uk_users_openid (openid),
                      KEY idx_users_unionid (unionid)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS auth_sessions (
                      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                      user_id BIGINT UNSIGNED NOT NULL,
                      token_hash CHAR(64) NOT NULL,
                      expires_at DATETIME NOT NULL,
                      revoked_at DATETIME NULL,
                      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP(),
                      last_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP(),
                      ip VARCHAR(64) NOT NULL DEFAULT '',
                      user_agent VARCHAR(255) NOT NULL DEFAULT '',
                      PRIMARY KEY (id),
                      UNIQUE KEY uk_auth_sessions_token_hash (token_hash),
                      KEY idx_auth_sessions_user_id (user_id),
                      KEY idx_auth_sessions_expires_at (expires_at),
                      CONSTRAINT fk_auth_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS oauth_pending (
                      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                      state VARCHAR(128) NOT NULL,
                      nonce VARCHAR(128) NOT NULL,
                      code_verifier VARCHAR(255) NOT NULL,
                      scope_text VARCHAR(255) NOT NULL DEFAULT '',
                      redirect_to VARCHAR(500) NOT NULL,
                      expires_at DATETIME NOT NULL,
                      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP(),
                      PRIMARY KEY (id),
                      UNIQUE KEY uk_oauth_pending_state (state),
                      KEY idx_oauth_pending_expires_at (expires_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_watchlist (
                      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                      user_id BIGINT UNSIGNED NOT NULL,
                      stock_code VARCHAR(32) NOT NULL,
                      sort_order INT NOT NULL DEFAULT 0,
                      payload_json LONGTEXT NOT NULL,
                      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP() ON UPDATE CURRENT_TIMESTAMP(),
                      PRIMARY KEY (id),
                      UNIQUE KEY uk_user_watchlist_stock (user_id, stock_code),
                      KEY idx_user_watchlist_sort (user_id, sort_order),
                      CONSTRAINT fk_user_watchlist_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_chat_sessions (
                      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                      user_id BIGINT UNSIGNED NOT NULL,
                      chat_uid VARCHAR(64) NOT NULL,
                      agent_id VARCHAR(64) NOT NULL,
                      title VARCHAR(255) NOT NULL,
                      sort_order INT NOT NULL DEFAULT 0,
                      created_at DATETIME NOT NULL,
                      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP() ON UPDATE CURRENT_TIMESTAMP(),
                      PRIMARY KEY (id),
                      UNIQUE KEY uk_user_chat_sessions_uid (user_id, chat_uid),
                      KEY idx_user_chat_sessions_sort (user_id, sort_order),
                      CONSTRAINT fk_user_chat_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_chat_messages (
                      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                      session_id BIGINT UNSIGNED NOT NULL,
                      msg_order INT NOT NULL,
                      role VARCHAR(16) NOT NULL,
                      content LONGTEXT NOT NULL,
                      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP(),
                      PRIMARY KEY (id),
                      KEY idx_user_chat_messages_order (session_id, msg_order),
                      CONSTRAINT fk_user_chat_messages_session FOREIGN KEY (session_id) REFERENCES user_chat_sessions(id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_shared_context (
                      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                      user_id BIGINT UNSIGNED NOT NULL,
                      summary_json LONGTEXT NOT NULL,
                      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP() ON UPDATE CURRENT_TIMESTAMP(),
                      PRIMARY KEY (id),
                      UNIQUE KEY uk_user_shared_context_user (user_id),
                      CONSTRAINT fk_user_shared_context_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS investor_profiles (
                      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                      user_id BIGINT UNSIGNED NOT NULL,
                      risk_score INT NOT NULL,
                      risk_level VARCHAR(64) NOT NULL,
                      max_single_stock_weight DOUBLE NOT NULL,
                      max_single_sector_weight DOUBLE NOT NULL,
                      summary_text TEXT NOT NULL,
                      recommendation TEXT NOT NULL,
                      analysis_basis_json LONGTEXT NOT NULL,
                      analysis_source VARCHAR(120) NOT NULL DEFAULT '',
                      answers_json LONGTEXT NOT NULL,
                      updated_at DATETIME NOT NULL,
                      PRIMARY KEY (id),
                      UNIQUE KEY uk_investor_profiles_user (user_id),
                      CONSTRAINT fk_investor_profiles_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sim_accounts (
                      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                      user_id BIGINT UNSIGNED NOT NULL,
                      initial_cash DOUBLE NOT NULL,
                      cash DOUBLE NOT NULL,
                      created_at DATETIME NOT NULL,
                      updated_at DATETIME NOT NULL,
                      PRIMARY KEY (id),
                      UNIQUE KEY uk_sim_accounts_user (user_id),
                      CONSTRAINT fk_sim_accounts_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sim_trades (
                      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                      user_id BIGINT UNSIGNED NOT NULL,
                      stock_code VARCHAR(32) NOT NULL,
                      stock_name VARCHAR(120) NOT NULL,
                      side VARCHAR(16) NOT NULL,
                      quantity INT NOT NULL,
                      price DOUBLE NOT NULL,
                      amount DOUBLE NOT NULL,
                      fees DOUBLE NOT NULL,
                      rationale TEXT NOT NULL,
                      plan_horizon VARCHAR(120) NOT NULL,
                      take_profit TEXT NOT NULL,
                      stop_loss TEXT NOT NULL,
                      created_at DATETIME NOT NULL,
                      PRIMARY KEY (id),
                      KEY idx_sim_trades_user_created (user_id, created_at),
                      CONSTRAINT fk_sim_trades_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sim_trade_reviews (
                      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                      user_id BIGINT UNSIGNED NOT NULL,
                      stock_code VARCHAR(32) NOT NULL,
                      stock_name VARCHAR(120) NOT NULL DEFAULT '',
                      summary_text TEXT NOT NULL,
                      thesis_status VARCHAR(120) NOT NULL DEFAULT '',
                      review_scope VARCHAR(32) NOT NULL DEFAULT '',
                      review_json LONGTEXT NOT NULL,
                      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP(),
                      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP() ON UPDATE CURRENT_TIMESTAMP(),
                      PRIMARY KEY (id),
                      KEY idx_sim_trade_reviews_user_created (user_id, created_at),
                      CONSTRAINT fk_sim_trade_reviews_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
            conn.commit()
            _SCHEMA_READY = True
        finally:
            conn.close()


@contextmanager
def mysql_conn(commit: bool = False) -> Iterator[Connection]:
    ensure_mysql_schema()
    conn = get_mysql_connection()
    try:
        yield conn
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
