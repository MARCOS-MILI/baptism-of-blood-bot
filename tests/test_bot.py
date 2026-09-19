"""Testes dos comandos do bot com interações simuladas (não conecta no Discord).
Rodar da pasta do bot: python tests/test_bot.py"""
import asyncio
import contextlib
import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
for k in ("DB_PATH", "RAILWAY_VOLUME_MOUNT_PATH"):
    os.environ.pop(k, None)

import discord
from discord import app_commands

import bot
import db
import dice
import rules

tmp = tempfile.mkdtemp()
db.DB_PATH = os.path.join(tmp, "teste.db")
db.init_db()
run = asyncio.run


# ------------------------------- ferramentas de teste -------------------------------
def inter(uid, nome, roles=(), admin=False, manage=False):
    i = MagicMock()
    i.user = MagicMock(); i.user.id = uid; i.user.display_name = nome
    i.user.guild_permissions = NS(administrator=admin, manage_guild=manage)
    i.user.roles = [NS(name=r) for r in roles]
    i.guild_id = 999
    i.response.send_message = AsyncMock(); i.response.edit_message = AsyncMock(); i.response.is_done = MagicMock(return_value=False)
    i.followup.send = AsyncMock()
    i.namespace = NS()
    i.guild = NS(roles=[])
    return i

def alvo(uid, nome):
    m = MagicMock(); m.id = uid; m.display_name = nome; m.mention = f"<@{uid}>"
    return m

def sent(i):
    a, kw = i.response.send_message.call_args
    return (a[0] if a else kw.get("content")), kw

def txt(i):
    c, kw = sent(i); e = kw.get("embed")
    return (c or "") + ((" | " + (e.title or "") + " | " + (e.description or "") + " | " + " ; ".join(f"{f.name}={f.value}" for f in e.fields)) if e else "")

def desc(i): return sent(i)[1]["embed"].description
def titulo(i): return sent(i)[1]["embed"].title
def rodape(i): return sent(i)[1]["embed"].footer.text
def row(uid, nome): return db.find_character(str(uid), nome)
def historico_de(uid, nome=None):
    c = row(uid, nome) if nome else None
    return db.get_history(str(uid), 50, c["id"] if c else None)

@contextlib.contextmanager
def dados(*totais):
    """Força os resultados dos próximos dados e confere que ninguém rolou dado a mais ou a menos."""
    seq = list(totais); real = dice.roll
    def fake(notation):
        assert seq, "rolou mais dados do que o esperado"
        return dice.RollResult(notation, [seq.pop(0)], 0)
    dice.roll = fake
    try: yield
    finally:
        dice.roll = real
        assert not seq, f"sobraram dados que ninguém rolou: {seq}"

gm = inter(4, "Mestre Belmont", roles=["Mestre"])
def novo(uid, nome, personagem, quantos=1):
    """Jogador com um personagem criado."""
    u = inter(uid, nome); run(bot.personagem_criar.callback(u, personagem)); return u


# ============================ A. o que o Discord vai receber ============================
raiz = {c.name: c for c in bot.bot.tree.get_commands()}
assert set(raiz) == {"rolar","historico","magia_inicial","raca_inicial","classe_social","classe","atributos","minha_ficha","niveis","extrato_xp","rank","calcular_recursos","ajuda","help","personagem","mestre"}, sorted(raiz)
pay = {n: c.to_dict(bot.bot.tree) for n, c in raiz.items()}
opt = lambda cmd, nome: next(o for o in cmd["options"] if o["name"] == nome)
sub_ = lambda g, n: next(o for o in pay[g]["options"] if o["name"] == n)
assert sorted(o["name"] for o in pay["personagem"]["options"]) == ["criar","excluir","listar","usar"]
assert sorted(o["name"] for o in pay["mestre"]["options"]) == sorted(["apagar","atributos","corrigir_classe","corrigir_estado","corrigir_magia","corrigir_nivel","corrigir_raca","dar_xp","excluir_personagem","exportar","ficha","jogador","rank_pericia","upar","vagas"])
req = lambda opts: {o["name"] for o in opts if o.get("required")}
assert req(pay["rolar"]["options"]) == {"dado"} and req(pay["raca_inicial"].get("options", [])) == set()
assert req(sub_("mestre", "dar_xp")["options"]) == {"usuario", "quantidade"}
q = opt(sub_("mestre", "dar_xp"), "quantidade"); assert (q["min_value"], q["max_value"]) == (-50000, 50000)
up = sub_("mestre", "upar"); assert (opt(up, "niveis")["min_value"], opt(up, "niveis")["max_value"], opt(up, "niveis").get("required", False)) == (1, 9, False)
cn = sub_("mestre", "corrigir_nivel"); assert (opt(cn, "nivel")["min_value"], opt(cn, "nivel")["max_value"]) == (1, 10)
rk = sub_("mestre", "rank_pericia"); assert (opt(rk, "rank")["min_value"], opt(rk, "rank")["max_value"]) == (0, 10)
va = sub_("mestre", "vagas"); assert (opt(va, "extras")["min_value"], opt(va, "extras")["max_value"]) == (0, 7) and req(va["options"]) == {"usuario", "extras"}
assert req(sub_("mestre", "excluir_personagem")["options"]) == {"usuario", "personagem"} and opt(sub_("mestre", "excluir_personagem"), "personagem")["autocomplete"] is True
assert [c["value"] for c in opt(sub_("mestre", "corrigir_raca"), "raca")["choices"]] == ["Humano", "Vampiro", "Dhampir"]
assert [c["value"] for c in opt(sub_("mestre", "apagar"), "definicao")["choices"]] == ["magic_rank","race","social_class","todas"]
assert [c["value"] for c in opt(sub_("mestre", "corrigir_estado"), "estado")["choices"]] == ["1-alto","1-baixo","2","3"]
assert [c["value"] for c in opt(pay["rank"], "tipo")["choices"]] == ["personagens", "jogadores"] and not opt(pay["rank"], "tipo").get("required")
assert (opt(pay["rank"], "limite")["min_value"], opt(pay["rank"], "limite")["max_value"]) == (3, 25)
cr = pay["calcular_recursos"]; assert req(cr["options"]) == {"classe","vitalidade","forca","vontade","alma"}
assert [c["value"] for c in opt(cr, "classe")["choices"]] == ["Nenhuma","Caçador","Feiticeiros","Ladrão","Mestre de Forja","Mundano","Sábio"]
assert pay["mestre"].get("dm_permission") is False or pay["mestre"].get("contexts") == [0]
at = pay["atributos"]; assert [o["name"] for o in at["options"]] == ["forca","destreza","vitalidade","razao","vontade","alma","personagem"] and req(at["options"]) == set()
assert all((opt(at, a)["min_value"], opt(at, a)["max_value"]) == (0, 20) for a in ("forca","destreza","vitalidade","razao","vontade","alma")) and opt(at, "personagem")["autocomplete"] is True
assert [c["value"] for c in opt(pay["classe"], "classe")["choices"]] == ["Caçador","Feiticeiros","Ladrão","Mestre de Forja","Mundano","Sábio"] and req(pay["classe"]["options"]) == {"classe"}
ma = sub_("mestre", "atributos"); assert req(ma["options"]) == {"usuario"} and all((opt(ma, a)["min_value"], opt(ma, a)["max_value"]) == (0, 30) for a in ("forca","alma"))
mc = sub_("mestre", "corrigir_classe"); assert req(mc["options"]) == {"usuario", "classe"} and [c["value"] for c in opt(mc, "classe")["choices"]] == ["Caçador","Feiticeiros","Ladrão","Mestre de Forja","Mundano","Sábio"]
assert not sub_("mestre", "exportar").get("options")
def walk(d, p=""):
    for o in d.get("options", []):
        if "description" in o: assert 1 <= len(o["description"]) <= 100, (p + o["name"], len(o["description"]))
        walk(o, p + o["name"] + ".")
for n, d in pay.items(): assert 1 <= len(d["description"]) <= 100, n; walk(d, n + ".")
assert isinstance(bot.bot.tree, bot.Arvore)
print("A. payload dos comandos OK")


# ============================ B. fluxo básico (personagens, sorteios, ficha) ============================
marcos = inter(1, "Marcos")
run(bot.rolar.callback(marcos, "1d20+3", None, None)); assert "Marcos rolou 1d20+3" in txt(marcos)      # sem personagem, rolar funciona
run(bot.magia_inicial.callback(marcos, None)); assert "personagem criar" in txt(marcos) and sent(marcos)[1]["ephemeral"]
run(bot.personagem_criar.callback(marcos, "  Kairon   Flagon ")); assert "Kairon Flagon" in txt(marcos) and "(1 de 3 vagas)" in txt(marcos)
run(bot.personagem_criar.callback(marcos, "kairon flagon")); assert "já tem" in txt(marcos) and "**Kairon Flagon**" in txt(marcos)
run(bot.personagem_criar.callback(marcos, "X")); assert "entre 2 e 60" in txt(marcos)
run(bot.personagem_criar.callback(marcos, "Akari Amaya")); run(bot.personagem_criar.callback(marcos, "Charles de Flagon"))
run(bot.personagem_usar.callback(marcos, "kairon FLAGON")); assert "Kairon Flagon" in txt(marcos)
run(bot.personagem_usar.callback(marcos, "Fantasma")); assert "Não achei" in txt(marcos)
run(bot.rolar.callback(marcos, "1d20", "ataque", None)); assert "Kairon Flagon rolou 1d20" in txt(marcos)
run(bot.rolar.callback(marcos, "1d6", None, "Akari Amaya")); assert "Akari Amaya rolou 1d6" in txt(marcos)
run(bot.rolar.callback(marcos, "1d6", None, "Fantasma")); assert "Não achei" in txt(marcos)
run(bot.rolar.callback(marcos, "abc", None, None)); assert "inválida" in txt(marcos)
run(bot.magia_inicial.callback(marcos, None)); assert "Magia Inicial de Kairon Flagon" in txt(marcos)
run(bot.magia_inicial.callback(marcos, None)); assert "já tem Rank de Magia" in txt(marcos)
with dados(96): run(bot.raca_inicial.callback(marcos, None))                                                # 96 é Dhampir
assert "Raça de Kairon Flagon" in txt(marcos) and "Raça: **Dhampir**" in txt(marcos) and row(1, "Kairon Flagon")["race"] == "Dhampir"
run(bot.raca_inicial.callback(marcos, None)); assert "já tem Raça" in txt(marcos)
run(bot.raca_inicial.callback(marcos, "Akari Amaya")); assert "Raça de Akari Amaya" in txt(marcos)
run(bot.minha_ficha.callback(marcos, None)); assert "Ficha de Kairon Flagon" in txt(marcos) and "1d100:" in txt(marcos) and "Dhampir" in txt(marcos)
run(bot.minha_ficha.callback(marcos, "Charles de Flagon")); assert "ainda não definido" in txt(marcos)
run(bot.personagem_listar.callback(marcos)); assert "▶️ **Kairon Flagon** · nível 1 · 0 XP" in txt(marcos) and rodape(marcos).endswith("vagas usadas: 3 de 3")
alvo1 = alvo(1, "Marcos")
run(bot.historico.callback(marcos, None, 10, None)); geral = txt(marcos); assert "raca_inicial" in geral and "magia_inicial" in geral
run(bot.historico.callback(marcos, alvo1, 25, "Akari Amaya")); assert "Histórico de Akari Amaya" in txt(marcos) and "ataque" not in txt(marcos)
run(bot.historico.callback(marcos, alvo1, 10, "Fantasma")); assert "não tem nenhum personagem" in txt(marcos)
run(bot.historico.callback(marcos, alvo1, 10, "Charles de Flagon")); assert "Nenhuma rolagem" in txt(marcos)
# horário: em vez de UTC seco, vai a marcação do Discord, que cada um vê no próprio fuso
run(bot.historico.callback(marcos, alvo1, 3, "Akari Amaya")); v = sent(marcos)[1]["embed"].fields[0].value
iso = db.get_history("1", 50, row(1, "Akari Amaya")["id"])[0]["created_at"]; ep = int(datetime.fromisoformat(iso).timestamp())
assert v.startswith(f"<t:{ep}:d> <t:{ep}:t>") and "UTC" not in v
assert bot._quando("lixo").endswith("UTC") and bot._quando("2026-09-18T20:00:00+00:00") == "<t:1789761600:d> <t:1789761600:t>"
print("B. fluxo básico OK")


