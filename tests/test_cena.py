"""Testes das cenas: iniciativa, NPCs, a vez de cada um, intenções e os quadros (cena.py e o banco delas).
Rodar da pasta do bot: python tests/test_cena.py"""
import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import discord

import cena
import db
import dice
import rules

tmp = tempfile.mkdtemp()
db.DB_PATH = os.path.join(tmp, "cena.db"); db.init_db()
real_roll = dice.roll


class Dados:
    """Fixa o número que sai em cada dado, na ordem (o modificador continua o de verdade). Sobrar ou faltar dado é erro."""
    def __init__(self, *valores): self.valores = list(valores)
    def __enter__(self):
        def falso(notacao):
            assert self.valores, "rolou mais dado do que o esperado"
            r = real_roll(notacao); r.rolls = [self.valores.pop(0)] + r.rolls[1:]; return r
        dice.roll = falso; return self
    def __exit__(self, *a):
        dice.roll = real_roll
        assert not self.valores, f"sobrou dado: {self.valores}"


def personagem(uid, nome, destreza=0, celeridade=0):
    c = db.create_character(str(uid), nome)["id"]
    db.set_race(c, "Vampiro" if celeridade else "Humano", 40)
    if destreza: db.set_attributes(c, {"destreza": destreza})
    if celeridade: db.set_discipline_grade(c, "Celeridade", celeridade)
    return db.get_character_by_id(c)


def nomes(cena_id): return [(p["name"], p["initiative"]) for p in db.get_participants(cena_id)]


# ---------- 1. abrir e fechar cena ----------
c1 = db.create_scene("g", "100", "Motim na praça", "9")
assert c1 is not None and c1["round"] == 1 and c1["active"] == 1 and c1["turn_participant_id"] is None and c1["board_message_id"] is None
assert db.create_scene("g", "100", "Outra", "9") is None                                    # um canal só tem uma cena aberta
assert db.get_active_scene("100")["id"] == c1["id"] and db.get_active_scene("101") is None
c2 = db.create_scene("g", "101", "Em outro canal", "9"); assert c2 is not None and c2["id"] != c1["id"]                   # outro canal é outra cena
db.end_scene(c2["id"]); assert db.get_active_scene("101") is None and db.get_scene(c2["id"])["ended_at"] is not None and db.get_scene(c2["id"])["active"] == 0
assert db.create_scene("g", "101", "Nova no mesmo canal", "9") is not None                  # depois de encerrada, o canal abre outra
db.set_scene_board(c1["id"], "555"); assert db.get_scene(c1["id"])["board_message_id"] == "555"
db.set_scene_board(c1["id"], None); assert db.get_scene(c1["id"])["board_message_id"] is None
print("1. abrir e fechar cena OK")

# ---------- 2. iniciativa: 1d20 + Destreza, com vantagem pra Celeridade ----------
cid = c1["id"]; C = lambda: db.get_scene(cid)
kairon = personagem(1, "Kairon", destreza=3); akari = personagem(2, "Akari", destreza=1); vlad = personagem(3, "Vlad", destreza=2, celeridade=1); zero = personagem(4, "Zero")
with Dados(14): r = cena.entrar_na_cena(C(), kairon, "1", "Marcos", "g")
assert r == cena.Resultado(True, "🎲 **Kairon**: 1d20 = 14 + Destreza 3 = **17** de iniciativa.", True)
with Dados(9): assert cena.entrar_na_cena(C(), akari, "2", "Ana", "g").texto == "🎲 **Akari**: 1d20 = 9 + Destreza 1 = **10** de iniciativa."
with Dados(6, 18): r = cena.entrar_na_cena(C(), vlad, "3", "Vlad", "g")                    # Celeridade 1: dois d20, fica o maior
assert r.texto == "🎲 **Vlad**: vantagem da Celeridade: 6 e 18, fica o 18 + Destreza 2 = **20** de iniciativa." and r.mudou
with Dados(10): cena.entrar_na_cena(C(), zero, "4", "Zé", "g")                              # Destreza 0: soma 0
assert nomes(cid) == [("Vlad", 20), ("Kairon", 17), ("Akari", 10), ("Zero", 10)]            # do maior pro menor; no empate, quem entrou primeiro (Akari)
with Dados():                                                                                # entrar de novo não rola nada
    r = cena.entrar_na_cena(C(), kairon, "1", "Marcos", "g")
