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


def _citar(texto: str, italico: bool = False) -> str:
    """O texto em citação. Em itálico, cada linha vai entre asteriscos (os textos não usam asterisco)."""
    def linha_certa(linha: str) -> str:
        if not linha.strip():
            return ">"
        return f"> *{linha}*" if italico else f"> {linha}"
    return "\n".join(linha_certa(linha) for linha in texto.split("\n"))


def _rodape(jogador: str, tentativa: tuple[int, int] | None = None) -> str:
    if tentativa is None:
        return f"jogador: {jogador}"
    usadas, total = tentativa
    aviso = "última chance" if usadas >= total else f"tentativa {usadas} de {total}"
    return f"jogador: {jogador} · {aviso}"


def resultado_atual(personagem, campo: str) -> str:
    """O resultado que o personagem tem hoje em 'race' ou 'social_class', escrito pra mostrar ao jogador."""
    if campo == "race":
        return personagem["race"]
    estado = personagem["social_class"]
    if estado == dice.SOCIAL_CLASS_MASTER:
        return "a decidir pelo mestre"
    titulo = lore.ESTADOS[estado]["titulo"]
    return f"{titulo} ({personagem['clergy']})" if personagem["clergy"] else titulo


def _montar(*, autor: str, titulo: str, cor: int, topo: str | None = None, texto: str | None = None,
            italico: bool = False, campos: list[tuple[str, str, bool]] = (), imagem=None, miniatura=None,
            rodape: str | None = None) -> Cartao:
    embed = discord.Embed(title=titulo, color=cor)
    embed.set_author(name=autor)
    partes = [p for p in (topo, _citar(texto, italico) if texto else None) if p]
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


def cartao_raca(personagem: str, raca: str, jogador: str, tentativa: tuple[int, int] | None = None) -> Cartao:
    """O dado sorteado não aparece no cartão (só o resultado); ele continua valendo e vai pro histórico."""
    info = lore.RACAS[raca]
    return _montar(
        autor=f"{info['emoji']} Raça de {personagem}",
        titulo=raca,
        cor=info["cor"],
        topo=lore.DIVISOR,
        texto=info["texto"],
        italico=True,
        campos=[("Em jogo", _em_jogo_da_raca(raca), False)],
        imagem=achar_imagem("raca", raca),
        rodape=_rodape(jogador, tentativa),
    )


# ---------------------------------------------------------------------------
# Classe social
# ---------------------------------------------------------------------------

def cartao_estado(personagem: str, estado: str, jogador: str, clero: str | None = None,
                  tentativa: tuple[int, int] | None = None) -> Cartao:
    """Os dados (o do Estado e o do clero) não aparecem no cartão, só o resultado."""
    autor = f"⚜️ Classe Social de {personagem}"
    if estado == dice.SOCIAL_CLASS_MASTER:
        info = lore.ESTADO_MESTRE
        return _montar(
            autor=autor, titulo=f"{info['emoji']} {info['titulo']}", cor=info["cor"], topo=lore.DIVISOR,
            texto=info["texto"], italico=True, imagem=achar_imagem("estado", "mestre"),
            rodape=_rodape(jogador, tentativa),
        )
    info = lore.ESTADOS[estado]
    campos = []
    miniatura = None
    if clero:
        campos.append((f"✝ {clero}", lore.CLERO[clero], False))
        miniatura = achar_imagem("clero", clero.split()[0])
    return _montar(
        autor=autor, titulo=info["titulo"], cor=info["cor"], topo=lore.DIVISOR, texto=info["texto"], italico=True,
        campos=campos, imagem=achar_imagem("estado", estado[0]), miniatura=miniatura,
        rodape=_rodape(jogador, tentativa),
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
        topo=lore.DIVISOR,
        texto=lore.CLASSES[classe],
        italico=True,
        campos=[
            ("Vantagem nas perícias", rules.CLASS_SKILLS[classe], False),
            ("Bônus", f"Vida +{b['vida']} · Sanidade +{b['sanidade']} · Mana +{b['mana']} · Estamina +{b['estamina']}", False),
            ("Continue a criação", proximo, False),
        ],
        imagem=achar_imagem("classe", classe),
        rodape=f"jogador: {jogador}" if jogador else None,
    )


def resumo_da_ficha(personagem) -> str:
    """A linha do topo da ficha: raça, classe e nível de relance (só o que o personagem já tem)."""
    partes = []
    raca = personagem["race"]
    if raca in lore.RACAS:
        partes.append(f"{lore.RACAS[raca]['emoji']} {raca}")
    if personagem["class_name"]:
        partes.append(f"🎓 {personagem['class_name']}")
    partes.append(f"Nível {personagem['level']}")
    return " · ".join(partes)


def cor_da_ficha(personagem) -> int:
    """A cor da raça, ou o roxo de sempre enquanto a raça não foi sorteada."""
    raca = personagem["race"]
    return lore.RACAS[raca]["cor"] if raca in lore.RACAS else discord.Color.dark_purple().value


def miniatura_da_ficha(personagem) -> str | None:
    """Link direto da imagem da raça (IMAGENS_URL), se existir. A ficha é privada e não leva anexo."""
    imagem = achar_imagem("raca", personagem["race"]) if personagem["race"] else None
    return imagem[1] if imagem and imagem[0] == "url" else None