# ============================ C. mestre: permissão e correções ============================
assert bot._eh_mestre(inter(2,"Zé", admin=True)) and bot._eh_mestre(inter(2,"Zé", manage=True))
assert bot._eh_mestre(inter(2,"Zé", roles=["mestre"])) and not bot._eh_mestre(inter(2,"Zé", roles=["Jogador"])) and not bot._eh_mestre(inter(2,"Zé"))
todos = list(bot.mestre_grupo.commands); assert len(todos) == 15
for c in todos:                                                     # TODOS os comandos de mestre barram quem não é mestre
    p = inter(3, "Intruso")
    assert run(c._check_can_run(p)) is False, c.name
    try: run(c._invoke_with_namespace(p, NS())); raise SystemExit(f"/mestre {c.name} executou pra não-mestre")
    except app_commands.CheckFailure: pass
    assert run(c._check_can_run(inter(4, "Mestre", roles=["Mestre"]))) is True
e = inter(3, "Intruso"); e.command = bot.mestre_grupo.get_command("apagar")
run(bot.on_app_command_error(e, app_commands.CheckFailure())); assert "só pra mestre" in txt(e) and sent(e)[1]["ephemeral"]
jogador1 = alvo(1, "Marcos")
run(bot.mestre_apagar.callback(gm, jogador1, "race", None)); assert "apagou a Raça de **Kairon Flagon**" in desc(gm) and "Antes era: Raça: Dhampir" in desc(gm)
assert sent(gm)[1]["content"] == "<@1>" and sent(gm)[1]["allowed_mentions"].users == [jogador1]
run(bot.mestre_apagar.callback(gm, jogador1, "race", None)); assert "nada definido" in txt(gm)
with dados(1): run(bot.raca_inicial.callback(marcos, None))
assert row(1, "Kairon Flagon")["race"] == "Humano"                                                         # conseguiu rolar de novo
run(bot.mestre_corrigir_raca.callback(gm, jogador1, "Dhampir", None)); assert "**Humano** → **Dhampir**" in txt(gm)
run(bot.minha_ficha.callback(marcos, None)); assert "definido por um mestre" in txt(marcos)
run(bot.mestre_corrigir_magia.callback(gm, jogador1, "Mítico", "Charles de Flagon")); assert "Charles de Flagon" in desc(gm)
run(bot.mestre_apagar.callback(gm, jogador1, "todas", "Charles de Flagon")); assert "o Rank de Magia de **Charles de Flagon**" in desc(gm) and "Raça" not in desc(gm)
run(bot.mestre_apagar.callback(gm, jogador1, "magic_rank", "Fantasma")); assert "não tem nenhum personagem chamado" in txt(gm)
run(bot.mestre_apagar.callback(gm, alvo(555, "Novato"), "todas", None)); assert "ainda não tem personagem" in txt(gm)
with sqlite3.connect(db.DB_PATH) as cn:
    acoes = [(a[0], a[1]) for a in cn.execute("SELECT action, detail FROM master_actions ORDER BY id")]
assert [a[0] for a in acoes] == ["apagar", "corrigir_race", "corrigir_magic_rank", "apagar"] and acoes[0][1] == "Raça: Dhampir"
ac = inter(1, "Marcos"); ch = run(bot._autocomplete_personagem(ac, "fla"))
assert {c.name for c in ch} == {"Kairon Flagon", "Charles de Flagon"}
ac.namespace = NS(usuario=NS(id=1)); assert len(run(bot._autocomplete_personagem(ac, ""))) == 3
ac.namespace = NS(usuario=NS(id=12345)); assert run(bot._autocomplete_personagem(ac, "")) == []
ac.namespace = NS(usuario="lixo-parcial"); assert len(run(bot._autocomplete_personagem(ac, ""))) == 3
print("C. mestre e correções OK")


# ============================ D. classe social ============================
p1 = novo(10, "Ana", "Ana Camponesa")
with dados(50): run(bot.classe_social.callback(p1, None))
assert "3º Estado (Povo)" in txt(p1) and "Outro 1d100" not in txt(p1) and "content" not in sent(p1)[1] and [h["purpose"] for h in historico_de(10)] == ["classe_social"]
with dados(): run(bot.classe_social.callback(p1, None))
assert "já tem Classe Social" in txt(p1) and sent(p1)[1]["ephemeral"]
for n, esperado in [(80, "3º Estado (Povo)"), (81, "2º Estado (Nobreza)"), (91, "2º Estado (Nobreza)")]:
    u = novo(20 + n, f"J{n}", f"Fulano {n}")
    with dados(n): run(bot.classe_social.callback(u, None))
    assert esperado in txt(u) and len(historico_de(20 + n)) == 1
for n1, n2, clero in [(92, 49, "Baixo Clero"), (92, 50, "Alto Clero"), (99, 100, "Alto Clero"), (95, 1, "Baixo Clero")]:
    u = novo(300 + n1 + n2, "Clerigo", "Padre Teste")
    with dados(n1, n2): run(bot.classe_social.callback(u, None))
    assert "1º Estado (Clero)" in txt(u) and f"Clero: **{clero}**" in txt(u) and f"Outro 1d100 = **{n2}**" in txt(u)
    c = row(300 + n1 + n2, "Padre Teste"); assert (c["social_class_roll"], c["clergy"], c["clergy_roll"]) == (n1, clero, n2)
    assert [(h["purpose"], h["total"]) for h in reversed(historico_de(300 + n1 + n2))] == [("classe_social", n1), ("clero", n2)]
mestre_papel = NS(id=555, name="Mestre", mention="<@&555>")
m100 = novo(40, "Sortudo", "Raro Demais"); m100.guild = NS(roles=[NS(id=1, name="Jogador", mention="<@&1>"), mestre_papel])
with dados(100): run(bot.classe_social.callback(m100, None))
kw = sent(m100)[1]
assert "Quem decide o Estado desse personagem é o mestre" in txt(m100) and "Estado:" not in txt(m100) and kw["content"] == "<@&555>" and kw["allowed_mentions"].roles == [mestre_papel]
c = row(40, "Raro Demais"); assert (c["social_class"], c["social_class_roll"], c["clergy"]) == (dice.SOCIAL_CLASS_MASTER, 100, None) and len(historico_de(40)) == 1
with dados(): run(bot.classe_social.callback(m100, None))
assert "tirou 100" in txt(m100)
run(bot.minha_ficha.callback(m100, None)); assert "aguardando o mestre" in txt(m100)
sem = novo(41, "Sortuda", "Outra Rara")
with dados(100): run(bot.classe_social.callback(sem, None))
assert "content" not in sent(sem)[1] and "Resultado especial" in txt(sem)                                   # sem cargo Mestre: não marca ninguém
dm = novo(42, "DM", "Solitário"); dm.guild = None
with dados(100): run(bot.classe_social.callback(dm, None))
assert "Resultado especial" in txt(dm)                                                                       # em DM não quebra
a40 = alvo(40, "Sortudo")
run(bot.mestre_corrigir_estado.callback(gm, a40, "1-alto", None)); assert "aguardando o mestre" in txt(gm) and "1º Estado (Clero), Alto Clero" in txt(gm)
c = row(40, "Raro Demais"); assert (c["social_class"], c["social_class_roll"], c["clergy"], c["clergy_roll"]) == ("1º Estado", None, "Alto Clero", None)
run(bot.mestre_corrigir_estado.callback(gm, a40, "3", None)); c = row(40, "Raro Demais"); assert (c["social_class"], c["clergy"]) == ("3º Estado", None)
run(bot.mestre_apagar.callback(gm, a40, "social_class", None)); assert "apagou a Classe Social de **Raro Demais**" in desc(gm) and "`/classe_social`" in desc(gm)
z = novo(50, "Zé", "Zé Pleno")
with dados(10, 20, 30): run(bot.magia_inicial.callback(z, None)); run(bot.raca_inicial.callback(z, None)); run(bot.classe_social.callback(z, None))
run(bot.mestre_apagar.callback(gm, alvo(50, "Zé"), "todas", None)); d = desc(gm)
assert "o Rank de Magia, a Raça e a Classe Social" in d and "`/magia_inicial`, `/raca_inicial` e `/classe_social`" in d
print("D. classe social OK")


# ============================ E. XP, níveis e Disciplina ============================
sem = inter(59, "Sem Personagem")
run(bot.niveis.callback(sem, None)); d = desc(sem)
assert d.count("▫️") == 10 and "▶️" not in d and "45.000 XP" in d and "**máximo**" in d and "Disciplina a cada 2 níveis" in d and "+1 disciplina" not in d
assert not sent(sem)[1]["embed"].fields and sent(sem)[1]["ephemeral"]

xp = novo(60, "Nívea", "Nívea Nível"); a60 = alvo(60, "Nívea")
run(bot.niveis.callback(xp, None)); e = sent(xp)[1]["embed"]
assert "▶️ **Nível 1** · 0 XP" in e.description and "1.000 XP · +2 perícia · +1 atributo" in e.description
f = e.fields[0]; assert f.name == "Nívea Nível: nível 1/10" and "Nível 1: 0/1.000 XP" in f.value and "XP total: 0" in f.value and "Já ganhou: nada (ficha inicial)" in f.value
assert "Próximo, nível 2: +2 pontos de Perícia · +1 ponto de Atributo · 1 habilidade nova ou melhorada (faltam 1.000 XP)" in f.value
run(bot.niveis.callback(xp, "Fantasma")); assert "Não achei" in txt(xp)