assert r == cena.Resultado(False, "**Kairon** já está na cena, com iniciativa **17**. Se precisar mudar, pede pra um mestre.", False) and len(nomes(cid)) == 4
h = db.get_history("1", 5); assert (h[0]["purpose"], h[0]["notation"], h[0]["total"], h[0]["character_name"]) == ("iniciativa", "1d20+3", 17, "Kairon") and h[0]["rolls_json"] == "[14]"
h = db.get_history("3", 5); assert (h[0]["purpose"], h[0]["notation"], h[0]["total"], h[0]["rolls_json"]) == ("iniciativa (vantagem)", "1d20+2", 20, "[6, 18]")
h = db.get_history("4", 5); assert h[0]["notation"] == "1d20"                              # Destreza 0: sem "+0"
p = db.find_participant_by_character(cid, vlad["id"]); assert (p["kind"], p["user_id"], p["character_id"], p["detail"]) == ("pc", "3", vlad["id"], "vantagem da Celeridade: 6 e 18, fica o 18 + Destreza 2")
celeridade0 = personagem(5, "Sem Vantagem", destreza=1); db.set_discipline_grade(celeridade0["id"], "Potência", 3)        # outra Disciplina não dá vantagem
with Dados(5): assert "1d20 = 5" in cena.entrar_na_cena(C(), celeridade0, "5", "X", "g").texto
print("2. iniciativa OK")

# ---------- 3. NPCs e a leitura da iniciativa ----------
L = cena.ler_iniciativa
assert L("12") == (12, "definida pelo mestre") and L(" -1 ") == (-1, "definida pelo mestre") and L("+3") == (3, "definida pelo mestre")
with Dados(11): assert L("1d20+3") == (14, "1d20+3: 11 + 3 = 14")
with Dados(7): assert L("d20") == (7, "d20: 7 = 7")
for ruim in ("abc", "d1", "1000", "", "12 13", "1d20++3"):
    assert isinstance(L(ruim), str) and L(ruim).startswith("Iniciativa inválida"), ruim
n1 = cena.adicionar_npc(C(), "Guarda", "12"); assert n1 == cena.Resultado(True, "➕ **Guarda** entrou na cena com iniciativa **12** (definida pelo mestre).", True)

g2 = cena.adicionar_npc(C(), "Guarda", "12"); assert g2.texto.startswith("➕ **Guarda 2** entrou") and g2.ok
g3 = cena.adicionar_npc(C(), "guarda", "12"); assert g3.texto.startswith("➕ **guarda 3** entrou")      # nome repetido ganha número, sem ligar pra maiúscula
with Dados(11): capitao = cena.adicionar_npc(C(), "  Capitão   Rocha  ", "1d20+3")
assert capitao.texto == "➕ **Capitão Rocha** entrou na cena com iniciativa **14** (1d20+3: 11 + 3 = 14)." and capitao.mudou                 # espaços sobrando somem
antes = len(nomes(cid))
for nome, ini, parte in (("", "10", "Escreve o nome"), ("   ", "10", "Escreve o nome"), ("A" * 41, "10", "passou de 40 letras"), ("Fulano", "xyz", "Iniciativa inválida")):
    r = cena.adicionar_npc(C(), nome, ini); assert (r.ok, r.mudou) == (False, False) and parte in r.texto, (nome, r)
assert len(nomes(cid)) == antes                                                            # nada disso entrou
assert [(p["name"], p["kind"]) for p in db.get_participants(cid) if p["name"].casefold().startswith("guarda")] == [("Guarda", "npc"), ("Guarda 2", "npc"), ("guarda 3", "npc")]
# a cena tem um limite de 25 (o menu do Discord mostra 25)
lotada = db.create_scene("g", "200", "Lotada", "9")["id"]
for i in range(25): assert db.add_participant(lotada, "npc", f"N{i}", i) is not None
assert db.add_participant(lotada, "npc", "N25", 1) is None and len(db.get_participants(lotada)) == 25
r = cena.adicionar_npc(db.get_scene(lotada), "Mais um", "5"); assert (r.ok, r.mudou) == (False, False) and "cheia" in r.texto
pj = personagem(6, "Retardatário", destreza=1)
with Dados(): r = cena.entrar_na_cena(db.get_scene(lotada), pj, "6", "R", "g")
assert (r.ok, r.mudou) == (False, False) and "cheia" in r.texto and db.count_rolls("6") == 0        # e nem rola dado
try: db.add_participant(lotada, "aliado", "X", 1); raise SystemExit("deveria recusar o tipo")
except ValueError: pass
print("3. NPCs OK")

