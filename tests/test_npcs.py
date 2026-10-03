"""Testes dos NPCs e criaturas (npcs.py): leitores de texto, ficha, vida e rolagem.
Rodar da pasta do bot: python tests/test_npcs.py"""
import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import db
import dice
import npcs
import rules

db.DB_PATH = os.path.join(tempfile.mkdtemp(), "npcs.db"); db.init_db()
ATUAIS = {"forca": 1, "destreza": 2, "vitalidade": 3, "razao": 4, "vontade": 5, "alma": 6}

# ---------- 1. ler atributos: só muda o que foi escrito ----------
ok = lambda t: npcs.ler_atributos(t, ATUAIS)
assert ok("Força 5, Destreza 3") == ({**ATUAIS, "forca": 5, "destreza": 3}, None)
assert ok("FORCA 7; alma=9\nrazão: 0") == ({**ATUAIS, "forca": 7, "alma": 9, "razao": 0}, None) and ok("Vitalidade99") == ({**ATUAIS, "vitalidade": 99}, None)
assert ok("força 5 destreza 3 vontade 1") == ({**ATUAIS, "forca": 5, "destreza": 3, "vontade": 1}, None) and ok("Força 5, Força 6")[0]["forca"] == 6      # a última vale
assert ok("Agilidade 5") == (None, 'Não conheço o atributo "Agilidade". Os que existem: Força, Destreza, Vitalidade, Razão, Vontade, Alma.')
assert ok("Força 5 blah") == (None, 'Não entendi "blah". Escreve assim: Força 5, Destreza 3.')
assert ok("") == (None, "Escreve assim: Força 5, Destreza 3.") and ok("Força 100") == (None, "Atributo vai de 0 a 99.") and ok("Força -1") == (None, "Atributo vai de 0 a 99.")
assert ATUAIS == {"forca": 1, "destreza": 2, "vitalidade": 3, "razao": 4, "vontade": 5, "alma": 6}                          # não mexe no que recebeu
print("1. atributos OK")

# ---------- 2. ler perícias: a lista completa ----------
assert npcs.ler_pericias("Luta 6, Furtividade 4") == ({"Luta": 6, "Furtividade": 4}, None) and npcs.ler_pericias("luta 6; percepção: 3\ninvestigacao 2") == ({"Luta": 6, "Percepção": 3, "Investigação": 2}, None)
assert npcs.ler_pericias("Luta 0, Tática 2") == ({"Tática": 2}, None) and npcs.ler_pericias("") == ({}, None) and npcs.ler_pericias("  \n ") == ({}, None)
assert npcs.ler_pericias("Voar 3") == (None, 'Não conheço a perícia "Voar". Os que existem: ' + ", ".join(rules.SKILLS) + ".")
assert npcs.ler_pericias("Luta 31") == (None, "Os pontos de perícia vão de 0 a 30.") and npcs.ler_pericias("Luta 30") == ({"Luta": 30}, None) and npcs.ler_pericias("Luta 5 xis")[1] == 'Não entendi "xis". Escreve assim: Força 5, Destreza 3.'
print("2. perícias OK")

# ---------- 3. ler classes: até 3, sem repetir ----------
assert npcs.ler_classes("Mercenário, Caçador") == (["Mercenário", "Caçador"], None) and npcs.ler_classes("mercenario e cacador") == (["Mercenário", "Caçador"], None)
assert npcs.ler_classes("Feiticeiro") == (["Feiticeiros"], None) and npcs.ler_classes("Forja; Sábio/Ladrão") == (["Mestre de Forja", "Sábio", "Ladrão"], None) and npcs.ler_classes("Caçador, caçador") == (["Caçador"], None)
assert npcs.ler_classes("") == ([], None) and npcs.ler_classes("  ,  ") == ([], None)
assert npcs.ler_classes("Paladino") == (None, 'Não conheço a classe "Paladino". As que existem: Caçador, Clérigo, Feiticeiros, Ladrão, Mercenário, Mestre de Forja, Mundano, Sábio.')
assert npcs.ler_classes("Caçador, Clérigo, Ladrão, Sábio") == (None, "No máximo 3 classes por NPC.")
print("3. classes OK")

# ---------- 4. ler número ----------
assert npcs.ler_inteiro("+10", -999, 9999, "Bônus") == (10, None) and npcs.ler_inteiro(" -5 ", -999, 9999, "Bônus") == (-5, None) and npcs.ler_inteiro("1 2", 0, 99, "X") == (12, None) and npcs.ler_inteiro("0", 0, 9, "X") == (0, None)
assert npcs.ler_inteiro("abc", 0, 9, "Vida") == (None, "Vida: escreve só um número, tipo 12 ou -5.") and npcs.ler_inteiro("", 0, 9, "Vida")[0] is None and npcs.ler_inteiro("3.5", 0, 9, "Vida")[0] is None
assert npcs.ler_inteiro("10000", -999, 9999, "Bônus de Vida") == (None, "Bônus de Vida vai de -999 a 9999.") and npcs.ler_inteiro("-1000", -999, 9999, "Bônus de Vida")[0] is None
print("4. números OK")

