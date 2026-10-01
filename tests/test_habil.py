"""Testes das habilidades criadas pelos jogadores (habil.py): criar, editar, apagar, o que o mestre decide e usar.
Rodar da pasta do bot: python tests/test_habil.py"""
import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import db
import dice
import habil
import rules

db.DB_PATH = os.path.join(tempfile.mkdtemp(), "habil.db"); db.init_db()
real_roll = dice.roll
R = habil.Resultado


def personagem(uid, nome, **atributos):
    c = db.create_character(str(uid), nome)["id"]
    if atributos: db.set_attributes(c, atributos)
    return c


def mexer_no_dado(rolls, modificador=0, lados=8):
    """Faz o próximo dado sair exatamente assim (os dados e o modificador)."""
    dice.roll = lambda notacao: dice.RollResult(notacao, list(rolls), modificador, lados)


# ---------- 1. criar ----------
c1 = personagem(1, "Kairon", forca=3)
r = habil.criar(c1, "  Bola   de  Fogo ", "Uma bola\nde fogo.", " causa   2d8 de dano ")
assert r.ok and r.id and r.texto == "⏳ **Bola de Fogo** foi pra fila do mestre. Quando ele aprovar e definir o custo e o dano, ela aparece aqui pronta pra usar."
ab = db.get_ability(r.id); assert (ab["name"], ab["description"], ab["effect_text"], ab["status"]) == ("Bola de Fogo", "Uma bola de fogo.", "causa 2d8 de dano", "pendente")      # espaços e quebras de linha viram um espaço só
assert habil.criar(c1, "bola de fogo", "Outra.", "x") == R(False, "Você já tem uma habilidade chamada **bola de fogo**.", None)            # nome repetido, sem ligar pra maiúscula
for nome, desc, ef, esperado in (
    ("", "d", "e", "Dá um nome pra habilidade."), ("   ", "d", "e", "Dá um nome pra habilidade."), ("N" * 41, "d", "e", "O nome passou de 40 letras. Encurta."),
    ("N", "", "e", "Escreve a descrição: o que é a habilidade e como ela funciona."), ("N", "d" * 401, "e", "A descrição passou de 400 letras. Resume."),
    ("N", "d", "", "Escreve o efeito que você quer: o que ela faz (dano, cura, custo...)."), ("N", "d", "e" * 301, "O efeito passou de 300 letras. Resume."),
):
    assert habil.criar(c1, nome, desc, ef) == R(False, esperado, None), (nome[:5], desc[:5], ef[:5])
assert len(db.list_abilities(c1)) == 1                                                                          # nada disso gravou
assert habil.criar(c1, "N" * 40, "d" * 400, "e" * 300).ok                                                       # o limite exato cabe
for k in range(6): assert habil.criar(c1, f"Hab {k}", "d", "e").ok
assert db.count_active_abilities(c1) == 8 and habil.criar(c1, "Nona", "d", "e") == R(False, "Você já tem 8 habilidades (sem contar as recusadas). Apaga uma pra criar outra.", None)
primeira = db.list_abilities(c1)[0]["id"]; db.save_ability_decision(primeira, "recusada", None, 0, None, None, None, None, "9")
assert habil.criar(c1, "Bola de Fogo", "d", "e").ok                                                # a recusada não conta no limite, e o nome dela fica livre
assert habil.criar(c1, "Nona", "d", "e") == R(False, "Você já tem 8 habilidades (sem contar as recusadas). Apaga uma pra criar outra.", None)      # mas só abriu uma vaga
print("1. criar OK")

# ---------- 2. editar e apagar ----------
c2 = personagem(2, "Akari"); ed = habil.criar(c2, "Gelo", "Congela.", "congela").id; ed2 = habil.criar(c2, "Neve", "Neva.", "neva").id
db.save_ability_decision(ed, "ajuste", None, 0, None, None, None, "Detalha mais", "9")
r = habil.editar(ed, "Gelo Forte", "Congela mais.", "congela por 2 turnos"); assert r == R(True, "⏳ **Gelo Forte** voltou pra fila do mestre.", ed)
ab = db.get_ability(ed); assert (ab["name"], ab["status"], ab["master_note"]) == ("Gelo Forte", "pendente", None)                      # editar volta pra fila e some a nota
assert habil.editar(ed, "Neve", "x", "y") == R(False, "Você já tem uma habilidade chamada **Neve**.", None) and db.get_ability(ed)["name"] == "Gelo Forte"
assert habil.editar(ed, "", "x", "y") == R(False, "Dá um nome pra habilidade.", None) and habil.editar(99999, "A", "b", "c") == R(False, "Essa habilidade não existe mais.", None)
assert habil.editar(ed, "Gelo Forte", "Congela mais.", "outro efeito").ok                                         # manter o próprio nome vale
db.save_ability_decision(ed2, "aprovada", "mana", 10, "dano", "1d6", None, None, "9")
assert habil.editar(ed2, "Neve 2", "x", "y") == R(False, "Habilidade aprovada: só o mestre muda. Fala com ele se quiser ajustar.", None) and db.get_ability(ed2)["name"] == "Neve"
assert habil.apagar(ed2) == R(False, "Habilidade aprovada: só o mestre tira. Fala com ele.", None) and db.get_ability(ed2) is not None
assert habil.apagar(ed) == R(True, "🗑 **Gelo Forte** foi apagada.", None) and db.get_ability(ed) is None and habil.apagar(ed) == R(False, "Essa habilidade já não existe.", None)
db.save_ability_decision(ed2, "recusada", None, 0, None, None, None, None, "9"); assert habil.apagar(ed2).ok                  # recusada também apaga
print("2. editar e apagar OK")

