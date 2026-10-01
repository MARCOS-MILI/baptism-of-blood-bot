"""Testes dos comandos do bot com interações simuladas (não conecta no Discord).
Rodar da pasta do bot: python tests/test_bot.py"""
import asyncio
import contextlib
import os
import re
import sqlite3
import sys
import tempfile
import unicodedata
from datetime import datetime
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
for k in ("DB_PATH", "RAILWAY_VOLUME_MOUNT_PATH"):
    os.environ.pop(k, None)

import discord
from discord import app_commands

os.environ["BAIXAR_IMAGENS"] = "0"      # o teste nunca mexe na rede: o download dos gifs tem teste próprio, com um baixador de mentira
import bot
import db
import habil
import dice
import lore
import paineis
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
    i.response.send_modal = AsyncMock(); i.edit_original_response = AsyncMock()
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
    return (c or "") + ((" | " + (e.author.name or "") + " | " + (e.title or "") + " | " + (e.description or "") + " | " + " ; ".join(f"{f.name}={f.value}" for f in e.fields)) if e else "")

def desc(i): return sent(i)[1]["embed"].description
def nome_do_cartao(e):
    """O título do cartão: o embed.title, ou (nos cartões decorados, que não têm título) o rótulo do cabeçalho."""
    if e.title: return e.title
    linha = re.sub(r"<a?:\w+:\d+>", "", e.description.split("\n")[0])
    for enfeite in (lore.PREENCHE, lore.ORNAMENTO_L, lore.NULO, lore.HIEROGLIFO): linha = linha.replace(enfeite, "")
    return unicodedata.normalize("NFKC", linha).strip()
def titulo(i): return nome_do_cartao(sent(i)[1]["embed"])
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
assert set(raiz) == {"rolar","historico","magia_inicial","raca_inicial","classe_social","classe","atributos","minha_ficha","niveis","extrato_xp","rank","calcular_recursos","ajuda","help","dados","disciplinas","iniciativa","intencao","habilidade","pericias","habilidades","personagem","mestre"}, sorted(raiz)
pay = {n: c.to_dict(bot.bot.tree) for n, c in raiz.items()}
opt = lambda cmd, nome: next(o for o in cmd["options"] if o["name"] == nome)
sub_ = lambda g, n: next(o for o in pay[g]["options"] if o["name"] == n)
assert sorted(o["name"] for o in pay["personagem"]["options"]) == ["criar","excluir","listar","usar"]
assert sorted(o["name"] for o in pay["mestre"]["options"]) == sorted(["apagar","apagar_historico","atributos","corrigir_classe","disciplina","escudo","sorte","ajuda","habilidades","pericia","comecar_aqui","corrigir_estado","corrigir_magia","corrigir_nivel","corrigir_raca","dar_xp","excluir_personagem","exportar","ficha","jogador","rank_pericia","upar","vagas"])
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
assert [c["value"] for c in opt(cr, "classe")["choices"]] == ["Nenhuma","Caçador","Clérigo","Feiticeiros","Ladrão","Mercenário","Mestre de Forja","Mundano","Sábio"]
assert pay["mestre"].get("dm_permission") is False or pay["mestre"].get("contexts") == [0]
at = pay["atributos"]; assert [o["name"] for o in at["options"]] == ["forca","destreza","vitalidade","razao","vontade","alma","personagem"] and req(at["options"]) == set()
assert all((opt(at, a)["min_value"], opt(at, a)["max_value"]) == (0, 20) for a in ("forca","destreza","vitalidade","razao","vontade","alma")) and opt(at, "personagem")["autocomplete"] is True
assert [c["value"] for c in opt(pay["classe"], "classe")["choices"]] == ["Caçador","Clérigo","Feiticeiros","Ladrão","Mercenário","Mestre de Forja","Mundano","Sábio"] and req(pay["classe"]["options"]) == {"classe"}
ma = sub_("mestre", "atributos"); assert req(ma["options"]) == {"usuario"} and all((opt(ma, a)["min_value"], opt(ma, a)["max_value"]) == (0, 30) for a in ("forca","alma"))
ph = pay["habilidade"]; assert [o["name"] for o in ph["options"]] == ["escolha", "personagem"] and req(ph["options"]) == set() and opt(ph, "escolha").get("autocomplete") and opt(ph, "personagem").get("autocomplete")
assert len(ph["description"]) <= 100 and "3#d20+5" in opt(pay["rolar"], "dado")["description"] and len(opt(pay["rolar"], "dado")["description"]) <= 100
ms = sub_("mestre", "sorte"); assert req(ms["options"]) == {"usuario", "efeito"} and len(ms["description"]) <= 100 and all(len(o["description"]) <= 100 for o in ms["options"])
assert [c["value"] for c in opt(ms, "efeito")["choices"]] == ["vantagem", "desvantagem", "bonus", "penalidade", "minimo", "maximo", "fixo", "ver", "limpar"] and all(len(c["name"]) <= 100 for c in opt(ms, "efeito")["choices"])
assert (opt(ms, "valor")["min_value"], opt(ms, "valor")["max_value"], opt(ms, "usos")["min_value"], opt(ms, "usos")["max_value"], opt(ms, "motivo")["max_length"]) == (1, 20, 1, 20, 100) and opt(ms, "discreto")["type"] == 5
mc = sub_("mestre", "corrigir_classe"); assert req(mc["options"]) == {"usuario", "classe"} and [c["value"] for c in opt(mc, "classe")["choices"]] == ["Caçador","Clérigo","Feiticeiros","Ladrão","Mercenário","Mestre de Forja","Mundano","Sábio"]
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
run(bot.magia_inicial.callback(marcos, None)); assert "Ainda não dá pra usar `/magia_inicial`" in txt(marcos) and row(1, "Kairon Flagon")["magic_rank"] is None   # sem raça nem classe: fechado
with dados(96): run(bot.raca_inicial.callback(marcos, None))                                                # 96 é Dhampir
assert "Raça de Kairon Flagon" in txt(marcos) and titulo(marcos) == "Dhampirs" and row(1, "Kairon Flagon")["race"] == "Dhampir"
run(bot.raca_inicial.callback(marcos, None))                                                                 # já tem raça: pergunta antes de trocar, e não rola nada
assert titulo(marcos) == "🔄 Rolar a raça de novo?" and isinstance(sent(marcos)[1]["view"], paineis.ConfirmarRepeticao) and sent(marcos)[1]["ephemeral"]
assert "**Dhampir**" in desc(marcos) and "troca esse resultado" in desc(marcos) and "sobram 1" in desc(marcos) and row(1, "Kairon Flagon")["race_attempts"] == 1
with dados(50): run(bot.raca_inicial.callback(marcos, "Akari Amaya"))
assert "Raça de Akari Amaya" in txt(marcos) and titulo(marcos) == "Humanos"
# o Rank de magia vem depois da raça e da classe, e só pra quem tem magia (Dhampir só com classe mágica: Kairon é Mestre de Forja)
with dados(20): run(bot.classe_social.callback(marcos, None))
run(bot.magia_inicial.callback(marcos, None)); assert "Ainda não dá pra usar `/magia_inicial`" in txt(marcos) and "▶️ Escolher a classe: `/classe`" in txt(marcos)
run(bot.classe_escolher.callback(marcos, "Mestre de Forja", None)); assert titulo(marcos).endswith("Mestre de Forja")
with dados(50): run(bot.magia_inicial.callback(marcos, None))
assert "Magia Inicial de Kairon Flagon" in txt(marcos) and row(1, "Kairon Flagon")["magic_rank"] == "Raro"
run(bot.magia_inicial.callback(marcos, None)); assert "já tem Rank de Magia" in txt(marcos)
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
todos = list(bot.mestre_grupo.commands); assert len(todos) == 23
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
assert titulo(p1) == "3° Estado —  Camponeses" and "Classe Social de" in txt(p1) and "🎲" not in desc(p1) and rodape(p1) == "jogador: Ana · tentativa 1 de 3" and "content" not in sent(p1)[1] and [h["purpose"] for h in historico_de(10)] == ["classe_social"]
with dados(): run(bot.classe_social.callback(p1, None))
assert titulo(p1) == "🔄 Rolar a classe social de novo?" and sent(p1)[1]["ephemeral"] and "3º Estado · Camponeses" in desc(p1) and row(10, "Ana Camponesa")["social_class_attempts"] == 1
for n, esperado in [(80, "3° Estado —  Camponeses"), (81, "2° Estado —  Nobreza"), (91, "2° Estado —  Nobreza")]:
    u = novo(20 + n, f"J{n}", f"Fulano {n}")
    with dados(n): run(bot.classe_social.callback(u, None))
    assert titulo(u) == esperado and "🎲" not in desc(u) and rodape(u) == f"jogador: J{n} · tentativa 1 de 3" and len(historico_de(20 + n)) == 1
for n1, n2, clero in [(92, 49, "Baixo Clero"), (92, 50, "Alto Clero"), (99, 100, "Alto Clero"), (95, 1, "Baixo Clero")]:
    u = novo(300 + n1 + n2, "Clerigo", "Padre Teste")
    with dados(n1, n2): run(bot.classe_social.callback(u, None))
    assert titulo(u) == "1° Estado —  Clero" and "🎲" not in desc(u) and f"✝ {clero}=" in txt(u)
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
with dados(10, 20): run(bot.raca_inicial.callback(z, None)); run(bot.classe_social.callback(z, None))
db.set_class(row(50, "Zé Pleno")["id"], "Feiticeiros")
with dados(30): run(bot.magia_inicial.callback(z, None))
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
assert titulo(r) == "Dhampirs" and "Meio humano" not in txt(r) and not sent(r)[1].get("ephemeral")            # continua público
print("H. horário e Dhampir OK")

# ============================ I. ficha automática: classe, atributos e recursos ============================
db.DB_PATH = os.path.join(tmp, "ficha.db"); db.init_db()
CAMPOS = ["Nível", "Raça", "Classe Social", "Rank de Magia", "Classe", "Atributos", "Recursos", "Ranks das perícias especiais"]
def campos(i): return {f.name: f.value for f in sent(i)[1]["embed"].fields}
def preparar(uid, nome, raca="Humano", classe="Caçador"):
    """Sorteios feitos, classe escolhida e, se a combinação tem magia, o Rank de magia (direto no banco)."""
    c = row(uid, nome)["id"]
    db.set_race(c, raca, 40); db.set_social_status(c, "3º Estado", 10)
    if rules.magic_access(raca, classe) == "sim": db.set_magic_rank(c, "Comum", 10)
    if classe: db.set_class(c, classe)
ana = novo(100, "Ana", "Ana Ficha"); a100 = alvo(100, "Ana"); ficha = lambda: row(100, "Ana Ficha")

# ficha nova: tudo zerado, e os campos novos ficam antes dos ranks, que continuam por último
run(bot.minha_ficha.callback(ana, None)); assert [f.name for f in sent(ana)[1]["embed"].fields] == CAMPOS
c = campos(ana); assert c["Classe"] == "ainda não definida\n(use `/classe`)" and c["Recursos"] == bot._SEM_CLASSE
assert c["Rank de Magia"] == "depende da raça e da classe\n(fica claro depois de escolher as duas)"
assert c["Atributos"] == "Força 0 · Destreza 0 · Vitalidade 0 · Razão 0 · Vontade 0 · Alma 0\nPontos de atributo: 0 de 6 usados (6 livres)"
run(bot.atributos.callback(ana, None, None, None, None, None, None, None))                # sem números: só mostra
assert sent(ana)[1]["ephemeral"] and titulo(ana) == "🧬 Atributos de Ana Ficha" and list(campos(ana)) == ["Atributos", "Recursos"]
# a ordem da criação: /atributos e /classe ficam fechados enquanto faltam passos antes
run(bot.minha_ficha.callback(ana, None)); e = sent(ana)[1]["embed"]
assert e.description.startswith("⚠️ **Ficha incompleta.** Próximo passo: `/raca_inicial`") and "/ajuda" in e.description
run(bot.atributos.callback(ana, 2, None, 3, None, 1, None, None)); print("  ", txt(ana).splitlines()[0])
assert "Ainda não dá pra usar `/atributos`" in txt(ana) and "▶️ Sortear a raça: `/raca_inicial`" in txt(ana) and "🔒 Escolher a classe: depois de sortear a raça e a classe social" in txt(ana)
assert sent(ana)[1]["ephemeral"] and db.attributes_of(ficha())["forca"] == 0
run(bot.classe_escolher.callback(ana, "Caçador", None)); assert "Ainda não dá pra usar `/classe`" in txt(ana) and ficha()["class_name"] is None
# a raça e a classe social, em qualquer ordem, abrem a classe
with dados(40, 20): run(bot.raca_inicial.callback(ana, None)); run(bot.classe_social.callback(ana, None))
assert (ficha()["race"], ficha()["magic_rank"], ficha()["social_class"]) == ("Humano", None, "3º Estado")
run(bot.atributos.callback(ana, 2, None, 3, None, 1, None, None))                          # sorteios feitos, mas ainda falta a classe
assert "Ainda não dá pra usar `/atributos`" in txt(ana) and "▶️ Escolher a classe: `/classe`" in txt(ana) and db.attributes_of(ficha())["forca"] == 0
run(bot.minha_ficha.callback(ana, None)); assert "Próximo passo: `/classe`" in sent(ana)[1]["embed"].description

# classe: vale uma vez, mostra bônus e vantagem
run(bot.classe_escolher.callback(ana, "Caçador", None)); print("  ", desc(ana).splitlines()[0:2])
assert titulo(ana) == "Caçador" and "Classe de Ana Ficha" in txt(ana) and "Vantagem nas perícias=Religião e Luta ou Pontaria" in txt(ana)
assert "Bônus=Vida +35 · Sanidade +15 · Mana +5 · Estamina +20" in txt(ana) and "/atributos" in txt(ana) and sent(ana)[1]["ephemeral"]
run(bot.classe_escolher.callback(ana, "Sábio", None)); assert "já é da classe **Caçador**" in txt(ana) and ficha()["class_name"] == "Caçador"
run(bot.minha_ficha.callback(ana, None)); c = campos(ana)
assert c["Classe"] == "Caçador\n(vantagem em Religião e Luta ou Pontaria)\n✨ Sem Dúvidas"
assert c["Rank de Magia"] == "sem magia\n(só Vampiros, Dhampirs, Feiticeiros e Mestres de Forja têm magia)"
n_antes = len(historico_de(100)); run(bot.magia_inicial.callback(ana, None)); m = txt(ana)
assert m.startswith("🚫 **Ana Ficha** não sorteia o Rank de magia") and "essa combinação é Humano com Caçador" in m and sent(ana)[1]["ephemeral"]
assert ficha()["magic_rank"] is None and len(historico_de(100)) == n_antes           # recusou sem rolar dado nenhum
run(bot.minha_ficha.callback(ana, None))                                                   # a próxima checagem lê a última resposta
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
run(bot.classe_escolher.callback(ana, "Ladrão", None, "Fantasma")); assert "Não achei" in txt(ana)
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
# "grau" é palavra das Disciplinas: só o /disciplinas e o /mestre disciplina podem usar
fora = [n for n, d in pay.items() if n not in ("disciplinas", "mestre") and any("grau" in t.lower() for t in todas(d))]
fora += [f"mestre {o['name']}" for o in pay["mestre"]["options"] if o["name"] != "disciplina" and any("grau" in t.lower() for t in todas(o))]
assert fora == [], fora
assert any("grau" in t.lower() for t in todas(next(o for o in pay["mestre"]["options"] if o["name"] == "disciplina")))

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
assert "Próximo passo: sortear a raça e a classe social (`/raca_inicial` e `/classe_social`, em qualquer ordem)." in desc(p0)
assert "Depois vêm `/classe`, o Rank de magia (`/magia_inicial`, só pra quem tem magia) e `/atributos`. O passo a passo completo está em `/ajuda`." in desc(p0)
# com o personagem criado, tudo de jogo fica fechado, e a mensagem diz o que fazer
for cmd in JOGO:
    m = tenta(cmd, p0); assert m.startswith("🔒 A ficha de **Recém Chegado** ainda não está pronta, e esse comando só abre quando ela estiver."), cmd.name
    assert "▶️ Sortear a raça: `/raca_inicial`" in m and "Próximo passo: `/raca_inicial`" in m and "`/ajuda`" in m and len(m) < 2000
print("  ", tenta(bot.rolar, p0).splitlines()[0])
assert tenta(bot.rolar, p0, "Recém Chegado") and tenta(bot.extrato_xp, p0, "Recém Chegado")                  # pelo nome também fecha
assert tenta(bot.rolar, p0, "Fantasma") is None                                                                # nome que não existe: o próprio comando avisa
# passo a passo, um de cada vez, pelos comandos de verdade (Humano Sábio: não tem magia)
run(bot.magia_inicial.callback(p0, None)); assert "Ainda não dá pra usar `/magia_inicial`" in txt(p0)                      # o Rank de magia só vem depois da raça e da classe
with dados(40): run(bot.raca_inicial.callback(p0, None))
m = tenta(bot.rolar, p0); assert "✅ Sortear a raça" in m and "▶️ Sortear a classe social: `/classe_social`" in m and "🔒 Escolher a classe: depois de sortear a classe social" in m
with dados(20): run(bot.classe_social.callback(p0, None))
m = tenta(bot.rolar, p0); assert "▶️ Escolher a classe: `/classe`" in m and "🔒 Sortear o Rank de magia: depois de escolher a classe" in m
assert "🔒 Distribuir os pontos de atributo: depois de escolher a classe e de sortear o Rank de magia" in m
run(bot.classe_escolher.callback(p0, "Sábio", None))
assert "Sua raça e sua classe não têm magia, então você não sorteia o Rank de magia." in txt(p0) and "Próximo passo: `/atributos`" in txt(p0)
m = tenta(bot.rolar, p0); assert "▶️ Distribuir os pontos de atributo: `/atributos` (0 de 6 pontos usados)" in m and "Próximo passo: `/atributos`" in m
assert "➖ Rank de magia: a sua raça e a sua classe não têm magia, então esse passo não vale pra você" in m
run(bot.magia_inicial.callback(p0, None)); assert txt(p0).startswith("🚫 **Recém Chegado** não sorteia o Rank de magia") and row(200, "Recém Chegado")["magic_rank"] is None
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
with dados(100, 40): run(bot.classe_social.callback(e6, None)); run(bot.raca_inicial.callback(e6, None))
assert "⏳ Classe social: você tirou 100, então um mestre vai definir o seu Estado" in tenta(bot.rolar, e6)
run(bot.classe_escolher.callback(e6, "Caçador", None)); print("  ", txt(e6))
assert txt(e6) == ("Ainda não dá pra usar `/classe`: você tirou 100 no sorteio da classe social, então um mestre precisa definir o seu "
                   "Estado primeiro. Fala com ele.") and row(206, "Sorte Grande")["class_name"] is None
run(bot.mestre_corrigir_estado.callback(gm, a206, "3", None))
run(bot.classe_escolher.callback(e6, "Caçador", None)); assert titulo(e6) == "Caçador" and "Classe de Sorte Grande" in txt(e6)                # o mestre decidiu: destravou

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
assert "depois de sortear a raça e a classe social" in ajuda.AJUDA["classe"]["requisito"]
assert "depois de escolher a classe" in ajuda.AJUDA["atributos"]["requisito"] and "Rank de magia" in ajuda.AJUDA["atributos"]["requisito"]
assert "só se a sua raça ou a sua classe tiver magia" in ajuda.AJUDA["magia_inicial"]["requisito"] and "Vampiro" in ajuda.AJUDA["magia_inicial"]["detalhes"]
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
assert "Comandos de mestre" not in [f.name for f in e.fields] and "/mestre dar_xp" not in str(e.to_dict()) and "Você ainda não tem personagem" in e.fields[0].value      # a ajuda geral não lista os de mestre, nem pra mestre
assert e.description.endswith("🛡️ Você é mestre: os comandos de mestre ficam separados, em `/mestre ajuda`.")
assert len(e) <= 6000 and all(len(f.value) <= 1024 for f in e.fields)

# /ajuda de um comando
run(bot.ajuda_comando.callback(h, "atributos")); e = sent(h)[1]["embed"]
assert sent(h)[1]["ephemeral"] and e.title == "📖 /atributos" and e.description.startswith("Distribui os pontos de atributo.")
assert {f.name: f.value for f in e.fields}["Como usar"] == "`/atributos forca:2 vitalidade:3 vontade:1`" and "Só depois de escolher a classe" in {f.name: f.value for f in e.fields}["Quando dá pra usar"]
run(bot.ajuda_comando.callback(h, "/ROLAR")); assert sent(h)[1]["embed"].title == "📖 /rolar"
run(bot.ajuda_comando.callback(h, "dar_xp")); assert txt(h) == 'Não achei nenhum comando com "dar_xp". Use `/ajuda` pra ver a lista de comandos.' and sent(h)[1]["ephemeral"]      # o jogador não descobre os comandos de mestre
run(bot.ajuda_comando.callback(h, "ficha")); assert sent(h)[1]["embed"].title == "📖 /minha_ficha"                              # jogador tem preferência
run(bot.ajuda_comando.callback(h, "personagem")); print("  ", txt(h)); assert txt(h).startswith('Não achei nenhum comando com "personagem". Quis dizer: `/personagem criar`') and sent(h)[1]["ephemeral"]
run(bot.ajuda_comando.callback(h, "xyzabc")); assert txt(h) == 'Não achei nenhum comando com "xyzabc". Use `/ajuda` pra ver a lista de comandos.'
# /help é a mesma coisa
for arg in (None, "atributos", "rolar", "xyz"):
    a, b = inter(211, "A"), inter(211, "A"); run(bot.ajuda_comando.callback(a, arg)); run(bot.help_comando.callback(b, arg))
    assert txt(a) == txt(b) and sent(a)[1] == sent(b)[1] or (sent(a)[1]["embed"].to_dict() == sent(b)[1]["embed"].to_dict())
# autocomplete do /ajuda: os comandos de mestre não aparecem pra ninguém (ficam no /mestre ajuda)
ch = run(bot._autocomplete_comando(inter(212, "J"), "atrib")); assert [(c.name, c.value) for c in ch] == [("/atributos", "atributos")]
ch = run(bot._autocomplete_comando(inter(4, "M", roles=["Mestre"]), "atrib")); assert [c.value for c in ch] == ["atributos"]
ch = run(bot._autocomplete_comando(inter(212, "J"), "")); assert len(ch) == 24 and ch[0].value == "personagem criar" and not any(c.value.startswith("mestre ") for c in ch)
ch = run(bot._autocomplete_comando(inter(4, "M", roles=["Mestre"]), "")); assert len(ch) == 24 and not any(c.value.startswith("mestre ") for c in ch) and all(len(c.name) <= 100 for c in ch)
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
    run(bot.classe_escolher.callback(novo0, "Sábio", None)); assert titulo(novo0) == "Sábio" and "Classe de Sem Ordem" in txt(novo0)                     # a classe não exige os sorteios
    run(bot.atributos.callback(novo0, 2, None, None, None, None, None, None)); assert "Ainda não dá pra usar `/atributos`" in txt(novo0)   # sem raça, não
    db.set_race(row(301, "Sem Ordem")["id"], "Humano", 40)
    run(bot.atributos.callback(novo0, 2, None, None, None, None, None, None)); assert titulo(novo0).endswith("atualizados")            # com raça, vai, mesmo sem o resto
finally:
    bot.ORDEM_DA_CRIACAO = True
for cmd in JOGO: assert tenta(cmd, novo0) is not None, cmd.name                                     # ligada de novo: volta a fechar
print("N. reabrir a ficha e a chavinha OK")

# ============================ O. quem tem magia: Vampiro (qualquer classe), Feiticeiros e Mestre de Forja ============================
db.DB_PATH = os.path.join(tmp, "magia.db"); db.init_db()
def montar(uid, jogador, personagem, raca=None, classe=None, estado="3º Estado"):
    """Personagem criado, com raça, classe social e classe já definidas (direto no banco)."""
    i = novo(uid, jogador, personagem); c = row(uid, personagem)["id"]
    if raca: db.set_race(c, raca, 40)
    if estado: db.set_social_status(c, estado, 10)
    if classe: db.set_class(c, classe)
    return i

# quem TEM magia rola o Rank: Vampiro e Dhampir de qualquer classe, Feiticeiros e Mestre de Forja
for uid, raca, classe in [(400, "Vampiro", "Mundano"), (401, "Vampiro", "Ladrão"), (402, "Humano", "Feiticeiros"),
                          (403, "Humano", "Mestre de Forja"), (404, "Dhampir", "Feiticeiros"), (405, "Vampiro", "Feiticeiros"),
                          (406, "Dhampir", "Sábio"), (407, "Dhampir", "Caçador"), (408, "Dhampir", "Mundano")]:
    i = montar(uid, f"J{uid}", f"P{uid}", raca, classe)
    with dados(60): run(bot.magia_inicial.callback(i, None))
    assert titulo(i) == "Rank Raro" and f"Magia Inicial de P{uid}" in txt(i) and row(uid, f"P{uid}")["magic_rank"] == "Raro" and not sent(i)[1].get("ephemeral"), (raca, classe)
# quem NÃO tem magia é recusado, sem rolar dado nenhum e sem mexer no histórico
for uid, raca, classe in [(410, "Humano", "Mundano"), (411, "Humano", "Caçador"), (412, "Humano", "Ladrão"), (413, "Humano", "Sábio")]:
    i = montar(uid, f"J{uid}", f"P{uid}", raca, classe); n = len(historico_de(uid))
    with dados(): run(bot.magia_inicial.callback(i, None))                                     # dados() vazio: rolar dado seria erro
    m = txt(i)
    assert m.startswith(f"🚫 **P{uid}** não sorteia o Rank de magia") and f"essa combinação é {raca} com {classe}." in m and sent(i)[1]["ephemeral"], (raca, classe)
    assert "Próximo passo: `/atributos`" in m and row(uid, f"P{uid}")["magic_rank"] is None and len(historico_de(uid)) == n
# o Rank de magia vem DEPOIS da raça e da classe: antes disso, fechado
v = montar(420, "V", "Vampiro Sem Classe", "Vampiro", None)
run(bot.magia_inicial.callback(v, None)); assert "Ainda não dá pra usar `/magia_inicial`" in txt(v) and "▶️ Escolher a classe: `/classe`" in txt(v)
f = montar(421, "F", "Feiticeiro Sem Raça", None, "Feiticeiros")                                     # classe feita por um mestre, sem a raça
run(bot.magia_inicial.callback(f, None)); assert "Ainda não dá pra usar `/magia_inicial`" in txt(f) and "▶️ Sortear a raça: `/raca_inicial`" in txt(f)
sr = montar(422, "S", "Sem Raça Nem Classe", None, None, estado=None)
run(bot.magia_inicial.callback(sr, None)); assert "Ainda não dá pra usar `/magia_inicial`" in txt(sr) and row(422, "Sem Raça Nem Classe")["magic_rank"] is None
# já sorteou: continua dizendo que já tem
m400 = inter(400, "J400"); run(bot.magia_inicial.callback(m400, None)); assert "já tem Rank de Magia: **Raro**" in txt(m400)

# o /classe já diz se o personagem tem magia e qual é o próximo passo
c1 = montar(430, "C1", "Classe Sem Magia", "Humano", None); run(bot.classe_escolher.callback(c1, "Sábio", None))
assert "Sua raça e sua classe não têm magia, então você não sorteia o Rank de magia." in txt(c1) and "Próximo passo: `/atributos`" in txt(c1)
c2 = montar(431, "C2", "Classe Vampira", "Vampiro", None); run(bot.classe_escolher.callback(c2, "Mundano", None))
assert "Sua raça ou sua classe tem magia." in txt(c2) and "Próximo passo: `/magia_inicial`" in txt(c2) and "não têm magia" not in txt(c2)
c3 = montar(432, "C3", "Classe Feiticeira", "Humano", None); run(bot.classe_escolher.callback(c3, "Feiticeiros", None))
assert "Sua raça ou sua classe tem magia." in txt(c3) and "Próximo passo: `/magia_inicial`" in txt(c3)
c4 = montar(433, "C4", "Classe Forjadora", "Humano", None); run(bot.classe_escolher.callback(c4, "Mestre de Forja", None)); assert "Próximo passo: `/magia_inicial`" in txt(c4)

# a ficha e a lista de personagens mostram a situação de cada um
e1 = montar(440, "E1", "Elegível", "Vampiro", "Mundano"); run(bot.minha_ficha.callback(e1, None))
assert campos(e1)["Rank de Magia"] == "ainda não definido\n(use `/magia_inicial`)"; run(bot.personagem_listar.callback(e1)); assert "magia: sem rank" in desc(e1)
e2 = montar(441, "E2", "Sem Magia", "Humano", "Mundano"); run(bot.minha_ficha.callback(e2, None))
assert campos(e2)["Rank de Magia"] == "sem magia\n(só Vampiros, Dhampirs, Feiticeiros e Mestres de Forja têm magia)"; run(bot.personagem_listar.callback(e2)); assert "magia: sem magia" in desc(e2)
e3 = montar(442, "E3", "Indefinido", "Humano", None); run(bot.minha_ficha.callback(e3, None))
assert campos(e3)["Rank de Magia"] == "depende da raça e da classe\n(fica claro depois de escolher as duas)"; run(bot.personagem_listar.callback(e3)); assert "magia: sem rank" in desc(e3)
e4 = montar(443, "E4", "Dado Antigo", "Humano", "Mundano"); db.set_magic_rank(row(443, "Dado Antigo")["id"], "Raro", 62)      # Rank guardado de antes da regra
run(bot.minha_ficha.callback(e4, None)); assert campos(e4)["Rank de Magia"] == "Raro\n(1d100: 62)\n⚠️ raça e classe sem magia, fala com um mestre"
run(bot.personagem_listar.callback(e4)); assert "magia: Raro" in desc(e4)
db.set_attributes(row(443, "Dado Antigo")["id"], {"vontade": 6}); assert tenta(bot.rolar, e4) is None                       # o dado antigo não trava a ficha
run(bot.minha_ficha.callback(e4, None)); assert "Ficha incompleta" not in (sent(e4)[1]["embed"].description or "")

