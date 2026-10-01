"""Habilidades criadas pelos jogadores: a regra, sem Discord.

O jogador cria (nome, descrição e o efeito que quer). O mestre vê numa fila, ajusta e aprova, escolhendo o custo
(Mana, Estamina, Sanidade ou Vida) e a rolagem (dano ou cura, com dado e, se quiser, um atributo somado). Depois
disso o jogador usa com um botão: o custo é gasto da barra e o dado é rolado sozinho.
"""

from typing import NamedTuple

import db
import dice
import rules

MARCA = {"pendente": "⏳", "ajuste": "🔧", "aprovada": "✅", "recusada": "❌"}
FRASE = {
    "pendente": "aguardando o mestre",
    "ajuste": "o mestre pediu ajuste",
    "aprovada": "aprovada, pode usar",
    "recusada": "recusada",
}
TAMANHO_NOME = 40
TAMANHO_DESCRICAO = 400
TAMANHO_EFEITO = 300
TAMANHO_NOTA = 200
PODE_EDITAR = ("pendente", "ajuste", "recusada")   # o jogador só mexe no texto de quem ainda não foi aprovada


class Resultado(NamedTuple):
    ok: bool
    texto: str
    id: int | None = None


def limpar(texto: str) -> str:
    return " ".join((texto or "").split())


def _problema_no_texto(nome: str, descricao: str, efeito: str) -> str | None:
    if not nome:
        return "Dá um nome pra habilidade."
    if len(nome) > TAMANHO_NOME:
        return f"O nome passou de {TAMANHO_NOME} letras. Encurta."
    if not descricao:
        return "Escreve a descrição: o que é a habilidade e como ela funciona."
    if len(descricao) > TAMANHO_DESCRICAO:
        return f"A descrição passou de {TAMANHO_DESCRICAO} letras. Resume."
    if not efeito:
        return "Escreve o efeito que você quer: o que ela faz (dano, cura, custo...)."
    if len(efeito) > TAMANHO_EFEITO:
        return f"O efeito passou de {TAMANHO_EFEITO} letras. Resume."
    return None


def _nome_repetido(character_id: int, nome: str, ignorar_id: int | None = None) -> bool:
    return any(
        a["name"].casefold() == nome.casefold() and a["id"] != ignorar_id and a["status"] != "recusada"
        for a in db.list_abilities(character_id)
    )


def criar(character_id: int, nome: str, descricao: str, efeito: str) -> Resultado:
    nome, descricao, efeito = limpar(nome), limpar(descricao), limpar(efeito)
    erro = _problema_no_texto(nome, descricao, efeito)
    if erro:
        return Resultado(False, erro)
    if db.count_active_abilities(character_id) >= rules.MAX_CUSTOM_ABILITIES:
        return Resultado(False, f"Você já tem {rules.MAX_CUSTOM_ABILITIES} habilidades (sem contar as recusadas). Apaga uma pra criar outra.")
    if _nome_repetido(character_id, nome):
        return Resultado(False, f"Você já tem uma habilidade chamada **{nome}**.")
    novo = db.create_ability(character_id, nome, descricao, efeito)
    return Resultado(True, f"⏳ **{nome}** foi pra fila do mestre. Quando ele aprovar e definir o custo e o dano, ela aparece aqui pronta pra usar.", novo)


def editar(ability_id: int, nome: str, descricao: str, efeito: str) -> Resultado:
    ab = db.get_ability(ability_id)
    if ab is None:
        return Resultado(False, "Essa habilidade não existe mais.")
    if ab["status"] not in PODE_EDITAR:
        return Resultado(False, "Habilidade aprovada: só o mestre muda. Fala com ele se quiser ajustar.")
    nome, descricao, efeito = limpar(nome), limpar(descricao), limpar(efeito)
    erro = _problema_no_texto(nome, descricao, efeito)
    if erro:
        return Resultado(False, erro)
    if _nome_repetido(ab["character_id"], nome, ability_id):
        return Resultado(False, f"Você já tem uma habilidade chamada **{nome}**.")
    db.update_ability_text(ability_id, nome, descricao, efeito, back_to_pending=True)
    return Resultado(True, f"⏳ **{nome}** voltou pra fila do mestre.", ability_id)