# ---------- 5. a ficha ----------
sid = npcs.criar_do_modelo("4", "Guarda do Rei", "Soldado", "npc", "Humano"); npc = db.get_npc(sid)
assert (npc["name"], npc["kind"], npc["species"], npc["level"], npcs.classes_de(npc), npcs.atributos_de(npc), npc["notes"]) == ("Guarda do Rei", "npc", "Humano", 2, ["Mercenário"], {"forca": 2, "destreza": 2, "vitalidade": 2, "razao": 1, "vontade": 1, "alma": 0}, "")
assert db.get_npc_skills(sid) == {"Luta": 3, "Pontaria": 2, "Percepção": 2} and {k: v["total"] for k, v in npcs.recursos(npc).items()} == {"vida": 50, "sanidade": 30, "mana": 11, "estamina": 44}
assert npcs.classes_de(db.get_npc(npcs.criar_do_modelo("4", "Povo", "Ralé", "criatura"))) == [] and db.get_npc(npcs.criar_do_modelo("4", "Rei Corvo", "Lenda", "criatura"))["level"] == 10
assert db.get_npc(npcs.criar_do_modelo("4", "Povinho", "Ralé"))["notes"] == rules.NPC_TEMPLATES["Ralé"]["notes"]                  # o modelo traz as notas dele
db.update_npc(sid, bonus_vida=10, classes="Mercenário,Caçador"); npc = db.get_npc(sid); assert npcs.bonus_de(npc) == {"vida": 10, "sanidade": 0, "mana": 0, "estamina": 0} and npcs.recursos(npc)["vida"]["total"] == 20 + 30 + 35 + 10
r = npcs.resumo(sid); assert set(r) == {"npc", "recursos", "perdidos", "pericias"} and r["pericias"] == {"Luta": 3, "Pontaria": 2, "Percepção": 2} and r["perdidos"] == {k: 0 for k in rules.VITAL_KEYS}
db.update_npc(sid, bonus_vida=10, classes="Mercenário")
print("5. ficha OK")

# ---------- 6. vida: sobe e desce, e o máximo manual ----------
assert npcs.ajustar(sid, "vida", -20) == 40 and db.get_npc_lost(sid)["vida"] == 20                                                                    # máximo 60: 50 da ficha + 10 de bônus manual
assert npcs.ajustar(sid, "vida", -100) == 0 and db.get_npc_lost(sid)["vida"] == 60 and npcs.ajustar(sid, "vida", 999) == 60 and db.get_npc_lost(sid)["vida"] == 0                # dano para no 0 e cura no máximo (50 + 10 de bônus)
assert npcs.definir(sid, "vida", 12) == 12 and db.get_npc_lost(sid)["vida"] == 48 and npcs.definir(sid, "vida", 999) == 60 and npcs.definir(sid, "vida", -5) == 0
assert npcs.ajustar(sid, "mana", -4) == 7 and db.get_npc_lost(sid)["mana"] == 4 and db.get_npc_lost(sid)["estamina"] == 0                          # cada barra é independente
db.set_npc_lost(sid, "vida", 20); db.update_npc(sid, bonus_vida=40)                                                                                 # aumentar a vida: o atual sobe junto com o máximo
assert rules.vital_current(npcs.recursos(db.get_npc(sid))["vida"]["total"], db.get_npc_lost(sid)["vida"]) == 90 - 20
npcs.restaurar(sid); assert db.get_npc_lost(sid) == {k: 0 for k in rules.VITAL_KEYS}
print("6. vida OK")

# ---------- 7. rolagem ----------
npc = db.get_npc(sid); pericias = db.get_npc_skills(sid)
assert npcs.modificador(npc, pericias, "Luta") == (2 + 3, "forca") and npcs.modificador(npc, pericias, "Luta", "destreza") == (2 + 3, "destreza") and npcs.modificador(npc, pericias, "Furtividade") == (2, "destreza")
assert npcs.modificador(npc, pericias, "Ocultismo") == (1, "razao") and npcs.modificador(npc, pericias, "Intuição") == (0, "alma")
chamadas = []; real = dice.roll_many
def falso(notacao, efeitos):
    chamadas.append((notacao, [(e.tipo, e.origem) for e in efeitos]))
    return [dice.RollResult(notacao, [14], 5, 20)], (["modo vantagem (4 e 14)"] if efeitos else []), []
dice.roll_many = falso
try:
    primeira = npcs.lancar(npc, pericias, "Luta"); assert primeira[0] == "1d20+5" and [x.rolls for x in primeira[1]] == [[14]] and primeira[1][0].total == 19 and chamadas[-1] == ("1d20+5", [])
    n_, rs, marcas, motivo = npcs.lancar(npc, pericias, "Luta", "vantagem"); assert chamadas[-1] == ("1d20+5", [("vantagem", "jogador")]) and marcas == ["modo vantagem (4 e 14)"] and motivo == "Luta (Força)"
    assert npcs.lancar(npc, pericias, "Luta", "desvantagem")[0] == "1d20+5" and chamadas[-1][1] == [("desvantagem", "jogador")] and npcs.lancar(npc, pericias, "Luta", "normal")[2] == [] and chamadas[-1][1] == []
    assert npcs.lancar(npc, pericias, "Luta", "normal", "vontade")[0] == "1d20+4" and npcs.lancar(npc, pericias, "Luta", "normal", "vontade")[3] == "Luta (Vontade)"          # atributo forçado
    zero = db.get_npc(db.create_npc("4", "Sombra", "criatura")); assert npcs.lancar(zero, {}, "Furtividade")[0] == "1d20"                                           # sem bônus nenhum: só o d20
finally:
    dice.roll_many = real
n_, rs, marcas, motivo = npcs.lancar(npc, pericias, "Pontaria"); assert n_ == "1d20+4" and len(rs) == 1 and 5 <= rs[0].total <= 24 and motivo == "Pontaria (Destreza)"          # com o dado de verdade
print("7. rolagem OK")

print("\nTODOS OS TESTES DOS NPCS PASSARAM")