# os mestres são avisados quando corrigir a raça ou a classe muda se o personagem tem magia
g1 = montar(450, "G1", "Nota Um", "Humano", "Mundano"); a450 = alvo(450, "G1")
run(bot.mestre_corrigir_raca.callback(gm, a450, "Vampiro", None)); assert "Agora **Nota Um** tem magia e precisa sortear o Rank de magia com `/magia_inicial`." in desc(gm)
run(bot.mestre_corrigir_raca.callback(gm, a450, "Dhampir", None)); assert "magia" not in desc(gm).split("→")[-1]              # sim -> sim (Dhampir também tem magia): nada a avisar
run(bot.mestre_corrigir_raca.callback(gm, a450, "Humano", None)); assert "Com essa combinação **Nota Um** não tem magia." in desc(gm) and "continua na ficha" not in desc(gm)   # sim -> não, sem Rank guardado
run(bot.mestre_corrigir_raca.callback(gm, a450, "Humano", None)); assert "magia" not in desc(gm).split("→")[-1]                # não -> não: nada a avisar
db.set_magic_rank(row(450, "Nota Um")["id"], "Comum", 10)
run(bot.mestre_corrigir_raca.callback(gm, a450, "Vampiro", None)); assert "precisa sortear" not in desc(gm)                        # já tem o Rank: nada a sortear
run(bot.mestre_corrigir_raca.callback(gm, a450, "Humano", None))
assert "Com essa combinação **Nota Um** não tem magia. O Rank de magia (Comum) continua na ficha; use `/mestre apagar` se quiser tirar." in desc(gm)
g2 = montar(451, "G2", "Nota Dois", "Humano", "Feiticeiros"); a451 = alvo(451, "G2")
run(bot.mestre_corrigir_classe.callback(gm, a451, "Mestre de Forja", None)); assert "não tem magia" not in desc(gm) and "precisa sortear" not in desc(gm)   # continua com magia
run(bot.mestre_corrigir_classe.callback(gm, a451, "Sábio", None)); assert "Com essa combinação **Nota Dois** não tem magia." in desc(gm)
run(bot.mestre_corrigir_classe.callback(gm, a451, "Feiticeiros", None)); assert "Agora **Nota Dois** tem magia e precisa sortear o Rank de magia com `/magia_inicial`." in desc(gm)
# o mestre pode passar por cima e dar o Rank a quem não tem magia (a ficha mostra o aviso), e depois apagar
g3 = montar(452, "G3", "Exceção", "Humano", "Mundano"); a452 = alvo(452, "G3")
run(bot.mestre_corrigir_magia.callback(gm, a452, "Lendário", None)); assert row(452, "Exceção")["magic_rank"] == "Lendário" and "não tem magia" not in desc(gm)
run(bot.minha_ficha.callback(g3, None)); assert "⚠️ raça e classe sem magia, fala com um mestre" in campos(g3)["Rank de Magia"] and "definido por um mestre" in campos(g3)["Rank de Magia"]
run(bot.mestre_apagar.callback(gm, a452, "magic_rank", None)); assert row(452, "Exceção")["magic_rank"] is None
run(bot.minha_ficha.callback(g3, None)); assert campos(g3)["Rank de Magia"].startswith("sem magia")

# de ponta a ponta pelos comandos: Vampiro Mundano precisa do Rank; Humano Sábio segue direto pros atributos
vp = inter(460, "Vampira"); run(bot.personagem_criar.callback(vp, "Vampira Mundana"))
with dados(90, 50): run(bot.raca_inicial.callback(vp, None)); run(bot.classe_social.callback(vp, None))
run(bot.classe_escolher.callback(vp, "Mundano", None)); assert "Próximo passo: `/magia_inicial`" in txt(vp)
run(bot.atributos.callback(vp, None, None, None, None, 6, None, None)); assert "Ainda não dá pra usar `/atributos`" in txt(vp) and "▶️ Sortear o Rank de magia: `/magia_inicial`" in txt(vp)
assert "Sortear o Rank de magia" in tenta(bot.rolar, vp)
with dados(70): run(bot.magia_inicial.callback(vp, None))
assert row(460, "Vampira Mundana")["race"] == "Vampiro" and row(460, "Vampira Mundana")["magic_rank"] == "Raro"
run(bot.atributos.callback(vp, None, None, None, None, 6, None, None)); assert titulo(vp).endswith("atualizados") and tenta(bot.rolar, vp) is None
hs = inter(461, "Humano"); run(bot.personagem_criar.callback(hs, "Humano Sábio"))
with dados(40, 50): run(bot.raca_inicial.callback(hs, None)); run(bot.classe_social.callback(hs, None))
run(bot.classe_escolher.callback(hs, "Sábio", None)); assert "Próximo passo: `/atributos`" in txt(hs)
run(bot.atributos.callback(hs, None, None, None, None, 6, None, None)); assert titulo(hs).endswith("atualizados") and tenta(bot.rolar, hs) is None      # pronto sem nunca ter magia
assert row(461, "Humano Sábio")["magic_rank"] is None

# chavinha desligada: quem tem raça ou classe indefinida pode rolar (como antes da ordem), mas a regra de quem NÃO tem magia continua
bot.ORDEM_DA_CRIACAO = False
try:
    l1 = montar(470, "L1", "Livre Um", "Humano", None)
    with dados(30): run(bot.magia_inicial.callback(l1, None))
    assert row(470, "Livre Um")["magic_rank"] == "Comum"
    l2 = montar(471, "L2", "Livre Dois", "Humano", "Mundano")
    with dados(): run(bot.magia_inicial.callback(l2, None))
    assert txt(l2).startswith("🚫 **Livre Dois** não sorteia o Rank de magia") and row(471, "Livre Dois")["magic_rank"] is None
finally:
    bot.ORDEM_DA_CRIACAO = True
print("O. quem tem magia OK")

# ============================ P. /mestre apagar_historico ============================
db.DB_PATH = os.path.join(tmp, "apagahist.db"); db.init_db()
pay = {c.name: c.to_dict(bot.bot.tree) for c in bot.bot.tree.get_commands()}
ah = sub_("mestre", "apagar_historico")
assert [o["name"] for o in ah["options"]] == ["usuario"] and req(ah["options"]) == {"usuario"} and len(ah["description"]) <= 100
assert "apagar_historico" in [o["name"] for o in pay["mestre"]["options"]]

# a Ana tem rolagens de dois personagens, sorteios de criação e rolagens sem personagem; o Beto tem as dele
ana = novo(500, "Ana", "Ana Um"); run(bot.personagem_criar.callback(ana, "Ana Dois")); a500 = alvo(500, "Ana")
um, dois = row(500, "Ana Um")["id"], row(500, "Ana Dois")["id"]
db.set_race(um, "Humano", 40, ); db.add_xp(um, 1500, "teste", "9", "M")
for i in range(5): db.log_roll("500", "Ana", "g", "1d20", [i + 1], i + 1, "teste", um, "Ana Um")
for i in range(3): db.log_roll("500", "Ana", "g", "1d100", [40], 40, "raca_inicial", dois, "Ana Dois")
for i in range(2): db.log_roll("500", "Ana", "g", "1d6", [3], 3, None, None, None)
beto = novo(501, "Beto", "Beto Solo"); a501 = alvo(501, "Beto")
for i in range(4): db.log_roll("501", "Beto", "g", "1d20", [7], 7, None, None, None)
assert (db.count_rolls("500"), db.count_rolls("501")) == (10, 4)

# quem não tem rolagem: só avisa, sem botões
vazio = novo(502, "Vazio", "Sem Rolagem"); run(bot.mestre_apagar_historico.callback(gm, alvo(502, "Vazio")))
assert txt(gm) == "Vazio não tem nenhuma rolagem no histórico." and sent(gm)[1]["ephemeral"] and "view" not in sent(gm)[1]
# um jogador com UMA rolagem: fala no singular
db.log_roll("502", "Vazio", "g", "1d20", [4], 4, None, None, None)
run(bot.mestre_apagar_historico.callback(gm, alvo(502, "Vazio"))); assert "**1 rolagem**" in desc(gm) and "**1 rolagens**" not in desc(gm)

async def apagar_com_botoes():
    u = inter(4, "Mestre Belmont", roles=["Mestre"]); await bot.mestre_apagar_historico.callback(u, a500)
    kw = u.response.send_message.call_args.kwargs; view = kw["view"]; e = kw["embed"]
    assert isinstance(view, bot.ConfirmarApagarHistorico) and kw["ephemeral"] and e.title == "🧹 Apagar o histórico de Ana?"
    assert "**10 rolagens**" in e.description and "Não tem como desfazer" in e.description and "sorteios de criação" in e.description and "A ficha, o XP e os personagens não mudam" in e.description
    assert db.count_rolls("500") == 10                                                       # só perguntou: nada apagado ainda
    # quem não pediu não confirma
    intruso = inter(999, "Intruso", roles=["Mestre"]); assert await view.interaction_check(intruso) is False
    assert "Só quem pediu pode confirmar." in intruso.response.send_message.call_args.args[0] and db.count_rolls("500") == 10
    # cancelar
    cancela = inter(4, "Mestre Belmont", roles=["Mestre"]); assert await view.interaction_check(cancela) is True
    await view.cancelar.callback(cancela); assert cancela.response.edit_message.call_args.kwargs["content"] == "Beleza, nada foi apagado." and db.count_rolls("500") == 10
    # tempo esgotado
    u2 = inter(4, "Mestre Belmont", roles=["Mestre"]); await bot.mestre_apagar_historico.callback(u2, a500); v2 = u2.response.send_message.call_args.kwargs["view"]
    u2.edit_original_response = AsyncMock(); await v2.on_timeout()
    assert u2.edit_original_response.call_args.kwargs["content"] == "Passou o tempo e nada foi apagado." and db.count_rolls("500") == 10
    # o mestre perdeu o cargo nesses 60 segundos: não apaga
    u3 = inter(4, "Mestre Belmont", roles=["Mestre"]); await bot.mestre_apagar_historico.callback(u3, a500); v3 = u3.response.send_message.call_args.kwargs["view"]
    ex_mestre = inter(4, "Ex-Mestre"); await v3.confirmar.callback(ex_mestre)
    assert "Você não é mais mestre aqui" in ex_mestre.response.edit_message.call_args.kwargs["content"] and db.count_rolls("500") == 10
    # confirmar
    ok = inter(4, "Mestre Belmont", roles=["Mestre"]); await view.confirmar.callback(ok)
    assert ok.response.edit_message.call_args.kwargs["content"] == "🧹 O histórico de **Ana** foi apagado (10 rolagens)."
    aviso = ok.followup.send.call_args.kwargs
    assert aviso["embed"].title == "🧹 Histórico apagado" and "content" not in aviso and "allowed_mentions" not in aviso            # público, sem marcar ninguém
    assert aviso["embed"].description == "Mestre Belmont apagou o histórico de rolagens de <@500> (10 rolagens). A ficha, o XP e os personagens continuam como estavam."
    # um segundo clique (ou dois mestres) não quebra nem registra de novo
    de_novo = inter(4, "Mestre Belmont", roles=["Mestre"]); await view.confirmar.callback(de_novo)
    assert "já estava vazio" in de_novo.response.edit_message.call_args.kwargs["content"] and not de_novo.followup.send.called
run(apagar_com_botoes())
assert db.count_rolls("500") == 0 and db.count_rolls("501") == 4 and db.count_rolls("502") == 1                  # só a da Ana sumiu
assert (row(500, "Ana Um")["xp"], row(500, "Ana Um")["race"]) == (1500, "Humano") and row(500, "Ana Dois") is not None  # ficha, XP e personagens ficam
with sqlite3.connect(db.DB_PATH) as cn:
    assert cn.execute("SELECT master_id, target_user_id, character_id, action, detail FROM master_actions WHERE action='apagar_historico'").fetchall() == [("4", "500", None, "apagar_historico", "10 rolagens")]
h = inter(500, "Ana"); run(bot.historico.callback(h, None, 10, None)); assert txt(h) == "Nenhuma rolagem registrada pra Ana ainda." and sent(h)[1]["ephemeral"]
db.log_roll("500", "Ana", "g", "1d20", [9], 9, "depois", um, "Ana Um"); assert db.count_rolls("500") == 1     # e o histórico volta a funcionar
run(bot.mestre_apagar_historico.callback(gm, alvo(500, "Ana"))); assert "**1 rolagem**" in desc(gm)
print("P. /mestre apagar_historico OK")

# ============================ Q. cartões com imagem, dados por texto e partida segura ============================
import subprocess
db.DB_PATH = os.path.join(tmp, "vitrine.db"); db.init_db()
def nomes_de_arquivo(i): return [f.filename for f in sent(i)[1].get("files", [])]
def pronto(uid, jogador, personagem, raca="Humano", classe="Caçador"):
    """Personagem com a ficha pronta (sorteios, classe e os 6 pontos de atributo)."""
    i = novo(uid, jogador, personagem); preparar(uid, personagem, raca, classe)
    db.set_attributes(row(uid, personagem)["id"], {"vontade": 6}); return i

# --- os cartões saem com a imagem anexada (quando existe) e o texto do resultado ---
k1 = novo(600, "Ana", "Ana Humana")
with dados(50): run(bot.raca_inicial.callback(k1, None))
assert titulo(k1) == "Humanos" and nomes_de_arquivo(k1) == ["raca-humano.webp"] and sent(k1)[1]["embed"].image.url == "attachment://raca-humano.webp"
assert all(isinstance(f, discord.File) for f in sent(k1)[1]["files"]) and not sent(k1)[1].get("ephemeral") and "Raça de Ana Humana" in txt(k1)
assert "São seres mundanos" in desc(k1) and "Em jogo=" in txt(k1)
k2 = novo(601, "Beto", "Beto Vampiro")
with dados(90): run(bot.raca_inicial.callback(k2, None))
assert titulo(k2) == "Vampiros" and nomes_de_arquivo(k2) == ["raca-vampiro.jpg"] and "Conde Drácula" in desc(k2)
k3 = novo(602, "Caio", "Caio Dhampir")
with dados(97): run(bot.raca_inicial.callback(k3, None))
assert titulo(k3) == "Dhampirs" and nomes_de_arquivo(k3) == ["raca-dhampir.webp"] and sent(k3)[1]["embed"].image.url == "attachment://raca-dhampir.webp" and "amaldiçoados pela imortalidade" in desc(k3)
assert row(602, "Caio Dhampir")["race"] == "Dhampir" and [h["purpose"] for h in historico_de(602)] == ["raca_inicial"]
for n, esperado_titulo, arquivo in [(50, "3° Estado —  Camponeses", "estado-3.png"), (85, "2° Estado —  Nobreza", "estado-2.png")]:
    u = novo(610 + n, f"E{n}", f"Estado {n}")
    with dados(n): run(bot.classe_social.callback(u, None))
    assert titulo(u) == esperado_titulo and nomes_de_arquivo(u) == [arquivo] and not sent(u)[1].get("ephemeral")
u = novo(690, "Clero", "Padre Imagem")
with dados(95, 70): run(bot.classe_social.callback(u, None))
assert titulo(u) == "1° Estado —  Clero" and nomes_de_arquivo(u) == ["estado-1.jpg"] and "🎲" not in desc(u) and "✝ Alto Clero=O Alto Clero, de bispos e abades" in txt(u)
assert [h["purpose"] for h in reversed(historico_de(690))] == ["classe_social", "clero"]
m100 = inter(691, "Sortudo"); m100.guild = NS(roles=[NS(id=1, name="Jogador", mention="<@&1>"), NS(id=555, name="Mestre", mention="<@&555>")])
run(bot.personagem_criar.callback(m100, "Raro Imagem"))
with dados(100): run(bot.classe_social.callback(m100, None))
assert titulo(m100) == "🎲 Resultado especial" and "files" not in sent(m100)[1] and sent(m100)[1]["content"] == "<@&555>"   # o aviso ao mestre continua
mg = pronto(692, "Mago", "Mago Vampiro", "Vampiro", "Mundano"); db.clear_definition(row(692, "Mago Vampiro")["id"], "magic_rank")
with dados(96): run(bot.magia_inicial.callback(mg, None))
assert titulo(mg) == "Rank Lendário" and "★★★★☆ · 4% de chance" in desc(mg) and "files" not in sent(mg)[1] and row(692, "Mago Vampiro")["magic_rank"] == "Lendário"
cl = novo(693, "Classe", "Classe Imagem"); preparar(693, "Classe Imagem", "Humano", None)
run(bot.classe_escolher.callback(cl, "Sábio", None))
assert titulo(cl) == "Sábio" and sent(cl)[1]["ephemeral"] and "files" not in sent(cl)[1] and "Os sábios buscam o saber" in desc(cl) and "Continue a criação=" in txt(cl)
# o /rolar usa o cartão novo (destaque de 20 e 1 naturais, só no visual)
rd = pronto(694, "Dado", "Dado Bonito")
real_roll = dice.roll
try:
    dice.roll = lambda n: dice.RollResult(n, [20], 0, 20)
    run(bot.rolar.callback(rd, "1d20", "ataque", None))
    assert titulo(rd) == "🎲 Dado Bonito rolou 1d20" and "🌟 **20 natural!**" in desc(rd) and rodape(rd) == "ataque · jogador: Dado"
    dice.roll = lambda n: dice.RollResult(n, [1], 5, 20)
    run(bot.rolar.callback(rd, "1d20+5", None, None)); assert "💀 **1 natural!**" in desc(rd) and "**1 + 5 = 6**" in desc(rd)
    dice.roll = lambda n: dice.RollResult(n, [7], 0, 20)
    run(bot.rolar.callback(rd, "1d20", None, None)); assert desc(rd) == "**7 = 7**"
finally:
    dice.roll = real_roll

# --- dados escritos direto no chat ---
def msg(uid, nome, texto, roles=(), bot_=False, dm=False, admin=False):
    m = MagicMock(); m.author = MagicMock(); m.author.id = uid; m.author.display_name = nome; m.author.bot = bot_
    m.author.guild_permissions = NS(administrator=admin, manage_guild=False); m.author.roles = [NS(name=r) for r in roles]
    m.guild = None if dm else NS(id=999); m.content = texto; m.reply = AsyncMock(); return m
def resposta(m):
    assert m.reply.call_count == 1, m.reply.call_count
    a, kw = m.reply.call_args; return (a[0] if a else None), kw
@contextlib.contextmanager
def fixo(valor):
    """Fixa só o número que sai no dado; o modificador e os lados continuam os de verdade."""
    real = dice.roll
    def falso(n):
        r = real(n); return dice.RollResult(n, [valor], r.modifier, r.sides)
    dice.roll = falso
    try: yield
    finally: dice.roll = real
def historico_texto(uid): return [(h["notation"], h["purpose"], h["character_name"], h["total"]) for h in reversed(db.get_history(str(uid), 50))]

assert bot.DADOS_POR_TEXTO is True and bot.bot.intents.message_content is True            # ligado por padrão, com a leitura de mensagens pedida
t1 = pronto(700, "Texto", "Texto Ficha")
with fixo(12):                                                                             # d20 escrito: rola 1d20 e responde na mensagem
    m = msg(700, "Texto", "d20+5"); run(bot.on_message(m))
_, kw = resposta(m); e = kw["embed"]
assert e.title == "🎲 Texto Ficha rolou 1d20+5" and e.description == "**12 + 5 = 17**" and e.footer.text == "jogador: Texto" and kw["mention_author"] is False and "delete_after" not in kw
assert historico_texto(700) == [("1d20+5", None, "Texto Ficha", 17)]                       # notação normalizada no histórico
with fixo(4):                                                                              # com "+", o resto vira o motivo
    m = msg(700, "Texto", "+d20 + 5 ataque com a espada"); run(bot.on_message(m))
_, kw = resposta(m); assert kw["embed"].title == "🎲 Texto Ficha rolou 1d20+5" and kw["embed"].footer.text == "ataque com a espada · jogador: Texto"
assert historico_texto(700)[-1] == ("1d20+5", "ataque com a espada", "Texto Ficha", 9)
h = inter(700, "Texto"); run(bot.historico.callback(h, None, 10, None)); assert "1d20+5 = 9 (ataque com a espada)" in txt(h) and "1d20+5 = 17" in txt(h)   # aparece no /historico
with dados():                                                                              # conversa normal não rola (dados() vazio: rolar seria erro)
    for papo in ("d20 é o melhor dado", "adoro d20", "vou rolar d20 agora", "bom dia", "d20+5 ataque", "https://x.com/d20", "/rolar d20"):
        m = msg(700, "Texto", papo); run(bot.on_message(m)); assert m.reply.call_count == 0, papo
    for ignorado in (msg(700, "Bot", "d20", bot_=True), msg(700, "Texto", "d20", dm=True)):  # bots e mensagens diretas
        run(bot.on_message(ignorado)); assert ignorado.reply.call_count == 0
assert len(historico_texto(700)) == 2                                                     # nada disso foi pro histórico
# dado inválido: só quem pediu com "+" recebe resposta (o dice.roll de verdade recusa antes de rolar qualquer coisa)
with contextlib.nullcontext():
    m = msg(700, "Texto", "+d1"); run(bot.on_message(m)); t, kw = resposta(m)
    assert t.startswith("⚠️ ") and "entre 2 e 1000 lados" in t and kw["delete_after"] == 15 and kw["mention_author"] is False
    m = msg(700, "Texto", "+101d6 dano"); run(bot.on_message(m)); t, kw = resposta(m); assert "entre 1 e 100" in t
    for calado in ("d1", "0d20", "d5000"):
        m = msg(700, "Texto", calado); run(bot.on_message(m)); assert m.reply.call_count == 0, calado
assert len(historico_texto(700)) == 2
# destaque de 20 natural também no texto
try:
    dice.roll = lambda n: dice.RollResult(n, [20], 0, 20)
    m = msg(700, "Texto", "d20"); run(bot.on_message(m)); assert "🌟 **20 natural!**" in resposta(m)[1]["embed"].description
finally:
    dice.roll = real_roll
# a mesma regra de ficha pronta do /rolar: sem personagem ou com a ficha incompleta, bloqueia com aviso curto que some sozinho
with dados():
    m = msg(701, "Sem Nada", "d20"); run(bot.on_message(m)); t, kw = resposta(m)
    assert t.startswith("🔒 Você ainda não tem personagem.") and "/personagem criar" in t and kw["delete_after"] == 20 and "embed" not in kw
    novo(702, "Meio", "Meio Pronto")
    m = msg(702, "Meio", "+d20+5 ataque"); run(bot.on_message(m)); t, kw = resposta(m)
    assert t == "🔒 A ficha de **Meio Pronto** ainda não está pronta. O passo a passo está em `/ajuda`." and kw["delete_after"] == 20
    assert db.count_rolls("701") == 0 and db.count_rolls("702") == 0
# os mestres passam direto, mesmo sem personagem, e a rolagem sai no nome deles
with dados(15):
    m = msg(703, "Mestre Texto", "d20", roles=["Mestre"]); run(bot.on_message(m))
_, kw = resposta(m); assert kw["embed"].title == "🎲 Mestre Texto rolou 1d20" and kw["embed"].footer.text is None
assert historico_texto(703) == [("1d20", None, None, 15)]
with dados(3):
    m = msg(704, "Admin", "d6", admin=True); run(bot.on_message(m))
assert resposta(m)[1]["embed"].description == "**3 = 3**"
# chavinha da ordem desligada: quem ainda não tem ficha pronta também rola (e sem personagem sai no nome do jogador)
bot.ORDEM_DA_CRIACAO = False
try:
    with dados(8):
        m = msg(701, "Sem Nada", "d20"); run(bot.on_message(m))
    assert resposta(m)[1]["embed"].title == "🎲 Sem Nada rolou 1d20" and historico_texto(701) == [("1d20", None, None, 8)]
finally:
    bot.ORDEM_DA_CRIACAO = True
# o recurso desligado: o bot ignora tudo (e a ajuda deixa de mencionar)
bot.DADOS_POR_TEXTO = False
try:
    with dados():
        m = msg(700, "Texto", "d20"); run(bot.on_message(m)); assert m.reply.call_count == 0
finally:
    bot.DADOS_POR_TEXTO = True

