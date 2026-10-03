"""Testes do banco (db.py) e das regras de XP. Rodar da pasta do bot: python tests/test_db.py"""
import importlib
import json
import os
import random
import sqlite3
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "tests"))
for k in ("DB_PATH", "RAILWAY_VOLUME_MOUNT_PATH"):
    os.environ.pop(k, None)

import db
import legacy_schemas as L
import rules

tmp = tempfile.mkdtemp()
def novo_banco(nome="t.db"):
    p = os.path.join(tmp, nome)
    if os.path.exists(p): os.remove(p)
    db.init_db(p)
    return p

# ---------- 1. onde o banco fica ----------
assert (db.DB_PATH, db.DB_SOURCE) == ("baptism_of_blood.db", "local") and not db.storage_is_persistent()
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = "/data"; importlib.reload(db)
assert (db.DB_PATH, db.DB_SOURCE) == ("/data/baptism_of_blood.db", "volume") and db.storage_is_persistent()
os.environ["DB_PATH"] = "/x/meu.db"; importlib.reload(db)
assert (db.DB_PATH, db.DB_SOURCE) == ("/x/meu.db", "DB_PATH")          # DB_PATH ganha do Volume
for k in ("DB_PATH", "RAILWAY_VOLUME_MOUNT_PATH"): os.environ.pop(k, None)
importlib.reload(db)
print("1. caminho do banco OK")

