"""Parsing e rolagem de dados no formato NdM+K (ex: 1d20, 2d6+3, 1d100-2)."""

import random
import re

DICE_PATTERN = re.compile(r"^\s*(\d*)d(\d+)\s*([+-]\s*\d+)?\s*$", re.IGNORECASE)


class DiceError(ValueError):
    """Erro ao interpretar uma notação de dado inválida."""


class RollResult:
    def __init__(self, notation: str, rolls: list[int], modifier: int):
        self.notation = notation
        self.rolls = rolls
        self.modifier = modifier

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
    modifier = int(mod_str.replace(" ", "")) if mod_str else 0

    if qty < 1 or qty > 100:
        raise DiceError("A quantidade de dados precisa ser entre 1 e 100.")
    if sides < 2 or sides > 1000:
        raise DiceError("O dado precisa ter entre 2 e 1000 lados.")

    rolls = [random.randint(1, sides) for _ in range(qty)]
    return RollResult(notation=notation, rolls=rolls, modifier=modifier)


# Tabela de raridade de magia já estabelecida no sistema (rolagem em 1d100).
MAGIC_RANK_TABLE = [
    (1, 45, "Comum"),
    (46, 75, "Raro"),
    (76, 95, "Super Raro"),
    (96, 99, "Lendário"),
    (100, 100, "Mítico"),
]

# Sorteio de Raça (rolagem em 1d100): 85% humano, 10% vampiro, 5% meio humano, meio vampiro.
RACE_TABLE = [
    (1, 85, "Humano"),
    (86, 95, "Vampiro"),
    (96, 100, "Meio humano, meio vampiro"),
]

MAGIC_RANKS = [name for _, _, name in MAGIC_RANK_TABLE]
RACES = [name for _, _, name in RACE_TABLE]


def _lookup(table: list[tuple[int, int, str]], d100_result: int) -> str:
    for low, high, name in table:
        if low <= d100_result <= high:
            return name
    raise DiceError(f"Resultado fora da faixa esperada de 1d100: {d100_result}")


def magic_rank_for(d100_result: int) -> str:
    return _lookup(MAGIC_RANK_TABLE, d100_result)


def race_for(d100_result: int) -> str:
    return _lookup(RACE_TABLE, d100_result)