# --- a ajuda ensina os dados por texto (só quando o recurso está ligado) ---
assert ajuda._dados_por_texto is True and "escreve o dado direto no chat" in ajuda.detalhe("rolar")["descricao"]
assert "nem precisa de barra" in ajuda.visao_geral(None, False, False)["descricao"]
def saida(env_extra):
    codigo = "import bot, ajuda; print(bot.DADOS_POR_TEXTO, bot.intents.message_content, ajuda._dados_por_texto)"
    r = subprocess.run([sys.executable, "-c", codigo], cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       env={**os.environ, **env_extra}, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr; return r.stdout.strip().splitlines()[-1]
assert saida({}) == "True True True" and saida({"DADOS_POR_TEXTO": "0"}) == "False False False" and saida({"DADOS_POR_TEXTO": "sim"}) == "True True True"

# --- partida segura: sem o "Message Content Intent" no Portal, o bot reinicia sem os dados por texto em vez de cair ---
chamadas = {}
orig = (bot.bot.run, os.execv, bot.TOKEN, db.init_db)
def run_sem_intent(token): chamadas["token"] = token; raise discord.PrivilegedIntentsRequired(None)
bot.bot.run = run_sem_intent; os.execv = lambda exe, args: chamadas.update(execv=(exe, args)); bot.TOKEN = "token-falso"; db.init_db = lambda *a, **k: chamadas.update(init=True)
try:
    bot.main()
    assert chamadas["init"] and chamadas["token"] == "token-falso" and chamadas["execv"][0] == sys.executable
    assert chamadas["execv"][1][0] == sys.executable and os.environ["DADOS_POR_TEXTO"] == "0"     # o processo novo nasce com o recurso desligado
    bot.DADOS_POR_TEXTO = False; chamadas.pop("execv")                                            # já desligado e ainda recusado: não reinicia em loop
    try: bot.main(); raise SystemExit("deveria propagar o erro")
    except discord.PrivilegedIntentsRequired: pass
    assert "execv" not in chamadas
    bot.DADOS_POR_TEXTO = True; bot.bot.run = lambda token: chamadas.update(rodou=token)          # sem problema nenhum: só roda
    bot.main(); assert chamadas["rodou"] == "token-falso" and "execv" not in chamadas
    bot.TOKEN = None
    try: bot.main(); raise SystemExit("deveria exigir o token")
    except SystemExit as e: assert "DISCORD_TOKEN" in str(e)
finally:
    bot.bot.run, os.execv, bot.TOKEN, db.init_db = orig; bot.DADOS_POR_TEXTO = True; os.environ.pop("DADOS_POR_TEXTO", None)
print("Q. cartões, dados por texto e partida segura OK")

# ============================ R. painéis com botões ============================
import paineis
LOOP = asyncio.new_event_loop(); runp = LOOP.run_until_complete      # um laço só: as telas (View) vivem entre um clique e outro
def criar(classe, *args, **kwargs):
    """Cria uma tela (View ou formulário) DENTRO do laço, como o bot faz. Fora dele, o stop() não vale."""
    async def fabrica(): return classe(*args, **kwargs)
    return runp(fabrica())
db.DB_PATH = os.path.join(tmp, "paineis.db"); db.init_db()

def botao(view, rotulo, emoji=None):
    achados = [b for b in view.children if isinstance(b, discord.ui.Button) and b.label == rotulo and (emoji is None or str(b.emoji) == emoji)]
    assert len(achados) == 1, (rotulo, emoji, [(b.label, str(b.emoji)) for b in view.children if isinstance(b, discord.ui.Button)])
    return achados[0]
def estado(view):
    """Rótulo -> (emoji, desligado) dos botões. Nas telas com abas (ficha e vitais) a linha das abas fica de fora: ela tem testes próprios."""
    abas = isinstance(view, (paineis.PainelFicha, paineis.PainelVitais, paineis.PainelPericias, paineis.PainelHabilidades))
    return {b.label: (str(b.emoji), b.disabled) for b in view.children if isinstance(b, discord.ui.Button) and not (abas and b.row == 0)}
def estado_completo(view): return {b.label: (str(b.emoji), b.disabled) for b in view.children if isinstance(b, discord.ui.Button)}
def seletor(view):
    achados = [c for c in view.children if isinstance(c, discord.ui.Select)]; return achados[0] if achados else None
def confere_componentes(view):
    """Cabe nas regras do Discord: até 5 linhas, 5 botões por linha, menu sozinho na linha, textos curtos."""
    linhas = {}
    for c in view.children:
        assert c.row is not None and 0 <= c.row <= 4, c
        linhas.setdefault(c.row, []).append(c)
        if isinstance(c, discord.ui.Button): assert len(c.label or "") <= 80
        else:
            assert len(c.options) <= 25 and len(c.placeholder or "") <= 150
            for o in c.options: assert len(o.label) <= 100 and len(o.description or "") <= 100 and len(o.value) <= 100
    for r, itens in linhas.items():
        assert len(itens) <= 5 and (len(itens) == 1 or not any(isinstance(x, discord.ui.Select) for x in itens)), (r, itens)
    assert len(view.children) <= 25
def enviada(i): return sent(i)[1]["view"]
def editada(i): return i.response.edit_message.call_args.kwargs
def followups(i): return [(a[0], kw) for a, kw in i.followup.send.call_args_list]
def clique(view, rotulo, uid, nome, emoji=None, **extras):
    c = inter(uid, nome, **extras); runp(botao(view, rotulo, emoji).callback(c)); return c

# --- criar o personagem já entrega o painel ---
u = inter(800, "Ana"); runp(bot.personagem_criar.callback(u, "Ana Painel"))
kw = sent(u)[1]; painel = kw["view"]
assert isinstance(painel, paineis.PainelFicha) and kw["ephemeral"] and painel.origem is u and painel.dono_id == 800 and "Ou é só clicar nos botões aqui embaixo." in desc(u)
confere_componentes(painel)
assert estado(painel) == {"Raça": ("🩸", False), "Classe social": ("⚜️", False), "Classe": ("🔒", True), "Magia": ("🔒", True),
                          "Físicos": ("🧬", True), "Mentais": ("🧠", True), "Dados": ("🎲", False), "Níveis": ("📈", False), "Ajuda": ("❓", False)}
assert seletor(painel) is None and botao(painel, "Raça").style == discord.ButtonStyle.primary                 # 1 personagem: sem menu de troca

# --- clicar em Raça: o painel se atualiza e o cartão sai público ---
with dados(50): c1 = clique(painel, "Raça", 800, "Ana")
assert c1.response.edit_message.call_count == 1 and c1.followup.send.call_count == 1 and painel.is_finished()
nova = editada(c1)["view"]; assert isinstance(nova, paineis.PainelFicha) and nova is not painel and nova.origem is u
assert editada(c1)["embed"].title == "📖 Ficha de Ana Painel" and "⚠️ **Ficha incompleta.**" in editada(c1)["embed"].description
(conteudo, fk), = followups(c1)
assert conteudo is None and nome_do_cartao(fk["embed"]) == "Humanos" and [f.filename for f in fk["files"]] == ["raca-humano.webp"] and "ephemeral" not in fk    # público, com a imagem (o gif ainda não foi baixado no teste)
assert row(800, "Ana Painel")["race"] == "Humano" and [h["purpose"] for h in historico_de(800)] == ["raca_inicial"]
assert estado(nova)["Raça (2)"] == ("🔄", False) and estado(nova)["Classe"] == ("🔒", True) and botao(nova, "Raça (2)").style == discord.ButtonStyle.secondary   # sobram 2 chances
assert fk["embed"].footer.text == "jogador: Ana · tentativa 1 de 3"

# --- Classe social, depois a escolha da classe com confirmação ---
with dados(50): c2 = clique(nova, "Classe social", 800, "Ana")
assert nome_do_cartao(followups(c2)[0][1]["embed"]) == "3° Estado —  Camponeses" and [f.filename for f in followups(c2)[0][1]["files"]] == ["estado-3.png"]
nova2 = editada(c2)["view"]; assert estado(nova2)["Classe"] == ("🎓", False) and estado(nova2)["Classe social (2)"] == ("🔄", False)
c3 = clique(nova2, "Classe", 800, "Ana")
esc = editada(c3)["view"]; assert isinstance(esc, paineis.EscolhaDeClasse) and c3.followup.send.call_count == 0 and nova2.is_finished()
e = editada(c3)["embed"]; assert e.title == "🎓 Escolha a classe de Ana Painel" and [f.name for f in e.fields] == list(rules.CLASSES) and "uma vez só" in e.description
confere_componentes(esc); sel = seletor(esc)
assert [o.value for o in sel.options] == list(rules.CLASSES) and sel.options[0].description == "Vantagem: Religião e Luta ou Pontaria" and botao(esc, "Confirmar classe").disabled
assert esc.origem is u
c4 = inter(800, "Ana"); sel._values = ["Caçador"]; runp(sel.callback(c4))                                 # escolher no menu só mostra a prévia
e = editada(c4)["embed"]; assert e.title == "🎓 Caçador" and "Os caçadores devotam" in e.description and "Confirmar classe" in e.description
assert row(800, "Ana Painel")["class_name"] is None and not botao(esc, "Confirmar classe").disabled and c4.followup.send.call_count == 0
assert [o.value for o in seletor(esc).options if o.default] == ["Caçador"]
c4b = inter(800, "Ana"); seletor(esc)._values = ["Paladino"]; runp(seletor(esc).callback(c4b))              # uma classe que não existe é recusada
assert "Não conheço essa classe" in c4b.response.send_message.call_args.args[0] and row(800, "Ana Painel")["class_name"] is None
c4c = clique(esc, "Voltar", 800, "Ana"); assert isinstance(editada(c4c)["view"], paineis.PainelFicha) and esc.is_finished()   # voltar não escolhe nada
assert row(800, "Ana Painel")["class_name"] is None
esc = criar(paineis.EscolhaDeClasse, 800, row(800, "Ana Painel")["id"], "Ana"); esc.origem = u; seletor(esc)._values = ["Caçador"]
runp(seletor(esc).callback(inter(800, "Ana")))
c5 = clique(esc, "Confirmar classe", 800, "Ana")
(conteudo, fk), = followups(c5); assert fk["ephemeral"] is True and fk["embed"].title == "Caçador" and "files" not in fk                # a classe continua privada
assert row(800, "Ana Painel")["class_name"] == "Caçador"
nova3 = editada(c5)["view"]; assert isinstance(nova3, paineis.PainelFicha)
assert estado(nova3)["Raça"] == ("✅", True) and estado(nova3)["Classe social"] == ("✅", True)                       # escolher a classe fecha as chances que sobravam
assert estado(nova3)["Classe"] == ("✅", True) and estado(nova3)["Sem magia"] == ("➖", True) and estado(nova3)["Físicos"] == ("🧬", False)   # Humano Caçador: sem magia; atributos liberados

# --- atributos: dois formulários de três campos ---
c6 = clique(nova3, "Físicos", 800, "Ana")
modal = c6.response.send_modal.call_args.args[0]
assert isinstance(modal, paineis.ModalAtributos) and modal.title == "Atributos físicos de Ana Painel" and list(modal.campos) == ["forca", "destreza", "vitalidade"]
assert [c.label for c in modal.campos.values()] == [f"{n} (só dá pra aumentar)" for n in ("Força", "Destreza", "Vitalidade")] and all(c.default == "0" for c in modal.campos.values())
assert len(modal.title) <= 45 and all(len(c.label) <= 45 for c in modal.campos.values())
def enviar_modal(modal, valores, uid=800, nome="Ana"):
    for chave, v in valores.items(): modal.campos[chave]._value = v
    i = inter(uid, nome); runp(modal.on_submit(i)); return i
for ruim in ({"forca": "abc", "destreza": "0", "vitalidade": "0"}, {"forca": "-1", "destreza": "0", "vitalidade": "0"}, {"forca": "25", "destreza": "0", "vitalidade": "0"}, {"forca": "", "destreza": "0", "vitalidade": "0"}, {"forca": "2.5", "destreza": "0", "vitalidade": "0"}):
    i = enviar_modal(modal, ruim); assert "use um número de 0 a 20" in i.response.send_message.call_args.args[0] and i.response.send_message.call_args.kwargs["ephemeral"] and i.response.edit_message.call_count == 0
assert db.attributes_of(row(800, "Ana Painel")) == {a: 0 for a in rules.ATTRIBUTES}
i = enviar_modal(modal, {"forca": "0", "destreza": "0", "vitalidade": "0"})                              # nada mudou
assert followups(i)[0][0] == "Nada mudou: **Ana Painel** já tem esses valores." and followups(i)[0][1]["ephemeral"] and i.response.edit_message.call_count == 1
nova3 = editada(i)["view"]; c6 = clique(nova3, "Físicos", 800, "Ana"); modal = c6.response.send_modal.call_args.args[0]
i = enviar_modal(modal, {"forca": "2", "destreza": "0", "vitalidade": "3"})
(conteudo, fk), = followups(i); assert fk["ephemeral"] is True and fk["embed"].title == "🧬 Atributos de Ana Painel atualizados"
assert db.attributes_of(row(800, "Ana Painel")) == {"forca": 2, "destreza": 0, "vitalidade": 3, "razao": 0, "vontade": 0, "alma": 0} and "Pontos de atributo: 5 de 6 usados" in fk["embed"].fields[0].value
nova4 = editada(i)["view"]; assert estado(nova4)["Físicos"] == ("🧬", False) and "⚠️ **Ficha incompleta.**" in editada(i)["embed"].description       # falta 1 ponto
c7 = clique(nova4, "Mentais", 800, "Ana"); modal2 = c7.response.send_modal.call_args.args[0]
assert modal2.title == "Atributos mentais de Ana Painel" and list(modal2.campos) == ["razao", "vontade", "alma"]
i = enviar_modal(modal2, {"razao": "0", "vontade": "1", "alma": "1"})                                    # 7 pontos no total: o mesmo aviso do /atributos
(aviso, kw_aviso), = followups(i); assert "Você distribuiu 7 pontos de atributo, mas no nível 1 o total é 6." in aviso and kw_aviso["ephemeral"] is True
assert db.attributes_of(row(800, "Ana Painel"))["vontade"] == 0
nova4 = editada(i)["view"]
i = enviar_modal(criar(paineis.ModalAtributos, nova4, "fisicos"), {"forca": "1", "destreza": "0", "vitalidade": "3"})    # diminuir não pode
assert "Só dá pra aumentar atributo, e Força ficaria menor do que já está." in followups(i)[0][0] and db.attributes_of(row(800, "Ana Painel"))["forca"] == 2
nova4 = editada(i)["view"]
c8 = clique(nova4, "Mentais", 800, "Ana"); modal2 = c8.response.send_modal.call_args.args[0]
i = enviar_modal(modal2, {"razao": "0", "vontade": "1", "alma": "0"})                                    # o último ponto: a ficha fica pronta
assert db.attributes_of(row(800, "Ana Painel"))["vontade"] == 1 and rules.creation_status(row(800, "Ana Painel"))["pronta"]
pronto4 = editada(i)["view"]; assert estado(pronto4)["Físicos"] == ("🧬", True) and estado(pronto4)["Mentais"] == ("🧠", True)   # sem ponto sobrando, os botões desligam
assert not (editada(i)["embed"].description or "").startswith("⚠️")
confere_componentes(pronto4)

# --- só o dono mexe; o tempo esgotado desliga tudo; erro vira aviso ---
intruso = inter(999, "Intruso"); assert runp(pronto4.interaction_check(intruso)) is False
assert intruso.response.send_message.call_args.args[0] == paineis.MSG_DE_OUTRA_PESSOA and intruso.response.send_message.call_args.kwargs["ephemeral"]
assert runp(pronto4.interaction_check(inter(800, "Ana"))) is True
runp(pronto4.on_timeout()); assert all(b.disabled for b in pronto4.children) and u.edit_original_response.call_count == 1 and u.edit_original_response.call_args.kwargs["view"] is pronto4
u.edit_original_response = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=404, reason="x"), "mensagem apagada")); runp(pronto4.on_timeout())   # mensagem já apagada: não estoura
err = inter(800, "Ana"); runp(pronto4.on_error(err, RuntimeError("falhou"), None)); assert err.response.send_message.call_args.args[0] == paineis.MSG_ERRO and err.response.send_message.call_args.kwargs["ephemeral"]
err2 = inter(800, "Ana"); err2.response.is_done = MagicMock(return_value=True); runp(pronto4.on_error(err2, RuntimeError("falhou"), None)); assert err2.followup.send.call_args.args[0] == paineis.MSG_ERRO
c = inter(800, "Ana"); runp(modal2.on_error(c, RuntimeError("x"))); assert c.response.send_message.call_args.args[0] == paineis.MSG_ERRO

# --- atalhos: dados, níveis e ajuda ---
painel = criar(paineis.PainelFicha, 800, row(800, "Ana Painel")["id"], "Ana"); painel.origem = u
c = clique(painel, "Dados", 800, "Ana"); bandeja = enviada(c)
assert isinstance(bandeja, paineis.BandejaDados) and sent(c)[1]["ephemeral"] and bandeja.origem is c and "## 1d20" in sent(c)[1]["embed"].description
c = clique(painel, "Níveis", 800, "Ana"); (_, fk), = followups(c); assert fk["ephemeral"] and fk["embed"].title == "📈 XP e vantagens de cada nível" and c.response.edit_message.call_count == 1
assert "▶️ **Nível 1**" in fk["embed"].description
c = clique(editada(c)["view"], "Ajuda", 800, "Ana"); (_, fk), = followups(c); assert fk["ephemeral"] and fk["embed"].title == "📖 Ajuda do bot" and "escreve `d20+5` no chat" in fk["embed"].description

# --- trocar de personagem pelo menu ---
runp(bot.personagem_criar.callback(inter(800, "Ana"), "Ana Segunda"))
outro = novo(801, "Beto", "Beto Alheio")
um = row(800, "Ana Painel"); dois = row(800, "Ana Segunda")
uu = inter(800, "Ana"); runp(bot.minha_ficha.callback(uu, "Ana Painel")); pv = enviada(uu)
assert isinstance(pv, paineis.PainelFicha) and pv.personagem_id == um["id"] and pv.origem is uu and sent(uu)[1]["ephemeral"] and titulo(uu) == "📖 Ficha de Ana Painel"
confere_componentes(pv); sel = seletor(pv)
assert [o.label for o in sel.options] == ["Ana Painel", "Ana Segunda"] and [o.default for o in sel.options] == [True, False] and sel.options[0].description == "nível 1 · Humano"
assert sel.options[1].description == "nível 1 · sem raça"
c = inter(800, "Ana"); sel._values = [str(dois["id"])]; runp(sel.callback(c))
assert editada(c)["embed"].title == "📖 Ficha de Ana Segunda" and db.get_active_character("800")["name"] == "Ana Segunda" and [o.default for o in seletor(editada(c)["view"]).options] == [False, True]
c = inter(800, "Ana"); alheio = row(801, "Beto Alheio"); seletor(pv)._values = [str(alheio["id"])]; runp(seletor(pv).callback(c))   # nunca troca pra personagem de outra pessoa
assert followups(c)[0][0] == "Não achei esse personagem. Abre o painel de novo com `/minha_ficha`." and db.get_active_character("800")["name"] == "Ana Segunda"
c = inter(800, "Ana"); seletor(pv)._values = ["99999"]; runp(seletor(pv).callback(c)); assert "Não achei esse personagem" in followups(c)[0][0]        # id que não existe
c = inter(800, "Ana"); runp(bot.minha_ficha.callback(c, "Fantasma")); assert "Não achei nenhum personagem" in txt(c) and "view" not in sent(c)[1]      # sem personagem: sem painel

# --- a classe social 100: o botão fica esperando o mestre, e o aviso ao cargo Mestre sai junto ---
m = novo(802, "Caio", "Caio Cem"); pv = criar(paineis.PainelFicha, 802, row(802, "Caio Cem")["id"], "Caio"); pv.origem = m
cem = inter(802, "Caio"); cem.guild = NS(roles=[NS(id=555, name="Mestre", mention="<@&555>")])
with dados(100): runp(botao(pv, "Classe social").callback(cem))
(conteudo, fk), = followups(cem); assert fk["embed"].title == "🎲 Resultado especial" and conteudo == "<@&555>" and fk["allowed_mentions"].roles == [cem.guild.roles[0]] and "ephemeral" not in fk
v = editada(cem)["view"]; assert estado(v)["Classe social"] == ("⏳", True) and estado(v)["Classe"] == ("🔒", True)
# --- quem tem magia vê o botão de Rank de magia ---
vp = novo(803, "Vlad", "Vlad Vampiro"); preparar(803, "Vlad Vampiro", "Vampiro", "Mundano"); db.clear_definition(row(803, "Vlad Vampiro")["id"], "magic_rank")
pv = criar(paineis.PainelFicha, 803, row(803, "Vlad Vampiro")["id"], "Vlad"); pv.origem = vp
assert estado(pv)["Magia"] == ("✨", False) and estado(pv)["Físicos"] == ("🧬", True)                     # a magia vem antes dos atributos
with dados(70): c = clique(pv, "Magia", 803, "Vlad")
assert followups(c)[0][1]["embed"].title == "Rank Raro" and "ephemeral" not in followups(c)[0][1]
v = editada(c)["view"]; assert estado(v)["Magia"] == ("✅", True) and estado(v)["Físicos"] == ("🧬", False)
# --- com a chavinha da ordem desligada, os passos ficam todos abertos (menos atributos, que precisam da raça) ---
bot.ORDEM_DA_CRIACAO = False
try:
    lv = novo(804, "Livre", "Livre Painel"); pv = criar(paineis.PainelFicha, 804, row(804, "Livre Painel")["id"], "Livre")
    assert estado(pv) == {"Raça": ("🩸", False), "Classe social": ("⚜️", False), "Classe": ("🎓", False), "Magia": ("✨", False), "Físicos": ("🧬", True), "Mentais": ("🧠", True),
                          "Dados": ("🎲", False), "Níveis": ("📈", False), "Ajuda": ("❓", False)}
finally:
    bot.ORDEM_DA_CRIACAO = True

# --- Coletor ---
cc = paineis.Coletor(inter(800, "Ana")); runp(cc.response.send_message("oi", embed=1, ephemeral=True)); runp(cc.response.send_message(embed=2)); cc.avisar("psiu")
assert cc.mensagens == [("oi", {"embed": 1, "ephemeral": True}), (None, {"embed": 2}), ("psiu", {"ephemeral": True})] and cc.response.is_done() is False
assert cc.guild_id == 999 and cc.user.id == 800 and cc.namespace.__dict__ == {}

# --- bandeja de dados ---
db.set_attributes(row(800, "Ana Painel")["id"], {"vontade": 6}); preparar(800, "Ana Painel"); db.set_active_character("800", row(800, "Ana Painel")["id"])
d = inter(800, "Ana"); runp(bot.dados_comando.callback(d)); kw = sent(d)[1]; tray = kw["view"]
assert isinstance(tray, paineis.BandejaDados) and kw["ephemeral"] and tray.origem is d and kw["embed"].title == "🎲 Bandeja de dados"
assert kw["embed"].description.startswith("## 1d20\n") and [(f.name, f.value) for f in kw["embed"].fields] == [("Motivo", "nenhum (aperta 📝 pra escrever um)"), ("Rolando como", "Ana Painel")]
confere_componentes(tray); assert {b.label: b.row for b in tray.children if b.label in ("d4", "d12", "d20", "d100", "Rolar", "+5", "Motivo")} == {"d4": 0, "d12": 0, "d20": 1, "d100": 1, "Rolar": 1, "+5": 2, "Motivo": 3}
assert botao(tray, "d20").style == discord.ButtonStyle.primary and botao(tray, "d6").style == discord.ButtonStyle.secondary
assert botao(tray, "Dado", "➖").disabled and not botao(tray, "Dado", "➕").disabled and botao(tray, "Zerar").disabled
def bd(i): return editada(i)["embed"].description.split("\n")[0]
c = clique(tray, "d6", 800, "Ana"); assert bd(c) == "## 1d6" and botao(tray, "d6").style == discord.ButtonStyle.primary and botao(tray, "d20").style == discord.ButtonStyle.secondary
c = clique(tray, "Dado", 800, "Ana", "➕"); c = clique(tray, "Dado", 800, "Ana", "➕"); assert bd(c) == "## 3d6" and not botao(tray, "Dado", "➖").disabled
c = clique(tray, "+5", 800, "Ana"); assert bd(c) == "## 3d6+5" and not botao(tray, "Zerar").disabled
c = clique(tray, "-1", 800, "Ana"); assert bd(c) == "## 3d6+4"
c = clique(tray, "-5", 800, "Ana"); c = clique(tray, "-5", 800, "Ana"); assert bd(c) == "## 3d6-6"
c = clique(tray, "Zerar", 800, "Ana"); assert bd(c) == "## 3d6" and botao(tray, "Zerar").disabled
for _ in range(9): c = clique(tray, "Dado", 800, "Ana", "➕") if not botao(tray, "Dado", "➕").disabled else c
assert bd(c) == "## 10d6" and botao(tray, "Dado", "➕").disabled and tray.qtd == 10                        # teto de 10 dados
for _ in range(9): c = clique(tray, "Dado", 800, "Ana", "➖")
assert tray.qtd == 1 and botao(tray, "Dado", "➖").disabled
for _ in range(8): c = clique(tray, "+5", 800, "Ana")
assert tray.mod == 30 and bd(c) == "## 1d6+30"                                                              # teto de +30
for _ in range(14): c = clique(tray, "-5", 800, "Ana")
assert tray.mod == -30 and bd(c) == "## 1d6-30"
c = clique(tray, "Zerar", 800, "Ana"); c = clique(tray, "d20", 800, "Ana")
# motivo pelo formulário
c = clique(tray, "Motivo", 800, "Ana"); mm = c.response.send_modal.call_args.args[0]
assert isinstance(mm, paineis.ModalMotivo) and mm.title == "Motivo da rolagem" and mm.campo.max_length == 80 and not mm.campo.required
mm.campo._value = "  ataque com a espada  "; c = inter(800, "Ana"); runp(mm.on_submit(c))
assert tray.motivo == "ataque com a espada" and dict((f.name, f.value) for f in editada(c)["embed"].fields)["Motivo"] == "ataque com a espada"
mm2 = runp(botao(tray, "Motivo").callback(inter(800, "Ana"))); mm2 = criar(paineis.ModalMotivo, tray); assert mm2.campo.default == "ataque com a espada"
mm2.campo._value = "   "; runp(mm2.on_submit(inter(800, "Ana"))); assert tray.motivo is None
mm.campo._value = "ataque com a espada"; runp(mm.on_submit(inter(800, "Ana")))
runp(tray.on_timeout()); assert all(b.disabled for b in tray.children); tray._montar()                     # (só pra seguir usando a mesma bandeja)
# rolar: sai público no nome do personagem, com o motivo, e vai pro histórico
c = clique(tray, "Dado", 800, "Ana", "➕"); c = clique(tray, "+5", 800, "Ana"); c = clique(tray, "-1", 800, "Ana")
antes = len(historico_de(800))
with fixo(4): c = clique(tray, "Rolar", 800, "Ana", "🎲")
assert c.response.edit_message.call_count == 1 and editada(c)["view"] is tray and editada(c)["embed"].description.startswith("## 2d20+4")
(_, fk), = followups(c); assert "ephemeral" not in fk and fk["embed"].title == "🎲 Ana Painel rolou 2d20+4" and fk["embed"].footer.text == "ataque com a espada · jogador: Ana"
assert historico_texto(800)[-1] == ("2d20+4", "ataque com a espada", "Ana Painel", 8) and len(historico_de(800)) == antes + 1
c = clique(tray, "Rolar", 800, "Ana", "🎲")                                                               # pode rolar de novo com a mesma bandeja (dados de verdade)
assert "natural" not in followups(c)[0][1]["embed"].description and len(historico_de(800)) == antes + 2   # 2d20 nunca ganha o destaque de natural
# sem personagem ou com a ficha incompleta: bloqueia com a mesma mensagem do /rolar, sem rolar nada
sem = criar(paineis.BandejaDados, 805, "Sem Nada")
with dados(): c = clique(sem, "Rolar", 805, "Sem Nada", "🎲")
assert followups(c)[0][0].startswith("Você ainda não tem personagem.") and followups(c)[0][1]["ephemeral"] and db.count_rolls("805") == 0 and c.response.edit_message.call_count == 1
novo(806, "Meio", "Meio Painel"); meio = criar(paineis.BandejaDados, 806, "Meio")
with dados(): c = clique(meio, "Rolar", 806, "Meio", "🎲")
assert followups(c)[0][0].startswith("🔒 A ficha de **Meio Painel**") and followups(c)[0][1]["ephemeral"] and db.count_rolls("806") == 0
# mestre passa direto, mesmo sem personagem
mest = criar(paineis.BandejaDados, 807, "Mestre Bandeja")
with fixo(9): c = clique(mest, "Rolar", 807, "Mestre Bandeja", "🎲", roles=["Mestre"])
assert followups(c)[0][1]["embed"].title == "🎲 Mestre Bandeja rolou 1d20" and historico_texto(807) == [("1d20", None, None, 9)]
# só o dono usa a bandeja
assert runp(tray.interaction_check(inter(999, "Intruso"))) is False and runp(tray.interaction_check(inter(800, "Ana"))) is True
# 20 natural na bandeja
solo = criar(paineis.BandejaDados, 800, "Ana")
try:
    dice.roll = lambda n: dice.RollResult(n, [20], 0, 20)
    c = clique(solo, "Rolar", 800, "Ana", "🎲"); assert "🌟 **20 natural!**" in followups(c)[0][1]["embed"].description
finally:
    dice.roll = real_roll
# a ajuda conhece os botões e o /dados
assert "botões" in ajuda.AJUDA["minha_ficha"]["resumo"] and "bandeja de dados" in ajuda.AJUDA["dados"]["resumo"] and "Ou é só clicar" not in ajuda.AJUDA["dados"]["detalhes"]
print("R. painéis com botões OK")

# ============================ S. ficha mais bonita: cor da raça, resumo no topo e imagem por link ============================
def ficha_de(uid, nome): 
    i = inter(uid, nome); runp(bot.minha_ficha.callback(i, None)); return sent(i)[1]["embed"]
n1 = novo(820, "Nova", "Sem Nada Ainda")
e = ficha_de(820, "Nova"); assert e.author.name == "Nível 1" and e.color == discord.Color.dark_purple() and e.thumbnail.url is None      # personagem novo: roxo de sempre
db.set_race(row(820, "Sem Nada Ainda")["id"], "Vampiro", 90)
e = ficha_de(820, "Nova"); assert e.author.name == "🩸 Vampiro · Nível 1" and e.color.value == lore.RACAS["Vampiro"]["cor"]
db.set_class(row(820, "Sem Nada Ainda")["id"], "Ladrão"); db.add_xp(row(820, "Sem Nada Ainda")["id"], 3000, "teste", "9", "M")
e = ficha_de(820, "Nova"); assert e.author.name == "🩸 Vampiro · 🎓 Ladrão · Nível 3" and e.title == "📖 Ficha de Sem Nada Ainda"
for raca, cor, emoji in (("Humano", lore.RACAS["Humano"]["cor"], "🕯️"), ("Dhampir", lore.RACAS["Dhampir"]["cor"], "🌒")):
    db.set_race(row(820, "Sem Nada Ainda")["id"], raca, 50); e = ficha_de(820, "Nova")
    assert e.color.value == cor and e.author.name.startswith(f"{emoji} {raca} · ")
_urls = dict(lore.IMAGENS_URL); lore.IMAGENS_URL.clear()                                                              # aqui só entra o que o teste põe: nada de links de verdade
try:
    e = ficha_de(820, "Nova"); assert e.thumbnail.url is None                                                         # o arquivo de assets/ não vira miniatura (não dá pra anexar na ficha privada)
    lore.IMAGENS_URL["raca-dhampir"] = "https://exemplo.com/dhampir.gif"                                              # link direto: aparece na ficha (privada, sem anexo)
    e = ficha_de(820, "Nova"); assert e.thumbnail.url == "https://exemplo.com/dhampir.gif"
    db.set_race(row(820, "Sem Nada Ainda")["id"], "Humano", 50); e = ficha_de(820, "Nova"); assert e.thumbnail.url is None
finally:
    lore.IMAGENS_URL.clear(); lore.IMAGENS_URL.update(_urls)
assert ficha_de(820, "Nova").thumbnail.url == lore.IMAGENS_URL["raca-humano"]                                         # com os gifs de verdade, a ficha do Humano mostra o da Sypha
mfic = inter(820, "Nova"); runp(bot.minha_ficha.callback(mfic, None)); assert "files" not in sent(mfic)[1]              # ficha privada nunca leva anexo
# o painel refaz a ficha com a mesma cor e o mesmo resumo
pv = criar(paineis.PainelFicha, 820, row(820, "Sem Nada Ainda")["id"], "Nova"); c = clique(pv, "Níveis", 820, "Nova")
assert editada(c)["embed"].author.name.endswith("Nível 3") and editada(c)["embed"].color.value == lore.RACAS["Humano"]["cor"]
print("S. ficha mais bonita OK")

# ============================ T. três chances de rolar raça e classe social ============================
db.DB_PATH = os.path.join(tmp, "chances.db"); db.init_db()
def tent(uid, nome): c = row(uid, nome); return (c["race_attempts"], c["social_class_attempts"])
def confirmar_de(i):
    v = sent(i)[1]["view"]; assert isinstance(v, paineis.ConfirmarRepeticao); return v

# --- raça pelo comando: a primeira rola direto; das próximas em diante, pergunta antes de trocar ---
r1 = novo(900, "Rita", "Rita Rolos"); gm900 = alvo(900, "Rita")
with dados(40): run(bot.raca_inicial.callback(r1, None))
assert titulo(r1) == "Humanos" and rodape(r1) == "jogador: Rita · tentativa 1 de 3" and tent(900, "Rita Rolos") == (1, 0)
with dados():                                                                                             # pedir de novo NÃO rola: só pergunta
    run(bot.raca_inicial.callback(r1, None))
assert titulo(r1) == "🔄 Rolar a raça de novo?" and "Rolando de novo, sobram 1." in desc(r1) and "Você já usou 1 de 3 chances" in desc(r1) and tent(900, "Rita Rolos") == (1, 0)
conf = confirmar_de(r1)
assert [b.label for b in conf.children] == ["Rolar de novo", "Manter"] and conf.children[0].style == discord.ButtonStyle.danger and conf.dono_id == 900
assert runp(conf.interaction_check(inter(999, "Intruso"))) is False and runp(conf.interaction_check(inter(900, "Rita"))) is True
# "Manter": nada muda, volta pro painel
c = inter(900, "Rita"); runp(conf.children[1].callback(c))
assert isinstance(editada(c)["view"], paineis.PainelFicha) and c.followup.send.call_count == 0 and tent(900, "Rita Rolos") == (1, 0) and row(900, "Rita Rolos")["race"] == "Humano"
# "Rolar de novo": troca o resultado, gasta uma chance, o cartão sai público e o painel volta
conf = confirmar_de(r1)
with dados(90): c = inter(900, "Rita"); runp(conf.children[0].callback(c))
(_, fk), = followups(c); assert nome_do_cartao(fk["embed"]) == "Vampiros" and fk["embed"].footer.text == "jogador: Rita · tentativa 2 de 3" and "ephemeral" not in fk
assert [f.filename for f in fk["files"]] == ["raca-vampiro.jpg"]
assert row(900, "Rita Rolos")["race"] == "Vampiro" and row(900, "Rita Rolos")["race_roll"] == 90 and tent(900, "Rita Rolos") == (2, 0)      # a última vale
assert isinstance(editada(c)["view"], paineis.PainelFicha) and estado(editada(c)["view"])["Raça (1)"] == ("🔄", False)
assert [h["total"] for h in reversed(historico_de(900))] == [40, 90] and {h["purpose"] for h in historico_de(900)} == {"raca_inicial"}      # todas as rolagens ficam no histórico
# a terceira é a última
r1b = inter(900, "Rita"); runp(bot.raca_inicial.callback(r1b, None)); conf = confirmar_de(r1b); assert "sobram 0." in desc(r1b)
with dados(97): c = inter(900, "Rita"); runp(conf.children[0].callback(c))
assert nome_do_cartao(followups(c)[0][1]["embed"]) == "Dhampirs" and followups(c)[0][1]["embed"].footer.text == "jogador: Rita · última chance" and tent(900, "Rita Rolos") == (3, 0)
assert estado(editada(c)["view"])["Raça"] == ("✅", True)                                                       # acabaram as chances: botão verde e desligado
# passou de 3: o comando recusa, sem rolar
with dados(): r2 = inter(900, "Rita"); runp(bot.raca_inicial.callback(r2, None))
assert txt(r2) == "**Rita Rolos** já usou as 3 chances de rolar a Raça e ficou com **Dhampir**. Fala com um mestre se precisar de outra." and sent(r2)[1]["ephemeral"] and "view" not in sent(r2)[1]
# um clique atrasado no "Rolar de novo" (as chances acabaram nesse meio tempo) não rola: o comando explica
with dados(): c = inter(900, "Rita"); runp(conf.children[0].callback(c))
assert "já usou as 3 chances" in followups(c)[0][0] and followups(c)[0][1]["ephemeral"] and tent(900, "Rita Rolos") == (3, 0)

# --- a magia continua sendo uma rolagem só (vantagem é com o mestre) ---
mg = novo(901, "Mago", "Mago Uma Vez"); preparar(901, "Mago Uma Vez", "Vampiro", "Mundano"); db.clear_definition(row(901, "Mago Uma Vez")["id"], "magic_rank")
with dados(60): run(bot.magia_inicial.callback(mg, None))
assert titulo(mg) == "Rank Raro" and "🎲 1d100 = **60**" in desc(mg)                                           # a magia segue mostrando o dado
with dados(): run(bot.magia_inicial.callback(mg, None))
assert "já tem Rank de Magia: **Raro**" in txt(mg) and "view" not in sent(mg)[1] and sent(mg)[1]["ephemeral"]