def previa_classe(personagem: str, classe: str) -> discord.Embed:
    """A classe como prévia, pro menu de escolha do painel. É mensagem privada, que não leva anexo: só usa
    imagem se for um link direto (IMAGENS_URL)."""
    b = rules.CLASSES[classe]
    embed = discord.Embed(
        title=f"🎓 {classe}",
        description=f"{lore.DIVISOR}\n\n{_citar(lore.CLASSES[classe], True)}\n\nSe for essa, aperta **Confirmar classe**. Vale uma vez só.",
        color=lore.COR_CLASSE,
    )
    embed.set_author(name=f"Classe de {personagem}")
    embed.add_field(name="Vantagem nas perícias", value=rules.CLASS_SKILLS[classe], inline=False)
    embed.add_field(
        name="Bônus",
        value=f"Vida +{b['vida']} · Sanidade +{b['sanidade']} · Mana +{b['mana']} · Estamina +{b['estamina']}",
        inline=False,
    )
    imagem = achar_imagem("classe", classe)
    if imagem and imagem[0] == "url":
        embed.set_image(url=imagem[1])
    return embed


# ---------------------------------------------------------------------------
# Disciplinas
# ---------------------------------------------------------------------------
COR_DISCIPLINA = 0x8B0000


def _maiuscula(texto: str) -> str:
    return texto[:1].upper() + texto[1:]


def barra_de_grau(grau: int) -> str:
    return rules.bar(grau, rules.MAX_DISCIPLINE_GRADE)


def linha_de_pontos(nivel: int, raca: str | None, graus: dict[str, int]) -> str:
    """'Pontos: 3 de 4 usados (1 livre)', com o aviso quando um mestre deu graus além dos pontos."""
    total = rules.discipline_points_total(nivel, raca)
    usados = rules.discipline_points_used(graus)
    livres = total - usados
    if livres > 0:
        sobra = f" ({livres} {'livre' if livres == 1 else 'livres'})"
    elif livres < 0:
        sobra = f" (passou {-livres})"
    else:
        sobra = ""
    return f"Pontos: {usados} de {total} usados{sobra}"


def texto_disciplinas_da_ficha(personagem, graus: dict[str, int]) -> str:
    """O campo 'Disciplinas' da ficha: os pontos e as Disciplinas que o personagem já tem."""
    cabecalho = linha_de_pontos(personagem["level"], personagem["race"], graus)
    if not graus:
        return f"{cabecalho}\nnenhuma ainda (o botão **Disciplinas** do `/minha_ficha` abre o painel)"
    linhas = [f"**{d}** {g}/{rules.MAX_DISCIPLINE_GRADE} {barra_de_grau(g)}" for d, g in graus.items()]
    return cabecalho + "\n" + "\n".join(linhas)


def embed_disciplinas(nome: str | None, raca: str | None, nivel: int, graus: dict[str, int]) -> discord.Embed:
    """A lista das dez Disciplinas. Quem tem Disciplinas vê o grau de cada uma; quem não tem só lê o tema."""
    tem = rules.has_disciplines(raca)
    embed = discord.Embed(
        title="🩸 Disciplinas" + (f" de {nome}" if nome and tem else ""), color=COR_DISCIPLINA,
    )
    if tem:
        embed.description = (
            f"{lore.DIVISOR_CURTO}\n\n{linha_de_pontos(nivel, raca, graus)}\n"
            "Escolhe uma no menu pra ler o texto de cada grau e subir."
        )
    else:
        embed.description = (
            f"{lore.DIVISOR_CURTO}\n\nSó **Vampiros e Dhampirs** têm Disciplinas. "
            "Aqui você pode ler o que cada uma faz."
        )
    for disciplina in rules.DISCIPLINES:
        info = lore.DISCIPLINAS[disciplina]
        if rules.discipline_blocked(disciplina):
            valor = "⏳ em desenvolvimento"
        elif tem:
            grau = graus.get(disciplina, 0)
            valor = f"{barra_de_grau(grau)} {grau}/{rules.MAX_DISCIPLINE_GRADE}\n{_maiuscula(info['tema'])}"
        else:
            valor = _maiuscula(info["tema"])
        embed.add_field(name=disciplina, value=valor, inline=True)
    return embed


def embed_disciplina(disciplina: str, grau_atual: int | None = None, pontos: str | None = None,
                     aviso: str | None = None) -> discord.Embed:
    """O texto de cada grau de uma Disciplina. Com grau_atual, marca ✅ os graus que o personagem já tem."""
    info = lore.DISCIPLINAS[disciplina]
    embed = discord.Embed(
        title=f"🩸 {disciplina}",
        description=f"{lore.DIVISOR_CURTO}\n\n{_citar(_maiuscula(info['tema']), True)}",
        color=COR_DISCIPLINA,
    )
    if info["graus"] is None or rules.discipline_blocked(disciplina):
        embed.add_field(name="⏳ Em desenvolvimento", value=lore.DISCIPLINA_EM_DESENVOLVIMENTO, inline=False)
    else:
        for grau, texto in info["graus"].items():
            marca = "" if grau_atual is None else ("✅ " if grau_atual >= grau else "▫️ ")
            embed.add_field(name=f"{marca}Grau {grau}", value=texto, inline=False)
    embed.add_field(name="Graus 4 e 5", value=lore.GRAUS_4_E_5, inline=False)
    if info.get("limite"):
        embed.add_field(name="Limite", value=info["limite"], inline=False)
    if aviso:
        embed.add_field(name="Pra subir", value=aviso, inline=False)
    if pontos:
        embed.set_footer(text=pontos)
    return embed


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
        topo=f"{lore.DIVISOR_CURTO}\n🎲 1d100 = **{rolagem}**\n{estrelas} · {_chance_do_rank(rank)}% de chance",
        texto=lore.TEXTO_MAGIA,
        italico=True,
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