# dar XP sem subir de nível
run(bot.mestre_dar_xp.callback(gm, a60, 250, "RP marcante", None)); kw = sent(gm)[1]
assert titulo(gm) == "✨ +250 XP para Nívea Nível" and "XP total: **250**" in desc(gm) and "Nível 1: 250/1.000 XP" in desc(gm) and "▰▰▱▱▱▱▱▱▱▱" in desc(gm)
assert "Motivo: RP marcante" in desc(gm) and rodape(gm) == "por Mestre Belmont" and kw["content"] == "<@60>" and kw["allowed_mentions"].users == [a60]
assert (row(60, "Nívea Nível")["xp"], row(60, "Nívea Nível")["level"]) == (250, 1)
run(bot.minha_ficha.callback(xp, None)); v = sent(xp)[1]["embed"].fields[0].value
assert v.startswith("1/10") and "XP total: 250" in v and "Faltam 750 pro nível 2" in v
# chegar em 1.000 sobe pro nível 2, com os ganhos
run(bot.mestre_dar_xp.callback(gm, a60, 750, None, None))
assert titulo(gm) == "⬆️ Nívea Nível subiu de nível! (+750 XP)" and "Nível **1** → **2**" in desc(gm)
assert "Ganhos: +2 pontos de Perícia · +1 ponto de Atributo · 1 habilidade nova ou melhorada" in desc(gm)
assert (row(60, "Nívea Nível")["level"], row(60, "Nívea Nível")["xp"]) == (2, 1000)
# 1.999 e 2.000 ainda são nível 2 (o 3 só vem aos 3.000)
run(bot.mestre_dar_xp.callback(gm, a60, 999, None, None)); assert "Ganhos" not in desc(gm) and row(60, "Nívea Nível")["level"] == 2
run(bot.mestre_dar_xp.callback(gm, a60, 1, None, None)); assert "Ganhos" not in desc(gm) and (row(60, "Nívea Nível")["level"], row(60, "Nívea Nível")["xp"]) == (2, 2000)
run(bot.mestre_dar_xp.callback(gm, a60, 1000, None, None)); assert "Nível **2** → **3**" in desc(gm) and "+2 pontos de Perícia" in desc(gm) and "Atributo" not in desc(gm)   # nível 3 é ímpar
# vários níveis de uma vez: 3.000 + 45.000 = 48.000, nível 10
run(bot.mestre_dar_xp.callback(gm, a60, 45000, "evento grande", None)); print("  ", titulo(gm), "|", desc(gm).splitlines()[3])
assert "Nível **3** → **10**" in desc(gm) and "+14 pontos de Perícia · +4 pontos de Atributo · 4 habilidades novas ou melhoradas" in desc(gm)   # níveis 4..10: 7x2 perícia, 4 pares
assert (row(60, "Nívea Nível")["level"], row(60, "Nívea Nível")["xp"]) == (10, 48000) and "Nível 10: máximo" in desc(gm)
# no nível 10 o XP continua contando, sem subir
run(bot.mestre_dar_xp.callback(gm, a60, 1000, None, None)); assert titulo(gm) == "✨ +1.000 XP para Nívea Nível" and row(60, "Nívea Nível")["xp"] == 49000 and row(60, "Nívea Nível")["level"] == 10
run(bot.minha_ficha.callback(xp, None)); v = sent(xp)[1]["embed"].fields[0].value; assert v.startswith("10/10") and "XP total: 49.000" in v and "Faltam" not in v
# tirar XP: derruba o nível quando cruza a fronteira, avisa, e não marca ninguém
run(bot.mestre_dar_xp.callback(gm, a60, -5000, "engano", None)); kw = sent(gm)[1]
assert titulo(gm) == "⬇️ Nívea Nível perdeu nível (-5.000 XP)" and "Nível **10** → **9**" in desc(gm) and "precisam ser ajustados" in desc(gm)
assert "content" not in kw and row(60, "Nívea Nível")["level"] == 9 and row(60, "Nívea Nível")["xp"] == 44000
# o XP nunca fica abaixo de zero; zero mudança não gera nada
u61 = novo(61, "Caio", "Caio Curto"); a61 = alvo(61, "Caio"); run(bot.mestre_dar_xp.callback(gm, a61, 100, None, None))
run(bot.mestre_dar_xp.callback(gm, a61, -500, None, None)); assert titulo(gm) == "🛠️ -100 XP em Caio Curto" and row(61, "Caio Curto")["xp"] == 0
run(bot.mestre_dar_xp.callback(gm, a61, -50, None, None)); assert "Nada mudou" in txt(gm) and sent(gm)[1]["ephemeral"]
run(bot.mestre_dar_xp.callback(gm, a61, 0, None, None)); assert "diferente de zero" in txt(gm) and sent(gm)[1]["ephemeral"]
run(bot.mestre_dar_xp.callback(gm, a61, 10, None, "Fantasma")); assert "não tem nenhum personagem chamado" in txt(gm)
run(bot.mestre_dar_xp.callback(gm, alvo(777, "Novato"), 10, None, None)); assert "ainda não tem personagem" in txt(gm)

# extrato do jogador: mais recente primeiro, com motivo, mestre e horário no fuso de quem lê
import re
run(bot.extrato_xp.callback(xp, None)); print("  extrato:", desc(xp).splitlines()[0][:90])
linhas = desc(xp).splitlines(); assert sent(xp)[1]["ephemeral"] and len(linhas) == 8
assert linhas[0].startswith("**-5.000 XP** · engano · por Mestre Belmont · ") and re.search(r"<t:\d+:d> <t:\d+:t>$", linhas[0])
assert "XP total: 44.000 · nível 9" in rodape(xp)
u62 = novo(62, "Vazio", "Sem Xp"); run(bot.extrato_xp.callback(u62, None)); assert "ainda não recebeu XP" in txt(u62) and sent(u62)[1]["ephemeral"]
# o extrato mostra só as 10 últimas, da mais nova pra mais antiga
for i in range(12): run(bot.mestre_dar_xp.callback(gm, a61, 10, f"entrada {i}", None))
run(bot.extrato_xp.callback(u61, None)); linhas = desc(u61).splitlines()
assert len(linhas) == 10 and linhas[0].startswith("**+10 XP** · entrada 11 ·") and linhas[-1].startswith("**+10 XP** · entrada 2 ·")

# upar = atalho que dá exatamente o XP que falta
u63 = novo(63, "Upa", "Upador"); a63 = alvo(63, "Upa")
run(bot.mestre_upar.callback(gm, a63, 1, None, "RP marcante")); assert titulo(gm) == "⬆️ Upador subiu de nível! (+1.000 XP)" and "Nível **1** → **2**" in desc(gm) and "Motivo: RP marcante" in desc(gm)
assert (row(63, "Upador")["level"], row(63, "Upador")["xp"]) == (2, 1000)
run(bot.mestre_dar_xp.callback(gm, a63, 500, None, None))                                     # 1.500: no meio do nível 2
run(bot.mestre_upar.callback(gm, a63, 1, None, None)); assert titulo(gm) == "⬆️ Upador subiu de nível! (+1.500 XP)" and row(63, "Upador")["xp"] == 3000 and row(63, "Upador")["level"] == 3
run(bot.mestre_upar.callback(gm, a63, 3, None, None)); assert "Nível **3** → **6**" in desc(gm) and row(63, "Upador")["xp"] == 15000
run(bot.mestre_upar.callback(gm, a63, 9, None, None)); assert "Nível **6** → **10**" in desc(gm) and row(63, "Upador")["xp"] == 45000   # trava no 10
run(bot.mestre_upar.callback(gm, a63, 1, None, None)); assert "nível máximo" in txt(gm) and sent(gm)[1]["ephemeral"] and row(63, "Upador")["xp"] == 45000
assert db.get_xp_log(row(63, "Upador")["id"], 1)[0]["reason"] == "atalho /mestre upar"
# corrigir nível: põe no começo do nível, com registro no extrato
run(bot.mestre_corrigir_nivel.callback(gm, a63, 7, None)); assert "Nível **10** → **7**" in desc(gm) and (row(63, "Upador")["level"], row(63, "Upador")["xp"]) == (7, 21000)
run(bot.mestre_corrigir_nivel.callback(gm, a63, 7, None)); assert "já está no nível 7" in txt(gm) and sent(gm)[1]["ephemeral"]
assert db.get_xp_log(row(63, "Upador")["id"], 1)[0]["reason"] == "correção de nível pra 7"
l63 = inter(63, "Upa"); run(bot.personagem_listar.callback(l63)); assert "nível 7 · 21.000 XP" in txt(l63)

# Disciplina: Vampiro e Dhampir ganham +1 ponto nos níveis pares; Humano não
for uid, raca, nome in [(64, "Dhampir", "Sangue Misto"), (65, "Vampiro", "Sangue Puro"), (66, "Humano", "Sangue Comum")]:
    u = novo(uid, f"J{uid}", nome); db.set_race(row(uid, nome)["id"], raca, 96)
    run(bot.niveis.callback(u, None)); d = desc(u); ficha = sent(u)[1]["embed"].fields[0].value
    if raca == "Humano":
        assert "+1 disciplina" not in d and "Disciplina" not in ficha and "pontos de Disciplina)" not in d
        assert "Vampiros e Dhampirs ganham também +1 ponto de Disciplina a cada 2 níveis." in d      # a nota explica pra quem não é vampiro
    else:
        assert d.count("+1 disciplina") == 5 and f"(com {rules.INITIAL_DISCIPLINE_POINTS[raca]} pontos de Disciplina)" in d
        assert "+5 pontos de Disciplina" in d and "+1 ponto de Disciplina (faltam 1.000 XP)" in ficha     # total do 1 ao 10 e o próximo nível
        assert "Vampiros e Dhampirs ganham também" not in d
    run(bot.mestre_dar_xp.callback(gm, alvo(uid, f"J{uid}"), 1000, None, None))
    assert ("+1 ponto de Disciplina" in desc(gm)) == (raca != "Humano"), (raca, desc(gm))
    run(bot.mestre_dar_xp.callback(gm, alvo(uid, f"J{uid}"), 2000, None, None))      # nível 3 (ímpar): sem disciplina
    assert "Disciplina" not in desc(gm)
print("E. XP, níveis e Disciplina OK")


# ============================ F. rank público por XP total (banco limpo) ============================
db.DB_PATH = os.path.join(tmp, "rank.db"); db.init_db()
r0 = inter(70, "Ana"); run(bot.rank.callback(r0, "personagens", 10)); assert "Ninguém ganhou XP ainda" in txt(r0) and sent(r0)[1]["ephemeral"]
ana = novo(70, "Ana", "Ana Alfa"); run(bot.personagem_criar.callback(ana, "Ana Beta"))
beto = novo(71, "Beto", "Beto Solo"); caio = novo(72, "Caio", "Caio Zero"); dani = novo(73, "Dani", "Dani Empata"); edu = novo(74, "Edu", "Edu Empata")
for tarefa in [(70, "Ana", 12300, "Ana Alfa"), (70, "Ana", 500, "Ana Beta"), (71, "Beto", 46000, "Beto Solo"), (73, "Dani", 500, "Dani Empata"), (74, "Edu", 500, "Edu Empata")]:
    run(bot.mestre_dar_xp.callback(gm, alvo(tarefa[0], tarefa[1]), tarefa[2], "teste", tarefa[3]))
# o nome do jogador vem do 'Arvore', que roda antes de todo comando de verdade
for uid, nome in [(70, "Ana"), (71, "Beto"), (73, "Dani"), (74, "Edu")]:
    assert run(bot.bot.tree.interaction_check(inter(uid, nome))) is True
assert db.get_player_names()["70"] == "Ana"
run(bot.rank.callback(ana, "personagens", 10)); linhas = desc(ana).splitlines(); print("  ", linhas)
assert not sent(ana)[1].get("ephemeral") and titulo(ana) == "🏆 Rank de XP: personagens"          # público
assert linhas[0] == "🥇 **Beto Solo** (Beto) · nível 10 · 46.000 XP" and linhas[1] == "🥈 **Ana Alfa** (Ana) · nível 5 · 12.300 XP"
assert linhas[2].startswith("🥉 **Ana Beta** (Ana) · nível 1 · 500 XP") and linhas[3].startswith("**4.** **Dani Empata**") and len(linhas) == 5
assert not any("Caio Zero" in l for l in linhas)                                                   # quem tem 0 XP não entra
assert rodape(ana) == "Seu melhor personagem: 2º (Ana Alfa)"
run(bot.rank.callback(ana, "jogadores", 10)); linhas = desc(ana).splitlines(); print("  ", linhas)
assert titulo(ana) == "🏆 Rank de XP: jogadores" and linhas[0] == "🥇 **Beto** · 46.000 XP · 1 personagem · melhor nível 10"
assert linhas[1] == "🥈 **Ana** · 12.800 XP · 2 personagens · melhor nível 5" and rodape(ana) == "Sua posição: 2º"     # soma dos personagens
run(bot.rank.callback(caio, "jogadores", 10)); assert sent(caio)[1]["embed"].footer.text is None      # sem XP, sem posição
run(bot.rank.callback(ana, "personagens", 3)); assert len(desc(ana).splitlines()) == 3                # o limite corta a lista
print("F. rank OK")