# ---------- 3. leitores do formulário do mestre ----------
assert habil.ler_dado("2d8") == ("2d8", None) and habil.ler_dado(" 1d6 + 2 ") == ("1d6+2", None) and habil.ler_dado("2D8") == ("2d8", None) and habil.ler_dado("") == (None, None) and habil.ler_dado("  ") == (None, None)
assert habil.ler_dado("3#d6") == (None, "Aqui o dado é um só, tipo 2d8 ou 1d6+2 (sem o #).")
d, erro = habil.ler_dado("abc"); assert d is None and erro.startswith("Dado inválido: escreve tipo 2d8 ou 1d6+2.") and habil.ler_dado("101d6")[0] is None
assert habil.ler_custo("mana 15") == ("mana", 15, None) and habil.ler_custo(" Estamina  5 ") == ("estamina", 5, None) and habil.ler_custo("VIDA 1") == ("vida", 1, None) and habil.ler_custo("sanidade 999") == ("sanidade", 999, None)
assert habil.ler_custo("") == habil.ler_custo("0") == habil.ler_custo("nenhum") == habil.ler_custo("Sem custo") == (None, 0, None)
MSG_CUSTO = "Custo inválido: escreve o recurso e o valor, tipo `mana 15` (recursos: vida, sanidade, mana, estamina)."
for ruim in ("mana", "mana 0", "mana 1000", "mana abc", "coragem 5", "mana 15 x", "15 mana", "mana -3"): assert habil.ler_custo(ruim) == (None, 0, MSG_CUSTO), ruim
assert habil.ler_atributo("força") == ("forca", None) and habil.ler_atributo("Razão") == ("razao", None) and habil.ler_atributo(" VONTADE ") == ("vontade", None) and habil.ler_atributo("alma") == ("alma", None)
assert habil.ler_atributo("") == habil.ler_atributo("nenhum") == habil.ler_atributo("Sem atributo") == (None, None)
assert habil.ler_atributo("agilidade") == (None, "Atributo inválido: escreve Força, Destreza, Vitalidade, Razão, Vontade ou Alma (ou deixa vazio).")
print("3. leitores OK")

# ---------- 4. o mestre decide ----------
c3 = personagem(3, "Mestrada"); h = habil.criar(c3, "Raio", "Um raio.", "dano de raio").id
def decidir(*a, **k): return habil.decidir(h, *a, **k)
assert decidir("aprovada", "mana", 15, "dano", "2d8", "forca", None, "4") == R(True, "✅ **Raio** aprovada: o jogador já pode usar.", h)
ab = db.get_ability(h); assert (ab["status"], ab["cost_resource"], ab["cost_amount"], ab["roll_kind"], ab["roll_dice"], ab["roll_attribute"], ab["decided_by"]) == ("aprovada", "mana", 15, "dano", "2d8", "forca", "4")
assert decidir("aprovada", None, 0, None, "1d6", None, None, "4").ok and (db.get_ability(h)["roll_kind"], db.get_ability(h)["cost_resource"]) == ("dano", None)          # dado sem tipo vira dano
assert decidir("aprovada", "mana", 5, "cura", None, None, None, "4") == R(False, "Escolheu dano ou cura mas faltou o dado. Escolhe um dado no menu.", None) and db.get_ability(h)["roll_dice"] == "1d6"
assert decidir("aprovada", "mana", 0, "cura", "1d8", None, None, "4").ok and db.get_ability(h)["cost_resource"] is None                                 # recurso com valor 0: sem custo
assert decidir("ajuste", None, 0, None, None, None, None, "  ") == R(False, "Escreve o que o jogador precisa ajustar.", None) and db.get_ability(h)["status"] == "aprovada"
assert decidir("ajuste", None, 0, None, None, None, "  Está   forte  demais " + "x" * 300, "4").ok and db.get_ability(h)["master_note"] == ("Está forte demais " + "x" * 300)[:200]       # a nota é limpa e limitada a 200
assert decidir("recusada", None, 0, None, None, None, None, "4") == R(True, "❌ **Raio** recusada.", h) and db.get_ability(h)["master_note"] is None
assert decidir("pendente", None, 0, None, None, None, None, "4").texto == "⏳ **Raio** salva (continua pendente)." and habil.decidir(99999, "aprovada", None, 0, None, None, None, None, "4") == R(False, "Essa habilidade não existe mais.", None)
decidir("aprovada", "estamina", 10, "dano", "1d6+2", "destreza", None, "4"); ab = db.get_ability(h)
assert habil.texto_do_custo(ab) == "⚡ 10 de Estamina" and habil.texto_da_rolagem(ab) == "dano 1d6+2 + Destreza"
decidir("aprovada", None, 0, "cura", "2d4", None, None, "4"); ab = db.get_ability(h); assert habil.texto_do_custo(ab) == "sem custo" and habil.texto_da_rolagem(ab) == "cura 2d4"
decidir("aprovada", None, 0, None, None, None, None, "4"); ab = db.get_ability(h); assert habil.texto_do_custo(ab) == "sem custo" and habil.texto_da_rolagem(ab) == "sem rolagem"
print("4. decidir OK")

