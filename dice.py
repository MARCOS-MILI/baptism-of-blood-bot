"""Parsing e rolagem de dados no formato NdM+K (ex: 1d20, 2d6+3, 1d100-2), o N#dado (3#d20+5 rola o
d20+5 três vezes, cada uma separada), os efeitos de sorte que o mestre põe num personagem, e a leitura de
dados escritos direto no chat (ex: d20+5, ou +d20+5 ataque com a espada)."""

import random
import re
from typing import NamedTuple

# Aceita vários modificadores seguidos (1d20+5-1 vale +4).
DICE_PATTERN = re.compile(r"^\s*(\d*)d(\d+)\s*((?:[+-]\s*\d{1,4}\s*)*)$", re.IGNORECASE)
_MODIFICADOR = re.compile(r"([+-])\s*(\d+)")


class DiceError(ValueError):
    """Erro ao interpretar uma notação de dado inválida."""


class RollResult:
    def __init__(self, notation: str, rolls: list[int], modifier: int, sides: int | None = None):
        self.notation = notation
        self.rolls = rolls
        self.modifier = modifier
        self.sides = sides  # quantos lados tinha o dado (None se não se sabe)

    @property
    def total(self) -> int:
        return sum(self.rolls) + self.modifier

    def describe(self) -> str:
        parts = " + ".join(str(r) for r in self.rolls)
        if self.modifier > 0:
            parts += f" + {self.modifier}"
        elif self.modifier < 0:
            parts += f" - {abs(self.modifier)}"
        return parts


def _ler(notation: str) -> tuple[int, int, int]:
    """Lê uma notação de dado (sem rolar): (quantidade, lados, modificador). Levanta DiceError se inválida."""
    match = DICE_PATTERN.match(notation)
    if not match:
        raise DiceError(f"Notação de dado inválida: '{notation}'. Use algo como 1d20 ou 2d6+3.")

    qty_str, sides_str, mod_str = match.groups()
    qty = int(qty_str) if qty_str else 1
    sides = int(sides_str)
    modifier = sum(int(f"{sinal}{numero}") for sinal, numero in _MODIFICADOR.findall(mod_str or ""))

    if qty < 1 or qty > 100:
        raise DiceError("A quantidade de dados precisa ser entre 1 e 100.")
    if sides < 2 or sides > 1000:
        raise DiceError("O dado precisa ter entre 2 e 1000 lados.")
    return qty, sides, modifier


def roll(notation: str) -> RollResult:
    """Rola uma notação de dado tipo '2d6+3'. Levanta DiceError se inválida."""
    qty, sides, modifier = _ler(notation)
    rolls = [random.randint(1, sides) for _ in range(qty)]
    return RollResult(notation=notation, rolls=rolls, modifier=modifier, sides=sides)


# ---------------------------------------------------------------------------
# N#dado: várias rolagens separadas (3#d20+5 = três vezes d20+5, cada uma com o seu resultado)
# ---------------------------------------------------------------------------
MAX_REPETICOES = 10
_REPETICAO = re.compile(r"^\s*(\d{1,3})\s*#\s*(\S.*?)\s*$")


def split_repeticao(notation: str) -> tuple[int, str]:
    """'3#d20+5' vira (3, 'd20+5'). Sem o '#', vira (1, a notação inteira)."""
    m = _REPETICAO.match(notation)
    if not m:
        return 1, notation
    vezes = int(m.group(1))
    if vezes < 1 or vezes > MAX_REPETICOES:
        raise DiceError(f"A repetição precisa ser de 1 a {MAX_REPETICOES} (por exemplo 3#d20+5).")
    return vezes, m.group(2)


# ---------------------------------------------------------------------------
# Sorte do mestre: efeitos que mexem no d20 de um personagem
# ---------------------------------------------------------------------------
EFEITOS = ("vantagem", "desvantagem", "bonus", "penalidade", "minimo", "maximo", "fixo")
EFEITOS_COM_VALOR = ("bonus", "penalidade", "minimo", "maximo", "fixo")
EFEITO_NOME = {
    "vantagem": "vantagem",
    "desvantagem": "desvantagem",
    "bonus": "bônus",
    "penalidade": "penalidade",
    "minimo": "dado mínimo",
    "maximo": "dado máximo",
    "fixo": "dado fixo",
}


