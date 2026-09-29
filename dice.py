"""Parsing e rolagem de dados no formato NdM+K (ex: 1d20, 2d6+3, 1d100-2), e a leitura de dados escritos
direto no chat (ex: d20+5, ou +d20+5 ataque com a espada)."""

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


def roll(notation: str) -> RollResult:
    """Rola uma notação de dado tipo '2d6+3'. Levanta DiceError se inválida."""
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

    rolls = [random.randint(1, sides) for _ in range(qty)]
    return RollResult(notation=notation, rolls=rolls, modifier=modifier, sides=sides)


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
    r"^\s*(?P<mais>\+)?\s*(?P<qtd>\d{0,3})\s*d\s*(?P<lados>\d{1,4})"
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
    notacao = f"{int(m['qtd'] or 1)}d{int(m['lados'])}" + "".join(
        f"{sinal}{int(numero)}" for sinal, numero in _MODIFICADOR.findall(m["mods"] or "")
    )
    return PedidoDeDado(notacao, motivo, bool(m["mais"]))
