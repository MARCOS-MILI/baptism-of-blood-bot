"""Regras do sistema que o bot precisa conhecer: XP e níveis, classes, perícias
especiais e cálculo de recursos. Tudo aqui segue o site e o documento do
Baptism of Blood; se a regra mudar lá, muda aqui também."""

# ---------------------------------------------------------------------------
# XP e níveis
# ---------------------------------------------------------------------------
START_LEVEL = 1
MAX_LEVEL = 10
XP_STEP = 1000                  # pra sair do nível N o personagem precisa de N x 1000 XP
SKILL_POINTS_PER_LEVEL = 2      # a cada nível ganho: +2 pontos de Perícia
LEVELS_PER_ATTRIBUTE = 2        # a cada 2 níveis: +1 ponto de Atributo e uma habilidade nova ou melhorada

# Quem tem sangue de vampiro ganha +1 ponto de Disciplina a cada 2 níveis.
VAMPIRIC_RACES = ("Vampiro", "Dhampir")
# Pontos de Disciplina na criação (o Dhampir começa com menos que o vampiro).
INITIAL_DISCIPLINE_POINTS = {"Vampiro": 4, "Dhampir": 3}


def xp_to_next(level: int) -> int | None:
    """XP que o nível pede pra passar pro próximo. No nível máximo não tem próximo."""
    if level >= MAX_LEVEL:
        return None
    return level * XP_STEP


def xp_at_level_start(level: int) -> int:
    """XP total acumulado que marca a chegada nesse nível (nível 1 = 0, nível 2 = 1.000,
    nível 3 = 3.000 ... nível 10 = 45.000)."""
    level = max(START_LEVEL, min(level, MAX_LEVEL))
    return XP_STEP * (level - 1) * level // 2


def level_for_xp(xp: int) -> int:
    xp = max(0, xp)
    nivel = START_LEVEL
    for n in range(START_LEVEL + 1, MAX_LEVEL + 1):
        if xp >= xp_at_level_start(n):
            nivel = n
    return nivel


def xp_progress(xp: int) -> tuple[int, int, int | None]:
    """(nível, XP dentro do nível, XP que o nível pede). No nível máximo o último vem None."""
    nivel = level_for_xp(xp)
    return nivel, xp - xp_at_level_start(nivel), xp_to_next(nivel)


def fmt_xp(n: int) -> str:
    """12300 vira '12.300'."""
    return f"{n:,}".replace(",", ".")