# --- classe social: rolar de novo troca o Estado e o clero ---
e1 = novo(902, "Est", "Est Rolos"); a902 = alvo(902, "Est")
with dados(95, 70): run(bot.classe_social.callback(e1, None))
assert titulo(e1) == "1° Estado —  Clero" and "✝ Alto Clero=" in txt(e1) and tent(902, "Est Rolos") == (0, 1)
run(bot.classe_social.callback(e1, None)); assert titulo(e1) == "🔄 Rolar a classe social de novo?" and "**1º Estado · Clero (Alto Clero)**" in desc(e1)
conf = confirmar_de(e1)
with dados(50): c = inter(902, "Est"); runp(conf.children[0].callback(c))
(_, fk), = followups(c); assert nome_do_cartao(fk["embed"]) == "3° Estado —  Camponeses" and fk["embed"].fields == [] and fk["embed"].footer.text == "jogador: Est · tentativa 2 de 3"
ch = row(902, "Est Rolos"); assert (ch["social_class"], ch["clergy"], ch["clergy_roll"], ch["social_class_roll"], ch["social_class_attempts"]) == ("3º Estado", None, None, 50, 2)   # o clero antigo some
assert [h["purpose"] for h in reversed(historico_de(902))] == ["classe_social", "clero", "classe_social"]
run(bot.classe_social.callback(e1, None)); conf = confirmar_de(e1)
with dados(100): c = inter(902, "Est"); c.guild = NS(roles=[NS(id=555, name="Mestre", mention="<@&555>")]); runp(conf.children[0].callback(c))
(conteudo, fk), = followups(c); assert fk["embed"].title == "🎲 Resultado especial" and conteudo == "<@&555>" and fk["embed"].footer.text == "jogador: Est · última chance"
with dados(): r = inter(902, "Est"); runp(bot.classe_social.callback(r, None))
assert "tirou 100 no sorteio da Classe Social" in txt(r) and "view" not in sent(r)[1]                          # o 100 fecha: quem decide é o mestre
assert estado(editada(c)["view"])["Classe social"] == ("⏳", True)
run(bot.mestre_corrigir_estado.callback(gm, a902, "2", None)); assert row(902, "Est Rolos")["social_class"] == "2º Estado" and tent(902, "Est Rolos")[1] == 3     # decisão do mestre fecha as chances
with dados(): r = inter(902, "Est"); runp(bot.classe_social.callback(r, None))
assert "já usou as 3 chances de rolar a Classe Social e ficou com **2º Estado · Nobreza**" in txt(r)

# --- mestre: apagar devolve as chances; corrigir na mão fecha ---
run(bot.mestre_apagar.callback(gm, a902, "social_class", None)); assert tent(902, "Est Rolos") == (0, 0) and row(902, "Est Rolos")["social_class"] is None
with dados(20): run(bot.classe_social.callback(e1, None))
assert titulo(e1) == "3° Estado —  Camponeses" and rodape(e1) == "jogador: Est · tentativa 1 de 3" and tent(902, "Est Rolos") == (0, 1)     # de novo com 3 chances
run(bot.mestre_corrigir_raca.callback(gm, a902, "Vampiro", None)); assert tent(902, "Est Rolos")[0] == 3
with dados(): r = inter(902, "Est"); runp(bot.raca_inicial.callback(r, None))
assert "já usou as 3 chances de rolar a Raça e ficou com **Vampiro**" in txt(r)

# --- escolher a classe fecha as chances que sobravam ---
k = novo(903, "Cla", "Cla Fechada")
with dados(40): run(bot.raca_inicial.callback(k, None))
with dados(20): run(bot.classe_social.callback(k, None))
assert tent(903, "Cla Fechada") == (1, 1)
run(bot.classe_escolher.callback(k, "Sábio", None))
for cmd in (bot.raca_inicial, bot.classe_social):
    with dados(): r = inter(903, "Cla"); runp(cmd.callback(r, None))
    assert "já escolheu a classe, então" in txt(r) and "não muda mais" in txt(r) and "view" not in sent(r)[1], txt(r)
r = inter(903, "Cla"); runp(bot.raca_inicial.callback(r, None)); assert "a Raça não muda mais (Humano)" in txt(r)
r = inter(903, "Cla"); runp(bot.classe_social.callback(r, None)); assert "a Classe Social não muda mais (3º Estado · Camponeses)" in txt(r)
assert tent(903, "Cla Fechada") == (1, 1)

# --- painel: o botão "Raça (n)" abre a confirmação dentro do painel, e a classe social também ---
pz = novo(904, "Pan", "Pan Chances")
with dados(40): c = clique(criar(paineis.PainelFicha, 904, row(904, "Pan Chances")["id"], "Pan"), "Raça", 904, "Pan")
pn = editada(c)["view"]; assert estado(pn)["Raça (2)"] == ("🔄", False)
c = clique(pn, "Raça (2)", 904, "Pan"); tela = editada(c)["view"]
assert isinstance(tela, paineis.ConfirmarRepeticao) and c.followup.send.call_count == 0 and editada(c)["embed"].title == "🔄 Rolar a raça de novo?" and pn.is_finished()
assert tent(904, "Pan Chances") == (1, 0)                                                                    # abrir a confirmação não gasta chance
with dados(50): c = clique(criar(paineis.PainelFicha, 904, row(904, "Pan Chances")["id"], "Pan"), "Classe social", 904, "Pan")
pn = editada(c)["view"]; assert estado(pn)["Classe social (2)"] == ("🔄", False) and estado(pn)["Raça (2)"] == ("🔄", False)
c = clique(pn, "Classe social (2)", 904, "Pan"); tela = editada(c)["view"]; assert isinstance(tela, paineis.ConfirmarRepeticao) and editada(c)["embed"].title == "🔄 Rolar a classe social de novo?"
with dados(85): c = inter(904, "Pan"); runp(tela.children[0].callback(c))
assert nome_do_cartao(followups(c)[0][1]["embed"]) == "2° Estado —  Nobreza" and tent(904, "Pan Chances") == (1, 2) and estado(editada(c)["view"])["Classe social (1)"] == ("🔄", False)
# painel com a chavinha da ordem desligada: rolar de novo continua valendo
bot.ORDEM_DA_CRIACAO = False
try:
    assert estado(criar(paineis.PainelFicha, 904, row(904, "Pan Chances")["id"], "Pan"))["Raça (2)"] == ("🔄", False)
finally:
    bot.ORDEM_DA_CRIACAO = True
# a ajuda e o texto dos comandos falam das chances
assert "3 chances" in ajuda.AJUDA["raca_inicial"]["detalhes"] and "3 chances" in ajuda.AJUDA["classe_social"]["detalhes"] and "uma rolagem só" in ajuda.AJUDA["magia_inicial"]["detalhes"] and "vantagem" in ajuda.AJUDA["magia_inicial"]["detalhes"]
print("T. três chances OK")

# ============================ U. Disciplinas ============================
db.DB_PATH = os.path.join(tmp, "disc.db"); db.init_db()
pay = {c.name: c.to_dict(bot.bot.tree) for c in bot.bot.tree.get_commands()}
dsc = pay["disciplinas"]; md = sub_("mestre", "disciplina")
assert [o["name"] for o in dsc["options"]] == ["personagem"] and req(dsc["options"]) == set() and opt(dsc, "personagem")["autocomplete"] is True and len(dsc["description"]) <= 100
assert [o["name"] for o in md["options"]] == ["usuario", "disciplina", "grau", "personagem"] and req(md["options"]) == {"usuario", "disciplina", "grau"}
assert [c["value"] for c in opt(md, "disciplina")["choices"]] == list(rules.DISCIPLINES) and (opt(md, "grau")["min_value"], opt(md, "grau")["max_value"]) == (0, 5)
def graus_de(uid, nome): return db.get_disciplines(row(uid, nome)["id"])
def painel_de(uid, nome, jogador): p = criar(paineis.PainelFicha, uid, row(uid, nome)["id"], jogador); return p
def tela_disc(painel, uid, jogador):
    c = clique(painel, "Disciplinas", uid, jogador, "🩸"); return c, editada(c)["view"]
def escolher(tela, disciplina, uid, jogador):
    c = inter(uid, jogador); seletor(tela)._values = [disciplina]; runp(seletor(tela).callback(c)); return c
def subir(tela, uid, jogador):
    b = [x for x in tela.children if isinstance(x, discord.ui.Button) and x.label.startswith("Subir")][0]
    c = inter(uid, jogador); runp(b.callback(c)); return c
def pra_subir(c): return {f.name: f.value for f in editada(c)["embed"].fields}["Pra subir"]

# --- a ficha: o campo Disciplinas só existe pra Vampiro e Dhampir ---
v = novo(950, "Vlad", "Vlad Vampiro"); preparar(950, "Vlad Vampiro", "Vampiro", "Mundano"); a950 = alvo(950, "Vlad")
d = novo(951, "Dani", "Dani Dhampir"); preparar(951, "Dani Dhampir", "Dhampir", "Sábio"); a951 = alvo(951, "Dani")
h = novo(952, "Hugo", "Hugo Humano"); preparar(952, "Hugo Humano", "Humano", "Sábio")
run(bot.minha_ficha.callback(v, None)); assert campos(v)["Disciplinas"] == "Pontos: 0 de 4 usados (4 livres)\nnenhuma ainda (o botão **Disciplinas** do `/minha_ficha` abre o painel)"
assert list(campos(v))[-2:] == ["Disciplinas", "Ranks das perícias especiais"]                             # entra antes dos ranks, que continuam por último
run(bot.minha_ficha.callback(d, None)); assert campos(d)["Disciplinas"].startswith("Pontos: 0 de 3 usados (3 livres)")
run(bot.minha_ficha.callback(h, None)); assert "Disciplinas" not in campos(h)
run(bot.mestre_ficha.callback(gm, a950, None)); assert "Disciplinas" in campos(gm)                          # o mestre também vê

# --- o botão na ficha ---
pv = painel_de(950, "Vlad Vampiro", "Vlad"); pv.origem = v; confere_componentes(pv)
assert estado(pv)["Disciplinas"] == ("🩸", False) and botao(pv, "Disciplinas").style == discord.ButtonStyle.primary and botao(pv, "Disciplinas").row == 1
assert "Disciplinas" not in estado(painel_de(952, "Hugo Humano", "Hugo"))                          # Humano não tem o botão

# --- o painel: menu, texto de cada grau e subir um grau por clique ---
c, tela = tela_disc(pv, 950, "Vlad")
assert isinstance(tela, paineis.PainelDisciplinas), type(tela)
assert pv.is_finished(), "o painel da ficha devia ter saído de cena"
assert tela.origem is v, (tela.origem, v)
assert c.followup.send.call_count == 0, c.followup.send.call_args_list
e = editada(c)["embed"]; assert e.title == "🩸 Disciplinas de Vlad Vampiro" and "Pontos: 0 de 4 usados (4 livres)" in e.description and [f.name for f in e.fields] == list(rules.DISCIPLINES)
confere_componentes(tela); sel = seletor(tela)
assert [o.value for o in sel.options] == list(rules.DISCIPLINES) and sel.options[0].description == "grau 0/5 · força sobrenatural bruta" and sel.options[8].description == "em desenvolvimento"
assert [b.label for b in tela.children if isinstance(b, discord.ui.Button)] == ["Voltar"]                    # sem escolha: só o Voltar
c = escolher(tela, "Potência", 950, "Vlad"); e = editada(c)["embed"]
assert e.title == "🩸 Potência" and [f.name for f in e.fields] == ["▫️ Grau 1", "▫️ Grau 2", "▫️ Grau 3", "Graus 4 e 5", "Pra subir"] and e.footer.text == "Pontos: 0 de 4 usados (4 livres)"
assert pra_subir(c) == "Aperta o botão pra gastar 1 ponto e subir pro grau 1. Não dá pra desfazer." and [o.default for o in seletor(tela).options][0] is True
assert [b.label for b in tela.children if isinstance(b, discord.ui.Button)] == ["Subir pro grau 1", "Ver todas", "Voltar"]
c = subir(tela, 950, "Vlad"); (aviso, fk), = followups(c)
assert aviso == "🩸 **Potência** subiu pro grau 1. Sobram 3 pontos." and fk["ephemeral"] is True and graus_de(950, "Vlad Vampiro") == {"Potência": 1}
e = editada(c)["embed"]; assert e.fields[0].name == "✅ Grau 1" and e.fields[1].name == "▫️ Grau 2" and e.footer.text == "Pontos: 1 de 4 usados (3 livres)" and botao(tela, "Subir pro grau 2")
c = subir(tela, 950, "Vlad"); assert followups(c)[0][0] == "🩸 **Potência** subiu pro grau 2. Sobram 2 pontos."
c = subir(tela, 950, "Vlad"); assert followups(c)[0][0] == "🩸 **Potência** subiu pro grau 3. Sobra 1 ponto." and graus_de(950, "Vlad Vampiro") == {"Potência": 3}
b = [x for x in tela.children if isinstance(x, discord.ui.Button)][0]; assert b.label == "Subir" and b.disabled                # o jogador não passa do grau 3 sozinho
assert pra_subir(c) == "Essa Disciplina já está no grau 3. Os graus 4 e 5 só um mestre concede."
c = inter(950, "Vlad"); runp(b.callback(c))                                                                  # painel velho: a regra confere de novo na hora
assert followups(c)[0][0] == "Essa Disciplina já está no grau 3. Os graus 4 e 5 só um mestre concede." and graus_de(950, "Vlad Vampiro") == {"Potência": 3}
c = escolher(tela, "Celeridade", 950, "Vlad"); c = subir(tela, 950, "Vlad")
assert followups(c)[0][0] == "🩸 **Celeridade** subiu pro grau 1. Não sobrou ponto." and graus_de(950, "Vlad Vampiro") == {"Potência": 3, "Celeridade": 1}
c = escolher(tela, "Ofuscação", 950, "Vlad"); assert pra_subir(c) == "Você não tem pontos de Disciplina sobrando. Vem +1 a cada 2 níveis (2, 4, 6, 8 e 10)."
b = [x for x in tela.children if isinstance(x, discord.ui.Button)][0]; assert b.disabled and b.label == "Subir"
c = inter(950, "Vlad"); runp(b.callback(c)); assert "não tem pontos de Disciplina sobrando" in followups(c)[0][0] and graus_de(950, "Vlad Vampiro") == {"Potência": 3, "Celeridade": 1}
# a ficha já mostra o que foi gasto
run(bot.minha_ficha.callback(v, None)); assert campos(v)["Disciplinas"] == "Pontos: 4 de 4 usados\n**Potência** 3/5 ▰▰▰▱▱\n**Celeridade** 1/5 ▰▱▱▱▱"
# subir de nível dá +1 ponto (nível 2) e o aviso do /mestre dar_xp lembra do botão
run(bot.mestre_dar_xp.callback(gm, a950, 1000, None, None)); assert "Você ganhou +1 ponto de Disciplina: gasta no botão **Disciplinas** do `/minha_ficha`." in desc(gm)
c = escolher(tela, "Ofuscação", 950, "Vlad"); assert pra_subir(c).startswith("Aperta o botão")
c = subir(tela, 950, "Vlad"); assert graus_de(950, "Vlad Vampiro")["Ofuscação"] == 1 and "Não sobrou ponto." in followups(c)[0][0]
# "Ver todas" e "Voltar"
c = clique(tela, "Ver todas", 950, "Vlad", "📜"); assert editada(c)["embed"].title == "🩸 Disciplinas de Vlad Vampiro" and tela.selecionada is None
por = {f.name: f.value for f in editada(c)["embed"].fields}; assert por["Potência"].startswith("▰▰▰▱▱ 3/5") and por["Domínio"].startswith("▱▱▱▱▱ 0/5") and por["Sanguessugia"] == "⏳ em desenvolvimento"
c = clique(tela, "Voltar", 950, "Vlad", "⬅️"); assert isinstance(editada(c)["view"], paineis.PainelFicha) and editada(c)["embed"].title == "📖 Ficha de Vlad Vampiro"
assert estado(editada(c)["view"])["Disciplinas"] == ("🩸", False) and botao(editada(c)["view"], "Disciplinas").style == discord.ButtonStyle.secondary       # sem ponto sobrando: cinza
assert runp(tela.interaction_check(inter(999, "Intruso"))) is False and runp(tela.interaction_check(inter(950, "Vlad"))) is True

# --- Sanguessugia: bloqueada pra todo mundo enquanto o texto não existir ---
tela = criar(paineis.PainelDisciplinas, 951, row(951, "Dani Dhampir")["id"], "Dani"); tela.origem = d
c = escolher(tela, "Sanguessugia", 951, "Dani"); e = editada(c)["embed"]
assert [f.name for f in e.fields][:1] == ["⏳ Em desenvolvimento"] and "Grau 1" not in " ".join(f.name for f in e.fields) and "ainda não foram definidos" in e.fields[0].value
assert "gastar ponto nela por enquanto" in pra_subir(c)
b = [x for x in tela.children if isinstance(x, discord.ui.Button)][0]; assert b.label == "Subir" and b.disabled
c = inter(951, "Dani"); runp(b.callback(c)); assert followups(c)[0][0] == paineis.TEXTO_DO_PROBLEMA["bloqueada"] and graus_de(951, "Dani Dhampir") == {}
rules.SANGUESSUGIA_LIBERADA = True                                                                           # o dia em que o texto ficar pronto: é só virar a chave
try:
    tela = criar(paineis.PainelDisciplinas, 951, row(951, "Dani Dhampir")["id"], "Dani"); tela.origem = d
    c = escolher(tela, "Sanguessugia", 951, "Dani"); c = subir(tela, 951, "Dani")
    assert followups(c)[0][0] == "🩸 **Sanguessugia** subiu pro grau 1. Sobram 2 pontos." and graus_de(951, "Dani Dhampir") == {"Sanguessugia": 1}
finally:
    rules.SANGUESSUGIA_LIBERADA = False
db.set_discipline_grade(row(951, "Dani Dhampir")["id"], "Sanguessugia", 0)

# --- /disciplinas: qualquer um lê; só Vampiro e Dhampir gastam ---
c = inter(950, "Vlad"); run(bot.disciplinas_comando.callback(c, None)); pn = enviada(c)
assert isinstance(pn, paineis.PainelDisciplinas) and sent(c)[1]["ephemeral"] and pn.origem is c and titulo(c) == "🩸 Disciplinas de Vlad Vampiro" and pn.personagem_id == row(950, "Vlad Vampiro")["id"]
c = inter(952, "Hugo"); run(bot.disciplinas_comando.callback(c, None)); pn = enviada(c)
assert titulo(c) == "🩸 Disciplinas" and "Só **Vampiros e Dhampirs** têm Disciplinas" in desc(c) and "0/5" not in " ".join(f.value for f in sent(c)[1]["embed"].fields)
assert seletor(pn).options[0].description == "força sobrenatural bruta"
c2 = escolher(pn, "Domínio", 952, "Hugo"); e = editada(c2)["embed"]
assert [f.name for f in e.fields] == ["Grau 1", "Grau 2", "Grau 3", "Graus 4 e 5"] and e.footer.text is None and e.fields[0].value.startswith("Impõe a sua vontade")     # só leitura: sem marcação nem "Pra subir"
assert [b.label for b in pn.children if isinstance(b, discord.ui.Button)] == ["Ver todas", "Voltar"]        # sem botão de subir
c = inter(952, "Hugo"); runp(pn._subir(c)); assert followups(c)[0][0] == "Só Vampiros e Dhampirs têm Disciplinas." and graus_de(952, "Hugo Humano") == {}
c = inter(960, "Sem Personagem"); run(bot.disciplinas_comando.callback(c, None)); pn = enviada(c)                # sem personagem: também lê
assert titulo(c) == "🩸 Disciplinas" and pn.personagem_id is None and [b for b in pn.children if isinstance(b, discord.ui.Button)] == []
c2 = escolher(pn, "Regeneração", 960, "Sem Personagem"); assert [f.name for f in editada(c2)["embed"].fields][-1] == "Limite" and [b.label for b in pn.children if isinstance(b, discord.ui.Button)] == ["Ver todas"]
c = inter(950, "Vlad"); run(bot.disciplinas_comando.callback(c, "Fantasma")); assert "Não achei nenhum personagem seu" in txt(c) and sent(c)[1]["ephemeral"] and "view" not in sent(c)[1]
for painel_lido in (criar(paineis.PainelDisciplinas, 952, row(952, "Hugo Humano")["id"], "Hugo"), criar(paineis.PainelDisciplinas, 960, None, "Sem")): confere_componentes(painel_lido)

# --- /mestre disciplina: sem conferir pontos, com registro ---
run(bot.mestre_disciplina.callback(gm, alvo(952, "Hugo"), "Potência", 1, None)); assert "só Vampiros e Dhampirs têm Disciplinas" in txt(gm) and "corrigir_raca" in txt(gm) and sent(gm)[1]["ephemeral"] and graus_de(952, "Hugo Humano") == {}
run(bot.mestre_disciplina.callback(gm, alvo(960, "Sem Personagem"), "Potência", 1, None)); assert "ainda não tem personagem" in txt(gm)
run(bot.mestre_disciplina.callback(gm, a951, "Sanguessugia", 1, None)); assert txt(gm) == paineis.TEXTO_DO_PROBLEMA["bloqueada"] and sent(gm)[1]["ephemeral"] and graus_de(951, "Dani Dhampir") == {}
run(bot.mestre_disciplina.callback(gm, a951, "Potência", 4, None))                                            # grau 4 direto (só o mestre concede)
assert titulo(gm) == "⬆️ Potência: grau 4/5" and "**0** → **4**  ▰▰▰▰▱" in desc(gm) and "Pontos: 3 de 3 usados" in desc(gm) and "Grau concedido pelo mestre: os graus 4 e 5 não gastam ponto." in desc(gm)
assert not sent(gm)[1].get("ephemeral") and graus_de(951, "Dani Dhampir") == {"Potência": 4} and "Os graus 1 a 3 contam como pontos gastos do jogador" in rodape(gm)
run(bot.mestre_disciplina.callback(gm, a951, "Potência", 4, None)); assert "Nada mudou" in txt(gm) and sent(gm)[1]["ephemeral"]
run(bot.mestre_disciplina.callback(gm, a951, "Presença", 2, "Dani Dhampir")); assert "Pontos: 5 de 3 usados (passou 2)" in desc(gm) and "Grau concedido" not in desc(gm)   # o mestre não é barrado pelos pontos
run(bot.mestre_disciplina.callback(gm, a951, "Presença", 0, None)); assert titulo(gm) == "🛠️ Presença: grau 0/5" and graus_de(951, "Dani Dhampir") == {"Potência": 4}
run(bot.mestre_disciplina.callback(gm, a951, "Potência", 1, "Fantasma")); assert "não tem nenhum personagem chamado" in txt(gm)
with sqlite3.connect(db.DB_PATH) as cn:
    assert [x for x in cn.execute("SELECT action, detail FROM master_actions WHERE action='disciplina' ORDER BY id")] == [("disciplina", "Potência: 0 -> 4"), ("disciplina", "Presença: 0 -> 2"), ("disciplina", "Presença: 2 -> 0")]
# o jogador com grau 4 do mestre não sobe mais sozinho, e a ficha mostra o 4
tela = criar(paineis.PainelDisciplinas, 951, row(951, "Dani Dhampir")["id"], "Dani"); tela.origem = d
c = escolher(tela, "Potência", 951, "Dani"); assert pra_subir(c) == "Essa Disciplina já está no grau 4. Os graus 4 e 5 só um mestre concede." and [f.name for f in editada(c)["embed"].fields][:3] == ["✅ Grau 1", "✅ Grau 2", "✅ Grau 3"]
run(bot.minha_ficha.callback(d, None)); assert "**Potência** 4/5 ▰▰▰▰▱" in campos(d)["Disciplinas"] and campos(d)["Disciplinas"].startswith("Pontos: 3 de 3 usados")
# subir de nível de um Humano não fala de Disciplina
run(bot.mestre_dar_xp.callback(gm, alvo(952, "Hugo"), 1000, None, None)); assert "Disciplina" not in desc(gm)
# excluir o personagem leva as Disciplinas junto
async def exclui_vlad():
    u = inter(950, "Vlad"); await bot.personagem_excluir.callback(u, "Vlad Vampiro"); view = u.response.send_message.call_args.kwargs["view"]
    await view.confirmar.callback(inter(950, "Vlad"))
run(exclui_vlad()); assert row(950, "Vlad Vampiro") is None
with sqlite3.connect(db.DB_PATH) as cn: assert cn.execute("SELECT COUNT(*) FROM character_disciplines").fetchone()[0] == 1       # só as do Dani sobraram
print("U. Disciplinas OK")

# ============================ V. Escudo do Mestre, /iniciativa e /intencao ============================
import cena, escudo
db.DB_PATH = os.path.join(tmp, "escudo.db"); db.init_db()
SEGREDO = "Esfaquear o duque sem ninguém ver"
def canal_fake():
    pm = MagicMock(); pm.edit = AsyncMock()
    ch = MagicMock(); ch.get_partial_message = MagicMock(return_value=pm); ch.send = AsyncMock(return_value=NS(id=777)); ch.pm = pm
    return ch
def no_canal(i, ch, canal_id="5000"):
    i.channel = ch; i.channel_id = canal_id; return i
def ic(uid, nome, ch, canal_id="5000", **extras): return no_canal(inter(uid, nome, **extras), ch, canal_id)
def clicar(view, rotulo, uid, nome, ch, canal_id="5000", emoji=None, **extras):
    i = ic(uid, nome, ch, canal_id, **extras); runp(botao(view, rotulo, emoji).callback(i)); return i
def submeter(modal, valores, uid, nome, ch, canal_id="5000", **extras):
    for campo, v in valores.items(): campo._value = v
    i = ic(uid, nome, ch, canal_id, **extras); runp(modal.on_submit(i)); return i
def menu(view, comeco):
    achados = [x for x in view.children if isinstance(x, discord.ui.Select) and x.placeholder.startswith(comeco)]
    assert len(achados) == 1, (comeco, [x.placeholder for x in view.children if isinstance(x, discord.ui.Select)]); return achados[0]
def ultimo_quadro(ch): return ch.pm.edit.call_args.kwargs
def texto_do_quadro(ch):
    e = ultimo_quadro(ch)["embed"]; return " ".join([e.title or "", e.description or "", e.footer.text or ""] + [f.name + f.value for f in e.fields])
MESTRE = dict(roles=["Mestre"])
CH = canal_fake()

# --- os comandos: as opções e as descrições ---
pay = {c.name: c.to_dict(bot.bot.tree) for c in bot.bot.tree.get_commands()}
assert pay["iniciativa"].get("options", []) == []
ci, cn = pay["intencao"], sub_("mestre", "escudo")
assert [o["name"] for o in ci["options"]] == ["texto"] and req(ci["options"]) == set() and (opt(ci, "texto")["min_length"], opt(ci, "texto")["max_length"]) == (1, 200)
assert len(pay["iniciativa"]["description"]) <= 100 and len(ci["description"]) <= 100 and len(cn["description"]) <= 100 and cn.get("options", []) == []
assert bot.bot.setup_hook is bot._preparar_bot and bot.escudo.CONFIG.eh_mestre is bot._membro_eh_mestre and bot.escudo.CONFIG.bloqueio_de_rolagem is bot._bloqueio_curto

# --- sem cena aberta, ninguém entra nem manda intenção ---
pronto(701, "Ana", "Ana Cena"); pronto(702, "Beto", "Beto Cena"); novo(703, "Caio", "Caio Incompleto")
for cmd, args in ((bot.iniciativa_comando, ()), (bot.intencao_comando, ("Atacar",)), (bot.intencao_comando, (None,))):
    i = ic(701, "Ana", CH); run(cmd.callback(i, *args)); assert txt(i) == escudo.SEM_CENA and sent(i)[1]["ephemeral"]
assert db.get_active_scene("5000") is None

# --- o mestre abre o Escudo: sem cena, só o botão de iniciar ---
m = ic(700, "Mestre Belmont", CH, **MESTRE); run(bot.mestre_escudo.callback(m)); esc = enviada(m)
assert isinstance(esc, escudo.EscudoDoMestre) and sent(m)[1]["ephemeral"] and esc.origem is m and esc.channel_id == "5000" and titulo(m) == "🛡️ Escudo do Mestre" and "Não tem cena aberta neste canal" in desc(m)
assert [b.label for b in esc.children] == ["Iniciar cena"]; confere_componentes(esc)
assert runp(esc.interaction_check(ic(999, "Intruso", CH, **MESTRE))) is False                       # outro mestre não mexe na tela alheia
assert runp(esc.interaction_check(ic(700, "Mestre Belmont", CH, **MESTRE))) is True
perdeu = ic(700, "Mestre Belmont", CH); assert runp(esc.interaction_check(perdeu)) is False and perdeu.response.send_message.call_args.args[0] == escudo.SO_MESTRE     # perdeu o cargo: a tela não obedece mais
# iniciar a cena: formulário -> nome -> tela do escudo completa
c = clicar(esc, "Iniciar cena", 700, "Mestre Belmont", CH, **MESTRE); mc = c.response.send_modal.call_args.args[0]
assert isinstance(mc, escudo.ModalCena) and mc.title == "Nova cena" and mc.campo.max_length == 60 and mc.campo.required
c = submeter(mc, {mc.campo: "  Motim   na praça  "}, 700, "Mestre Belmont", CH, **MESTRE)
cena0 = db.get_active_scene("5000"); assert cena0["name"] == "Motim na praça" and cena0["created_by"] == "700" and cena0["guild_id"] == "999" and cena0["round"] == 1
(aviso, fk), = followups(c); assert "Cena **Motim na praça** aberta" in aviso and fk["ephemeral"] is True
esc = editada(c)["view"]; assert esc is not None and titulo(m) == "🛡️ Escudo do Mestre" and editada(c)["embed"].title == "🛡️ Escudo do Mestre · Motim na praça"
assert [b.label for b in esc.children if isinstance(b, discord.ui.Button)] == ["Próximo turno", "Mostrar iniciativa", "NPC", "Atualizar", "Encerrar"] and seletor(esc) is None; confere_componentes(esc)
mc2 = criar(escudo.ModalCena, esc); mc2.campo._value = "Outra"; c2 = ic(700, "Mestre Belmont", CH, **MESTRE); runp(mc2.on_submit(c2))
assert "Já tem uma cena aberta neste canal" in followups(c2)[0][0] and db.get_active_scene("5000")["id"] == cena0["id"]      # uma cena por canal
mc3 = criar(escudo.ModalCena, esc); mc3.campo._value = "   "; db.end_scene(cena0["id"]); c3 = ic(700, "Mestre Belmont", CH, **MESTRE); runp(mc3.on_submit(c3))
assert db.get_active_scene("5000")["name"] == "Cena" and db.get_active_scene("5000")["id"] != cena0["id"]                    # nome vazio vira "Cena"
db.end_scene(db.get_active_scene("5000")["id"]); cena0 = db.create_scene("999", "5000", "Motim na praça", "700"); SID = cena0["id"]
esc = criar(escudo.EscudoDoMestre, 700, "5000"); esc.origem = m

