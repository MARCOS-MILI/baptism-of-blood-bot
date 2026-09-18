"""Guarda o histórico de rolagens, os personagens e os resultados de definição
(Rank de magia, Raça) num arquivo SQLite.

Onde o arquivo fica (nessa ordem):
  1. variável de ambiente DB_PATH, se existir;
  2. o Volume do Railway (RAILWAY_VOLUME_MOUNT_PATH), se tiver um anexado ao serviço;
  3. baptism_of_blood.db na pasta do bot. No Railway isso é APAGADO a cada redeploy.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_FILENAME = "baptism_of_blood.db"
SCHEMA_VERSION = 2


def _resolve_db_path() -> tuple[str, str]:
    """Devolve (caminho, origem). Origem: 'DB_PATH', 'volume' ou 'local'."""
    explicito = os.environ.get("DB_PATH")
    if explicito:
        return explicito, "DB_PATH"
    volume = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if volume:
        return os.path.join(volume, DB_FILENAME), "volume"
    return DB_FILENAME, "local"


DB_PATH, DB_SOURCE = _resolve_db_path()


def storage_is_persistent() -> bool:
    """True se o banco está num lugar que sobrevive a redeploy (DB_PATH ou Volume)."""
    return DB_SOURCE in ("DB_PATH", "volume")


class CharacterExists(ValueError):
    """Já existe um personagem com esse nome pra esse jogador."""


# Campos de definição que a gente sabe manipular (lista fechada, nunca vem do usuário).
_DEFINITION_FIELDS = {
    "magic_rank": ("magic_rank", "magic_rank_roll", "magic_rank_set_at"),
    "race": ("race", "race_roll", "race_set_at"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _connect(path: str | None = None):
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def normalize_name(name: str) -> str:
    """Tira espaços sobrando. O nome fica com a caixa que o jogador escreveu."""
    return " ".join(name.split())


def name_key(name: str) -> str:
    """Chave pra comparar nomes sem ligar pra maiúscula/minúscula (funciona com acento)."""
    return normalize_name(name).casefold()


# ---------------------------------------------------------------------------
# Criação e migração do banco
# ---------------------------------------------------------------------------

def init_db(path: str | None = None) -> None:
    path = path or DB_PATH
    pasta = os.path.dirname(path)
    if pasta:
        os.makedirs(pasta, exist_ok=True)

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
        # Bancos criados antes dos personagens não têm essas duas colunas.
        colunas = _column_names(conn, "rolls")
        if "character_id" not in colunas:
            conn.execute("ALTER TABLE rolls ADD COLUMN character_id INTEGER")
        if "character_name" not in colunas:
            conn.execute("ALTER TABLE rolls ADD COLUMN character_name TEXT")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                name_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                magic_rank TEXT,
                magic_rank_roll INTEGER,
                magic_rank_set_at TEXT,
                race TEXT,
                race_roll INTEGER,
                race_set_at TEXT,
                UNIQUE (user_id, name_key)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_state (
                user_id TEXT PRIMARY KEY,
                active_character_id INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS master_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                master_id TEXT NOT NULL,
                master_name TEXT NOT NULL,
                target_user_id TEXT NOT NULL,
                character_id INTEGER,
                character_name TEXT,
                action TEXT NOT NULL,
                detail TEXT,
                created_at TEXT NOT NULL
            )
        """)

        versao = conn.execute("PRAGMA user_version").fetchone()[0]
        if versao < 2:
            _migrar_definicoes_antigas(conn)

    # PRAGMA não aceita parâmetro, mas o valor aqui é uma constante nossa.
    with _connect(path) as conn:
        conn.execute(f"PRAGMA user_version = {int(SCHEMA_VERSION)}")


def _migrar_definicoes_antigas(conn: sqlite3.Connection) -> None:
    """Versão 1 guardava a definição por usuário (tabela character_definitions).
    Aqui cada linha antiga vira um personagem com o nome do jogador. A tabela antiga
    não é apagada, só deixa de ser usada."""
    if not _table_exists(conn, "character_definitions"):
        return
    for antigo in conn.execute("SELECT * FROM character_definitions").fetchall():
        nome = normalize_name(antigo["username"]) or "Personagem"
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO characters
                (user_id, name, name_key, created_at, magic_rank, magic_rank_roll, magic_rank_set_at,
                 race, race_set_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (antigo["user_id"], nome, name_key(nome), _now(), antigo["magic_rank"],
             antigo["magic_rank_roll"], antigo["magic_rank_set_at"], antigo["race"], antigo["race_set_at"]),
        )
        if cur.rowcount:
            conn.execute(
                "INSERT OR IGNORE INTO user_state (user_id, active_character_id) VALUES (?, ?)",
                (antigo["user_id"], cur.lastrowid),
            )


# ---------------------------------------------------------------------------
# Personagens
# ---------------------------------------------------------------------------

def create_character(user_id: str, name: str, path: str | None = None) -> sqlite3.Row:
    """Cria o personagem e já deixa ele como o ativo do jogador."""
    nome = normalize_name(name)
    try:
        with _connect(path) as conn:
            cur = conn.execute(
                "INSERT INTO characters (user_id, name, name_key, created_at) VALUES (?, ?, ?, ?)",
                (user_id, nome, name_key(nome), _now()),
            )
            novo_id = cur.lastrowid
            conn.execute(
                """
                INSERT INTO user_state (user_id, active_character_id) VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET active_character_id = excluded.active_character_id
                """,
                (user_id, novo_id),
            )
    except sqlite3.IntegrityError:
        raise CharacterExists(nome) from None
    return get_character_by_id(novo_id, path)


