"""Testes dos comandos do bot com interações simuladas (não conecta no Discord).
Rodar da pasta do bot: python tests/test_bot.py"""
import asyncio
import contextlib
import os
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
assert set(raiz) == {"rolar","historico","magia_inicial","raca_inicial","classe_social","minha_ficha","niveis","extrato_xp","rank","calcular_recursos","personagem","mestre"}, sorted(raiz)
pay = {n: c.to_dict(bot.bot.tree) for n, c in raiz.items()}
opt = lambda cmd, nome: next(o for o in cmd["options"] if o["name"] == nome)
sub_ = lambda g, n: next(o for o in pay[g]["options"] if o["name"] == n)
assert sorted(o["name"] for o in pay["personagem"]["options"]) == ["criar","excluir","listar","usar"]
assert sorted(o["name"] for o in pay["mestre"]["options"]) == sorted(["apagar","corrigir_estado","corrigir_magia","corrigir_nivel","corrigir_raca","dar_xp","excluir_personagem","ficha","jogador","rank_pericia","upar","vagas"])
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
todos = list(bot.mestre_grupo.commands); assert len(todos) == 12
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

print("\nTODOS OS TESTES DO BOT PASSARAM")