# --- o jogador entra na iniciativa: 1d20 + Destreza, só ele vê, e a regra de ficha pronta vale ---
i = ic(703, "Caio", CH); run(bot.iniciativa_comando.callback(i)); assert "A ficha de **Caio Incompleto** ainda não está pronta" in txt(i) and sent(i)[1]["ephemeral"] and db.get_participants(SID) == []
i = ic(710, "Sem Personagem", CH); run(bot.iniciativa_comando.callback(i)); assert "Você ainda não tem personagem" in txt(i) and db.get_participants(SID) == []
with dados(14): i = ic(701, "Ana", CH); run(bot.iniciativa_comando.callback(i))
assert txt(i) == "🎲 **Ana Cena**: 1d20 = 14 + Destreza 0 = **14** de iniciativa." and sent(i)[1]["ephemeral"] and [p["name"] for p in db.get_participants(SID)] == ["Ana Cena"]
assert CH.pm.edit.call_count == 0                                                                    # ainda não tem quadro no canal: nada a editar
with dados(): i = ic(701, "Ana", CH); run(bot.iniciativa_comando.callback(i))
assert "já está na cena, com iniciativa **14**" in txt(i) and len(db.get_participants(SID)) == 1
assert [h["purpose"] for h in historico_de(701)][-1] == "iniciativa"

# --- o mestre põe um NPC, e o menu de baixo aparece ---
c = clicar(esc, "NPC", 700, "Mestre Belmont", CH, **MESTRE); mn = c.response.send_modal.call_args.args[0]
assert isinstance(mn, escudo.ModalNpc) and mn.title == "NPC na cena" and mn.nome.max_length == 40 and mn.iniciativa.max_length == 12
c = submeter(mn, {mn.nome: "Guarda", mn.iniciativa: "abc"}, 700, "Mestre Belmont", CH, **MESTRE); assert "Iniciativa inválida" in followups(c)[0][0] and len(db.get_participants(SID)) == 1
c = submeter(mn, {mn.nome: "Guarda", mn.iniciativa: "12"}, 700, "Mestre Belmont", CH, **MESTRE); esc = editada(c)["view"]
assert followups(c)[0][0] == "➕ **Guarda** entrou na cena com iniciativa **12** (definida pelo mestre)." and [(p["name"], p["initiative"]) for p in db.get_participants(SID)] == [("Ana Cena", 14), ("Guarda", 12)]
sel = seletor(esc); confere_componentes(esc)
assert [o.label for o in sel.options] == ["1. Ana Cena", "2. Guarda"] and sel.options[1].description == "iniciativa 12 · NPC" and sel.options[0].description == "iniciativa 14" and sel.placeholder == "Editar ou remover alguém"

# --- o quadro público: postado uma vez, editado nas próximas, e refeito se apagarem ---
c = clicar(esc, "Mostrar iniciativa", 700, "Mestre Belmont", CH, **MESTRE)
kw = CH.send.call_args.kwargs; assert isinstance(kw["view"], escudo.QuadroDaCena) and kw["embed"].title == "⚔️ Motim na praça" and db.get_scene(SID)["board_message_id"] == "777"
assert "Quadro da iniciativa postado no canal" in followups(c)[0][0] and followups(c)[0][1]["ephemeral"] and CH.pm.edit.call_count == 0
esc = editada(c)["view"]
c = clicar(esc, "Mostrar iniciativa", 700, "Mestre Belmont", CH, **MESTRE); assert CH.send.call_count == 1 and CH.pm.edit.call_count == 1 and "Quadro atualizado" in followups(c)[0][0]      # segunda vez: edita, não posta outro
CH.get_partial_message.assert_called_with(777); esc = editada(c)["view"]
assert isinstance(ultimo_quadro(CH)["view"], escudo.QuadroDaCena)
CH.pm.edit.side_effect = discord.NotFound(MagicMock(status=404, reason="x"), "sumiu")                # apagaram o quadro: o bot posta outro
c = clicar(esc, "Mostrar iniciativa", 700, "Mestre Belmont", CH, **MESTRE); assert CH.send.call_count == 2 and "postado" in followups(c)[0][0]; esc = editada(c)["view"]
CH.pm.edit.side_effect = None
CH2 = canal_fake(); CH2.send.side_effect = discord.Forbidden(MagicMock(status=403, reason="x"), "sem permissão")   # sem permissão pra escrever
db.set_scene_board(SID, None); c = clicar(esc, "Mostrar iniciativa", 700, "Mestre Belmont", CH2, **MESTRE)
assert "Não consegui postar o quadro aqui" in followups(c)[0][0] and db.get_scene(SID)["board_message_id"] is None; esc = editada(c)["view"]
CH.send.reset_mock(); c = clicar(esc, "Mostrar iniciativa", 700, "Mestre Belmont", CH, **MESTRE); esc = editada(c)["view"]; assert db.get_scene(SID)["board_message_id"] == "777"; CH.pm.edit.reset_mock()

# --- os botões do quadro público: persistentes, qualquer jogador aperta ---
quadro = criar(escudo.QuadroDaCena)
assert quadro.is_persistent() and quadro.timeout is None and {b.custom_id: b.label for b in quadro.children} == {"cena:iniciativa": "Entrar na iniciativa", "cena:intencao": "Enviar intenção", "cena:minha": "Minha intenção"}
assert all(len(b.custom_id) <= 100 for b in quadro.children)
with dados(9): c = clicar(quadro, "Entrar na iniciativa", 702, "Beto", CH)                          # o mesmo que /iniciativa, pelo botão
assert txt(c) == "🎲 **Beto Cena**: 1d20 = 9 + Destreza 0 = **9** de iniciativa." and sent(c)[1]["ephemeral"] and CH.pm.edit.call_count == 1
assert "▶️" not in ultimo_quadro(CH)["embed"].description and "1. Ana Cena · 14 ⏳" in ultimo_quadro(CH)["embed"].description and "3. Beto Cena · 9 ⏳" in ultimo_quadro(CH)["embed"].description      # o quadro se atualizou sozinho
c = clicar(quadro, "Enviar intenção", 701, "Ana", CH); mi = c.response.send_modal.call_args.args[0]
assert isinstance(mi, escudo.ModalIntencao) and mi.title == "Sua intenção" and mi.campo.max_length == 200 and mi.campo.required and mi.campo.style == discord.TextStyle.paragraph
c = submeter(mi, {mi.campo: SEGREDO}, 701, "Ana", CH); assert "Intenção de **Ana Cena** enviada pro mestre" in txt(c) and sent(c)[1]["ephemeral"]
assert "3. Beto Cena · 9 ⏳" in ultimo_quadro(CH)["embed"].description and "1. Ana Cena · 14 📝" in ultimo_quadro(CH)["embed"].description and SEGREDO not in texto_do_quadro(CH)      # o quadro mostra 📝, e NUNCA o texto
c = clicar(quadro, "Minha intenção", 701, "Ana", CH); assert "**Ana Cena**, rodada 1: 📝 intenção aguardando o mestre" in txt(c) and SEGREDO in txt(c) and sent(c)[1]["ephemeral"]      # só ela vê o próprio texto
c = clicar(quadro, "Minha intenção", 702, "Beto", CH); assert "ainda não mandou intenção na rodada 1" in txt(c)
c = clicar(quadro, "Minha intenção", 703, "Caio", CH); assert txt(c) == cena._SEM_LUGAR                 # quem não entrou na cena
c = clicar(quadro, "Enviar intenção", 701, "Ana", CH, canal_id="6000"); assert txt(c) == escudo.SEM_CENA and c.response.send_modal.call_count == 0    # o botão em outro canal, sem cena
i = ic(702, "Beto", CH); run(bot.intencao_comando.callback(i, "Proteger a Ana")); assert "enviada pro mestre" in txt(i) and CH.pm.edit.call_count >= 3
i = ic(701, "Ana", CH); run(bot.intencao_comando.callback(i, None)); assert "📝 intenção aguardando o mestre" in txt(i) and SEGREDO in txt(i)
i = ic(701, "Ana", CH); run(bot.intencao_comando.callback(i, "x" * 201)); assert "201 letras" in txt(i) and db.get_intention(db.find_participant_by_character(SID, row(701, "Ana Cena")["id"])["id"], 1)["text"] == SEGREDO
i = ic(703, "Caio", CH); run(bot.intencao_comando.callback(i, "Entrar de penetra")); assert txt(i) == cena._SEM_LUGAR

# --- o mestre lê as intenções (só ele) e decide ---
c = clicar(esc, "Atualizar", 700, "Mestre Belmont", CH, **MESTRE); esc = editada(c)["view"]; e = editada(c)["embed"]
assert c.followup.send.call_count == 0 and SEGREDO in e.description and "Proteger a Ana" in e.description and e.footer.text.startswith("2 aguardando você")           # o escudo mostra o texto; o quadro não
confere_componentes(esc)
selecao = [x for x in esc.children if isinstance(x, discord.ui.Select)]; pend = selecao[0]
assert pend.placeholder == "Intenções aguardando (2)" and [o.label for o in pend.options] == ["Ana Cena (14)", "Beto Cena (9)"] and pend.options[0].description == SEGREDO
assert [b.label for b in esc.children if isinstance(b, discord.ui.Button)] == ["Próximo turno", "Mostrar iniciativa", "NPC", "Atualizar", "Encerrar"]     # sem escolher, sem Permitir/Negar
c = inter(700, "Mestre Belmont", **MESTRE); no_canal(c, CH); pend._values = [pend.options[0].value]; runp(pend.callback(c)); esc = editada(c)["view"]
assert [f.name for f in editada(c)["embed"].fields] == ["📝 Ana Cena"] and SEGREDO in editada(c)["embed"].fields[0].value
assert [b.label for b in esc.children if isinstance(b, discord.ui.Button)][-2:] == ["Permitir", "Negar"] and botao(esc, "Permitir").row == 3; confere_componentes(esc)
CH.pm.edit.reset_mock(); c = clicar(esc, "Permitir", 700, "Mestre Belmont", CH, **MESTRE); esc = editada(c)["view"]
assert followups(c)[0][0] == "✅ Intenção de **Ana Cena** permitida." and followups(c)[0][1]["ephemeral"] and db.get_intention(db.find_participant_by_character(SID, row(701, "Ana Cena")["id"])["id"], 1)["status"] == "permitida"
assert "1. Ana Cena · 14 ✅" in ultimo_quadro(CH)["embed"].description and SEGREDO not in texto_do_quadro(CH)              # o quadro público avisa ✅ e continua sem o texto
assert "Permitir" not in [b.label for b in esc.children if isinstance(b, discord.ui.Button)] and seletor(esc).placeholder == "Intenções aguardando (1)"
# negar, com motivo, num formulário; o jogador vê o motivo
pend = [x for x in esc.children if isinstance(x, discord.ui.Select)][0]; c = inter(700, "Mestre Belmont", **MESTRE); no_canal(c, CH); pend._values = [pend.options[0].value]; runp(pend.callback(c)); esc = editada(c)["view"]
c = clicar(esc, "Negar", 700, "Mestre Belmont", CH, **MESTRE); mg = c.response.send_modal.call_args.args[0]
assert isinstance(mg, escudo.ModalNegar) and mg.title == "Negar a intenção" and not mg.campo.required and mg.campo.max_length == 150
c = submeter(mg, {mg.campo: "  Ela está   longe  demais "}, 700, "Mestre Belmont", CH, **MESTRE); esc = editada(c)["view"]
assert followups(c)[0][0] == "❌ Intenção de **Beto Cena** negada: Ela está longe demais. O jogador vê o motivo em 👁 Minha intenção." and "3. Beto Cena · 9 ❌" in ultimo_quadro(CH)["embed"].description
c = clicar(quadro, "Minha intenção", 702, "Beto", CH); assert "❌ intenção negada" in txt(c) and "Motivo do mestre: Ela está longe demais" in txt(c) and "Manda outra com `/intencao`" in txt(c)
# painel velho: decidir a mesma intenção de novo não estraga nada
mg_velho = criar(escudo.ModalNegar, esc, db.get_intention(db.find_participant_by_character(SID, row(702, "Beto Cena")["id"])["id"], 1)["id"]); mg_velho.campo._value = "de novo"
c = ic(700, "Mestre Belmont", CH, **MESTRE); runp(mg_velho.on_submit(c)); assert "já foi decidida" in followups(c)[0][0] and db.get_intention(db.find_participant_by_character(SID, row(702, "Beto Cena")["id"])["id"], 1)["master_note"] == "Ela está longe demais"
esc.intencao_sel = None
c = clicar(esc, "Atualizar", 700, "Mestre Belmont", CH, **MESTRE); esc = editada(c)["view"]
i = ic(701, "Ana", CH); run(bot.intencao_comando.callback(i, "Mudei de ideia")); assert "já foi permitida" in txt(i)              # permitida: não troca
i = ic(702, "Beto", CH); run(bot.intencao_comando.callback(i, "Ficar parado")); assert "trocada" in txt(i) and "3. Beto Cena · 9 📝" in ultimo_quadro(CH)["embed"].description   # negada: pode mandar outra

# --- a vez: próximo turno marca só o jogador, e a rodada vira ---
CH.pm.edit.reset_mock()
c = clicar(esc, "Próximo turno", 700, "Mestre Belmont", CH, **MESTRE); esc = editada(c)["view"]
(texto, fk), = followups(c); assert texto == "▶️ Vez de <@701> · **Ana Cena** (14) · ✅ intenção permitida" and "ephemeral" not in fk and [u.id for u in fk["allowed_mentions"].users] == [701]
assert fk["allowed_mentions"].everyone is False and fk["allowed_mentions"].roles is False                   # só ela pode ser marcada
assert "▶️ **1. Ana Cena** · 14 ✅" in ultimo_quadro(CH)["embed"].description and "vez de **Ana Cena**" in editada(c)["embed"].description
c = clicar(esc, "Próximo turno", 700, "Mestre Belmont", CH, **MESTRE); esc = editada(c)["view"]
assert followups(c)[0][0] == "▶️ Vez de **Guarda** (NPC, 12)" and "allowed_mentions" not in followups(c)[0][1]              # NPC não marca ninguém
c = clicar(esc, "Próximo turno", 700, "Mestre Belmont", CH, **MESTRE); esc = editada(c)["view"]; assert followups(c)[0][0].startswith("▶️ Vez de <@702> · **Beto Cena** (9) · 📝 intenção aguardando o mestre")
c = clicar(esc, "Próximo turno", 700, "Mestre Belmont", CH, **MESTRE); esc = editada(c)["view"]                    # passou do último: rodada nova
assert followups(c)[0][0] == "🔔 **Rodada 2** começou.\n▶️ Vez de <@701> · **Ana Cena** (14) · ⏳ sem intenção" and db.get_scene(SID)["round"] == 2
assert "**Rodada 2**" in ultimo_quadro(CH)["embed"].description and "1" not in "".join(ch for ch in ultimo_quadro(CH)["embed"].description if ch in "✅📝❌")   # a rodada nova começa sem intenções
assert seletor(esc).placeholder == "Editar ou remover alguém" and len([x for x in esc.children if isinstance(x, discord.ui.Select)]) == 1                   # sem intenção pendente: só o menu de participantes
i = ic(701, "Ana", CH); run(bot.intencao_comando.callback(i, "Correr")); assert "enviada pro mestre" in txt(i)      # cada rodada tem a sua

# --- editar a iniciativa e remover ---
pt = [x for x in esc.children if isinstance(x, discord.ui.Select)][0]; c = inter(700, "Mestre Belmont", **MESTRE); no_canal(c, CH); pt._values = [pt.options[2].value]; runp(pt.callback(c)); esc = editada(c)["view"]
assert [b.label for b in esc.children if isinstance(b, discord.ui.Button)][-2:] == ["Iniciativa", "Remover"] and [o.default for o in menu(esc, "Editar ou remover").options] == [False, False, True]
c = clicar(esc, "Iniciativa", 700, "Mestre Belmont", CH, **MESTRE); mi2 = c.response.send_modal.call_args.args[0]
assert isinstance(mi2, escudo.ModalIniciativa) and mi2.campo.default == "9" and mi2.title == "Iniciativa de Beto Cena"
c = submeter(mi2, {mi2.campo: "20"}, 700, "Mestre Belmont", CH, **MESTRE); esc = editada(c)["view"]
assert "agora é **20**" in followups(c)[0][0] and [(p["name"], p["initiative"]) for p in db.get_participants(SID)] == [("Beto Cena", 20), ("Ana Cena", 14), ("Guarda", 12)] and "1. Beto Cena · 20" in ultimo_quadro(CH)["embed"].description
c = submeter(mi2, {mi2.campo: "zzz"}, 700, "Mestre Belmont", CH, **MESTRE); assert "Iniciativa inválida" in followups(c)[0][0] and db.get_participant(mi2.participante_id)["initiative"] == 20
guarda = next(p for p in db.get_participants(SID) if p["name"] == "Guarda")
esc.participante_sel = guarda["id"]; esc._montar(); c = clicar(esc, "Remover", 700, "Mestre Belmont", CH, **MESTRE); esc = editada(c)["view"]
assert followups(c)[0][0] == "🗑 **Guarda** saiu da cena." and [p["name"] for p in db.get_participants(SID)] == ["Beto Cena", "Ana Cena"] and "Guarda" not in ultimo_quadro(CH)["embed"].description
assert [b.label for b in esc.children if isinstance(b, discord.ui.Button)] == ["Próximo turno", "Mostrar iniciativa", "NPC", "Atualizar", "Encerrar"]      # sem seleção: sem Iniciativa/Remover
esc.participante_sel = guarda["id"]; esc._montar(); assert esc.participante_sel is None                    # seleção velha (já saiu) é esquecida
c = inter(700, "Mestre Belmont", **MESTRE); no_canal(c, CH); esc.participante_sel = 99999; runp(esc._editar(c)); assert "já saiu da cena" in followups(c)[0][0]
c = inter(700, "Mestre Belmont", **MESTRE); no_canal(c, CH); runp(esc._remover(c)); assert "já saiu da cena" in followups(c)[0][0]

# --- próximo turno numa cena vazia ---
vazia = db.create_scene("999", "5100", "Vazia", "700")["id"]; ev = criar(escudo.EscudoDoMestre, 700, "5100")
c = clicar(ev, "Próximo turno", 700, "Mestre Belmont", CH, "5100", **MESTRE); assert "Ninguém entrou na iniciativa ainda" in followups(c)[0][0] and followups(c)[0][1]["ephemeral"] and db.get_scene(vazia)["turn_participant_id"] is None
c = clicar(ev, "Mostrar iniciativa", 700, "Mestre Belmont", canal_fake(), "5100", **MESTRE)

# --- encerrar: pede confirmação, dá pra voltar, e fecha o quadro ---
c = clicar(esc, "Encerrar", 700, "Mestre Belmont", CH, **MESTRE); conf = editada(c)["view"]
assert isinstance(conf, escudo.ConfirmarEncerrar) and editada(c)["embed"].title == "⛔ Encerrar Motim na praça?" and [b.label for b in conf.children] == ["Encerrar a cena", "Voltar"] and esc.is_finished() and c.followup.send.call_count == 0
assert runp(conf.interaction_check(ic(999, "Intruso", CH, **MESTRE))) is False and runp(conf.interaction_check(ic(700, "X", CH))) is False
c = clicar(conf, "Voltar", 700, "Mestre Belmont", CH, **MESTRE); esc = editada(c)["view"]; assert isinstance(esc, escudo.EscudoDoMestre) and db.get_active_scene("5000") is not None
c = clicar(esc, "Encerrar", 700, "Mestre Belmont", CH, **MESTRE); conf = editada(c)["view"]
CH.pm.edit.reset_mock(); c = clicar(conf, "Encerrar a cena", 700, "Mestre Belmont", CH, **MESTRE); esc = editada(c)["view"]
assert db.get_active_scene("5000") is None and db.get_scene(SID)["active"] == 0 and "Cena **Motim na praça** encerrada" in followups(c)[0][0]
assert ultimo_quadro(CH)["view"] is None and "(encerrada)" in ultimo_quadro(CH)["embed"].title and cena.LEGENDA not in ultimo_quadro(CH)["embed"].description       # o quadro vira registro, sem botões
assert [b.label for b in esc.children] == ["Iniciar cena"] and editada(c)["embed"].title == "🛡️ Escudo do Mestre"
for cmd, args in ((bot.iniciativa_comando, ()), (bot.intencao_comando, ("Atacar",))):
    i = ic(701, "Ana", CH); run(cmd.callback(i, *args)); assert txt(i) == escudo.SEM_CENA                      # depois de encerrada, ninguém entra
c = clicar(quadro, "Entrar na iniciativa", 702, "Beto", CH); assert txt(c) == escudo.SEM_CENA                  # nem pelo botão do quadro antigo
c = clicar(conf, "Encerrar a cena", 700, "Mestre Belmont", CH, **MESTRE); assert "já tinha sido encerrada" in followups(c)[0][0]                      # clique repetido
mc4 = criar(escudo.ModalCena, esc); mc4.campo._value = "Segunda cena"; c = ic(700, "Mestre Belmont", CH, **MESTRE); runp(mc4.on_submit(c))
assert db.get_active_scene("5000")["name"] == "Segunda cena" and db.get_active_scene("5000")["id"] != SID and db.get_participants(db.get_active_scene("5000")["id"]) == []      # cena nova começa do zero

# --- a cena cheia, tela velha e erro ---
lot = db.create_scene("999", "5200", "Lotada", "700")["id"]
for k in range(25): db.add_participant(lot, "npc", f"N{k}", k)
el = criar(escudo.EscudoDoMestre, 700, "5200"); confere_componentes(el)
assert [len(x.options) for x in el.children if isinstance(x, discord.ui.Select)] == [25]
errv = ic(700, "Mestre Belmont", CH, **MESTRE); runp(el.on_error(errv, RuntimeError("falhou"), None)); assert errv.response.send_message.call_args.args[0] == paineis.MSG_ERRO
errq = ic(701, "Ana", CH); runp(quadro.on_error(errq, RuntimeError("falhou"), None)); assert errq.response.send_message.call_args.args[0] == paineis.MSG_ERRO
errm = ic(701, "Ana", CH); runp(mi.on_error(errm, RuntimeError("falhou"))); assert errm.response.send_message.call_args.args[0] == paineis.MSG_ERRO
# o registro do quadro persistente na partida
registrados = []; original_add = bot.bot.add_view; bot.bot.add_view = lambda v, **k: registrados.append(v)
try: runp(bot._preparar_bot())
finally: bot.bot.add_view = original_add
assert [type(v) for v in registrados] == [escudo.QuadroDaCena, bot.ComecoAqui] and all(v.is_persistent() for v in registrados)
# a ajuda conhece os três comandos
for chave in ("iniciativa", "intencao", "mestre escudo"): assert chave in ajuda.AJUDA and len(ajuda.AJUDA[chave]["detalhes"]) <= 600
print("V. Escudo do Mestre OK")

# ============================ W. Resultado especial: 66 e 77 nos sorteios de criação ============================
VERMELHO, AMARELO = 0xC0392B, 0xF1C40F
papel_mestre = NS(id=555, name="Mestre", mention="<@&555>")
def sem_numero(i, n):
    """O número não aparece na resposta. Os horários (<t:1790782581:d>) são ignorados: os dígitos deles mudam a cada segundo."""
    return str(n) not in re.sub(r"<t:\d+:\w>", "", txt(i))
def cartao_de(i): return sent(i)[1]["embed"]
def so_interrogacao(e):
    tudo = " ".join([e.title or "", e.author.name or "", e.description or "", e.footer.text or ""] + [f.name + f.value for f in e.fields])
    return "?" in tudo and not any(ch.isalnum() for ch in tudo)              # nenhuma letra nem número: só interrogação e enfeite
def com_cargo(i): i.guild = NS(roles=[papel_mestre]); return i

# --- raça 66: cartão vermelho, nada definido, uma chance gasta, o cargo Mestre é avisado ---
z = com_cargo(novo(1100, "Zé", "Sombra"))
with dados(66): run(bot.raca_inicial.callback(z, None))
e, kw = cartao_de(z), sent(z)[1]
assert e.color.value == VERMELHO and so_interrogacao(e) and kw["content"] == "<@&555>" and kw["allowed_mentions"].roles == [papel_mestre]
assert not kw.get("ephemeral") and "files" not in kw and "view" not in kw                    # público, sem imagem (ainda não tem o desenho)
c = row(1100, "Sombra"); assert (c["race"], c["race_roll"], c["race_set_at"], c["race_special"], c["race_attempts"]) == (None, None, None, 66, 1)
assert [(h["purpose"], h["total"]) for h in historico_de(1100)] == [("raca_inicial", 66)]      # a rolagem fica no histórico
# o histórico é público: o número do sorteio especial não aparece ali, mas uma rolagem comum de 66 aparece normal
run(bot.historico.callback(z, None, 10, None)); assert [f.name for f in sent(z)[1]["embed"].fields] == ["1d100 = ??? (raca_inicial)"] and sem_numero(z, 66)
db.log_roll(user_id="1100", username="Zé", guild_id=None, notation="1d100", rolls=[66], total=66, purpose="ataque", character_id=c["id"], character_name="Sombra")
run(bot.historico.callback(z, None, 10, None)); assert [f.name for f in sent(z)[1]["embed"].fields] == ["1d100 = 66 (ataque)", "1d100 = ??? (raca_inicial)"]
# não rola de novo (nem pelo comando), e a resposta não diz o que saiu
with dados(): run(bot.raca_inicial.callback(z, None))
assert "Algo diferente aconteceu" in txt(z) and sem_numero(z, 66) and sent(z)[1]["ephemeral"] and row(1100, "Sombra")["race_attempts"] == 1
# a ficha do jogador só mostra interrogação; a do mestre mostra o número
run(bot.minha_ficha.callback(z, None)); assert campos(z)["Raça"] == "❓ ???\n(aguardando o mestre)" and sem_numero(z, 66)
run(bot.mestre_ficha.callback(gm, alvo(1100, "Zé"), None)); assert campos(gm)["Raça"] == "❓ ???\n(aguardando o mestre, tirou 66)"
run(bot.personagem_listar.callback(z)); assert "raça: ❓ ???" in txt(z)
# o botão da raça fica travado com ❓, e os outros passos seguem o que já valia
pf = criar(paineis.PainelFicha, 1100, c["id"], "Zé"); est = estado(pf)
assert est["Raça"] == ("❓", True) and est["Classe social"] == ("⚜️", False) and est["Classe"] == ("🔒", True) and est["Magia"] == ("🔒", True); confere_componentes(pf)
# a ajuda entende: o próximo passo é com o mestre e não manda rolar de novo
run(bot.ajuda_comando.callback(z, None)); assert "algo diferente aconteceu no seu sorteio" in txt(z) and sem_numero(z, 66)
# o mestre decide: escolhe a raça na mão, o especial some e a raça vale como qualquer outra
run(bot.mestre_corrigir_raca.callback(gm, alvo(1100, "Zé"), "Humano", None)); assert "**❓ ??? (tirou 66)** → **Humano**" in txt(gm)
c = row(1100, "Sombra"); assert (c["race"], c["race_roll"], c["race_special"]) == ("Humano", None, None) and rules.reroll_block(c, "race") == "tentativas"
# ...ou apaga o sorteio e devolve as chances
y = com_cargo(novo(1101, "Ya", "Ya Sombra"))
with dados(77): run(bot.raca_inicial.callback(y, None))
assert cartao_de(y).color.value == AMARELO and row(1101, "Ya Sombra")["race_special"] == 77
run(bot.mestre_apagar.callback(gm, alvo(1101, "Ya"), "race", None)); c = row(1101, "Ya Sombra")
assert (c["race"], c["race_special"], c["race_attempts"]) == (None, None, 0)
with dados(50): run(bot.raca_inicial.callback(y, None))
assert titulo(y) == "Humanos" and row(1101, "Ya Sombra")["race"] == "Humano"                   # depois, rola normal

# --- classe social 77 (amarelo), inclusive um 66 ou 77 no sorteio do clero ---
q = com_cargo(novo(1102, "Quim", "Quimera"))
with dados(77): run(bot.classe_social.callback(q, None))
e, kw = cartao_de(q), sent(q)[1]
assert e.color.value == AMARELO and so_interrogacao(e) and kw["content"] == "<@&555>" and not kw.get("ephemeral")
c = row(1102, "Quimera"); assert (c["social_class"], c["social_class_roll"], c["clergy"], c["social_class_special"], c["social_class_attempts"]) == (None, None, None, 77, 1)
with dados(): run(bot.classe_social.callback(q, None))
assert "Algo diferente aconteceu" in txt(q) and sem_numero(q, 77)
run(bot.mestre_ficha.callback(gm, alvo(1102, "Quim"), None)); assert campos(gm)["Classe Social"] == "❓ ???\n(aguardando o mestre, tirou 77)"
cl = com_cargo(novo(1103, "Clero", "Padre Misterioso"))
with dados(95, 66): run(bot.classe_social.callback(cl, None))                                # 1º Estado, e o dado do clero deu 66
assert cartao_de(cl).color.value == VERMELHO and so_interrogacao(cartao_de(cl))
c = row(1103, "Padre Misterioso"); assert (c["social_class"], c["clergy"], c["social_class_special"]) == (None, None, 66)
assert [(h["purpose"], h["total"]) for h in reversed(historico_de(1103))] == [("classe_social", 95), ("clero", 66)]      # o banco guarda os dois
run(bot.historico.callback(cl, None, 10, None)); assert [f.name for f in sent(cl)[1]["embed"].fields] == ["1d100 = ??? (clero)", "1d100 = 95 (classe_social)"]
run(bot.mestre_apagar.callback(gm, alvo(1103, "Clero"), "social_class", None)); c = row(1103, "Padre Misterioso")
assert (c["social_class_special"], c["social_class_attempts"]) == (None, 0)

# --- magia 77: o Rank fica vazio, a ficha espera o mestre e os atributos ficam fechados ---
def vampiro_sem_magia(uid, nome, personagem):
    u = com_cargo(novo(uid, nome, personagem)); c = row(uid, personagem)["id"]
    db.set_race(c, "Vampiro", 90); db.set_social_status(c, "3º Estado", 10); db.set_class(c, "Caçador"); return u
