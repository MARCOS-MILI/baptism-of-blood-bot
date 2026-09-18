"""Guarda o histórico de rolagens, os personagens, o XP e os resultados de definição
(Rank de magia, Raça, Classe social) num arquivo SQLite.

Onde o arquivo fica (nessa ordem):
  1. variável de ambiente DB_PATH, se existir;
  2. o Volume do Railway (RAILWAY_VOLUME_MOUNT_PATH), se tiver um anexado ao serviço;
  3. baptism_of_blood.db na pasta do bot. No Railway isso é APAGADO a cada redeploy.

Regra que vale pro banco inteiro: o nível de um personagem é sempre o que o XP dele
diz (rules.level_for_xp). Toda escrita de XP passa por add_xp ou set_xp, que mantêm
os dois juntos.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import rules

DB_FILENAME = "baptism_of_blood.db"
SCHEMA_VERSION = 4


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


class CharacterLimit(ValueError):
    """O jogador já usou todas as vagas de personagem."""

    def __init__(self, usados: int, permitidos: int):
        super().__init__(f"{usados} de {permitidos} vagas usadas")
        self.usados = usados
        self.permitidos = permitidos


# Campos de definição que a gente sabe manipular (lista fechada, nunca vem do usuário).
_DEFINITION_FIELDS = {
    "magic_rank": ("magic_rank", "magic_rank_roll", "magic_rank_set_at"),
    "race": ("race", "race_roll", "race_set_at"),
    "social_class": ("social_class", "social_class_roll", "social_class_set_at"),
    "clergy": ("clergy", "clergy_roll", "clergy_set_at"),
}

# O que 'clear_definition' apaga em cada opção. O clero depende do Estado, então saem juntos.
_CLEAR_GROUPS = {
    "magic_rank": ["magic_rank"],
    "race": ["race"],
    "social_class": ["social_class", "clergy"],
    "todas": ["magic_rank", "race", "social_class", "clergy"],
}

# Colunas que bancos criados antes da versão atual ainda não têm.
_CHARACTER_COLUMNS = {
    "level": "INTEGER NOT NULL DEFAULT 1",
    "social_class": "TEXT",
    "social_class_roll": "INTEGER",
    "social_class_set_at": "TEXT",
    "clergy": "TEXT",
    "clergy_roll": "INTEGER",
    "clergy_set_at": "TEXT",
    "xp": "INTEGER NOT NULL DEFAULT 0",
}

# Nome antigo da raça sorteada de 96 a 100, trocado por 'Dhampir' na versão 4.
_RACA_ANTIGA = "Meio humano, meio vampiro"
_RACA_NOVA = "Dhampir"


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
                level INTEGER NOT NULL DEFAULT 1,
                social_class TEXT,
                social_class_roll INTEGER,
                social_class_set_at TEXT,
                clergy TEXT,
                clergy_roll INTEGER,
                clergy_set_at TEXT,
                xp INTEGER NOT NULL DEFAULT 0,
                UNIQUE (user_id, name_key)
            )
        """)
        # Bancos de versões anteriores têm a tabela, mas sem as colunas novas.
        existentes = _column_names(conn, "characters")
        for coluna, tipo in _CHARACTER_COLUMNS.items():
            if coluna in existentes:
                continue
            conn.execute(f"ALTER TABLE characters ADD COLUMN {coluna} {tipo}")
            if coluna == "xp":
                # Quem já existia começa no início do nível em que está: 1000 x (n-1) x n / 2.
                conn.execute("UPDATE characters SET xp = ? * (level - 1) * level / 2", (rules.XP_STEP,))

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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS character_ranks (
                character_id INTEGER NOT NULL,
                skill TEXT NOT NULL,
                skill_rank INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (character_id, skill)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS xp_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id INTEGER NOT NULL,
                character_name TEXT NOT NULL,
                amount INTEGER NOT NULL,
                xp_before INTEGER NOT NULL,
                xp_after INTEGER NOT NULL,
                level_before INTEGER NOT NULL,
                level_after INTEGER NOT NULL,
                reason TEXT,
                master_id TEXT,
                master_name TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                user_id TEXT PRIMARY KEY,
                display_name TEXT,
                extra_slots INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS deleted_characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                deleted_by_id TEXT,
                deleted_by_name TEXT,
                deleted_at TEXT NOT NULL
            )
        """)

        versao = conn.execute("PRAGMA user_version").fetchone()[0]
        if versao < 2:
            _migrar_definicoes_antigas(conn)
        if versao < 4:
            conn.execute("UPDATE characters SET race = ? WHERE race = ?", (_RACA_NOVA, _RACA_ANTIGA))

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
# Jogadores (nome pra mostrar no rank e vagas extras de personagem)
# ---------------------------------------------------------------------------

def remember_player(user_id: str, display_name: str, path: str | None = None) -> None:
    """Guarda o nome atual do jogador, pro rank poder mostrar quem é dono de cada personagem."""
    with _connect(path) as conn:
        conn.execute(
            """
            INSERT INTO players (user_id, display_name, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                display_name = excluded.display_name, updated_at = excluded.updated_at
            """,
            (user_id, display_name, _now()),
        )


def get_extra_slots(user_id: str, path: str | None = None) -> int:
    with _connect(path) as conn:
        row = conn.execute("SELECT extra_slots FROM players WHERE user_id = ?", (user_id,)).fetchone()
    return row["extra_slots"] if row else 0


def set_extra_slots(user_id: str, extras: int, path: str | None = None) -> None:
    """Define quantas vagas EXTRAS o jogador tem (além do limite padrão)."""
    with _connect(path) as conn:
        conn.execute(
            """
            INSERT INTO players (user_id, extra_slots, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET extra_slots = excluded.extra_slots
            """,
            (user_id, extras, _now()),
        )


def get_player_names(path: str | None = None) -> dict[str, str]:
    with _connect(path) as conn:
        rows = conn.execute("SELECT user_id, display_name FROM players WHERE display_name IS NOT NULL").fetchall()
    return {r["user_id"]: r["display_name"] for r in rows}


# ---------------------------------------------------------------------------
# Personagens
# ---------------------------------------------------------------------------

def create_character(user_id: str, name: str, max_characters: int | None = None,
                     path: str | None = None) -> sqlite3.Row:
    """Cria o personagem e já deixa ele como o ativo do jogador.
    Com max_characters, recusa (CharacterLimit) quando o jogador já usou todas as vagas."""
    nome = normalize_name(name)
    try:
        with _connect(path) as conn:
            if max_characters is not None:
                usados = conn.execute(
                    "SELECT COUNT(*) FROM characters WHERE user_id = ?", (user_id,)
                ).fetchone()[0]
                if usados >= max_characters:
                    raise CharacterLimit(usados, max_characters)
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


def delete_character(character_id: int, deleted_by_id: str, deleted_by_name: str,
                     path: str | None = None) -> dict | None:
    """Exclui o personagem PRA SEMPRE: a ficha, os ranks e o extrato de XP somem e a vaga é liberada.
    As rolagens antigas continuam no histórico (sem ligação com a ficha). Fica guardada uma
    cópia da ficha no registro de excluídos, só pra os mestres poderem conferir.
    Devolve essa cópia, ou None se o personagem não existe mais."""
    with _connect(path) as conn:
        row = conn.execute("SELECT * FROM characters WHERE id = ?", (character_id,)).fetchone()
        if not row:
            return None
        snapshot = {chave: row[chave] for chave in row.keys()}
        snapshot["ranks"] = {
            r["skill"]: r["skill_rank"]
            for r in conn.execute("SELECT skill, skill_rank FROM character_ranks WHERE character_id = ?", (character_id,))
        }
        conn.execute(
            "INSERT INTO deleted_characters (character_id, user_id, name, snapshot_json, deleted_by_id,"
            " deleted_by_name, deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (character_id, row["user_id"], row["name"], json.dumps(snapshot, ensure_ascii=False),
             deleted_by_id, deleted_by_name, _now()),
        )
        conn.execute("DELETE FROM character_ranks WHERE character_id = ?", (character_id,))
        conn.execute("DELETE FROM xp_log WHERE character_id = ?", (character_id,))
        conn.execute("UPDATE rolls SET character_id = NULL WHERE character_id = ?", (character_id,))
        conn.execute("DELETE FROM characters WHERE id = ?", (character_id,))
        # O personagem ativo passa a ser o mais recente que sobrou (ou nenhum).
        conn.execute(
            "UPDATE user_state SET active_character_id ="
            " (SELECT id FROM characters WHERE user_id = ? ORDER BY id DESC LIMIT 1) WHERE user_id = ?",
            (row["user_id"], row["user_id"]),
        )
    return snapshot


def count_deleted(user_id: str, path: str | None = None) -> int:
    with _connect(path) as conn:
        return conn.execute("SELECT COUNT(*) FROM deleted_characters WHERE user_id = ?", (user_id,)).fetchone()[0]


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
# Definições (Rank de magia, Raça, Classe social)
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
    """quais: 'magic_rank', 'race', 'social_class' ou 'todas'. Deixa vazio pra o jogador poder rolar de novo."""
    if quais not in _CLEAR_GROUPS:
        raise ValueError(f"Definição desconhecida: {quais}")
    with _connect(path) as conn:
        for campo in _CLEAR_GROUPS[quais]:
            col_valor, col_roll, col_data = _DEFINITION_FIELDS[campo]
            conn.execute(
                f"UPDATE characters SET {col_valor} = NULL, {col_roll} = NULL, {col_data} = NULL WHERE id = ?",
                (character_id,),
            )


def set_social_status(character_id: int, estado: str, estado_roll: int | None,
                      clergy: str | None = None, clergy_roll: int | None = None,
                      path: str | None = None) -> None:
    """Grava o Estado e, se for 1º Estado, o Clero, na mesma operação.
    Sem clergy, o clero fica vazio. Rolls None significam que o mestre definiu na mão."""
    agora = _now()
    with _connect(path) as conn:
        conn.execute(
            "UPDATE characters SET social_class = ?, social_class_roll = ?, social_class_set_at = ?,"
            " clergy = ?, clergy_roll = ?, clergy_set_at = ? WHERE id = ?",
            (estado, estado_roll, agora,
             clergy, clergy_roll if clergy else None, agora if clergy else None,
             character_id),
        )


# ---------------------------------------------------------------------------
# XP e nível
# ---------------------------------------------------------------------------

def add_xp(character_id: int, amount: int, reason: str | None = None,
           master_id: str | None = None, master_name: str | None = None,
           path: str | None = None) -> dict | None:
    """Soma (ou tira, se negativo) XP e recalcula o nível, tudo numa operação só, e grava no
    extrato. O XP nunca fica abaixo de zero. 'applied' é o quanto mudou de verdade.
    Devolve None se o personagem não existe."""
    with _connect(path) as conn:
        row = conn.execute("SELECT id, name, xp, level FROM characters WHERE id = ?", (character_id,)).fetchone()
        if not row:
            return None
        antes_xp, antes_nivel = row["xp"], row["level"]
        depois_xp = max(0, antes_xp + amount)
        depois_nivel = rules.level_for_xp(depois_xp)
        conn.execute("UPDATE characters SET xp = ?, level = ? WHERE id = ?", (depois_xp, depois_nivel, character_id))
        if depois_xp != antes_xp:
            conn.execute(
                "INSERT INTO xp_log (character_id, character_name, amount, xp_before, xp_after, level_before,"
                " level_after, reason, master_id, master_name, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (character_id, row["name"], depois_xp - antes_xp, antes_xp, depois_xp, antes_nivel, depois_nivel,
                 reason, master_id, master_name, _now()),
            )
    return {
        "applied": depois_xp - antes_xp,
        "before_xp": antes_xp, "after_xp": depois_xp,
        "before_level": antes_nivel, "after_level": depois_nivel,
    }


def set_xp(character_id: int, xp: int, path: str | None = None) -> None:
    """Define o XP exato (sem passar pelo extrato) e o nível que ele dá."""
    xp = max(0, xp)
    with _connect(path) as conn:
        conn.execute("UPDATE characters SET xp = ?, level = ? WHERE id = ?", (xp, rules.level_for_xp(xp), character_id))


def set_level(character_id: int, level: int, path: str | None = None) -> None:
    """Põe o personagem no começo desse nível (XP mínimo dele). Pra mexer com registro, use add_xp."""
    set_xp(character_id, rules.xp_at_level_start(level), path)


def get_xp_log(character_id: int, limit: int = 10, path: str | None = None) -> list[sqlite3.Row]:
    with _connect(path) as conn:
        return conn.execute(
            "SELECT * FROM xp_log WHERE character_id = ? ORDER BY id DESC LIMIT ?", (character_id, limit)
        ).fetchall()


def rank_characters(path: str | None = None) -> list[sqlite3.Row]:
    """Personagens com XP, do maior pro menor (empate: o mais antigo fica na frente)."""
    with _connect(path) as conn:
        return conn.execute(
            """
            SELECT c.id, c.user_id, c.name, c.level, c.xp, p.display_name AS owner
            FROM characters c LEFT JOIN players p ON p.user_id = c.user_id
            WHERE c.xp > 0 ORDER BY c.xp DESC, c.id ASC
            """
        ).fetchall()


def rank_players(path: str | None = None) -> list[sqlite3.Row]:
    """Jogadores pelo XP somado de todos os personagens deles."""
    with _connect(path) as conn:
        return conn.execute(
            """
            SELECT c.user_id, SUM(c.xp) AS total_xp, COUNT(*) AS personagens, MAX(c.level) AS melhor_nivel,
                   p.display_name AS owner
            FROM characters c LEFT JOIN players p ON p.user_id = c.user_id
            GROUP BY c.user_id HAVING SUM(c.xp) > 0
            ORDER BY total_xp DESC, MIN(c.id) ASC
            """
        ).fetchall()


# ---------------------------------------------------------------------------
# Ranks das perícias especiais
# ---------------------------------------------------------------------------

def set_skill_rank(character_id: int, skill: str, skill_rank: int, path: str | None = None) -> None:
    with _connect(path) as conn:
        conn.execute(
            """
            INSERT INTO character_ranks (character_id, skill, skill_rank, updated_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(character_id, skill) DO UPDATE SET
                skill_rank = excluded.skill_rank, updated_at = excluded.updated_at
            """,
            (character_id, skill, skill_rank, _now()),
        )


def get_skill_ranks(character_id: int, path: str | None = None) -> dict[str, int]:
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT skill, skill_rank FROM character_ranks WHERE character_id = ?", (character_id,)
        ).fetchall()
    return {r["skill"]: r["skill_rank"] for r in rows}


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