# ---------- 4. mudar a iniciativa e remover ----------
guarda = next(p for p in db.get_participants(cid) if p["name"] == "Guarda")
r = cena.mudar_iniciativa(guarda["id"], "25"); assert r == cena.Resultado(True, "✏️ A iniciativa de **Guarda** agora é **25** (definida pelo mestre).", True)
assert nomes(cid)[0] == ("Guarda", 25) and nomes(cid)[1] == ("Vlad", 20)                    # a ordem se refaz
assert cena.mudar_iniciativa(guarda["id"], "zzz").ok is False and db.get_participant(guarda["id"])["initiative"] == 25
assert cena.mudar_iniciativa(99999, "5") == cena.Resultado(False, "Esse participante já saiu da cena.", False)
r = cena.remover_participante(C(), guarda["id"]); assert r == cena.Resultado(True, "🗑 **Guarda** saiu da cena.", True) and db.get_participant(guarda["id"]) is None
assert cena.remover_participante(C(), guarda["id"]).ok is False                            # já tinha saído
assert cena.remover_participante(C(), db.get_participants(lotada)[0]["id"]).ok is False    # de outra cena: recusa
assert len(db.get_participants(lotada)) == 25
print("4. mudar e remover OK")

# ---------- 5. a vez e a rodada ----------
t = db.create_scene("g", "300", "Turnos", "9")["id"]; T = lambda: db.get_scene(t)
assert cena.proximo_turno(t) == ("vazio", None, 1)                                          # ninguém na cena
a = db.add_participant(t, "pc", "Ana", 20, character_id=1, user_id="1"); b = db.add_participant(t, "npc", "Bruto", 15); c = db.add_participant(t, "pc", "Caio", 10, character_id=2, user_id="2")
assert T()["turn_participant_id"] is None
ev, p, rd = cena.proximo_turno(t); assert (ev, p["name"], rd) == ("turno", "Ana", 1) and T()["turn_participant_id"] == a
ev, p, rd = cena.proximo_turno(t); assert (ev, p["name"], rd) == ("turno", "Bruto", 1)
ev, p, rd = cena.proximo_turno(t); assert (ev, p["name"], rd) == ("turno", "Caio", 1)
ev, p, rd = cena.proximo_turno(t); assert (ev, p["name"], rd) == ("rodada", "Ana", 2) and T()["round"] == 2                # passou do último: rodada nova
ev, p, rd = cena.proximo_turno(t); assert (ev, p["name"], rd) == ("turno", "Bruto", 2)
# quem entra no meio não atrapalha a vez; a ordem se refaz e a vez continua com quem estava
d = db.add_participant(t, "npc", "Dragão", 30); assert T()["turn_participant_id"] == b
ev, p, rd = cena.proximo_turno(t); assert (ev, p["name"]) == ("turno", "Caio")
db.set_participant_initiative(c, 40, "x")                                                   # Caio (que está com a vez) passa pra frente: [Caio 40, Dragão 30, Ana 20, Bruto 15]
ev, p, rd = cena.proximo_turno(t); assert (ev, p["name"], rd) == ("turno", "Dragão", 2)      # a vez segue com quem estava: depois do Caio vem o Dragão
# remover: quem não tem a vez não muda nada
cena.remover_participante(T(), a); assert T()["turn_participant_id"] == d and [x["name"] for x in db.get_participants(t)] == ["Caio", "Dragão", "Bruto"]
# remover quem tem a vez: a vez volta pra quem vinha antes, e o próximo turno segue dali
cena.remover_participante(T(), d); assert T()["turn_participant_id"] == c
ev, p, rd = cena.proximo_turno(t); assert (ev, p["name"], rd) == ("turno", "Bruto", 2)
cena.remover_participante(T(), c); assert T()["turn_participant_id"] == b                    # tirar quem não tem a vez não mexe nela
ev, p, rd = cena.proximo_turno(t); assert (ev, p["name"], rd) == ("rodada", "Bruto", 3)      # sozinho na cena: cada passada é uma rodada
cena.remover_participante(T(), b); assert T()["turn_participant_id"] is None and cena.proximo_turno(t) == ("vazio", None, 3)   # tirou o único que tinha a vez
# quem tem a vez sai sendo o primeiro da ordem: a vez fica "de ninguém" e o próximo turno começa do primeiro
t2 = db.create_scene("g", "301", "Primeiro sai", "9")["id"]; x = db.add_participant(t2, "npc", "X", 20); y = db.add_participant(t2, "npc", "Y", 10)
cena.proximo_turno(t2); assert db.get_scene(t2)["turn_participant_id"] == x
cena.remover_participante(db.get_scene(t2), x); assert db.get_scene(t2)["turn_participant_id"] is None
ev, p, rd = cena.proximo_turno(t2); assert (ev, p["name"], rd) == ("turno", "Y", 1)
print("5. a vez e a rodada OK")

