"""NPCs e criaturas dos mestres: a lógica, sem Discord.

Um NPC é uma ficha automática só dos mestres: nível de 1 a 10, atributos sem limite, até 3 classes (o bônus de cada
uma soma), perícias com pontos livres, bônus manual de recursos e barras de Vida, Sanidade, Mana e Estamina que o
mestre sobe e desce à vontade.
"""

import re
import unicodedata

import db
import dice
import rules


def _norm(texto: str) -> str:
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return sem_acento.casefold().strip()


_ATRIBUTOS = {_norm(rotulo): chave for chave, rotulo in rules.ATTRIBUTE_LABELS.items()} | {c: c for c in rules.ATTRIBUTES}
_PERICIAS = {_norm(p): p for p in rules.SKILLS}
_CLASSES = {_norm(c): c for c in rules.CLASSES} | {"feiticeiro": "Feiticeiros", "forja": "Mestre de Forja", "ferreiro": "Mestre de Forja"}
_PAR = re.compile(r"([^\W\d_]+)\s*[:=]?\s*(-?\d+)")


def _ler_pares(texto: str, dicionario: dict, nome_do_que: str, lista_bonita: str) -> tuple[dict | None, str | None]:
    """'Força 5, Destreza 3' vira {'forca': 5, 'destreza': 3}. Qualquer coisa que não seja par vira erro."""
    texto = texto or ""
    achados = {}
    ultimo = 0
    resto = []
    for m in _PAR.finditer(texto):
        resto.append(texto[ultimo:m.start()])
        ultimo = m.end()
        chave = dicionario.get(_norm(m.group(1)))
        if chave is None:
            return None, f"Não conheço {nome_do_que} \"{m.group(1)}\". Os que existem: {lista_bonita}."
        achados[chave] = int(m.group(2))
    resto.append(texto[ultimo:])
    if "".join(resto).strip(" ,;.\n\t") != "":
        return None, f"Não entendi \"{''.join(resto).strip(' ,;.')[:40]}\". Escreve assim: Força 5, Destreza 3."
    return achados, None


def ler_atributos(texto: str, atuais: dict[str, int]) -> tuple[dict[str, int] | None, str | None]:
    """Só muda o que foi escrito; o resto fica como estava. Cada atributo vai de 0 a NPC_MAX_ATTRIBUTE."""
    pares, erro = _ler_pares(texto, _ATRIBUTOS, "o atributo", ", ".join(rules.ATTRIBUTE_LABELS.values()))
    if erro:
        return None, erro
    if not pares:
        return None, "Escreve assim: Força 5, Destreza 3."
    if any(not 0 <= v <= rules.NPC_MAX_ATTRIBUTE for v in pares.values()):
        return None, f"Atributo vai de 0 a {rules.NPC_MAX_ATTRIBUTE}."
    return {**atuais, **pares}, None


def ler_pericias(texto: str) -> tuple[dict[str, int] | None, str | None]:
    """A lista completa de perícias do NPC (o que não for escrito sai). Vazio = sem perícias. Pontos de 0 a NPC_MAX_SKILL."""
    if not (texto or "").strip():
        return {}, None
    pares, erro = _ler_pares(texto, _PERICIAS, "a perícia", ", ".join(rules.SKILLS))
    if erro:
        return None, erro
    if any(not 0 <= v <= rules.NPC_MAX_SKILL for v in pares.values()):
        return None, f"Os pontos de perícia vão de 0 a {rules.NPC_MAX_SKILL}."
    return {p: v for p, v in pares.items() if v > 0}, None


def ler_classes(texto: str) -> tuple[list[str] | None, str | None]:
    """'Mercenário, Caçador' vira a lista (até 3, sem repetir). Vazio = sem classe."""
    pedacos = [p for p in re.split(r"[,;/\n]| e ", texto or "") if p.strip()]
    achadas = []
    for pedaco in pedacos:
        classe = _CLASSES.get(_norm(pedaco))
        if classe is None:
            return None, f"Não conheço a classe \"{pedaco.strip()}\". As que existem: {', '.join(rules.CLASSES)}."
        if classe not in achadas:
            achadas.append(classe)
    if len(achadas) > rules.NPC_MAX_CLASSES:
        return None, f"No máximo {rules.NPC_MAX_CLASSES} classes por NPC."
    return achadas, None


_MODELOS = {_norm(m): m for m in rules.NPC_TEMPLATES}