class EfeitoDeSorte(NamedTuple):
    id: int
    tipo: str
    valor: int | None
    usos: int          # quantas rolagens ainda pode afetar
    discreto: bool     # se sim, o cartão da rolagem não mostra a marca de sorte
    origem: str = "mestre"   # 'jogador' quando é o modo vantagem/desvantagem que o próprio jogador escolheu


def descrever_efeito(tipo: str, valor: int | None) -> str:
    """Como o efeito aparece escrito: 'vantagem', 'bônus +3', 'dado mínimo 10'."""
    if tipo in ("bonus", "penalidade"):
        return f"{EFEITO_NOME[tipo]} {'+' if tipo == 'bonus' else '-'}{valor}"
    return f"{EFEITO_NOME[tipo]} {valor}" if valor is not None else EFEITO_NOME[tipo]


def _d20_simples(r: "RollResult") -> bool:
    return r.sides == 20 and len(r.rolls) == 1


def aplicar_sorte(r: "RollResult", efeitos: list[EfeitoDeSorte],
                  restantes: dict[int, int]) -> tuple["RollResult", list[str], list[int]]:
    """Aplica os efeitos ao d20 já rolado. Só vale pra um d20 sozinho (1d20, com ou sem modificador); qualquer
    outro dado passa direto. Cada efeito gasta um uso por rolagem que afeta ('restantes' é o que sobra de
    cada um). Devolve (o resultado novo, as marcas que o cartão pode mostrar, os ids dos efeitos usados).

    Ordem: vantagem e desvantagem (uma anula a outra); depois dado fixo, ou mínimo e máximo; por fim bônus e
    penalidade, que somam ao total."""
    if not efeitos or not _d20_simples(r):
        return r, [], []
    usados: list[int] = []
    marcas: list[str] = []

    def ativo(tipo):
        return next((e for e in efeitos if e.tipo == tipo and restantes.get(e.id, 0) > 0), None)

    def gastar(e, marca=None):
        restantes[e.id] -= 1
        usados.append(e.id)
        if marca and not e.discreto:
            marcas.append(marca)

    natural, modificador = r.rolls[0], r.modifier
    vant, desv = ativo("vantagem"), ativo("desvantagem")
    if vant and desv:
        gastar(vant)
        gastar(desv)
        if not (vant.discreto and desv.discreto):
            marcas.append("vantagem e desvantagem se anularam")
    elif vant or desv:
        e = vant or desv
        outro = roll("1d20").rolls[0]
        novo = max(natural, outro) if vant else min(natural, outro)
        gastar(e, f"{'modo ' if e.origem == 'jogador' else ''}{EFEITO_NOME[e.tipo]} ({natural} e {outro})")
        natural = novo

    fixo = ativo("fixo")
    if fixo:
        gastar(fixo, f"dado fixo em {fixo.valor}")
        natural = fixo.valor
    else:
        minimo, maximo = ativo("minimo"), ativo("maximo")
        if minimo:
            gastar(minimo, f"dado mínimo {minimo.valor}")
            natural = max(natural, minimo.valor)
        if maximo:
            gastar(maximo, f"dado máximo {maximo.valor}")
            natural = min(natural, maximo.valor)

    for tipo, sinal in (("bonus", 1), ("penalidade", -1)):
        e = ativo(tipo)
        if e:
            gastar(e, f"{'+' if sinal > 0 else '-'}{e.valor}")
            modificador += sinal * e.valor
    return RollResult(r.notation, [natural], modificador, r.sides), marcas, usados


def validate(notation: str) -> None:
    """Confere se a notação vale (inclusive o N#dado), sem rolar nada. Levanta DiceError se não valer."""
    _, expr = split_repeticao(notation)
    _ler(expr)


def roll_many(notation: str, efeitos: list[EfeitoDeSorte] | None = None
              ) -> tuple[list["RollResult"], list[list[str]], list[int]]:
    """Rola a notação, que pode ser um N#dado. Devolve, uma lista com cada rolagem, as marcas de sorte de
    cada uma e os ids dos efeitos gastos (um id por uso). Levanta DiceError se a notação for inválida."""
    vezes, expr = split_repeticao(notation)
    restantes = {e.id: e.usos for e in (efeitos or [])}
    resultados, marcas, usados = [], [], []
    for _ in range(vezes):
        novo, m, u = aplicar_sorte(roll(expr), efeitos or [], restantes)
        resultados.append(novo)
        marcas.append(m)
        usados += u
    return resultados, marcas, usados