# ---------- 6. o aviso da vez (só marca jogador; NPC não marca ninguém) ----------
m = db.create_scene("g", "400", "Aviso", "9")["id"]; M = lambda: db.get_scene(m)
pa = db.add_participant(m, "pc", "Ana", 20, character_id=11, user_id="7"); pn = db.add_participant(m, "npc", "Bruto", 15)
texto, ment = cena.mensagem_da_vez(m, "turno", db.get_participant(pa))
assert texto == "▶️ Vez de <@7> · **Ana** (20) · ⏳ sem intenção" and [u.id for u in ment.users] == [7] and ment.everyone is False and not ment.roles
db.save_intention(m, pa, 1, "Atacar o guarda")
assert cena.mensagem_da_vez(m, "turno", db.get_participant(pa))[0].endswith("· 📝 intenção aguardando o mestre")
db.decide_intention(db.get_intention(pa, 1)["id"], "permitida", None, "9")
assert cena.mensagem_da_vez(m, "turno", db.get_participant(pa))[0] == "▶️ Vez de <@7> · **Ana** (20) · ✅ intenção permitida"
texto, ment = cena.mensagem_da_vez(m, "turno", db.get_participant(pn)); assert texto == "▶️ Vez de **Bruto** (NPC, 15)" and ment is None
db.set_scene_turn(m, pa, 2)                                                                  # rodada nova: as intenções da rodada 1 não valem mais
texto, _ = cena.mensagem_da_vez(m, "rodada", db.get_participant(pa)); assert texto == "🔔 **Rodada 2** começou.\n▶️ Vez de <@7> · **Ana** (20) · ⏳ sem intenção"
db.set_scene_turn(m, pa, 1)
print("6. aviso da vez OK")

# ---------- 7. intenções ----------
s7 = db.create_scene("g", "500", "Intenções", "9")["id"]; S = lambda: db.get_scene(s7)
ana7 = personagem(21, "Ana Sete", destreza=1); bia7 = personagem(22, "Bia Sete")
r = cena.enviar_intencao(S(), "21", "Atacar o guarda"); assert r == cena.Resultado(False, cena._SEM_LUGAR, False) and "/iniciativa" in r.texto     # fora da cena não manda
assert cena.ver_minha_intencao(S(), "21").texto == cena._SEM_LUGAR
with Dados(10): cena.entrar_na_cena(S(), ana7, "21", "Ana", "g")
with Dados(3): cena.entrar_na_cena(S(), bia7, "22", "Bia", "g")
pana = db.find_participant_by_character(s7, ana7["id"]); pbia = db.find_participant_by_character(s7, bia7["id"])
assert "ainda não mandou intenção na rodada 1" in cena.ver_minha_intencao(S(), "21").texto
for vazio in ("", "   ", "\n\n"):
    r = cena.enviar_intencao(S(), "21", vazio); assert (r.ok, r.mudou) == (False, False) and "Escreve a sua intenção" in r.texto