mg = vampiro_sem_magia(1104, "Mago", "Mago Sombrio")
with dados(77): run(bot.magia_inicial.callback(mg, None))
e, kw = cartao_de(mg), sent(mg)[1]
assert e.color.value == AMARELO and so_interrogacao(e) and kw["content"] == "<@&555>" and "🎲" not in txt(mg)
c = row(1104, "Mago Sombrio"); assert (c["magic_rank"], c["magic_rank_roll"], c["magic_rank_special"]) == (None, None, 77)
with dados(): run(bot.magia_inicial.callback(mg, None))
assert "Algo diferente aconteceu" in txt(mg) and sem_numero(mg, 77)                          # nem a magia (uma rolagem só) roda de novo
run(bot.historico.callback(mg, None, 10, None)); assert [f.name for f in sent(mg)[1]["embed"].fields] == ["1d100 = ??? (magia_inicial)"]
run(bot.minha_ficha.callback(mg, None)); assert campos(mg)["Rank de Magia"] == "❓ ???\n(aguardando o mestre)"
run(bot.atributos.callback(mg, forca=1)); assert "algo diferente aconteceu num dos seus sorteios" in txt(mg)
assert estado(criar(paineis.PainelFicha, 1104, c["id"], "Mago"))["Magia"] == ("❓", True)
run(bot.mestre_corrigir_magia.callback(gm, alvo(1104, "Mago"), "Raro", None)); assert "**❓ ??? (tirou 77)** → **Raro**" in txt(gm)
c = row(1104, "Mago Sombrio"); assert (c["magic_rank"], c["magic_rank_special"]) == ("Raro", None)

# --- um 66 ao ROLAR DE NOVO também vale: troca o resultado que já existia ---
rr = com_cargo(novo(1105, "Rui", "Rui Rolos"))
with dados(50): run(bot.raca_inicial.callback(rr, None))
run(bot.raca_inicial.callback(rr, None)); conf = confirmar_de(rr)
with dados(66): c = com_cargo(inter(1105, "Rui")); runp(conf.children[0].callback(c))
(conteudo, fk), = followups(c); assert fk["embed"].color.value == VERMELHO and so_interrogacao(fk["embed"]) and conteudo == "<@&555>" and fk["allowed_mentions"].roles == [papel_mestre]
c2 = row(1105, "Rui Rolos"); assert (c2["race"], c2["race_special"], c2["race_attempts"]) == (None, 66, 2)      # o Humano de antes saiu, a última rolagem vale

# --- os vizinhos (65, 67, 76, 78) são sorteios normais, e o 100 continua como era ---
for k, (n, raca) in enumerate(((65, "Humano"), (67, "Humano"), (76, "Humano"), (78, "Humano"))):
    v = com_cargo(novo(1110 + k, f"Viz{n}", f"Vizinho {n}"))
    with dados(n): run(bot.raca_inicial.callback(v, None))
    assert titulo(v) == "Humanos" and not so_interrogacao(cartao_de(v)) and row(1110 + k, f"Vizinho {n}")["race_special"] is None
    with dados(n): run(bot.classe_social.callback(v, None))
    assert nome_do_cartao(cartao_de(v)) == "3° Estado —  Camponeses"
    assert row(1110 + k, f"Vizinho {n}")["social_class_special"] is None
vm = vampiro_sem_magia(1115, "Vm", "Vizinho Magia")
with dados(78): run(bot.magia_inicial.callback(vm, None))
assert row(1115, "Vizinho Magia")["magic_rank"] == "Super Raro" and row(1115, "Vizinho Magia")["magic_rank_special"] is None and not so_interrogacao(cartao_de(vm))
cem = com_cargo(novo(1116, "Cem", "Cem Por Cento"))
with dados(100): run(bot.classe_social.callback(cem, None))
assert row(1116, "Cem Por Cento")["social_class"] == dice.SOCIAL_CLASS_MASTER and row(1116, "Cem Por Cento")["social_class_special"] is None and cartao_de(cem).title == "🎲 Resultado especial"
# (o texto do 100 continua o mesmo de antes: ele é o "mestre decide" conhecido, o 66 e o 77 é que são o mistério)
print("W. Resultado especial 66/77 OK")

# ============================ X. classes novas, /habilidade, 3#d20 e /mestre sorte ============================
@contextlib.contextmanager
def d20s(*valores):
    """Fixa o número de cada d20 (os lados e o modificador continuam os de verdade) e confere que não sobrou nem faltou dado."""
    seq = list(valores); real = dice.roll
    def fake(notacao):
        assert seq, "rolou mais dado do que o esperado"
        r = real(notacao); r.rolls = [seq.pop(0)] + r.rolls[1:]; return r
    dice.roll = fake
    try: yield
    finally:
        dice.roll = real
        assert not seq, f"sobrou dado: {seq}"
def campos_do_cartao(i): return [f.name for f in sent(i)[1]["embed"].fields]
def valor_do_campo(i, nome): return next(f.value for f in sent(i)[1]["embed"].fields if f.name == nome)

# --- /habilidade ---
sem_pers = inter(1299, "Sem"); run(bot.habilidade.callback(sem_pers, None, None)); assert "Você ainda não tem personagem" in txt(sem_pers) and sent(sem_pers)[1]["ephemeral"]
p = novo(1200, "Pat", "Padre Pat"); preparar(1200, "Padre Pat", "Humano", None)
run(bot.habilidade.callback(p, None, None)); assert "ainda não tem classe" in txt(p) and sent(p)[1]["ephemeral"]
runp(bot.classe_escolher.callback(p, "Clérigo", None))                                                            # o cartão da classe já oferece os botões
assert campos_do_cartao(p) == ["Vantagem nas perícias", "Bônus", "Combina com (exemplos)", "Habilidade de classe", "✨ Mãos que Curam", "✨ Bênção", "Continue a criação"]
assert valor_do_campo(p, "Continue a criação").startswith("Escolhe a sua habilidade de classe nos botões abaixo. Sua raça e sua classe não têm magia")
vb = enviada(p); assert isinstance(vb, paineis.EscolhaDeHabilidade) and estado(vb) == {"Mãos que Curam": ("✨", False), "Bênção": ("✨", False), "Confirmar habilidade": ("✅", True)} and valor_do_campo(p, "Vantagem nas perícias") == "Religião e Medicina"
assert valor_do_campo(p, "Combina com (exemplos)") == "Padre · Freira · Pastor · Hospedeiro" and row(1200, "Padre Pat")["class_ability"] is None
run(bot.minha_ficha.callback(p, None)); assert campos(p)["Classe"] == "Clérigo\n(vantagem em Religião e Medicina)\n✨ falta escolher (botão **Habilidade** ou `/habilidade`)"
runp(bot.habilidade.callback(p, None, None)); e = sent(p)[1]["embed"]
assert isinstance(enviada(p), paineis.EscolhaDeHabilidade) and sent(p)[1]["ephemeral"] and e.author.name == "✨ Habilidade de Padre Pat" and campos_do_cartao(p) == ["Habilidade de classe", "✨ Mãos que Curam", "✨ Bênção"]
assert valor_do_campo(p, "Habilidade de classe") == "Escolha uma das duas: **Mãos que Curam** ou **Bênção**. Aperta um dos botões abaixo."
run(bot.habilidade.callback(p, "não existe", None)); assert txt(p) == "**não existe** não é uma habilidade de **Clérigo**. As opções são: **Mãos que Curam** ou **Bênção**." and row(1200, "Padre Pat")["class_ability"] is None
run(bot.habilidade.callback(p, "mão leve", None)); assert "não é uma habilidade de **Clérigo**" in txt(p) and row(1200, "Padre Pat")["class_ability"] is None     # a do Ladrão não vale
run(bot.habilidade.callback(p, "  bÊnção ", None)); assert row(1200, "Padre Pat")["class_ability"] == "Bênção"                                    # sem ligar pra maiúscula nem pra espaço
assert campos_do_cartao(p) == ["Habilidade de classe", "✨ Mãos que Curam", "✨ Bênção ✅"] and valor_do_campo(p, "Habilidade de classe") == "Você levou **Bênção**." and "view" not in sent(p)[1]
run(bot.habilidade.callback(p, "Mãos que Curam", None)); assert txt(p) == "**Padre Pat** já levou **Bênção**. Fala com um mestre se precisar mudar." and row(1200, "Padre Pat")["class_ability"] == "Bênção"
run(bot.minha_ficha.callback(p, None)); assert campos(p)["Classe"] == "Clérigo\n(vantagem em Religião e Medicina)\n✨ Bênção"
run(bot.habilidade.callback(p, None, "Fantasma")); assert "Não achei nenhum personagem seu chamado **Fantasma**" in txt(p)
run(bot.mestre_corrigir_classe.callback(gm, alvo(1200, "Pat"), "Clérigo", None)); assert row(1200, "Padre Pat")["class_ability"] is None      # o mestre refez a classe: a escolha volta a ficar aberta
run(bot.minha_ficha.callback(p, None)); assert campos(p)["Classe"].endswith("✨ falta escolher (botão **Habilidade** ou `/habilidade`)")
# classes de uma habilidade só
c1 = novo(1201, "Cac", "Cacador Cac"); preparar(1201, "Cacador Cac", "Humano", None); run(bot.classe_escolher.callback(c1, "Caçador", None))
assert campos_do_cartao(c1) == ["Vantagem nas perícias", "Bônus", "Combina com (exemplos)", "✨ Sem Dúvidas", "Continue a criação"] and "Escolha a sua habilidade" not in valor_do_campo(c1, "Continue a criação")
run(bot.habilidade.callback(c1, "Sem Dúvidas", None)); assert txt(c1) == "A classe **Caçador** só tem uma habilidade (**Sem Dúvidas**), então não tem o que escolher." and row(1201, "Cacador Cac")["class_ability"] is None
run(bot.habilidade.callback(c1, None, None)); assert campos_do_cartao(c1) == ["✨ Sem Dúvidas"]
run(bot.minha_ficha.callback(c1, None)); assert campos(c1)["Classe"] == "Caçador\n(vantagem em Religião e Luta ou Pontaria)\n✨ Sem Dúvidas"
# o Ladrão também escolhe, e a classe nova Mercenário tem a dela
l1 = novo(1202, "Lad", "Ladrao Lad"); preparar(1202, "Ladrao Lad", "Humano", None); run(bot.classe_escolher.callback(l1, "Ladrão", None)); run(bot.habilidade.callback(l1, "Língua de Prata", None))
assert row(1202, "Ladrao Lad")["class_ability"] == "Língua de Prata" and campos_do_cartao(l1) == ["Habilidade de classe", "✨ Mão Leve", "✨ Língua de Prata ✅"]
m1 = novo(1203, "Mer", "Mercenario Mer"); preparar(1203, "Mercenario Mer", "Humano", None); run(bot.classe_escolher.callback(m1, "Mercenário", None))
assert campos_do_cartao(m1)[3] == "✨ Ombro a Ombro" and valor_do_campo(m1, "Vantagem nas perícias") == "Tática e Luta ou Pontaria" and valor_do_campo(m1, "Bônus") == "Vida +30 · Sanidade +20 · Mana +5 · Estamina +20"
# o menu de sugestões: só o que o personagem pode escolher
def sugestoes_hab(uid, busca=""): return [c.value for c in run(bot._autocomplete_habilidade(inter(uid, "J"), busca))]
assert sugestoes_hab(1200) == ["Mãos que Curam", "Bênção"] and sugestoes_hab(1200, "bên") == ["Bênção"] and sugestoes_hab(1202) == ["Mão Leve", "Língua de Prata"]
assert sugestoes_hab(1201) == ["Mãos que Curam", "Bênção", "Mão Leve", "Língua de Prata"] and sugestoes_hab(1299) == sugestoes_hab(1201)       # quem não tem escolha a fazer vê todas
# o Sábio ganha o dobro de pontos de perícia
sab = pronto(1210, "Sab", "Sabio Sab", classe="Sábio"); run(bot.niveis.callback(sab, None)); d = desc(sab)
assert "**Nível 2** · " in d and " +4 perícia" in d and " +2 perícia" not in d and "+36 pontos de Perícia" in d
cac = pronto(1211, "Cac2", "Cacador Dois"); run(bot.niveis.callback(cac, None)); d = desc(cac); assert " +2 perícia" in d and " +4 perícia" not in d and "+18 pontos de Perícia" in d
print("X1. /habilidade e classes novas OK")

# --- 3#d20: rolagens separadas, no comando e no chat ---
r1 = pronto(1220, "Rol", "Rolador Rol")
with d20s(14, 1, 20): i = inter(1220, "Rol"); run(bot.rolar.callback(i, "3#d20+5", "ataque", None))
e = sent(i)[1]["embed"]; assert not sent(i)[1].get("ephemeral") and e.title == "🎲 Rolador Rol rolou 3#d20+5" and e.footer.text == "ataque · jogador: Rol"
assert e.description == "**1.** 14 + 5 = **19**\n**2.** 1 + 5 = **6** 💀\n**3.** 20 + 5 = **25** 🌟\n\n⬆️ Maior **25** · ⬇️ Menor **6**"
assert [(h["purpose"], h["notation"], h["total"], h["character_name"]) for h in reversed(historico_de(1220))] == [("ataque", "d20+5", 19, "Rolador Rol"), ("ataque", "d20+5", 6, "Rolador Rol"), ("ataque", "d20+5", 25, "Rolador Rol")]
with d20s(): i = inter(1220, "Rol"); run(bot.rolar.callback(i, "11#d20", None, None))
assert txt(i) == "⚠️ A repetição precisa ser de 1 a 10 (por exemplo 3#d20+5)." and sent(i)[1]["ephemeral"] and len(historico_de(1220)) == 3     # recusou sem rolar nem gravar
with d20s(): i = inter(1220, "Rol"); run(bot.rolar.callback(i, "3#abc", None, None)); assert txt(i).startswith("⚠️ Notação de dado inválida: 'abc'")
with d20s(9): i = inter(1220, "Rol"); run(bot.rolar.callback(i, "1#d20", None, None))                          # 1# é um dado só, no cartão de sempre
assert sent(i)[1]["embed"].title == "🎲 Rolador Rol rolou 1#d20" and sent(i)[1]["embed"].description == "**9 = 9**" and "⬆️" not in desc(i) and len(historico_de(1220)) == 4
r2 = pronto(1221, "Rol2", "Rolador Dois")
with d20s(14, 1, 20): m = msg(1221, "Rol2", "+3#d20+5 ataque"); run(bot.on_message(m))
_, kw = resposta(m); assert kw["embed"].description == "**1.** 14 + 5 = **19**\n**2.** 1 + 5 = **6** 💀\n**3.** 20 + 5 = **25** 🌟\n\n⬆️ Maior **25** · ⬇️ Menor **6**"
assert [(h["purpose"], h["total"]) for h in reversed(historico_de(1221))] == [("ataque", 19), ("ataque", 6), ("ataque", 25)]
with d20s(): m = msg(1221, "Rol2", "3#d20 ola gente"); run(bot.on_message(m)); assert m.reply.call_count == 0          # conversa normal nunca rola
with d20s(): m = msg(1221, "Rol2", "+11#d20"); run(bot.on_message(m))
assert resposta(m)[0] == "⚠️ A repetição precisa ser de 1 a 10 (por exemplo 3#d20+5)." and len(historico_de(1221)) == 3
print("X2. 3#d20 OK")
# --- /mestre sorte ---
s1 = pronto(1230, "Sor", "Sortudo Sor"); A = alvo(1230, "Sor"); CID = row(1230, "Sortudo Sor")["id"]
efs = lambda: [(r["kind"], r["value"], r["uses_left"], r["quiet"], r["note"]) for r in db.get_dice_effects(CID)]
def acoes_de_sorte():
    with sqlite3.connect(db.DB_PATH) as cn: return [tuple(r) for r in cn.execute("SELECT action, detail FROM master_actions WHERE action IN ('sorte', 'sorte_limpar') ORDER BY id")]
assert bot._eh_mestre in bot.mestre_sorte.checks and bot._eh_mestre(inter(1230, "Sor")) is False              # só mestre usa
run(bot.mestre_sorte.callback(gm, A, "vantagem", None, 2, False, None, "abençoado")); t = txt(gm)
assert t.startswith("🍀 **Sortudo Sor** agora tem **vantagem** nas próximas 2 rolagens de d20.\nO cartão da rolagem mostra a marca 🍀. ") and "Não mexe nos sorteios da criação nem na iniciativa" in t and sent(gm)[1]["ephemeral"]
assert efs() == [("vantagem", None, 2, 0, "abençoado")] and db.get_dice_effects(CID)[0]["created_by"] == "4" and acoes_de_sorte() == [("sorte", "vantagem x2: abençoado")]
ri = inter(1230, "Sor")
with d20s(4, 15): run(bot.rolar.callback(ri, "1d20+5", None, None))                                               # fica o maior
assert sent(ri)[1]["embed"].description == "**15 + 5 = 20**\n🍀 vantagem (4 e 15)" and efs() == [("vantagem", None, 1, 0, "abençoado")]
assert [(h["total"], h["rolls_json"]) for h in historico_de(1230)][0] == (20, "[15]")                             # o histórico guarda o dado que valeu
run(bot.mestre_sorte.callback(gm, A, "bonus", 3, 1, True, None, None)); assert "agora tem **bônus +3** nas próximas 1 rolagem de d20" in txt(gm) and "Nada aparece no cartão da rolagem (discreto)." in txt(gm)
run(bot.mestre_sorte.callback(gm, A, "ver", None, 1, False, None, None)); assert txt(gm) == "🍀 **Sorte de Sortudo Sor**\n• vantagem · 1 uso · nota: abençoado\n• bônus +3 · 1 uso · discreto"
with d20s(12, 3): ri = inter(1230, "Sor"); run(bot.rolar.callback(ri, "1d20+5", None, None))                     # a vantagem aparece, o bônus discreto não (mas soma)
assert sent(ri)[1]["embed"].description == "**12 + 8 = 20**\n🍀 vantagem (12 e 3)" and efs() == []                 # os dois acabaram
with d20s(7): ri = inter(1230, "Sor"); run(bot.rolar.callback(ri, "1d20+5", None, None)); assert sent(ri)[1]["embed"].description == "**7 + 5 = 12**"
run(bot.mestre_sorte.callback(gm, A, "ver", None, 1, False, None, None)); assert txt(gm) == "🍀 **Sorte de Sortudo Sor**\nNenhum efeito ativo."
# discreto: aplica e não marca
run(bot.mestre_sorte.callback(gm, A, "fixo", 20, 1, True, None, None))
with d20s(3): ri = inter(1230, "Sor"); run(bot.rolar.callback(ri, "1d20", None, None))
assert sent(ri)[1]["embed"].description == "**20 = 20**\n🌟 **20 natural!**" and "🍀" not in desc(ri) and efs() == []
assert acoes_de_sorte()[-1] == ("sorte", "dado fixo 20 x1 (discreto)")
# os erros e o que o comando NÃO afeta
run(bot.mestre_sorte.callback(gm, A, "bonus", None, 1, False, None, None)); assert txt(gm) == "O efeito **bônus** precisa do campo `valor` (de 1 a 20)." and efs() == []
run(bot.mestre_sorte.callback(gm, alvo(9998, "Fantasma"), "vantagem", None, 1, False, None, None)); assert txt(gm) == "Fantasma ainda não tem personagem criado." and sent(gm)[1]["ephemeral"]
run(bot.mestre_sorte.callback(gm, A, "vantagem", None, 1, False, "Inexistente", None)); assert txt(gm) == "Sor não tem nenhum personagem chamado **Inexistente**." and efs() == []
run(bot.mestre_sorte.callback(gm, A, "penalidade", 2, 1, False, None, None))
with d20s(3): ri = inter(1230, "Sor"); run(bot.rolar.callback(ri, "1d6", None, None))                            # outro dado: passa direto e não gasta
assert sent(ri)[1]["embed"].description == "**3 = 3**" and efs() == [("penalidade", 2, 1, 0, None)]
db.create_character("1230", "Segundo Sor")                                                                       # o efeito é do personagem, não do jogador
with d20s(8): ri = inter(1230, "Sor"); run(bot.rolar.callback(ri, "1d20", None, "Segundo Sor"))
assert sent(ri)[1]["embed"].description == "**8 = 8**" and efs() == [("penalidade", 2, 1, 0, None)]
db.set_active_character("1230", CID)
with d20s(10): m = msg(1230, "Sor", "d20"); run(bot.on_message(m))                                               # o dado escrito no chat também usa a sorte
assert resposta(m)[1]["embed"].description == "**10 - 2 = 8**\n🍀 -2" and efs() == []
n1 = novo(1231, "Nov", "Novato Nov"); NID = row(1231, "Novato Nov")["id"]; db.add_dice_effect(NID, "fixo", 20, 1, False, None, "4")
with dados(50): run(bot.raca_inicial.callback(n1, None))                                                         # sorteio de criação nunca é mexido
assert row(1231, "Novato Nov")["race"] == "Humano" and [(r["kind"], r["uses_left"]) for r in db.get_dice_effects(NID)] == [("fixo", 1)]
# vários d20 com a vantagem de 2 usos
run(bot.mestre_sorte.callback(gm, A, "vantagem", None, 2, False, None, None))
with d20s(5, 17, 9, 2, 14): ri = inter(1230, "Sor"); run(bot.rolar.callback(ri, "3#d20", None, None))
assert sent(ri)[1]["embed"].description == "**1.** 17 = **17** · 🍀 vantagem (5 e 17)\n**2.** 9 = **9** · 🍀 vantagem (9 e 2)\n**3.** 14 = **14**\n\n⬆️ Maior **17** · ⬇️ Menor **9**" and efs() == []
assert [h["total"] for h in reversed(historico_de(1230))][-3:] == [17, 9, 14]
# limpar
run(bot.mestre_sorte.callback(gm, A, "minimo", 10, 5, False, None, "teste")); run(bot.mestre_sorte.callback(gm, A, "maximo", 15, 1, False, None, None))
run(bot.mestre_sorte.callback(gm, A, "limpar", None, 1, False, None, None)); assert txt(gm) == "🍀 Tirei 2 efeitos de sorte de **Sortudo Sor**." and efs() == [] and acoes_de_sorte()[-1] == ("sorte_limpar", "2 efeito(s) tirado(s)")
run(bot.mestre_sorte.callback(gm, A, "limpar", None, 1, False, None, None)); assert txt(gm) == "🍀 Tirei 0 efeitos de sorte de **Sortudo Sor**."
print("X3. /mestre sorte OK")

# ============================ X4. classe e habilidade escolhidas juntas, tudo por botão ============================
def campos_da_ficha(embed): return {f.name: f.value for f in embed.fields}
def cartao_do_followup(c, posicao=0):
    conteudo, kw = followups(c)[posicao]; return kw["embed"], kw
def marcar(view, nome, uid, jogador):
    c = inter(uid, jogador); runp(botao(view, nome).callback(c)); return c
def escolher_no_menu(view, valor, uid, jogador):
    sel = seletor(view); sel._values = [valor]; c = inter(uid, jogador); runp(sel.callback(c)); return c

# --- o painel da ficha: a classe e a habilidade entram juntas ---
a = novo(1300, "Ana", "Ana Dupla"); preparar(1300, "Ana Dupla", "Humano", None)
pf = painel_de(1300, "Ana Dupla", "Ana"); assert estado(pf)["Classe"] == ("🎓", False)
c = clique(pf, "Classe", 1300, "Ana"); esc = editada(c)["view"]; e = editada(c)["embed"]
assert isinstance(esc, paineis.EscolhaDeClasse) and pf.is_finished() and len(seletor(esc).options) == 8 and estado(esc) == {"Confirmar classe": ("✅", True), "Voltar": ("⬅️", False)}
assert "O Clérigo e o Ladrão têm duas habilidades" in e.description and e.fields[1].value.endswith("\n✨ Mãos que Curam ou Bênção") and e.fields[0].value.endswith("\n✨ Sem Dúvidas"); confere_componentes(esc)
c = escolher_no_menu(esc, "Clérigo", 1300, "Ana"); e = editada(c)["embed"]                                            # escolheu a classe: aparecem os botões, o confirmar segue trancado
assert estado(esc) == {"Mãos que Curam": ("✨", False), "Bênção": ("✨", False), "Confirmar classe e habilidade": ("✅", True), "Voltar": ("⬅️", False)}
assert e.description.endswith("Escolhe a habilidade nos botões e depois confirma. Vale uma vez só, a classe e a habilidade juntas.") and e.fields[3].value == "Escolha uma das duas: **Mãos que Curam** ou **Bênção**. Aperta um dos botões abaixo."; confere_componentes(esc)
c = inter(1300, "Ana"); runp(esc._confirmar(c)); assert c.response.send_message.call_args.args[0] == "Escolhe a habilidade nos botões antes de confirmar." and row(1300, "Ana Dupla")["class_name"] is None     # sem habilidade, nada é gravado
c = marcar(esc, "Bênção", 1300, "Ana"); e = editada(c)["embed"]
assert botao(esc, "Bênção").style == discord.ButtonStyle.success and botao(esc, "Mãos que Curam").style == discord.ButtonStyle.primary and estado(esc)["Confirmar classe e habilidade"] == ("✅", False)
assert e.fields[3].value == "Você vai levar **Bênção**. Confirma nos botões abaixo." and e.description.endswith("aperta **Confirmar classe e habilidade**. Vale uma vez só.") and row(1300, "Ana Dupla")["class_name"] is None   # marcar não grava
escolher_no_menu(esc, "Caçador", 1300, "Ana")                                                                      # mudou de classe: os botões e a marcação somem
assert estado(esc) == {"Confirmar classe": ("✅", False), "Voltar": ("⬅️", False)} and esc.habilidade is None
escolher_no_menu(esc, "Ladrão", 1300, "Ana"); assert esc.habilidade is None and estado(esc) == {"Mão Leve": ("✨", False), "Língua de Prata": ("✨", False), "Confirmar classe e habilidade": ("✅", True), "Voltar": ("⬅️", False)}
escolher_no_menu(esc, "Clérigo", 1300, "Ana"); c = marcar(esc, "Mãos que Curam", 1300, "Ana")
assert runp(esc.interaction_check(inter(999, "Intruso"))) is False and runp(esc.interaction_check(inter(1300, "Ana"))) is True
c = clique(esc, "Confirmar classe e habilidade", 1300, "Ana"); nova = editada(c)["view"]
r = row(1300, "Ana Dupla"); assert (r["class_name"], r["class_ability"]) == ("Clérigo", "Mãos que Curam") and esc.is_finished()
assert isinstance(nova, paineis.PainelFicha) and estado(nova)["Classe"] == ("✅", True) and "Habilidade de classe" not in estado(nova)
e, kw = cartao_do_followup(c); assert kw["ephemeral"] and e.fields[3].value == "Você levou **Mãos que Curam**." and [f.name for f in e.fields][4:6] == ["✨ Mãos que Curam ✅", "✨ Bênção"] and "Escolhe a sua habilidade" not in e.fields[-1].value
assert campos_da_ficha(editada(c)["embed"])["Classe"] == "Clérigo\n(vantagem em Religião e Medicina)\n✨ Mãos que Curam"
# uma classe de uma habilidade só não tem botão de habilidade
b = novo(1301, "Beto", "Beto Um"); preparar(1301, "Beto Um", "Humano", None); esc = editada(clique(painel_de(1301, "Beto Um", "Beto"), "Classe", 1301, "Beto"))["view"]
escolher_no_menu(esc, "Mercenário", 1301, "Beto"); assert estado(esc) == {"Confirmar classe": ("✅", False), "Voltar": ("⬅️", False)}
c = clique(esc, "Confirmar classe", 1301, "Beto"); r = row(1301, "Beto Um"); assert (r["class_name"], r["class_ability"]) == ("Mercenário", None) and rules.class_ability_of(r) == "Ombro a Ombro"
# Voltar não grava nada
v = novo(1302, "Vol", "Volta Vol"); preparar(1302, "Volta Vol", "Humano", None); esc = editada(clique(painel_de(1302, "Volta Vol", "Vol"), "Classe", 1302, "Vol"))["view"]
escolher_no_menu(esc, "Ladrão", 1302, "Vol"); marcar(esc, "Mão Leve", 1302, "Vol"); c = clique(esc, "Voltar", 1302, "Vol")
assert isinstance(editada(c)["view"], paineis.PainelFicha) and row(1302, "Volta Vol")["class_name"] is None

# --- /classe com habilidade: os dois juntos no comando ---
s1 = novo(1310, "Sim", "Sim Dupla"); preparar(1310, "Sim Dupla", "Humano", None)
runp(bot.classe_escolher.callback(s1, "Ladrão", "língua de prata", None))
r = row(1310, "Sim Dupla"); assert (r["class_name"], r["class_ability"]) == ("Ladrão", "Língua de Prata") and "view" not in sent(s1)[1] and sent(s1)[1]["ephemeral"]
assert valor_do_campo(s1, "Habilidade de classe") == "Você levou **Língua de Prata**." and "Escolhe a sua habilidade" not in valor_do_campo(s1, "Continue a criação")
s2 = novo(1311, "Err", "Erro Um"); preparar(1311, "Erro Um", "Humano", None)
runp(bot.classe_escolher.callback(s2, "Clérigo", "Mão Leve", None)); assert txt(s2) == "**Mão Leve** não é uma habilidade de **Clérigo**. As opções são: **Mãos que Curam** ou **Bênção**." and row(1311, "Erro Um")["class_name"] is None
runp(bot.classe_escolher.callback(s2, "Caçador", "Sem Dúvidas", None)); assert txt(s2) == "A classe **Caçador** só tem uma habilidade (**Sem Dúvidas**), então é só escolher a classe, sem `habilidade`." and row(1311, "Erro Um")["class_name"] is None
runp(bot.classe_escolher.callback(s2, "Caçador", "", None)); assert row(1311, "Erro Um")["class_name"] == "Caçador" and "view" not in sent(s2)[1]          # texto vazio vale como sem habilidade
def sugerir(classe=None, uid=1):
    i = inter(uid, "J"); i.namespace = NS(classe=classe) if classe else NS(); return [c.value for c in run(bot._autocomplete_habilidade(i, ""))]
assert sugerir("Clérigo") == ["Mãos que Curam", "Bênção"] and sugerir("Ladrão") == ["Mão Leve", "Língua de Prata"] and sugerir("Caçador") == ["Mãos que Curam", "Bênção", "Mão Leve", "Língua de Prata"]