# Tabela de raridade de magia já estabelecida no sistema (rolagem em 1d100).
MAGIC_RANK_TABLE = [
    (1, 45, "Comum"),
    (46, 75, "Raro"),
    (76, 95, "Super Raro"),
    (96, 99, "Lendário"),
    (100, 100, "Mítico"),
]

# Sorteio de Raça (rolagem em 1d100): 85% humano, 10% vampiro, 5% Dhampir (meio humano, meio vampiro).
RACE_TABLE = [
    (1, 85, "Humano"),
    (86, 95, "Vampiro"),
    (96, 100, "Dhampir"),
]

# Classe social, em 1d100. Um 100 não vira Estado nenhum: o mestre é quem decide.
SOCIAL_CLASS_MASTER = "Aguardando o mestre"
SOCIAL_CLASS_TABLE = [
    (1, 80, "3º Estado"),
    (81, 91, "2º Estado"),
    (92, 99, "1º Estado"),
    (100, 100, SOCIAL_CLASS_MASTER),
]

# Quem cai no 1º Estado rola outro 1d100: de 50 pra cima é Alto Clero, abaixo disso Baixo Clero.
CLERGY_TABLE = [
    (1, 49, "Baixo Clero"),
    (50, 100, "Alto Clero"),
]

MAGIC_RANKS = [name for _, _, name in MAGIC_RANK_TABLE]
RACES = [name for _, _, name in RACE_TABLE]
SOCIAL_CLASSES = ["1º Estado", "2º Estado", "3º Estado"]
CLERGY_LEVELS = ["Alto Clero", "Baixo Clero"]


def _lookup(table: list[tuple[int, int, str]], d100_result: int) -> str:
    for low, high, name in table:
        if low <= d100_result <= high:
            return name
    raise DiceError(f"Resultado fora da faixa esperada de 1d100: {d100_result}")


def magic_rank_for(d100_result: int) -> str:
    return _lookup(MAGIC_RANK_TABLE, d100_result)


def race_for(d100_result: int) -> str:
    return _lookup(RACE_TABLE, d100_result)


def social_class_for(d100_result: int) -> str:
    """Devolve '1º Estado', '2º Estado', '3º Estado' ou SOCIAL_CLASS_MASTER (o 100)."""
    return _lookup(SOCIAL_CLASS_TABLE, d100_result)


def clergy_for(d100_result: int) -> str:
    return _lookup(CLERGY_TABLE, d100_result)


# ---------------------------------------------------------------------------
# Dados escritos direto no chat, sem barra
# ---------------------------------------------------------------------------
class PedidoDeDado(NamedTuple):
    notacao: str          # já normalizada: "d20+5" vira "1d20+5"
    motivo: str | None    # o texto depois do dado, só quando a mensagem começa com "+"
    explicito: bool       # a mensagem começou com "+": é um pedido claro, então erro também merece resposta


_TEXTO = re.compile(
    r"^\s*(?P<mais>\+)?\s*(?:(?P<rep>\d{1,3})\s*#\s*)?(?P<qtd>\d{0,3})\s*d\s*(?P<lados>\d{1,4})"
    r"(?P<mods>(?:\s*[+-]\s*\d{1,4})*)"
    r"(?:\s+(?P<resto>\S.*?))?\s*$",
    re.IGNORECASE | re.DOTALL,
)


def parse_texto(conteudo: str | None) -> PedidoDeDado | None:
    """Lê uma mensagem de chat e devolve o dado pedido, ou None se a mensagem não é um dado.

    Sem o "+" na frente, a mensagem inteira tem que ser só o dado (d20, 1d20+5, 2d6 - 1), pra uma conversa
    normal nunca disparar rolagem. Com o "+" na frente, o que vem depois do dado vira o motivo
    (+d20+5 ataque com a espada). O dado em si é validado só na hora de rolar."""
    if not conteudo:
        return None
    m = _TEXTO.match(conteudo)
    if not m:
        return None
    motivo = m["resto"].strip() if m["resto"] else None
    if motivo and not m["mais"]:
        return None
    notacao = (f"{int(m['rep'])}#" if m["rep"] else "") + f"{int(m['qtd'] or 1)}d{int(m['lados'])}" + "".join(
        f"{sinal}{int(numero)}" for sinal, numero in _MODIFICADOR.findall(m["mods"] or "")
    )
    return PedidoDeDado(notacao, motivo, bool(m["mais"]))