# ---------- 2. banco novo, em pasta que ainda não existe ----------
p = os.path.join(tmp, "volume", "sub", "bob.db")
db.init_db(p); db.init_db(p)                                              # rodar duas vezes não quebra
with sqlite3.connect(p) as c:
    assert c.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    tabelas = {r[0] for r in c.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")}
assert tabelas == {"rolls","characters","user_state","master_actions","character_ranks","xp_log","players","deleted_characters","level_attributes","character_disciplines","scenes","scene_participants","scene_intentions","dice_effects","character_vitals","character_skills","custom_abilities","character_skill_picks","npcs","npc_skills"}, tabelas
print("2. init_db OK")

# ---------- 3. personagens ----------
U, V = "111", "222"
k = db.create_character(U, "  Kairon   Flagon ", path=p)
assert k["name"] == "Kairon Flagon" and k["level"] == 1 and k["xp"] == 0
assert db.get_active_character(U, p)["id"] == k["id"]
c = db.create_character(U, "Charles de Flagon", path=p)
assert db.get_active_character(U, p)["id"] == c["id"]                     # criar já ativa
for dup in ("kairon flagon", "KAIRON  FLAGON"):
    try: db.create_character(U, dup, path=p); raise SystemExit("duplicado passou: " + dup)
    except db.CharacterExists: pass
db.create_character(V, "Kairon Flagon", path=p)                           # mesmo nome, outro jogador
e = db.create_character(U, "Émile", path=p)
assert db.find_character(U, "émile", p)["id"] == e["id"] and db.find_character(U, "Emile", p) is None
assert [r["name"] for r in db.list_characters(U, p)] == ["Kairon Flagon", "Charles de Flagon", "Émile"]
db.set_active_character(U, k["id"], p)
assert db.resolve_character(U, None, p)["name"] == "Kairon Flagon" and db.resolve_character(U, "charles DE flagon", p)["name"] == "Charles de Flagon"
assert db.resolve_character(U, "inexistente", p) is None and db.get_active_character("999", p) is None
outro = db.find_character(V, "Kairon Flagon", p)
db.set_active_character(U, outro["id"], p)
assert db.get_active_character(U, p)["user_id"] == U                       # nunca vaza o personagem de outro
db.set_active_character(U, k["id"], p)
print("3. personagens OK")

# ---------- 3b. limite de vagas ----------
pl = novo_banco("limite.db")
for n in ("A", "B", "C"): db.create_character("1", f"Pers {n}", max_characters=3, path=pl)
try: db.create_character("1", "Pers D", max_characters=3, path=pl); raise SystemExit("passou do limite")
except db.CharacterLimit as ex: assert (ex.usados, ex.permitidos) == (3, 3)
assert len(db.list_characters("1", pl)) == 3 and db.get_active_character("1", pl)["name"] == "Pers C"   # a recusa não mexeu em nada
db.create_character("2", "Outro jogador", max_characters=3, path=pl)     # o limite é por jogador
db.create_character("1", "Pers D", max_characters=4, path=pl)             # vaga extra
db.create_character("1", "Pers E", path=pl)                               # sem limite informado, não trava
try: db.create_character("1", "pers a", max_characters=99, path=pl); raise SystemExit("duplicado")
except db.CharacterExists: pass                                            # nome repetido continua valendo antes do limite
print("3b. limite de vagas OK")

# ---------- 4. histórico por personagem ----------
db.log_roll(U, "Marcos", "g1", "1d20", [7], 7, "ataque", k["id"], k["name"], p)
db.log_roll(U, "Marcos", "g1", "1d20", [15], 15, None, c["id"], c["name"], p)
db.log_roll(U, "Marcos", "g1", "1d6", [3], 3, None, None, None, p)
assert len(db.get_history(U, 10, None, p)) == 3
h = db.get_history(U, 10, k["id"], p); assert len(h) == 1 and h[0]["total"] == 7 and h[0]["character_name"] == "Kairon Flagon"
assert db.get_history(U, 1, None, p)[0]["notation"] == "1d6"
print("4. histórico OK")

# ---------- 5. definições ----------
db.set_magic_rank(k["id"], "Raro", 62, p); db.set_race(k["id"], "Vampiro", 90, p)
r = db.get_character_by_id(k["id"], p); assert (r["magic_rank"], r["magic_rank_roll"], r["race"], r["race_roll"]) == ("Raro", 62, "Vampiro", 90)
db.set_race(k["id"], "Dhampir", None, p); r = db.get_character_by_id(k["id"], p); assert r["race"] == "Dhampir" and r["race_roll"] is None
db.clear_definition(k["id"], "race", p); r = db.get_character_by_id(k["id"], p)
assert r["race"] is None and r["race_set_at"] is None and r["magic_rank"] == "Raro"
db.set_social_status(k["id"], "1º Estado", 95, "Alto Clero", 63, p)
r = db.get_character_by_id(k["id"], p); assert (r["social_class"], r["social_class_roll"], r["clergy"], r["clergy_roll"]) == ("1º Estado", 95, "Alto Clero", 63)
db.set_social_status(k["id"], "2º Estado", None, None, None, p)
r = db.get_character_by_id(k["id"], p); assert (r["clergy"], r["clergy_roll"], r["clergy_set_at"], r["social_class_roll"]) == (None, None, None, None)
db.set_social_status(k["id"], "1º Estado", 92, "Baixo Clero", 10, p); db.clear_definition(k["id"], "social_class", p)
r = db.get_character_by_id(k["id"], p); assert r["social_class"] is None and r["clergy"] is None and r["magic_rank"] == "Raro"
db.set_race(k["id"], "Humano", 5, p); db.clear_definition(k["id"], "todas", p)
r = db.get_character_by_id(k["id"], p); assert r["magic_rank"] is None and r["race"] is None and r["social_class"] is None
for ruim in ("vida; DROP TABLE characters", "ambos"):
    try: db.clear_definition(k["id"], ruim, p); raise SystemExit("aceitou: " + ruim)
    except ValueError: pass
db.log_master_action("1", "Mestre", U, k["id"], k["name"], "apagar", "ambos", p)
print("5. definições OK")

# ---------- 6. migrações a partir dos esquemas ANTIGOS reais ----------
# v1: definição por jogador, sem personagens
p1 = os.path.join(tmp, "v1.db"); L.create(p1, L.V1)
with sqlite3.connect(p1) as cn:
    cn.execute("INSERT INTO rolls (user_id, username, guild_id, notation, rolls_json, total, purpose, created_at) VALUES ('42','Fulano','g','1d100','[62]',62,'magia_inicial','2026-01-01T10:00:00+00:00')")
    cn.execute("INSERT INTO character_definitions (user_id, username, magic_rank, magic_rank_roll, magic_rank_set_at) VALUES ('42','Fulano','Raro',62,'2026-01-01T10:00:00+00:00')")
    cn.execute("INSERT INTO character_definitions (user_id, username, magic_rank, magic_rank_roll, magic_rank_set_at, race) VALUES ('77','Beltrana','Mítico',100,'2026-01-02T10:00:00+00:00','Vampiro')")
db.init_db(p1); db.init_db(p1)
f = db.get_active_character("42", p1)
assert (f["name"], f["magic_rank"], f["magic_rank_roll"], f["level"], f["xp"], f["social_class"]) == ("Fulano", "Raro", 62, 1, 0, None)
assert db.get_active_character("77", p1)["race"] == "Vampiro" and len(db.list_characters("42", p1)) == 1
assert len(db.get_history("42", 10, None, p1)) == 1
print("6a. v1 -> atual OK")

# v2: personagens, sem nível/estado/xp; com a raça no nome antigo
p2 = os.path.join(tmp, "v2.db"); L.create(p2, L.V2)
with sqlite3.connect(p2) as cn:
    cn.execute("INSERT INTO characters (id, user_id, name, name_key, created_at, magic_rank, magic_rank_roll, race, race_roll) VALUES (1,'7','Velho Personagem','velho personagem','2026-02-01T00:00:00+00:00','Raro',62,'Meio humano, meio vampiro',98)")
    cn.execute("INSERT INTO characters (id, user_id, name, name_key, created_at, race, race_roll) VALUES (2,'7','Vampiro Antigo','vampiro antigo','2026-02-01T00:00:00+00:00','Vampiro',90)")
    cn.execute("INSERT INTO user_state (user_id, active_character_id) VALUES ('7', 1)")
    cn.execute("INSERT INTO rolls (user_id, username, guild_id, notation, rolls_json, total, purpose, created_at, character_id, character_name) VALUES ('7','Zé','g','1d20','[4]',4,'teste','2026-02-01T00:00:00+00:00',1,'Velho Personagem')")
    cn.execute("INSERT INTO master_actions (master_id, master_name, target_user_id, action, created_at) VALUES ('1','M','7','apagar','2026-02-01T00:00:00+00:00')")
db.init_db(p2); db.init_db(p2)
r = db.get_character_by_id(1, p2)
assert (r["name"], r["magic_rank"], r["race"], r["race_roll"], r["level"], r["xp"], r["social_class"]) == ("Velho Personagem", "Raro", "Dhampir", 98, 1, 0, None)   # raça renomeada, número mantido
assert db.get_character_by_id(2, p2)["race"] == "Vampiro" and db.get_active_character("7", p2)["id"] == 1
assert len(db.get_history("7", 10, 1, p2)) == 1
with sqlite3.connect(p2) as cn: assert cn.execute("SELECT COUNT(*) FROM master_actions").fetchone()[0] == 1
print("6b. v2 -> atual OK")

# v3 (o que está em produção agora): nível 3 e nível 10 já existentes viram XP no começo do nível
p3 = os.path.join(tmp, "v3.db"); L.create(p3, L.V3)
with sqlite3.connect(p3) as cn:
    cn.execute("INSERT INTO characters (id, user_id, name, name_key, created_at, race, level, social_class, social_class_roll, clergy, clergy_roll) VALUES (1,'9','Nível Três','nível três','2026-03-01T00:00:00+00:00','Meio humano, meio vampiro',3,'1º Estado',95,'Alto Clero',63)")
    cn.execute("INSERT INTO characters (id, user_id, name, name_key, created_at, level) VALUES (2,'9','No Máximo','no máximo','2026-03-01T00:00:00+00:00',10)")
    cn.execute("INSERT INTO characters (id, user_id, name, name_key, created_at, level) VALUES (3,'9','Recém Nascido','recém nascido','2026-03-01T00:00:00+00:00',1)")
    cn.execute("INSERT INTO character_ranks VALUES (1,'Forja',5,'2026-03-01T00:00:00+00:00')")
db.init_db(p3); db.init_db(p3)
a, b, n = (db.get_character_by_id(i, p3) for i in (1, 2, 3))
assert (a["level"], a["xp"], b["level"], b["xp"], n["level"], n["xp"]) == (3, 3000, 10, 45000, 1, 0)
assert all(rules.level_for_xp(x["xp"]) == x["level"] for x in (a, b, n))   # nível e XP já saem coerentes
assert a["race"] == "Dhampir" and (a["social_class"], a["clergy"]) == ("1º Estado", "Alto Clero") and db.get_skill_ranks(1, p3) == {"Forja": 5}
with sqlite3.connect(p3) as cn:
    assert cn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
r = db.add_xp(1, 500, "pós-migração", "1", "Mestre", p3); assert (r["before_xp"], r["after_xp"]) == (3000, 3500)   # já dá pra usar
print("6c. v3 -> atual OK")

# v4 (o que está em produção agora): ganha classe e atributos, sem perder nada
p4 = os.path.join(tmp, "v4.db"); L.create(p4, L.V4)
with sqlite3.connect(p4) as cn:
    cn.execute("INSERT INTO characters (id, user_id, name, name_key, created_at, magic_rank, magic_rank_roll, race, race_roll, level, xp, social_class, social_class_roll) VALUES (1,'7','Kairon Flagon','kairon flagon','2026-09-18T00:00:00+00:00','Raro',62,'Dhampir',98,4,6500,'2º Estado',85)")
    cn.execute("INSERT INTO rolls (user_id, username, guild_id, notation, rolls_json, total, purpose, created_at, character_id, character_name) VALUES ('7','Marcos','g','1d20','[17]',17,'ataque','2026-09-18T00:00:00+00:00',1,'Kairon Flagon')")
    cn.execute("INSERT INTO xp_log (character_id, character_name, amount, xp_before, xp_after, level_before, level_after, reason, master_id, master_name, created_at) VALUES (1,'Kairon Flagon',6500,0,6500,1,4,'início','1','Mestre','2026-09-18T00:00:00+00:00')")
    cn.execute("INSERT INTO players (user_id, display_name, extra_slots, updated_at) VALUES ('7','Marcos',2,'2026-09-18T00:00:00+00:00')")
    cn.execute("INSERT INTO deleted_characters (character_id, user_id, name, snapshot_json, deleted_by_id, deleted_by_name, deleted_at) VALUES (9,'7','Antigo','{}','7','Marcos','2026-09-18T00:00:00+00:00')")
    cn.execute("INSERT INTO character_ranks VALUES (1,'Forja',3,'2026-09-18T00:00:00+00:00')")
db.init_db(p4); db.init_db(p4)
a = db.get_character_by_id(1, p4)
assert (a["name"], a["magic_rank"], a["race"], a["level"], a["xp"], a["social_class"]) == ("Kairon Flagon", "Raro", "Dhampir", 4, 6500, "2º Estado")   # nada mudou
assert a["class_name"] is None and a["class_set_at"] is None and db.attributes_of(a) == {x: 0 for x in rules.ATTRIBUTES}                                # colunas novas, neutras
assert len(db.get_history("7", 10, None, p4)) == 1 and db.get_skill_ranks(1, p4) == {"Forja": 3} and db.get_extra_slots("7", p4) == 2 and db.count_deleted("7", p4) == 1
assert len(db.get_xp_log(1, 10, p4)) == 1 and db.get_player_names(p4) == {"7": "Marcos"}
with sqlite3.connect(p4) as cn: assert cn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
db.set_class(1, "Caçador", p4); db.set_attributes(1, {"vitalidade": 3}, p4); assert db.attributes_of(db.get_character_by_id(1, p4))["vitalidade"] == 3   # já dá pra usar
print("6d. v4 -> v5 (com dados) OK")

# v5 (o que está em produção agora): quem já passou do nível 1 congela os níveis de trás com os atributos de hoje
p5 = os.path.join(tmp, "v5.db"); L.create(p5, L.V5)
INS = ("INSERT INTO characters (id, user_id, name, name_key, created_at, level, xp, class_name, attr_forca, attr_destreza,"
       " attr_vitalidade, attr_razao, attr_vontade, attr_alma) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)")
with sqlite3.connect(p5) as cn:
    cn.execute(INS, (1, "7", "Kairon Flagon", "kairon flagon", "2026-09-18T00:00:00+00:00", 4, 6000, "Caçador", 1, 0, 3, 0, 2, 1))   # nível 4, com atributos
    cn.execute(INS, (2, "7", "Sem Pontos", "sem pontos", "2026-09-18T00:00:00+00:00", 4, 6000, "Sábio", 0, 2, 0, 3, 0, 0))           # nível 4, só Destreza e Razão (não contam)
    cn.execute(INS, (3, "7", "Novato", "novato", "2026-09-18T00:00:00+00:00", 1, 0, None, 0, 0, 0, 0, 0, 0))                        # nível 1
    cn.execute(INS, (4, "8", "No Máximo", "no máximo", "2026-09-18T00:00:00+00:00", 10, 45000, "Ladrão", 2, 0, 3, 0, 1, 1))        # nível 10
    cn.execute("INSERT INTO rolls (user_id, username, guild_id, notation, rolls_json, total, purpose, created_at, character_id, character_name) VALUES ('7','Marcos','g','1d20','[17]',17,'ataque','2026-09-18T00:00:00+00:00',1,'Kairon Flagon')")
    cn.execute("INSERT INTO xp_log (character_id, character_name, amount, xp_before, xp_after, level_before, level_after, reason, master_id, master_name, created_at) VALUES (1,'Kairon Flagon',6000,0,6000,1,4,'início','1','Mestre','2026-09-18T00:00:00+00:00')")
    cn.execute("INSERT INTO players (user_id, display_name, extra_slots, updated_at) VALUES ('7','Marcos',1,'2026-09-18T00:00:00+00:00')")
db.init_db(p5); db.init_db(p5)                                                                   # migra; repetir não estraga
with sqlite3.connect(p5) as cn: assert cn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
k, sp, nv, mx = (db.get_character_by_id(i, p5) for i in (1, 2, 3, 4))
assert (k["name"], k["level"], k["xp"], k["class_name"]) == ("Kairon Flagon", 4, 6000, "Caçador") and (mx["level"], mx["xp"]) == (10, 45000)      # nada mudou
assert len(db.get_history("7", 10, None, p5)) == 1 and len(db.get_xp_log(1, 10, p5)) == 1 and db.get_extra_slots("7", p5) == 1
atuais = {"forca": 1, "destreza": 0, "vitalidade": 3, "razao": 0, "vontade": 2, "alma": 1}
assert db.get_level_attributes(1, p5) == {1: atuais, 2: atuais, 3: atuais}                                # níveis 1 a 3 congelados, o 4 (atual) não tem linha
assert db.get_level_attributes(2, p5) == {} and db.get_level_attributes(3, p5) == {}                        # zerado (só Destreza/Razão) e nível 1: nada
assert sorted(db.get_level_attributes(4, p5)) == list(range(1, 10))                                        # nível 10: 9 linhas
assert [len(db.attributes_per_level(x, p5)) for x in (k, sp, nv, mx)] == [4, 4, 1, 10]
assert rules.calculate_resources_by_level(db.attributes_per_level(k, p5), "Caçador")["vida"]["total"] == 15 * 4 + 35
with db._connect(p5) as cn:                                                                              # rodar a migração de novo à mão não duplica nem muda nada
    db._migrar_v6(cn); db._migrar_v6(cn)
assert db.get_level_attributes(1, p5) == {1: atuais, 2: atuais, 3: atuais} and sorted(db.get_level_attributes(4, p5)) == list(range(1, 10))
with sqlite3.connect(p5) as cn: assert cn.execute("SELECT COUNT(*) FROM level_attributes").fetchone()[0] == 3 + 9
db.add_xp(1, 4000, "pós-migração", "1", "Mestre", p5)                                                    # já funciona: o nível 4 congela ao ir pro 5
assert sorted(db.get_level_attributes(1, p5)) == [1, 2, 3, 4]
db.set_attributes(2, {"vitalidade": 2}, p5); db.add_xp(2, 4000, "pós-migração", "1", "Mestre", p5)         # quem estava zerado congela quando distribui e sobe
assert sorted(db.get_level_attributes(2, p5)) == [1, 2, 3, 4] and db.get_level_attributes(2, p5)[1]["vitalidade"] == 2
print("6e. v5 -> v6 (com dados) OK")

# v6 (o que está em produção agora): raça e classe social ganham o contador de chances, sem perder nada
p6 = os.path.join(tmp, "v6.db"); L.create(p6, L.V6)
INS6 = ("INSERT INTO characters (id, user_id, name, name_key, created_at, level, xp, race, race_roll, social_class, social_class_roll,"
        " clergy, clergy_roll, class_name, magic_rank, magic_rank_roll) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")
with sqlite3.connect(p6) as cn:
    cn.execute(INS6, (1, "7", "Completo", "completo", "2026-09-18T00:00:00+00:00", 4, 6000, "Vampiro", 90, "1º Estado", 95, "Alto Clero", 60, "Caçador", "Raro", 62))
    cn.execute(INS6, (2, "7", "So Raca", "so raca", "2026-09-18T00:00:00+00:00", 1, 0, "Humano", 40, None, None, None, None, None, None, None))
    cn.execute(INS6, (3, "8", "Novato", "novato", "2026-09-18T00:00:00+00:00", 1, 0, None, None, None, None, None, None, None, None, None))
    cn.execute(INS6, (4, "8", "Cem", "cem", "2026-09-18T00:00:00+00:00", 1, 0, "Dhampir", 97, "Aguardando o mestre", 100, None, None, None, None, None))
    cn.execute("INSERT INTO rolls (user_id, username, guild_id, notation, rolls_json, total, purpose, created_at, character_id, character_name) VALUES ('7','Marcos','g','1d20','[17]',17,'ataque','2026-09-18T00:00:00+00:00',1,'Completo')")
    cn.execute("INSERT INTO players (user_id, display_name, extra_slots, updated_at) VALUES ('7','Marcos',1,'2026-09-18T00:00:00+00:00')")
    cn.execute("INSERT INTO level_attributes VALUES (1, 1, 1, 0, 3, 0, 2, 1)")
db.init_db(p6); db.init_db(p6)                                                                   # migra; repetir não estraga
with sqlite3.connect(p6) as cn: assert cn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
por = {i: db.get_character_by_id(i, p6) for i in (1, 2, 3, 4)}
assert [(por[i]["race_attempts"], por[i]["social_class_attempts"]) for i in (1, 2, 3, 4)] == [(1, 1), (1, 0), (0, 0), (1, 1)]   # quem já rolou gastou 1 chance
assert (por[1]["race"], por[1]["race_roll"], por[1]["social_class"], por[1]["clergy"], por[1]["class_name"], por[1]["magic_rank"], por[1]["level"], por[1]["xp"]) == ("Vampiro", 90, "1º Estado", "Alto Clero", "Caçador", "Raro", 4, 6000)   # nada mudou
assert len(db.get_history("7", 10, None, p6)) == 1 and db.get_extra_slots("7", p6) == 1 and sorted(db.get_level_attributes(1, p6)) == [1]
assert rules.reroll_block(por[1], "race") == "classe" and rules.reroll_block(por[2], "race") is None and rules.attempts_left(por[2], "race") == 2
assert rules.reroll_block(por[4], "social_class") == "mestre" and rules.attempts_left(por[3], "race") == 3
db.set_race(2, "Vampiro", 90, p6); assert db.get_character_by_id(2, p6)["race_attempts"] == 2                                 # já dá pra usar
with db._connect(p6) as cn: db.init_db(p6)                                                                                     # rodar de novo não zera nem soma
assert db.get_character_by_id(2, p6)["race_attempts"] == 2 and db.get_character_by_id(1, p6)["race_attempts"] == 1
with sqlite3.connect(p6) as cn:                                                                                                   # a tabela nova nasce vazia no banco migrado
    assert cn.execute("SELECT COUNT(*) FROM character_disciplines").fetchone()[0] == 0
db.set_discipline_grade(1, "Potência", 2, p6); assert db.get_disciplines(1, p6) == {"Potência": 2}
with sqlite3.connect(p6) as cn:                                                                                                   # as tabelas das cenas nascem vazias no banco migrado
    for tabela in ("scenes", "scene_participants", "scene_intentions"): assert cn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0] == 0, tabela
    assert {r[1] for r in cn.execute("PRAGMA index_list(scenes)")} == {"idx_scenes_channel"}
