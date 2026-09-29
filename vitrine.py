"""Monta os cartões bonitos do bot: um título, o texto do resultado em citação, campos e uma imagem grande.

Os textos e as cores ficam em lore.py, as imagens na pasta assets/, e as regras (números) vêm de rules.py e
dice.py. Aqui só se junta tudo. Cada função devolve um Cartao; pra mandar, use
    await interaction.response.send_message(**cartao.kwargs())
"""

import io
import os
import re
import unicodedata
from dataclasses import dataclass

import discord

import dice
import lore
import rules

PASTA_IMAGENS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
EXTENSOES = ("gif", "png", "jpg", "jpeg", "webp")

_bytes_em_cache: dict[str, bytes] = {}


def slug(texto: str) -> str:
    """'Mestre de Forja' vira 'mestre-de-forja': minúsculas, sem acento, hífen no lugar de espaço."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")


def chave_de_imagem(tipo: str, nome: str) -> str:
    return f"{tipo}-{slug(nome)}"


def achar_imagem(tipo: str, nome: str) -> tuple[str, str] | None:
    """('url', link) ou ('arquivo', caminho) da imagem desse resultado, ou None se não tem."""
    chave = chave_de_imagem(tipo, nome)
    if chave in lore.IMAGENS_URL:
        return ("url", lore.IMAGENS_URL[chave])
    for extensao in EXTENSOES:
        caminho = os.path.join(PASTA_IMAGENS, f"{chave}.{extensao}")
        if os.path.isfile(caminho):
            return ("arquivo", caminho)
    return None


def _conteudo(caminho: str) -> bytes:
    if caminho not in _bytes_em_cache:
        with open(caminho, "rb") as arquivo:
            _bytes_em_cache[caminho] = arquivo.read()
    return _bytes_em_cache[caminho]


@dataclass
class Cartao:
    embed: discord.Embed
    arquivos: list[discord.File]

    def kwargs(self) -> dict:
        """Os argumentos pra send_message / reply / followup.send. Só leva 'files' quando tem arquivo."""
        return {"embed": self.embed, **({"files": self.arquivos} if self.arquivos else {})}


def _citar(texto: str) -> str:
    return "\n".join(f"> {linha}" if linha.strip() else ">" for linha in texto.split("\n"))


def _montar(*, autor: str, titulo: str, cor: int, topo: str | None = None, texto: str | None = None,
            campos: list[tuple[str, str, bool]] = (), imagem=None, miniatura=None,
            rodape: str | None = None) -> Cartao:
    embed = discord.Embed(title=titulo, color=cor)
    embed.set_author(name=autor)
    partes = [p for p in (topo, _citar(texto) if texto else None) if p]
    if partes:
        embed.description = "\n\n".join(partes)
    for nome, valor, em_linha in campos:
        embed.add_field(name=nome, value=valor, inline=em_linha)

    arquivos: list[discord.File] = []

    def aplicar(referencia, colocar):
        if referencia is None:
            return
        tipo, valor = referencia
        if tipo == "url":
            colocar(url=valor)
            return
        nome_do_arquivo = os.path.basename(valor)
        arquivos.append(discord.File(io.BytesIO(_conteudo(valor)), filename=nome_do_arquivo))
        colocar(url=f"attachment://{nome_do_arquivo}")

    aplicar(imagem, embed.set_image)
    aplicar(miniatura, embed.set_thumbnail)
    if rodape:
        embed.set_footer(text=rodape)
    return Cartao(embed, arquivos)


# ---------------------------------------------------------------------------
# Raça
# ---------------------------------------------------------------------------

def _em_jogo_da_raca(raca: str) -> str:
    """O que a raça muda na ficha. Os números vêm do rules.py, então não saem do compasso com as regras."""
    lim = rules.CREATION_LIMITS.get(raca, {})
    if raca == "Humano":
        return (
            "Sem Disciplinas\n"
            f"Força, Destreza e Vitalidade até {lim['forca']} e Razão até {lim['razao']} na criação"
        )
    pontos = rules.INITIAL_DISCIPLINE_POINTS[raca]
    linhas = [
        f"{pontos} pontos de Disciplina na criação (grau máximo {rules.DISCIPLINE_CREATION_MAX_GRADE})"
        + (", pode usar as dez" if raca == "Dhampir" else "")
    ]
    if lim:
        linhas.append(f"Força, Destreza e Vitalidade até {lim['forca']} na criação")
    else:
        linhas.append("Limites de atributo ainda a definir")
    linhas.append(f"Fraquezas: {lore.RACAS[raca]['fraquezas']}")
    return "\n".join(linhas)


def cartao_raca(personagem: str, raca: str, rolagem: int, jogador: str) -> Cartao:
    info = lore.RACAS[raca]
    return _montar(
        autor=f"{info['emoji']} Raça de {personagem}",
        titulo=raca,
        cor=info["cor"],
        topo=f"🎲 1d100 = **{rolagem}**",
        texto=info["texto"],
        campos=[("Em jogo", _em_jogo_da_raca(raca), False)],
        imagem=achar_imagem("raca", raca),
        rodape=f"jogador: {jogador}",
    )


# ---------------------------------------------------------------------------
# Classe social
# ---------------------------------------------------------------------------

def cartao_estado(personagem: str, estado: str, r1: int, jogador: str,
                  clero: str | None = None, r2: int | None = None) -> Cartao:
    autor = f"⚜️ Classe Social de {personagem}"
    topo = f"🎲 1d100 = **{r1}**"
    if estado == dice.SOCIAL_CLASS_MASTER:
        info = lore.ESTADO_MESTRE
        return _montar(
            autor=autor, titulo=f"{info['emoji']} {info['titulo']}", cor=info["cor"], topo=topo,
            texto=info["texto"], imagem=achar_imagem("estado", "mestre"), rodape=f"jogador: {jogador}",
        )
    info = lore.ESTADOS[estado]
    campos = []
    miniatura = None
    if clero:
        topo += f"\n🎲 1d100 = **{r2}** → **{clero}**"
        campos.append((clero, lore.CLERO[clero], False))
        miniatura = achar_imagem("clero", clero.split()[0])
    return _montar(
        autor=autor, titulo=info["titulo"], cor=info["cor"], topo=topo, texto=info["texto"], campos=campos,
        imagem=achar_imagem("estado", estado[0]), miniatura=miniatura, rodape=f"jogador: {jogador}",
    )


# ---------------------------------------------------------------------------
# Classe
# ---------------------------------------------------------------------------

def cartao_classe(personagem: str, classe: str, proximo: str, jogador: str | None = None) -> Cartao:
    b = rules.CLASSES[classe]
    return _montar(
        autor=f"🎓 Classe de {personagem}",
        titulo=classe,
        cor=lore.COR_CLASSE,
        texto=lore.CLASSES[classe],
        campos=[
            ("Vantagem nas perícias", rules.CLASS_SKILLS[classe], False),
            ("Bônus", f"Vida +{b['vida']} · Sanidade +{b['sanidade']} · Mana +{b['mana']} · Estamina +{b['estamina']}", False),
            ("Continue a criação", proximo, False),
        ],
        imagem=achar_imagem("classe", classe),
        rodape=f"jogador: {jogador}" if jogador else None,
    )


# ---------------------------------------------------------------------------
# Rank de magia
# ---------------------------------------------------------------------------

def _chance_do_rank(rank: str) -> int:
    return sum(fim - inicio + 1 for inicio, fim, nome in dice.MAGIC_RANK_TABLE if nome == rank)


def cartao_magia(personagem: str, rank: str, rolagem: int, jogador: str) -> Cartao:
    info = lore.RANKS_MAGIA[rank]
    estrelas = "★" * info["estrelas"] + "☆" * (5 - info["estrelas"])
    return _montar(
        autor=f"✨ Magia Inicial de {personagem}",
        titulo=f"Rank {rank}",
        cor=info["cor"],
        topo=f"🎲 1d100 = **{rolagem}**\n{estrelas} · {_chance_do_rank(rank)}% de chance",
        texto=lore.TEXTO_MAGIA,
        imagem=achar_imagem("magia", rank),
        rodape=f"jogador: {jogador}",
    )


# ---------------------------------------------------------------------------
# Rolagem de dados (vale pro /rolar e pros dados escritos no chat)
# ---------------------------------------------------------------------------

def cartao_rolagem(quem: str, notacao: str, resultado: "dice.RollResult", motivo: str | None,
                   jogador: str, com_personagem: bool) -> Cartao:
    descricao = f"**{resultado.describe()} = {resultado.total}**"
    cor = discord.Color.dark_red()
    if resultado.sides == 20 and len(resultado.rolls) == 1:  # destaque só no visual, sem efeito de regra
        if resultado.rolls[0] == 20:
            descricao += "\n🌟 **20 natural!**"
            cor = discord.Color.gold()
        elif resultado.rolls[0] == 1:
            descricao += "\n💀 **1 natural!**"
            cor = discord.Color.dark_grey()
    embed = discord.Embed(title=f"🎲 {quem} rolou {notacao}", description=descricao, color=cor)
    rodape = []
    if motivo:
        rodape.append(motivo)
    if com_personagem:
        rodape.append(f"jogador: {jogador}")
    if rodape:
        embed.set_footer(text=" · ".join(rodape))
    return Cartao(embed, [])
