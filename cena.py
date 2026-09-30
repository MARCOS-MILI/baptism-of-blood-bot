"""A lógica das cenas (iniciativa, intenções e a vez de cada um) e os quadros que o bot mostra.

Uma cena vive num canal. Os jogadores entram com a iniciativa (1d20 + Destreza, o que o site define) e mandam
uma intenção por rodada, que só o mestre lê. O quadro público mostra a ordem e se cada um já tem intenção
permitida, mas NUNCA o texto das intenções (pode ter ação em segredo).

Aqui só tem regra e texto. Mandar e editar mensagens no Discord é com o escudo.py.
"""

import re
import sqlite3
from typing import NamedTuple

import discord

import db
import dice

TAMANHO_MAX_INTENCAO = 200
TAMANHO_MAX_NOME = 40
TAMANHO_MAX_MOTIVO = 150

# status da intenção -> ícone. None é "ainda não mandou".
ICONES = {None: "⏳", "pendente": "📝", "permitida": "✅", "negada": "❌"}
LEGENDA = "⏳ sem intenção · 📝 aguardando o mestre · ✅ permitida · ❌ negada"
_FRASE_DO_STATUS = {
    None: "⏳ sem intenção",
    "pendente": "📝 intenção aguardando o mestre",
    "permitida": "✅ intenção permitida",
    "negada": "❌ intenção negada",
}
COR_QUADRO = 0x3A6EA5
COR_ESCUDO = 0x8B6F2E


class Resultado(NamedTuple):
    ok: bool
    texto: str
    mudou: bool = False   # mudou algo que o quadro público mostra?


def _uma_linha(texto: str) -> str:
    return " ".join(texto.split())