cena6 = db.create_scene("g", "1", "Migrada", "9", p6); assert cena6 is not None and db.add_participant(cena6["id"], "npc", "Guarda", 12, None, None, None, p6)
print("6f. v6 -> v7 (com dados) OK")

# ---------- 7. XP: níveis, saltos, remoção, extrato ----------
px = novo_banco("xp.db"); x = db.create_character("5", "Xis", path=px)["id"]
seq = [(999, 999, 1), (1, 1000, 2), (2000, 3000, 3), (2999, 5999, 3), (1, 6000, 4), (39000, 45000, 10), (5000, 50000, 10)]
for quantia, xp_esp, nivel_esp in seq:
    r = db.add_xp(x, quantia, "teste", "1", "Mestre", px)
    assert (r["applied"], r["after_xp"], r["after_level"]) == (quantia, xp_esp, nivel_esp), (quantia, r)
    ch = db.get_character_by_id(x, px); assert (ch["xp"], ch["level"]) == (xp_esp, nivel_esp)
assert len(db.get_xp_log(x, 50, px)) == 7 and db.get_xp_log(x, 3, px)[0]["amount"] == 5000 and db.get_xp_log(x, 1, px)[0]["reason"] == "teste"
r = db.add_xp(x, 1_000_000, None, "1", "Mestre", px); assert r["after_level"] == 10                      # no 10 o XP continua contando
r = db.add_xp(x, -2_000_000, "engano", "1", "Mestre", px)                                                # tirar demais: para no zero
assert (r["after_xp"], r["after_level"]) == (0, 1) and r["applied"] == -1_050_000
assert db.add_xp(x, -5, "nada a tirar", "1", "M", px)["applied"] == 0                                    # sem XP: nada muda...
n_log = len(db.get_xp_log(x, 100, px)); db.add_xp(x, 0, "zero", "1", "M", px); assert len(db.get_xp_log(x, 100, px)) == n_log   # ...e não polui o extrato
db.add_xp(x, 3000, None, None, None, px); r = db.add_xp(x, -1, "cruzou pra baixo", "1", "M", px)         # 2999 => desce pro nível 2
assert (r["before_level"], r["after_level"]) == (3, 2) and db.get_character_by_id(x, px)["level"] == 2
assert db.add_xp(9999, 10, None, None, None, px) is None                                                  # personagem inexistente
db.set_level(x, 7, px); ch = db.get_character_by_id(x, px); assert (ch["level"], ch["xp"]) == (7, 21000)
db.set_level(x, 1, px); assert db.get_character_by_id(x, px)["xp"] == 0
db.set_xp(x, 4250, px); ch = db.get_character_by_id(x, px); assert (ch["level"], ch["xp"]) == (3, 4250)
# invariante: depois de qualquer sequência de operações, nível == nível do XP, XP >= 0, e o extrato fecha
random.seed(7); pr = novo_banco("prop.db"); y = db.create_character("6", "Propriedade", path=pr)["id"]
for _ in range(600):
    db.add_xp(y, random.choice([-50000, -3000, -1, 1, 250, 999, 1000, 7777, 45000]), "x", "1", "M", pr)
    ch = db.get_character_by_id(y, pr)
    assert ch["xp"] >= 0 and ch["level"] == rules.level_for_xp(ch["xp"])
log = db.get_xp_log(y, 10000, pr)
assert sum(l["amount"] for l in log) == db.get_character_by_id(y, pr)["xp"]
assert all(l["xp_after"] - l["xp_before"] == l["amount"] for l in log)
print("7. XP OK (600 operações aleatórias mantêm nível e XP coerentes)")

# ---------- 8. ranks de perícia ----------
db.set_skill_rank(k["id"], "Forja", 3, p); db.set_skill_rank(k["id"], "Fé", 1, p); db.set_skill_rank(k["id"], "Forja", 5, p)
assert db.get_skill_ranks(k["id"], p) == {"Forja": 5, "Fé": 1} and db.get_skill_ranks(c["id"], p) == {}
print("8. ranks de perícia OK")

# ---------- 9. jogadores e vagas extras ----------
pj = novo_banco("jog.db")
assert db.get_extra_slots("1", pj) == 0
db.set_extra_slots("1", 2, pj); assert db.get_extra_slots("1", pj) == 2
db.remember_player("1", "Marcos", pj); assert db.get_extra_slots("1", pj) == 2 and db.get_player_names(pj) == {"1": "Marcos"}   # guardar o nome não zera as vagas
db.remember_player("1", "Marcos M.", pj); assert db.get_player_names(pj)["1"] == "Marcos M."
db.set_extra_slots("1", 0, pj); assert db.get_extra_slots("1", pj) == 0 and db.get_player_names(pj)["1"] == "Marcos M."         # mexer nas vagas não apaga o nome
db.set_extra_slots("3", 1, pj); assert db.get_player_names(pj) == {"1": "Marcos M."}                                             # jogador sem nome guardado não aparece
print("9. jogadores e vagas OK")

# ---------- 10. exclusão permanente ----------
pd = novo_banco("del.db")
a = db.create_character("1", "Apagável", path=pd); b = db.create_character("1", "Fica", path=pd)
db.set_active_character("1", a["id"], pd)
db.add_xp(a["id"], 4000, "RP", "9", "Mestre", pd); db.set_race(a["id"], "Vampiro", 90, pd); db.set_skill_rank(a["id"], "Forja", 4, pd)
db.log_roll("1", "Ana", "g", "1d20", [9], 9, "ataque", a["id"], a["name"], pd)
snap = db.delete_character(a["id"], "1", "Ana", pd)
assert snap["name"] == "Apagável" and snap["xp"] == 4000 and snap["level"] == 3 and snap["race"] == "Vampiro" and snap["ranks"] == {"Forja": 4}
assert db.get_character_by_id(a["id"], pd) is None and db.find_character("1", "Apagável", pd) is None
assert db.get_skill_ranks(a["id"], pd) == {} and db.get_xp_log(a["id"], 10, pd) == []           # ranks e extrato somem
h = db.get_history("1", 10, None, pd); assert len(h) == 1 and h[0]["character_id"] is None and h[0]["character_name"] == "Apagável"   # rolagem fica, sem ligação
assert db.get_active_character("1", pd)["id"] == b["id"]                                      # o ativo passou pro que sobrou
assert db.get_character_by_id(b["id"], pd)["xp"] == 0                                          # o outro não foi mexido
assert db.count_deleted("1", pd) == 1 and db.count_deleted("2", pd) == 0
with sqlite3.connect(pd) as cn:
    linha = cn.execute("SELECT name, snapshot_json, deleted_by_name FROM deleted_characters").fetchone()
    assert linha[0] == "Apagável" and linha[2] == "Ana" and json.loads(linha[1])["xp"] == 4000