def apagar(ability_id: int) -> Resultado:
    ab = db.get_ability(ability_id)
    if ab is None:
        return Resultado(False, "Essa habilidade já não existe.")
    if ab["status"] not in PODE_EDITAR:
        return Resultado(False, "Habilidade aprovada: só o mestre tira. Fala com ele.")
    db.delete_ability(ability_id)
    return Resultado(True, f"🗑 **{ab['name']}** foi apagada.")


# ---------------------------------------------------------------------------
# O que o mestre decide
# ---------------------------------------------------------------------------
def ler_dado(texto: str) -> tuple[str | None, str | None]:
    """O dado que o mestre digita (2d8, 1d6+2). Devolve (dado limpo, None), (None, None) se estiver vazio ou
    (None, erro)."""
    t = limpar(texto).replace(" ", "").lower()
    if not t:
        return None, None
    if "#" in t:
        return None, "Aqui o dado é um só, tipo 2d8 ou 1d6+2 (sem o #)."
    try:
        dice.validate(t)
    except dice.DiceError as e:
        return None, f"Dado inválido: escreve tipo 2d8 ou 1d6+2. {e}"
    return t, None


def decidir(ability_id: int, status: str, recurso: str | None, valor: int, tipo: str | None, dado: str | None,
            atributo: str | None, nota: str | None, mestre_id: str) -> Resultado:
    """O mestre aprova, pede ajuste ou recusa, e deixa gravado o custo e a rolagem."""
    ab = db.get_ability(ability_id)
    if ab is None:
        return Resultado(False, "Essa habilidade não existe mais.")
    nota = limpar(nota or "")[:TAMANHO_NOTA] or None
    if status == "ajuste" and not nota:
        return Resultado(False, "Escreve o que o jogador precisa ajustar.")
    if tipo and not dado:
        return Resultado(False, "Escolheu dano ou cura mas faltou o dado. Escolhe um dado no menu.")
    if dado and not tipo:
        tipo = "dano"
    if recurso and valor <= 0:
        recurso = None
    db.save_ability_decision(ability_id, status, recurso, valor if recurso else 0, tipo, dado, atributo, nota, mestre_id)
    nome = ab["name"]
    return Resultado(True, {
        "aprovada": f"✅ **{nome}** aprovada: o jogador já pode usar.",
        "ajuste": f"🔧 Pedi ajuste em **{nome}**: o jogador vê a sua nota.",
        "recusada": f"❌ **{nome}** recusada.",
        "pendente": f"⏳ **{nome}** salva (continua pendente).",
    }[status], ability_id)


def corrigir_texto(ability_id: int, nome: str, descricao: str, efeito: str) -> Resultado:
    """O mestre corrige o texto (não volta pra fila nem mexe no status)."""
    ab = db.get_ability(ability_id)
    if ab is None:
        return Resultado(False, "Essa habilidade não existe mais.")
    nome, descricao, efeito = limpar(nome), limpar(descricao), limpar(efeito)
    erro = _problema_no_texto(nome, descricao, efeito)
    if erro:
        return Resultado(False, erro)
    db.update_ability_text(ability_id, nome, descricao, efeito, back_to_pending=False)
    return Resultado(True, f"✏️ Texto de **{nome}** corrigido.", ability_id)


def ler_custo(texto: str) -> tuple[str | None, int, str | None]:
    """'mana 15' vira ('mana', 15, None). Vazio vira (None, 0, None). Erro vira (None, 0, texto do erro)."""
    t = limpar(texto).casefold()
    if not t or t in ("0", "nenhum", "sem custo"):
        return None, 0, None
    partes = t.split(" ")
    achado = next((k for k in rules.VITAL_KEYS if k == partes[0] or rules.VITAL_LABELS[k].casefold() == partes[0]), None)
    if achado is None or len(partes) != 2 or not partes[1].isdigit() or not 1 <= int(partes[1]) <= 999:
        return None, 0, "Custo inválido: escreve o recurso e o valor, tipo `mana 15` (recursos: vida, sanidade, mana, estamina)."
    return achado, int(partes[1]), None