def _cortar(texto: str, tamanho: int) -> str:
    return texto if len(texto) <= tamanho else texto[: tamanho - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# Iniciativa
# ---------------------------------------------------------------------------
def rolar_iniciativa(personagem) -> tuple[int, str, list[int]]:
    """1d20 + Destreza. Quem tem Celeridade (grau 1 ou mais) rola com vantagem: dois d20, fica o maior.
    Devolve (total, como saiu, os dados rolados)."""
    destreza = db.attributes_of(personagem)["destreza"]
    com_vantagem = db.get_disciplines(personagem["id"]).get("Celeridade", 0) >= 1
    if com_vantagem:
        a, b = dice.roll("1d20").total, dice.roll("1d20").total
        dado = max(a, b)
        como = f"vantagem da Celeridade: {a} e {b}, fica o {dado}"
        rolados = [a, b]
    else:
        dado = dice.roll("1d20").total
        como = f"1d20 = {dado}"
        rolados = [dado]
    return dado + destreza, f"{como} + Destreza {destreza}", rolados


def entrar_na_cena(cena, personagem, user_id: str, username: str, guild_id: str | None) -> Resultado:
    """Põe o personagem na iniciativa. Uma vez só por cena (só um mestre muda o valor depois)."""
    existente = db.find_participant_by_character(cena["id"], personagem["id"])
    if existente:
        return Resultado(
            False,
            f"**{personagem['name']}** já está na cena, com iniciativa **{existente['initiative']}**. "
            "Se precisar mudar, pede pra um mestre.",
        )
    if len(db.get_participants(cena["id"])) >= db.MAX_SCENE_PARTICIPANTS:
        return Resultado(False, f"A cena está cheia ({db.MAX_SCENE_PARTICIPANTS} participantes).")
    total, como, rolados = rolar_iniciativa(personagem)
    db.add_participant(
        cena["id"], "pc", personagem["name"], total, como, character_id=personagem["id"], user_id=user_id,
    )
    db.log_roll(
        user_id=user_id, username=username, guild_id=guild_id,
        notation=f"1d20{db.attributes_of(personagem)['destreza']:+d}" if db.attributes_of(personagem)["destreza"] else "1d20",
        rolls=rolados, total=total, purpose="iniciativa" + (" (vantagem)" if len(rolados) == 2 else ""),
        character_id=personagem["id"], character_name=personagem["name"],
    )
    return Resultado(True, f"🎲 **{personagem['name']}**: {como} = **{total}** de iniciativa.", True)


def ler_iniciativa(texto: str) -> tuple[int, str] | str:
    """A iniciativa que o mestre digita: um número (12, -1) ou uma rolagem (1d20+3, d20).
    Devolve (valor, como saiu) ou o texto do erro."""
    t = _uma_linha(texto)
    if re.fullmatch(r"[+-]?\d{1,3}", t):
        return int(t), "definida pelo mestre"
    try:
        r = dice.roll(t)
    except dice.DiceError as e:
        return f"Iniciativa inválida: escreve um número (12) ou uma rolagem (1d20+3). {e}"
    return r.total, f"{t}: {r.describe()} = {r.total}"


def adicionar_npc(cena, nome: str, iniciativa_texto: str) -> Resultado:
    nome = _uma_linha(nome)
    if not nome:
        return Resultado(False, "Escreve o nome do NPC.")
    if len(nome) > TAMANHO_MAX_NOME:
        return Resultado(False, f"O nome passou de {TAMANHO_MAX_NOME} letras. Encurta.")
    lido = ler_iniciativa(iniciativa_texto)
    if isinstance(lido, str):
        return Resultado(False, lido)
    valor, como = lido
    partes = db.get_participants(cena["id"])
    if len(partes) >= db.MAX_SCENE_PARTICIPANTS:
        return Resultado(False, f"A cena está cheia ({db.MAX_SCENE_PARTICIPANTS} participantes).")
    existentes = {p["name"].casefold() for p in partes}
    final, n = nome, 1
    while final.casefold() in existentes:  # dois "Guarda" viram "Guarda" e "Guarda 2"
        n += 1
        final = f"{nome} {n}"
    db.add_participant(cena["id"], "npc", final, valor, como)
    return Resultado(True, f"➕ **{final}** entrou na cena com iniciativa **{valor}** ({como}).", True)


def mudar_iniciativa(participante_id: int, iniciativa_texto: str) -> Resultado:
    p = db.get_participant(participante_id)
    if p is None:
        return Resultado(False, "Esse participante já saiu da cena.")
    lido = ler_iniciativa(iniciativa_texto)
    if isinstance(lido, str):
        return Resultado(False, lido)
    valor, como = lido
    db.set_participant_initiative(participante_id, valor, como)
    return Resultado(True, f"✏️ A iniciativa de **{p['name']}** agora é **{valor}** ({como}).", True)


def remover_participante(cena, participante_id: int) -> Resultado:
    """Tira da cena. Se era a vez dele, a vez volta pra quem vem antes, pra 'próximo turno' seguir de onde estava."""
    p = db.get_participant(participante_id)
    if p is None or p["scene_id"] != cena["id"]:
        return Resultado(False, "Esse participante já saiu da cena.")
    partes = db.get_participants(cena["id"])
    if cena["turn_participant_id"] == participante_id:
        idx = [x["id"] for x in partes].index(participante_id)
        db.set_scene_turn(cena["id"], partes[idx - 1]["id"] if idx > 0 else None, cena["round"])
    db.remove_participant(participante_id)
    return Resultado(True, f"🗑 **{p['name']}** saiu da cena.", True)


# ---------------------------------------------------------------------------
# A vez de cada um
# ---------------------------------------------------------------------------
def proximo_turno(cena_id: int) -> tuple[str, sqlite3.Row | None, int]:
    """Passa a vez. Devolve (evento, participante da vez, rodada). Evento: 'vazio' (ninguém na cena), 'turno'
    ou 'rodada' (passou do último: volta pro primeiro e começa outra rodada)."""
    cena = db.get_scene(cena_id)
    partes = db.get_participants(cena_id)
    if not partes:
        return "vazio", None, cena["round"]
    ids = [p["id"] for p in partes]
    atual = cena["turn_participant_id"]
    if atual not in ids:  # ninguém tinha a vez ainda (ou quem tinha saiu)
        db.set_scene_turn(cena_id, ids[0], cena["round"])
        return "turno", partes[0], cena["round"]
    idx = ids.index(atual)
    if idx + 1 < len(partes):
        db.set_scene_turn(cena_id, ids[idx + 1], cena["round"])
        return "turno", partes[idx + 1], cena["round"]
    db.set_scene_turn(cena_id, ids[0], cena["round"] + 1)
    return "rodada", partes[0], cena["round"] + 1


def mensagem_da_vez(cena_id: int, evento: str, participante) -> tuple[str, discord.AllowedMentions | None]:
    """O aviso público de quando a vez muda. Só marca o jogador da vez (NPC não marca ninguém)."""
    cena = db.get_scene(cena_id)
    linhas = []
    if evento == "rodada":
        linhas.append(f"🔔 **Rodada {cena['round']}** começou.")
    if participante["kind"] == "pc" and participante["user_id"]:
        intencao = db.get_intention(participante["id"], cena["round"])
        status = _FRASE_DO_STATUS[intencao["status"] if intencao else None]
        linhas.append(f"▶️ Vez de <@{participante['user_id']}> · **{participante['name']}** ({participante['initiative']}) · {status}")
        # Só o jogador da vez pode ser marcado. O nome do personagem é o jogador quem escolhe, então
        # @everyone e cargos ficam proibidos de forma explícita, sem depender do padrão do bot.
        permitidas = discord.AllowedMentions(
            everyone=False, roles=False, replied_user=False, users=[discord.Object(id=int(participante["user_id"]))],
        )
    else:
        linhas.append(f"▶️ Vez de **{participante['name']}** (NPC, {participante['initiative']})")
        permitidas = None
    return "\n".join(linhas), permitidas


# ---------------------------------------------------------------------------
# Intenções
# ---------------------------------------------------------------------------
def participante_do_usuario(cena_id: int, user_id: str):
    """Quem esse jogador é na cena: o personagem em uso, se ele está nela; senão o primeiro que estiver."""
    ativo = db.get_active_character(user_id)
    if ativo is not None:
        p = db.find_participant_by_character(cena_id, ativo["id"])
        if p is not None:
            return p
    meus = [p for p in db.get_participants(cena_id) if p["user_id"] == user_id]
    return meus[0] if meus else None


_SEM_LUGAR = (
    "Você ainda não está na iniciativa desta cena. Aperta 🎲 no quadro ou usa `/iniciativa` primeiro."
)


def enviar_intencao(cena, user_id: str, texto: str) -> Resultado:
    participante = participante_do_usuario(cena["id"], user_id)
    if participante is None:
        return Resultado(False, _SEM_LUGAR)
    texto = _uma_linha(texto)
    if not texto:
        return Resultado(False, "Escreve a sua intenção, numa frase: o que o seu personagem quer fazer.")
    if len(texto) > TAMANHO_MAX_INTENCAO:
        return Resultado(False, f"A sua intenção tem {len(texto)} letras e o limite é {TAMANHO_MAX_INTENCAO}. Resume numa frase.")
    resultado = db.save_intention(cena["id"], participante["id"], cena["round"], texto)
    if resultado == "permitida":
        return Resultado(
            False,
            f"A intenção de **{participante['name']}** nesta rodada já foi permitida. Faz a ação na sua vez.",
        )
    if resultado == "trocada":
        return Resultado(True, f"📝 Intenção de **{participante['name']}** trocada. A anterior foi descartada.\n> {texto}", True)
    return Resultado(True, f"📝 Intenção de **{participante['name']}** enviada pro mestre.\n> {texto}\nO quadro mostra quando ele decidir.", True)


def ver_minha_intencao(cena, user_id: str) -> Resultado:
    participante = participante_do_usuario(cena["id"], user_id)
    if participante is None:
        return Resultado(False, _SEM_LUGAR)
    intencao = db.get_intention(participante["id"], cena["round"])
    if intencao is None:
        return Resultado(True, f"**{participante['name']}** ainda não mandou intenção na rodada {cena['round']}. Usa `/intencao` ou o botão 📝 do quadro.")
    linhas = [f"**{participante['name']}**, rodada {cena['round']}: {_FRASE_DO_STATUS[intencao['status']]}", f"> {intencao['text']}"]
    if intencao["status"] == "negada" and intencao["master_note"]:
        linhas.append(f"Motivo do mestre: {intencao['master_note']}")
    if intencao["status"] == "negada":
        linhas.append("Manda outra com `/intencao` se quiser tentar de novo.")
    return Resultado(True, "\n".join(linhas))


# ---------------------------------------------------------------------------
# Os quadros
# ---------------------------------------------------------------------------
def _icone(participante, intencoes: dict) -> str:
    if participante["kind"] != "pc":
        return ""
    intencao = intencoes.get(participante["id"])
    return ICONES[intencao["status"] if intencao else None]


def _linhas_da_ordem(cena, partes, intencoes: dict, mostrar_texto: bool) -> list[str]:
    linhas = []
    for i, p in enumerate(partes, 1):
        npc = " (NPC)" if p["kind"] == "npc" else ""
        icone = _icone(p, intencoes)
        base = f"{i}. {p['name']}{npc} · {p['initiative']}" + (f" {icone}" if icone else "")
        if p["id"] == cena["turn_participant_id"]:
            base = f"▶️ **{i}. {p['name']}{npc}** · {p['initiative']}" + (f" {icone}" if icone else "")
        linhas.append(base)
        intencao = intencoes.get(p["id"])
        if mostrar_texto and intencao is not None:
            linhas.append(f"    ↳ “{_cortar(intencao['text'], 90)}”")
    return linhas


def embed_quadro(cena_id: int) -> discord.Embed:
    """O quadro público: a ordem e o status de cada um. Sem o texto das intenções."""
    cena = db.get_scene(cena_id)
    partes = db.get_participants(cena_id)
    intencoes = db.list_intentions(cena_id, cena["round"])
    encerrada = not cena["active"]
    linhas = _linhas_da_ordem(cena, partes, intencoes, mostrar_texto=False) or ["Ninguém entrou na iniciativa ainda."]
    embed = discord.Embed(
        title=f"⚔️ {cena['name']}" + (" (encerrada)" if encerrada else ""),
        description=f"**Rodada {cena['round']}**\n\n" + "\n".join(linhas) + ("" if encerrada else f"\n\n{LEGENDA}"),
        color=discord.Color.dark_grey().value if encerrada else COR_QUADRO,
    )
    if not encerrada:
        embed.set_footer(text="🎲 entra na iniciativa · 📝 manda a sua intenção pro mestre (só ele lê)")
    return embed


def embed_escudo(cena_id: int, intencao_selecionada: int | None = None) -> discord.Embed:
    """O quadro do mestre: a ordem com as intenções escritas (só ele vê)."""
    cena = db.get_scene(cena_id)
    partes = db.get_participants(cena_id)
    intencoes = db.list_intentions(cena_id, cena["round"])
    linhas = _linhas_da_ordem(cena, partes, intencoes, mostrar_texto=True) or ["Ninguém entrou na iniciativa ainda."]
    vez = next((p["name"] for p in partes if p["id"] == cena["turn_participant_id"]), None)
    embed = discord.Embed(
        title=f"🛡️ Escudo do Mestre · {cena['name']}",
        description=(
            f"**Rodada {cena['round']}** · vez de {('**' + vez + '**') if vez else 'ninguém ainda'}\n\n"
            + "\n".join(linhas) + f"\n\n{LEGENDA}"
        ),
        color=COR_ESCUDO,
    )
    pendentes = [i for i in intencoes.values() if i["status"] == "pendente"]
    if intencao_selecionada is not None:
        escolhida = next((i for i in pendentes if i["id"] == intencao_selecionada), None)
        if escolhida is not None:
            dono = next((p["name"] for p in partes if p["id"] == escolhida["participant_id"]), "?")
            embed.add_field(name=f"📝 {dono}", value=f"“{escolhida['text']}”\nPermitir ou negar?", inline=False)
    embed.set_footer(text=f"{len(pendentes)} aguardando você · o que os jogadores mandam só aparece aqui · 🔄 Atualizar mostra o que chegou")
    return embed


def embed_sem_cena() -> discord.Embed:
    return discord.Embed(
        title="🛡️ Escudo do Mestre",
        description=(
            "Não tem cena aberta neste canal.\n\n"
            "Aperta **Iniciar cena** pra abrir uma. Depois os jogadores entram com `/iniciativa` (ou pelo botão do "
            "quadro) e mandam a intenção com `/intencao`."
        ),
        color=COR_ESCUDO,
    )


def opcoes_de_intencoes(cena_id: int) -> list[tuple[str, str, str]]:
    """(rótulo, valor, descrição) das intenções pendentes, na ordem da iniciativa."""
    cena = db.get_scene(cena_id)
    intencoes = db.list_intentions(cena_id, cena["round"])
    saida = []
    for p in db.get_participants(cena_id):
        i = intencoes.get(p["id"])
        if i is not None and i["status"] == "pendente":
            saida.append((_cortar(f"{p['name']} ({p['initiative']})", 100), str(i["id"]), _cortar(i["text"], 100)))
    return saida