assert db.delete_character(a["id"], "1", "Ana", pd) is None                                    # apagar de novo (clique duplo): nada acontece
assert db.count_deleted("1", pd) == 1
db.delete_character(b["id"], "1", "Ana", pd); assert db.get_active_character("1", pd) is None   # sem personagens sobrando
for i in range(3): db.create_character("1", f"Novo {i}", max_characters=3, path=pd)             # a vaga foi liberada de verdade
again = db.create_character("1", "Apagável", max_characters=99, path=pd)                        # mesmo nome de novo: é outro personagem, sem herdar nada
assert again["id"] != a["id"] and again["xp"] == 0 and db.get_xp_log(again["id"], 10, pd) == []
print("10. exclusão permanente OK")

# ---------- 11. rank público de XP ----------
pk = novo_banco("rank.db")
def mk(uid, nome, xp):
    ch = db.create_character(uid, nome, path=pk)
    if xp: db.add_xp(ch["id"], xp, "t", "9", "M", pk)
    return ch
mk("1", "Ana Um", 12300); mk("1", "Ana Dois", 500); mk("2", "Beto", 12300); mk("2", "Beto Zerado", 0); mk("3", "Caio", 45000); mk("3", "Caio Novo", 1000)
db.remember_player("1", "Ana", pk); db.remember_player("2", "Beto", pk)
rc = db.rank_characters(pk)
assert [r["name"] for r in rc] == ["Caio", "Ana Um", "Beto", "Caio Novo", "Ana Dois"]          # desempate: o mais antigo na frente; zerado fora
assert [r["owner"] for r in rc] == [None, "Ana", "Beto", None, "Ana"] and rc[0]["level"] == 10
rp = db.rank_players(pk)
assert [(r["user_id"], r["total_xp"], r["personagens"], r["melhor_nivel"]) for r in rp] == [("3", 46000, 2, 10), ("1", 12800, 2, 5), ("2", 12300, 2, 5)]
assert [r["owner"] for r in rp] == [None, "Ana", "Beto"]
assert db.rank_characters(novo_banco("vazio.db")) == [] and db.rank_players(novo_banco("vazio2.db")) == []
print("11. rank OK")

# ---------- 12. classe e atributos ----------
pf = novo_banco("ficha.db"); f = db.create_character("1", "Ficha Viva", path=pf)
assert f["class_name"] is None and f["class_set_at"] is None and db.attributes_of(f) == {a: 0 for a in rules.ATTRIBUTES}
db.set_class(f["id"], "Ladrão", pf); r = db.get_character_by_id(f["id"], pf); assert r["class_name"] == "Ladrão" and r["class_set_at"]
db.set_class(f["id"], "Sábio", pf); assert db.get_character_by_id(f["id"], pf)["class_name"] == "Sábio"
db.set_attributes(f["id"], {"forca": 2, "vitalidade": 3}, pf)
assert db.attributes_of(db.get_character_by_id(f["id"], pf)) == {"forca": 2, "destreza": 0, "vitalidade": 3, "razao": 0, "vontade": 0, "alma": 0}
db.set_attributes(f["id"], {"vontade": 1}, pf)                                            # só mexe no que veio
assert db.attributes_of(db.get_character_by_id(f["id"], pf)) == {"forca": 2, "destreza": 0, "vitalidade": 3, "razao": 0, "vontade": 1, "alma": 0}
db.set_attributes(f["id"], {}, pf)                                                        # vazio não faz nada
for ruim in ({"sorte": 3}, {"forca": 1, "vitalidade = 99; DROP TABLE characters; --": 1}):
    try: db.set_attributes(f["id"], ruim, pf); raise SystemExit("deveria recusar " + str(ruim))
    except ValueError: pass
assert db.get_character_by_id(f["id"], pf)["attr_forca"] == 2                             # a recusa não gravou nada, e a tabela segue viva
outro = db.create_character("1", "Outro", path=pf); assert db.attributes_of(outro) == {a: 0 for a in rules.ATTRIBUTES} and outro["class_name"] is None
snap = db.delete_character(f["id"], "1", "Ana", pf); assert snap["class_name"] == "Sábio" and snap["attr_vitalidade"] == 3   # a cópia dos excluídos leva a ficha toda
db.clear_definition(outro["id"], "todas", pf); assert db.get_character_by_id(outro["id"], pf)["class_name"] is None          # 'apagar' não mexe na classe
print("12. classe e atributos OK")

# ---------- 13. cópia de segurança ----------
pc = novo_banco("orig.db"); c1 = db.create_character("1", "Copiado", path=pc)["id"]; db.add_xp(c1, 2500, "teste", "9", "M", pc); db.set_class(c1, "Mundano", pc)
dest = os.path.join(tmp, "copia", "backup.db"); os.makedirs(os.path.dirname(dest))
db.export_copy(dest, pc)
with sqlite3.connect(dest) as cn:
    assert cn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    assert cn.execute("SELECT name, xp, level, class_name FROM characters").fetchone() == ("Copiado", 2500, 2, "Mundano")
    assert cn.execute("SELECT COUNT(*) FROM xp_log").fetchone()[0] == 1
db.add_xp(c1, 1, "depois da cópia", "9", "M", pc)
with sqlite3.connect(dest) as cn: assert cn.execute("SELECT xp FROM characters").fetchone()[0] == 2500       # a cópia é uma foto
copia = db.get_character_by_id(1, dest)                                                                        # e é um banco de verdade: abre e funciona
assert copia["name"] == "Copiado"; db.init_db(dest)
try: db.export_copy(os.path.join(tmp, "nao_existe", "x.db"), pc); raise SystemExit("deveria falhar")
except sqlite3.OperationalError: pass
print("13. cópia de segurança OK")

# ---------- 14. atributo da época: cada nível guarda os atributos que o personagem tinha ----------
pe = novo_banco("epoca.db")
def cria(nome, **attrs):
    cid = db.create_character("1", nome, path=pe)["id"]; db.set_class(cid, "Caçador", pe)
    if attrs: db.set_attributes(cid, attrs, pe)
    return cid
def linhas(cid): return db.get_level_attributes(cid, pe)
def total(cid, recurso="vida"):
    return rules.calculate_resources_by_level(db.attributes_per_level(db.get_character_by_id(cid, pe), pe), "Caçador")[recurso]["total"]

# o exemplo do prompt: Vitalidade 3 nos níveis 1 a 3 e 4 a partir do nível 4 -> Vida 80, 100, 120
a = cria("Época A", vitalidade=3)
assert total(a) == 15 + 35 and linhas(a) == {}                                          # nível 1: uma vez só, sem linha
db.add_xp(a, 3000, "nível 3", path=pe); assert total(a) == 80 and sorted(linhas(a)) == [1, 2]
db.add_xp(a, 3000, "nível 4", path=pe); assert sorted(linhas(a)) == [1, 2, 3]
db.set_attributes(a, {"vitalidade": 4}, pe)                                             # aumento depois de subir: só vale daí pra frente
assert total(a) == 100 and [linhas(a)[n]["vitalidade"] for n in (1, 2, 3)] == [3, 3, 3]
db.add_xp(a, 4000, "nível 5", path=pe); assert total(a) == 120 and sorted(linhas(a)) == [1, 2, 3, 4] and linhas(a)[4]["vitalidade"] == 4
assert [x["vitalidade"] for x in db.attributes_per_level(db.get_character_by_id(a, pe), pe)] == [3, 3, 3, 4, 4]
# baixar de nível (XP negativo, set_level ou set_xp) apaga as linhas do nível novo em diante
db.add_xp(a, -4000, "volta pro 4", path=pe); assert db.get_character_by_id(a, pe)["level"] == 4 and sorted(linhas(a)) == [1, 2, 3] and total(a) == 100
db.set_level(a, 2, pe); assert sorted(linhas(a)) == [1] and total(a) == 15 + 20 + 35      # o nível 2 (atual) passa a usar Vitalidade 4
db.set_xp(a, 0, pe); assert linhas(a) == {} and db.get_character_by_id(a, pe)["level"] == 1
db.set_xp(a, 500, pe); assert linhas(a) == {}                                           # mexer no XP sem mudar de nível não faz nada
# atributos zerados na hora de subir: não congela, e o nível continua usando os atributos atuais até congelar de verdade
b = cria("Época B"); db.add_xp(b, 1000, "nível 2", path=pe); assert linhas(b) == {}
db.set_attributes(b, {"vitalidade": 3}, pe); assert total(b) == 15 * 2 + 35             # os dois níveis usam o atributo que ele distribuiu depois
db.add_xp(b, 2000, "nível 3", path=pe); assert sorted(linhas(b)) == [1, 2]
db.set_attributes(b, {"vitalidade": 4}, pe); assert total(b) == 15 * 2 + 20 + 35 and linhas(b)[1]["vitalidade"] == 3
# só Destreza e Razão preenchidas não contam como 'distribuiu' (elas não entram nos recursos)
c = cria("Época C", destreza=2, razao=3); db.add_xp(c, 1000, "nível 2", path=pe); assert linhas(c) == {}
# subir vários níveis de uma vez: os do meio congelam com os atributos do momento da subida
d = cria("Época D", vitalidade=3); db.add_xp(d, 10000, "salto pro 5", path=pe)
assert sorted(linhas(d)) == [1, 2, 3, 4] and all(linhas(d)[n]["vitalidade"] == 3 for n in (1, 2, 3, 4))
db.set_attributes(d, {"vitalidade": 5}, pe); antes = dict(linhas(d)); db.add_xp(d, 26000, "salto pro 9", path=pe)
assert sorted(linhas(d)) == list(range(1, 9)) and {n: linhas(d)[n] for n in (1, 2, 3, 4)} == {n: antes[n] for n in (1, 2, 3, 4)}   # as de trás não são reescritas
assert all(linhas(d)[n]["vitalidade"] == 5 for n in (5, 6, 7, 8))
# set_attributes nunca mexe nas linhas; e uma linha perdida no nível atual é ignorada
antes = dict(linhas(d)); db.set_attributes(d, {"vitalidade": 6, "forca": 2}, pe); assert linhas(d) == antes
with sqlite3.connect(pe) as cn: cn.execute("INSERT INTO level_attributes VALUES (?, 9, 9, 9, 9, 9, 9, 9)", (d,))
assert db.attributes_per_level(db.get_character_by_id(d, pe), pe)[-1]["vitalidade"] == 6
# excluir o personagem apaga as linhas dele, e só as dele
e = cria("Época E", vitalidade=2); db.add_xp(e, 3000, "nível 3", path=pe); assert sorted(linhas(e)) == [1, 2]
fica = dict(linhas(d)); assert db.delete_character(e, "1", "Ana", pe)
assert linhas(e) == {} and linhas(d) == fica
with sqlite3.connect(pe) as cn: assert cn.execute("SELECT COUNT(*) FROM level_attributes WHERE character_id = ?", (e,)).fetchone()[0] == 0
# 500 operações aleatórias contra um modelo simples e independente
rng = random.Random(6); ids = [cria(f"Aleatório {i}") for i in range(3)]
M = {i: {"xp": 0, "attrs": {x: 0 for x in rules.ATTRIBUTES}, "rows": {}} for i in ids}
def modelo_mudou(m, antes, depois):
    if depois > antes:
        if any(m["attrs"][x] for x in rules.RESOURCE_ATTRIBUTES):
            for n in range(1, depois): m["rows"].setdefault(n, dict(m["attrs"]))
    elif depois < antes:
        m["rows"] = {n: v for n, v in m["rows"].items() if n < depois}