# ============================ G. limite de personagens, vagas extras e exclusão ============================
db.DB_PATH = os.path.join(tmp, "vagas.db"); db.init_db()
v80 = novo(80, "Vaga", "P1"); a80 = alvo(80, "Vaga")
run(bot.personagem_criar.callback(v80, "P2")); assert "(2 de 3 vagas)" in desc(v80)
run(bot.personagem_criar.callback(v80, "P3")); assert "(3 de 3 vagas)" in desc(v80)
run(bot.personagem_criar.callback(v80, "P4")); print("  limite:", txt(v80))
assert "Você já usa todas as suas vagas de personagem (3 de 3)" in txt(v80) and "/personagem excluir" in txt(v80) and sent(v80)[1]["ephemeral"]
assert row(80, "P4") is None and len(db.list_characters("80")) == 3
# outro jogador não é afetado, e o mestre também segue o limite (pode se dar vagas)
u81 = inter(81, "Outro"); run(bot.personagem_criar.callback(u81, "Solo")); assert "(1 de 3 vagas)" in desc(u81)
# vagas extras: o número é o TOTAL de extras, não soma
run(bot.mestre_vagas.callback(gm, a80, 2)); print("  vagas:", desc(gm).replace("\n", " "))
assert "**0** → **2**" in desc(gm) and "Agora são 5 vagas (3 padrão + 2 extras), 3 em uso." in desc(gm) and not sent(gm)[1].get("ephemeral")
run(bot.mestre_vagas.callback(gm, a80, 2)); assert "**2** → **2**" in desc(gm)                          # repetir não soma
run(bot.personagem_criar.callback(v80, "P4")); assert "(4 de 5 vagas)" in desc(v80)
run(bot.personagem_criar.callback(v80, "P5")); assert "(5 de 5 vagas)" in desc(v80)
run(bot.personagem_criar.callback(v80, "P6")); assert "(5 de 5)" in txt(v80) and row(80, "P6") is None
run(bot.mestre_vagas.callback(gm, a80, 1)); assert "**2** → **1**" in desc(gm) and "Agora são 4 vagas (3 padrão + 1 extra), 5 em uso." in desc(gm)   # tirar vaga não apaga personagem
assert len(db.list_characters("80")) == 5
run(bot.mestre_vagas.callback(gm, a80, 7)); assert "Agora são 10 vagas (3 padrão + 7 extras)" in desc(gm)   # teto de 10 personagens
lv = inter(80, "Vaga"); run(bot.personagem_listar.callback(lv)); assert "vagas usadas: 5 de 10" in rodape(lv)
with sqlite3.connect(db.DB_PATH) as cn:
    assert [r[0] for r in cn.execute("SELECT detail FROM master_actions WHERE action='vagas' ORDER BY id")] == ["extras 0 -> 2", "extras 2 -> 2", "extras 2 -> 1", "extras 1 -> 7"]

# exclusão pelo jogador: aviso, confirmação por botão, permanente, libera a vaga, rolagens ficam
run(bot.rolar.callback(v80, "1d20", "antes de morrer", "P2"))
run(bot.mestre_dar_xp.callback(gm, a80, 1200, "morre logo", "P2"))
db.set_skill_rank(row(80, "P2")["id"], "Forja", 3)
p2_id = row(80, "P2")["id"]

async def excluir_com_botoes():
    u = inter(80, "Vaga"); await bot.personagem_excluir.callback(u, "P2")
    kw = u.response.send_message.call_args.kwargs; view = kw["view"]
    assert isinstance(view, bot.ConfirmarExclusao) and kw["ephemeral"] and kw["embed"].title == "🗑️ Excluir P2?" and "pra sempre" in kw["embed"].description
    assert row(80, "P2") is not None                                             # só perguntou, ainda não apagou
    intruso = inter(81, "Intruso"); assert await view.interaction_check(intruso) is False and "Só quem pediu" in intruso.response.send_message.call_args.args[0]
    assert row(80, "P2") is not None
    cancela = inter(80, "Vaga"); assert await view.interaction_check(cancela) is True
    await view.cancelar.callback(cancela); assert "nada foi excluído" in cancela.response.edit_message.call_args.kwargs["content"] and row(80, "P2") is not None
    u2 = inter(80, "Vaga"); await bot.personagem_excluir.callback(u2, "P2"); view2 = u2.response.send_message.call_args.kwargs["view"]
    ok = inter(80, "Vaga"); await view2.confirmar.callback(ok)
    assert ok.response.edit_message.call_args.kwargs["content"] == "🗑️ **P2** foi excluído pra sempre."
    # tempo esgotado: só troca a mensagem, não apaga nada
    u3 = inter(80, "Vaga"); await bot.personagem_excluir.callback(u3, "P3"); view3 = u3.response.send_message.call_args.kwargs["view"]
    u3.edit_original_response = AsyncMock(); await view3.on_timeout()
    assert "Passou o tempo" in u3.edit_original_response.call_args.kwargs["content"] and row(80, "P3") is not None
    # um clique depois de já excluído não quebra
    de_novo = inter(80, "Vaga"); await view2.confirmar.callback(de_novo); assert "já tinha sido excluído" in de_novo.response.edit_message.call_args.kwargs["content"]
run(excluir_com_botoes())
assert row(80, "P2") is None and len(db.list_characters("80")) == 4 and db.count_deleted("80") == 1
assert db.get_xp_log(p2_id) == [] and db.get_skill_ranks(p2_id) == {}                       # ficha, extrato e ranks somem
h = [x for x in db.get_history("80", 50) if x["purpose"] == "antes de morrer"]
assert len(h) == 1 and h[0]["character_id"] is None and h[0]["character_name"] == "P2"      # a rolagem antiga fica no histórico
assert db.get_active_character("80")["name"] != "P2"
ex = inter(80, "Vaga"); run(bot.personagem_excluir.callback(ex, "P2")); assert "Não achei" in txt(ex)
run(bot.personagem_criar.callback(v80, "P2 Novo")); assert "vagas)" in desc(v80)                # a vaga foi liberada
# o rank também perde o XP do personagem excluído
assert all(r["name"] != "P2" for r in db.rank_characters())

# exclusão pelo mestre: confirmação, registro e aviso público pro jogador
async def mestre_exclui():
    u = inter(4, "Mestre Belmont", roles=["Mestre"]); await bot.mestre_excluir_personagem.callback(u, a80, "P3")
    kw = u.response.send_message.call_args.kwargs; view = kw["view"]
    assert view.por_mestre and kw["ephemeral"] and "Vaga" in kw["embed"].description
    btn = inter(4, "Mestre Belmont", roles=["Mestre"]); await view.confirmar.callback(btn)
    aviso = btn.followup.send.call_args.kwargs
    assert aviso["content"] == "<@80>" and aviso["embed"].title == "🗑️ Personagem excluído" and "Mestre Belmont excluiu **P3**" in aviso["embed"].description
    # o que o Discord recebe de verdade (junta com o padrão do bot, que não marca ninguém): só o dono do personagem
    from discord.webhook.async_ import handle_message_parameters
    enviado = handle_message_parameters(content=aviso["content"], allowed_mentions=aviso["allowed_mentions"],
                                        previous_allowed_mentions=bot.bot.allowed_mentions).payload["allowed_mentions"]
    assert enviado == {"users": [80], "parse": []}, enviado
run(mestre_exclui())
assert row(80, "P3") is None and db.count_deleted("80") == 2
with sqlite3.connect(db.DB_PATH) as cn:
    assert cn.execute("SELECT COUNT(*) FROM master_actions WHERE action='excluir_personagem'").fetchone()[0] == 1
    assert cn.execute("SELECT COUNT(*) FROM deleted_characters").fetchone()[0] == 2
# /mestre jogador: o painel do mestre
run(bot.mestre_jogador.callback(gm, a80)); d = desc(gm); print("  ", d.replace("\n", " | "))
assert sent(gm)[1]["ephemeral"] and titulo(gm) == "👤 Vaga" and "Personagens: **4** de **10** vagas (3 padrão + 7 extras)" in d and "Já excluiu: **2** personagens" in d and "**P1** · nível 1 · 0 XP · sem raça" in d
novato = alvo(90, "Novato"); run(bot.mestre_jogador.callback(gm, novato)); assert "Personagens: **0** de **3** vagas (3 padrão + 0 extras)" in desc(gm) and "Ainda não criou nenhum personagem" in desc(gm) and "Já excluiu: **0** personagens" in desc(gm)
print("G. limite, vagas e exclusão OK")


# ============================ H. horário no fuso de quem lê, e o nome novo da raça ============================
h1 = inter(80, "Vaga"); run(bot.historico.callback(h1, None, 10, None)); campos = sent(h1)[1]["embed"].fields
assert campos and all(re.search(r"<t:\d+:d> <t:\d+:t>", c.value) for c in campos) and not any(re.search(r"\d{4}-\d{2}-\d{2}T", c.value) for c in campos)
assert bot._quando("2026-09-18T20:10:00+00:00") == "<t:1789762200:d> <t:1789762200:t>"
assert bot._quando("lixo") == "lixo UTC"
assert dice.race_for(95) == "Vampiro" and dice.race_for(96) == "Dhampir" and dice.race_for(100) == "Dhampir" and dice.RACES == ["Humano", "Vampiro", "Dhampir"]
r = inter(82, "Rara"); run(bot.personagem_criar.callback(r, "Rara Raça"))
with dados(96): run(bot.raca_inicial.callback(r, None))
assert "Raça: **Dhampir**" in txt(r) and "Meio humano" not in txt(r) and not sent(r)[1].get("ephemeral")            # continua público
print("H. horário e Dhampir OK")

# ============================ I. ficha automática: classe, atributos e recursos ============================
db.DB_PATH = os.path.join(tmp, "ficha.db"); db.init_db()
CAMPOS = ["Nível", "Raça", "Classe Social", "Rank de Magia", "Classe", "Atributos", "Recursos", "Ranks das perícias especiais"]
def campos(i): return {f.name: f.value for f in sent(i)[1]["embed"].fields}
def preparar(uid, nome, raca="Humano", classe="Caçador"):
    """Sorteios feitos e classe escolhida (direto no banco): o personagem já pode distribuir atributos."""
    c = row(uid, nome)["id"]
    db.set_race(c, raca, 40); db.set_magic_rank(c, "Comum", 10); db.set_social_status(c, "3º Estado", 10)
    if classe: db.set_class(c, classe)
ana = novo(100, "Ana", "Ana Ficha"); a100 = alvo(100, "Ana"); ficha = lambda: row(100, "Ana Ficha")