# --- /classe sem habilidade: já vêm os botões, sem outro comando ---
n1 = novo(1320, "Bot", "Botao Um"); preparar(1320, "Botao Um", "Humano", None); runp(bot.classe_escolher.callback(n1, "Clérigo", None, None))
vb = enviada(n1); assert isinstance(vb, paineis.EscolhaDeHabilidade) and vb.origem is n1 and vb.com_voltar is False and set(estado(vb)) == {"Mãos que Curam", "Bênção", "Confirmar habilidade"}; confere_componentes(vb)
assert row(1320, "Botao Um")["class_name"] == "Clérigo" and row(1320, "Botao Um")["class_ability"] is None
c = marcar(vb, "Bênção", 1320, "Bot"); e = editada(c)["embed"]; assert botao(vb, "Bênção").style == discord.ButtonStyle.success and e.fields[0].value == "Você vai levar **Bênção**. Confirma nos botões abaixo." and e.description.endswith("Vale **uma vez só**: depois de confirmar, só um mestre muda.")
assert estado(vb)["Confirmar habilidade"] == ("✅", False) and row(1320, "Botao Um")["class_ability"] is None
assert runp(vb.interaction_check(inter(999, "Intruso"))) is False and runp(vb.interaction_check(inter(1320, "Bot"))) is True
c = clique(vb, "Confirmar habilidade", 1320, "Bot"); assert editada(c)["view"] is None and editada(c)["embed"].fields[0].value == "Você levou **Bênção**." and row(1320, "Botao Um")["class_ability"] == "Bênção" and vb.is_finished()
# /habilidade sem argumento: botões se falta escolher, só o cartão se já escolheu
n2 = novo(1321, "Bot2", "Botao Dois"); preparar(1321, "Botao Dois", "Humano", "Ladrão")
runp(bot.habilidade.callback(n2, None, None)); vb2 = enviada(n2); assert isinstance(vb2, paineis.EscolhaDeHabilidade) and valor_do_campo(n2, "Habilidade de classe").endswith("Aperta um dos botões abaixo.")
marcar(vb2, "Língua de Prata", 1321, "Bot2")
c = clique(vb2, "Confirmar habilidade", 1321, "Bot2"); assert row(1321, "Botao Dois")["class_ability"] == "Língua de Prata"
runp(bot.habilidade.callback(n2, None, None)); assert "view" not in sent(n2)[1] and valor_do_campo(n2, "Habilidade de classe") == "Você levou **Língua de Prata**."
# confirmar com a escolha já feita por outro caminho: avisa e não sobrescreve
n3 = novo(1322, "Bot3", "Botao Tres"); preparar(1322, "Botao Tres", "Humano", "Clérigo"); runp(bot.habilidade.callback(n3, None, None)); vb3 = enviada(n3)
marcar(vb3, "Bênção", 1322, "Bot3"); db.set_class_ability(row(1322, "Botao Tres")["id"], "Mãos que Curam")                # enquanto isso, a escolha foi feita em outro lugar
c = clique(vb3, "Confirmar habilidade", 1322, "Bot3"); assert editada(c)["view"] is None and followups(c)[0][0].startswith("Não deu pra confirmar: a habilidade já foi escolhida") and row(1322, "Botao Tres")["class_ability"] == "Mãos que Curam"

# --- quem já tinha classe (Ladrão antigo) e falta a habilidade: botão Habilidade na ficha ---
o1 = novo(1330, "Vel", "Velho Ladrao"); preparar(1330, "Velho Ladrao", "Humano", "Ladrão")
pf = painel_de(1330, "Velho Ladrao", "Vel"); assert estado(pf)["Habilidade de classe"] == ("✨", False) and "Classe" not in estado(pf); confere_componentes(pf)
assert botao(pf, "Habilidade de classe").style == discord.ButtonStyle.primary
c = clique(pf, "Habilidade de classe", 1330, "Vel"); hv = editada(c)["view"]; e = editada(c)["embed"]
assert isinstance(hv, paineis.EscolhaDeHabilidade) and hv.com_voltar and pf.is_finished() and estado(hv) == {"Mão Leve": ("✨", False), "Língua de Prata": ("✨", False), "Confirmar habilidade": ("✅", True), "Voltar": ("⬅️", False)}
assert e.fields[0].value == "Escolha uma das duas: **Mão Leve** ou **Língua de Prata**. Aperta um dos botões abaixo." and e.author.name == "✨ Habilidade de Velho Ladrao"; confere_componentes(hv)
c = clique(hv, "Voltar", 1330, "Vel"); pf = editada(c)["view"]; assert isinstance(pf, paineis.PainelFicha) and estado(pf)["Habilidade de classe"] == ("✨", False) and row(1330, "Velho Ladrao")["class_ability"] is None
hv = editada(clique(pf, "Habilidade de classe", 1330, "Vel"))["view"]; marcar(hv, "Mão Leve", 1330, "Vel"); c = clique(hv, "Confirmar habilidade", 1330, "Vel")
pf = editada(c)["view"]; assert isinstance(pf, paineis.PainelFicha) and estado(pf)["Classe"] == ("✅", True) and "Habilidade de classe" not in estado(pf) and row(1330, "Velho Ladrao")["class_ability"] == "Mão Leve"
e, kw = cartao_do_followup(c); assert kw["ephemeral"] and e.fields[0].value == "Você levou **Mão Leve**." and campos_da_ficha(editada(c)["embed"])["Classe"].endswith("✨ Mão Leve")
# o mestre refaz a classe: a escolha volta a ficar aberta e o botão reaparece
run(bot.mestre_corrigir_classe.callback(gm, alvo(1330, "Vel"), "Ladrão", None)); assert estado(painel_de(1330, "Velho Ladrao", "Vel"))["Habilidade de classe"] == ("✨", False)
# classe de uma habilidade só nunca mostra o botão
assert "Habilidade de classe" not in estado(painel_de(1301, "Beto Um", "Beto")) and estado(painel_de(1301, "Beto Um", "Beto"))["Classe"] == ("✅", True)
print("X4. classe e habilidade por botão OK")

# ============================ Y. as abas e as barras de Vida, Sanidade, Mana e Estamina ============================
def vitais_de(uid, nome): return db.get_vitals_lost(row(uid, nome)["id"])
def desc_de(c): return editada(c)["embed"].description
yv = pronto(1400, "Vit", "Vital Vit", classe="Caçador"); YC = row(1400, "Vital Vit")["id"]
db.set_attributes(YC, {"forca": 2, "destreza": 0, "vitalidade": 3, "razao": 0, "vontade": 2, "alma": 1})     # Caçador: Vida 3x5+35=50, Sanidade 2x5+15=25, Mana (1+2)x3+5=14, Estamina (2+3)x3+20=35
# --- as abas ---
pf = painel_de(1400, "Vital Vit", "Vit")
assert estado_completo(pf)["Ficha"] == ("📋", True) and estado_completo(pf)["Vitais"] == ("❤️", False) and botao(pf, "Ficha").style == discord.ButtonStyle.primary and botao(pf, "Vitais").style == discord.ButtonStyle.secondary
assert botao(pf, "Ficha").row == 0 and botao(pf, "Vitais").row == 0 and all(b.row >= 1 for b in pf.children if b.label not in ("Ficha", "Vitais", "Perícias", "Habilidades")); confere_componentes(pf)
c = clique(pf, "Vitais", 1400, "Vit"); pv = editada(c)["view"]
assert isinstance(pv, paineis.PainelVitais) and pf.is_finished() and pv.selecionado == "vida" and editada(c)["embed"].title == "❤️ Vitais de Vital Vit"; confere_componentes(pv)
assert estado_completo(pv) == {"Ficha": ("📋", False), "Vitais": ("❤️", True), "Perícias": ("🎯", False), "Habilidades": ("✨", False), "-10": ("None", False), "-5": ("None", False), "-1": ("None", False), "+1": ("None", False), "+5": ("None", False), "+10": ("None", False), "Valor exato": ("✏️", False), "Restaurar tudo": ("♻️", False)}
assert [b.label for b in pv.children if isinstance(b, discord.ui.Button) and b.row == 2] == ["-10", "-5", "-1", "+1", "+5"] and [b.label for b in pv.children if isinstance(b, discord.ui.Button) and b.row == 3] == ["+10", "Valor exato", "Restaurar tudo"]
assert botao(pv, "-5").style == discord.ButtonStyle.danger and botao(pv, "+5").style == discord.ButtonStyle.success
sel = seletor(pv); assert sel.placeholder == "1. Escolhe a barra" and [(o.label, o.value, o.description, o.default) for o in sel.options] == [("Vida", "vida", "50/50", True), ("Sanidade", "sanidade", "25/25", False), ("Mana", "mana", "14/14", False), ("Estamina", "estamina", "35/35", False)]
d = desc_de(c); assert "▶️ ❤️ **Vida** · 50/50\n" + "▰" * 10 in d and "▫️ 🧠 **Sanidade** · 25/25" in d and "▫️ 🔷 **Mana** · 14/14" in d and "▫️ ⚡ **Estamina** · 35/35" in d and "1. Escolhe a barra" not in d and "**1.** Escolhe a barra no menu" in d
# --- dano e cura ---
c = clique(pv, "-10", 1400, "Vit"); assert vitais_de(1400, "Vital Vit")["vida"] == 10 and "▶️ ❤️ **Vida** · 40/50\n" + "▰" * 8 + "▱" * 2 in desc_de(c) and editada(c)["view"] is pv
c = clique(pv, "-5", 1400, "Vit"); c = clique(pv, "-1", 1400, "Vit"); assert vitais_de(1400, "Vital Vit")["vida"] == 16 and "Vida** · 34/50" in desc_de(c)
assert seletor(pv).options[0].description == "34/50"                                                        # o menu também mostra o atual
for _ in range(5): c = clique(pv, "-10", 1400, "Vit")                                                       # dano demais: para no 0
assert vitais_de(1400, "Vital Vit")["vida"] == 50 and "Vida** · 0/50" in desc_de(c) and "💀 **Vida em 0.**" in desc_de(c) and editada(c)["embed"].color == discord.Color.dark_grey()
c = clique(pv, "+10", 1400, "Vit"); assert "Vida** · 10/50" in desc_de(c) and "💀" not in desc_de(c)
for _ in range(6): c = clique(pv, "+10", 1400, "Vit")                                                       # cura demais: para no máximo
assert vitais_de(1400, "Vital Vit")["vida"] == 0 and "Vida** · 50/50" in desc_de(c)
# --- trocar de barra ---
sel = seletor(pv); sel._values = ["mana"]; c = inter(1400, "Vit"); runp(sel.callback(c))
assert pv.selecionado == "mana" and "▶️ 🔷 **Mana** · 14/14" in desc_de(c) and "▫️ ❤️ **Vida** · 50/50" in desc_de(c) and [o.default for o in seletor(pv).options] == [False, False, True, False]
c = clique(pv, "-5", 1400, "Vit"); assert vitais_de(1400, "Vital Vit") == {"vida": 0, "sanidade": 0, "mana": 5, "estamina": 0} and "Mana** · 9/14" in desc_de(c)            # mexeu só na Mana
sel = seletor(pv); sel._values = ["coragem"]; c = inter(1400, "Vit"); runp(sel.callback(c)); assert c.response.send_message.call_args.args[0] == "Não conheço essa barra. Escolhe uma do menu." and pv.selecionado == "mana"
# --- valor exato ---
c = clique(pv, "Valor exato", 1400, "Vit"); m = c.response.send_modal.call_args.args[0]
assert isinstance(m, paineis.ModalValorExato) and m.title == "Mana: valor exato" and m.campo.default == "9" and m.campo.label == "Quanto de Mana você tem agora? (0 a 14)" and m.campo.required
def enviar_valor(texto): m.campo._value = texto; c = inter(1400, "Vit"); runp(m.on_submit(c)); return c
c = enviar_valor("3"); assert vitais_de(1400, "Vital Vit")["mana"] == 11 and "Mana** · 3/14" in desc_de(c) and editada(c)["view"] is pv
c = enviar_valor("99"); assert vitais_de(1400, "Vital Vit")["mana"] == 0 and "Mana** · 14/14" in desc_de(c)                                   # passou do máximo: fica no máximo
c = enviar_valor("0"); assert vitais_de(1400, "Vital Vit")["mana"] == 14
for ruim in ("abc", "-2", "", "3.5", "1 2"):
    c = enviar_valor(ruim); assert c.response.send_message.call_args.args[0] == "Escreve só um número, tipo 12." and c.response.send_message.call_args.kwargs["ephemeral"] and vitais_de(1400, "Vital Vit")["mana"] == 14
# --- restaurar tudo ---
for chave in ("vida", "estamina"): db.set_vital_lost(YC, chave, 7)
c = clique(pv, "Restaurar tudo", 1400, "Vit"); assert vitais_de(1400, "Vital Vit") == {k: 0 for k in rules.VITAL_KEYS} and "Vida** · 50/50" in desc_de(c) and "Estamina** · 35/35" in desc_de(c)
# --- o máximo sobe, o atual sobe junto ---
db.set_vital_lost(YC, "vida", 10); db.set_attributes(YC, {"vitalidade": 4})
pv2 = criar(paineis.PainelVitais, 1400, YC, "Vit"); assert "Vida** · 45/55" in pv2.embed().description                    # máximo 4x5+35=55, perdeu 10
db.set_attributes(YC, {"vitalidade": 3}); db.reset_vitals(YC)
# --- só o dono mexe, e a volta pra ficha guarda o que foi feito ---
assert runp(pv.interaction_check(inter(999, "Intruso"))) is False and runp(pv.interaction_check(inter(1400, "Vit"))) is True
db.set_vital_lost(YC, "vida", 20)
c = clique(pv, "Ficha", 1400, "Vit"); pf2 = editada(c)["view"]; assert isinstance(pf2, paineis.PainelFicha) and pv.is_finished() and estado_completo(pf2)["Ficha"] == ("📋", True) and estado(pf2)["Classe"] == ("✅", True)
c = clique(pf2, "Vitais", 1400, "Vit"); assert "Vida** · 30/50" in desc_de(c)                                # os números continuam lá
# --- sem classe não tem máximo: a aba avisa em vez de quebrar ---
sc = novo(1401, "Sem", "Sem Classe"); psc = painel_de(1401, "Sem Classe", "Sem"); c = clique(psc, "Vitais", 1401, "Sem"); pvs = editada(c)["view"]
assert "ainda não tem" in desc_de(c) and "aba **Ficha**" in desc_de(c) and set(estado_completo(pvs)) == {"Ficha", "Vitais", "Perícias", "Habilidades"} and seletor(pvs) is None
c = inter(1401, "Sem"); runp(pvs._mudar(5, c)); runp(pvs.aplicar_valor(c, 3)); assert vitais_de(1401, "Sem Classe") == {k: 0 for k in rules.VITAL_KEYS}    # sem classe, nada é gravado
print("Y. abas e vitais OK")

# ============================ Z. comandos de mestre separados e escondidos, e o aviso dos ADMs no resultado especial ============================
gm_ = inter(4, "Mestre Belmont", roles=["Mestre"]); jog = inter(1500, "Jogador")
# --- /mestre ajuda: só mestre ---
assert bot._eh_mestre in bot.mestre_ajuda.checks and bot._eh_mestre(jog) is False
run(bot.mestre_ajuda.callback(gm_, None)); e = sent(gm_)[1]["embed"]
assert sent(gm_)[1]["ephemeral"] and e.title == "🛡️ Ajuda do mestre" and [f.name for f in e.fields] == ["XP e nível", "Ficha", "Dados", "Sorteios", "Cena", "Habilidades e perícias", "Ajuda", "Jogadores"] and len(e) <= 6000
assert sum(f.value.count("`/mestre ") for f in e.fields) == 23 and "`/mestre sorte` mexe na sorte dos d20 de um personagem" in e.fields[2].value
run(bot.mestre_ajuda.callback(gm_, "dar_xp")); e = sent(gm_)[1]["embed"]; assert e.title == "📖 /mestre dar_xp" and sent(gm_)[1]["ephemeral"]
run(bot.mestre_ajuda.callback(gm_, "mestre sorte")); assert sent(gm_)[1]["embed"].title == "📖 /mestre sorte"
run(bot.mestre_ajuda.callback(gm_, "corrigir")); assert txt(gm_) == "Não achei nenhum comando de mestre com \"corrigir\". Quis dizer: `/mestre corrigir_nivel`, `/mestre corrigir_magia`, `/mestre corrigir_raca`, `/mestre corrigir_estado`, `/mestre corrigir_classe`?"
run(bot.mestre_ajuda.callback(gm_, "zzz")); assert txt(gm_) == "Não achei nenhum comando de mestre com \"zzz\". Usa `/mestre ajuda` pra ver a lista."
assert [c.value for c in run(bot._autocomplete_comando_mestre(gm_, "xp"))] == ["dar_xp", "exportar"] and [c.name for c in run(bot._autocomplete_comando_mestre(gm_, "escudo"))] == ["/mestre escudo"]
assert run(bot._autocomplete_comando_mestre(jog, "")) == []                                                      # quem não é mestre não vê nem o autocomplete
pm = {c.name: c.to_dict(bot.bot.tree) for c in bot.bot.tree.get_commands()}["mestre"]; aj = [o for o in pm["options"] if o["name"] == "ajuda"][0]
assert len(aj["description"]) <= 100 and [o["name"] for o in aj["options"]] == ["comando"] and not aj["options"][0].get("required") and aj["options"][0].get("autocomplete")
# --- o /ajuda dos jogadores: os comandos de mestre não existem ---
for quem in (jog, gm_):
    ch = run(bot._autocomplete_comando(quem, "")); assert ch and not any("mestre" in c.value for c in ch) and not any("mestre" in c.value for c in run(bot._autocomplete_comando(quem, "mestre")))      # nem pro mestre: fica no /mestre ajuda
for buscado in ("mestre dar_xp", "dar_xp", "sorte", "escudo", "mestre"):
    jog2 = inter(1500, "Jogador"); run(bot.ajuda_comando.callback(jog2, buscado)); t = txt(jog2)
    assert t.startswith(f"Não achei nenhum comando com \"{buscado}\".") and "Quis dizer" not in t and "`/mestre" not in t and t.endswith("Use `/ajuda` pra ver a lista de comandos."), buscado      # sem dica que revele os comandos
gm2 = inter(4, "Mestre Belmont", roles=["Mestre"]); run(bot.ajuda_comando.callback(gm2, "mestre dar_xp")); assert sent(gm2)[1]["embed"].title == "📖 /mestre dar_xp"      # o mestre ainda pode por aqui
jog3 = inter(1500, "Jogador"); run(bot.help_comando.callback(jog3, "mestre dar_xp")); assert txt(jog3).startswith("Não achei nenhum comando")
# --- o grupo /mestre fica escondido de quem não tem Gerenciar servidor ---
assert bot.ESCONDER_COMANDOS_DE_MESTRE is True and pm["default_member_permissions"] == discord.Permissions(manage_guild=True).value == 32 and pm["dm_permission"] is False
assert [c.name for c in bot.bot.tree.get_commands() if c.to_dict(bot.bot.tree).get("default_member_permissions") is not None] == ["mestre"]    # os comandos dos jogadores continuam visíveis pra todos
# --- 66 e 77 marcam o mestre e os ADMs do servidor ---
def cargo(id_, nome, adm=False, bot_=False): return NS(id=id_, name=nome, mention=f"<@&{id_}>" if nome != "@everyone" else "@everyone", permissions=NS(administrator=adm), managed=bot_)
todos_ = cargo(1, "@everyone"); r_mestre = cargo(555, "Mestre"); r_dono = cargo(777, "Dono", adm=True); r_bot = cargo(888, "Baptism of Blood", adm=True, bot_=True); r_jogador = cargo(999, "Jogador")
def com_cargos(i, *cargos): i.guild = NS(roles=list(cargos)); return i
za = com_cargos(novo(1510, "Zé", "Zé Adm"), todos_, r_jogador, r_mestre, r_dono, r_bot)
with dados(66): run(bot.raca_inicial.callback(za, None))
kw = sent(za)[1]; assert kw["content"] == "<@&555> <@&777>" and kw["allowed_mentions"].roles == [r_mestre, r_dono]       # o mestre e o ADM; nem o bot, nem o @everyone, nem o cargo de jogador
assert cartao_de(za).color.value == 0xC0392B and so_interrogacao(cartao_de(za))
zs = com_cargos(novo(1511, "Zé", "Zé Sem Mestre"), todos_, r_dono, r_bot)                                        # sem cargo de mestre: só os ADMs
with dados(77): run(bot.classe_social.callback(zs, None))
assert sent(zs)[1]["content"] == "<@&777>" and sent(zs)[1]["allowed_mentions"].roles == [r_dono] and cartao_de(zs).color.value == 0xF1C40F
zn = com_cargos(novo(1512, "Zé", "Zé Ninguém"), todos_, r_jogador, r_bot)                                        # ninguém pra marcar: o cartão sai igual, sem marcação
with dados(66): run(bot.raca_inicial.callback(zn, None))
assert "content" not in sent(zn)[1] and "allowed_mentions" not in sent(zn)[1] and so_interrogacao(cartao_de(zn))
muitos = [cargo(2000 + k, f"Adm{k}", adm=True) for k in range(8)]; zm = com_cargos(novo(1513, "Zé", "Zé Muitos"), r_mestre, *muitos)
vm_ = vampiro_sem_magia(1514, "Mago", "Zé Mago"); com_cargos(vm_, r_mestre, r_dono)
with dados(77): run(bot.magia_inicial.callback(vm_, None))
assert sent(vm_)[1]["content"] == "<@&555> <@&777>"                                                              # na magia também
with dados(66): run(bot.raca_inicial.callback(zm, None))
assert sent(zm)[1]["content"].count("<@&") == 5 == len(sent(zm)[1]["allowed_mentions"].roles) and sent(zm)[1]["content"].startswith("<@&555> <@&2000>")      # no máximo 5 cargos
zc = com_cargos(novo(1515, "Zé", "Zé Cem"), todos_, r_mestre, r_dono)                                            # o 100 da classe social segue marcando só o cargo de mestre
with dados(100): run(bot.classe_social.callback(zc, None))
assert sent(zc)[1]["content"] == "<@&555>" and sent(zc)[1]["allowed_mentions"].roles == [r_mestre]
print("Z. mestre separado e 66/77 OK")

# ============================ AA. perícias, habilidades criadas pelos jogadores e a fila do mestre ============================
def selects(view): return [x for x in view.children if isinstance(x, discord.ui.Select)]
def escolher(view, indice, valor, uid, nome, **extras):
    sel = selects(view)[indice]; sel._values = [valor]; c = inter(uid, nome, **extras); runp(sel.callback(c)); return c
def pontos_de(uid, nome): return db.get_skills(row(uid, nome)["id"])
def card_publico(c): return followups(c)[0][1]["embed"]
MESTRE_ = dict(roles=["Mestre"])
pe = pronto(1600, "Per", "Perito", classe="Caçador"); PC = row(1600, "Perito")["id"]
db.set_attributes(PC, {"forca": 3, "destreza": 2, "vitalidade": 3, "razao": 0, "vontade": 2, "alma": 1})          # Caçador: Mana (1+2)x3+5 = 14

# --- a aba Perícias: um ícone por perícia, que rola sozinho ---
def botao_de(view, pericia):
    achados = [b for b in view.children if isinstance(b, discord.ui.Button) and str(b.emoji) == rules.SKILL_ICONS[pericia]]
    assert len(achados) == 1, pericia; return achados[0]
def rolar_icone(view, pericia, uid=1600, nome="Per"):
    c = inter(uid, nome); runp(botao_de(view, pericia).callback(c)); return c
def azuis(view): return [p for p in rules.SKILLS if botao_de(view, p).style == discord.ButtonStyle.primary]
c = clique(painel_de(1600, "Perito", "Per"), "Perícias", 1600, "Per"); pp = editada(c)["view"]
assert isinstance(pp, paineis.PainelPericias) and editada(c)["embed"].title == "🎲 Perícias de Perito"; confere_componentes(pp)
botoes = [b for b in pp.children if isinstance(b, discord.ui.Button)]; icones = [b for b in botoes if b.label is None]
assert len(botoes) == 25 and {r: sum(1 for b in botoes if b.row == r) for r in range(5)} == {0: 5, 1: 5, 2: 5, 3: 5, 4: 5}
assert [str(b.emoji) for b in icones] == [rules.SKILL_ICONS[p] for p in rules.SKILLS] and [b.row for b in icones] == [1] * 5 + [2] * 5 + [3] * 5 + [4] * 3          # 18 ícones: 5, 5, 5 e 3
assert {b.label: (str(b.emoji), b.row) for b in botoes if b.label} == {"Ficha": ("📋", 0), "Vitais": ("❤️", 0), "Perícias": ("🎯", 0), "Habilidades": ("✨", 0), "Normal": ("🎲", 0), "Distribuir": ("🎯", 4), "Atributo": ("🧬", 4)}
assert azuis(pp) == ["Religião"]                                                                                         # Caçador que ainda não escolheu: só a vantagem fixa é azul
d = editada(c)["embed"].description; assert "⚠️ Escolhe a vantagem da sua classe: Luta ou Pontaria." in d and "🥷 **Furtividade** +2 · Destreza 2 + 0" in d.split("\n") and "⛪ **Religião** +0 · Razão 0 + 0 ⭐" in d.split("\n")
with d20s(9): c = rolar_icone(pp, "Furtividade")                                                                        # Destreza 2 + 0 pontos
e = card_publico(c); assert e.title == "🎲 Perito rolou 1d20+2" and e.description == "**9 + 2 = 11**" and e.footer.text == "Furtividade (Destreza) · jogador: Per" and "ephemeral" not in followups(c)[0][1] and editada(c)["view"] is pp
assert [(h["purpose"], h["notation"], h["total"], h["character_name"]) for h in historico_de(1600)][0] == ("Furtividade (Destreza)", "1d20+2", 11, "Perito")
with d20s(4, 15): c = rolar_icone(pp, "Religião")                                                                       # a vantagem da classe entra sozinha
assert card_publico(c).title == "🎲 Perito rolou 1d20" and card_publico(c).description == "**15 = 15**\n⭐ classe: vantagem (4 e 15)" and card_publico(c).footer.text == "Religião (Razão) · jogador: Per"
db.set_skill_points(PC, "Luta", 4)
with d20s(14): c = rolar_icone(pp, "Luta")                                                                              # Força 3 + 4 pontos, sem vantagem (ainda não escolheu)
assert card_publico(c).title == "🎲 Perito rolou 1d20+7" and card_publico(c).description == "**14 + 7 = 21**"
# o modo do jogador
c = clique(pp, "Normal", 1600, "Per"); assert pp.modo == "vantagem" and editada(c)["embed"].footer.text.startswith("Modo: vantagem") and estado_completo(pp)["Vantagem"] == ("⬆️", False)
with d20s(4, 15): c = rolar_icone(pp, "Furtividade")
assert card_publico(c).description == "**15 + 2 = 17**\n🎲 modo vantagem (4 e 15)"
with d20s(4, 15): c = rolar_icone(pp, "Religião")                                                                       # vantagem do jogador + vantagem da classe: não soma, vale a do jogador
assert card_publico(c).description == "**15 = 15**\n🎲 modo vantagem (4 e 15)"
c = clique(pp, "Vantagem", 1600, "Per"); assert pp.modo == "desvantagem" and estado_completo(pp)["Desvantagem"] == ("⬇️", False)
with d20s(12, 3): c = rolar_icone(pp, "Furtividade")
assert card_publico(c).description == "**3 + 2 = 5**\n🎲 modo desvantagem (12 e 3)"
with d20s(8): c = rolar_icone(pp, "Religião")                                                                            # desvantagem e vantagem da classe se cancelam
assert card_publico(c).title == "🎲 Perito rolou 1d20" and card_publico(c).description == "**8 = 8**"
c = clique(pp, "Desvantagem", 1600, "Per"); assert pp.modo == "normal"
db.add_dice_effect(PC, "bonus", 2, 1, False, None, "4")                                                                # sorte do mestre junto com a vantagem da classe
with d20s(4, 15): c = rolar_icone(pp, "Religião")
assert card_publico(c).description == "**15 + 2 = 17**\n🍀 classe: vantagem (4 e 15) · +2" and db.get_dice_effects(PC) == []
# o atributo forçado
c = clique(pp, "Atributo", 1600, "Per"); assert pp.atributo == "forca" and botao(pp, "Atributo").style == discord.ButtonStyle.success and editada(c)["embed"].footer.text == "Modo: normal · Atributo: Força · jogador: Per"
with d20s(9): c = rolar_icone(pp, "Furtividade")                                                                         # Força 3 em vez de Destreza 2
assert card_publico(c).title == "🎲 Perito rolou 1d20+3" and card_publico(c).description == "**9 + 3 = 12**" and card_publico(c).footer.text == "Furtividade (Força) · jogador: Per"
for esperado in ("destreza", "vitalidade", "razao", "vontade", "alma", None): clique(pp, "Atributo", 1600, "Per"); assert pp.atributo == esperado
assert botao(pp, "Atributo").style == discord.ButtonStyle.secondary and runp(pp.interaction_check(inter(999, "Intruso"))) is False and runp(pp.interaction_check(inter(1600, "Per"))) is True
# --- a tela de distribuir pontos ---
for p in rules.SKILLS: db.set_skill_points(PC, p, 0)
c = clique(pp, "Distribuir", 1600, "Per"); pd = editada(c)["view"]
assert isinstance(pd, paineis.PainelDistribuirPericias) and pp.is_finished() and editada(c)["embed"].title == "🎯 Pontos de perícia de Perito"; confere_componentes(pd)
assert estado_completo(pd) == {"Ficha": ("📋", False), "Vitais": ("❤️", False), "Perícias": ("🎯", True), "Habilidades": ("✨", False), "-1": ("None", True), "+1": ("None", False), "Rolar perícias": ("🎲", False)}
sk, vant = selects(pd); assert sk.placeholder == "1. Escolhe a perícia" and len(sk.options) == 18 and sk.options[0].default and (vant.placeholder, vant.min_values, vant.max_values) == ("⭐ Escolhe a vantagem da classe (Luta ou Pontaria)", 1, 1)
assert [(o.label, o.default) for o in vant.options] == [("Luta", False), ("Pontaria", False)] and [o.description for o in sk.options if "⭐" in o.description] == ["0 pontos · ⭐ vantagem da classe"] and "⚠️ Escolhe a vantagem da sua classe" in editada(c)["embed"].description
c = escolher(pd, 1, "Pontaria", 1600, "Per"); assert db.get_skill_picks(PC) == ["Pontaria"] and "⚠️" not in editada(c)["embed"].description and [(o.label, o.default) for o in selects(pd)[1].options] == [("Luta", False), ("Pontaria", True)]
c = escolher(pd, 1, "Luta", 1600, "Per"); assert db.get_skill_picks(PC) == ["Luta"]                                       # troca, não soma
c = escolher(pd, 1, "Furtividade", 1600, "Per"); assert db.get_skill_picks(PC) == ["Luta"]                              # o que não cabe na classe é ignorado
c = inter(1600, "Per"); runp(pd._redesenhar(c)); assert "🎯 Pontos livres: **25** de 25" in editada(c)["embed"].description
for _ in range(7): c = clique(pd, "+1", 1600, "Per")
assert pontos_de(1600, "Perito") == {"Acrobacia": 7} and estado_completo(pd)["+1"] == ("None", True) and "Pontos livres: **18** de 25" in editada(c)["embed"].description      # chegou no máximo: o +1 desliga
c = inter(1600, "Per"); runp(pd._mudar(1, c)); assert pontos_de(1600, "Perito") == {"Acrobacia": 7}                      # nem forçando passa de 7
escolher(pd, 0, "Luta", 1600, "Per")
for _ in range(5): c = clique(pd, "+1", 1600, "Per")
c = clique(pd, "-1", 1600, "Per"); assert pontos_de(1600, "Perito") == {"Acrobacia": 7, "Luta": 4} and "Pontos livres: **14** de 25" in editada(c)["embed"].description and pd.selecionada == "Luta"
assert [o.description for o in selects(pd)[0].options if o.label == "Luta"] == ["4 pontos · ⭐ vantagem da classe"]
for _ in range(4): clique(pd, "-1", 1600, "Per")
assert pontos_de(1600, "Perito") == {"Acrobacia": 7} and estado_completo(pd)["-1"] == ("None", True); c = inter(1600, "Per"); runp(pd._mudar(-1, c)); assert pontos_de(1600, "Perito") == {"Acrobacia": 7}    # em 0, nada negativo
for pericia, n in (("Luta", 4), ("Fortitude", 7), ("Reflexos", 7)): db.set_skill_points(PC, pericia, n)
escolher(pd, 0, "Atletismo", 1600, "Per"); c = inter(1600, "Per"); runp(pd._redesenhar(c))
assert "✅ Todos os 25 pontos distribuídos" in editada(c)["embed"].description and estado_completo(pd)["+1"] == ("None", True) and editada(c)["embed"].color == discord.Color.green()     # tudo gasto: o +1 desliga mesmo com 0 na perícia
db.set_skill_points(PC, "Reflexos", 0); db.set_skill_points(PC, "Fortitude", 3); c = inter(1600, "Per"); runp(pd._redesenhar(c))
assert pontos_de(1600, "Perito") == {"Acrobacia": 7, "Luta": 4, "Fortitude": 3} and "Pontos livres: **11** de 25" in editada(c)["embed"].description
# de volta pra rolagem: a escolha de Luta já vale
c = clique(pd, "Rolar perícias", 1600, "Per"); pp2 = editada(c)["view"]; assert isinstance(pp2, paineis.PainelPericias) and pd.is_finished() and azuis(pp2) == ["Luta", "Religião"]
with d20s(4, 15): c = rolar_icone(pp2, "Luta")                                                                          # Força 3 + 4 pontos, e a vantagem da classe sozinha
assert card_publico(c).title == "🎲 Perito rolou 1d20+7" and card_publico(c).description == "**15 + 7 = 22**\n⭐ classe: vantagem (4 e 15)" and "⚠️" not in editada(c)["embed"].description
c = clique(pp2, "Ficha", 1600, "Per"); assert isinstance(editada(c)["view"], paineis.PainelFicha) and pp2.is_finished()
# --- Mundano escolhe duas; Sábio tem as duas fixas; os pontos de cada um ---
mu = pronto(1601, "Mun", "Mundana", classe="Mundano"); MU = row(1601, "Mundana")["id"]
pm = editada(clique(painel_de(1601, "Mundana", "Mun"), "Perícias", 1601, "Mun"))["view"]
assert "⚠️ Escolhe 2 perícias com vantagem." in pm.embed().description and azuis(pm) == []
cm = clique(pm, "Distribuir", 1601, "Mun"); pdm = editada(cm)["view"]; assert "de 30" in editada(cm)["embed"].description
vm = selects(pdm)[1]; assert (vm.min_values, vm.max_values, len(vm.options), vm.placeholder) == (1, 2, 18, "⭐ Escolhe a vantagem da classe (2 perícias)")
vm._values = ["Luta", "Furtividade"]; c = inter(1601, "Mun"); runp(vm.callback(c)); assert db.get_skill_picks(MU) == ["Luta", "Furtividade"] and "⚠️" not in editada(c)["embed"].description
pm2 = editada(clique(pdm, "Rolar perícias", 1601, "Mun"))["view"]; assert azuis(pm2) == ["Furtividade", "Luta"]
sa = pronto(1602, "Sab", "Sabia", classe="Sábio"); db.set_level(row(1602, "Sabia")["id"], 3)
psa = editada(clique(painel_de(1602, "Sabia", "Sab"), "Perícias", 1602, "Sab"))["view"]; assert azuis(psa) == ["Ciências", "Investigação"] and "⚠️" not in psa.embed().description
csa = clique(psa, "Distribuir", 1602, "Sab"); assert "de 33" in editada(csa)["embed"].description and len(selects(editada(csa)["view"])) == 1          # Sábio nível 3: 25 + 2 x 4, e não tem escolha de vantagem
# --- /pericias abre a aba direto; /mestre pericia conserta ---
i = inter(1600, "Per"); runp(bot.pericias_comando.callback(i, None)); v = enviada(i)
assert isinstance(v, paineis.PainelPericias) and sent(i)[1]["ephemeral"] and v.origem is i and sent(i)[1]["embed"].title == "🎲 Perícias de Perito"
i = inter(1600, "Per"); runp(bot.pericias_comando.callback(i, "Fantasma")); assert "Não achei nenhum personagem seu chamado **Fantasma**" in txt(i)
assert bot._eh_mestre in bot.mestre_pericia.checks
for p in rules.SKILLS: db.set_skill_points(PC, p, 0)
db.set_skill_points(PC, "Acrobacia", 7); db.set_skill_points(PC, "Luta", 4)
run(bot.mestre_pericia.callback(gm, alvo(1600, "Per"), "Luta", 6, None)); assert txt(gm) == "🎯 **Perito**: Luta foi de 4 pra **6**. Pontos livres agora: **12**." and pontos_de(1600, "Perito")["Luta"] == 6 and sent(gm)[1]["ephemeral"]
run(bot.mestre_pericia.callback(gm, alvo(1600, "Per"), "Luta", 20, None)); assert pontos_de(1600, "Perito")["Luta"] == 20 and "Pontos livres agora: **-2**" in txt(gm)             # o mestre passa do limite
run(bot.mestre_pericia.callback(gm, alvo(1600, "Per"), "Luta", 0, None)); assert "Luta" not in pontos_de(1600, "Perito")
run(bot.mestre_pericia.callback(gm, alvo(9990, "Fantasma"), "Luta", 3, None)); assert txt(gm) == "Fantasma ainda não tem personagem criado."
with sqlite3.connect(db.DB_PATH) as cn: assert cn.execute("SELECT detail FROM master_actions WHERE action = 'pericia' ORDER BY id").fetchall() == [("Luta: 4 -> 6",), ("Luta: 6 -> 20",), ("Luta: 20 -> 0",)]
print("AA1. perícias OK")