for _ in range(500):
    i = rng.choice(ids); m = M[i]; antes = rules.level_for_xp(m["xp"]); op = rng.choice(["xp", "xp", "attr", "nivel"])
    if op == "xp":
        q = rng.randint(-8000, 12000); db.add_xp(i, q, path=pe); m["xp"] = max(0, m["xp"] + q); modelo_mudou(m, antes, rules.level_for_xp(m["xp"]))
    elif op == "attr":
        v = {x: rng.randint(0, 6) for x in rng.sample(rules.ATTRIBUTES, rng.randint(1, 3))}; db.set_attributes(i, v, pe); m["attrs"].update(v)
    else:
        n = rng.randint(1, 10); db.set_level(i, n, pe); m["xp"] = rules.xp_at_level_start(n); modelo_mudou(m, antes, n)
    ch = db.get_character_by_id(i, pe)
    assert (ch["xp"], ch["level"]) == (m["xp"], rules.level_for_xp(m["xp"]))
    assert linhas(i) == m["rows"] and all(n < ch["level"] for n in m["rows"]) and len(db.attributes_per_level(ch, pe)) == ch["level"]
print("14. atributo da época OK (500 operações aleatórias batem com o modelo)")

# ---------- 15. apagar o histórico de rolagens de um jogador ----------
ph = novo_banco("historico.db")
ca = db.create_character("1", "Com Rolagens", path=ph)["id"]; cb = db.create_character("1", "Outro Da Ana", path=ph)["id"]
for i in range(5): db.log_roll("1", "Ana", "g", "1d20", [i + 1], i + 1, "teste", ca, "Com Rolagens", ph)        # com personagem
for i in range(2): db.log_roll("1", "Ana", "g", "1d100", [40], 40, "raca_inicial", cb, "Outro Da Ana", ph)     # sorteio de criação
for i in range(3): db.log_roll("1", "Ana", "g", "1d6", [2], 2, None, None, None, ph)                            # sem personagem
for i in range(4): db.log_roll("2", "Beto", "g", "1d20", [7], 7, None, None, None, ph)
db.add_xp(ca, 1500, "x", "9", "M", ph); db.set_race(cb, "Humano", 40, ph); db.set_class(ca, "Sábio", ph)
assert (db.count_rolls("1", ph), db.count_rolls("2", ph), db.count_rolls("999", ph)) == (10, 4, 0)
assert db.delete_rolls("1", ph) == 10                                                                            # devolve quantas eram
assert db.count_rolls("1", ph) == 0 and db.get_history("1", 50, None, ph) == [] and db.get_history("1", 50, ca, ph) == []
assert db.count_rolls("2", ph) == 4 and len(db.get_history("2", 50, None, ph)) == 4                              # o histórico de ninguém mais mexe
a = db.get_character_by_id(ca, ph); b = db.get_character_by_id(cb, ph)                                            # ficha, XP e personagens ficam
assert (a["xp"], a["level"], a["class_name"]) == (1500, 2, "Sábio") and b["race"] == "Humano" and len(db.list_characters("1", ph)) == 2
assert len(db.get_xp_log(ca, 10, ph)) == 1
assert db.delete_rolls("1", ph) == 0 and db.delete_rolls("999", ph) == 0                                          # de novo (ou quem não tem nada): 0
db.log_roll("1", "Ana", "g", "1d20", [9], 9, None, ca, "Com Rolagens", ph); assert db.count_rolls("1", ph) == 1  # e o histórico volta a funcionar
print("15. apagar histórico OK")

# ---------- 16. chances de rolar raça e classe social (3 cada, a última vale) ----------
pc = novo_banco("chances.db"); cid = db.create_character("1", "Rolador", path=pc)["id"]; outro = db.create_character("1", "Outro", path=pc)["id"]
g = lambda i=cid: db.get_character_by_id(i, pc)
assert rules.CREATION_ROLL_ATTEMPTS == 3 and (g()["race_attempts"], g()["social_class_attempts"]) == (0, 0)
assert rules.attempts_left(g(), "race") == 3 and rules.reroll_block(g(), "race") is None
for n, (raca, d) in enumerate([("Humano", 40), ("Vampiro", 90), ("Dhampir", 97)], 1):                  # cada sorteio de verdade gasta uma chance
    db.set_race(cid, raca, d, pc); assert g()["race_attempts"] == n and g()["race"] == raca and g()["race_roll"] == d      # a última vale
assert rules.attempts_left(g(), "race") == 0 and rules.reroll_block(g(), "race") == "tentativas"
assert g()["social_class_attempts"] == 0 and g(outro)["race_attempts"] == 0                           # uma contagem não mexe na outra, nem no outro personagem
db.set_social_status(cid, "3º Estado", 50, None, None, pc); assert g()["social_class_attempts"] == 1
db.set_social_status(cid, "1º Estado", 95, "Alto Clero", 60, pc); assert g()["social_class_attempts"] == 2 and (g()["clergy"], g()["clergy_roll"]) == ("Alto Clero", 60)
db.set_social_status(cid, "2º Estado", 85, None, None, pc); assert g()["social_class_attempts"] == 3 and g()["clergy"] is None      # trocou o Estado: o clero antigo some
assert rules.reroll_block(g(), "social_class") == "tentativas"
db.set_magic_rank(cid, "Raro", 62, pc); assert g()["magic_rank"] == "Raro" and (g()["race_attempts"], g()["social_class_attempts"]) == (3, 3)   # a magia não tem chances
# o 100 da classe social gasta uma chance mas fecha: quem decide é o mestre
db.clear_definition(cid, "social_class", pc); assert (g()["social_class_attempts"], g()["social_class"], g()["clergy"]) == (0, None, None)
db.set_social_status(cid, "Aguardando o mestre", 100, None, None, pc); assert g()["social_class_attempts"] == 1 and rules.reroll_block(g(), "social_class") == "mestre"
# valor definido por mestre (roll None) fecha as chances, mesmo com todas sobrando
db.clear_definition(cid, "todas", pc); assert (g()["race_attempts"], g()["social_class_attempts"]) == (0, 0) and g()["magic_rank"] is None
db.set_race(cid, "Vampiro", None, pc); assert g()["race_attempts"] == 3 and g()["race_roll"] is None and rules.reroll_block(g(), "race") == "tentativas"
db.set_social_status(cid, "3º Estado", None, None, None, pc); assert g()["social_class_attempts"] == 3
# escolher a classe fecha as chances que sobravam
db.clear_definition(cid, "todas", pc); db.set_race(cid, "Humano", 40, pc); assert rules.reroll_block(g(), "race") is None
db.set_class(cid, "Sábio", pc); assert rules.reroll_block(g(), "race") == "classe" and rules.reroll_block(g(), "social_class") == "classe" and rules.attempts_left(g(), "race") == 2
db.clear_definition(cid, "race", pc); assert g()["race_attempts"] == 0 and g()["class_name"] == "Sábio"                # apagar só devolve as chances de quem foi apagado
db.clear_definition(cid, "magic_rank", pc); assert g()["race_attempts"] == 0
# excluir e criar de novo não herda nada
db.set_race(cid, "Humano", 40, pc); db.delete_character(cid, "1", "Ana", pc); novo_id = db.create_character("1", "Rolador", path=pc)["id"]
assert (g(novo_id)["race_attempts"], g(novo_id)["social_class_attempts"]) == (0, 0)
print("16. chances de raça e classe social OK")

# ---------- 17. Disciplinas ----------
pd = novo_banco("disciplinas.db"); vid = db.create_character("1", "Vlad", path=pd)["id"]; outro = db.create_character("1", "Outro", path=pd)["id"]
assert db.get_disciplines(vid, pd) == {}
db.set_discipline_grade(vid, "Regeneração", 2, pd); db.set_discipline_grade(vid, "Potência", 1, pd)
assert db.get_disciplines(vid, pd) == {"Potência": 1, "Regeneração": 2}                              # na ordem do sistema, não na ordem em que foram dadas
db.set_discipline_grade(vid, "Potência", 3, pd); db.set_discipline_grade(vid, "Potência", 4, pd)      # sobe, e o grau 4 do mestre também grava
assert db.get_disciplines(vid, pd)["Potência"] == 4 and db.get_disciplines(outro, pd) == {}           # o outro personagem não muda
db.set_discipline_grade(vid, "Regeneração", 0, pd); assert "Regeneração" not in db.get_disciplines(vid, pd)    # grau 0 tira
db.set_discipline_grade(vid, "Regeneração", 0, pd)                                                    # tirar o que não tem não estoura
with sqlite3.connect(pd) as cn: assert cn.execute("SELECT COUNT(*) FROM character_disciplines WHERE grade = 0").fetchone()[0] == 0
for ruim in (("Sombra", 1), ("Potência", 6), ("Potência", -1)):
    try: db.set_discipline_grade(vid, *ruim, pd); raise SystemExit("deveria recusar " + str(ruim))
    except ValueError: pass
