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

import dice
import rules

DB_FILENAME = "baptism_of_blood.db"
SCHEMA_VERSION = 12


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
    "class_name": "TEXT",
    "class_set_at": "TEXT",
    # A habilidade de classe escolhida (só nas classes que oferecem duas); vazio até o jogador escolher.
    "class_ability": "TEXT",
    "race_attempts": "INTEGER NOT NULL DEFAULT 0",
    "social_class_attempts": "INTEGER NOT NULL DEFAULT 0",
    # Resultado especial (66 ou 77) num sorteio de criação: guarda qual foi, e o valor do campo fica vazio
    # até um mestre decidir. Vazio quando não aconteceu.
    "race_special": "INTEGER",
    "social_class_special": "INTEGER",
    "magic_rank_special": "INTEGER",
    **{f"attr_{atributo}": "INTEGER NOT NULL DEFAULT 0" for atributo in rules.ATTRIBUTES},
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
                class_name TEXT,
                class_set_at TEXT,
                race_attempts INTEGER NOT NULL DEFAULT 0,
                social_class_attempts INTEGER NOT NULL DEFAULT 0,
                attr_forca INTEGER NOT NULL DEFAULT 0,
                attr_destreza INTEGER NOT NULL DEFAULT 0,
                attr_vitalidade INTEGER NOT NULL DEFAULT 0,
                attr_razao INTEGER NOT NULL DEFAULT 0,
                attr_vontade INTEGER NOT NULL DEFAULT 0,
                attr_alma INTEGER NOT NULL DEFAULT 0,
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
            elif coluna == "race_attempts":
                # Quem já tinha raça sorteada já gastou uma das chances.
                conn.execute("UPDATE characters SET race_attempts = 1 WHERE race IS NOT NULL")
            elif coluna == "social_class_attempts":
                conn.execute("UPDATE characters SET social_class_attempts = 1 WHERE social_class IS NOT NULL")

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
        # O 'atributo da época': os atributos que o personagem tinha em cada nível que ficou pra trás.
        # O nível atual não tem linha e usa sempre os atributos atuais.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS character_skill_picks (
                character_id INTEGER NOT NULL,
                skill TEXT NOT NULL,
                PRIMARY KEY (character_id, skill)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS character_skills (
                character_id INTEGER NOT NULL,
                skill TEXT NOT NULL,
                points INTEGER NOT NULL,
                PRIMARY KEY (character_id, skill)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_abilities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                effect_text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pendente',
                cost_resource TEXT,
                cost_amount INTEGER NOT NULL DEFAULT 0,
                roll_kind TEXT,
                roll_dice TEXT,
                roll_attribute TEXT,
                master_note TEXT,
                decided_by TEXT,
                decided_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_abilities_character ON custom_abilities (character_id)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS character_vitals (
                character_id INTEGER PRIMARY KEY,
                lost_vida INTEGER NOT NULL DEFAULT 0,
                lost_sanidade INTEGER NOT NULL DEFAULT 0,
                lost_mana INTEGER NOT NULL DEFAULT 0,
                lost_estamina INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dice_effects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                value INTEGER,
                uses_left INTEGER NOT NULL,
                quiet INTEGER NOT NULL DEFAULT 0,
                note TEXT,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dice_effects_character ON dice_effects (character_id)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scenes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                channel_id TEXT NOT NULL,
                name TEXT NOT NULL,
                round INTEGER NOT NULL DEFAULT 1,
                turn_participant_id INTEGER,
                active INTEGER NOT NULL DEFAULT 1,
                board_message_id TEXT,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                ended_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scenes_channel ON scenes (channel_id, active)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scene_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scene_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                character_id INTEGER,
                user_id TEXT,
                name TEXT NOT NULL,
                initiative INTEGER NOT NULL,
                detail TEXT,
                added_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_participants_scene ON scene_participants (scene_id)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scene_intentions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scene_id INTEGER NOT NULL,
                participant_id INTEGER NOT NULL,
                round INTEGER NOT NULL,
                text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pendente',
                master_note TEXT,
                decided_by TEXT,
                decided_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (participant_id, round)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS character_disciplines (
                character_id INTEGER NOT NULL,
                discipline TEXT NOT NULL,
                grade INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (character_id, discipline)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS level_attributes (
                character_id INTEGER NOT NULL,
                level INTEGER NOT NULL,
                attr_forca INTEGER NOT NULL,
                attr_destreza INTEGER NOT NULL,
                attr_vitalidade INTEGER NOT NULL,
                attr_razao INTEGER NOT NULL,
                attr_vontade INTEGER NOT NULL,
                attr_alma INTEGER NOT NULL,
                PRIMARY KEY (character_id, level)
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
        if versao < 6:
            _migrar_v6(conn)

    # PRAGMA não aceita parâmetro, mas o valor aqui é uma constante nossa.
    with _connect(path) as conn:
        conn.execute(f"PRAGMA user_version = {int(SCHEMA_VERSION)}")


def _migrar_v6(conn: sqlite3.Connection) -> None:
    """Só aditiva: quem já passou do nível 1 tem os níveis que ficaram pra trás congelados com os
    atributos de hoje (mesma regra de pular se estiverem zerados). Pode rodar de novo sem estragar nada."""
    for personagem in conn.execute("SELECT id, level FROM characters WHERE level > 1").fetchall():
        _congelar_niveis(conn, personagem["id"], personagem["level"])


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
        snapshot["disciplines"] = {
            r["discipline"]: r["grade"]
            for r in conn.execute("SELECT discipline, grade FROM character_disciplines WHERE character_id = ?", (character_id,))
        }
        conn.execute(
            "INSERT INTO deleted_characters (character_id, user_id, name, snapshot_json, deleted_by_id,"
            " deleted_by_name, deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (character_id, row["user_id"], row["name"], json.dumps(snapshot, ensure_ascii=False),
             deleted_by_id, deleted_by_name, _now()),
        )
        conn.execute("DELETE FROM character_disciplines WHERE character_id = ?", (character_id,))
        conn.execute("DELETE FROM dice_effects WHERE character_id = ?", (character_id,))
        conn.execute("DELETE FROM character_vitals WHERE character_id = ?", (character_id,))
        conn.execute("DELETE FROM character_skills WHERE character_id = ?", (character_id,))
        conn.execute("DELETE FROM custom_abilities WHERE character_id = ?", (character_id,))
        conn.execute("DELETE FROM character_skill_picks WHERE character_id = ?", (character_id,))
        conn.execute("DELETE FROM character_ranks WHERE character_id = ?", (character_id,))
        conn.execute("DELETE FROM level_attributes WHERE character_id = ?", (character_id,))
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


def count_rolls(user_id: str, path: str | None = None) -> int:
    """Quantas rolagens o jogador tem no histórico (de todos os personagens, e as sem personagem)."""
    with _connect(path) as conn:
        return conn.execute("SELECT COUNT(*) FROM rolls WHERE user_id = ?", (user_id,)).fetchone()[0]


def delete_rolls(user_id: str, path: str | None = None) -> int:
    """Apaga TODO o histórico de rolagens do jogador e devolve quantas eram. Não mexe na ficha, no XP
    nem nos personagens: as definições (raça, magia, Estado) ficam guardadas nos personagens."""
    with _connect(path) as conn:
        return conn.execute("DELETE FROM rolls WHERE user_id = ?", (user_id,)).rowcount


# ---------------------------------------------------------------------------
# Definições (Rank de magia, Raça, Classe social)
# ---------------------------------------------------------------------------

_ATTEMPT_COLUMN = {"race": "race_attempts", "social_class": "social_class_attempts"}
_SPECIAL_FIELDS = ("race", "social_class", "magic_rank")


def _attempts_sql(campo: str, d100_result: int | None) -> tuple[str, list]:
    """O pedaço do UPDATE que mexe nas chances. Sorteio de verdade (d100_result) gasta uma; valor definido
    por mestre (None) fecha as chances, pra o jogador não trocar o que o mestre decidiu."""
    coluna = _ATTEMPT_COLUMN.get(campo)
    if coluna is None:
        return "", []
    if d100_result is None:
        return f", {coluna} = ?", [rules.CREATION_ROLL_ATTEMPTS]
    return f", {coluna} = {coluna} + 1", []


def _set_definition(character_id: int, campo: str, valor: str, d100_result: int | None,
                    path: str | None) -> None:
    col_valor, col_roll, col_data = _DEFINITION_FIELDS[campo]
    extra_sql, extra = _attempts_sql(campo, d100_result)
    with _connect(path) as conn:
        conn.execute(
            f"UPDATE characters SET {col_valor} = ?, {col_roll} = ?, {col_data} = ?, {campo}_special = NULL"
            f"{extra_sql} WHERE id = ?",
            (valor, d100_result, _now(), *extra, character_id),
        )


def set_magic_rank(character_id: int, rank: str, d100_result: int | None, path: str | None = None) -> None:
    """d100_result None significa que o mestre definiu na mão."""
    _set_definition(character_id, "magic_rank", rank, d100_result, path)


def set_race(character_id: int, race: str, d100_result: int | None, path: str | None = None) -> None:
    """d100_result None significa que o mestre definiu na mão."""
    _set_definition(character_id, "race", race, d100_result, path)


def limpa_especial(campo: str) -> str:
    """O pedaço do UPDATE que zera o resultado especial (66/77) do campo. O clero não tem coluna própria."""
    return f", {campo}_special = NULL" if campo in _SPECIAL_FIELDS else ""


def set_special(character_id: int, campo: str, valor: int, path: str | None = None) -> None:
    """Grava um resultado especial (66 ou 77): o campo fica vazio (nem a raça, nem o Estado, nem o Rank
    valem) e só um mestre decide. Gasta uma chance, mas o jogador não rola de novo enquanto isso."""
    if campo not in _SPECIAL_FIELDS:
        raise ValueError(f"Campo sem resultado especial: {campo}")
    if valor not in rules.SPECIAL_ROLLS:
        raise ValueError(f"Resultado que não é especial: {valor}")
    col_valor, col_roll, col_data = _DEFINITION_FIELDS[campo]
    extra_sql, extra = _attempts_sql(campo, valor)
    limpa_clero = ", clergy = NULL, clergy_roll = NULL, clergy_set_at = NULL" if campo == "social_class" else ""
    with _connect(path) as conn:
        conn.execute(
            f"UPDATE characters SET {col_valor} = NULL, {col_roll} = NULL, {col_data} = NULL,"
            f" {campo}_special = ?{limpa_clero}{extra_sql} WHERE id = ?",
            (valor, *extra, character_id),
        )


def clear_definition(character_id: int, quais: str, path: str | None = None) -> None:
    """quais: 'magic_rank', 'race', 'social_class' ou 'todas'. Deixa vazio pra o jogador poder rolar de novo."""
    if quais not in _CLEAR_GROUPS:
        raise ValueError(f"Definição desconhecida: {quais}")
    with _connect(path) as conn:
        for campo in _CLEAR_GROUPS[quais]:
            col_valor, col_roll, col_data = _DEFINITION_FIELDS[campo]
            devolver = f", {_ATTEMPT_COLUMN[campo]} = 0" if campo in _ATTEMPT_COLUMN else ""
            conn.execute(
                f"UPDATE characters SET {col_valor} = NULL, {col_roll} = NULL, {col_data} = NULL{devolver}"
                f"{limpa_especial(campo)} WHERE id = ?",
                (character_id,),
            )


def set_social_status(character_id: int, estado: str, estado_roll: int | None,
                      clergy: str | None = None, clergy_roll: int | None = None,
                      path: str | None = None) -> None:
    """Grava o Estado e, se for 1º Estado, o Clero, na mesma operação.
    Sem clergy, o clero fica vazio. Rolls None significam que o mestre definiu na mão."""
    agora = _now()
    extra_sql, extra = _attempts_sql("social_class", estado_roll)
    with _connect(path) as conn:
        conn.execute(
            "UPDATE characters SET social_class = ?, social_class_roll = ?, social_class_set_at = ?,"
            f" social_class_special = NULL, clergy = ?, clergy_roll = ?, clergy_set_at = ?{extra_sql} WHERE id = ?",
            (estado, estado_roll, agora,
             clergy, clergy_roll if clergy else None, agora if clergy else None,
             *extra, character_id),
        )


# ---------------------------------------------------------------------------
# Disciplinas (só Vampiro e Dhampir)
# ---------------------------------------------------------------------------

def get_disciplines(character_id: int, path: str | None = None) -> dict[str, int]:
    """As Disciplinas que o personagem tem (grau maior que 0), na ordem do sistema."""
    with _connect(path) as conn:
        linhas = conn.execute(
            "SELECT discipline, grade FROM character_disciplines WHERE character_id = ? AND grade > 0", (character_id,)
        ).fetchall()
    graus = {l["discipline"]: l["grade"] for l in linhas}
    return {d: graus[d] for d in rules.DISCIPLINES if d in graus}


def set_discipline_grade(character_id: int, discipline: str, grade: int, path: str | None = None) -> None:
    """Grava o grau (0 a 5) de uma Disciplina. Grau 0 tira a Disciplina. Não confere pontos nem regras: quem
    chama é que confere (o jogador pelo painel, o mestre pelo /mestre disciplina)."""
    if discipline not in rules.DISCIPLINES:
        raise ValueError(f"Disciplina desconhecida: {discipline}")
    if not 0 <= grade <= rules.MAX_DISCIPLINE_GRADE:
        raise ValueError(f"Grau fora de 0 a {rules.MAX_DISCIPLINE_GRADE}: {grade}")
    with _connect(path) as conn:
        if grade == 0:
            conn.execute("DELETE FROM character_disciplines WHERE character_id = ? AND discipline = ?", (character_id, discipline))
            return
        conn.execute(
            """
            INSERT INTO character_disciplines (character_id, discipline, grade, updated_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(character_id, discipline) DO UPDATE SET grade = excluded.grade, updated_at = excluded.updated_at
            """,
            (character_id, discipline, grade, _now()),
        )


# ---------------------------------------------------------------------------
# Perícias comuns: os pontos de cada uma
# ---------------------------------------------------------------------------
def get_skills(character_id: int, path: str | None = None) -> dict[str, int]:
    """Os pontos de cada perícia que o personagem tem (as que estão em 0 não aparecem)."""
    with _connect(path) as conn:
        linhas = conn.execute("SELECT skill, points FROM character_skills WHERE character_id = ?", (character_id,)).fetchall()
    return {l["skill"]: l["points"] for l in linhas}


def set_skill_points(character_id: int, skill: str, points: int, path: str | None = None) -> None:
    if skill not in rules.SKILLS:
        raise ValueError(f"Perícia desconhecida: {skill}")
    if not isinstance(points, int) or not 0 <= points <= 20:
        raise ValueError("Os pontos precisam ser de 0 a 20.")
    with _connect(path) as conn:
        if points == 0:
            conn.execute("DELETE FROM character_skills WHERE character_id = ? AND skill = ?", (character_id, skill))
        else:
            conn.execute(
                "INSERT INTO character_skills (character_id, skill, points) VALUES (?, ?, ?)"
                " ON CONFLICT (character_id, skill) DO UPDATE SET points = excluded.points",
                (character_id, skill, points),
            )


# ---------------------------------------------------------------------------
# Vantagem de classe nas perícias: o que o jogador escolheu (Luta ou Pontaria; as duas do Mundano)
# ---------------------------------------------------------------------------
def get_skill_picks(character_id: int, path: str | None = None) -> list[str]:
    with _connect(path) as conn:
        linhas = conn.execute("SELECT skill FROM character_skill_picks WHERE character_id = ? ORDER BY rowid", (character_id,)).fetchall()
    return [l["skill"] for l in linhas]


def set_skill_picks(character_id: int, skills: list[str], path: str | None = None) -> None:
    """Troca TODAS as escolhas do personagem pelas dadas."""
    if any(p not in rules.SKILLS for p in skills):
        raise ValueError("Perícia desconhecida na escolha.")
    with _connect(path) as conn:
        conn.execute("DELETE FROM character_skill_picks WHERE character_id = ?", (character_id,))
        conn.executemany("INSERT OR IGNORE INTO character_skill_picks (character_id, skill) VALUES (?, ?)", [(character_id, p) for p in skills])


# ---------------------------------------------------------------------------
# Habilidades criadas pelos jogadores
# ---------------------------------------------------------------------------
def create_ability(character_id: int, name: str, description: str, effect_text: str, path: str | None = None) -> int:
    agora = _now()
    with _connect(path) as conn:
        cur = conn.execute(
            "INSERT INTO custom_abilities (character_id, name, description, effect_text, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (character_id, name, description, effect_text, agora, agora),
        )
        return cur.lastrowid


def get_ability(ability_id: int, path: str | None = None) -> sqlite3.Row | None:
    with _connect(path) as conn:
        return conn.execute("SELECT * FROM custom_abilities WHERE id = ?", (ability_id,)).fetchone()


def list_abilities(character_id: int, path: str | None = None) -> list[sqlite3.Row]:
    with _connect(path) as conn:
        return conn.execute("SELECT * FROM custom_abilities WHERE character_id = ? ORDER BY id", (character_id,)).fetchall()


def count_active_abilities(character_id: int, path: str | None = None) -> int:
    """As habilidades que contam no limite: todas menos as recusadas."""
    with _connect(path) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM custom_abilities WHERE character_id = ? AND status != 'recusada'", (character_id,)
        ).fetchone()[0]


def list_ability_queue(limit: int = 25, path: str | None = None) -> list[sqlite3.Row]:
    """A fila dos mestres: o que espera resposta primeiro (pendentes e pedidos de ajuste), depois as aprovadas, da mais
    nova pra mais velha. Cada linha traz o nome do personagem e o dono."""
    with _connect(path) as conn:
        return conn.execute(
            "SELECT a.*, c.name AS character_name, c.user_id AS user_id FROM custom_abilities a"
            " JOIN characters c ON c.id = a.character_id WHERE a.status != 'recusada'"
            " ORDER BY CASE a.status WHEN 'pendente' THEN 0 WHEN 'ajuste' THEN 1 ELSE 2 END, a.id DESC LIMIT ?",
            (limit,),
        ).fetchall()


def update_ability_text(ability_id: int, name: str, description: str, effect_text: str, back_to_pending: bool,
                        path: str | None = None) -> None:
    """Muda o texto. Quando é o jogador mexendo, volta pra fila (pendente) e some a nota do mestre."""
    with _connect(path) as conn:
        if back_to_pending:
            conn.execute(
                "UPDATE custom_abilities SET name = ?, description = ?, effect_text = ?, status = 'pendente',"
                " master_note = NULL, updated_at = ? WHERE id = ?",
                (name, description, effect_text, _now(), ability_id),
            )
        else:
            conn.execute(
                "UPDATE custom_abilities SET name = ?, description = ?, effect_text = ?, updated_at = ? WHERE id = ?",
                (name, description, effect_text, _now(), ability_id),
            )


def save_ability_decision(ability_id: int, status: str, cost_resource: str | None, cost_amount: int,
                          roll_kind: str | None, roll_dice: str | None, roll_attribute: str | None,
                          master_note: str | None, decided_by: str, path: str | None = None) -> None:
    """O mestre decide: o status e o que a habilidade custa e rola."""
    if status not in rules.ABILITY_STATUS:
        raise ValueError(f"Status desconhecido: {status}")
    if cost_resource is not None and cost_resource not in rules.VITAL_KEYS:
        raise ValueError(f"Recurso desconhecido: {cost_resource}")
    if roll_kind is not None and roll_kind not in rules.ABILITY_ROLL_KINDS:
        raise ValueError(f"Tipo de rolagem desconhecido: {roll_kind}")
    if roll_attribute is not None and roll_attribute not in rules.ATTRIBUTES:
        raise ValueError(f"Atributo desconhecido: {roll_attribute}")
    if not isinstance(cost_amount, int) or not 0 <= cost_amount <= 999:
        raise ValueError("O custo precisa ser de 0 a 999.")
    agora = _now()
    with _connect(path) as conn:
        conn.execute(
            "UPDATE custom_abilities SET status = ?, cost_resource = ?, cost_amount = ?, roll_kind = ?, roll_dice = ?,"
            " roll_attribute = ?, master_note = ?, decided_by = ?, decided_at = ?, updated_at = ? WHERE id = ?",
            (status, cost_resource if cost_amount else None, cost_amount if cost_resource else 0, roll_kind, roll_dice,
             roll_attribute, master_note, decided_by, agora, agora, ability_id),
        )


def delete_ability(ability_id: int, path: str | None = None) -> None:
    with _connect(path) as conn:
        conn.execute("DELETE FROM custom_abilities WHERE id = ?", (ability_id,))


# ---------------------------------------------------------------------------
# Vitais: quanto o personagem PERDEU de Vida, Sanidade, Mana e Estamina (o atual é o máximo menos isso)
# ---------------------------------------------------------------------------
def get_vitals_lost(character_id: int, path: str | None = None) -> dict[str, int]:
    """O que o personagem perdeu de cada vital. Quem nunca mexeu nas barras não perdeu nada (tudo 0)."""
    with _connect(path) as conn:
        linha = conn.execute("SELECT * FROM character_vitals WHERE character_id = ?", (character_id,)).fetchone()
    return {k: (linha[f"lost_{k}"] if linha else 0) for k in rules.VITAL_KEYS}


def set_vital_lost(character_id: int, key: str, lost: int, path: str | None = None) -> None:
    if key not in rules.VITAL_KEYS:
        raise ValueError(f"Vital desconhecido: {key}")
    if not isinstance(lost, int) or lost < 0:
        raise ValueError("O que se perdeu precisa ser um número de 0 pra cima.")
    with _connect(path) as conn:
        conn.execute("INSERT OR IGNORE INTO character_vitals (character_id) VALUES (?)", (character_id,))
        conn.execute(f"UPDATE character_vitals SET lost_{key} = ? WHERE character_id = ?", (lost, character_id))


def reset_vitals(character_id: int, path: str | None = None) -> None:
    """Descansou: tudo de volta no máximo."""
    with _connect(path) as conn:
        conn.execute("DELETE FROM character_vitals WHERE character_id = ?", (character_id,))


# ---------------------------------------------------------------------------
# Sorte do mestre: efeitos que mexem no d20 de um personagem (a regra está no dice.py)
# ---------------------------------------------------------------------------
MAX_DICE_EFFECT_USES = 20


def add_dice_effect(character_id: int, kind: str, value: int | None, uses: int, quiet: bool,
                    note: str | None, created_by: str, path: str | None = None) -> int:
    """Põe um efeito de sorte no personagem. 'uses' é quantas rolagens ele ainda pode afetar."""
    if kind not in dice.EFEITOS:
        raise ValueError(f"Efeito desconhecido: {kind}")
    if kind in dice.EFEITOS_COM_VALOR and not (isinstance(value, int) and 1 <= value <= 20):
        raise ValueError("O valor do efeito precisa ser de 1 a 20.")
    if kind not in dice.EFEITOS_COM_VALOR:
        value = None
    if not 1 <= uses <= MAX_DICE_EFFECT_USES:
        raise ValueError(f"Os usos precisam ser de 1 a {MAX_DICE_EFFECT_USES}.")
    with _connect(path) as conn:
        cur = conn.execute(
            "INSERT INTO dice_effects (character_id, kind, value, uses_left, quiet, note, created_by, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (character_id, kind, value, uses, int(quiet), note, created_by, _now()),
        )
        return cur.lastrowid


def get_dice_effects(character_id: int, path: str | None = None) -> list[sqlite3.Row]:
    """Os efeitos que ainda têm uso, do mais antigo pro mais novo."""
    with _connect(path) as conn:
        return conn.execute(
            "SELECT * FROM dice_effects WHERE character_id = ? AND uses_left > 0 ORDER BY id", (character_id,)
        ).fetchall()


def use_dice_effects(ids: list[int], path: str | None = None) -> None:
    """Gasta um uso de cada id da lista (um id repetido gasta mais de um). O efeito que fica sem uso some."""
    with _connect(path) as conn:
        for effect_id in ids:
            conn.execute("UPDATE dice_effects SET uses_left = uses_left - 1 WHERE id = ? AND uses_left > 0", (effect_id,))
        conn.execute("DELETE FROM dice_effects WHERE uses_left <= 0")


def clear_dice_effects(character_id: int, path: str | None = None) -> int:
    """Tira todos os efeitos do personagem. Devolve quantos tinha."""
    with _connect(path) as conn:
        return conn.execute("DELETE FROM dice_effects WHERE character_id = ?", (character_id,)).rowcount


# ---------------------------------------------------------------------------
# Cenas: iniciativa e intenções (o Escudo do Mestre)
# ---------------------------------------------------------------------------
MAX_SCENE_PARTICIPANTS = 25          # o menu do Discord mostra no máximo 25 opções
INTENTION_STATUSES = ("pendente", "permitida", "negada")


def create_scene(guild_id: str | None, channel_id: str, name: str, created_by: str,
                 path: str | None = None) -> sqlite3.Row | None:
    """Abre uma cena no canal. Devolve None se já existe uma cena aberta nesse canal."""
    with _connect(path) as conn:
        if conn.execute("SELECT 1 FROM scenes WHERE channel_id = ? AND active = 1", (channel_id,)).fetchone():
            return None
        cur = conn.execute(
            "INSERT INTO scenes (guild_id, channel_id, name, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
            (guild_id, channel_id, name, created_by, _now()),
        )
        return conn.execute("SELECT * FROM scenes WHERE id = ?", (cur.lastrowid,)).fetchone()


def get_scene(scene_id: int, path: str | None = None) -> sqlite3.Row | None:
    with _connect(path) as conn:
        return conn.execute("SELECT * FROM scenes WHERE id = ?", (scene_id,)).fetchone()


def get_active_scene(channel_id: str, path: str | None = None) -> sqlite3.Row | None:
    with _connect(path) as conn:
        return conn.execute("SELECT * FROM scenes WHERE channel_id = ? AND active = 1", (channel_id,)).fetchone()


def end_scene(scene_id: int, path: str | None = None) -> None:
    with _connect(path) as conn:
        conn.execute("UPDATE scenes SET active = 0, ended_at = ?, turn_participant_id = NULL WHERE id = ?", (_now(), scene_id))


def set_scene_board(scene_id: int, message_id: str | None, path: str | None = None) -> None:
    with _connect(path) as conn:
        conn.execute("UPDATE scenes SET board_message_id = ? WHERE id = ?", (message_id, scene_id))


def set_scene_turn(scene_id: int, participant_id: int | None, round_: int, path: str | None = None) -> None:
    with _connect(path) as conn:
        conn.execute("UPDATE scenes SET turn_participant_id = ?, round = ? WHERE id = ?", (participant_id, round_, scene_id))


def add_participant(scene_id: int, kind: str, name: str, initiative: int, detail: str | None = None,
                    character_id: int | None = None, user_id: str | None = None,
                    path: str | None = None) -> int | None:
    """Põe alguém na cena. Devolve o id, ou None se a cena já está cheia. kind: 'pc' ou 'npc'."""
    if kind not in ("pc", "npc"):
        raise ValueError(f"Tipo de participante desconhecido: {kind}")
    with _connect(path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM scene_participants WHERE scene_id = ?", (scene_id,)).fetchone()[0]
        if total >= MAX_SCENE_PARTICIPANTS:
            return None
        cur = conn.execute(
            "INSERT INTO scene_participants (scene_id, kind, character_id, user_id, name, initiative, detail, added_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (scene_id, kind, character_id, user_id, name, initiative, detail, _now()),
        )
        return cur.lastrowid


def get_participants(scene_id: int, path: str | None = None) -> list[sqlite3.Row]:
    """Na ordem da iniciativa: do maior pro menor; empate, quem entrou primeiro."""
    with _connect(path) as conn:
        return conn.execute(
            "SELECT * FROM scene_participants WHERE scene_id = ? ORDER BY initiative DESC, id ASC", (scene_id,)
        ).fetchall()


def get_participant(participant_id: int, path: str | None = None) -> sqlite3.Row | None:
    with _connect(path) as conn:
        return conn.execute("SELECT * FROM scene_participants WHERE id = ?", (participant_id,)).fetchone()


def find_participant_by_character(scene_id: int, character_id: int, path: str | None = None) -> sqlite3.Row | None:
    with _connect(path) as conn:
        return conn.execute(
            "SELECT * FROM scene_participants WHERE scene_id = ? AND character_id = ?", (scene_id, character_id)
        ).fetchone()


def set_participant_initiative(participant_id: int, initiative: int, detail: str | None,
                               path: str | None = None) -> None:
    with _connect(path) as conn:
        conn.execute("UPDATE scene_participants SET initiative = ?, detail = ? WHERE id = ?", (initiative, detail, participant_id))


def remove_participant(participant_id: int, path: str | None = None) -> None:
    """Tira da cena, junto com as intenções dele. Quem chama cuida de mexer no turno, se era a vez dele."""
    with _connect(path) as conn:
        conn.execute("DELETE FROM scene_intentions WHERE participant_id = ?", (participant_id,))
        conn.execute("DELETE FROM scene_participants WHERE id = ?", (participant_id,))


def save_intention(scene_id: int, participant_id: int, round_: int, text: str,
                   path: str | None = None) -> str:
    """Grava a intenção da rodada. Devolve 'nova', 'trocada' (havia uma pendente ou negada, que foi
    substituída) ou 'permitida' (já estava permitida: nada muda)."""
    with _connect(path) as conn:
        atual = conn.execute(
            "SELECT status FROM scene_intentions WHERE participant_id = ? AND round = ?", (participant_id, round_)
        ).fetchone()
        if atual and atual["status"] == "permitida":
            return "permitida"
        agora = _now()
        if atual is None:
            conn.execute(
                "INSERT INTO scene_intentions (scene_id, participant_id, round, text, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (scene_id, participant_id, round_, text, agora, agora),
            )
            return "nova"
        conn.execute(
            "UPDATE scene_intentions SET text = ?, status = 'pendente', master_note = NULL, decided_by = NULL,"
            " decided_at = NULL, updated_at = ? WHERE participant_id = ? AND round = ?",
            (text, agora, participant_id, round_),
        )
        return "trocada"


def get_intention(participant_id: int, round_: int, path: str | None = None) -> sqlite3.Row | None:
    with _connect(path) as conn:
        return conn.execute(
            "SELECT * FROM scene_intentions WHERE participant_id = ? AND round = ?", (participant_id, round_)
        ).fetchone()


def get_intention_by_id(intention_id: int, path: str | None = None) -> sqlite3.Row | None:
    with _connect(path) as conn:
        return conn.execute("SELECT * FROM scene_intentions WHERE id = ?", (intention_id,)).fetchone()


def list_intentions(scene_id: int, round_: int, path: str | None = None) -> dict[int, sqlite3.Row]:
    """As intenções da rodada, por id de participante."""
    with _connect(path) as conn:
        linhas = conn.execute(
            "SELECT * FROM scene_intentions WHERE scene_id = ? AND round = ?", (scene_id, round_)
        ).fetchall()
    return {l["participant_id"]: l for l in linhas}


def decide_intention(intention_id: int, status: str, note: str | None, decided_by: str,
                     path: str | None = None) -> bool:
    """Permite ou nega. Só decide intenção pendente; devolve False se ela já foi decidida (ou sumiu)."""
    if status not in ("permitida", "negada"):
        raise ValueError(f"Decisão desconhecida: {status}")
    with _connect(path) as conn:
        cur = conn.execute(
            "UPDATE scene_intentions SET status = ?, master_note = ?, decided_by = ?, decided_at = ?, updated_at = ?"
            " WHERE id = ? AND status = 'pendente'",
            (status, note, decided_by, _now(), _now(), intention_id),
        )
        return cur.rowcount == 1


# ---------------------------------------------------------------------------
# Atributo da época: cada nível guarda os atributos que o personagem tinha nele
# ---------------------------------------------------------------------------
_ATTR_COLUMNS = [f"attr_{a}" for a in rules.ATTRIBUTES]


def _congelar_niveis(conn: sqlite3.Connection, character_id: int, ate_nivel: int) -> None:
    """Grava os atributos ATUAIS nos níveis de 1 até ate_nivel - 1 que ainda não têm linha.
    Se Força, Vitalidade, Vontade e Alma estão todos zerados (o jogador ainda não distribuiu os
    pontos), não grava nada: esses níveis continuam usando os atributos atuais até congelarem de verdade."""
    atuais = conn.execute(
        f"SELECT {', '.join(_ATTR_COLUMNS)} FROM characters WHERE id = ?", (character_id,)
    ).fetchone()
    if atuais is None or not any(atuais[f"attr_{a}"] for a in rules.RESOURCE_ATTRIBUTES):
        return
    ja_tem = {r["level"] for r in conn.execute(
        "SELECT level FROM level_attributes WHERE character_id = ?", (character_id,))}
    valores = [atuais[c] for c in _ATTR_COLUMNS]
    for nivel in range(1, ate_nivel):
        if nivel not in ja_tem:
            conn.execute(
                f"INSERT INTO level_attributes (character_id, level, {', '.join(_ATTR_COLUMNS)})"
                f" VALUES (?, ?, {', '.join('?' * len(_ATTR_COLUMNS))})",
                [character_id, nivel, *valores],
            )


def _nivel_mudou(conn: sqlite3.Connection, character_id: int, antes: int, depois: int) -> None:
    """Subiu: os níveis que ficaram pra trás congelam com os atributos de agora (se o mestre sobe vários
    de uma vez, os do meio congelam com os atributos do momento da subida). Baixou: somem as linhas do
    nível novo em diante, que voltam a usar os atributos atuais."""
    if depois > antes:
        _congelar_niveis(conn, character_id, depois)
    elif depois < antes:
        conn.execute("DELETE FROM level_attributes WHERE character_id = ? AND level >= ?", (character_id, depois))


def get_level_attributes(character_id: int, path: str | None = None) -> dict[int, dict[str, int]]:
    """Só os níveis que já têm linha (os que o personagem deixou pra trás)."""
    with _connect(path) as conn:
        linhas = conn.execute(
            "SELECT * FROM level_attributes WHERE character_id = ? ORDER BY level", (character_id,)
        ).fetchall()
    return {l["level"]: {a: l[f"attr_{a}"] for a in rules.ATTRIBUTES} for l in linhas}


def attributes_per_level(personagem, path: str | None = None) -> list[dict[str, int]]:
    """Os atributos de cada nível, do 1 até o atual. O nível atual sempre usa os atributos atuais;
    os que ficaram pra trás usam a linha congelada, ou os atuais se ainda não têm linha."""
    atuais = attributes_of(personagem)
    congelados = get_level_attributes(personagem["id"], path)
    nivel = personagem["level"]
    return [congelados.get(n, atuais) if n < nivel else atuais for n in range(1, nivel + 1)]


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
        _nivel_mudou(conn, character_id, antes_nivel, depois_nivel)
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
        atual = conn.execute("SELECT level FROM characters WHERE id = ?", (character_id,)).fetchone()
        if not atual:
            return
        novo_nivel = rules.level_for_xp(xp)
        conn.execute("UPDATE characters SET xp = ?, level = ? WHERE id = ?", (xp, novo_nivel, character_id))
        _nivel_mudou(conn, character_id, atual["level"], novo_nivel)


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
# Classe e atributos (a ficha automática)
# ---------------------------------------------------------------------------

def set_class(character_id: int, class_name: str, path: str | None = None) -> None:
    with _connect(path) as conn:
        conn.execute(
            "UPDATE characters SET class_name = ?, class_set_at = ?, class_ability = NULL WHERE id = ?",
            (class_name, _now(), character_id),
        )


def set_class_ability(character_id: int, ability: str | None, path: str | None = None) -> None:
    with _connect(path) as conn:
        conn.execute("UPDATE characters SET class_ability = ? WHERE id = ?", (ability, character_id))


def attributes_of(personagem) -> dict[str, int]:
    """Os seis atributos de um personagem (linha do banco) como dicionário."""
    return {a: personagem[f"attr_{a}"] for a in rules.ATTRIBUTES}


def set_attributes(character_id: int, values: dict[str, int], path: str | None = None) -> None:
    """Grava só os atributos que vieram em values. Os nomes vêm de rules.ATTRIBUTES, nunca do usuário."""
    if not values:
        return
    if any(a not in rules.ATTRIBUTES for a in values):
        raise ValueError(f"Atributo desconhecido: {list(values)}")
    colunas = [f"attr_{a}" for a in values]
    with _connect(path) as conn:
        conn.execute(
            f"UPDATE characters SET {', '.join(c + ' = ?' for c in colunas)} WHERE id = ?",
            [int(v) for v in values.values()] + [character_id],
        )


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
# Registro das ações de mestre e cópia de segurança
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


def export_copy(dest_path: str, path: str | None = None) -> None:
    """Copia o banco inteiro pra dest_path de forma consistente, mesmo com o bot rodando."""
    origem = sqlite3.connect(path or DB_PATH)
    destino = sqlite3.connect(dest_path)
    try:
        origem.backup(destino)
    finally:
        destino.close()
        origem.close()