# ---------- 5. usar: gasta o custo e rola o dado ----------
c5 = personagem(5, "Mago", forca=3, vontade=2); P = lambda: db.get_character_by_id(c5)
rec = {k: {"total": t} for k, t in (("vida", 50), ("sanidade", 25), ("mana", 14), ("estamina", 35))}
h5 = habil.criar(c5, "Bola", "Fogo.", "dano").id; A = lambda: db.get_ability(h5)
u = habil.usar(P(), A(), rec); assert u == habil.Uso(False, "Essa habilidade ainda não foi aprovada pelo mestre.")                 # pendente não usa
db.save_ability_decision(h5, "aprovada", "mana", 5, "dano", "2d8", "forca", None, "9")
mexer_no_dado([5, 3])
try:
    u = habil.usar(P(), A(), rec)
    assert u.ok and u.erro is None and u.custo == ("mana", 5, 9, 14) and u.rolagem.rolls == [5, 3] and u.atributo == ("Força", 3) and u.total == 11     # 5 + 3 + Força 3
    assert db.get_vitals_lost(c5)["mana"] == 5 and db.get_vitals_lost(c5)["vida"] == 0                                # gastou da Mana, só dela
    u = habil.usar(P(), A(), rec); assert u.custo == ("mana", 5, 4, 14) and db.get_vitals_lost(c5)["mana"] == 10       # gasta de novo, a partir do que sobrou
    u = habil.usar(P(), A(), rec); assert not u.ok and u.erro == "Mana insuficiente: você tem 4 e a habilidade custa 5." and db.get_vitals_lost(c5)["mana"] == 10 and u.rolagem is None      # não gasta nada
    db.set_vital_lost(c5, "mana", 9); u = habil.usar(P(), A(), rec); assert u.ok and u.custo == ("mana", 5, 0, 14) and db.get_vitals_lost(c5)["mana"] == 14      # gastar exatamente o que tem vale
finally:
    dice.roll = real_roll
db.reset_vitals(c5)
assert habil.usar(P(), A(), None) == habil.Uso(False, "As barras dependem da classe, e este personagem ainda não tem. Escolhe a classe primeiro.")
db.save_ability_decision(h5, "aprovada", "mana", 5, "dano", "abc", None, None, "9")                                    # dado estragado: avisa e não gasta o custo
u = habil.usar(P(), A(), rec); assert u == habil.Uso(False, "O dado dessa habilidade está inválido. Avisa o mestre.") and db.get_vitals_lost(c5)["mana"] == 0
db.save_ability_decision(h5, "aprovada", "vida", 10, "cura", "1d6", None, None, "9"); mexer_no_dado([4], 2, 6)
try:
    u = habil.usar(P(), A(), rec); assert u.ok and u.custo == ("vida", 10, 40, 50) and u.total == 6 and u.atributo is None and db.get_vitals_lost(c5)["vida"] == 10        # 4 + 2
finally:
    dice.roll = real_roll
db.save_ability_decision(h5, "aprovada", None, 0, None, None, None, None, "9")
u = habil.usar(P(), A(), None); assert u == habil.Uso(True, None, None, None, None, None) and db.get_vitals_lost(c5)["vida"] == 10        # sem custo e sem rolagem: só narrativa (e funciona até sem classe)
db.save_ability_decision(h5, "aprovada", "sanidade", 30, None, None, None, None, "9")
assert habil.usar(P(), A(), rec).erro == "Sanidade insuficiente: você tem 25 e a habilidade custa 30."
db.save_ability_decision(h5, "ajuste", None, 0, None, None, None, "x", "9"); assert not habil.usar(P(), A(), rec).ok
print("5. usar OK")

print("\nTODOS OS TESTES DAS HABILIDADES PASSARAM")