assert db.get_disciplines(vid, pd) == {"Potência": 4}
db.set_discipline_grade(vid, "Sanguessugia", 1, pd); assert db.get_disciplines(vid, pd)["Sanguessugia"] == 1     # o banco não bloqueia a Sanguessugia: quem bloqueia é a regra
snap = db.delete_character(vid, "1", "Ana", pd)
assert snap["disciplines"] == {"Potência": 4, "Sanguessugia": 1} and db.get_disciplines(vid, pd) == {}         # a cópia dos excluídos leva as Disciplinas, e elas somem
with sqlite3.connect(pd) as cn: assert cn.execute("SELECT COUNT(*) FROM character_disciplines WHERE character_id = ?", (vid,)).fetchone()[0] == 0
with sqlite3.connect(pd) as cn: assert cn.execute("SELECT COUNT(*) FROM deleted_characters WHERE character_id = ?", (vid,)).fetchone()[0] == 1   # uma cópia só
print("17. Disciplinas OK")

# ---------- 18. resultado especial (66 e 77) ----------
p8 = novo_banco("especial.db")
cid = db.create_character("1", "Sombra", path=p8)["id"]; G = lambda: db.get_character_by_id(cid, p8)
assert db.SCHEMA_VERSION == 13 and (G()["race_special"], G()["social_class_special"], G()["magic_rank_special"]) == (None, None, None)
db.set_race(cid, "Humano", 50, p8); assert G()["race_attempts"] == 1
db.set_special(cid, "race", 66, p8); c = G()                                                        # rolar de novo e cair 66 troca o Humano
assert (c["race"], c["race_roll"], c["race_set_at"], c["race_special"], c["race_attempts"]) == (None, None, None, 66, 2)
db.set_special(cid, "social_class", 77, p8); c = G()
assert (c["social_class"], c["social_class_roll"], c["social_class_special"], c["social_class_attempts"]) == (None, None, 77, 1)
db.set_social_status(cid, "1º Estado", 95, "Alto Clero", 80, p8); assert G()["clergy"] == "Alto Clero" and G()["social_class_special"] is None      # o sorteio normal limpa o especial
db.set_special(cid, "social_class", 66, p8); c = G()                                                # o clero sai junto
assert (c["social_class"], c["clergy"], c["clergy_roll"], c["clergy_set_at"], c["social_class_special"]) == (None, None, None, None, 66)
db.set_special(cid, "magic_rank", 77, p8); assert (G()["magic_rank"], G()["magic_rank_roll"], G()["magic_rank_special"]) == (None, None, 77)
# o mestre define: limpa o especial daquele campo, e só dele
db.set_race(cid, "Vampiro", None, p8); c = G(); assert (c["race"], c["race_special"], c["social_class_special"], c["magic_rank_special"]) == ("Vampiro", None, 66, 77)
db.set_magic_rank(cid, "Raro", None, p8); assert (G()["magic_rank"], G()["magic_rank_special"], G()["social_class_special"]) == ("Raro", None, 66)
db.set_social_status(cid, "3º Estado", None, None, None, p8); assert (G()["social_class"], G()["social_class_special"]) == ("3º Estado", None)
# apagar limpa o especial e devolve as chances
db.set_special(cid, "race", 77, p8); db.clear_definition(cid, "race", p8); c = G(); assert (c["race"], c["race_special"], c["race_attempts"]) == (None, None, 0)
db.set_special(cid, "social_class", 66, p8); db.set_special(cid, "magic_rank", 66, p8); db.clear_definition(cid, "todas", p8); c = G()
assert (c["social_class_special"], c["magic_rank_special"], c["social_class_attempts"]) == (None, None, 0)
# só aceita 66 ou 77 e campos que têm sorteio
for args in (("race", 65), ("race", 100), ("clergy", 66), ("class_name", 66)):
    try: db.set_special(cid, *args, path=p8); raise SystemExit(f"deveria recusar {args}")
    except ValueError: pass
assert (G()["race_special"], G()["social_class_special"], G()["magic_rank_special"]) == (None, None, None)     # as recusas não gravaram nada
print("18. resultado especial OK")

# ---------- 19. migração v7 -> v8: o banco que está no Railway ganha as três colunas sem perder nada ----------
p7 = novo_banco("v7_real.db")
with sqlite3.connect(p7) as cn:
    for coluna in ("race_special", "social_class_special", "magic_rank_special"): cn.execute(f"ALTER TABLE characters DROP COLUMN {coluna}")
    cn.execute("INSERT INTO characters (user_id, name, name_key, created_at, level, xp, race, race_roll, social_class, social_class_roll, class_name, race_attempts, social_class_attempts)"
               " VALUES ('7', 'Kairon Flagon', 'kairon flagon', '2026-09-18T00:00:00+00:00', 4, 6000, 'Vampiro', 90, '3º Estado', 50, 'Caçador', 1, 1)")
    cn.execute("PRAGMA user_version = 7")
with sqlite3.connect(p7) as cn: assert "race_special" not in {r[1] for r in cn.execute("PRAGMA table_info(characters)")}      # de fato é o formato antigo
db.init_db(p7); db.init_db(p7)                                                                      # duas vezes: idempotente
with sqlite3.connect(p7) as cn:
    assert cn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION == 13      # um banco v7 chega direto na versão atual
    colunas = {r[1] for r in cn.execute("PRAGMA table_info(characters)")}
    assert {"race_special", "social_class_special", "magic_rank_special"} <= colunas
    linha = cn.execute("SELECT name, level, xp, race, race_roll, social_class, class_name, race_attempts, social_class_attempts, race_special, social_class_special, magic_rank_special FROM characters").fetchone()
assert tuple(linha) == ("Kairon Flagon", 4, 6000, "Vampiro", 90, "3º Estado", "Caçador", 1, 1, None, None, None)      # nada mudou, as colunas novas nascem vazias
k7 = db.find_character("7", "Kairon Flagon", p7); db.set_special(k7["id"], "magic_rank", 77, p7); assert db.get_character_by_id(k7["id"], p7)["magic_rank_special"] == 77
print("19. migração v7 -> v8 OK")

# ---------- 20. a habilidade de classe escolhida ----------
p20 = novo_banco("habilidade.db")
h = db.create_character("1", "Padre", path=p20)["id"]; H = lambda: db.get_character_by_id(h, p20)
assert H()["class_ability"] is None
db.set_class(h, "Clérigo", p20); db.set_class_ability(h, "Bênção", p20); assert (H()["class_name"], H()["class_ability"]) == ("Clérigo", "Bênção")
db.set_class(h, "Clérigo", p20); assert H()["class_ability"] is None                                     # trocar (ou refazer) a classe zera a escolha
db.set_class_ability(h, "Mãos que Curam", p20); db.set_class(h, "Ladrão", p20); assert (H()["class_name"], H()["class_ability"]) == ("Ladrão", None)
db.set_class_ability(h, None, p20); assert H()["class_ability"] is None
snap = db.delete_character(h, "9", "Mestre", p20); assert snap["class_ability"] is None and "class_ability" in snap      # a coluna vai junto na cópia de quem foi excluído
print("20. habilidade escolhida OK")

# ---------- 21. efeitos de sorte do mestre ----------
p21 = novo_banco("sorte.db")
k = db.create_character("1", "Kairon", path=p21)["id"]; e = lambda: [(r["kind"], r["value"], r["uses_left"], r["quiet"], r["note"]) for r in db.get_dice_effects(k, p21)]
assert e() == [] and db.MAX_DICE_EFFECT_USES == 20
a = db.add_dice_effect(k, "vantagem", 12, 2, False, "boa noite", "9", p21)                                 # o valor é ignorado onde não se aplica
b = db.add_dice_effect(k, "bonus", 3, 1, True, None, "9", p21)
assert e() == [("vantagem", None, 2, 0, "boa noite"), ("bonus", 3, 1, 1, None)] and [r["id"] for r in db.get_dice_effects(k, p21)] == [a, b]
db.use_dice_effects([a], p21); assert e() == [("vantagem", None, 1, 0, "boa noite"), ("bonus", 3, 1, 1, None)]
db.use_dice_effects([a, b], p21); assert e() == []                                                          # sem uso, o efeito some
c = db.add_dice_effect(k, "minimo", 10, 5, False, None, "9", p21); db.use_dice_effects([c, c, c], p21); assert e() == [("minimo", 10, 2, 0, None)]     # um id repetido gasta várias vezes
db.use_dice_effects([c, c, c, c], p21); assert e() == [] and db.get_dice_effects(k, p21) == []            # gastar além do que tem não passa de zero
other = db.create_character("2", "Outro", path=p21)["id"]; db.add_dice_effect(other, "fixo", 20, 1, False, None, "9", p21)
db.add_dice_effect(k, "penalidade", 2, 3, False, None, "9", p21); db.add_dice_effect(k, "maximo", 15, 1, False, None, "9", p21)
assert db.clear_dice_effects(k, p21) == 2 and e() == [] and len(db.get_dice_effects(other, p21)) == 1          # limpar só mexe no personagem dele
assert db.clear_dice_effects(k, p21) == 0
for args in (("explosivo", 1, 1), ("bonus", None, 1), ("bonus", 0, 1), ("bonus", 21, 1), ("fixo", "x", 1), ("vantagem", None, 0), ("vantagem", None, 21)):
    try: db.add_dice_effect(k, args[0], args[1], args[2], False, None, "9", p21); raise SystemExit(f"deveria recusar {args}")
    except ValueError: pass
assert e() == []                                                                                             # as recusas não gravaram nada
db.add_dice_effect(other, "vantagem", None, 1, False, None, "9", p21); db.delete_character(other, "9", "Mestre", p21); assert db.get_dice_effects(other, p21) == []      # excluir o personagem leva os efeitos
print("21. efeitos de sorte OK")