# ficha nova: tudo zerado, e os campos novos ficam antes dos ranks, que continuam por último
run(bot.minha_ficha.callback(ana, None)); assert [f.name for f in sent(ana)[1]["embed"].fields] == CAMPOS
c = campos(ana); assert c["Classe"] == "ainda não definida\n(use `/classe`)" and c["Recursos"] == bot._SEM_CLASSE
assert c["Atributos"] == "Força 0 · Destreza 0 · Vitalidade 0 · Razão 0 · Vontade 0 · Alma 0\nPontos de atributo: 0 de 6 usados (6 livres)"
run(bot.atributos.callback(ana, None, None, None, None, None, None, None))                # sem números: só mostra
assert sent(ana)[1]["ephemeral"] and titulo(ana) == "🧬 Atributos de Ana Ficha" and list(campos(ana)) == ["Atributos", "Recursos"]
# a ordem da criação: /atributos e /classe ficam fechados enquanto faltam passos antes
run(bot.minha_ficha.callback(ana, None)); e = sent(ana)[1]["embed"]
assert e.description.startswith("⚠️ **Ficha incompleta.** Próximo passo: `/raca_inicial`") and "/ajuda" in e.description
run(bot.atributos.callback(ana, 2, None, 3, None, 1, None, None)); print("  ", txt(ana).splitlines()[0])
assert "Ainda não dá pra usar `/atributos`" in txt(ana) and "▶️ Sortear a raça: `/raca_inicial`" in txt(ana) and "🔒 Escolher a classe: depois dos sorteios" in txt(ana)
assert sent(ana)[1]["ephemeral"] and db.attributes_of(ficha())["forca"] == 0
run(bot.classe_escolher.callback(ana, "Caçador", None)); assert "Ainda não dá pra usar `/classe`" in txt(ana) and ficha()["class_name"] is None
# os três sorteios, em qualquer ordem, abrem a classe
with dados(50, 20, 40): run(bot.magia_inicial.callback(ana, None)); run(bot.classe_social.callback(ana, None)); run(bot.raca_inicial.callback(ana, None))
assert (ficha()["race"], ficha()["magic_rank"], ficha()["social_class"]) == ("Humano", "Raro", "3º Estado")
run(bot.atributos.callback(ana, 2, None, 3, None, 1, None, None))                          # sorteios feitos, mas ainda falta a classe
assert "Ainda não dá pra usar `/atributos`" in txt(ana) and "▶️ Escolher a classe: `/classe`" in txt(ana) and db.attributes_of(ficha())["forca"] == 0
run(bot.minha_ficha.callback(ana, None)); assert "Próximo passo: `/classe`" in sent(ana)[1]["embed"].description

# classe: vale uma vez, mostra bônus e vantagem
run(bot.classe_escolher.callback(ana, "Caçador", None)); print("  ", desc(ana).splitlines()[0:2])
assert titulo(ana) == "🎓 Classe de Ana Ficha: Caçador" and "Vantagem nas perícias: Religião e Luta ou Pontaria" in desc(ana)
assert "Bônus: Vida +35 · Sanidade +15 · Mana +5 · Estamina +20" in desc(ana) and "/atributos" in desc(ana) and sent(ana)[1]["ephemeral"]
run(bot.classe_escolher.callback(ana, "Sábio", None)); assert "já é da classe **Caçador**" in txt(ana) and ficha()["class_name"] == "Caçador"
run(bot.minha_ficha.callback(ana, None)); c = campos(ana)
assert c["Classe"] == "Caçador\n(vantagem em Religião e Luta ou Pontaria)"
assert c["Recursos"] == "❤️ Vida **35** · 🧠 Sanidade **15**\n🔮 Mana **5** · 💪 Estamina **20**"          # só o bônus da classe, ainda sem atributos
assert "Próximo passo: `/atributos`" in sent(ana)[1]["embed"].description

# 6 pontos no nível 1, direto no limite: a ficha fica pronta
run(bot.atributos.callback(ana, 2, None, 3, None, 1, None, None)); print("  ", campos(ana)["Atributos"].replace("\n", " | "))
assert titulo(ana) == "🧬 Atributos de Ana Ficha atualizados" and sent(ana)[1]["ephemeral"]
assert campos(ana)["Atributos"] == "Força 2 · Destreza 0 · Vitalidade 3 · Razão 0 · Vontade 1 · Alma 0\nPontos de atributo: 6 de 6 usados"
assert campos(ana)["Recursos"] == "❤️ Vida **50** · 🧠 Sanidade **20**\n🔮 Mana **8** · 💪 Estamina **35**"       # 15+35, 5+15, 3+5, 15+20
assert db.attributes_of(ficha()) == {"forca": 2, "destreza": 0, "vitalidade": 3, "razao": 0, "vontade": 1, "alma": 0}
run(bot.minha_ficha.callback(ana, None)); assert sent(ana)[1]["embed"].description is None and campos(ana)["Recursos"].startswith("❤️ Vida **50**")   # pronta: sem aviso
assert rules.calculate_resources(vitalidade=3, forca=2, vontade=1, alma=0, classe="Caçador")["estamina"]["total"] == 35   # mesma conta do /calcular_recursos
run(bot.classe_escolher.callback(ana, "Ladrão", "Fantasma")); assert "Não achei" in txt(ana)
sp = inter(199, "Sem Personagem"); run(bot.classe_escolher.callback(sp, "Sábio", None)); assert "Você ainda não tem personagem" in txt(sp)

# só dá pra aumentar
run(bot.atributos.callback(ana, 1, None, None, None, None, None, None)); assert "Só dá pra aumentar atributo, e Força ficaria menor do que já está." in txt(ana) and ficha()["attr_forca"] == 2
run(bot.atributos.callback(ana, 1, None, 2, None, None, None, None)); assert "Força e Vitalidade ficariam menores do que já estão" in txt(ana) and ficha()["attr_vitalidade"] == 3
# passar do total (6 no nível 1)
run(bot.atributos.callback(ana, None, None, None, None, None, 1, None)); assert "Você distribuiu 7 pontos de atributo, mas no nível 1 o total é 6." in txt(ana) and ficha()["attr_alma"] == 0
run(bot.atributos.callback(ana, None, None, None, None, None, 1, "Fantasma")); assert "Não achei" in txt(ana)

# limite de criação do humano (3), só ultrapassável com ponto de nível
lim = novo(102, "Lia", "Lia Limite"); preparar(102, "Lia Limite"); alia = alvo(102, "Lia")
run(bot.atributos.callback(lim, 4, None, None, None, None, None, None)); print("  ", txt(lim)[:120])
assert "O limite de criação de Humano é: Força 3, Destreza 3, Vitalidade 3, Razão 6." in txt(lim) and "você tem 0" in txt(lim) and row(102, "Lia Limite")["attr_forca"] == 0
run(bot.atributos.callback(lim, None, None, None, 6, None, None, None)); assert titulo(lim).endswith("atualizados")             # Razão vai até 6 no humano
run(bot.atributos.callback(lim, None, None, None, 7, None, None, None)); assert "Você distribuiu 7 pontos" in txt(lim) and "O limite de criação" in txt(lim)   # dois problemas juntos
run(bot.mestre_dar_xp.callback(gm, alia, 1000, None, None)); assert "Use `/atributos` pra distribuir o ponto de atributo." in desc(gm)                # nível 2: ganhou 1 ponto
run(bot.atributos.callback(lim, 4, None, None, 6, None, None, None)); assert "Você distribuiu 10 pontos" in txt(lim)                        # ainda passa do total (7)
db.set_attributes(row(102, "Lia Limite")["id"], {"razao": 3})
run(bot.atributos.callback(lim, 4, None, None, None, None, None, None)); assert titulo(lim).endswith("atualizados") and row(102, "Lia Limite")["attr_forca"] == 4   # o ponto de nível cobre o excesso
run(bot.atributos.callback(lim, 5, None, None, None, None, None, None)); assert "essa distribuição passa 2" in txt(lim)                     # dois acima do limite, só 1 ponto de nível
run(bot.atributos.callback(lim, None, None, None, None, None, None, None)); assert "Pontos de atributo: 7 de 7 usados" in campos(lim)["Atributos"]

# Vampiro (limite 5) e Dhampir (sem limite por atributo, só o total)
for uid, raca, nome in [(103, "Vampiro", "Vlad"), (104, "Dhampir", "Alu")]:
    u = novo(uid, f"J{uid}", nome); preparar(uid, nome, raca)
    if raca == "Vampiro":
        run(bot.atributos.callback(u, 5, 1, None, None, None, None, None)); assert titulo(u).endswith("atualizados")
        run(bot.atributos.callback(u, 6, None, None, None, None, None, None)); assert "O limite de criação de Vampiro é: Força 5, Destreza 5, Vitalidade 5." in txt(u)
    else:
        run(bot.atributos.callback(u, 6, None, None, None, None, None, None)); assert titulo(u).endswith("atualizados") and row(uid, nome)["attr_forca"] == 6
        run(bot.atributos.callback(u, 7, None, None, None, None, None, None)); assert "Você distribuiu 7 pontos" in txt(u) and "O limite de criação" not in txt(u)

# subir de nível avisa pra distribuir o ponto; nível ímpar não avisa; vários níveis falam em "pontos"
b = novo(105, "Bia", "Bia Nível"); ab = alvo(105, "Bia")
run(bot.mestre_dar_xp.callback(gm, ab, 1000, None, None)); assert "Use `/atributos` pra distribuir o ponto de atributo." in desc(gm)
run(bot.mestre_dar_xp.callback(gm, ab, 2000, None, None)); assert "/atributos" not in desc(gm) and "Ganhos" in desc(gm)          # nível 3
run(bot.mestre_dar_xp.callback(gm, ab, 42000, None, None)); assert "Nível **3** → **10**" in desc(gm) and "Use `/atributos` pra distribuir os pontos de atributo." in desc(gm)
run(bot.mestre_dar_xp.callback(gm, ab, 500, None, None)); assert "/atributos" not in desc(gm)                                     # só XP, sem nível
run(bot.mestre_dar_xp.callback(gm, ab, -5000, None, None)); assert "/atributos" not in desc(gm)                                  # perder nível não fala disso

# mestre: mexe direto, sem conferir limites, e fica registrado
m = novo(106, "Caio", "Caio Mestrado"); am = alvo(106, "Caio")
run(bot.mestre_atributos.callback(gm, am, None, None, None, None, None, None, None)); assert "pelo menos um atributo" in txt(gm) and sent(gm)[1]["ephemeral"]
run(bot.mestre_atributos.callback(gm, am, 9, None, 2, None, None, None, None)); print("  ", desc(gm).replace("\n", " | "))
assert titulo(gm) == "🛠️ Atributos corrigidos" and "Força: **0** → **9**" in desc(gm) and "Vitalidade: **0** → **2**" in desc(gm) and "Destreza" not in desc(gm)
assert "Pontos de atributo: 11 de 6 usados (passou 5)" in desc(gm) and rodape(gm) == "Definido por um mestre, sem conferir os limites." and not sent(gm)[1].get("ephemeral")
assert (row(106, "Caio Mestrado")["attr_forca"], row(106, "Caio Mestrado")["attr_vitalidade"]) == (9, 2)
run(bot.mestre_atributos.callback(gm, am, 9, None, None, None, None, None, None)); assert "Nada mudou" in txt(gm) and sent(gm)[1]["ephemeral"]
run(bot.mestre_atributos.callback(gm, am, 3, None, None, None, None, None, None)); assert "Força: **9** → **3**" in desc(gm)          # o mestre pode diminuir
run(bot.mestre_atributos.callback(gm, am, 5, None, None, None, None, None, "Fantasma")); assert "não tem nenhum personagem chamado" in txt(gm)
run(bot.mestre_atributos.callback(gm, alvo(777, "Novato"), 5, None, None, None, None, None, None)); assert "ainda não tem personagem" in txt(gm)
# mestre passou dos pontos: a ficha mostra, e o jogador não consegue mexer até acertar
run(bot.mestre_atributos.callback(gm, am, 9, None, None, None, None, None, None)); preparar(106, "Caio Mestrado", classe=None)
run(bot.minha_ficha.callback(m, None)); assert "Pontos de atributo: 11 de 6 usados (passou 5)" in campos(m)["Atributos"]
run(bot.atributos.callback(m, None, None, None, None, None, 1, None)); assert "Ainda não dá pra usar `/atributos`" in txt(m) and row(106, "Caio Mestrado")["attr_alma"] == 0   # sem classe, fechado
# o mestre define a classe (ele passa por cima da ordem), e aí o jogador pode tentar
run(bot.mestre_corrigir_classe.callback(gm, am, "Sábio", None)); assert titulo(gm) == "🛠️ Definição corrigida" and "**nada** → **Sábio**" in desc(gm)
run(bot.atributos.callback(m, None, None, None, None, None, 1, None)); assert "Você distribuiu 12 pontos" in txt(m) and row(106, "Caio Mestrado")["attr_alma"] == 0
run(bot.mestre_corrigir_classe.callback(gm, am, "Ladrão", None)); assert "**Sábio** → **Ladrão**" in desc(gm) and row(106, "Caio Mestrado")["class_name"] == "Ladrão"
run(bot.classe_escolher.callback(m, "Mundano", None)); assert "já é da classe **Ladrão**" in txt(m)
run(bot.mestre_ficha.callback(gm, am, None)); cf = campos(gm); assert sent(gm)[1]["ephemeral"] and cf["Classe"].startswith("Ladrão") and "Vida" in cf["Recursos"]
run(bot.mestre_corrigir_classe.callback(gm, am, "Sábio", "Fantasma")); assert "não tem nenhum personagem chamado" in txt(gm)
# 'apagar' limpa sorteios, nunca a classe nem os atributos
run(bot.mestre_apagar.callback(gm, am, "todas", None)); c = row(106, "Caio Mestrado")
assert c["race"] is None and c["class_name"] == "Ladrão" and c["attr_forca"] == 9
with sqlite3.connect(db.DB_PATH) as cn:
    acoes = [r for r in cn.execute("SELECT action, detail FROM master_actions WHERE action IN ('atributos','corrigir_class') ORDER BY id")]
