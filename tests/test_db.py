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
assert tabelas == {"rolls","characters","user_state","master_actions","character_ranks","xp_log","players","deleted_characters"}, tabelas
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
with sqlite3.connect(p4) as cn: assert cn.execute("PRAGMA user_version").fetchone()[0] == 5
db.set_class(1, "Caçador", p4); db.set_attributes(1, {"vitalidade": 3}, p4); assert db.attributes_of(db.get_character_by_id(1, p4))["vitalidade"] == 3   # já dá pra usar
print("6d. v4 -> v5 (com dados) OK")

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

print("\nTODOS OS TESTES DO BANCO PASSARAM")