# ---------- 22. migração v8 -> v9: o banco que está no Railway ganha a coluna e a tabela sem perder nada ----------
p8 = novo_banco("v8_real.db")
with sqlite3.connect(p8) as cn:
    cn.execute("ALTER TABLE characters DROP COLUMN class_ability"); cn.execute("DROP TABLE dice_effects")
    cn.execute("INSERT INTO characters (user_id, name, name_key, created_at, level, xp, race, race_roll, class_name)"
               " VALUES ('7', 'Kairon Flagon', 'kairon flagon', '2026-09-18T00:00:00+00:00', 4, 6000, 'Vampiro', 90, 'Mestre de Forja')")
    cn.execute("PRAGMA user_version = 8")
with sqlite3.connect(p8) as cn:
    assert "class_ability" not in {r[1] for r in cn.execute("PRAGMA table_info(characters)")}
    assert not cn.execute("SELECT 1 FROM sqlite_master WHERE name = 'dice_effects'").fetchone()               # de fato é o formato antigo
db.init_db(p8); db.init_db(p8)                                                                              # duas vezes: idempotente
with sqlite3.connect(p8) as cn:
    assert cn.execute("PRAGMA user_version").fetchone()[0] == 13      # o v8 também chega direto na versão atual
    assert "class_ability" in {r[1] for r in cn.execute("PRAGMA table_info(characters)")} and cn.execute("SELECT COUNT(*) FROM dice_effects").fetchone()[0] == 0
    linha = cn.execute("SELECT name, level, xp, race, race_roll, class_name, class_ability FROM characters").fetchone()
assert tuple(linha) == ("Kairon Flagon", 4, 6000, "Vampiro", 90, "Mestre de Forja", None)                    # nada mudou
k8 = db.find_character("7", "Kairon Flagon", p8); db.add_dice_effect(k8["id"], "vantagem", None, 1, False, None, "9", p8); assert len(db.get_dice_effects(k8["id"], p8)) == 1
print("22. migração v8 -> v9 OK")

# ---------- 23. vitais (Vida, Sanidade, Mana, Estamina) ----------
p23 = novo_banco("vitais.db")
vi = db.create_character("1", "Vital", path=p23)["id"]; outro = db.create_character("2", "Outro", path=p23)["id"]
assert db.get_vitals_lost(vi, p23) == {"vida": 0, "sanidade": 0, "mana": 0, "estamina": 0}                   # quem nunca mexeu não perdeu nada
db.set_vital_lost(vi, "vida", 12, p23); db.set_vital_lost(vi, "mana", 3, p23); db.set_vital_lost(outro, "vida", 99, p23)
assert db.get_vitals_lost(vi, p23) == {"vida": 12, "sanidade": 0, "mana": 3, "estamina": 0} and db.get_vitals_lost(outro, p23)["vida"] == 99
db.set_vital_lost(vi, "vida", 0, p23); assert db.get_vitals_lost(vi, p23)["vida"] == 0 and db.get_vitals_lost(vi, p23)["mana"] == 3
for args in (("coragem", 1), ("vida", -1), ("vida", "3"), ("vida", None)):
    try: db.set_vital_lost(vi, *args, path=p23); raise SystemExit(f"deveria recusar {args}")
    except ValueError: pass
db.reset_vitals(vi, p23); assert db.get_vitals_lost(vi, p23) == {"vida": 0, "sanidade": 0, "mana": 0, "estamina": 0} and db.get_vitals_lost(outro, p23)["vida"] == 99   # descansar só zera o dele
db.set_vital_lost(outro, "estamina", 4, p23); db.delete_character(outro, "9", "Mestre", p23); assert db.get_vitals_lost(outro, p23) == {k: 0 for k in rules.VITAL_KEYS}   # excluir leva as barras junto
print("23. vitais OK")

# ---------- 24. migração v9 -> v10 ----------
p9 = novo_banco("v9_real.db")
with sqlite3.connect(p9) as cn:
    cn.execute("DROP TABLE character_vitals")
    cn.execute("INSERT INTO characters (user_id, name, name_key, created_at, level, xp, race, class_name) VALUES ('7', 'Kairon Flagon', 'kairon flagon', '2026-09-18T00:00:00+00:00', 4, 6000, 'Vampiro', 'Mestre de Forja')")
    cn.execute("PRAGMA user_version = 9")
    assert not cn.execute("SELECT 1 FROM sqlite_master WHERE name = 'character_vitals'").fetchone()
db.init_db(p9); db.init_db(p9)
with sqlite3.connect(p9) as cn:
    assert cn.execute("PRAGMA user_version").fetchone()[0] == 13 and cn.execute("SELECT COUNT(*) FROM character_vitals").fetchone()[0] == 0
    assert tuple(cn.execute("SELECT name, level, xp, race, class_name FROM characters").fetchone()) == ("Kairon Flagon", 4, 6000, "Vampiro", "Mestre de Forja")
k9 = db.find_character("7", "Kairon Flagon", p9); db.set_vital_lost(k9["id"], "vida", 5, p9); assert db.get_vitals_lost(k9["id"], p9)["vida"] == 5
print("24. migração v9 -> v10 OK")

# ---------- 25. perícias ----------
p25 = novo_banco("pericias.db")
sk = db.create_character("1", "Skill", path=p25)["id"]; sk2 = db.create_character("2", "Skill2", path=p25)["id"]
assert db.get_skills(sk, p25) == {}
db.set_skill_points(sk, "Luta", 3, p25); db.set_skill_points(sk, "Percepção", 7, p25); db.set_skill_points(sk2, "Luta", 1, p25)
assert db.get_skills(sk, p25) == {"Luta": 3, "Percepção": 7} and db.get_skills(sk2, p25) == {"Luta": 1}
db.set_skill_points(sk, "Luta", 5, p25); assert db.get_skills(sk, p25)["Luta"] == 5 and len(db.get_skills(sk, p25)) == 2          # mudar não duplica
db.set_skill_points(sk, "Luta", 0, p25); assert db.get_skills(sk, p25) == {"Percepção": 7}                                       # zero tira da lista
for args in (("Voar", 1), ("Luta", -1), ("Luta", 21), ("Luta", "3"), ("Luta", None)):
    try: db.set_skill_points(sk, *args, path=p25); raise SystemExit(f"deveria recusar {args}")
    except ValueError: pass
db.delete_character(sk2, "9", "Mestre", p25); assert db.get_skills(sk2, p25) == {} and db.get_skills(sk, p25) == {"Percepção": 7}
print("25. perícias OK")

# ---------- 26. habilidades criadas pelos jogadores ----------
p26 = novo_banco("habilidades.db")
h1 = db.create_character("1", "Kairon", path=p26)["id"]; h2 = db.create_character("2", "Akari", path=p26)["id"]
a1 = db.create_ability(h1, "Bola de Fogo", "Uma bola de fogo.", "2d8 de dano", p26); a2 = db.create_ability(h1, "Cura", "Fecha feridas.", "cura 1d6", p26); a3 = db.create_ability(h2, "Gelo", "Congela.", "congela", p26)
ab = db.get_ability(a1, p26); assert (ab["name"], ab["description"], ab["effect_text"], ab["status"], ab["cost_resource"], ab["cost_amount"], ab["roll_dice"], ab["master_note"]) == ("Bola de Fogo", "Uma bola de fogo.", "2d8 de dano", "pendente", None, 0, None, None)
assert [a["id"] for a in db.list_abilities(h1, p26)] == [a1, a2] and db.count_active_abilities(h1, p26) == 2 and db.get_ability(99999, p26) is None
db.save_ability_decision(a1, "aprovada", "mana", 15, "dano", "2d8", "forca", None, "9", p26)
ab = db.get_ability(a1, p26); assert (ab["status"], ab["cost_resource"], ab["cost_amount"], ab["roll_kind"], ab["roll_dice"], ab["roll_attribute"], ab["decided_by"]) == ("aprovada", "mana", 15, "dano", "2d8", "forca", "9") and ab["decided_at"]
db.save_ability_decision(a2, "ajuste", None, 10, None, None, None, "Muito forte", "9", p26)                                       # custo sem recurso: não grava custo
ab = db.get_ability(a2, p26); assert (ab["status"], ab["cost_resource"], ab["cost_amount"], ab["master_note"]) == ("ajuste", None, 0, "Muito forte")
db.save_ability_decision(a2, "ajuste", "mana", 0, None, None, None, "Muito forte", "9", p26); assert db.get_ability(a2, p26)["cost_resource"] is None      # recurso sem valor: também não
fila = db.list_ability_queue(25, p26); assert [(a["id"], a["status"]) for a in fila] == [(a3, "pendente"), (a2, "ajuste"), (a1, "aprovada")]       # pendentes primeiro, depois ajuste, depois aprovadas
assert (fila[0]["character_name"], fila[0]["user_id"]) == ("Akari", "2") and len(db.list_ability_queue(2, p26)) == 2
db.save_ability_decision(a3, "recusada", None, 0, None, None, None, None, "9", p26); assert [a["id"] for a in db.list_ability_queue(25, p26)] == [a2, a1] and db.count_active_abilities(h2, p26) == 0     # recusada sai da fila e do limite
db.update_ability_text(a1, "Bola Grande", "Maior.", "3d8", back_to_pending=False, path=p26); ab = db.get_ability(a1, p26); assert (ab["name"], ab["status"], ab["roll_dice"]) == ("Bola Grande", "aprovada", "2d8")   # o mestre corrige sem mexer no status
db.update_ability_text(a2, "Cura Boa", "Mais.", "cura 2d6", back_to_pending=True, path=p26); ab = db.get_ability(a2, p26); assert (ab["name"], ab["status"], ab["master_note"]) == ("Cura Boa", "pendente", None)    # o jogador mexendo volta pra fila
for args in (("explodida", None, 0, None, None, None, None, "9"), ("aprovada", "coragem", 1, None, None, None, None, "9"), ("aprovada", "mana", 1, "veneno", "1d6", None, None, "9"),
             ("aprovada", "mana", 1, "dano", "1d6", "sorte", None, "9"), ("aprovada", "mana", -1, None, None, None, None, "9"), ("aprovada", "mana", 1000, None, None, None, None, "9")):
    try: db.save_ability_decision(a1, *args, path=p26); raise SystemExit(f"deveria recusar {args}")
    except ValueError: pass