r = cena.enviar_intencao(S(), "21", "x" * 201); assert (r.ok, r.mudou) == (False, False) and "201 letras" in r.texto and "limite é 200" in r.texto
assert db.get_intention(pana["id"], 1) is None                                              # nada disso gravou
r = cena.enviar_intencao(S(), "21", "  Atacar   o guarda\npela retaguarda  ")
assert r == cena.Resultado(True, "📝 Intenção de **Ana Sete** enviada pro mestre.\n> Atacar o guarda pela retaguarda\nO quadro mostra quando ele decidir.", True)
assert db.get_intention(pana["id"], 1)["text"] == "Atacar o guarda pela retaguarda" and db.get_intention(pana["id"], 1)["status"] == "pendente"          # espaços e quebras de linha viram um espaço só
assert cena.enviar_intencao(S(), "21", "x" * 200).ok                                        # 200 cabe
r = cena.enviar_intencao(S(), "21", "Fugir pela janela"); assert r.ok and r.texto.startswith("📝 Intenção de **Ana Sete** trocada. A anterior foi descartada.") and db.get_intention(pana["id"], 1)["text"] == "Fugir pela janela"
assert list(db.list_intentions(s7, 1)) == [pana["id"]] and len(db.list_intentions(s7, 1)) == 1
intencao = db.get_intention(pana["id"], 1)
assert db.decide_intention(intencao["id"], "negada", "Tem um guarda na janela", "9") is True
assert db.decide_intention(intencao["id"], "permitida", None, "9") is False                # já decidida: quem chegou depois não sobrescreve
i2 = db.get_intention(pana["id"], 1); assert (i2["status"], i2["master_note"], i2["decided_by"]) == ("negada", "Tem um guarda na janela", "9") and i2["decided_at"]
v = cena.ver_minha_intencao(S(), "21").texto
assert v == "**Ana Sete**, rodada 1: ❌ intenção negada\n> Fugir pela janela\nMotivo do mestre: Tem um guarda na janela\nManda outra com `/intencao` se quiser tentar de novo."
r = cena.enviar_intencao(S(), "21", "Subir no telhado"); assert r.ok and r.texto.startswith("📝 Intenção de **Ana Sete** trocada")      # negada: pode mandar outra
i3 = db.get_intention(pana["id"], 1); assert (i3["status"], i3["master_note"], i3["decided_by"], i3["decided_at"]) == ("pendente", None, None, None) and i3["id"] == intencao["id"]
assert db.decide_intention(i3["id"], "permitida", None, "9") is True
assert cena.ver_minha_intencao(S(), "21").texto == "**Ana Sete**, rodada 1: ✅ intenção permitida\n> Subir no telhado"
r = cena.enviar_intencao(S(), "21", "Mudei de ideia"); assert (r.ok, r.mudou) == (False, False) and "já foi permitida" in r.texto and db.get_intention(pana["id"], 1)["text"] == "Subir no telhado"
try: db.decide_intention(i3["id"], "talvez", None, "9"); raise SystemExit("deveria recusar")
except ValueError: pass
# cada rodada tem a sua intenção
db.set_scene_turn(s7, None, 2)
assert "ainda não mandou intenção na rodada 2" in cena.ver_minha_intencao(S(), "21").texto and cena.enviar_intencao(S(), "21", "Correr").ok
assert db.get_intention(pana["id"], 1)["text"] == "Subir no telhado" and db.get_intention(pana["id"], 2)["text"] == "Correr"
db.set_scene_turn(s7, None, 1)
# a Bia tem duas personagens: vale a que está na cena, mesmo com a outra em uso
outra = personagem(22, "Bia Outra"); db.set_active_character("22", outra["id"])
assert cena.participante_do_usuario(s7, "22")["id"] == pbia["id"] and cena.enviar_intencao(S(), "22", "Esperar").ok
db.set_active_character("22", bia7["id"]); assert cena.participante_do_usuario(s7, "22")["id"] == pbia["id"]
assert cena.participante_do_usuario(s7, "999") is None
# tirar o participante leva as intenções dele junto
cena.remover_participante(S(), pbia["id"]); assert db.get_intention(pbia["id"], 1) is None and db.list_intentions(s7, 1).keys() == {pana["id"]}
print("7. intenções OK")