print("   auditoria:", acoes)
assert acoes == [("atributos", "forca 0 -> 9; vitalidade 0 -> 2"), ("atributos", "forca 9 -> 3"), ("atributos", "forca 3 -> 9"), ("corrigir_class", "nada -> Sábio"), ("corrigir_class", "Sábio -> Ladrão")]
# a cópia dos excluídos leva a ficha inteira (classe e atributos incluídos)
async def exclui_caio():
    u = inter(106, "Caio"); await bot.personagem_excluir.callback(u, "Caio Mestrado"); view = u.response.send_message.call_args.kwargs["view"]
    await view.confirmar.callback(inter(106, "Caio"))
run(exclui_caio())
with sqlite3.connect(db.DB_PATH) as cn:
    import json
    snap = json.loads(cn.execute("SELECT snapshot_json FROM deleted_characters WHERE name='Caio Mestrado'").fetchone()[0])
assert snap["class_name"] == "Ladrão" and snap["attr_forca"] == 9
print("I. ficha automática OK")


# ============================ J. /mestre exportar ============================
db.DB_PATH = os.path.join(tmp, "export.db"); db.init_db()
ex = novo(110, "Exp", "Exportável"); run(bot.mestre_dar_xp.callback(gm, alvo(110, "Exp"), 1500, "teste", None))
db.set_class(row(110, "Exportável")["id"], "Mundano"); db.set_attributes(row(110, "Exportável")["id"], {"vitalidade": 2})
capt = {}
async def captura(*a, **kw):
    f = kw.get("file")
    if f is not None:
        capt["nome"] = f.filename; capt["dados"] = f.fp.read(); f.fp.seek(0)
    capt["kw"] = kw; capt["args"] = a
mx = inter(4, "Mestre Belmont", roles=["Mestre"]); mx.response.send_message = AsyncMock(side_effect=captura)
run(bot.mestre_exportar.callback(mx))
assert capt["kw"]["ephemeral"] and re.fullmatch(r"baptism_of_blood_\d{4}-\d{2}-\d{2}_\d{4}\.db", capt["nome"]) and "todos os jogadores" in capt["args"][0]
recebido = os.path.join(tmp, "recebido.db"); open(recebido, "wb").write(capt["dados"])
with sqlite3.connect(recebido) as cn:
    assert cn.execute("SELECT name, xp, class_name, attr_vitalidade FROM characters").fetchone() == ("Exportável", 1500, "Mundano", 2)
    assert cn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION and cn.execute("SELECT COUNT(*) FROM xp_log").fetchone()[0] == 1
with sqlite3.connect(db.DB_PATH) as cn:
    assert [r[0] for r in cn.execute("SELECT detail FROM master_actions WHERE action='exportar'")] == [f"{len(capt['dados'])} bytes"]
# maior que o limite do servidor: não manda o arquivo, explica, e não registra exportação
mg = inter(4, "Mestre Belmont", roles=["Mestre"]); mg.guild = NS(roles=[], filesize_limit=1000)
run(bot.mestre_exportar.callback(mg)); kw = sent(mg)[1]
assert "file" not in kw and kw["ephemeral"] and "só aceita arquivo de até" in sent(mg)[0] and "railway volume files download" in sent(mg)[0]
with sqlite3.connect(db.DB_PATH) as cn: assert cn.execute("SELECT COUNT(*) FROM master_actions WHERE action='exportar'").fetchone()[0] == 1
print("J. exportar OK")

# ============================ K. recursos por nível, textos de XP e Rank ============================
db.DB_PATH = os.path.join(tmp, "nivel.db"); db.init_db()
pay = {c.name: c.to_dict(bot.bot.tree) for c in bot.bot.tree.get_commands()}
def todas(d):
    yield d["description"]
    for o in d.get("options", []):
        yield from todas(o) if "options" in o else [o["description"]]
cr = pay["calcular_recursos"]; nv = opt(cr, "nivel")
assert (nv["min_value"], nv["max_value"], nv.get("required", False)) == (1, 10, False) and "mesmo atributo em todos os níveis" in nv["description"]
assert req(cr["options"]) == {"classe", "vitalidade", "forca", "vontade", "alma"} and "pelo nível" in cr["description"]
assert pay["minha_ficha"]["description"] == "Mostra nível, XP, raça, classe, atributos, recursos e ranks do seu personagem."
dx, up = sub_("mestre", "dar_xp"), sub_("mestre", "upar")
assert "missão de mestre ou desenvolvimento" in dx["description"] and "por roleplay, não por ação avulsa" in opt(dx, "motivo")["description"]
assert "missão de mestre" in opt(up, "motivo")["description"] and "RP marcante" not in opt(up, "motivo")["description"]
assert "nenhum Rank" in opt(sub_("mestre", "rank_pericia"), "rank")["description"]
assert not [t for d in pay.values() for t in todas(d) if "grau" in t.lower()]              # 'grau' ficou só pras Disciplinas, que o bot não tem

# /calcular_recursos: soma por nível, com o mesmo atributo em todos os níveis
calc = inter(70, "Calculista")
run(bot.calcular_recursos.callback(calc, "Caçador", 3, 1, 2, 1, 5)); e = sent(calc)[1]["embed"]; print("  ", e.title, "|", e.description.splitlines()[0:2])
assert e.title == "🧮 Recursos (Caçador, nível 5)" and sent(calc)[1]["ephemeral"]
assert "**Vida: 110**\n　Vitalidade 3 × 5 × 5 níveis = 75, mais 35 da classe" in e.description
assert "**Sanidade: 65**\n　Vontade 2 × 5 × 5 níveis = 50, mais 15 da classe" in e.description
assert "**Mana: 50**\n　(Alma 1 + Vontade 2) × 3 × 5 níveis = 45, mais 5 da classe" in e.description
assert "**Estamina: 80**\n　(Força 1 + Vitalidade 3) × 3 × 5 níveis = 60, mais 20 da classe" in e.description
assert "Por nível" in e.footer.text and "a conta exata é a da /minha_ficha" in e.footer.text and "Destreza e Razão não entram" in e.footer.text and "`" not in e.footer.text
run(bot.calcular_recursos.callback(calc, "Caçador", 3, 2, 2, 1)); e = sent(calc)[1]["embed"]      # sem nível: nível 1, igual ao cálculo antigo
assert e.title == "🧮 Recursos (Caçador)" and "níveis" not in e.description
assert "**Vida: 50**\n　Vitalidade 3 × 5 = 15, mais 35 da classe" in e.description and "**Estamina: 35**" in e.description
run(bot.calcular_recursos.callback(calc, "Nenhuma", 3, 1, 2, 1, 10)); e = sent(calc)[1]["embed"]
assert e.title == "🧮 Recursos (sem classe, nível 10)" and "**Vida: 150**\n　Vitalidade 3 × 5 × 10 níveis = 150" in e.description and "da classe" not in e.description
run(bot.calcular_recursos.callback(calc, "Caçador", 3, 1, 2, 1, 10)); assert "**Vida: 185**" in sent(calc)[1]["embed"].description and "**Estamina: 140**" in sent(calc)[1]["embed"].description
assert len(historico_de(70)) == 0 and db.list_characters("70") == []                             # a calculadora continua sem escrever nada

# a ficha soma nível a nível: mesma tabela do prompt (Caçador, Força 1, Vitalidade 3, Vontade 2, Alma 1 em todos os níveis)
f1 = novo(120, "Nivel", "Nível Ficha"); a120 = alvo(120, "Nivel"); ch = lambda: row(120, "Nível Ficha")
db.set_race(ch()["id"], "Humano", 40); db.set_class(ch()["id"], "Caçador")
db.set_attributes(ch()["id"], {"forca": 1, "vitalidade": 3, "vontade": 2, "alma": 1})
run(bot.minha_ficha.callback(f1, None)); assert campos(f1)["Recursos"] == "❤️ Vida **50** · 🧠 Sanidade **25**\n🔮 Mana **14** · 💪 Estamina **32**"     # nível 1: uma vez só
run(bot.mestre_dar_xp.callback(gm, a120, 10000, None, None))
assert "Use `/atributos` pra distribuir os pontos de atributo. Distribui logo: o nível novo já conta com os atributos que você tiver." in desc(gm)
run(bot.minha_ficha.callback(f1, None)); assert campos(f1)["Recursos"] == "❤️ Vida **110** · 🧠 Sanidade **65**\n🔮 Mana **50** · 💪 Estamina **80**"   # nível 5
run(bot.mestre_dar_xp.callback(gm, a120, 35000, None, None))
run(bot.minha_ficha.callback(f1, None)); assert campos(f1)["Recursos"] == "❤️ Vida **185** · 🧠 Sanidade **115**\n🔮 Mana **95** · 💪 Estamina **140**"  # nível 10
run(bot.mestre_ficha.callback(gm, a120, None)); assert campos(gm)["Recursos"] == campos(f1)["Recursos"]                       # a ficha do mestre é a mesma conta
run(bot.atributos.callback(f1, None, None, None, None, None, None, None)); assert campos(f1)["Recursos"] == campos(gm)["Recursos"]   # e a tela de /atributos também
assert sorted(db.get_level_attributes(ch()["id"])) == list(range(1, 10))