def ler_atributo(texto: str) -> tuple[str | None, str | None]:
    """'força' vira 'forca'. Vazio vira (None, None). Erro vira (None, texto do erro)."""
    t = limpar(texto).casefold()
    if not t or t in ("nenhum", "sem atributo"):
        return None, None
    achado = next((a for a in rules.ATTRIBUTES if a == t or rules.ATTRIBUTE_LABELS[a].casefold() == t), None)
    if achado is None:
        return None, "Atributo inválido: escreve Força, Destreza, Vitalidade, Razão, Vontade ou Alma (ou deixa vazio)."
    return achado, None


def texto_do_custo(ab) -> str:
    if ab["cost_resource"] and ab["cost_amount"]:
        return f"{rules.VITAL_EMOJI[ab['cost_resource']]} {ab['cost_amount']} de {rules.VITAL_LABELS[ab['cost_resource']]}"
    return "sem custo"


def texto_da_rolagem(ab) -> str:
    if not ab["roll_dice"]:
        return "sem rolagem"
    rotulo = {"dano": "dano", "cura": "cura"}.get(ab["roll_kind"], "dano")
    extra = f" + {rules.ATTRIBUTE_LABELS[ab['roll_attribute']]}" if ab["roll_attribute"] else ""
    return f"{rotulo} {ab['roll_dice']}{extra}"


# ---------------------------------------------------------------------------
# Usar a habilidade
# ---------------------------------------------------------------------------
class Uso(NamedTuple):
    ok: bool
    erro: str | None = None
    custo: tuple | None = None       # (recurso, valor gasto, o que sobrou, o máximo)
    rolagem: object | None = None    # o RollResult do dado
    atributo: tuple | None = None    # (nome do atributo, valor somado)
    total: int | None = None


def usar(personagem, ab, recursos: dict | None) -> Uso:
    """Gasta o custo da barra e rola o dado. Se algo não der (não aprovada, sem recurso, sem classe), não gasta nada."""
    if ab["status"] != "aprovada":
        return Uso(False, "Essa habilidade ainda não foi aprovada pelo mestre.")
    recurso, valor = ab["cost_resource"], ab["cost_amount"]
    maximo = perdido = None
    if recurso and valor:
        if recursos is None:
            return Uso(False, "As barras dependem da classe, e este personagem ainda não tem. Escolhe a classe primeiro.")
        maximo = recursos[recurso]["total"]
        perdido = db.get_vitals_lost(personagem["id"])[recurso]
        atual = rules.vital_current(maximo, perdido)
        if atual < valor:
            return Uso(False, f"{rules.VITAL_LABELS[recurso]} insuficiente: você tem {atual} e a habilidade custa {valor}.")
    rolagem = None
    if ab["roll_dice"]:
        try:
            rolagem = dice.roll(ab["roll_dice"])
        except dice.DiceError:
            return Uso(False, "O dado dessa habilidade está inválido. Avisa o mestre.")
    custo = None
    if recurso and valor:
        novo_perdido = rules.vital_lost_after_change(maximo, perdido, -valor)
        db.set_vital_lost(personagem["id"], recurso, novo_perdido)
        custo = (recurso, valor, rules.vital_current(maximo, novo_perdido), maximo)
    atributo = total = None
    if rolagem is not None:
        total = rolagem.total
        if ab["roll_attribute"]:
            bonus = db.attributes_of(personagem)[ab["roll_attribute"]]
            atributo = (rules.ATTRIBUTE_LABELS[ab["roll_attribute"]], bonus)
            total += bonus
    return Uso(True, None, custo, rolagem, atributo, total)
