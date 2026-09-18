"""Esquemas EXATOS das versões antigas do banco, pra testar a migração automática.
Gerado a partir do código de cada versão. Não editar na mão."""

import sqlite3

V1 = {
    "user_version": 0,
    "tables": [
        'CREATE TABLE rolls ( id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, username TEXT NOT NULL, guild_id TEXT, notation TEXT NOT NULL, rolls_json TEXT NOT NULL, total INTEGER NOT NULL, purpose TEXT, created_at TEXT NOT NULL )',
        'CREATE TABLE character_definitions ( user_id TEXT PRIMARY KEY, username TEXT NOT NULL, magic_rank TEXT, magic_rank_roll INTEGER, magic_rank_set_at TEXT, race TEXT, race_set_at TEXT )',
    ],
}

V2 = {
    "user_version": 2,
    "tables": [
        'CREATE TABLE rolls ( id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, username TEXT NOT NULL, guild_id TEXT, notation TEXT NOT NULL, rolls_json TEXT NOT NULL, total INTEGER NOT NULL, purpose TEXT, created_at TEXT NOT NULL , character_id INTEGER, character_name TEXT)',
        'CREATE TABLE characters ( id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, name TEXT NOT NULL, name_key TEXT NOT NULL, created_at TEXT NOT NULL, magic_rank TEXT, magic_rank_roll INTEGER, magic_rank_set_at TEXT, race TEXT, race_roll INTEGER, race_set_at TEXT, UNIQUE (user_id, name_key) )',
        'CREATE TABLE user_state ( user_id TEXT PRIMARY KEY, active_character_id INTEGER )',
        'CREATE TABLE master_actions ( id INTEGER PRIMARY KEY AUTOINCREMENT, master_id TEXT NOT NULL, master_name TEXT NOT NULL, target_user_id TEXT NOT NULL, character_id INTEGER, character_name TEXT, action TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL )',
    ],
}

V3 = {
    "user_version": 3,
    "tables": [
        'CREATE TABLE rolls ( id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, username TEXT NOT NULL, guild_id TEXT, notation TEXT NOT NULL, rolls_json TEXT NOT NULL, total INTEGER NOT NULL, purpose TEXT, created_at TEXT NOT NULL , character_id INTEGER, character_name TEXT)',
        'CREATE TABLE characters ( id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, name TEXT NOT NULL, name_key TEXT NOT NULL, created_at TEXT NOT NULL, magic_rank TEXT, magic_rank_roll INTEGER, magic_rank_set_at TEXT, race TEXT, race_roll INTEGER, race_set_at TEXT, level INTEGER NOT NULL DEFAULT 1, social_class TEXT, social_class_roll INTEGER, social_class_set_at TEXT, clergy TEXT, clergy_roll INTEGER, clergy_set_at TEXT, UNIQUE (user_id, name_key) )',
        'CREATE TABLE character_ranks ( character_id INTEGER NOT NULL, skill TEXT NOT NULL, skill_rank INTEGER NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY (character_id, skill) )',
        'CREATE TABLE user_state ( user_id TEXT PRIMARY KEY, active_character_id INTEGER )',
        'CREATE TABLE master_actions ( id INTEGER PRIMARY KEY AUTOINCREMENT, master_id TEXT NOT NULL, master_name TEXT NOT NULL, target_user_id TEXT NOT NULL, character_id INTEGER, character_name TEXT, action TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL )',
    ],
}


def create(path: str, versao: dict) -> None:
    """Cria um banco vazio no formato de uma versão antiga."""
    conn = sqlite3.connect(path)
    for sql in versao["tables"]:
        conn.execute(sql)
    conn.execute(f"PRAGMA user_version = {int(versao['user_version'])}")
    conn.commit()
    conn.close()
