"""Regras do sistema que o bot precisa conhecer: classes, progressão de nível,
perícias especiais e cálculo de recursos. Tudo aqui segue o site e o documento do
Baptism of Blood; se a regra mudar lá, muda aqui também."""

# ---------------------------------------------------------------------------
# Progressão de personagem
# ---------------------------------------------------------------------------
START_LEVEL = 1
MAX_LEVEL = 10
SKILL_POINTS_PER_LEVEL = 2      # a cada nível ganho: +2 pontos de Perícia
LEVELS_PER_ATTRIBUTE = 2        # a cada 2 níveis: +1 ponto de Atributo e uma habilidade nova ou melhorada


def gains_for_level(level: int) -> dict[str, int]:
    """O que se ganha ao ALCANÇAR esse nível. O nível 1 é a ficha inicial e não ganha nada."""
    if level <= START_LEVEL:
        return {"pericia": 0, "atributo": 0, "habilidade": 0}
    par = level % LEVELS_PER_ATTRIBUTE == 0
    return {"pericia": SKILL_POINTS_PER_LEVEL, "atributo": int(par), "habilidade": int(par)}


def gains_between(old_level: int, new_level: int) -> dict[str, int]:
    """Soma dos ganhos de todos os níveis depois de old_level, até new_level inclusive."""
    total = {"pericia": 0, "atributo": 0, "habilidade": 0}
    for nivel in range(old_level + 1, new_level + 1):
        for chave, valor in gains_for_level(nivel).items():
            total[chave] += valor
    return total


def total_gains(level: int) -> dict[str, int]:
    return gains_between(START_LEVEL, level)


def _plural(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural


def describe_gains(g: dict[str, int]) -> str:
    partes = []
    if g["pericia"]:
        partes.append(f"+{g['pericia']} {_plural(g['pericia'], 'ponto', 'pontos')} de Perícia")
    if g["atributo"]:
        partes.append(f"+{g['atributo']} {_plural(g['atributo'], 'ponto', 'pontos')} de Atributo")
    if g["habilidade"]:
        partes.append(f"{g['habilidade']} {_plural(g['habilidade'], 'habilidade nova ou melhorada', 'habilidades novas ou melhoradas')}")
    return " · ".join(partes) if partes else "nada (ficha inicial)"


def level_line(level: int) -> str:
    """Uma linha da tabela de vantagens, sem marcação de 'nível atual'."""
    if level <= START_LEVEL:
        return f"**Nível {level}** · ficha inicial, feita na criação"
    g = gains_for_level(level)
    texto = f"**Nível {level}** · +{g['pericia']} perícia"
    if g["atributo"]:
        texto += " · +1 atributo · habilidade nova ou melhorada"
    if level == MAX_LEVEL:
        texto += " · **máximo**"
    return texto


def level_table_lines(current_level: int | None = None) -> list[str]:
    linhas = []
    for nivel in range(START_LEVEL, MAX_LEVEL + 1):
        marca = "▶️" if nivel == current_level else "▫️"
        linhas.append(f"{marca} {level_line(nivel)}")
    return linhas


def bar(value: int, maximum: int) -> str:
    value = max(0, min(value, maximum))
    return "▰" * value + "▱" * (maximum - value)


# ---------------------------------------------------------------------------
# Perícias especiais (grau/Rank de 1 a 10, concedido pelos mestres)
# ---------------------------------------------------------------------------
SPECIAL_SKILLS = ["Ritualismo", "Alquimia", "Forja", "Culinária", "Fé"]
MAX_SKILL_RANK = 10


# ---------------------------------------------------------------------------
# Estados sociais (o resultado do sorteio fica em dice.py)
# ---------------------------------------------------------------------------
ESTADO_LABELS = {
    "1º Estado": "1º Estado (Clero)",
    "2º Estado": "2º Estado (Nobreza)",
    "3º Estado": "3º Estado (Povo)",
}


# ---------------------------------------------------------------------------
# Classes e recursos
# ---------------------------------------------------------------------------
CLASS_NONE = "Nenhuma"

# Bônus de cada classe somado a Vida, Sanidade, Mana e Estamina.
CLASSES = {
    "Caçador":         {"vida": 35, "sanidade": 15, "mana": 5,  "estamina": 20},
    "Feiticeiros":     {"vida": 20, "sanidade": 20, "mana": 25, "estamina": 5},
    "Ladrão":          {"vida": 25, "sanidade": 20, "mana": 10, "estamina": 15},
    "Mestre de Forja": {"vida": 15, "sanidade": 35, "mana": 15, "estamina": 20},
    "Mundano":         {"vida": 10, "sanidade": 15, "mana": 10, "estamina": 10},
    "Sábio":           {"vida": 15, "sanidade": 35, "mana": 20, "estamina": 5},
}
CLASS_CHOICES = [CLASS_NONE, *CLASSES]
_SEM_BONUS = {"vida": 0, "sanidade": 0, "mana": 0, "estamina": 0}


def calculate_resources(*, vitalidade: int, forca: int, vontade: int, alma: int,
                        classe: str = CLASS_NONE) -> dict[str, dict[str, int]]:
    """Vida = Vitalidade x5, Sanidade = Vontade x5, Mana = (Alma + Vontade) x3,
    Estamina = (Força + Vitalidade) x3, sempre mais o bônus da classe.
    Destreza e Razão não entram em nenhuma dessas contas."""
    if classe != CLASS_NONE and classe not in CLASSES:
        raise ValueError(f"Classe desconhecida: {classe}")
    bonus = _SEM_BONUS if classe == CLASS_NONE else CLASSES[classe]
    base = {
        "vida": vitalidade * 5,
        "sanidade": vontade * 5,
        "mana": (alma + vontade) * 3,
        "estamina": (forca + vitalidade) * 3,
    }
    return {
        nome: {"base": base[nome], "bonus": bonus[nome], "total": base[nome] + bonus[nome]}
        for nome in base
    }