# --- a aba Habilidades: criar, editar ---
def enviar_form(m, nome, desc, ef, uid=1600, jog="Per"):
    m.nome._value, m.descricao._value, m.efeito._value = nome, desc, ef; c = inter(uid, jog); runp(m.on_submit(c)); return c
GM = lambda: inter(4, "Mestre Belmont", **MESTRE_)
c = clique(painel_de(1600, "Perito", "Per"), "Habilidades", 1600, "Per"); ph = editada(c)["view"]
assert isinstance(ph, paineis.PainelHabilidades) and editada(c)["embed"].title == "✨ Habilidades de Perito" and "Você ainda não criou nenhuma habilidade" in editada(c)["embed"].description
assert estado_completo(ph) == {"Ficha": ("📋", False), "Vitais": ("❤️", False), "Perícias": ("🎯", False), "Habilidades": ("✨", True), "Criar habilidade": ("➕", False), "Usar": ("⚡", True), "Editar": ("✏️", True), "Apagar": ("🗑", True)} and selects(ph) == []; confere_componentes(ph)
c = clique(ph, "Criar habilidade", 1600, "Per"); m = c.response.send_modal.call_args.args[0]
assert isinstance(m, paineis.ModalHabilidade) and m.title == "Nova habilidade" and [x.label for x in m.children] == ["Nome da habilidade", "Descrição (o que é e como funciona)", "O que você quer que ela faça"]
assert [x.max_length for x in m.children] == [40, 400, 300] and all(x.required for x in m.children) and all(x.default is None for x in m.children)
c = enviar_form(m, "", "Fogo.", "dano"); assert followups(c)[0] == ("Dá um nome pra habilidade.", {"ephemeral": True}) and db.list_abilities(PC) == []                  # erro: nada é criado
c = enviar_form(m, "Bola de Fogo", "Uma bola de fogo.", "causa 2d8 de dano e gasta 15 de Mana"); AID = db.list_abilities(PC)[0]["id"]
assert followups(c)[0][0].startswith("⏳ **Bola de Fogo** foi pra fila do mestre.") and followups(c)[0][1] == {"ephemeral": True} and ph.selecionada == AID and editada(c)["view"] is ph
assert [(o.label, o.value, o.description, str(o.emoji), o.default) for o in selects(ph)[0].options] == [("Bola de Fogo", str(AID), "aguardando o mestre", "⏳", True)] and selects(ph)[0].placeholder == "Escolhe uma habilidade"
assert estado_completo(ph)["Usar"] == ("⚡", True) and estado_completo(ph)["Editar"] == ("✏️", False) and estado_completo(ph)["Apagar"] == ("🗑", False) and [f.name for f in editada(c)["embed"].fields] == ["Descrição", "Efeito que você pediu"]
c = clique(ph, "Editar", 1600, "Per"); m = c.response.send_modal.call_args.args[0]
assert m.title == "Editar habilidade" and [x.default for x in m.children] == ["Bola de Fogo", "Uma bola de fogo.", "causa 2d8 de dano e gasta 15 de Mana"]
c = enviar_form(m, "Bola de Fogo", "Uma bola de fogo.", "causa 2d8 de dano e gasta 5 de Mana"); assert followups(c)[0][0] == "⏳ **Bola de Fogo** voltou pra fila do mestre." and db.get_ability(AID)["effect_text"] == "causa 2d8 de dano e gasta 5 de Mana"

# --- a fila do mestre ---
m_ = GM(); runp(bot.mestre_habilidades.callback(m_)); fila = enviada(m_)
assert bot._eh_mestre in bot.mestre_habilidades.checks and isinstance(fila, escudo.FilaDeHabilidades) and fila.origem is m_ and sent(m_)[1]["ephemeral"] and sent(m_)[1]["embed"].title == "🛡️ Habilidades dos jogadores"
assert sent(m_)[1]["embed"].description == "⏳ **1** aguardando · 🔧 **0** em ajuste · ✅ 0 aprovadas (as mais recentes)\n\nEscolhe uma no primeiro menu."
assert len(selects(fila)) == 1 and not [b for b in fila.children if isinstance(b, discord.ui.Button)]; q = selects(fila)[0]
assert q.placeholder == "1. Escolhe a habilidade" and [(o.label, o.value, str(o.emoji)) for o in q.options] == [("Bola de Fogo · Perito", str(AID), "⏳")]
assert runp(fila.interaction_check(inter(999, "Intruso", **MESTRE_))) is False and runp(fila.interaction_check(inter(4, "Mestre Belmont"))) is False and runp(fila.interaction_check(GM())) is True      # só o dono, e só enquanto for mestre
c = escolher(fila, 0, str(AID), 4, "Mestre Belmont", **MESTRE_)
assert [x.placeholder for x in selects(fila)] == ["1. Escolhe a habilidade", "2. Dado de dano ou cura", "3. O que custa pra usar", "4. Somar um atributo ao dano ou à cura (opcional)"] and [len(x.options) for x in selects(fila)] == [1, 25, 21, 7]
assert [b.label for b in fila.children if isinstance(b, discord.ui.Button)] == ["Aprovar", "Pedir ajuste", "Recusar", "Corrigir texto", "Valores exatos"] and all(b.row == 4 for b in fila.children if isinstance(b, discord.ui.Button)); confere_componentes(fila)
e = editada(c)["embed"]; assert [f.name for f in e.fields] == ["⏳ Bola de Fogo", "Descrição", "Efeito que o jogador pediu", "Como vai ficar (nos menus)"] and e.fields[0].value == "**Perito** · <@1600> · aguardando o mestre"
assert e.fields[3].value == "**Custo:** sem custo\n**Rolagem:** sem rolagem" and [[o.value for o in x.options if o.default] for x in selects(fila)[1:]] == [["nenhuma"], ["nenhum"], ["nenhum"]]
escolher(fila, 1, "dano:2d8", 4, "Mestre Belmont", **MESTRE_); escolher(fila, 2, "mana:5", 4, "Mestre Belmont", **MESTRE_); c = escolher(fila, 3, "forca", 4, "Mestre Belmont", **MESTRE_)
assert editada(c)["embed"].fields[3].value == "**Custo:** 🔷 5 de Mana\n**Rolagem:** dano 2d8 + Força" and [[o.value for o in x.options if o.default] for x in selects(fila)[1:]] == [["dano:2d8"], ["mana:5"], ["forca"]]
assert (db.get_ability(AID)["status"], db.get_ability(AID)["cost_resource"], db.get_ability(AID)["roll_dice"]) == ("pendente", None, None)               # os menus ainda não gravam: só o botão
escolher(fila, 1, "cura:1d6", 4, "Mestre Belmont", **MESTRE_); assert fila.rascunho["tipo"] == "cura" and fila.rascunho["dado"] == "1d6"
escolher(fila, 1, "nenhuma", 4, "Mestre Belmont", **MESTRE_); assert (fila.rascunho["tipo"], fila.rascunho["dado"]) == (None, None)
escolher(fila, 2, "nenhum", 4, "Mestre Belmont", **MESTRE_); assert (fila.rascunho["recurso"], fila.rascunho["valor"]) == (None, 0)
escolher(fila, 3, "nenhum", 4, "Mestre Belmont", **MESTRE_); assert fila.rascunho["atributo"] is None
# valores exatos (o que não está nos menus)
c = clique(fila, "Valores exatos", 4, "Mestre Belmont", **MESTRE_); mv = c.response.send_modal.call_args.args[0]
assert mv.title == "Valores exatos" and [x.default for x in mv.children] == [None, "dano", None, None] and not any(x.required for x in mv.children)
def enviar_valores(dado, tipo, custo, atributo):
    mv.dado._value, mv.tipo._value, mv.custo._value, mv.atributo._value = dado, tipo, custo, atributo; c = GM(); runp(mv.on_submit(c)); return c
assert followups(enviar_valores("abc", "dano", "", ""))[0][0].startswith("Dado inválido: escreve tipo 2d8 ou 1d6+2.") and fila.rascunho["dado"] is None
assert followups(enviar_valores("2d8", "veneno", "", ""))[0][0] == "Escreve **dano** ou **cura** no tipo." and followups(enviar_valores("2d8", "dano", "mana x", ""))[0][0].startswith("Custo inválido")
assert followups(enviar_valores("2d8", "dano", "", "agilidade"))[0][0].startswith("Atributo inválido") and fila.rascunho["dado"] is None                    # um erro não muda nada
c = enviar_valores("1d6+2", "cura", "estamina 10", "destreza"); assert followups(c)[0] == ("🔢 Valores marcados. Falta só apertar **Aprovar** (ou pedir ajuste).", {"ephemeral": True})
assert editada(c)["embed"].fields[3].value == "**Custo:** ⚡ 10 de Estamina\n**Rolagem:** cura 1d6+2 + Destreza" and db.get_ability(AID)["status"] == "pendente"
c = enviar_valores("2d8", "dano", "mana 5", "força"); assert editada(c)["embed"].fields[3].value == "**Custo:** 🔷 5 de Mana\n**Rolagem:** dano 2d8 + Força"
c = clique(fila, "Valores exatos", 4, "Mestre Belmont", **MESTRE_); assert [x.default for x in c.response.send_modal.call_args.args[0].children] == ["2d8", "dano", "mana 5", "Força"]      # o formulário já vem com o que está marcado
# corrigir o texto
c = clique(fila, "Corrigir texto", 4, "Mestre Belmont", **MESTRE_); mt = c.response.send_modal.call_args.args[0]; assert mt.title == "Corrigir a habilidade" and [x.default for x in mt.children][0] == "Bola de Fogo"
mt.nome._value, mt.descricao._value, mt.efeito._value = "", "d", "e"; c = GM(); runp(mt.on_submit(c)); assert followups(c)[0][0] == "Dá um nome pra habilidade." and db.get_ability(AID)["name"] == "Bola de Fogo"
mt.nome._value = "Bola de Fogo Maior"; mt.descricao._value = "Uma bola enorme."; mt.efeito._value = "causa 2d8 de dano"; c = GM(); runp(mt.on_submit(c))
assert followups(c)[0][0] == "✏️ Texto de **Bola de Fogo Maior** corrigido." and db.get_ability(AID)["status"] == "pendente" and selects(fila)[0].options[0].label == "Bola de Fogo Maior · Perito"
# aprovar
c = clique(fila, "Aprovar", 4, "Mestre Belmont", **MESTRE_)
assert followups(c)[0] == ("✅ **Bola de Fogo Maior** aprovada: o jogador já pode usar.", {"ephemeral": True}) and editada(c)["embed"].description.startswith("⏳ **0** aguardando · 🔧 **0** em ajuste · ✅ 1 aprovadas")
ab = db.get_ability(AID); assert (ab["status"], ab["cost_resource"], ab["cost_amount"], ab["roll_kind"], ab["roll_dice"], ab["roll_attribute"], ab["decided_by"]) == ("aprovada", "mana", 5, "dano", "2d8", "forca", "4") and fila.selecionada == AID
with sqlite3.connect(db.DB_PATH) as cn: assert cn.execute("SELECT master_name, action, detail FROM master_actions WHERE action = 'habilidade' ORDER BY id").fetchall() == [("Mestre Belmont", "habilidade", f"aprovada: habilidade #{AID} (🔷 5 de Mana, dano 2d8 + Força)")]

# --- o jogador usa a habilidade aprovada ---
ph = criar(paineis.PainelHabilidades, 1600, PC, "Per", AID); e = ph.embed(); assert len(e) <= 6000 and all(len(f.value) <= 1024 for f in e.fields)
assert [(f.name, f.value) for f in e.fields] == [("Descrição", "Uma bola enorme."), ("Efeito que você pediu", "causa 2d8 de dano"), ("Custo e rolagem", "🔷 5 de Mana · dano 2d8 + Força")]
assert estado_completo(ph)["Usar"] == ("⚡", False) and estado_completo(ph)["Editar"] == ("✏️", True) and estado_completo(ph)["Apagar"] == ("🗑", True)             # aprovada: usa, mas não edita nem apaga
ROLL_REAL = dice.roll
dice.roll = lambda n: dice.RollResult(n, [5, 3], 0, 8)
try: c = clique(ph, "Usar", 1600, "Per")
finally: dice.roll = ROLL_REAL
e = card_publico(c); assert "ephemeral" not in followups(c)[0][1] and e.title == "✨ Bola de Fogo Maior" and e.author.name == "Perito usou uma habilidade" and e.color == discord.Color.red() and e.footer.text == "jogador: Per"
assert [(f.name, f.value) for f in e.fields] == [("Custo", "🔷 -5 de Mana (sobram 9/14)"), ("Dano", "🎲 2d8: 5 + 3 + Força 3 = **11**"), ("O que ela faz", "causa 2d8 de dano")]
assert vitais_de(1600, "Perito")["mana"] == 5 and editada(c)["view"] is ph and [(h["purpose"], h["notation"], h["total"], h["rolls_json"]) for h in historico_de(1600)][0] == ("habilidade: Bola de Fogo Maior", "2d8", 11, "[5, 3]")
db.set_vital_lost(PC, "mana", 12)                                                                                       # sobra 2 de Mana, e a habilidade custa 5
def nao_pode_rolar(_): raise AssertionError("não pode rolar sem poder pagar")
dice.roll = nao_pode_rolar
try: c = clique(ph, "Usar", 1600, "Per")
finally: dice.roll = ROLL_REAL
assert followups(c) == [("Mana insuficiente: você tem 2 e a habilidade custa 5.", {"ephemeral": True})] and vitais_de(1600, "Perito")["mana"] == 12                 # nada de carta pública, nada gasto
db.reset_vitals(PC)
# aprovada: o jogador não edita nem apaga
mf = criar(paineis.ModalHabilidade, ph, db.get_ability(AID)); c = enviar_form(mf, "Outro Nome", "d", "e")
assert followups(c)[0] == ("Habilidade aprovada: só o mestre muda. Fala com ele se quiser ajustar.", {"ephemeral": True}) and db.get_ability(AID)["name"] == "Bola de Fogo Maior"
c = inter(1600, "Per"); runp(ph._apagar(c)); assert followups(c)[0] == ("Habilidade aprovada: só o mestre tira. Fala com ele.", {"ephemeral": True}) and db.get_ability(AID) is not None
# pedir ajuste
c = clique(fila, "Pedir ajuste", 4, "Mestre Belmont", **MESTRE_); mn = c.response.send_modal.call_args.args[0]
assert mn.title == "Pedir ajuste" and mn.campo.label == "O que o jogador precisa ajustar?" and mn.campo.required and mn.campo.max_length == 200
mn.campo._value = "  "; c = GM(); runp(mn.on_submit(c)); assert followups(c)[0][0] == "Escreve o que o jogador precisa ajustar." and db.get_ability(AID)["status"] == "aprovada"
mn.campo._value = "Menos dano"; c = GM(); runp(mn.on_submit(c))
assert followups(c)[0][0] == "🔧 Pedi ajuste em **Bola de Fogo Maior**: o jogador vê a sua nota." and (db.get_ability(AID)["status"], db.get_ability(AID)["master_note"]) == ("ajuste", "Menos dano") and "🔧 **1** em ajuste" in editada(c)["embed"].description
ph = criar(paineis.PainelHabilidades, 1600, PC, "Per", AID); assert ("Nota do mestre", "Menos dano") in [(f.name, f.value) for f in ph.embed().fields] and estado_completo(ph)["Usar"] == ("⚡", True) and estado_completo(ph)["Editar"] == ("✏️", False)
assert "🔧 **Bola de Fogo Maior** · o mestre pediu ajuste" in ph.embed().description
mf = criar(paineis.ModalHabilidade, ph, db.get_ability(AID)); c = enviar_form(mf, "Bola de Fogo Maior", "Uma bola enorme.", "causa 2d6 de dano")                  # o jogador ajusta e volta pra fila
assert db.get_ability(AID)["status"] == "pendente" and db.get_ability(AID)["master_note"] is None
c = escolher(fila, 0, str(AID), 4, "Mestre Belmont", **MESTRE_); assert editada(c)["embed"].description.startswith("⏳ **1** aguardando") and fila.rascunho["recurso"] == "mana" and fila.rascunho["dado"] == "2d8"      # o que o mestre tinha marcado continua gravado
# recusar
c = clique(fila, "Recusar", 4, "Mestre Belmont", **MESTRE_); mr = c.response.send_modal.call_args.args[0]
assert mr.title == "Recusar habilidade" and mr.campo.label == "Motivo (opcional, o jogador vê)" and not mr.campo.required
mr.campo._value = "Não cabe na campanha"; c = GM(); runp(mr.on_submit(c))
assert followups(c)[0][0] == "❌ **Bola de Fogo Maior** recusada." and db.get_ability(AID)["status"] == "recusada" and db.get_ability(AID)["master_note"] == "Não cabe na campanha" and fila.selecionada is None and fila.children == []
assert editada(c)["embed"].description == "Nenhuma habilidade na fila por enquanto. Quando um jogador criar uma, ela aparece aqui."
ph = criar(paineis.PainelHabilidades, 1600, PC, "Per", AID); assert "❌ **Bola de Fogo Maior** · recusada" in ph.embed().description and ("Nota do mestre", "Não cabe na campanha") in [(f.name, f.value) for f in ph.embed().fields]
assert estado_completo(ph)["Editar"] == ("✏️", False) and estado_completo(ph)["Apagar"] == ("🗑", False) and estado_completo(ph)["Usar"] == ("⚡", True)
c = clique(ph, "Apagar", 1600, "Per"); assert followups(c)[0] == ("🗑 **Bola de Fogo Maior** foi apagada.", {"ephemeral": True}) and db.get_ability(AID) is None and ph.selecionada is None and selects(ph) == []
# o limite de 8
for k in range(8): db.create_ability(PC, f"Hab {k}", "d", "e")
ph8 = criar(paineis.PainelHabilidades, 1600, PC, "Per"); assert estado_completo(ph8)["Criar habilidade"] == ("➕", True) and len(selects(ph8)[0].options) == 8 and habil.criar(PC, "Nona", "d", "e").ok is False
db.save_ability_decision(db.list_abilities(PC)[0]["id"], "recusada", None, 0, None, None, None, None, "4"); assert estado_completo(criar(paineis.PainelHabilidades, 1600, PC, "Per"))["Criar habilidade"] == ("➕", False)
# /habilidades abre a aba direto
i = inter(1600, "Per"); runp(bot.habilidades_comando.callback(i, None)); v = enviada(i)
assert isinstance(v, paineis.PainelHabilidades) and sent(i)[1]["ephemeral"] and v.origem is i and sent(i)[1]["embed"].title == "✨ Habilidades de Perito"
i = inter(1600, "Per"); runp(bot.habilidades_comando.callback(i, "Fantasma")); assert "Não achei nenhum personagem seu chamado **Fantasma**" in txt(i)
print("AA2. habilidades criadas e fila do mestre OK")

# ============================ AB. a mensagem "Comece aqui" ============================
def apertar(view, rotulo, uid, nome):
    c = inter(uid, nome); botao_ = [b for b in view.children if b.label == rotulo]; assert len(botao_) == 1, rotulo; run(botao_[0].callback(c)); return c
assert bot._eh_mestre in bot.mestre_comecar_aqui.checks
registrados = []; add_view_real = bot.bot.add_view; bot.bot.add_view = lambda v: registrados.append(type(v).__name__)
try: run(bot._preparar_bot())
finally: bot.bot.add_view = add_view_real
assert registrados == ["QuadroDaCena", "ComecoAqui"]                                                                    # os dois quadros de botões fixos voltam a funcionar quando o bot reinicia
va = bot.ComecoAqui(); assert va.timeout is None and va.is_persistent()
assert [(b.label, str(b.emoji), b.custom_id) for b in va.children] == [("Criar personagem", "🆕", "inicio:criar"), ("Minha ficha", "📋", "inicio:ficha"), ("Dados", "🎲", "inicio:dados"), ("Como funciona", "❓", "inicio:como")]
# o mestre posta a mensagem (pública) e recebe um aviso só pra ele
m_ = GM(); run(bot.mestre_comecar_aqui.callback(m_)); kw = sent(m_)[1]
assert "ephemeral" not in kw and kw["embed"].title == "🩸 Baptism of Blood" and isinstance(kw["view"], bot.ComecoAqui) and "/mestre" not in kw["embed"].description and "ficha" in kw["embed"].description
assert followups(m_) == [("📌 Postei. Fixa a mensagem no canal (o pino) pra ela ficar sempre à vista. Os botões continuam funcionando mesmo se o bot reiniciar.", {"ephemeral": True})]
# 🆕 Criar personagem: um formulário só com o nome
c = apertar(va, "Criar personagem", 1700, "Novata"); mn = c.response.send_modal.call_args.args[0]
assert isinstance(mn, bot.ModalNovoPersonagem) and mn.title == "Novo personagem" and (mn.nome.label, mn.nome.min_length, mn.nome.max_length, mn.nome.required) == ("Nome do personagem", 2, 60, True)
mn.nome._value = "A"; c = inter(1700, "Novata"); run(mn.on_submit(c)); assert txt(c) == "⚠️ O nome precisa ter entre 2 e 60 letras." and db.get_active_character("1700") is None
mn.nome._value = "Aurora Reis"; c = inter(1700, "Novata"); run(mn.on_submit(c)); kw = sent(c)[1]
assert kw["embed"].title == "🎭 Personagem criado" and "**Aurora Reis** agora é o personagem que você está usando (1 de 3 vagas)." in kw["embed"].description and isinstance(kw["view"], paineis.PainelFicha) and kw["ephemeral"] and db.get_active_character("1700")["name"] == "Aurora Reis"
c = inter(1700, "Novata"); run(mn.on_submit(c)); assert txt(c) == "Você já tem um personagem chamado **Aurora Reis**. Use `/personagem usar` pra voltar pra ele." and sent(c)[1]["ephemeral"]
# 📋 Minha ficha, 🎲 Dados e ❓ Como funciona
c = apertar(va, "Minha ficha", 1700, "Novata"); kw = sent(c)[1]; assert kw["embed"].title == "📖 Ficha de Aurora Reis" and isinstance(kw["view"], paineis.PainelFicha) and kw["ephemeral"] and kw["view"].origem is c
c = apertar(va, "Minha ficha", 1701, "Sem Ficha"); assert txt(c) == "Você ainda não tem personagem. Aperta **🆕 Criar personagem** na mensagem de boas-vindas pra começar." and sent(c)[1]["ephemeral"]
c = apertar(va, "Dados", 1700, "Novata"); kw = sent(c)[1]; assert isinstance(kw["view"], paineis.BandejaDados) and kw["ephemeral"]
c = apertar(va, "Como funciona", 1700, "Novata"); kw = sent(c)[1]; assert kw["embed"].title == "❓ Como funciona" and kw["ephemeral"] and kw["embed"].description.startswith("**1.** Aperta **🆕 Criar personagem** e diz o nome.") and "/mestre" not in kw["embed"].description and len(kw["embed"]) <= 6000
# ícone de perícia com a ficha incompleta: não rola (igual ao /rolar)
pp_inc = editada(clique(painel_de(1700, "Aurora Reis", "Novata"), "Perícias", 1700, "Novata"))["view"]
c = rolar_icone(pp_inc, "Furtividade", 1700, "Novata")
assert followups(c) == [("🔒 A ficha de **Aurora Reis** ainda não está pronta. O passo a passo está em `/ajuda`.", {"ephemeral": True})] and historico_de(1700) == []
# o download dos gifs: começa na partida, em segundo plano, deixa o resultado no log e dá pra desligar
import contextlib
import io as io_
chamadas = []
async def baixar_falso():
    chamadas.append("baixou"); return {"raca-humano": "ok (3 bytes, gif)", "raca-dhampir": "falhou: HTTP 403"}
async def partida():
    await bot._preparar_bot(); await asyncio.gather(*bot._tarefas_de_fundo)
baixar_real = bot.vitrine.baixar_imagens; bot.vitrine.baixar_imagens = baixar_falso; bot.bot.add_view = lambda v: None
try:
    os.environ["BAIXAR_IMAGENS"] = "1"; saida = io_.StringIO()
    with contextlib.redirect_stdout(saida): run(partida())
    assert chamadas == ["baixou"] and saida.getvalue() == "[imagens] raca-humano: ok (3 bytes, gif)\n[imagens] raca-dhampir: falhou: HTTP 403\n"
    bot._tarefas_de_fundo.clear(); os.environ["BAIXAR_IMAGENS"] = "0"
    run(partida()); assert chamadas == ["baixou"] and bot._tarefas_de_fundo == []                                  # desligado: não baixa nada
finally:
    os.environ["BAIXAR_IMAGENS"] = "0"; bot.vitrine.baixar_imagens = baixar_real; bot.bot.add_view = add_view_real; bot._tarefas_de_fundo.clear()
print("AB. Comece aqui OK")

print("\nTODOS OS TESTES DO BOT PASSARAM")
