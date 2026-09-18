"""Guarda o histórico de rolagens e os resultados de definição (tipo Rank de magia)
num arquivo SQLite local. Isso fica salvo entre reinicializações do bot."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = "baptism_of_blood.db"


def init_db(path: str = DB_PATH) -> None:
    with _connect(path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rolls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                guild_id TEXT,
                notation TEXT NOT NULL,
                rolls_json TEXT NOT NULL,
                total INTEGER NOT NULL,
                purpose TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS character_definitions (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                magic_rank TEXT,
                magic_rank_roll INTEGER,
                magic_rank_set_at TEXT,
                race TEXT,
                race_set_at TEXT
            )
        """)
        conn.commit()


@contextmanager
def _connect(path: str = DB_PATH):
    conn = sqlite3.connect(path)
    try:
        yield conn
    finally:
        conn.close()


def log_roll(user_id: str, username: str, guild_id: str | None, notation: str,
             rolls: list[int], total: int, purpose: str | None = None, path: str = DB_PATH) -> None:
    import json
    with _connect(path) as conn:
        conn.execute(
            "INSERT INTO rolls (user_id, username, guild_id, notation, rolls_json, total, purpose, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, username, guild_id, notation, json.dumps(rolls), total, purpose,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def get_history(user_id: str, limit: int = 10, path: str = DB_PATH) -> list[sqlite3.Row]:
    with _connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT * FROM rolls WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        return cur.fetchall()


def set_magic_rank(user_id: str, username: str, rank: str, d100_result: int, path: str = DB_PATH) -> None:
    with _connect(path) as conn:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO character_definitions (user_id, username, magic_rank, magic_rank_roll, magic_rank_set_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                magic_rank=excluded.magic_rank,
                magic_rank_roll=excluded.magic_rank_roll,
                magic_rank_set_at=excluded.magic_rank_set_at
            """,
            (user_id, username, rank, d100_result, now),
        )
        conn.commit()


def get_character(user_id: str, path: str = DB_PATH) -> sqlite3.Row | None:
    with _connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM character_definitions WHERE user_id = ?", (user_id,))
        return cur.fetchone()