# ---------- 8. os quadros: o público nunca mostra o texto da intenção ----------
q = db.create_scene("g", "600", "Assalto ao palácio", "9")["id"]; Q = lambda: db.get_scene(q)
assert cena.embed_quadro(q).description == "**Rodada 1**\n\nNinguém entrou na iniciativa ainda.\n\n" + cena.LEGENDA
k = personagem(31, "Kai", destreza=2); l = personagem(32, "Lia"); n = personagem(33, "Nino")
with Dados(10): cena.entrar_na_cena(Q(), k, "31", "K", "g")                                # 12
with Dados(15): cena.entrar_na_cena(Q(), l, "32", "L", "g")                                # 15
with Dados(1): cena.entrar_na_cena(Q(), n, "33", "N", "g")                                 # 1
cena.adicionar_npc(Q(), "Guarda", "13")
SEGREDO = "Esfaquear o duque sem ninguém ver"
cena.enviar_intencao(Q(), "31", SEGREDO); cena.enviar_intencao(Q(), "32", "Distrair a guarda " + "muito " * 30)
db.decide_intention(db.get_intention(db.find_participant_by_character(q, l["id"])["id"], 1)["id"], "permitida", None, "9")
cena.proximo_turno(q)
e = cena.embed_quadro(q); tudo = " ".join([e.title or "", e.description or "", e.footer.text or ""] + [f.name + f.value for f in e.fields])
assert SEGREDO not in tudo and "Esfaquear" not in tudo and "Distrair" not in tudo and "“" not in tudo                             # o texto da intenção NUNCA vai pro quadro público
assert e.title == "⚔️ Assalto ao palácio" and e.color.value == cena.COR_QUADRO and e.footer.text == "🎲 entra na iniciativa · 📝 manda a sua intenção pro mestre (só ele lê)"
assert e.description == ("**Rodada 1**\n\n▶️ **1. Lia** · 15 ✅\n2. Guarda (NPC) · 13\n3. Kai · 12 📝\n4. Nino · 1 ⏳\n\n" + cena.LEGENDA)
# o do mestre mostra o texto (cortado), quem tem a vez e quantas esperam
ee = cena.embed_escudo(q)
assert ee.title == "🛡️ Escudo do Mestre · Assalto ao palácio" and SEGREDO in ee.description and "Distrair a guarda muito muito" in ee.description and "…" in ee.description
assert "vez de **Lia**" in ee.description and "▶️ **1. Lia** · 15 ✅" in ee.description and "    ↳ “" in ee.description and ee.footer.text.startswith("1 aguardando você")
kid = db.get_intention(db.find_participant_by_character(q, k["id"])["id"], 1)["id"]
ee = cena.embed_escudo(q, kid); assert [(f.name, f.value) for f in ee.fields] == [("📝 Kai", f"“{SEGREDO}”\nPermitir ou negar?")]
assert cena.embed_escudo(q, 99999).fields == [] and cena.embed_escudo(q, db.get_intention(db.find_participant_by_character(q, l["id"])["id"], 1)["id"]).fields == []     # decidida ou inexistente: nada selecionado
assert cena.opcoes_de_intencoes(q) == [(("Kai (12)"), str(kid), SEGREDO)]                   # só as pendentes, na ordem da iniciativa
for e2 in (cena.embed_quadro(q), cena.embed_escudo(q), cena.embed_sem_cena()):
    assert len(e2) <= 6000 and len(e2.description) <= 4096
assert cena.embed_sem_cena().title == "🛡️ Escudo do Mestre" and "Iniciar cena" in cena.embed_sem_cena().description
# encerrada: o quadro fica só com o registro, sem legenda nem botões
db.end_scene(q); e = cena.embed_quadro(q)
assert e.title == "⚔️ Assalto ao palácio (encerrada)" and cena.LEGENDA not in e.description and e.footer.text is None and e.color == discord.Color.dark_grey()
# uma cena cheia (25) cabe no embed
cheia = db.get_scene(lotada); assert len(cena.embed_quadro(lotada).description) < 4096 and len(cena.embed_escudo(lotada)) < 6000
# a opção do menu respeita os 100 caracteres do Discord
z = db.create_scene("g", "700", "Longa", "9")["id"]; zp = db.add_participant(z, "pc", "N" * 40, 5, character_id=91, user_id="91")
db.save_intention(z, zp, 1, "y" * 200)
(rot, val, desc), = cena.opcoes_de_intencoes(z); assert len(rot) <= 100 and len(desc) <= 100 and desc.endswith("…")
print("8. quadros OK")

print("\nTODOS OS TESTES DAS CENAS PASSARAM")