def achar_modelo(texto: str) -> tuple[str | None, str | None]:
    """'soldado' vira 'Soldado'. Vazio vale o Soldado. Modelo que não existe vira erro com a lista."""
    t = _norm(texto or "")
    if not t:
        return "Soldado", None
    if t in _MODELOS:
        return _MODELOS[t], None
    return None, f"Não existe o modelo \"{texto.strip()}\". Os modelos: {', '.join(rules.NPC_TEMPLATES)}."


def ler_inteiro(texto: str, minimo: int, maximo: int, rotulo: str) -> tuple[int | None, str | None]:
    t = (texto or "").strip().replace(" ", "")
    if not re.fullmatch(r"[+-]?\d+", t):
        return None, f"{rotulo}: escreve só um número, tipo 12 ou -5."
    valor = int(t)
    if not minimo <= valor <= maximo:
        return None, f"{rotulo} vai de {minimo} a {maximo}."
    return valor, None


# ---------------------------------------------------------------------------
# A ficha
# ---------------------------------------------------------------------------
def classes_de(npc) -> list[str]:
    return [c for c in npc["classes"].split(",") if c]


def atributos_de(npc) -> dict[str, int]:
    return {a: npc[a] for a in rules.ATTRIBUTES}


def bonus_de(npc) -> dict[str, int]:
    return {k: npc[f"bonus_{k}"] for k in rules.VITAL_KEYS}


def recursos(npc) -> dict[str, dict[str, int]]:
    return rules.npc_resources(atributos_de(npc), npc["level"], classes_de(npc), bonus_de(npc))


def criar_do_modelo(mestre_id: str, nome: str, modelo: str, tipo: str = "npc", especie: str = "") -> int:
    m = rules.NPC_TEMPLATES[modelo]
    return db.create_npc(mestre_id, nome, tipo, m["level"], dict(m["attributes"]), list(m["classes"]), especie, m["notes"], dict(m["skills"]))


def resumo(npc_id: int) -> dict:
    """Tudo o que a tela da ficha precisa de um NPC."""
    npc = db.get_npc(npc_id)
    return {"npc": npc, "recursos": recursos(npc), "perdidos": db.get_npc_lost(npc_id), "pericias": db.get_npc_skills(npc_id)}


# ---------------------------------------------------------------------------
# Vida e os outros recursos
# ---------------------------------------------------------------------------
def ajustar(npc_id: int, chave: str, delta: int) -> int:
    """Soma delta ao valor atual (negativo = dano) sem passar do máximo nem de 0. Devolve o valor atual novo."""
    npc = db.get_npc(npc_id)
    maximo = recursos(npc)[chave]["total"]
    novo_perdido = rules.vital_lost_after_change(maximo, npc[f"lost_{chave}"], delta)
    db.set_npc_lost(npc_id, chave, novo_perdido)
    return rules.vital_current(maximo, novo_perdido)


def definir(npc_id: int, chave: str, valor: int) -> int:
    npc = db.get_npc(npc_id)
    maximo = recursos(npc)[chave]["total"]
    db.set_npc_lost(npc_id, chave, rules.vital_lost_for_value(maximo, valor))
    return max(0, min(maximo, valor))


def restaurar(npc_id: int) -> None:
    db.reset_npc_lost(npc_id)


# ---------------------------------------------------------------------------
# Testes de perícia
# ---------------------------------------------------------------------------
def modificador(npc, pericias: dict[str, int], pericia: str, atributo: str | None = None) -> tuple[int, str]:
    """O bônus de um teste: o atributo (o padrão da perícia, ou o escolhido) mais os pontos da perícia."""
    atributo = atributo or rules.SKILL_DEFAULT_ATTRIBUTE[pericia]
    return npc[atributo] + pericias.get(pericia, 0), atributo


def lancar(npc, pericias: dict[str, int], pericia: str, modo: str = "normal", atributo: str | None = None):
    """Rola 1d20 + atributo + perícia pelo NPC. Devolve (notação, resultados, marcas, motivo). Não grava histórico."""
    bonus, usado = modificador(npc, pericias, pericia, atributo)
    notacao = f"1d20{bonus:+d}" if bonus else "1d20"
    extras = [dice.EfeitoDeSorte(-1, modo, None, 1, False, "jogador")] if modo in ("vantagem", "desvantagem") else []
    resultados, marcas, _ = dice.roll_many(notacao, extras)
    return notacao, resultados, marcas, f"{pericia} ({rules.ATTRIBUTE_LABELS[usado]})"