def get_character_by_id(character_id: int, path: str | None = None) -> sqlite3.Row | None:
    with _connect(path) as conn:
        return conn.execute("SELECT * FROM characters WHERE id = ?", (character_id,)).fetchone()


def list_characters(user_id: str, path: str | None = None) -> list[sqlite3.Row]:
    with _connect(path) as conn:
        return conn.execute("SELECT * FROM characters WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()


def find_character(user_id: str, name: str, path: str | None = None) -> sqlite3.Row | None:
    with _connect(path) as conn:
        return conn.execute(
            "SELECT * FROM characters WHERE user_id = ? AND name_key = ?", (user_id, name_key(name))
        ).fetchone()


def get_active_character(user_id: str, path: str | None = None) -> sqlite3.Row | None:
    with _connect(path) as conn:
        ativo = conn.execute(
            """
            SELECT c.* FROM user_state s
            JOIN characters c ON c.id = s.active_character_id AND c.user_id = s.user_id
            WHERE s.user_id = ?
            """,
            (user_id,),
        ).fetchone()
        if ativo:
            return ativo
        # Sem ativo marcado mas com personagens: usa o mais recente.
        return conn.execute(
            "SELECT * FROM characters WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)
        ).fetchone()


def set_active_character(user_id: str, character_id: int, path: str | None = None) -> None:
    with _connect(path) as conn:
        conn.execute(
            """
            INSERT INTO user_state (user_id, active_character_id) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET active_character_id = excluded.active_character_id
            """,
            (user_id, character_id),
        )


def resolve_character(user_id: str, name: str | None = None, path: str | None = None) -> sqlite3.Row | None:
    """Personagem pelo nome, ou o ativo do jogador se o nome não foi informado."""
    if name:
        return find_character(user_id, name, path)
    return get_active_character(user_id, path)


# ---------------------------------------------------------------------------
# Rolagens
# ---------------------------------------------------------------------------

def log_roll(user_id: str, username: str, guild_id: str | None, notation: str,
             rolls: list[int], total: int, purpose: str | None = None,
             character_id: int | None = None, character_name: str | None = None,
             path: str | None = None) -> None:
    with _connect(path) as conn:
        conn.execute(
            "INSERT INTO rolls (user_id, username, guild_id, notation, rolls_json, total, purpose,"
            " created_at, character_id, character_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, username, guild_id, notation, json.dumps(rolls), total, purpose,
             _now(), character_id, character_name),
        )


def get_history(user_id: str, limit: int = 10, character_id: int | None = None,
                path: str | None = None) -> list[sqlite3.Row]:
    with _connect(path) as conn:
        if character_id is None:
            return conn.execute(
                "SELECT * FROM rolls WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)
            ).fetchall()
        return conn.execute(
            "SELECT * FROM rolls WHERE user_id = ? AND character_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, character_id, limit),
        ).fetchall()


# ---------------------------------------------------------------------------
# Definições (Rank de magia, Raça)
# ---------------------------------------------------------------------------

def _set_definition(character_id: int, campo: str, valor: str, d100_result: int | None,
                    path: str | None) -> None:
    col_valor, col_roll, col_data = _DEFINITION_FIELDS[campo]
    with _connect(path) as conn:
        conn.execute(
            f"UPDATE characters SET {col_valor} = ?, {col_roll} = ?, {col_data} = ? WHERE id = ?",
            (valor, d100_result, _now(), character_id),
        )


def set_magic_rank(character_id: int, rank: str, d100_result: int | None, path: str | None = None) -> None:
    """d100_result None significa que o mestre definiu na mão."""
    _set_definition(character_id, "magic_rank", rank, d100_result, path)


def set_race(character_id: int, race: str, d100_result: int | None, path: str | None = None) -> None:
    """d100_result None significa que o mestre definiu na mão."""
    _set_definition(character_id, "race", race, d100_result, path)


def clear_definition(character_id: int, quais: str, path: str | None = None) -> None:
    """quais: 'magic_rank', 'race' ou 'ambos'. Deixa vazio pra o jogador poder rolar de novo."""
    campos = list(_DEFINITION_FIELDS) if quais == "ambos" else [quais]
    if any(c not in _DEFINITION_FIELDS for c in campos):
        raise ValueError(f"Definição desconhecida: {quais}")
    with _connect(path) as conn:
        for campo in campos:
            col_valor, col_roll, col_data = _DEFINITION_FIELDS[campo]
            conn.execute(
                f"UPDATE characters SET {col_valor} = NULL, {col_roll} = NULL, {col_data} = NULL WHERE id = ?",
                (character_id,),
            )


# ---------------------------------------------------------------------------
# Registro das ações de mestre
# ---------------------------------------------------------------------------

def log_master_action(master_id: str, master_name: str, target_user_id: str,
                      character_id: int | None, character_name: str | None,
                      action: str, detail: str | None = None, path: str | None = None) -> None:
    with _connect(path) as conn:
        conn.execute(
            "INSERT INTO master_actions (master_id, master_name, target_user_id, character_id,"
            " character_name, action, detail, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (master_id, master_name, target_user_id, character_id, character_name, action, detail, _now()),
        )