# atributo da época pelos comandos: Vitalidade 3 nos níveis 1 a 3 e 4 a partir do 4 -> Vida 80, 100, 120
v = novo(121, "Vida", "Vida Época"); av = alvo(121, "Vida"); vc = lambda: row(121, "Vida Época")
preparar(121, "Vida Época")
vida_de = lambda i: int(re.search(r"Vida \*\*(\d+)\*\*", campos(i)["Recursos"]).group(1))
run(bot.atributos.callback(v, None, None, 3, None, None, None, None)); assert vida_de(v) == 50
run(bot.mestre_dar_xp.callback(gm, av, 3000, None, None)); run(bot.minha_ficha.callback(v, None)); assert vida_de(v) == 80                   # nível 3
run(bot.mestre_dar_xp.callback(gm, av, 3000, None, None)); run(bot.minha_ficha.callback(v, None)); assert vida_de(v) == 95                   # nível 4, ainda com Vitalidade 3
run(bot.atributos.callback(v, None, None, 4, None, None, None, None)); assert vida_de(v) == 100                                              # distribuiu o ponto: só o nível 4 sente
run(bot.minha_ficha.callback(v, None)); assert campos(v)["Recursos"] == "❤️ Vida **100** · 🧠 Sanidade **15**\n🔮 Mana **5** · 💪 Estamina **59**"
run(bot.mestre_dar_xp.callback(gm, av, 4000, None, None)); run(bot.minha_ficha.callback(v, None)); assert vida_de(v) == 120                   # nível 5
assert campos(v)["Recursos"] == "❤️ Vida **120** · 🧠 Sanidade **15**\n🔮 Mana **5** · 💪 Estamina **71**"
run(bot.mestre_dar_xp.callback(gm, av, -4000, "engano", None)); run(bot.minha_ficha.callback(v, None)); assert vida_de(v) == 100                # baixou: some a linha do 4
run(bot.mestre_corrigir_nivel.callback(gm, av, 2, None)); run(bot.minha_ficha.callback(v, None)); assert vida_de(v) == 15 + 20 + 35            # nível 2 usa Vitalidade 4
run(bot.mestre_atributos.callback(gm, av, None, None, 6, None, None, None, None)); run(bot.minha_ficha.callback(v, None))
assert vida_de(v) == 15 + 30 + 35                                                                                                          # o mestre só mexe no nível atual
assert sorted(db.get_level_attributes(vc()["id"])) == [1]

# textos: quem dá XP e o Rank das perícias
run(bot.niveis.callback(f1, None)); assert "missão de mestre e desenvolvimento do personagem" in rodape(f1) and "sempre por roleplay e não por ação avulsa" in rodape(f1)
r0 = novo(122, "Rank", "Sem Rank"); run(bot.minha_ficha.callback(r0, None)); assert campos(r0)["Ranks das perícias especiais"] == "nenhum Rank ainda"
a122 = alvo(122, "Rank"); run(bot.mestre_rank_pericia.callback(gm, a122, "Forja", 3, None)); assert titulo(gm) == "⬆️ Forja: Rank 3/10" and "**0** → **3**" in desc(gm)
run(bot.minha_ficha.callback(r0, None)); assert campos(r0)["Ranks das perícias especiais"] == "**Forja** 3/10 ▰▰▰▱▱▱▱▱▱▱"
run(bot.mestre_rank_pericia.callback(gm, a122, "Forja", 0, None)); run(bot.minha_ficha.callback(r0, None)); assert campos(r0)["Ranks das perícias especiais"] == "nenhum Rank ainda"

# excluir o personagem apaga as linhas de nível dele
async def exclui_nivel():
    u = inter(120, "Nivel"); await bot.personagem_excluir.callback(u, "Nível Ficha"); view = u.response.send_message.call_args.kwargs["view"]
    await view.confirmar.callback(inter(120, "Nivel"))
run(exclui_nivel()); assert row(120, "Nível Ficha") is None
with sqlite3.connect(db.DB_PATH) as cn: assert cn.execute("SELECT COUNT(*) FROM level_attributes WHERE character_id = ?", (1,)).fetchone()[0] == 0
assert sorted(db.get_level_attributes(vc()["id"])) == [1]                                       # e não mexeu no de ninguém mais
print("K. recursos por nível OK")

# ============================ L. a ordem: comandos de jogo só com a ficha pronta ============================
import ajuda
db.DB_PATH = os.path.join(tmp, "ordem.db"); db.init_db()
async def checa(cmd, i):
    """Roda os bloqueios do comando. Devolve None se passou, ou a mensagem do bloqueio."""
    try:
        return None if await cmd._check_can_run(i) else "falhou sem mensagem"
    except bot.FichaIncompleta as e:
        return e.mensagem
def tenta(cmd, i, personagem=None):
    i.namespace = NS(personagem=personagem)
    return run(checa(cmd, i))
JOGO = [bot.rolar, bot.extrato_xp, bot.historico, bot.rank]
# só esses quatro têm bloqueio de ficha; criação, ficha, níveis, calculadora, personagens e ajuda ficam sempre abertos
assert {c.name for c in bot.bot.tree.get_commands() if not isinstance(c, app_commands.Group) and c.checks} == {"rolar", "extrato_xp", "historico", "rank"}
assert all(not c.checks for c in bot.personagem_grupo.commands)
assert all(len(c.checks) == 1 for c in JOGO)

# sem personagem nenhum
p0 = inter(200, "Novo")
for cmd in JOGO: assert tenta(cmd, p0) == bot._SEM_PERSONAGEM, cmd.name
assert "/personagem criar" in bot._SEM_PERSONAGEM and "/ajuda" in bot._SEM_PERSONAGEM
# criar o personagem aponta pro passo a passo
run(bot.personagem_criar.callback(p0, "Recém Chegado")); print("  ", desc(p0).replace("\n", " "))
assert "Próximo passo: os três sorteios (`/raca_inicial`, `/magia_inicial` e `/classe_social`, em qualquer ordem)." in desc(p0)
assert "Depois vêm `/classe` e `/atributos`. O passo a passo completo está em `/ajuda`." in desc(p0)
# com o personagem criado, tudo de jogo fica fechado, e a mensagem diz o que fazer
for cmd in JOGO:
    m = tenta(cmd, p0); assert m.startswith("🔒 A ficha de **Recém Chegado** ainda não está pronta, e esse comando só abre quando ela estiver."), cmd.name
    assert "▶️ Sortear a raça: `/raca_inicial`" in m and "Próximo passo: `/raca_inicial`" in m and "`/ajuda`" in m and len(m) < 2000
print("  ", tenta(bot.rolar, p0).splitlines()[0])
assert tenta(bot.rolar, p0, "Recém Chegado") and tenta(bot.extrato_xp, p0, "Recém Chegado")                  # pelo nome também fecha
assert tenta(bot.rolar, p0, "Fantasma") is None                                                                # nome que não existe: o próprio comando avisa
# passo a passo, um de cada vez, pelos comandos de verdade
with dados(40): run(bot.raca_inicial.callback(p0, None))
m = tenta(bot.rolar, p0); assert "✅ Sortear a raça" in m and "▶️ Sortear o Rank de magia: `/magia_inicial`" in m
with dados(50): run(bot.magia_inicial.callback(p0, None))
with dados(20): run(bot.classe_social.callback(p0, None))
m = tenta(bot.rolar, p0); assert "▶️ Escolher a classe: `/classe`" in m and "🔒 Distribuir os pontos de atributo: depois de escolher a classe" in m
run(bot.classe_escolher.callback(p0, "Sábio", None))
m = tenta(bot.rolar, p0); assert "▶️ Distribuir os pontos de atributo: `/atributos` (0 de 6 pontos usados)" in m and "Próximo passo: `/atributos`" in m
run(bot.atributos.callback(p0, None, None, None, None, 5, None, None)); assert titulo(p0).endswith("atualizados")            # 5 de 6: ainda fechado
m = tenta(bot.rolar, p0); assert "(5 de 6 pontos usados)" in m
for cmd in JOGO: assert tenta(cmd, p0) is not None
run(bot.atributos.callback(p0, None, None, None, None, 6, None, None))                                                       # 6 de 6: abriu tudo
for cmd in JOGO: assert tenta(cmd, p0) is None, cmd.name
assert tenta(bot.rolar, p0, "Recém Chegado") is None

# dois personagens: vale o que está sendo usado (ou o que foi digitado)
d2 = inter(201, "Dois"); run(bot.personagem_criar.callback(d2, "Pronta")); preparar(201, "Pronta"); db.set_attributes(row(201, "Pronta")["id"], {"vontade": 6})
run(bot.personagem_criar.callback(d2, "Nova"))                                                                               # o novo vira o ativo
assert "**Nova**" in tenta(bot.rolar, d2) and tenta(bot.rolar, d2, "Pronta") is None and "**Nova**" in tenta(bot.rolar, d2, "Nova")
assert "**Nova**" in tenta(bot.extrato_xp, d2)
assert tenta(bot.historico, d2) is None and tenta(bot.rank, d2) is None                                                      # tem um pronto: histórico e rank abrem
run(bot.personagem_usar.callback(d2, "Pronta")); assert tenta(bot.rolar, d2) is None
# só personagens incompletos: histórico e rank fecham, mostrando o que está em uso
d3 = inter(203, "Três"); run(bot.personagem_criar.callback(d3, "Rascunho A")); run(bot.personagem_criar.callback(d3, "Rascunho B"))
for cmd in (bot.historico, bot.rank): assert "**Rascunho B**" in tenta(cmd, d3), cmd.name

# ficha incompleta por poucos pontos: continua fechada e diz quantos faltam
d4 = inter(204, "Quatro"); run(bot.personagem_criar.callback(d4, "Meio Pronto")); preparar(204, "Meio Pronto"); db.set_attributes(row(204, "Meio Pronto")["id"], {"forca": 3})
assert "(3 de 6 pontos usados)" in tenta(bot.rolar, d4)
# em qualquer nível vale só os 6 pontos da criação
d5 = inter(205, "Cinco"); run(bot.personagem_criar.callback(d5, "Veterano")); preparar(205, "Veterano"); db.set_attributes(row(205, "Veterano")["id"], {"vitalidade": 3, "vontade": 3})
run(bot.mestre_dar_xp.callback(gm, alvo(205, "Cinco"), 10000, None, None)); assert row(205, "Veterano")["level"] == 5 and tenta(bot.rolar, d5) is None

# mestres passam direto, mesmo sem personagem nenhum
mm = inter(4, "Mestre Belmont", roles=["Mestre"]); adm = inter(6, "Admin", admin=True); ger = inter(7, "Gerente", manage=True)
for quem in (mm, adm, ger):
    for cmd in JOGO: assert tenta(cmd, quem) is None, (quem.user.display_name, cmd.name)
# ...mas quem só tem um cargo parecido não passa
for cmd in JOGO: assert tenta(cmd, inter(8, "Jogador", roles=["Jogador"])) == bot._SEM_PERSONAGEM

# 100 na classe social: a ficha espera o mestre, e a classe fica fechada até ele decidir
e6 = inter(206, "Seis"); run(bot.personagem_criar.callback(e6, "Sorte Grande")); a206 = alvo(206, "Seis")
with dados(50, 100, 40): run(bot.magia_inicial.callback(e6, None)); run(bot.classe_social.callback(e6, None)); run(bot.raca_inicial.callback(e6, None))
assert "⏳ Classe social: você tirou 100, então um mestre vai definir o seu Estado" in tenta(bot.rolar, e6)
run(bot.classe_escolher.callback(e6, "Caçador", None)); print("  ", txt(e6))
assert txt(e6) == ("Ainda não dá pra usar `/classe`: você tirou 100 no sorteio da classe social, então um mestre precisa definir o seu "
                   "Estado primeiro. Fala com ele.") and row(206, "Sorte Grande")["class_name"] is None
run(bot.mestre_corrigir_estado.callback(gm, a206, "3", None))
run(bot.classe_escolher.callback(e6, "Caçador", None)); assert titulo(e6) == "🎓 Classe de Sorte Grande: Caçador"                # o mestre decidiu: destravou

# o mestre passa por cima da ordem: define a classe e os atributos sem os sorteios
g7 = inter(207, "Sete"); run(bot.personagem_criar.callback(g7, "Por Cima")); a207 = alvo(207, "Sete")
run(bot.mestre_corrigir_classe.callback(gm, a207, "Ladrão", None)); assert row(207, "Por Cima")["class_name"] == "Ladrão"
run(bot.mestre_atributos.callback(gm, a207, 2, None, 2, None, 2, None, None)); assert row(207, "Por Cima")["attr_forca"] == 2
run(bot.atributos.callback(g7, None, None, 1, None, None, None, None)); assert "Ainda não dá pra usar `/atributos`" in txt(g7)   # o jogador segue a ordem: faltam os sorteios
assert "✅ Escolher a classe" in txt(g7) and "✅ Distribuir os pontos de atributo" in txt(g7) and "▶️ Sortear a raça: `/raca_inicial`" in txt(g7)   # o que o mestre já fez aparece como feito

