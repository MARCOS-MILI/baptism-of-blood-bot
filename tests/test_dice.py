"""Testes dos dados: N#dado (3#d20+5), os efeitos de sorte do mestre e a leitura de dados escritos no chat.
Rodar da pasta do bot: python tests/test_dice.py"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import dice

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


def E(id_, tipo, valor=None, usos=1, discreto=False): return dice.EfeitoDeSorte(id_, tipo, valor, usos, discreto)
def totais(rs): return [r.total for r in rs]


def erra(funcao, *args):
    try: funcao(*args)
    except dice.DiceError as e: return str(e)
    raise SystemExit(f"deveria dar DiceError: {funcao.__name__}{args}")


# ---------- 1. N#dado: a leitura ----------
assert dice.split_repeticao("3#d20+5") == (3, "d20+5") and dice.split_repeticao(" 3 # d20+5 ") == (3, "d20+5")
assert dice.split_repeticao("d20") == (1, "d20") and dice.split_repeticao("1#d20") == (1, "d20") and dice.split_repeticao("10#d6") == (10, "d6")
assert dice.split_repeticao("3#") == (1, "3#")                                                              # sem dado depois do #: não é repetição
for ruim in ("11#d20", "0#d20", "100#d6"):
    assert "de 1 a 10" in erra(dice.split_repeticao, ruim), ruim
assert dice.MAX_REPETICOES == 10

# ---------- 2. validar sem rolar ----------
def nao_rola(_): raise SystemExit("validar não pode rolar dado")
dice.roll = nao_rola
try:
    for bom in ("d20", "1d20+5", "3#d20+5", "10#2d6-1", "100d6", "1d1000"): dice.validate(bom)
    for ruim in ("3#xyz", "abc", "3#0d20", "3#1d1", "101d6", "1d1001", "11#d20", "3#", ""): erra(dice.validate, ruim)
finally:
    dice.roll = real_roll
assert "Notação de dado inválida: 'xyz'" in erra(dice.validate, "3#xyz")
print("1-2. N# e validação OK")

# ---------- 3. N#dado sem sorte: cada rolagem é separada ----------
with Dados(14, 3, 20):
    rs, marcas, usados = dice.roll_many("3#d20+5")
assert totais(rs) == [19, 8, 25] and [r.rolls for r in rs] == [[14], [3], [20]] and [r.modifier for r in rs] == [5, 5, 5]
assert marcas == [[], [], []] and usados == [] and all(r.notation == "d20+5" and r.sides == 20 for r in rs)
with Dados(7):
    rs, marcas, usados = dice.roll_many("d20+5")                                                             # sem #: uma rolagem só
assert totais(rs) == [12] and marcas == [[]] and usados == []
with Dados(4, 5):
    rs, _, _ = dice.roll_many("2#2d6-1")                                                                     # os dados de cada rolagem somam separados
assert len(rs) == 2 and all(len(r.rolls) == 2 and r.modifier == -1 for r in rs)
erra(dice.roll_many, "11#d20"); erra(dice.roll_many, "3#xyz")
print("3. rolagens separadas OK")

# ---------- 4. cada efeito de sorte ----------
def com_sorte(notacao, efeitos, *dados):
    with Dados(*dados): return dice.roll_many(notacao, efeitos)

rs, marcas, usados = com_sorte("1d20+5", [E(1, "vantagem")], 4, 15)                                         # fica o maior
assert (totais(rs), rs[0].rolls, marcas, usados) == ([20], [15], [["vantagem (4 e 15)"]], [1])
rs, marcas, usados = com_sorte("1d20+5", [E(1, "vantagem")], 12, 3); assert (rs[0].rolls, marcas) == ([12], [["vantagem (12 e 3)"]])
rs, marcas, usados = com_sorte("1d20", [E(2, "desvantagem")], 12, 3); assert (totais(rs), marcas, usados) == ([3], [["desvantagem (12 e 3)"]], [2])
rs, marcas, usados = com_sorte("1d20", [E(2, "desvantagem")], 3, 12); assert rs[0].rolls == [3]
rs, marcas, usados = com_sorte("1d20+5", [E(1, "vantagem"), E(2, "desvantagem")], 9)                          # uma anula a outra: um dado só, gasta as duas
assert (totais(rs), marcas, usados) == ([14], [["vantagem e desvantagem se anularam"]], [1, 2])
rs, marcas, usados = com_sorte("1d20", [E(1, "vantagem", discreto=True), E(2, "desvantagem", discreto=True)], 9); assert (marcas, usados) == ([[]], [1, 2])
rs, marcas, usados = com_sorte("1d20", [E(1, "vantagem", discreto=True), E(2, "desvantagem")], 9); assert marcas == [["vantagem e desvantagem se anularam"]]
rs, marcas, usados = com_sorte("1d20+2", [E(3, "fixo", 20)], 3); assert (totais(rs), marcas, usados) == ([22], [["dado fixo em 20"]], [3])
rs, marcas, usados = com_sorte("1d20", [E(1, "vantagem"), E(3, "fixo", 1)], 5, 17); assert (rs[0].rolls, usados) == ([1], [1, 3])    # o fixo manda, e a vantagem também gasta
rs, marcas, usados = com_sorte("1d20", [E(4, "minimo", 10)], 3); assert (rs[0].rolls, marcas, usados) == ([10], [["dado mínimo 10"]], [4])
rs, marcas, usados = com_sorte("1d20", [E(4, "minimo", 10)], 15); assert (rs[0].rolls, marcas, usados) == ([15], [["dado mínimo 10"]], [4])   # gasta o uso mesmo sem mudar
rs, marcas, usados = com_sorte("1d20", [E(5, "maximo", 8)], 15); assert (rs[0].rolls, marcas, usados) == ([8], [["dado máximo 8"]], [5])
rs, marcas, usados = com_sorte("1d20", [E(5, "maximo", 8)], 6); assert rs[0].rolls == [6]
rs, marcas, usados = com_sorte("1d20", [E(4, "minimo", 10), E(5, "maximo", 12)], 20); assert (rs[0].rolls, usados) == ([12], [4, 5])
rs, marcas, usados = com_sorte("1d20+5", [E(6, "bonus", 3)], 10); assert (totais(rs), rs[0].modifier, rs[0].rolls, marcas, usados) == ([18], 8, [10], [["+3"]], [6])
rs, marcas, usados = com_sorte("1d20+5", [E(7, "penalidade", 2)], 10); assert (totais(rs), marcas, usados) == ([13], [["-2"]], [7])
rs, marcas, usados = com_sorte("1d20+5", [E(6, "bonus", 3), E(7, "penalidade", 2)], 10); assert (totais(rs), marcas, usados) == ([16], [["+3", "-2"]], [6, 7])
rs, marcas, usados = com_sorte("1d20", [E(1, "vantagem"), E(4, "minimo", 10), E(6, "bonus", 1)], 2, 6)         # a ordem: vantagem, depois o mínimo, depois o bônus
assert (rs[0].rolls, totais(rs), marcas, usados) == ([10], [11], [["vantagem (2 e 6)", "dado mínimo 10", "+1"]], [1, 4, 6])
print("4. efeitos OK")

# ---------- 5. vários usos, vários d20, discreto ----------
rs, marcas, usados = com_sorte("3#d20", [E(1, "vantagem", usos=2)], 5, 17, 9, 2, 14)                         # os 2 usos são das 2 primeiras rolagens
assert [r.rolls for r in rs] == [[17], [9], [14]] and marcas == [["vantagem (5 e 17)"], ["vantagem (9 e 2)"], []] and usados == [1, 1]
rs, marcas, usados = com_sorte("3#d20+1", [E(1, "bonus", 1, usos=1), E(2, "bonus", 5, usos=1)], 10, 10, 10)     # o segundo bônus entra quando o primeiro acaba
assert totais(rs) == [12, 16, 11] and marcas == [["+1"], ["+5"], []] and usados == [1, 2]
rs, marcas, usados = com_sorte("2#d20", [E(1, "bonus", 4, discreto=True)], 10, 10); assert (totais(rs), marcas, usados) == ([14, 10], [[], []], [1])   # discreto: aplica e não marca
efeitos = [E(1, "vantagem", usos=2)]; com_sorte("2#d20", efeitos, 1, 2, 3, 4); assert efeitos == [E(1, "vantagem", usos=2)]                        # a lista de quem chamou não é mexida
# só vale pra um d20 sozinho: qualquer outro dado passa direto, sem gastar e sem rolar dado extra
todos = [E(1, "vantagem"), E(2, "fixo", 20), E(3, "bonus", 9)]
for notacao, dados in (("1d6", (3,)), ("1d100", (3,)), ("2d20", (3,)), ("2#1d6", (3, 4))):
    rs, marcas, usados = com_sorte(notacao, todos, *dados)
    assert all(m == [] for m in marcas) and usados == [] and all(r.modifier == 0 for r in rs), notacao
rs, marcas, usados = com_sorte("1d20", [E(1, "vantagem", usos=0)], 5); assert (rs[0].rolls, marcas, usados) == ([5], [[]], [])                 # sem uso sobrando, não vale
rs, marcas, usados = com_sorte("1d20", [], 5); assert (rs[0].rolls, marcas, usados) == ([5], [[]], [])
rs, marcas, usados = com_sorte("1d20", None, 5); assert (rs[0].rolls, marcas, usados) == ([5], [[]], [])        # sem lista nenhuma
print("5. usos e discreto OK")

# ---------- 6. os nomes ----------
assert dice.EFEITOS == ("vantagem", "desvantagem", "bonus", "penalidade", "minimo", "maximo", "fixo")
assert set(dice.EFEITOS_COM_VALOR) == {"bonus", "penalidade", "minimo", "maximo", "fixo"} and set(dice.EFEITO_NOME) == set(dice.EFEITOS)
assert [dice.descrever_efeito(t, v) for t, v in (("vantagem", None), ("desvantagem", None), ("bonus", 3), ("penalidade", 2), ("minimo", 10), ("maximo", 8), ("fixo", 20))] == \
       ["vantagem", "desvantagem", "bônus +3", "penalidade -2", "dado mínimo 10", "dado máximo 8", "dado fixo 20"]
print("6. nomes OK")

# ---------- 7. dados escritos no chat, com N# ----------
P = dice.parse_texto
assert P("3#d20+5") == dice.PedidoDeDado("3#1d20+5", None, False) and P("3 # d20 + 5") == dice.PedidoDeDado("3#1d20+5", None, False)
assert P("+3#d20+5 ataque com a espada") == dice.PedidoDeDado("3#1d20+5", "ataque com a espada", True)
assert P("2#3d6-1") == dice.PedidoDeDado("2#3d6-1", None, False) and P("+2#d20") == dice.PedidoDeDado("2#1d20", None, True)
assert P("999#d20") == dice.PedidoDeDado("999#1d20", None, False) and "de 1 a 10" in erra(dice.validate, "999#1d20")      # a leitura aceita, o erro vem na hora de rolar
for conversa in ("3#d20 oi gente", "olá 3#d20", "3#", "#d20", "3#3", "d20 oi", "###d20", "3##d20"):
    assert P(conversa) is None, conversa                                                                      # conversa normal nunca rola
assert P("d20") == dice.PedidoDeDado("1d20", None, False) and P("d20+5") == dice.PedidoDeDado("1d20+5", None, False) and P("+d20+5 ataque") == dice.PedidoDeDado("1d20+5", "ataque", True)   # o que já existia segue igual
print("7. dados no chat OK")

print("\nTODOS OS TESTES DOS DADOS PASSARAM")