def xp_bar(inside: int, needed: int, size: int = 10) -> str:
    cheios = 0 if needed <= 0 else max(0, min(size, inside * size // needed))
    return "▰" * cheios + "▱" * (size - cheios)


def bar(value: int, maximum: int) -> str:
    value = max(0, min(value, maximum))
    return "▰" * value + "▱" * (maximum - value)


# ---------------------------------------------------------------------------
# Ganhos de cada nível
# ---------------------------------------------------------------------------

def gains_for_level(level: int, race: str | None = None) -> dict[str, int]:
    """O que se ganha ao ALCANÇAR esse nível. O nível 1 é a ficha inicial e não ganha nada."""
    if level <= START_LEVEL:
        return {"pericia": 0, "atributo": 0, "habilidade": 0, "disciplina": 0}
    par = level % LEVELS_PER_ATTRIBUTE == 0
    return {
        "pericia": SKILL_POINTS_PER_LEVEL,
        "atributo": int(par),
        "habilidade": int(par),
        "disciplina": int(par and race in VAMPIRIC_RACES),
    }


def gains_between(old_level: int, new_level: int, race: str | None = None) -> dict[str, int]:
    """Soma dos ganhos de todos os níveis depois de old_level, até new_level inclusive."""
    total = {"pericia": 0, "atributo": 0, "habilidade": 0, "disciplina": 0}
    for nivel in range(old_level + 1, new_level + 1):
        for chave, valor in gains_for_level(nivel, race).items():
            total[chave] += valor
    return total


def total_gains(level: int, race: str | None = None) -> dict[str, int]:
    return gains_between(START_LEVEL, level, race)


def _plural(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural


def describe_gains(g: dict[str, int]) -> str:
    partes = []
    if g.get("pericia"):
        partes.append(f"+{g['pericia']} {_plural(g['pericia'], 'ponto', 'pontos')} de Perícia")
    if g.get("atributo"):
        partes.append(f"+{g['atributo']} {_plural(g['atributo'], 'ponto', 'pontos')} de Atributo")
    if g.get("habilidade"):
        partes.append(
            f"{g['habilidade']} {_plural(g['habilidade'], 'habilidade nova ou melhorada', 'habilidades novas ou melhoradas')}"
        )
    if g.get("disciplina"):
        partes.append(f"+{g['disciplina']} {_plural(g['disciplina'], 'ponto', 'pontos')} de Disciplina")
    return " · ".join(partes) if partes else "nada (ficha inicial)"


def level_line(level: int, race: str | None = None) -> str:
    """Uma linha da tabela de vantagens, sem marcação de 'nível atual'."""
    if level <= START_LEVEL:
        extra = ""
        if race in INITIAL_DISCIPLINE_POINTS:
            extra = f" (com {INITIAL_DISCIPLINE_POINTS[race]} pontos de Disciplina)"
        return f"**Nível {level}** · 0 XP · ficha inicial, feita na criação{extra}"
    g = gains_for_level(level, race)
    texto = f"**Nível {level}** · {fmt_xp(xp_at_level_start(level))} XP · +{g['pericia']} perícia"
    if g["atributo"]:
        texto += " · +1 atributo · habilidade nova ou melhorada"
    if g["disciplina"]:
        texto += " · +1 disciplina"
    if level == MAX_LEVEL:
        texto += " · **máximo**"
    return texto


def level_table_lines(current_level: int | None = None, race: str | None = None) -> list[str]:
    linhas = []
    for nivel in range(START_LEVEL, MAX_LEVEL + 1):
        marca = "▶️" if nivel == current_level else "▫️"
        linhas.append(f"{marca} {level_line(nivel, race)}")
    return linhas


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

# Vantagem nas perícias de cada classe.
CLASS_SKILLS = {
    "Caçador": "Religião e Luta ou Pontaria",
    "Feiticeiros": "Investigação e Ocultismo",
    "Ladrão": "Furtividade e Enganação",
    "Mestre de Forja": "Ocultismo e Tática",
    "Mundano": "duas à sua escolha",
    "Sábio": "Ciências e Investigação",
}
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


# ---------------------------------------------------------------------------
# Atributos
# ---------------------------------------------------------------------------
ATTRIBUTES = ("forca", "destreza", "vitalidade", "razao", "vontade", "alma")
ATTRIBUTE_LABELS = {
    "forca": "Força", "destreza": "Destreza", "vitalidade": "Vitalidade",
    "razao": "Razão", "vontade": "Vontade", "alma": "Alma",
}
CREATION_ATTRIBUTE_POINTS = 6   # pontos pra distribuir nos 6 atributos na criação

# Limite de cada atributo na criação, por raça. Atributo que não aparece aqui não tem limite.
# O Dhampir fica de fora: os limites dele ainda não foram definidos (Em Aberto no site).
CREATION_LIMITS = {
    "Humano": {"forca": 3, "destreza": 3, "vitalidade": 3, "razao": 6},
    "Vampiro": {"forca": 5, "destreza": 5, "vitalidade": 5},
}


def attribute_points_from_levels(level: int) -> int:
    """Pontos de Atributo que vieram de nível: +1 a cada 2 níveis (2, 4, 6, 8 e 10)."""
    return max(0, min(level, MAX_LEVEL)) // LEVELS_PER_ATTRIBUTE


def attribute_points_total(level: int) -> int:
    """Pontos de Atributo que o personagem pode ter no total nesse nível (criação mais níveis)."""
    return CREATION_ATTRIBUTE_POINTS + attribute_points_from_levels(level)


def validate_attributes(values: dict[str, int], level: int, race: str | None) -> list[str]:
    """Confere a distribuição de atributos. Devolve a lista de problemas (vazia se está tudo certo).
    1) o total não pode passar dos pontos que o nível dá;
    2) os limites de criação da raça só podem ser ultrapassados com pontos que vieram de nível."""
    erros = []
    total = sum(values.get(a, 0) for a in ATTRIBUTES)
    disponiveis = attribute_points_total(level)
    if total > disponiveis:
        erros.append(
            f"Você distribuiu {total} pontos de atributo, mas no nível {level} o total é {disponiveis}."
        )
    limites = CREATION_LIMITS.get(race or "", {})
    excesso = sum(max(0, values.get(a, 0) - limite) for a, limite in limites.items())
    de_nivel = attribute_points_from_levels(level)
    if excesso > de_nivel:
        lista = ", ".join(f"{ATTRIBUTE_LABELS[a]} {limite}" for a, limite in limites.items())
        erros.append(
            f"O limite de criação de {race} é: {lista}. Só os pontos que vieram de nível podem passar "
            f"disso (você tem {de_nivel}) e essa distribuição passa {excesso}."
        )
    return erros


def describe_attributes(values: dict[str, int]) -> str:
    return " · ".join(f"{ATTRIBUTE_LABELS[a]} {values.get(a, 0)}" for a in ATTRIBUTES)