# o tratador de erros mostra a mensagem do bloqueio, e não a de "só pra mestre"
er = inter(208, "Erro"); er.command = bot.rolar
run(bot.on_app_command_error(er, bot.FichaIncompleta("🔒 mensagem do bloqueio"))); assert sent(er)[0] == "🔒 mensagem do bloqueio" and sent(er)[1]["ephemeral"]
er2 = inter(209, "Erro2"); er2.command = bot.mestre_upar
run(bot.on_app_command_error(er2, app_commands.CheckFailure("x"))); assert "só pra mestre" in sent(er2)[0]
print("L. ordem e bloqueio OK")


# ============================ M. /ajuda ============================
def todos_os_comandos():
    for c in bot.bot.tree.get_commands():
        if isinstance(c, app_commands.Group):
            for sub in c.commands: yield f"{c.name} {sub.name}", sub
        else: yield c.name, c
reais = dict(todos_os_comandos())
# todo comando de verdade tem ajuda (e o contrário), e os exemplos só usam opções que existem
assert set(reais) - {"help"} == set(ajuda.AJUDA), sorted((set(reais) - {"help"}) ^ set(ajuda.AJUDA))
for chave, cmd in reais.items():
    if chave == "help": continue
    opcoes = {p.name for p in cmd.parameters}
    usadas = set(re.findall(r"(\w+):", ajuda.AJUDA[chave]["uso"]))
    assert usadas <= opcoes, (chave, sorted(usadas - opcoes))
    assert ajuda.AJUDA[chave]["uso"].startswith("/" + chave)
# quem tem bloqueio de ficha (ou exige um passo anterior) diz isso na ajuda
for chave in ("rolar", "historico", "extrato_xp", "rank"): assert ajuda.AJUDA[chave]["requisito"].startswith("Só "), chave
assert "depois dos três sorteios" in ajuda.AJUDA["classe"]["requisito"] and "depois de escolher a classe" in ajuda.AJUDA["atributos"]["requisito"]
# os números e regras que a ajuda cita batem com o código
assert "N × 1.000 XP" in ajuda.AJUDA["niveis"]["detalhes"] and "3 vagas" in ajuda.AJUDA["personagem criar"]["detalhes"] and "até 25" in ajuda.AJUDA["historico"]["detalhes"]
assert bot.LIMITE_BASE == 3 and bot.LIMITE_MAXIMO == 10 and "teto é de 10" in ajuda.AJUDA["mestre vagas"]["detalhes"]
assert "6 pontos na criação" in ajuda.AJUDA["atributos"]["detalhes"] and rules.CREATION_ATTRIBUTE_POINTS == 6

# payload: /ajuda e /help têm o campo comando, opcional e com autocomplete
pay = {c.name: c.to_dict(bot.bot.tree) for c in bot.bot.tree.get_commands()}
for nome in ("ajuda", "help"):
    assert [(o["name"], o.get("required", False), o.get("autocomplete")) for o in pay[nome]["options"]] == [("comando", False, True)], nome
    assert len(pay[nome]["description"]) <= 100 and len(pay[nome]["options"][0]["description"]) <= 100

# /ajuda geral, em cada situação
h = inter(210, "Ajuda")
run(bot.ajuda_comando.callback(h, None)); e = sent(h)[1]["embed"]; print("  ", [f.name for f in e.fields])
assert sent(h)[1]["ephemeral"] and e.title == "📖 Ajuda do bot" and "/ajuda comando:atributos" in e.description
assert [f.name for f in e.fields] == ["Seu passo a passo", "Seu personagem", "Sorteios de criação", "Jogo (só com a ficha pronta)", "Consultas"]
assert "Você ainda não tem personagem" in e.fields[0].value and "`/personagem criar`" in e.fields[0].value
assert len(e) <= 6000 and all(len(f.value) <= 1024 for f in e.fields)
assert "`/rolar` rola um dado e guarda no histórico" in e.fields[3].value and "`/classe` escolhe a classe do personagem" in e.fields[1].value
run(bot.personagem_criar.callback(h, "Aprendiz")); run(bot.ajuda_comando.callback(h, None)); e = sent(h)[1]["embed"]
assert "▶️ Sortear a raça: `/raca_inicial`" in e.fields[0].value and "Próximo passo:" in e.fields[0].value and "Comandos de mestre" not in [f.name for f in e.fields]
preparar(210, "Aprendiz"); db.set_attributes(row(210, "Aprendiz")["id"], {"vontade": 6})
run(bot.ajuda_comando.callback(h, None)); assert sent(h)[1]["embed"].fields[0].value == "✅ Ficha pronta. Todos os comandos estão liberados."
mh = inter(4, "Mestre Belmont", roles=["Mestre"]); run(bot.ajuda_comando.callback(mh, None)); e = sent(mh)[1]["embed"]
assert e.fields[-1].name == "Comandos de mestre" and "`/mestre dar_xp`" in e.fields[-1].value and "Você ainda não tem personagem" in e.fields[0].value
assert len(e) <= 6000 and all(len(f.value) <= 1024 for f in e.fields)

# /ajuda de um comando
run(bot.ajuda_comando.callback(h, "atributos")); e = sent(h)[1]["embed"]
assert sent(h)[1]["ephemeral"] and e.title == "📖 /atributos" and e.description.startswith("Distribui os pontos de atributo.")
assert {f.name: f.value for f in e.fields}["Como usar"] == "`/atributos forca:2 vitalidade:3 vontade:1`" and "Só depois de escolher a classe" in {f.name: f.value for f in e.fields}["Quando dá pra usar"]
run(bot.ajuda_comando.callback(h, "/ROLAR")); assert sent(h)[1]["embed"].title == "📖 /rolar"
run(bot.ajuda_comando.callback(h, "dar_xp")); e = sent(h)[1]["embed"]; assert e.title == "📖 /mestre dar_xp" and e.fields[-1].name == "Quem usa"
run(bot.ajuda_comando.callback(h, "ficha")); assert sent(h)[1]["embed"].title == "📖 /minha_ficha"                              # jogador tem preferência
run(bot.ajuda_comando.callback(h, "personagem")); print("  ", txt(h)); assert txt(h).startswith('Não achei nenhum comando com "personagem". Quis dizer: `/personagem criar`') and sent(h)[1]["ephemeral"]
run(bot.ajuda_comando.callback(h, "xyzabc")); assert txt(h) == 'Não achei nenhum comando com "xyzabc". Use `/ajuda` pra ver a lista de comandos.'
# /help é a mesma coisa
for arg in (None, "atributos", "rolar", "xyz"):
    a, b = inter(211, "A"), inter(211, "A"); run(bot.ajuda_comando.callback(a, arg)); run(bot.help_comando.callback(b, arg))
    assert txt(a) == txt(b) and sent(a)[1] == sent(b)[1] or (sent(a)[1]["embed"].to_dict() == sent(b)[1]["embed"].to_dict())
# autocomplete: mestre só aparece pra mestre
ch = run(bot._autocomplete_comando(inter(212, "J"), "atrib")); assert [(c.name, c.value) for c in ch] == [("/atributos", "atributos")]
ch = run(bot._autocomplete_comando(inter(4, "M", roles=["Mestre"]), "atrib")); assert [c.value for c in ch] == ["atributos", "mestre atributos"]
ch = run(bot._autocomplete_comando(inter(212, "J"), "")); assert len(ch) == 17 and ch[0].value == "personagem criar" and not any(c.value.startswith("mestre ") for c in ch)
ch = run(bot._autocomplete_comando(inter(4, "M", roles=["Mestre"]), "")); assert len(ch) == 25 and all(len(c.name) <= 100 for c in ch)
print("M. /ajuda OK")

# ============================ N. reabrir a ficha e a chavinha ORDEM_DA_CRIACAO ============================
db.DB_PATH = os.path.join(tmp, "chavinha.db"); db.init_db()
# o mestre apaga um sorteio: a ficha volta a ficar incompleta e os comandos de jogo fecham até o jogador rolar de novo
n1 = inter(300, "Reabre"); run(bot.personagem_criar.callback(n1, "Ficha Pronta")); preparar(300, "Ficha Pronta"); db.set_attributes(row(300, "Ficha Pronta")["id"], {"vontade": 6})
assert tenta(bot.rolar, n1) is None and tenta(bot.rank, n1) is None
a300 = alvo(300, "Reabre"); run(bot.mestre_apagar.callback(gm, a300, "race", None))
m = tenta(bot.rolar, n1); assert m.startswith("🔒 A ficha de **Ficha Pronta**") and "▶️ Sortear a raça: `/raca_inicial`" in m
assert tenta(bot.historico, n1) is not None and tenta(bot.rank, n1) is not None
run(bot.atributos.callback(n1, None, None, None, None, None, 1, None)); assert "Ainda não dá pra usar `/atributos`" in txt(n1)     # e sem raça não distribui
with dados(40): run(bot.raca_inicial.callback(n1, None))
assert tenta(bot.rolar, n1) is None                                                                                                  # rolou de novo: reabriu
assert "incompleta" in ajuda.AJUDA["mestre apagar"]["detalhes"] and "os comandos de jogo dele fecham" in ajuda.AJUDA["mestre apagar"]["detalhes"]

# a chavinha: lê a variável de ambiente (só 0, false, nao, não e off desligam; sem nada, fica ligada)
for valor, esperado in [(None, True), ("1", True), ("", True), ("sim", True), ("0", False), ("false", False), ("FALSE", False), (" off ", False), ("não", False), ("nao", False)]:
    if valor is None: os.environ.pop("CHAVE_DE_TESTE", None)
    else: os.environ["CHAVE_DE_TESTE"] = valor
    assert bot._flag_ligada("CHAVE_DE_TESTE") is esperado, repr(valor)
os.environ.pop("CHAVE_DE_TESTE", None); assert bot.ORDEM_DA_CRIACAO is True                                                          # ligada por padrão
# desligada: tudo abre como antes da ordem (mas os passos continuam pedindo a raça, que os limites de atributo exigem)
bot.ORDEM_DA_CRIACAO = False
try:
    novo0 = inter(301, "Livre"); run(bot.personagem_criar.callback(novo0, "Sem Ordem"))
    for cmd in JOGO: assert tenta(cmd, novo0) is None, cmd.name                                     # ficha vazia e os quatro comandos abertos
    assert tenta(bot.rolar, inter(302, "Sem Personagem")) is None                                    # nem personagem precisa
    run(bot.minha_ficha.callback(novo0, None)); assert sent(novo0)[1]["embed"].description is None    # sem aviso de "ficha incompleta"
    run(bot.classe_escolher.callback(novo0, "Sábio", None)); assert titulo(novo0) == "🎓 Classe de Sem Ordem: Sábio"                     # a classe não exige os sorteios
    run(bot.atributos.callback(novo0, 2, None, None, None, None, None, None)); assert "Ainda não dá pra usar `/atributos`" in txt(novo0)   # sem raça, não
    db.set_race(row(301, "Sem Ordem")["id"], "Humano", 40)
    run(bot.atributos.callback(novo0, 2, None, None, None, None, None, None)); assert titulo(novo0).endswith("atualizados")            # com raça, vai, mesmo sem o resto
finally:
    bot.ORDEM_DA_CRIACAO = True
for cmd in JOGO: assert tenta(cmd, novo0) is not None, cmd.name                                     # ligada de novo: volta a fechar
print("N. reabrir a ficha e a chavinha OK")

print("\nTODOS OS TESTES DO BOT PASSARAM")
