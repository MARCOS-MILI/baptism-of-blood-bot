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
import habil
import lore
import rules

PASTA_IMAGENS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
EXTENSOES = ("gif", "png", "jpg", "jpeg", "webp")

_bytes_em_cache: dict[str, bytes] = {}

LIMITE_DO_DOWNLOAD = 8 * 1024 * 1024   # o que o Discord aceita de anexo, com folga
_baixadas: dict[str, tuple[str, bytes]] = {}   # chave da imagem -> (nome do arquivo, conteúdo) dos links já baixados


def slug(texto: str) -> str:
    """'Mestre de Forja' vira 'mestre-de-forja': minúsculas, sem acento, hífen no lugar de espaço."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")


def chave_de_imagem(tipo: str, nome: str) -> str:
    return f"{tipo}-{slug(nome)}"


def _arquivo_local(chave: str) -> str | None:
    for extensao in EXTENSOES:
        caminho = os.path.join(PASTA_IMAGENS, f"{chave}.{extensao}")
        if os.path.isfile(caminho):
            return caminho
    return None


def _extensao_pela_assinatura(dados: bytes) -> str | None:
    """Confere nos primeiros bytes se é mesmo uma imagem (e de que tipo), pra não anexar uma página de erro."""
    if dados[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if dados[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if dados[:3] == b"\xff\xd8\xff":
        return "jpg"
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "webp"
    return None


async def _baixar_link(link: str) -> bytes:
    import aiohttp   # já vem com o discord.py
    cabecalhos = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25), headers=cabecalhos) as sessao:
        async with sessao.get(link) as resposta:
            if resposta.status != 200:
                raise RuntimeError(f"HTTP {resposta.status}")
            return await resposta.read()


async def baixar_imagens(baixar=None) -> dict[str, str]:
    """Baixa os links de IMAGENS_URL e guarda na memória, pra o cartão anexar o arquivo (anexo sempre aparece; o Discord
    às vezes não mostra uma imagem de link). Devolve o que aconteceu com cada uma, pra ir pro log."""
    baixar = baixar or _baixar_link
    resultado = {}
    for chave, link in list(lore.IMAGENS_URL.items()):
        try:
            dados = await baixar(link)
            if len(dados) > LIMITE_DO_DOWNLOAD:
                raise ValueError("passou de 8 MB")
            extensao = _extensao_pela_assinatura(dados)
            if extensao is None:
                raise ValueError("não é uma imagem")
        except Exception as erro:   # um link fora do ar não pode derrubar o bot: o cartão usa a imagem da pasta
            resultado[chave] = f"falhou: {erro}"
            continue
        _baixadas[chave] = (f"{chave}.{extensao}", dados)
        resultado[chave] = f"ok ({len(dados)} bytes, {extensao})"
    return resultado


def achar_imagem(tipo: str, nome: str) -> tuple[str, str] | None:
    """('url', link) ou ('arquivo', caminho) da imagem desse resultado, ou None se não tem."""
    chave = chave_de_imagem(tipo, nome)
    if chave in lore.IMAGENS_URL:
        return ("url", lore.IMAGENS_URL[chave])
    caminho = _arquivo_local(chave)
    return ("arquivo", caminho) if caminho else None


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


def _negrito_matematico(c: str) -> str:
    """A letra maiúscula ou o número em negrito matemático (𝐇, 𝟏), como nas mensagens do servidor."""
    if "A" <= c <= "Z":
        return chr(0x1D400 + ord(c) - ord("A"))
    if "0" <= c <= "9":
        return chr(0x1D7CE + ord(c) - ord("0"))
    return c


def enfeitar_rotulo(rotulo: str) -> str:
    """'Humanos' vira '𝐇umanos': só a inicial de cada palavra (e os números) em negrito matemático."""
    saida, inicio = [], True
    for c in rotulo:
        saida.append(_negrito_matematico(c) if c.isdigit() or (inicio and c.isalpha()) else c)
        inicio = c == " "
    return "".join(saida)


def _cabecalho(rotulo: str, emoji: str) -> str:
    """A linha do título no estilo do servidor: emoji, espaço, ornamento e o rótulo enfeitado."""
    return (
        f"{emoji}{' ' * 12}{lore.PREENCHE * 5}{lore.ORNAMENTO_L}{lore.NULO * 8}{enfeitar_rotulo(rotulo)}"
        f"{lore.NULO * 3}{lore.PREENCHE * 2} {lore.PREENCHE * 2}{lore.HIEROGLIFO}"
    )


def _citar_decorado(texto: str, emoji: str) -> str:
    """O texto em citação, em negrito e (se lore.TEXTO_PEQUENO) em letra pequena, com o emoji na frente."""
    pequeno = "-# " if lore.TEXTO_PEQUENO else ""
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    saida = []
    for i, linha in enumerate(linhas):
        abre = f"{emoji}{' ' * 6}" if i == 0 else ""
        saida.append(f"> {pequeno}{abre}{lore.NULO * 4}{lore.ORNAMENTO_L}{lore.NULO * 4}**{linha}**")
    return "\n".join(saida)


def embed_decorado(rotulo: str, frase: str | None, corpo: str | None, cor, *, autor: str | None = None,
                   rodape: str | None = None, emoji_titulo: str = lore.EMOJI_TITULO,
                   emoji_texto: str = lore.EMOJI_TEXTO) -> discord.Embed:
    """Uma tela no estilo das raças e dos Estados: sem título de embed. O rótulo enfeitado abre a descrição, a frase vem
    em citação pequena e em negrito, e o corpo (o conteúdo da tela) vem depois."""
    partes = [_cabecalho(rotulo, emoji_titulo)]
    if frase:
        partes.append(_citar_decorado(frase, emoji_texto))
    if corpo:
        partes.append(corpo)
    embed = discord.Embed(description="\n\n".join(partes), color=cor)
    if autor:
        embed.set_author(name=autor)
    if rodape:
        embed.set_footer(text=rodape)
    return embed


# ---------------------------------------------------------------------------
# O estilo do servidor em TODAS as telas: tela() faz o que o embed_decorado faz, mas recebe o título como o
# discord.Embed recebia ("🎲 Bandeja de dados"): o emoji sai, o resto vira o cabeçalho enfeitado, e a frase de época
# (se houver) vem em citação pequena, em negrito. As frases ficam aqui, num lugar só.
# ---------------------------------------------------------------------------
FRASES_DA_EPOCA = {
    "Ajuda do bot": "Quem se perde entre as sombras há de precisar de um guia. Eis os comandos ao vosso dispor.",
    "Ajuda do mestre": "Estas linhas são só para os mestres. Eis as ferramentas da mesa.",
    "XP e vantagens de cada nível": "Cada nível custa mais sangue que o anterior. Eis o preço da glória e o que ela concede.",
    "Disciplinas": "Os dons sombrios do sangue, para quem os carrega.",
    "Habilidades dos jogadores": "As obras dos jogadores aguardam o vosso selo.",
    "Vagas de personagem": "Quantos viajantes cada jogador pode conduzir.",
    "Personagem excluído": "Mais um nome some dos registros da França.",
    "Bandeja de dados": "Lançai os dados: a sorte, ou a desgraça, é vossa.",
    "Definição apagada": "O livro de registros foi emendado, como mandou o mestre.",
    "Definição corrigida": "O livro de registros foi emendado, como mandou o mestre.",
    "Atributos corrigidos": "O livro de registros foi emendado, como mandou o mestre.",
    "Histórico apagado": "O livro de registros foi emendado, como mandou o mestre.",
}
PREFIXOS_DA_EPOCA = (
    ("Disciplinas de", FRASES_DA_EPOCA["Disciplinas"]),
    ("Extrato de XP de", "O livro de contas de tudo o que vos rendeu experiência."),
    ("Rank de XP", "Os mais calejados da França, segundo o livro de registros."),
    ("Recursos (", "Quanto de vida, mente, magia e fôlego vos resta, e o que cada nível acrescenta."),
    ("Escolha a classe de", "Que ofício abraçareis? Ele define o que sabeis fazer."),
    ("Rolar a ", "A sorte pode vos favorecer, ou não. Quereis tentá-la outra vez?"),
    ("Excluir ", "Esta ação não tem volta. Pensai bem."),
    ("Apagar o histórico de", "Esta ação não tem volta. Pensai bem."),
    ("Encerrar ", "Fechar a cena é definitivo. Quereis mesmo encerrá-la?"),
)
_AUTO = object()


def _sem_emoji(texto: str) -> str:
    """Tira os emojis do começo de um título ('🎲 Bandeja de dados' vira 'Bandeja de dados')."""
    i = 0
    while i < len(texto) and (unicodedata.category(texto[i]) in ("So", "Sk", "Mn", "Cf", "Zs", "Cn") or texto[i] in "\ufe0f\u200d"):
        i += 1
    return texto[i:].strip()


def frase_da_epoca(rotulo: str) -> str | None:
    if rotulo in FRASES_DA_EPOCA:
        return FRASES_DA_EPOCA[rotulo]
    if rotulo in rules.CLASS_SKILLS:
        return "O ofício que vos define, e o que ele vos concede."
    return next((f for prefixo, f in PREFIXOS_DA_EPOCA if rotulo.startswith(prefixo)), None)


def tela(*, title: str | None = None, description: str | None = None, color=None, frase=_AUTO,
         emoji_titulo: str = lore.EMOJI_TITULO, emoji_texto: str = lore.EMOJI_TEXTO) -> discord.Embed:
    """Um embed no estilo do servidor a partir de um título comum. Sem título, é um embed normal."""
    if not title:
        return discord.Embed(description=description, color=color)
    rotulo = _sem_emoji(title)
    return embed_decorado(
        rotulo, frase_da_epoca(rotulo) if frase is _AUTO else frase, description, color,
        emoji_titulo=emoji_titulo, emoji_texto=emoji_texto,
    )


def _montar(*, autor: str, titulo: str, cor: int, topo: str | None = None, texto: str | None = None,
            italico: bool = False, campos: list[tuple[str, str, bool]] = (), imagem=None, miniatura=None,
            rodape: str | None = None, decorado: tuple[str, str, str] | None = None, enfeitar: bool = True) -> Cartao:
    """decorado = (rótulo, emoji do cabeçalho, emoji do texto) usa o estilo do servidor: sem título do embed
    (o rótulo enfeitado abre a descrição) e o texto em citação pequena e em negrito."""
    novo_estilo = decorado or ((_sem_emoji(titulo), lore.EMOJI_TITULO, lore.EMOJI_TEXTO) if enfeitar else None)
    embed = discord.Embed(title=None if novo_estilo else titulo, color=cor)
    embed.set_author(name=autor)
    if novo_estilo:
        rotulo, emoji_titulo, emoji_texto = novo_estilo
        partes = [_cabecalho(rotulo, emoji_titulo), None if decorado else topo, _citar_decorado(texto, emoji_texto) if texto else None]
        partes = [p for p in partes if p]
    else:
        partes = [p for p in (topo, _citar(texto, italico) if texto else None) if p]
    if partes:
        embed.description = "\n\n".join(partes)
    for nome, valor, em_linha in campos:
        embed.add_field(name=nome, value=valor, inline=em_linha)

    arquivos: list[discord.File] = []

    def aplicar(referencia, colocar, anexar_link=False):
        if referencia is None:
            return
        tipo, valor = referencia
        if tipo == "url" and anexar_link:
            # a imagem grande de um link vira anexo: o que o bot baixou, senão a imagem parada da pasta, senão o link
            chave = next((k for k, v in lore.IMAGENS_URL.items() if v == valor), None)
            if chave in _baixadas:
                nome_do_arquivo, dados = _baixadas[chave]
                arquivos.append(discord.File(io.BytesIO(dados), filename=nome_do_arquivo))
                colocar(url=f"attachment://{nome_do_arquivo}")
                return
            local = _arquivo_local(chave) if chave else None
            if local:
                tipo, valor = "arquivo", local
        if tipo == "url":
            colocar(url=valor)
            return
        nome_do_arquivo = os.path.basename(valor)
        arquivos.append(discord.File(io.BytesIO(_conteudo(valor)), filename=nome_do_arquivo))
        colocar(url=f"attachment://{nome_do_arquivo}")

    aplicar(imagem, embed.set_image, anexar_link=True)
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
            "Sem magia inicial, só as classes Feiticeiros e Mestre de Forja têm\n"
            f"Força, Destreza e Vitalidade até {lim['forca']} e Razão até {lim['razao']} na criação"
        )
    pontos = rules.INITIAL_DISCIPLINE_POINTS[raca]
    linhas = [
        f"{pontos} pontos de Disciplina na criação (grau máximo {rules.DISCIPLINE_CREATION_MAX_GRADE})"
        + (", pode usar as dez" if raca == "Dhampir" else ""),
        "Tem magia inicial (`/magia_inicial`)",
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
        texto=info["texto"],
        campos=[("Em jogo", _em_jogo_da_raca(raca), False)],
        imagem=achar_imagem("raca", raca),
        rodape=_rodape(jogador, tentativa),
        decorado=(info["rotulo"], info["emoji_titulo"], info["emoji_texto"]),
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
            enfeitar=False,
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
        autor=autor, titulo=info["titulo"], cor=info["cor"], texto=info["texto"],
        campos=campos, imagem=achar_imagem("estado", estado[0]), miniatura=miniatura,
        rodape=_rodape(jogador, tentativa),
        decorado=(info["rotulo"], info["emoji_titulo"], info["emoji_texto"]),
    )


# ---------------------------------------------------------------------------
# Vitais: as barras de Vida, Sanidade, Mana e Estamina
# ---------------------------------------------------------------------------
TAMANHO_DA_BARRA = 10


def barra(atual: int, maximo: int, tamanho: int = TAMANHO_DA_BARRA) -> str:
    """▰▰▰▰▰▱▱▱▱▱: cheia só se estiver no máximo, e com pelo menos um quadrado se ainda sobrou alguma coisa."""
    if maximo <= 0:
        return "▱" * tamanho
    cheios = round(atual / maximo * tamanho)
    if atual > 0:
        cheios = max(1, cheios)
    if atual < maximo:
        cheios = min(tamanho - 1, cheios)
    return "▰" * cheios + "▱" * (tamanho - cheios)


def embed_vitais(nome: str, recursos: dict, perdidos: dict, jogador: str | None = None,
                selecionado: str = "vida") -> discord.Embed:
    """As quatro barras do personagem. 'recursos' vem do cálculo por nível; 'perdidos' é o que ele perdeu."""
    linhas = []
    for chave in rules.VITAL_KEYS:
        maximo = recursos[chave]["total"]
        atual = rules.vital_current(maximo, perdidos.get(chave, 0))
        seta = "▶️" if chave == selecionado else "▫️"
        linhas.append(f"{seta} {rules.VITAL_EMOJI[chave]} **{rules.VITAL_LABELS[chave]}** · {atual}/{maximo}\n{barra(atual, maximo)}")
    vida_max = recursos["vida"]["total"]
    vida = rules.vital_current(vida_max, perdidos.get("vida", 0))
    cor = (
        discord.Color.dark_grey() if vida == 0
        else discord.Color.red() if vida * 4 <= vida_max
        else discord.Color.orange() if vida * 2 <= vida_max
        else discord.Color.green()
    )
    aviso = "\n\n💀 **Vida em 0.** Hora de falar com o mestre." if vida == 0 else ""
    return embed_decorado(
        "Vitais", "Fostes ferido ou esgotastes a vossa mana? Escolhei a barra no menu e apertai os botões para descer ou subir.",
        "\n\n".join(linhas) + aviso, cor, autor=nome, rodape=f"jogador: {jogador}" if jogador else None,
    )


# ---------------------------------------------------------------------------
# Perícias: distribuir os pontos e testar com um clique
# ---------------------------------------------------------------------------
MODOS_DE_TESTE = {"normal": ("🎲", "Normal"), "vantagem": ("⬆️", "Vantagem"), "desvantagem": ("⬇️", "Desvantagem")}


def _aviso_de_vantagem(classe: str | None, escolhidas) -> str | None:
    """O lembrete quando a classe pede uma escolha de vantagem que o jogador ainda não fez."""
    faltam = rules.skill_advantage_missing(classe, escolhidas)
    if faltam <= 0:
        return None
    info = rules.CLASS_SKILL_ADVANTAGES[classe]
    if info.get("escolha"):
        return f"⚠️ Escolhe a vantagem da sua classe: {' ou '.join(info['escolha'])}. O menu fica na tela **Distribuir**."
    return f"⚠️ Escolhe {faltam} perícia{'s' if faltam > 1 else ''} com vantagem. O menu fica na tela **Distribuir**."


def embed_rolar_pericias(nome: str, pontos: dict, atributos: dict, classe: str | None, escolhidas, modo: str,
                         forcado: str | None, jogador: str | None = None) -> discord.Embed:
    """A tela principal das perícias: um ícone por perícia, e o bonus de cada uma já somado."""
    vantagens = rules.skills_with_advantage(classe, escolhidas)
    linhas = []
    for pericia in rules.SKILLS:
        atributo = forcado or rules.SKILL_DEFAULT_ATTRIBUTE[pericia]
        valor, pts = atributos[atributo], pontos.get(pericia, 0)
        linhas.append(
            f"{rules.SKILL_ICONS[pericia]} **{pericia}** {valor + pts:+d} · {rules.ATTRIBUTE_LABELS[atributo]} {valor} + {pts}"
            + (" ⭐" if pericia in vantagens else "")
        )
    corpo = "\n".join(linhas)
    if vantagens:
        corpo += "\n\n⭐ Vantagem da sua classe: entra sozinha na rolagem."
    aviso = _aviso_de_vantagem(classe, escolhidas)
    if aviso:
        corpo += f"\n\n{aviso}"
    _, rotulo = MODOS_DE_TESTE[modo]
    return embed_decorado(
        "Perícias", "Tocai no emblema da perícia e o dado rola sozinho: 1d20 + atributo + perícia, em nome do vosso personagem.",
        corpo, discord.Color.blurple(), autor=nome,
        rodape=f"Modo: {rotulo.lower()} · Atributo: {rules.ATTRIBUTE_LABELS[forcado] if forcado else 'automático (o padrão de cada perícia)'}"
        + (f" · jogador: {jogador}" if jogador else ""),
    )


def embed_pericias(nome: str, pontos: dict, total: int, selecionada: str, classe: str | None, escolhidas,
                   jogador: str | None = None) -> discord.Embed:
    """A tela de distribuir os pontos."""
    livres = total - sum(pontos.values())
    vantagens = rules.skills_with_advantage(classe, escolhidas)
    linhas = []
    for pericia in rules.SKILLS:
        pts = pontos.get(pericia, 0)
        seta = "▶️" if pericia == selecionada else "▫️"
        linhas.append(f"{seta} {rules.SKILL_ICONS[pericia]} {pericia} · **{pts}** {barra(pts, rules.SKILL_MAX_POINTS, rules.SKILL_MAX_POINTS)}" + (" ⭐" if pericia in vantagens else ""))
    if livres > 0:
        situacao = f"🎯 Pontos livres: **{livres}** de {total} (máximo {rules.SKILL_MAX_POINTS} em cada perícia)"
    elif livres == 0:
        situacao = f"✅ Todos os {total} pontos distribuídos"
    else:
        situacao = f"⚠️ **{-livres}** pontos a mais do que o permitido ({total}). Fala com um mestre."
    corpo = f"{situacao}\n\n" + "\n".join(linhas)
    if vantagens:
        corpo += "\n\n⭐ Vantagem da sua classe (entra sozinha na rolagem)."
    aviso = _aviso_de_vantagem(classe, escolhidas)
    if aviso:
        corpo += f"\n\n{aviso}"
    return embed_decorado(
        "Pontos de perícia", "Escolhei a perícia no menu e apertai +1 ou -1. Para lançar os dados, apertai Rolar perícias.",
        corpo, discord.Color.green() if livres == 0 else discord.Color.blurple(), autor=nome,
        rodape=f"jogador: {jogador}" if jogador else None,
    )


# ---------------------------------------------------------------------------
# Habilidades criadas pelos jogadores
# ---------------------------------------------------------------------------
def _linhas_da_habilidade(ab) -> list[tuple[str, str]]:
    campos = [("Descrição", ab["description"]), ("Efeito que você pediu", ab["effect_text"])]
    if ab["status"] == "aprovada":
        campos.append(("Custo e rolagem", f"{habil.texto_do_custo(ab)} · {habil.texto_da_rolagem(ab)}"))
    if ab["master_note"] and ab["status"] in ("ajuste", "recusada"):
        campos.append(("Nota do mestre", ab["master_note"]))
    return campos


def embed_habilidades(nome: str, habilidades: list, selecionada: int | None, jogador: str | None = None) -> discord.Embed:
    """A aba Habilidades do jogador: o caminho (criar, o mestre aprova, usar) e a lista com o status de cada uma."""
    if habilidades:
        corpo = "\n".join(
            f"{'▶️' if a['id'] == selecionada else '▫️'} {habil.MARCA[a['status']]} **{a['name']}** · {habil.FRASE[a['status']]}"
            for a in habilidades
        )
    else:
        corpo = "Você ainda não criou nenhuma habilidade. Aperta **➕ Criar habilidade** pra começar."
    embed = embed_decorado(
        "Habilidades", "1. Criai a vossa habilidade · 2. O mestre a ajusta e aprova · 3. Usai com um toque", corpo,
        discord.Color.purple(), autor=nome, rodape=f"jogador: {jogador}" if jogador else None,
    )
    escolhida = next((a for a in habilidades if a["id"] == selecionada), None)
    if escolhida is not None:
        for titulo, valor in _linhas_da_habilidade(escolhida):
            embed.add_field(name=titulo, value=valor[:1024], inline=False)
    return embed


def cartao_uso_habilidade(personagem: str, ab, uso, jogador: str | None = None) -> Cartao:
    """A mensagem pública de quando alguém usa uma habilidade: o que gastou e o que rolou."""
    cor = discord.Color.blurple()
    if uso.rolagem is not None:
        cor = discord.Color.red() if ab["roll_kind"] != "cura" else discord.Color.green()
    embed = tela(title=f"✨ {ab['name']}", description=_citar(ab["description"], True), color=cor)
    embed.set_author(name=f"{personagem} usou uma habilidade")
    if uso.custo:
        recurso, valor, resta, maximo = uso.custo
        embed.add_field(name="Custo", value=f"{rules.VITAL_EMOJI[recurso]} -{valor} de {rules.VITAL_LABELS[recurso]} (sobram {resta}/{maximo})", inline=False)
    if uso.rolagem is not None:
        conta = f"{ab['roll_dice']}: {uso.rolagem.describe()}"
        if uso.atributo:
            conta += f" + {uso.atributo[0]} {uso.atributo[1]}"
        rotulo = "Cura" if ab["roll_kind"] == "cura" else "Dano"
        embed.add_field(name=rotulo, value=f"🎲 {conta} = **{uso.total}**", inline=False)
    embed.add_field(name="O que ela faz", value=ab["effect_text"][:1024], inline=False)
    if jogador:
        embed.set_footer(text=f"jogador: {jogador}")
    return Cartao(embed, [])


def embed_fila(itens: list, selecionada, rascunho: dict) -> discord.Embed:
    """A tela do mestre: quantas esperam e, da escolhida, tudo o que ele precisa pra decidir. 'rascunho' é o que
    ele já marcou nos menus (ainda não gravado)."""
    esperando = sum(1 for i in itens if i["status"] == "pendente")
    ajuste = sum(1 for i in itens if i["status"] == "ajuste")
    topo = f"⏳ **{esperando}** aguardando · 🔧 **{ajuste}** em ajuste · ✅ {len(itens) - esperando - ajuste} aprovadas (as mais recentes)"
    if not itens:
        topo = "Nenhuma habilidade na fila por enquanto. Quando um jogador criar uma, ela aparece aqui."
    embed = tela(
        title="🛡️ Habilidades dos jogadores",
        description=topo + ("\n\nEscolhe uma no primeiro menu." if selecionada is None and itens else ""),
        color=discord.Color.dark_gold(),
    )
    if selecionada is not None:
        ab = selecionada
        quem = f"**{ab['character_name']}**" + (f" · <@{ab['user_id']}>" if ab["user_id"] else "")
        embed.add_field(name=f"{habil.MARCA[ab['status']]} {ab['name']}", value=f"{quem} · {habil.FRASE[ab['status']]}", inline=False)
        embed.add_field(name="Descrição", value=ab["description"][:1024], inline=False)
        embed.add_field(name="Efeito que o jogador pediu", value=ab["effect_text"][:1024], inline=False)
        embed.add_field(name="Como vai ficar (nos menus)", value=texto_do_rascunho(rascunho), inline=False)
        if ab["master_note"]:
            embed.add_field(name="Última nota", value=ab["master_note"][:1024], inline=False)
        embed.set_footer(text="Ajusta o custo e a rolagem nos menus. Depois: Aprovar, Pedir ajuste ou Recusar.")
    return embed


def texto_do_rascunho(r: dict) -> str:
    custo = f"{rules.VITAL_EMOJI[r['recurso']]} {r['valor']} de {rules.VITAL_LABELS[r['recurso']]}" if r.get("recurso") and r.get("valor") else "sem custo"
    if r.get("dado"):
        extra = f" + {rules.ATTRIBUTE_LABELS[r['atributo']]}" if r.get("atributo") else ""
        rolagem = f"{'cura' if r.get('tipo') == 'cura' else 'dano'} {r['dado']}{extra}"
    else:
        rolagem = "sem rolagem"
    return f"**Custo:** {custo}\n**Rolagem:** {rolagem}"


# ---------------------------------------------------------------------------
# Resultado especial (66 ou 77): tudo interrogação
# ---------------------------------------------------------------------------

def cartao_especial(valor: int) -> Cartao:
    """O cartão de um 66 ou 77 em qualquer sorteio de criação. Não diz o que saiu, nem de quem é, nem qual
    sorteio foi: é tudo interrogação. O 77 é amarelo e o 66 é vermelho. A imagem é opcional
    (assets/especial-66 e especial-77). Quem decide o destino é um mestre."""
    info = lore.ESPECIAL[valor]
    nome_campo, texto_campo = lore.ESPECIAL_CAMPO
    return _montar(
        enfeitar=False,
        autor=lore.ESPECIAL_AUTOR, titulo=lore.ESPECIAL_TITULO, cor=info["cor"], topo=lore.ESPECIAL_DIVISOR,
        texto=lore.ESPECIAL_TEXTO, italico=True, campos=[(nome_campo, texto_campo, False)],
        imagem=achar_imagem("especial", str(valor)), rodape=lore.ESPECIAL_RODAPE,
    )


# ---------------------------------------------------------------------------
# Classe
# ---------------------------------------------------------------------------

_LIMITE_DO_CAMPO = 1000   # o Discord aceita 1024 caracteres por campo; sobra uma folga


def _texto_da_habilidade(opcao: dict) -> list[str]:
    """As linhas de uma habilidade: as marcas (tipo e custo), a frase e cada efeito."""
    linhas = [f"*{' · '.join(opcao['marcas'])}*", f"*{opcao['frase']}*"]
    linhas += [f"**{rotulo}** {texto}" for rotulo, texto in opcao["efeitos"]]
    return linhas


def _campos_da_habilidade(classe: str, escolhida: str | None = None, modo: str = "comando") -> list[tuple[str, str, bool]]:
    """Os campos do embed com a habilidade inicial da classe (uma, ou as duas opções). Cada campo cabe nos
    1024 caracteres do Discord: um texto mais comprido continua num campo seguinte.
    modo: 'comando' (manda usar o /habilidade), 'botao' (tem botões embaixo) ou 'previa' (botões, e a escolha
    ainda não vale: só depois de confirmar)."""
    info = lore.HABILIDADES[classe]
    campos: list[tuple[str, str, bool]] = []
    if info["escolha"]:
        nomes = " ou ".join(f"**{o['nome']}**" for o in info["opcoes"])
        como = "Use `/habilidade` pra escolher." if modo == "comando" else "Aperta um dos botões abaixo."
        if escolhida:
            situacao = f"Você vai levar **{escolhida}**. Confirma nos botões abaixo." if modo == "previa" else f"Você levou **{escolhida}**."
        else:
            situacao = f"Escolha uma das duas: {nomes}. {como}"
        campos.append(("Habilidade de classe", situacao, False))
    for opcao in info["opcoes"]:
        nome = f"✨ {opcao['nome']}" + (" ✅" if info["escolha"] and escolhida == opcao["nome"] else "")   # o ✅ só faz sentido onde há escolha
        atual, tamanho, parte = [], 0, 1
        for linha in _texto_da_habilidade(opcao):
            if atual and tamanho + len(linha) + 1 > _LIMITE_DO_CAMPO:
                campos.append((nome if parte == 1 else f"{nome} (continua)", "\n".join(atual), False))
                atual, tamanho, parte = [], 0, parte + 1
            atual.append(linha)
            tamanho += len(linha) + 1
        campos.append((nome if parte == 1 else f"{nome} (continua)", "\n".join(atual), False))
    return campos


def _campos_da_classe(classe: str, escolhida: str | None = None, modo: str = "comando") -> list[tuple[str, str, bool]]:
    b = rules.CLASSES[classe]
    return [
        ("Vantagem nas perícias", rules.CLASS_SKILLS[classe], False),
        ("Bônus", f"Vida +{b['vida']} · Sanidade +{b['sanidade']} · Mana +{b['mana']} · Estamina +{b['estamina']}", False),
        ("Combina com (exemplos)", " · ".join(lore.CLASSE_COMBINA[classe]), False),
        *_campos_da_habilidade(classe, escolhida, modo),
    ]


def _descricao_da_classe(classe: str) -> str:
    return f"**{lore.CLASSE_FRASE[classe]}**\n{lore.DIVISOR}\n\n{_citar(lore.CLASSES[classe], True)}"


def cartao_classe(personagem: str, classe: str, proximo: str, jogador: str | None = None,
                  escolhida: str | None = None, com_botoes: bool = False) -> Cartao:
    return _montar(
        autor=f"🎓 Classe de {personagem}",
        titulo=classe,
        cor=lore.COR_CLASSE,
        topo=_descricao_da_classe(classe),
        campos=[*_campos_da_classe(classe, escolhida, "botao" if com_botoes else "comando"), ("Continue a criação", proximo, False)],
        imagem=achar_imagem("classe", classe),
        rodape=f"jogador: {jogador}" if jogador else None,
    )


def cartao_habilidade(personagem: str, classe: str, escolhida: str | None, jogador: str | None = None,
                      modo: str = "comando") -> Cartao:
    """A habilidade de classe do personagem (ou as duas opções, se ele ainda não escolheu). modo: ver
    _campos_da_habilidade."""
    return _montar(
        autor=f"✨ Habilidade de {personagem}",
        titulo=classe,
        cor=lore.COR_CLASSE,
        topo=f"**{lore.CLASSE_FRASE[classe]}**\n{lore.DIVISOR}",
        campos=_campos_da_habilidade(classe, escolhida, modo),
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


def previa_classe(personagem: str, classe: str, habilidade: str | None = None) -> discord.Embed:
    """A classe como prévia, pro menu de escolha do painel. É mensagem privada, que não leva anexo: só usa
    imagem se for um link direto (IMAGENS_URL). Nas classes com duas habilidades, 'habilidade' é a que está
    marcada nos botões (a escolha só vale depois de confirmar)."""
    if not rules.class_needs_ability_choice(classe):
        rodape = "Se for essa, aperta **Confirmar classe**. Vale uma vez só."
    elif habilidade is None:
        rodape = "Escolhe a habilidade nos botões e depois confirma. Vale uma vez só, a classe e a habilidade juntas."
    else:
        rodape = "Se for essa, aperta **Confirmar classe e habilidade**. Vale uma vez só."
    embed = tela(
        title=f"🎓 {classe}",
        description=f"{_descricao_da_classe(classe)}\n\n{rodape}",
        color=lore.COR_CLASSE,
    )
    embed.set_author(name=f"Classe de {personagem}")
    for nome, valor, em_linha in _campos_da_classe(classe, habilidade, "previa"):
        embed.add_field(name=nome, value=valor, inline=em_linha)
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
    embed = tela(
        title="🩸 Disciplinas" + (f" de {nome}" if nome and tem else ""), color=COR_DISCIPLINA,
    )
    if tem:
        embed.description += "\n\n" + (
            f"{lore.DIVISOR_CURTO}\n\n{linha_de_pontos(nivel, raca, graus)}\n"
            "Escolhe uma no menu pra ler o texto de cada grau e subir."
        )
    else:
        embed.description += "\n\n" + (
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
    embed = tela(
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

def _marca_da_sorte(marcas: list[str] | None) -> str:
    """A marca que o cartão mostra quando o mestre mexeu na sorte da rolagem (vazia se não mexeu, ou se foi discreto)."""
    if not marcas:
        return ""
    emoji = "🍀"   # sorte do mestre
    if all(m.startswith("modo ") for m in marcas):
        emoji = "🎲"   # o modo que o jogador escolheu
    elif all(m.startswith("classe: ") for m in marcas):
        emoji = "⭐"   # a vantagem da classe
    return f"{emoji} {' · '.join(marcas)}"


def cartao_rolagens(quem: str, notacao: str, resultados: list["dice.RollResult"], motivo: str | None,
                    jogador: str, com_personagem: bool, marcas: list[list[str]] | None = None) -> Cartao:
    """O cartão de um N#dado (3#d20+5): uma linha por rolagem, e o maior e o menor no fim."""
    marcas = marcas or [[] for _ in resultados]
    linhas = []
    for i, (r, m) in enumerate(zip(resultados, marcas), 1):
        linha = f"**{i}.** {r.describe()} = **{r.total}**"
        if r.sides == 20 and len(r.rolls) == 1:
            linha += " 🌟" if r.rolls[0] == 20 else " 💀" if r.rolls[0] == 1 else ""
        if _marca_da_sorte(m):
            linha += f" · {_marca_da_sorte(m)}"
        linhas.append(linha)
    totais = [r.total for r in resultados]
    linhas.append(f"\n⬆️ Maior **{max(totais)}** · ⬇️ Menor **{min(totais)}**")
    tem_20 = any(r.sides == 20 and len(r.rolls) == 1 and r.rolls[0] == 20 for r in resultados)
    embed = discord.Embed(
        title=f"🎲 {quem} rolou {notacao}", description="\n".join(linhas),
        color=discord.Color.gold() if tem_20 else discord.Color.dark_red(),
    )
    rodape = []
    if motivo:
        rodape.append(motivo)
    if com_personagem:
        rodape.append(f"jogador: {jogador}")
    if rodape:
        embed.set_footer(text=" · ".join(rodape))
    return Cartao(embed, [])


def cartao_rolagem(quem: str, notacao: str, resultado: "dice.RollResult", motivo: str | None,
                   jogador: str, com_personagem: bool, marcas: list[str] | None = None) -> Cartao:
    descricao = f"**{resultado.describe()} = {resultado.total}**"
    cor = discord.Color.dark_red()
    if resultado.sides == 20 and len(resultado.rolls) == 1:  # destaque só no visual, sem efeito de regra
        if resultado.rolls[0] == 20:
            descricao += "\n🌟 **20 natural!**"
            cor = discord.Color.gold()
        elif resultado.rolls[0] == 1:
            descricao += "\n💀 **1 natural!**"
            cor = discord.Color.dark_grey()
    if _marca_da_sorte(marcas):
        descricao += f"\n{_marca_da_sorte(marcas)}"
    embed = discord.Embed(title=f"🎲 {quem} rolou {notacao}", description=descricao, color=cor)
    rodape = []
    if motivo:
        rodape.append(motivo)
    if com_personagem:
        rodape.append(f"jogador: {jogador}")
    if rodape:
        embed.set_footer(text=" · ".join(rodape))
    return Cartao(embed, [])