assert db.get_ability(a1, p26)["status"] == "aprovada" and db.get_ability(a1, p26)["cost_amount"] == 15                         # as recusas não gravaram nada
db.delete_ability(a2, p26); assert db.get_ability(a2, p26) is None and [a["id"] for a in db.list_abilities(h1, p26)] == [a1]
db.delete_character(h1, "9", "Mestre", p26); assert db.list_abilities(h1, p26) == []                                              # excluir o personagem leva as habilidades
print("26. habilidades criadas OK")

# ---------- 27. migração v10 -> v11 ----------
p10 = novo_banco("v10_real.db")
with sqlite3.connect(p10) as cn:
    cn.execute("DROP TABLE character_skills"); cn.execute("DROP TABLE custom_abilities")
    cn.execute("INSERT INTO characters (user_id, name, name_key, created_at, level, xp, race, class_name) VALUES ('7', 'Kairon Flagon', 'kairon flagon', '2026-09-18T00:00:00+00:00', 4, 6000, 'Vampiro', 'Mestre de Forja')")
    cn.execute("PRAGMA user_version = 10")
    assert not cn.execute("SELECT 1 FROM sqlite_master WHERE name IN ('character_skills', 'custom_abilities')").fetchone()
db.init_db(p10); db.init_db(p10)
with sqlite3.connect(p10) as cn:
    assert cn.execute("PRAGMA user_version").fetchone()[0] == 13 and cn.execute("SELECT COUNT(*) FROM character_skills").fetchone()[0] == 0 and cn.execute("SELECT COUNT(*) FROM custom_abilities").fetchone()[0] == 0
    assert tuple(cn.execute("SELECT name, level, xp, race, class_name FROM characters").fetchone()) == ("Kairon Flagon", 4, 6000, "Vampiro", "Mestre de Forja")
k10 = db.find_character("7", "Kairon Flagon", p10); db.set_skill_points(k10["id"], "Luta", 4, p10); assert db.get_skills(k10["id"], p10) == {"Luta": 4}
print("27. migração v10 -> v11 OK")

# ---------- 28. a escolha de vantagem da classe, e a migração v11 -> v12 ----------
p28 = novo_banco("picks.db")
pk = db.create_character("1", "Pick", path=p28)["id"]; pk2 = db.create_character("2", "Pick2", path=p28)["id"]
assert db.get_skill_picks(pk, p28) == []
db.set_skill_picks(pk, ["Luta"], p28); db.set_skill_picks(pk2, ["Furtividade", "Medicina"], p28)
assert db.get_skill_picks(pk, p28) == ["Luta"] and db.get_skill_picks(pk2, p28) == ["Furtividade", "Medicina"]
db.set_skill_picks(pk, ["Pontaria", "Religião"], p28); assert db.get_skill_picks(pk, p28) == ["Pontaria", "Religião"]            # troca tudo, não soma
db.set_skill_picks(pk, ["Luta", "Luta"], p28); assert db.get_skill_picks(pk, p28) == ["Luta"]
try: db.set_skill_picks(pk, ["Voar"], p28); raise SystemExit("deveria recusar")
except ValueError: pass
assert db.get_skill_picks(pk, p28) == ["Luta"]                                                                   # recusou antes de apagar
db.set_skill_picks(pk, [], p28); assert db.get_skill_picks(pk, p28) == [] and db.get_skill_picks(pk2, p28) == ["Furtividade", "Medicina"]
db.delete_character(pk2, "9", "Mestre", p28); assert db.get_skill_picks(pk2, p28) == []
p11 = novo_banco("v11_real.db")
with sqlite3.connect(p11) as cn:
    cn.execute("DROP TABLE character_skill_picks")
    cn.execute("INSERT INTO characters (user_id, name, name_key, created_at, level, xp, race, class_name) VALUES ('7', 'Kairon Flagon', 'kairon flagon', '2026-09-18T00:00:00+00:00', 4, 6000, 'Vampiro', 'Mestre de Forja')")
    cn.execute("PRAGMA user_version = 11")
db.init_db(p11); db.init_db(p11)
with sqlite3.connect(p11) as cn:
    assert cn.execute("PRAGMA user_version").fetchone()[0] == 13 and cn.execute("SELECT COUNT(*) FROM character_skill_picks").fetchone()[0] == 0
    assert tuple(cn.execute("SELECT name, level, class_name FROM characters").fetchone()) == ("Kairon Flagon", 4, "Mestre de Forja")
print("28. escolha de vantagem e migração v11 -> v12 OK")

# ---------- 29. NPCs e criaturas ----------
p29 = novo_banco("npcs.db")
n1 = db.create_npc("4", "  Guarda do Rei ", "npc", 3, {"forca": 4, "vitalidade": 3}, ["Mercenário"], "Humano", "Armadura pesada.", {"Luta": 5, "Percepção": 2}, p29)
n = db.get_npc(n1, p29)
assert (n["name"], n["kind"], n["species"], n["level"], n["forca"], n["vitalidade"], n["destreza"], n["classes"], n["notes"], n["created_by"]) == ("Guarda do Rei", "npc", "Humano", 3, 4, 3, 0, "Mercenário", "Armadura pesada.", "4") and n["created_at"] and n["updated_at"] >= n["created_at"]
assert db.get_npc_skills(n1, p29) == {"Luta": 5, "Percepção": 2} and db.get_npc_lost(n1, p29) == {"vida": 0, "sanidade": 0, "mana": 0, "estamina": 0} and db.get_npc(99999, p29) is None
n2 = db.create_npc("4", "Cerberus", "criatura", 8, {a: 6 for a in rules.ATTRIBUTES}, ["Caçador", "Mercenário", "Feiticeiros"], path=p29)
assert [x["name"] for x in db.list_npcs(path=p29)] == ["Cerberus", "Guarda do Rei"] and [x["name"] for x in db.list_npcs("criatura", path=p29)] == ["Cerberus"] and len(db.list_npcs(limit=1, path=p29)) == 1 and db.count_npcs(p29) == 2
db.update_npc(n1, p29, name="Capitão", level=5, alma=99, bonus_vida=50, classes="Mercenário,Caçador", notes="")
n = db.get_npc(n1, p29); assert (n["name"], n["level"], n["alma"], n["bonus_vida"], n["classes"], n["notes"]) == ("Capitão", 5, 99, 50, "Mercenário,Caçador", "") and db.get_npc(n2, p29)["name"] == "Cerberus"    # só mexe nos campos dados
db.update_npc(n1, p29); assert db.get_npc(n1, p29)["name"] == "Capitão"                                           # sem campos, nada acontece
for campos in ({"name": ""}, {"name": "x" * 61}, {"kind": "deus"}, {"level": 0}, {"level": 11}, {"level": "3"}, {"forca": -1}, {"forca": 100}, {"classes": "Paladino"}, {"classes": "Caçador,Caçador"},
               {"classes": "Caçador,Clérigo,Ladrão,Sábio"}, {"bonus_vida": 10000}, {"bonus_mana": -1000}, {"notes": "n" * 1501}, {"species": "e" * 41}, {"lost_vida": 3}, {"apelido": "x"}):
    try: db.update_npc(n1, p29, **campos); raise SystemExit(f"deveria recusar {campos}")
    except ValueError: pass
assert db.get_npc(n1, p29)["name"] == "Capitão" and db.get_npc(n1, p29)["level"] == 5                             # as recusas não gravaram nada
db.set_npc_lost(n1, "vida", 12, p29); db.set_npc_lost(n1, "mana", 3, p29); assert db.get_npc_lost(n1, p29) == {"vida": 12, "sanidade": 0, "mana": 3, "estamina": 0} and db.get_npc_lost(n2, p29)["vida"] == 0
for args in (("coragem", 1), ("vida", -1), ("vida", "3")):
    try: db.set_npc_lost(n1, *args, path=p29); raise SystemExit(f"deveria recusar {args}")
    except ValueError: pass
db.reset_npc_lost(n1, p29); assert db.get_npc_lost(n1, p29) == {k: 0 for k in rules.VITAL_KEYS}
db.set_npc_skills(n1, {"Luta": 30, "Tática": 0, "Furtividade": 4}, p29); assert db.get_npc_skills(n1, p29) == {"Luta": 30, "Furtividade": 4}        # troca tudo; 0 sai
for ruim in ({"Voar": 1}, {"Luta": 31}, {"Luta": -1}, {"Luta": "2"}):
    try: db.set_npc_skills(n1, ruim, p29); raise SystemExit(f"deveria recusar {ruim}")
    except ValueError: pass
assert db.get_npc_skills(n1, p29) == {"Luta": 30, "Furtividade": 4}
for ruim in (dict(name="", kind="npc"), dict(name="A", kind="x"), dict(name="A", level=11)):
    try: db.create_npc("4", path=p29, **ruim); raise SystemExit(f"deveria recusar {ruim}")
    except ValueError: pass
assert db.count_npcs(p29) == 2
db.delete_npc(n1, p29); assert db.get_npc(n1, p29) is None and db.get_npc_skills(n1, p29) == {} and db.count_npcs(p29) == 1                                   # apagar leva as perícias junto
print("29. NPCs OK")

# ---------- 30. migração v12 -> v13 ----------
p12 = novo_banco("v12_real.db")
with sqlite3.connect(p12) as cn:
    cn.execute("DROP TABLE npcs"); cn.execute("DROP TABLE npc_skills")
    cn.execute("INSERT INTO characters (user_id, name, name_key, created_at, level, xp, race, class_name) VALUES ('7', 'Kairon Flagon', 'kairon flagon', '2026-09-18T00:00:00+00:00', 4, 6000, 'Vampiro', 'Mestre de Forja')")
    cn.execute("PRAGMA user_version = 12")
db.init_db(p12); db.init_db(p12)
with sqlite3.connect(p12) as cn:
    assert cn.execute("PRAGMA user_version").fetchone()[0] == 13 and cn.execute("SELECT COUNT(*) FROM npcs").fetchone()[0] == 0 and cn.execute("SELECT COUNT(*) FROM npc_skills").fetchone()[0] == 0
    assert tuple(cn.execute("SELECT name, level, class_name FROM characters").fetchone()) == ("Kairon Flagon", 4, "Mestre de Forja")
assert db.create_npc("4", "Novo", path=p12) and db.count_npcs(p12) == 1
print("30. migração v12 -> v13 OK")

print("\nTODOS OS TESTES DO BANCO PASSARAM")
