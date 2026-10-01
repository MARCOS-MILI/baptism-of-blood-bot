"""Bot de Discord do Baptism of Blood.

Jogadores:
  /rolar dado:1d20+3 [motivo] [personagem]   -> rola e salva no histórico
  d20+5 (direto no chat, sem barra)          -> também rola e salva; +d20+5 ataque usa o texto como motivo
  /historico [usuario] [limite] [personagem] -> últimas rolagens de alguém (ou de um personagem)
  /personagem criar | usar | listar | excluir -> gerencia os personagens (limite de vagas por jogador)
  /raca_inicial | /classe_social | /magia_inicial -> sorteios de criação, uma vez por personagem (a magia só pra quem tem)
  /classe [personagem]                       -> escolhe a classe (uma vez)
  /atributos [forca..alma] [personagem]      -> distribui os pontos de atributo (só aumenta)
  /minha_ficha [personagem]                  -> a ficha com botões (sorteios, classe, atributos, dados)
  /dados                                     -> bandeja de dados com botões (d4 a d100)
  /iniciativa | /intencao                    -> entrar na cena do canal e mandar a intenção pro mestre
  /mestre escudo                             -> o Escudo do Mestre (iniciativa e intenções)
  /niveis [personagem]                       -> XP e vantagens de cada nível
  /extrato_xp [personagem]                   -> de onde veio o XP do personagem
  /rank [tipo] [limite]                      -> rank público de XP total (personagens ou jogadores)
  /calcular_recursos                         -> simula Vida, Sanidade, Mana e Estamina (por nível)
  /ajuda [comando]                           -> ensina a usar o bot e explica cada comando (também /help)

Ordem da criação: /personagem criar, /raca_inicial e /classe_social (em qualquer ordem), /classe, /magia_inicial
(só pra Vampiro, Dhampir e pras classes Feiticeiros e Mestre de Forja) e /atributos.
Só com a ficha pronta abrem /rolar, /historico, /extrato_xp e /rank (os mestres passam direto).

Mestres:
  /mestre dar_xp | upar | corrigir_nivel | rank_pericia
  /mestre apagar | corrigir_magia | corrigir_raca | corrigir_estado
  /mestre ficha | jogador | vagas | excluir_personagem | apagar_historico
  /mestre atributos | corrigir_classe | exportar

Setup rápido:
  1. pip install -r requirements.txt
  2. Cria um arquivo .env com DISCORD_TOKEN=seu_token_aqui (veja o README)
  3. python bot.py
"""

import os
import sys
import tempfile
import traceback
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

import ajuda
import db
import dice
import escudo
import paineis
import rules
import vitrine

load_dotenv()
TOKEN = os.environ.get("DISCORD_TOKEN")

# Quem tem esse cargo (ou a permissão de Gerenciar Servidor) pode usar os comandos /mestre.
MESTRE_ROLE = os.environ.get("MESTRE_ROLE", "Mestre")
# Esconde os comandos /mestre de quem não tem a permissão Gerenciar servidor (eles nem aparecem na lista). Pra o cargo
# Mestre ver, libera no Discord: Configurações do servidor > Integrações > o bot > Comandos > /mestre > adiciona o cargo.
ESCONDER_COMANDOS_DE_MESTRE = os.environ.get("ESCONDER_COMANDOS_DE_MESTRE", "1") != "0"

# Quantos personagens cada jogador pode ter. Os mestres liberam vagas extras na mão, até o teto.
LIMITE_BASE = int(os.environ.get("LIMITE_PERSONAGENS", "3"))
LIMITE_MAXIMO = max(LIMITE_BASE, int(os.environ.get("LIMITE_MAXIMO_PERSONAGENS", "10")))
MAX_VAGAS_EXTRAS = LIMITE_MAXIMO - LIMITE_BASE

NOME_MIN, NOME_MAX = 2, 60


def _flag_ligada(nome: str) -> bool:
    """Variável de ambiente ligada por padrão. Só desliga com 0, false, nao, não ou off."""
    return os.environ.get(nome, "1").strip().casefold() not in ("0", "false", "nao", "não", "off")


# Chavinha de segurança: ORDEM_DA_CRIACAO=0 no Railway libera tudo de novo (como era antes da ordem),
# sem precisar de deploy. Desligada, o bot não bloqueia nenhum comando por causa da ficha.
ORDEM_DA_CRIACAO = _flag_ligada("ORDEM_DA_CRIACAO")

# Dados escritos direto no chat (d20+5), sem barra. Precisa que o "Message Content Intent" esteja ligado no
# Portal do Desenvolvedor (Bot > Privileged Gateway Intents). Se não estiver, o bot detecta na partida, avisa
# no log e sobe sem essa parte (veja main()). DADOS_POR_TEXTO=0 desliga de propósito.
DADOS_POR_TEXTO = _flag_ligada("DADOS_POR_TEXTO")
ajuda.ativar_dados_por_texto(DADOS_POR_TEXTO)


class Arvore(app_commands.CommandTree):
    """Antes de cada comando, guarda o nome atual do jogador (o rank usa isso pra mostrar o dono)."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        try:
            db.remember_player(str(interaction.user.id), str(interaction.user.display_name))
        except Exception as e:  # nunca deixar de responder um comando por causa disso
            print(f"Não consegui guardar o nome do jogador: {e!r}", flush=True)
        return True


intents = discord.Intents.default()
intents.message_content = DADOS_POR_TEXTO
# Ninguém consegue fazer o bot marcar @everyone ou cargos através de um nome de personagem.
bot = commands.Bot(
    command_prefix="!", intents=intents, tree_cls=Arvore,
    allowed_mentions=discord.AllowedMentions.none(),
)

_comandos_sincronizados = False


@bot.event
async def on_ready():
    global _comandos_sincronizados
    # on_ready pode disparar de novo quando a conexão cai e volta. Só precisa sincronizar uma vez.
    if not _comandos_sincronizados:
        await bot.tree.sync()
        _comandos_sincronizados = True
    print(f"Conectado como {bot.user}. Banco: {db.DB_PATH} (origem: {db.DB_SOURCE})", flush=True)
    print(f"Dados por texto (d20+5 no chat): {'ligado' if DADOS_POR_TEXTO else 'desligado'}", flush=True)
    if not db.storage_is_persistent():
        print(
            "AVISO: o banco está na pasta do bot e some a cada redeploy. "
            "No Railway, anexe um Volume ao serviço (veja o README).",
            flush=True,
        )


# ---------------------------------------------------------------------------
# Erros e permissão de mestre
# ---------------------------------------------------------------------------

def _membro_eh_mestre(membro) -> bool:
    perms = getattr(membro, "guild_permissions", None)
    if perms and (perms.administrator or perms.manage_guild):
        return True
    cargo = MESTRE_ROLE.casefold()
    return any(r.name.casefold() == cargo for r in getattr(membro, "roles", []))


def _eh_mestre(interaction: discord.Interaction) -> bool:
    return _membro_eh_mestre(interaction.user)


def _cargo_mestre(guild: discord.Guild | None):
    """O cargo de mestre do servidor, se existir (usado pra avisar os mestres)."""
    if guild is None:
        return None
    cargo = MESTRE_ROLE.casefold()
    return next((r for r in guild.roles if r.name.casefold() == cargo), None)


class FichaIncompleta(app_commands.CheckFailure):
    """Comando de jogo usado antes de a ficha estar pronta. A mensagem já vem pronta pra mostrar."""

    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


_SEM_PERSONAGEM = "Você ainda não tem personagem. Começa por `/personagem criar`; o passo a passo está em `/ajuda`."


async def _exigir_personagem_pronto(interaction: discord.Interaction) -> bool:
    """Pra comandos que agem como o personagem (rolar, extrato de XP): o personagem usado precisa estar com a
    ficha pronta. Os mestres passam direto."""
    if not ORDEM_DA_CRIACAO or _eh_mestre(interaction):
        return True
    uid = str(interaction.user.id)
    nome = getattr(interaction.namespace, "personagem", None)
    if nome:
        char = db.find_character(uid, nome)
        if char is None:
            return True  # o próprio comando avisa que não achou o personagem
    else:
        char = db.get_active_character(uid)
        if char is None:
            raise FichaIncompleta(_SEM_PERSONAGEM)
    status = rules.creation_status(char)
    if status["pronta"]:
        return True
    raise FichaIncompleta(ajuda.texto_bloqueio(char["name"], status))


async def _exigir_algum_personagem_pronto(interaction: discord.Interaction) -> bool:
    """Pra comandos que não usam um personagem (histórico, rank): vale ter pelo menos um com a ficha pronta."""
    if not ORDEM_DA_CRIACAO or _eh_mestre(interaction):
        return True
    uid = str(interaction.user.id)
    chars = db.list_characters(uid)
    if not chars:
        raise FichaIncompleta(_SEM_PERSONAGEM)
    if any(rules.creation_status(c)["pronta"] for c in chars):
        return True
    ativo = db.get_active_character(uid) or chars[0]
    raise FichaIncompleta(ajuda.texto_bloqueio(ativo["name"], rules.creation_status(ativo)))


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, FichaIncompleta):
        msg = error.mensagem
    elif isinstance(error, app_commands.CheckFailure):
        msg = f"⛔ Esse comando é só pra mestre (quem tem o cargo **{MESTRE_ROLE}** ou a permissão de Gerenciar Servidor)."
    else:
        nome = interaction.command.qualified_name if interaction.command else "?"
        print(f"Erro no comando /{nome}: {error!r}", flush=True)
        traceback.print_exception(type(error), error, error.__traceback__)
        msg = "⚠️ Deu erro aqui do meu lado. Tenta de novo, e se repetir avisa quem cuida do bot."
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)


# ---------------------------------------------------------------------------
# Ajudas
# ---------------------------------------------------------------------------

def _dono_do_autocomplete(interaction: discord.Interaction) -> str:
    """De quem listar os personagens: do 'usuario' já escolhido no comando, ou de quem digitou."""
    alvo = getattr(interaction.namespace, "usuario", None)
    if alvo is not None:
        try:
            return str(int(getattr(alvo, "id", alvo)))
        except (TypeError, ValueError):
            pass
    return str(interaction.user.id)


async def _autocomplete_personagem(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    busca = current.casefold()
    escolhas = [
        app_commands.Choice(name=p["name"][:100], value=p["name"])
        for p in db.list_characters(_dono_do_autocomplete(interaction))
        if busca in p["name"].casefold()
    ]
    return escolhas[:25]


def _resolver(user_id: str, nome: str | None):
    """Personagem do próprio jogador (pelo nome, ou o ativo). Devolve (personagem, mensagem_de_erro)."""
    personagem = db.resolve_character(user_id, nome)
    if personagem:
        return personagem, None
    if nome:
        return None, f"Não achei nenhum personagem seu chamado **{nome}**. Use `/personagem listar` pra ver os seus."
    return None, "Você ainda não tem personagem. Cria um com `/personagem criar` e tenta de novo."


def _resolver_do_alvo(alvo: discord.Member, nome: str | None):
    """Mesma coisa, mas pro personagem de outro jogador (usado nos comandos de mestre)."""
    personagem = db.resolve_character(str(alvo.id), nome)
    if personagem:
        return personagem, None
    if nome:
        return None, f"{alvo.display_name} não tem nenhum personagem chamado **{nome}**."
    return None, f"{alvo.display_name} ainda não tem personagem criado."


def _juntar(itens: list[str]) -> str:
    """['a', 'b', 'c'] vira 'a, b e c'."""
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


def _quando(iso: str) -> str:
    """Data e hora no fuso de quem está lendo (o Discord converte sozinho)."""
    try:
        epoch = int(datetime.fromisoformat(iso).timestamp())
    except ValueError:
        return iso[:16].replace("T", " ") + " UTC"
    return f"<t:{epoch}:d> <t:{epoch}:t>"


def _mais(n: int) -> str:
    """1250 vira '+1.250', -500 vira '-500'."""
    return ("+" if n > 0 else "-" if n < 0 else "") + rules.fmt_xp(abs(n))


def _vagas(user_id: str) -> tuple[int, int, int]:
    """(vagas usadas, vagas permitidas, vagas extras) do jogador."""
    extras = db.get_extra_slots(user_id)
    permitidas = min(LIMITE_BASE + extras, LIMITE_MAXIMO)
    return len(db.list_characters(user_id)), permitidas, extras


_PASSO_ESPECIAL = {"race": "raca", "social_class": "estado", "magic_rank": "magia"}
_QUESTAO = "❓ ???"


def _especial_de(personagem, campo: str) -> int | None:
    """66 ou 77 se o sorteio desse campo ('race', 'social_class' ou 'magic_rank') caiu num resultado especial
    e ainda espera o mestre."""
    return rules.special_result(personagem, _PASSO_ESPECIAL[campo])


def _texto_especial(personagem, campo: str, para_mestre: bool = False) -> str | None:
    """O que a ficha mostra num resultado especial: só interrogação. Os mestres veem também o número."""
    valor = _especial_de(personagem, campo)
    if not valor:
        return None
    return f"{_QUESTAO}\n(aguardando o mestre" + (f", tirou {valor}" if para_mestre else "") + ")"


MAX_CARGOS_MARCADOS = 5


def _ping_mestre(guild: discord.Guild | None, admins: bool = False) -> dict:
    """A marcação de quem decide: o cargo de mestre e, com admins=True, também os cargos de administrador do
    servidor (os de bot e o @everyone ficam de fora; no máximo 5, pra não marcar meio servidor). Vazia se
    não tem ninguém pra marcar."""
    cargos = []
    mestre = _cargo_mestre(guild)
    if mestre:
        cargos.append(mestre)
    if admins and guild is not None:
        for r in guild.roles:
            permissoes = getattr(r, "permissions", None)
            if (getattr(permissoes, "administrator", False) and not getattr(r, "managed", False)
                    and r.name != "@everyone" and r not in cargos):
                cargos.append(r)
    cargos = cargos[:MAX_CARGOS_MARCADOS]
    if not cargos:
        return {}
    return {"content": " ".join(c.mention for c in cargos), "allowed_mentions": discord.AllowedMentions(roles=cargos)}


def _raca_curta(personagem) -> str:
    return personagem["race"] or (_QUESTAO if _especial_de(personagem, "race") else "sem raça")


def _texto_habilidade(personagem) -> str:
    """A linha da habilidade de classe na ficha: o nome, ou o aviso de que falta escolher entre as duas."""
    habilidade = rules.class_ability_of(personagem)
    return f"✨ {habilidade}" if habilidade else "✨ falta escolher (botão **Habilidade** ou `/habilidade`)"


def _texto_definicao(personagem, campo: str, comando: str, para_mestre: bool = False) -> str:
    especial = _texto_especial(personagem, campo, para_mestre)
    if especial:
        return especial
    valor = personagem[campo]
    if not valor:
        return f"ainda não definido\n(use `{comando}`)"
    rolagem = personagem[f"{campo}_roll"]
    origem = "definido por um mestre" if rolagem is None else f"1d100: {rolagem}"
    return f"{valor}\n({origem})"


_SEM_MAGIA = "só Vampiros, Dhampirs, Feiticeiros e Mestres de Forja têm magia"


def _texto_magia(personagem, para_mestre: bool = False) -> str:
    """O campo 'Rank de Magia' da ficha: depende de a raça e a classe terem magia."""
    especial = _texto_especial(personagem, "magic_rank", para_mestre)
    if especial:
        return especial
    acesso = rules.magic_access(personagem["race"], personagem["class_name"])
    if personagem["magic_rank"]:
        texto = _texto_definicao(personagem, "magic_rank", "/magia_inicial")
        if acesso == "nao":
            texto += "\n⚠️ raça e classe sem magia, fala com um mestre"
        return texto
    if acesso == "nao":
        return f"sem magia\n({_SEM_MAGIA})"
    if acesso == "sim":
        return "ainda não definido\n(use `/magia_inicial`)"
    return "depende da raça e da classe\n(fica claro depois de escolher as duas)"


def _magia_curta(personagem) -> str:
    if _especial_de(personagem, "magic_rank"):
        return _QUESTAO
    if personagem["magic_rank"]:
        return personagem["magic_rank"]
    return "sem magia" if rules.magic_access(personagem["race"], personagem["class_name"]) == "nao" else "sem rank"


def _nota_magia(antes, depois) -> str | None:
    """Pros mestres: avisa quando mudar a raça ou a classe muda se o personagem tem magia."""
    a0 = rules.magic_access(antes["race"], antes["class_name"])
    a1 = rules.magic_access(depois["race"], depois["class_name"])
    if a0 == a1:
        return None
    nome = depois["name"]
    if a1 == "sim" and not depois["magic_rank"]:
        return f"Agora **{nome}** tem magia e precisa sortear o Rank de magia com `/magia_inicial`."
    if a1 == "nao":
        if depois["magic_rank"]:
            return (
                f"Com essa combinação **{nome}** não tem magia. O Rank de magia ({depois['magic_rank']}) "
                "continua na ficha; use `/mestre apagar` se quiser tirar."
            )
        return f"Com essa combinação **{nome}** não tem magia."
    return None


def _resumo_estado(personagem) -> str | None:
    """'2º Estado (Nobreza)', '1º Estado (Clero), Alto Clero' ou 'aguardando o mestre'."""
    estado = personagem["social_class"]
    if _especial_de(personagem, "social_class"):
        return _QUESTAO
    if not estado:
        return None
    if estado == dice.SOCIAL_CLASS_MASTER:
        return "aguardando o mestre"
    texto = rules.ESTADO_LABELS.get(estado, estado)
    if personagem["clergy"]:
        texto += f", {personagem['clergy']}"
    return texto


def _texto_estado(personagem, para_mestre: bool = False) -> str:
    especial = _texto_especial(personagem, "social_class", para_mestre)
    if especial:
        return especial
    resumo = _resumo_estado(personagem)
    if not resumo:
        return "ainda não definido\n(use `/classe_social`)"
    r1, r2 = personagem["social_class_roll"], personagem["clergy_roll"]
    if personagem["social_class"] == dice.SOCIAL_CLASS_MASTER:
        return f"{resumo}\n(tirou {r1}, fala com um mestre)"
    if r1 is None:
        origem = "definido por um mestre"
    else:
        origem = f"1d100: {r1}" + (f" e {r2}" if r2 is not None else "")
    return f"{resumo}\n({origem})"


def _barra_xp(xp: int) -> str:
    """'Nível 3: 1.250/3.000 XP' com a barra embaixo, ou 'Nível 10: máximo'."""
    nivel, dentro, precisa = rules.xp_progress(xp)
    if precisa is None:
        return f"Nível {nivel}: máximo"
    return f"Nível {nivel}: {rules.fmt_xp(dentro)}/{rules.fmt_xp(precisa)} XP\n{rules.xp_bar(dentro, precisa)}"


def _recursos_do_personagem(personagem):
    """Vida, Sanidade, Mana e Estamina somados nível a nível, com o atributo que o personagem tinha em cada
    nível, mais o bônus da classe uma vez só. None enquanto não tem classe."""
    classe = personagem["class_name"]
    if not classe:
        return None
    return rules.calculate_resources_by_level(db.attributes_per_level(personagem), classe)


def _texto_recursos(res) -> str:
    return (
        f"❤️ Vida **{res['vida']['total']}** · 🧠 Sanidade **{res['sanidade']['total']}**\n"
        f"🔮 Mana **{res['mana']['total']}** · 💪 Estamina **{res['estamina']['total']}**"
    )


def _texto_pontos(personagem) -> str:
    total = rules.attribute_points_total(personagem["level"])
    usados = sum(db.attributes_of(personagem).values())
    livres = total - usados
    if livres > 0:
        sobra = f" ({livres} {'livre' if livres == 1 else 'livres'})"
    elif livres < 0:
        sobra = f" (passou {-livres})"
    else:
        sobra = ""
    return f"Pontos de atributo: {usados} de {total} usados{sobra}"


_SEM_CLASSE = "escolha a classe com `/classe` pra ver Vida, Sanidade, Mana e Estamina"


def _embed_atributos(personagem, titulo: str) -> discord.Embed:
    embed = discord.Embed(title=titulo, color=discord.Color.dark_green())
    embed.add_field(
        name="Atributos",
        value=rules.describe_attributes(db.attributes_of(personagem)) + "\n" + _texto_pontos(personagem),
        inline=False,
    )
    res = _recursos_do_personagem(personagem)
    embed.add_field(name="Recursos", value=_texto_recursos(res) if res else _SEM_CLASSE, inline=False)
    return embed


def _embed_ficha(personagem, jogador: str, para_mestre: bool = False) -> discord.Embed:
    nivel, xp = personagem["level"], personagem["xp"]
    _, dentro, precisa = rules.xp_progress(xp)
    embed = discord.Embed(title=f"📖 Ficha de {personagem['name']}", color=vitrine.cor_da_ficha(personagem))
    embed.set_author(name=vitrine.resumo_da_ficha(personagem))
    miniatura = vitrine.miniatura_da_ficha(personagem)
    if miniatura:
        embed.set_thumbnail(url=miniatura)
    status = rules.creation_status(personagem)
    if ORDEM_DA_CRIACAO and not status["pronta"]:
        embed.description = f"⚠️ **Ficha incompleta.** {ajuda.proximo_passo(status)} Veja o passo a passo em `/ajuda`."
    nivel_txt = f"{nivel}/{rules.MAX_LEVEL}\n{rules.bar(nivel, rules.MAX_LEVEL)}\nXP total: {rules.fmt_xp(xp)}"
    if precisa is not None:
        nivel_txt += f"\nFaltam {rules.fmt_xp(precisa - dentro)} pro nível {nivel + 1}"
    embed.add_field(name="Nível", value=nivel_txt, inline=True)
    embed.add_field(name="Raça", value=_texto_definicao(personagem, "race", "/raca_inicial", para_mestre), inline=True)
    embed.add_field(name="Classe Social", value=_texto_estado(personagem, para_mestre), inline=True)
    embed.add_field(name="Rank de Magia", value=_texto_magia(personagem, para_mestre), inline=True)
    classe = personagem["class_name"]
    embed.add_field(
        name="Classe",
        value=(
            f"{classe}\n(vantagem em {rules.CLASS_SKILLS.get(classe, 'perícias da classe')})\n{_texto_habilidade(personagem)}"
            if classe else "ainda não definida\n(use `/classe`)"
        ),
        inline=True,
    )
    embed.add_field(
        name="Atributos",
        value=rules.describe_attributes(db.attributes_of(personagem)) + "\n" + _texto_pontos(personagem),
        inline=False,
    )
    res = _recursos_do_personagem(personagem)
    embed.add_field(name="Recursos", value=_texto_recursos(res) if res else _SEM_CLASSE, inline=False)
    if rules.has_disciplines(personagem["race"]):
        embed.add_field(
            name="Disciplinas",
            value=vitrine.texto_disciplinas_da_ficha(personagem, db.get_disciplines(personagem["id"])),
            inline=False,
        )
    ranks = db.get_skill_ranks(personagem["id"])
    linhas = [
        f"**{pericia}** {ranks[pericia]}/{rules.MAX_SKILL_RANK} {rules.bar(ranks[pericia], rules.MAX_SKILL_RANK)}"
        for pericia in rules.SPECIAL_SKILLS
        if ranks.get(pericia)
    ]
    embed.add_field(
        name="Ranks das perícias especiais",
        value="\n".join(linhas) or "nenhum Rank ainda",
        inline=False,
    )
    embed.set_footer(text=f"jogador: {jogador}")
    return embed


# ---------------------------------------------------------------------------
# Rolagens e histórico
# ---------------------------------------------------------------------------

def _rolar_com_sorte(char, notacao: str, extras=()):
    """Rola a notação (que pode ser um N#dado, tipo 3#d20+5) já com a sorte que o mestre pôs no personagem, e
    gasta os usos dela. Devolve (resultados, marcas de cada um). Levanta DiceError se a notação for inválida."""
    efeitos = []
    if char:
        efeitos = [
            dice.EfeitoDeSorte(e["id"], e["kind"], e["value"], e["uses_left"], bool(e["quiet"]))
            for e in db.get_dice_effects(char["id"])
        ]
    resultados, marcas, usados = dice.roll_many(notacao, efeitos + list(extras))
    if usados:
        db.use_dice_effects([i for i in usados if i > 0])   # os extras (id negativo) não são do banco
    return resultados, marcas


def _registrar_e_montar_cartao(uid: str, jogador: str, guild_id: str | None, char, notacao: str,
                               motivo: str | None, resultados, marcas):
    """Guarda cada rolagem no histórico (um N#dado vira uma linha por rolagem) e monta o cartão."""
    vezes, expr = dice.split_repeticao(notacao)
    for r in resultados:
        db.log_roll(
            user_id=uid, username=jogador, guild_id=guild_id,
            notation=notacao if vezes == 1 else expr.strip(),
            rolls=r.rolls, total=r.total, purpose=motivo,
            character_id=char["id"] if char else None,
            character_name=char["name"] if char else None,
        )
    quem = char["name"] if char else jogador
    if vezes == 1:
        return vitrine.cartao_rolagem(quem, notacao, resultados[0], motivo, jogador, bool(char), marcas[0])
    return vitrine.cartao_rolagens(quem, notacao, resultados, motivo, jogador, bool(char), marcas)


@bot.tree.command(name="rolar", description="Rola um dado (ex: 1d20, 2d6+3, 3#d20+5) e guarda no histórico.")
@app_commands.describe(
    dado="Notação do dado: 1d20, 2d6+3, ou 3#d20+5 pra rolar o d20+5 três vezes, cada uma separada",
    motivo="Opcional: pra que é essa rolagem",
    personagem="Opcional: rolar por outro personagem seu (padrão: o que você está usando)",
)
@app_commands.autocomplete(personagem=_autocomplete_personagem)
@app_commands.check(_exigir_personagem_pronto)
async def rolar(interaction: discord.Interaction, dado: str, motivo: str | None = None, personagem: str | None = None):
    await _executar_rolagem(interaction, dado, motivo, personagem)


async def _executar_rolagem(interaction, dado: str, motivo: str | None, personagem: str | None, extras=()) -> None:
    """O que o /rolar faz, pra o teste de perícia do painel usar também. 'extras' são efeitos de dado que não vêm do
    banco (o modo vantagem ou desvantagem que o jogador escolheu)."""
    uid = str(interaction.user.id)
    try:  # confere a notação antes de qualquer coisa, sem rolar e sem gastar a sorte do personagem
        dice.validate(dado)
    except dice.DiceError as e:
        await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
        return

    if personagem:
        char = db.find_character(uid, personagem)
        if not char:
            await interaction.response.send_message(
                f"Não achei nenhum personagem seu chamado **{personagem}**. Use `/personagem listar` pra ver os seus.",
                ephemeral=True,
            )
            return
    else:
        char = db.get_active_character(uid)  # pode ser None: rolar sem personagem continua valendo

    resultados, marcas = _rolar_com_sorte(char, dado, extras)
    cartao = _registrar_e_montar_cartao(
        uid, str(interaction.user.display_name), str(interaction.guild_id) if interaction.guild_id else None,
        char, dado, motivo, resultados, marcas,
    )
    await interaction.response.send_message(**cartao.kwargs())


async def _teste_de_pericia(coletor, notacao: str, motivo: str, personagem: str, modo: str) -> None:
    """O ícone da aba Perícias: rola 1d20 + atributo + perícia no nome do personagem do painel. Com a ficha ainda
    incompleta não rola (igual ao /rolar), a não ser pra mestre."""
    char = db.find_character(str(coletor.user.id), personagem)
    if ORDEM_DA_CRIACAO and char is not None and not _membro_eh_mestre(coletor.user) and not rules.creation_status(char)["pronta"]:
        coletor.avisar(f"🔒 A ficha de **{char['name']}** ainda não está pronta. O passo a passo está em `/ajuda`.")
        return
    extras = []
    if modo in ("vantagem", "desvantagem"):   # o modo que o jogador escolheu no painel
        extras = [dice.EfeitoDeSorte(-1, modo, None, 1, False, "jogador")]
    elif modo == "classe":   # a vantagem que a classe dá nessa perícia
        extras = [dice.EfeitoDeSorte(-1, "vantagem", None, 1, False, "classe")]
    await _executar_rolagem(coletor, notacao, motivo, personagem, extras)


def _bloqueio_curto(uid: str, eh_mestre: bool) -> str | None:
    """Versão curta do bloqueio de ficha, pra responder no chat sem poluir o canal."""
    if not ORDEM_DA_CRIACAO or eh_mestre:
        return None
    char = db.get_active_character(uid)
    if char is None:
        return "🔒 Você ainda não tem personagem. Começa por `/personagem criar`; o passo a passo está em `/ajuda`."
    if rules.creation_status(char)["pronta"]:
        return None
    return f"🔒 A ficha de **{char['name']}** ainda não está pronta. O passo a passo está em `/ajuda`."


async def _rolar_por_texto(message: discord.Message, pedido: dice.PedidoDeDado):
    uid = str(message.author.id)
    bloqueio = _bloqueio_curto(uid, _membro_eh_mestre(message.author))
    if bloqueio:
        await message.reply(bloqueio, mention_author=False, delete_after=20)
        return
    try:  # confere a notação antes de qualquer coisa, sem rolar e sem gastar a sorte do personagem
        dice.validate(pedido.notacao)
    except dice.DiceError as e:
        if pedido.explicito:  # só responde erro a quem pediu com o "+"; conversa normal passa batido
            await message.reply(f"⚠️ {e}", mention_author=False, delete_after=15)
        return

    char = db.get_active_character(uid)  # pode ser None: rolar sem personagem continua valendo
    jogador = str(message.author.display_name)
    resultados, marcas = _rolar_com_sorte(char, pedido.notacao)
    cartao = _registrar_e_montar_cartao(
        uid, jogador, str(message.guild.id) if message.guild else None, char, pedido.notacao, pedido.motivo,
        resultados, marcas,
    )
    await message.reply(mention_author=False, **cartao.kwargs())


@bot.event
async def on_message(message: discord.Message):
    if not DADOS_POR_TEXTO or message.author.bot or message.guild is None:
        return
    pedido = dice.parse_texto(message.content)
    if pedido is not None:
        await _rolar_por_texto(message, pedido)


_SORTEIOS_DE_CRIACAO = {"raca_inicial", "classe_social", "clero", "magia_inicial"}


def _total_no_historico(linha) -> str:
    """O histórico é público. Um 66 ou 77 num sorteio de criação é segredo (o cartão é só interrogação),
    então o número não aparece aqui também. Rolagem comum de 66 ou 77 (um ataque, por exemplo) aparece normal."""
    if linha["purpose"] in _SORTEIOS_DE_CRIACAO and rules.is_special_roll(linha["total"]):
        return "???"
    return str(linha["total"])


@bot.tree.command(name="historico", description="Mostra as últimas rolagens de um usuário (ou de um personagem dele).")
@app_commands.describe(
    usuario="De quem ver o histórico (padrão: você mesmo)",
    limite="Quantas rolagens mostrar (padrão 10)",
    personagem="Opcional: só as rolagens desse personagem",
)
@app_commands.autocomplete(personagem=_autocomplete_personagem)
@app_commands.check(_exigir_algum_personagem_pronto)
async def historico(
    interaction: discord.Interaction,
    usuario: discord.Member | None = None,
    limite: int = 10,
    personagem: str | None = None,
):
    alvo = usuario or interaction.user
    limite = max(1, min(limite, 25))

    char = None
    if personagem:
        char = db.find_character(str(alvo.id), personagem)
        if not char:
            await interaction.response.send_message(
                f"{alvo.display_name} não tem nenhum personagem chamado **{personagem}**.", ephemeral=True
            )
            return

    linhas = db.get_history(str(alvo.id), limit=limite, character_id=char["id"] if char else None)
    if not linhas:
        onde = f"{char['name']} ({alvo.display_name})" if char else alvo.display_name
        await interaction.response.send_message(f"Nenhuma rolagem registrada pra {onde} ainda.", ephemeral=True)
        return

    titulo = f"📜 Histórico de {char['name']}" if char else f"📜 Histórico de {alvo.display_name}"
    embed = discord.Embed(title=titulo, color=discord.Color.dark_gold())
    for linha in linhas:
        quando = _quando(linha["created_at"])
        motivo = f" ({linha['purpose'][:80]})" if linha["purpose"] else ""
        if not char and linha["character_name"]:
            quando += f" · {linha['character_name']}"
        embed.add_field(
            name=f"{linha['notation']} = {_total_no_historico(linha)}{motivo}",
            value=quando,
            inline=False,
        )
    await interaction.response.send_message(embed=embed)


# ---------------------------------------------------------------------------
# Personagens
# ---------------------------------------------------------------------------

personagem_grupo = app_commands.Group(name="personagem", description="Cria, troca e exclui personagens.")


def _resumo_excluido(snap: dict) -> str:
    return f"nível {snap['level']}, {rules.fmt_xp(snap['xp'])} XP, raça {snap['race'] or 'não sorteada'}"


class ConfirmarExclusao(discord.ui.View):
    """Botões de confirmação da exclusão de um personagem. Só quem pediu consegue apertar."""

    def __init__(self, executor, personagem, dono_id: str, por_mestre: bool = False):
        super().__init__(timeout=60)
        self.executor = executor
        self.char_id = personagem["id"]
        self.char_nome = personagem["name"]
        self.dono_id = dono_id
        self.por_mestre = por_mestre
        self.origem: discord.Interaction | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.executor.id:
            await interaction.response.send_message("Só quem pediu a exclusão pode confirmar.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Excluir pra sempre", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        snap = db.delete_character(self.char_id, str(self.executor.id), str(self.executor.display_name))
        if snap is None:
            await interaction.response.edit_message(
                content="Esse personagem já tinha sido excluído.", embed=None, view=None
            )
            return
        if self.por_mestre:
            db.log_master_action(
                master_id=str(self.executor.id),
                master_name=str(self.executor.display_name),
                target_user_id=self.dono_id,
                character_id=self.char_id,
                character_name=self.char_nome,
                action="excluir_personagem",
                detail=_resumo_excluido(snap),
            )
        await interaction.response.edit_message(
            content=f"🗑️ **{self.char_nome}** foi excluído pra sempre.", embed=None, view=None
        )
        if self.por_mestre:
            dono = discord.Object(id=int(self.dono_id))
            aviso = discord.Embed(
                title="🗑️ Personagem excluído",
                description=(
                    f"{self.executor.display_name} excluiu **{self.char_nome}** ({_resumo_excluido(snap)}). "
                    "A vaga foi liberada."
                ),
                color=discord.Color.red(),
            )
            await interaction.followup.send(
                content=f"<@{self.dono_id}>", embed=aviso, allowed_mentions=discord.AllowedMentions(users=[dono]),
            )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="Beleza, nada foi excluído.", embed=None, view=None)

    async def on_timeout(self):
        if self.origem is not None:
            try:
                await self.origem.edit_original_response(
                    content="Passou o tempo e nada foi excluído.", embed=None, view=None
                )
            except discord.HTTPException:
                pass


def _embed_aviso_exclusao(personagem, quem_e_dono: str) -> discord.Embed:
    return discord.Embed(
        title=f"🗑️ Excluir {personagem['name']}?",
        description=(
            f"Isso apaga **{personagem['name']}** de {quem_e_dono} (nível {personagem['level']}, "
            f"{rules.fmt_xp(personagem['xp'])} XP) **pra sempre**. Não tem como desfazer, e o extrato de XP "
            "e os ranks dele somem junto.\n"
            "A vaga é liberada. As rolagens antigas continuam no histórico."
        ),
        color=discord.Color.red(),
    )


@personagem_grupo.command(name="criar", description="Cria um personagem novo e já passa a usar ele.")
@app_commands.describe(nome="Nome do personagem")
async def personagem_criar(interaction: discord.Interaction, nome: str):
    await _criar_personagem(interaction, nome)


async def _criar_personagem(interaction: discord.Interaction, nome: str) -> None:
    """Cria o personagem e abre a ficha. Usada pelo /personagem criar e pelo botão da mensagem de boas-vindas."""
    limpo = db.normalize_name(nome)
    if not (NOME_MIN <= len(limpo) <= NOME_MAX):
        await interaction.response.send_message(
            f"⚠️ O nome precisa ter entre {NOME_MIN} e {NOME_MAX} letras.", ephemeral=True
        )
        return

    uid = str(interaction.user.id)
    usadas, permitidas, _ = _vagas(uid)
    sem_vaga = (
        f"Você já usa todas as suas vagas de personagem ({usadas} de {permitidas}). Pra criar outro, exclua um "
        "com `/personagem excluir` (é pra sempre) ou peça uma vaga extra pra um mestre."
    )
    if usadas >= permitidas:
        await interaction.response.send_message(sem_vaga, ephemeral=True)
        return

    try:
        novo = db.create_character(uid, limpo, max_characters=permitidas)
    except db.CharacterLimit:
        await interaction.response.send_message(sem_vaga, ephemeral=True)
        return
    except db.CharacterExists:
        existente = db.find_character(uid, limpo)
        await interaction.response.send_message(
            f"Você já tem um personagem chamado **{existente['name'] if existente else limpo}**. "
            "Use `/personagem usar` pra voltar pra ele.",
            ephemeral=True,
        )
        return
    embed = discord.Embed(
        title="🎭 Personagem criado",
        description=(
            f"**{novo['name']}** agora é o personagem que você está usando ({usadas + 1} de {permitidas} vagas).\n"
            "Próximo passo: sortear a raça e a classe social (`/raca_inicial` e `/classe_social`, em qualquer ordem). "
            "Depois vêm `/classe`, o Rank de magia (`/magia_inicial`, só pra quem tem magia) e `/atributos`. "
            "O passo a passo completo está em `/ajuda`.\n\n"
            "**Ou é só clicar nos botões aqui embaixo.**"
        ),
        color=discord.Color.dark_purple(),
    )
    painel = paineis.PainelFicha(interaction.user.id, novo["id"], str(interaction.user.display_name))
    await interaction.response.send_message(embed=embed, view=painel, ephemeral=True)
    painel.origem = interaction


@personagem_grupo.command(name="usar", description="Troca o personagem que você está usando nas rolagens.")
@app_commands.describe(nome="Nome do personagem")
@app_commands.autocomplete(nome=_autocomplete_personagem)
async def personagem_usar(interaction: discord.Interaction, nome: str):
    char = db.find_character(str(interaction.user.id), nome)
    if not char:
        await interaction.response.send_message(
            f"Não achei nenhum personagem seu chamado **{nome}**. Use `/personagem listar` pra ver os seus.",
            ephemeral=True,
        )
        return
    db.set_active_character(str(interaction.user.id), char["id"])
    await interaction.response.send_message(
        f"Agora você está usando **{char['name']}**. As próximas rolagens vão pro histórico dele.", ephemeral=True
    )


@personagem_grupo.command(name="listar", description="Lista os seus personagens.")
async def personagem_listar(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    chars = db.list_characters(uid)
    if not chars:
        await interaction.response.send_message(
            "Você ainda não tem personagem. Cria um com `/personagem criar`.", ephemeral=True
        )
        return
    ativo = db.get_active_character(uid)
    linhas = []
    for c in chars:
        marca = "▶️" if ativo and c["id"] == ativo["id"] else "▫️"
        linhas.append(
            f"{marca} **{c['name']}** · nível {c['level']} · {rules.fmt_xp(c['xp'])} XP\n"
            f"　magia: {_magia_curta(c)} · raça: {_raca_curta(c)}"
            f" · estado: {_resumo_estado(c) or 'sem estado'}"
        )
    _, permitidas, _ = _vagas(uid)
    embed = discord.Embed(
        title="🎭 Seus personagens",
        description="\n".join(linhas),
        color=discord.Color.dark_purple(),
    )
    embed.set_footer(text=f"▶️ = o que você está usando agora · vagas usadas: {len(chars)} de {permitidas}")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@personagem_grupo.command(name="excluir", description="Exclui um personagem seu pra sempre (não tem volta).")
@app_commands.describe(nome="Nome do personagem que vai ser excluído")
@app_commands.autocomplete(nome=_autocomplete_personagem)
async def personagem_excluir(interaction: discord.Interaction, nome: str):
    uid = str(interaction.user.id)
    char = db.find_character(uid, nome)
    if not char:
        await interaction.response.send_message(
            f"Não achei nenhum personagem seu chamado **{nome}**. Use `/personagem listar` pra ver os seus.",
            ephemeral=True,
        )
        return
    view = ConfirmarExclusao(interaction.user, char, uid)
    await interaction.response.send_message(
        embed=_embed_aviso_exclusao(char, "você"), view=view, ephemeral=True
    )
    view.origem = interaction


bot.tree.add_command(personagem_grupo)


# ---------------------------------------------------------------------------
# Definições: Rank de magia, Raça e Classe social (uma rolagem só por personagem)
# ---------------------------------------------------------------------------

DEFINICOES = {
    "magic_rank": {
        "rotulo": "Rank de Magia",
        "titulo": "Magia Inicial",
        "resultado": "Rank",
        "emoji": "✨",
        "cor": discord.Color.purple(),
        "sorteio": dice.magic_rank_for,
        "salvar": db.set_magic_rank,
        "purpose": "magia_inicial",
    },
    "race": {
        "rotulo": "Raça",
        "titulo": "Raça",
        "resultado": "Raça",
        "emoji": "🩸",
        "cor": discord.Color.dark_red(),
        "sorteio": dice.race_for,
        "salvar": db.set_race,
        "purpose": "raca_inicial",
    },
}


_PASSO_DO_CAMPO = {"race": "raca", "social_class": "estado"}
_ROTULO_DO_CAMPO = {"race": "a Raça", "social_class": "a Classe Social"}


def _texto_sem_chances(char, campo: str, bloqueio: str) -> str:
    """Por que a raça ou a classe social não pode ser rolada de novo."""
    nome, resultado = char["name"], vitrine.resultado_atual(char, campo)
    if bloqueio == "mestre":
        return (
            f"**{nome}** tirou 100 no sorteio da Classe Social, então quem decide o Estado é o mestre. "
            "Fala com um mestre."
        )
    if bloqueio == "classe":
        return (
            f"**{nome}** já escolheu a classe, então {_ROTULO_DO_CAMPO[campo]} não muda mais ({resultado}). "
            "Fala com um mestre se precisar mudar."
        )
    return (
        f"**{nome}** já usou as {rules.CREATION_ROLL_ATTEMPTS} chances de rolar {_ROTULO_DO_CAMPO[campo]} "
        f"e ficou com **{resultado}**. Fala com um mestre se precisar de outra."
    )


def _texto_especial_pendente(char) -> str:
    """Resposta a quem tenta rolar de novo depois de um 66 ou 77. Não diz o que saiu."""
    return (
        f"❓ Algo diferente aconteceu no sorteio de **{char['name']}**, e só um mestre pode decidir o destino. "
        "Fala com um mestre."
    )


async def _pedir_confirmacao(interaction, char, campo: str):
    """Rolar de novo troca o resultado e não dá pra voltar: sempre pergunta antes."""
    view = paineis.ConfirmarRepeticao(
        interaction.user.id, char["id"], str(interaction.user.display_name), _PASSO_DO_CAMPO[campo]
    )
    await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)
    if hasattr(interaction, "edit_original_response"):
        view.origem = interaction


async def _sortear_definicao(interaction: discord.Interaction, campo: str, personagem_nome: str | None,
                             repetir: bool = False):
    cfg = DEFINICOES[campo]
    uid = str(interaction.user.id)

    char, erro = _resolver(uid, personagem_nome)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return

    if _especial_de(char, campo):  # caiu um 66 ou 77 antes: não rola de novo, um mestre decide
        await interaction.response.send_message(_texto_especial_pendente(char), ephemeral=True)
        return

    if char[campo]:
        if campo == "magic_rank":  # a magia é uma rolagem só (vantagem é combinada com um mestre)
            rolagem = char[f"{campo}_roll"]
            detalhe = "definido por um mestre" if rolagem is None else f"resultado {rolagem} no 1d100"
            await interaction.response.send_message(
                f"**{char['name']}** já tem {cfg['rotulo']}: **{char[campo]}** ({detalhe}). "
                "Fala com um mestre se precisar rolar de novo.",
                ephemeral=True,
            )
            return
        bloqueio = rules.reroll_block(char, campo)
        if bloqueio:
            await interaction.response.send_message(_texto_sem_chances(char, campo, bloqueio), ephemeral=True)
            return
        if not repetir:
            await _pedir_confirmacao(interaction, char, campo)
            return

    if campo == "magic_rank":
        status = rules.creation_status(char)
        if status["sem_magia"]:
            await interaction.response.send_message(
                ajuda.texto_sem_magia(char["name"], char["race"], char["class_name"], status), ephemeral=True
            )
            return
        if ORDEM_DA_CRIACAO and rules.creation_missing_before("magia", status):
            await interaction.response.send_message(ajuda.texto_falta_para("magia", status), ephemeral=True)
            return

    # Daqui até salvar não tem nenhum 'await', então dois comandos seguidos do mesmo jogador
    # nunca se intercalam e não dá pra rolar duas vezes.
    resultado = dice.roll("1d100")
    valor = resultado.total
    definido = cfg["sorteio"](valor)

    db.log_roll(
        user_id=uid,
        username=str(interaction.user.display_name),
        guild_id=str(interaction.guild_id) if interaction.guild_id else None,
        notation="1d100",
        rolls=resultado.rolls,
        total=valor,
        purpose=cfg["purpose"],
        character_id=char["id"],
        character_name=char["name"],
    )
    if rules.is_special_roll(valor):
        # 66 ou 77: nada é definido. O cartão é só interrogação e um mestre decide o destino.
        db.set_special(char["id"], campo, valor)
        await interaction.response.send_message(
            **_ping_mestre(interaction.guild, admins=True), **vitrine.cartao_especial(valor).kwargs()
        )
        return
    cfg["salvar"](char["id"], definido, valor)

    jogador = interaction.user.display_name
    if campo == "race":
        novo = db.get_character_by_id(char["id"])
        tentativa = (rules.attempts_used(novo, "race"), rules.CREATION_ROLL_ATTEMPTS)
        cartao = vitrine.cartao_raca(char["name"], definido, jogador, tentativa)
    else:
        cartao = vitrine.cartao_magia(char["name"], definido, valor, jogador)
    await interaction.response.send_message(**cartao.kwargs())


@bot.tree.command(name="magia_inicial", description="Rola 1d100 e define o Rank de magia (só Vampiros, Dhampirs, Feiticeiros e Mestres de Forja).")
@app_commands.describe(personagem="Opcional: qual personagem seu (padrão: o que você está usando)")
@app_commands.autocomplete(personagem=_autocomplete_personagem)
async def magia_inicial(interaction: discord.Interaction, personagem: str | None = None):
    await _sortear_definicao(interaction, "magic_rank", personagem)


@bot.tree.command(name="raca_inicial", description="Rola 1d100 e sorteia a Raça do seu personagem.")
@app_commands.describe(personagem="Opcional: qual personagem seu (padrão: o que você está usando)")
@app_commands.autocomplete(personagem=_autocomplete_personagem)
async def raca_inicial(interaction: discord.Interaction, personagem: str | None = None):
    await _sortear_definicao(interaction, "race", personagem)


@bot.tree.command(name="classe_social", description="Rola 1d100 e sorteia o Estado social do seu personagem (1º, 2º ou 3º).")
@app_commands.describe(personagem="Opcional: qual personagem seu (padrão: o que você está usando)")
@app_commands.autocomplete(personagem=_autocomplete_personagem)
async def classe_social(interaction: discord.Interaction, personagem: str | None = None):
    await _sortear_estado(interaction, personagem)


async def _sortear_estado(interaction, personagem_nome: str | None, repetir: bool = False):
    uid = str(interaction.user.id)
    char, erro = _resolver(uid, personagem_nome)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return

    if _especial_de(char, "social_class"):
        await interaction.response.send_message(_texto_especial_pendente(char), ephemeral=True)
        return

    if char["social_class"]:
        bloqueio = rules.reroll_block(char, "social_class")
        if bloqueio:
            await interaction.response.send_message(_texto_sem_chances(char, "social_class", bloqueio), ephemeral=True)
            return
        if not repetir:
            await _pedir_confirmacao(interaction, char, "social_class")
            return

    # Sem 'await' daqui até salvar: o mesmo jogador não consegue rolar duas vezes ao mesmo tempo.
    guild_id = str(interaction.guild_id) if interaction.guild_id else None
    nome_jogador = str(interaction.user.display_name)

    r1 = dice.roll("1d100")
    estado = dice.social_class_for(r1.total)
    db.log_roll(
        user_id=uid, username=nome_jogador, guild_id=guild_id, notation="1d100", rolls=r1.rolls,
        total=r1.total, purpose="classe_social", character_id=char["id"], character_name=char["name"],
    )

    clero = r2 = None
    if estado == "1º Estado":
        # Quem cai no clero rola outro 1d100: de 50 pra cima é Alto Clero.
        r2 = dice.roll("1d100")
        clero = dice.clergy_for(r2.total)
        db.log_roll(
            user_id=uid, username=nome_jogador, guild_id=guild_id, notation="1d100", rolls=r2.rolls,
            total=r2.total, purpose="clero", character_id=char["id"], character_name=char["name"],
        )
    especial = next((r.total for r in (r1, r2) if r is not None and rules.is_special_roll(r.total)), None)
    if especial:
        # 66 ou 77 no Estado (ou no clero): nada é definido, o cartão é só interrogação e um mestre decide.
        db.set_special(char["id"], "social_class", especial)
        await interaction.response.send_message(**_ping_mestre(interaction.guild, admins=True), **vitrine.cartao_especial(especial).kwargs())
        return
    db.set_social_status(char["id"], estado, r1.total, clero, r2.total if r2 else None)

    ping = _ping_mestre(interaction.guild) if estado == dice.SOCIAL_CLASS_MASTER else {}
    novo = db.get_character_by_id(char["id"])
    tentativa = (rules.attempts_used(novo, "social_class"), rules.CREATION_ROLL_ATTEMPTS)
    cartao = vitrine.cartao_estado(char["name"], estado, nome_jogador, clero, tentativa)
    await interaction.response.send_message(**ping, **cartao.kwargs())


# ---------------------------------------------------------------------------
# Classe e atributos (a ficha automática)
# ---------------------------------------------------------------------------

async def _autocomplete_habilidade(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """As habilidades que dá pra escolher: as da classe que a pessoa já digitou no /classe, ou as do personagem
    em uso; se nenhuma das duas tem escolha, todas as que têm."""
    digitada = getattr(interaction.namespace, "classe", None)
    ativo = db.get_active_character(_dono_do_autocomplete(interaction))
    classe = digitada if digitada in rules.CLASSES else (ativo["class_name"] if ativo else None)
    opcoes = rules.class_ability_options(classe)
    if not rules.class_needs_ability_choice(classe):
        opcoes = tuple(o for c in rules.CLASS_ABILITIES if rules.class_needs_ability_choice(c) for o in rules.CLASS_ABILITIES[c])
    busca = current.casefold()
    return [app_commands.Choice(name=o, value=o) for o in opcoes if busca in o.casefold()][:25]


@bot.tree.command(name="classe", description="Escolhe a classe (e a habilidade, no Clérigo e no Ladrão). Vale uma vez.")
@app_commands.describe(
    classe="A classe do personagem",
    habilidade="Só Clérigo e Ladrão: qual das duas habilidades você leva (ou escolhe nos botões depois)",
    personagem="Opcional: qual personagem seu (padrão: o que você está usando)",
)
@app_commands.choices(classe=[app_commands.Choice(name=n, value=n) for n in rules.CLASSES])
@app_commands.autocomplete(habilidade=_autocomplete_habilidade, personagem=_autocomplete_personagem)
async def classe_escolher(interaction: discord.Interaction, classe: str, habilidade: str | None = None, personagem: str | None = None):
    char, erro = _resolver(str(interaction.user.id), personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return
    if char["class_name"]:
        await interaction.response.send_message(
            f"**{char['name']}** já é da classe **{char['class_name']}**. Fala com um mestre se precisar mudar.",
            ephemeral=True,
        )
        return
    status = rules.creation_status(char)
    if ORDEM_DA_CRIACAO and rules.creation_missing_before("classe", status):
        await interaction.response.send_message(ajuda.texto_falta_para("classe", status), ephemeral=True)
        return
    escolhida = None
    if habilidade:  # confere antes de gravar qualquer coisa: a classe e a habilidade entram juntas, ou nenhuma
        opcoes = rules.class_ability_options(classe)
        if not rules.class_needs_ability_choice(classe):
            await interaction.response.send_message(
                f"A classe **{classe}** só tem uma habilidade (**{opcoes[0]}**), então é só escolher a classe, sem `habilidade`.",
                ephemeral=True,
            )
            return
        escolhida = next((o for o in opcoes if o.casefold() == habilidade.strip().casefold()), None)
        if escolhida is None:
            await interaction.response.send_message(
                f"**{habilidade}** não é uma habilidade de **{classe}**. As opções são: {' ou '.join(f'**{o}**' for o in opcoes)}.",
                ephemeral=True,
            )
            return
    db.set_class(char["id"], classe)
    if escolhida:
        db.set_class_ability(char["id"], escolhida)
    novo = db.get_character_by_id(char["id"])
    status_novo = rules.creation_status(novo)
    if status_novo["sem_magia"]:
        magia = "Sua raça e sua classe não têm magia, então você não sorteia o Rank de magia. "
    elif status_novo["magia_acesso"] == "sim" and not status_novo["magia_sorteada"]:
        magia = "Sua raça ou sua classe tem magia. "
    else:
        magia = ""
    proximo = ajuda.proximo_passo(status_novo) if ORDEM_DA_CRIACAO else "Agora distribua os pontos de atributo com `/atributos`."
    pendente = paineis.habilidade_pendente(novo)
    aviso = "Escolhe a sua habilidade de classe nos botões abaixo. " if pendente else ""
    cartao = vitrine.cartao_classe(
        char["name"], classe, f"{aviso}{magia}{proximo}", interaction.user.display_name,
        rules.class_ability_of(novo), com_botoes=pendente,
    )
    extras = {}
    if pendente:  # a classe foi escolhida sem a habilidade: já oferece os botões, sem precisar de outro comando
        extras["view"] = paineis.EscolhaDeHabilidade(interaction.user.id, char["id"], interaction.user.display_name, com_voltar=False)
    await interaction.response.send_message(**cartao.kwargs(), ephemeral=True, **extras)
    if "view" in extras and not isinstance(interaction, paineis.Coletor):   # o Coletor (caminho do painel) não tem mensagem própria
        extras["view"].origem = interaction


@bot.tree.command(name="habilidade", description="Mostra a habilidade da sua classe, ou escolhe uma das duas (Clérigo e Ladrão).")
@app_commands.describe(
    escolha="Só pras classes que oferecem duas habilidades: qual você leva (vale uma vez)",
    personagem="Opcional: qual personagem seu (padrão: o que você está usando)",
)
@app_commands.autocomplete(escolha=_autocomplete_habilidade, personagem=_autocomplete_personagem)
async def habilidade(interaction: discord.Interaction, escolha: str | None = None, personagem: str | None = None):
    char, erro = _resolver(str(interaction.user.id), personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return
    classe = char["class_name"]
    if not classe:
        await interaction.response.send_message(
            f"**{char['name']}** ainda não tem classe. Escolhe a classe com `/classe` e depois volta aqui.", ephemeral=True
        )
        return
    opcoes = rules.class_ability_options(classe)
    if escolha:
        if not rules.class_needs_ability_choice(classe):
            await interaction.response.send_message(
                f"A classe **{classe}** só tem uma habilidade (**{opcoes[0]}**), então não tem o que escolher.", ephemeral=True
            )
            return
        alvo = next((o for o in opcoes if o.casefold() == escolha.strip().casefold()), None)
        if alvo is None:
            await interaction.response.send_message(
                f"**{escolha}** não é uma habilidade de **{classe}**. As opções são: {' ou '.join(f'**{o}**' for o in opcoes)}.",
                ephemeral=True,
            )
            return
        atual = rules.class_ability_of(char)
        if atual:
            await interaction.response.send_message(
                f"**{char['name']}** já levou **{atual}**. Fala com um mestre se precisar mudar.", ephemeral=True
            )
            return
        db.set_class_ability(char["id"], alvo)
        char = db.get_character_by_id(char["id"])
    pendente = paineis.habilidade_pendente(char)
    cartao = vitrine.cartao_habilidade(
        char["name"], classe, rules.class_ability_of(char), interaction.user.display_name, "botao" if pendente else "comando",
    )
    extras = {}
    if pendente:  # falta escolher: em vez de mandar digitar outro comando, já mostra os botões
        extras["view"] = paineis.EscolhaDeHabilidade(interaction.user.id, char["id"], interaction.user.display_name, com_voltar=False)
    await interaction.response.send_message(**cartao.kwargs(), ephemeral=True, **extras)
    if "view" in extras and not isinstance(interaction, paineis.Coletor):   # o Coletor (caminho do painel) não tem mensagem própria
        extras["view"].origem = interaction


_DESCRICAO_ATRIBUTO = {a: f"Novo valor de {rules.ATTRIBUTE_LABELS[a]}" for a in rules.ATTRIBUTES}


@bot.tree.command(name="atributos", description="Distribui os pontos de atributo do seu personagem (só dá pra aumentar).")
@app_commands.describe(**_DESCRICAO_ATRIBUTO, personagem="Opcional: qual personagem seu (padrão: o que você está usando)")
@app_commands.autocomplete(personagem=_autocomplete_personagem)
async def atributos(
    interaction: discord.Interaction,
    forca: app_commands.Range[int, 0, 20] | None = None,
    destreza: app_commands.Range[int, 0, 20] | None = None,
    vitalidade: app_commands.Range[int, 0, 20] | None = None,
    razao: app_commands.Range[int, 0, 20] | None = None,
    vontade: app_commands.Range[int, 0, 20] | None = None,
    alma: app_commands.Range[int, 0, 20] | None = None,
    personagem: str | None = None,
):
    char, erro = _resolver(str(interaction.user.id), personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return

    pedidos = {
        nome: valor
        for nome, valor in [("forca", forca), ("destreza", destreza), ("vitalidade", vitalidade),
                            ("razao", razao), ("vontade", vontade), ("alma", alma)]
        if valor is not None
    }
    if not pedidos:  # sem números: só mostra como está
        await interaction.response.send_message(
            embed=_embed_atributos(char, f"🧬 Atributos de {char['name']}"), ephemeral=True
        )
        return

    status = rules.creation_status(char)
    if (ORDEM_DA_CRIACAO and rules.creation_missing_before("atributos", status)) or not char["race"]:
        await interaction.response.send_message(ajuda.texto_falta_para("atributos", status), ephemeral=True)
        return
    atuais = db.attributes_of(char)
    baixaram = [rules.ATTRIBUTE_LABELS[n] for n, v in pedidos.items() if v < atuais[n]]
    if baixaram:
        um = len(baixaram) == 1
        await interaction.response.send_message(
            f"Só dá pra aumentar atributo, e {_juntar(baixaram)} {'ficaria menor' if um else 'ficariam menores'} "
            f"do que {'já está' if um else 'já estão'}. Pra diminuir, fala com um mestre.",
            ephemeral=True,
        )
        return
    problemas = rules.validate_attributes({**atuais, **pedidos}, char["level"], char["race"])
    if problemas:
        await interaction.response.send_message("⚠️ " + "\n".join(problemas), ephemeral=True)
        return

    db.set_attributes(char["id"], pedidos)
    novo = db.get_character_by_id(char["id"])
    await interaction.response.send_message(
        embed=_embed_atributos(novo, f"🧬 Atributos de {char['name']} atualizados"), ephemeral=True
    )


# ---------------------------------------------------------------------------
# Ficha, XP, níveis, rank e calculadora de recursos
# ---------------------------------------------------------------------------

@bot.tree.command(name="minha_ficha", description="Mostra nível, XP, raça, classe, atributos, recursos e ranks do seu personagem.")
@app_commands.describe(personagem="Opcional: qual personagem seu (padrão: o que você está usando)")
@app_commands.autocomplete(personagem=_autocomplete_personagem)
async def minha_ficha(interaction: discord.Interaction, personagem: str | None = None):
    char, erro = _resolver(str(interaction.user.id), personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return
    painel = paineis.PainelFicha(interaction.user.id, char["id"], str(interaction.user.display_name))
    await interaction.response.send_message(
        embed=_embed_ficha(char, interaction.user.display_name), view=painel, ephemeral=True
    )
    painel.origem = interaction


async def _abrir_aba(interaction: discord.Interaction, aba: str, personagem: str | None) -> None:
    """Abre a ficha direto numa aba (perícias ou habilidades), pra a pessoa não precisar procurar."""
    char, erro = _resolver(str(interaction.user.id), personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return
    jogador = str(interaction.user.display_name)
    painel = (paineis.PainelPericias if aba == "pericias" else paineis.PainelHabilidades)(interaction.user.id, char["id"], jogador)
    await interaction.response.send_message(embed=painel.embed(), view=painel, ephemeral=True)
    painel.origem = interaction


@bot.tree.command(name="pericias", description="Distribui os pontos das suas perícias e testa uma com um clique.")
@app_commands.describe(personagem="Opcional: qual personagem seu (padrão: o que você está usando)")
@app_commands.autocomplete(personagem=_autocomplete_personagem)
async def pericias_comando(interaction: discord.Interaction, personagem: str | None = None):
    await _abrir_aba(interaction, "pericias", personagem)


@bot.tree.command(name="habilidades", description="Cria as suas habilidades (o mestre aprova) e usa as aprovadas.")
@app_commands.describe(personagem="Opcional: qual personagem seu (padrão: o que você está usando)")
@app_commands.autocomplete(personagem=_autocomplete_personagem)
async def habilidades_comando(interaction: discord.Interaction, personagem: str | None = None):
    await _abrir_aba(interaction, "habilidades", personagem)


@bot.tree.command(name="iniciativa", description="Entra na iniciativa da cena deste canal (1d20 + Destreza).")
async def iniciativa_comando(interaction: discord.Interaction):
    await escudo.entrar_na_iniciativa(interaction)


@bot.tree.command(name="intencao", description="Manda pro mestre, numa frase, o que o seu personagem quer fazer na cena.")
@app_commands.describe(texto="Uma frase, até 200 letras. Só o mestre lê. Sem texto, mostra a sua intenção desta rodada.")
async def intencao_comando(interaction: discord.Interaction, texto: app_commands.Range[str, 1, 200] | None = None):
    await escudo.mandar_intencao(interaction, texto)


@bot.tree.command(name="disciplinas", description="Lê o texto das dez Disciplinas vampíricas e, se for Vampiro ou Dhampir, gasta os pontos.")
@app_commands.describe(personagem="Opcional: qual personagem seu (padrão: o que você está usando)")
@app_commands.autocomplete(personagem=_autocomplete_personagem)
async def disciplinas_comando(interaction: discord.Interaction, personagem: str | None = None):
    uid = str(interaction.user.id)
    char = db.resolve_character(uid, personagem)
    if personagem and char is None:  # pediu um personagem que não existe; sem pedir nenhum, o painel só lê
        await interaction.response.send_message(
            f"Não achei nenhum personagem seu chamado **{personagem}**. Use `/personagem listar` pra ver os seus.",
            ephemeral=True,
        )
        return
    painel = paineis.PainelDisciplinas(interaction.user.id, char["id"] if char else None, str(interaction.user.display_name))
    await interaction.response.send_message(embed=painel.embed(), view=painel, ephemeral=True)
    painel.origem = interaction


@bot.tree.command(name="dados", description="Abre uma bandeja de dados com botões (d4 a d100), sem digitar nada.")
async def dados_comando(interaction: discord.Interaction):
    bandeja = paineis.BandejaDados(interaction.user.id, str(interaction.user.display_name))
    await interaction.response.send_message(embed=bandeja.embed(), view=bandeja, ephemeral=True)
    bandeja.origem = interaction


_SEM_PERSONAGEM_NO_BOTAO = "Você ainda não tem personagem. Aperta **🆕 Criar personagem** na mensagem de boas-vindas pra começar."


def _embed_comeco() -> discord.Embed:
    return discord.Embed(
        title="🩸 Baptism of Blood",
        description=(
            "Aqui o seu personagem é criado e jogado por botões, sem decorar comando.\n\n"
            "🆕 **Criar personagem**: começa por aqui. É só dizer o nome.\n"
            "📋 **Minha ficha**: abre a sua ficha, com as abas Vitais, Perícias e Habilidades.\n"
            "🎲 **Dados**: abre a bandeja de dados.\n"
            "❓ **Como funciona**: o passo a passo em poucas linhas."
        ),
        color=discord.Color.dark_red(),
    )


class ModalNovoPersonagem(discord.ui.Modal):
    """O formulário do botão Criar personagem: só o nome."""

    def __init__(self):
        super().__init__(title="Novo personagem", timeout=paineis.TEMPO_DO_PAINEL)
        self.nome = discord.ui.TextInput(
            label="Nome do personagem", required=True, min_length=NOME_MIN, max_length=NOME_MAX, placeholder="ex: Kairon Flagon"
        )
        self.add_item(self.nome)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await _criar_personagem(interaction, self.nome.value)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await paineis._avisar_erro(interaction, error)


class ComecoAqui(discord.ui.View):
    """A mensagem de boas-vindas que o mestre posta no canal. Os botões têm identificador fixo, então continuam
    funcionando depois que o bot reinicia (veja _preparar_bot)."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Criar personagem", emoji="🆕", style=discord.ButtonStyle.success, custom_id="inicio:criar")
    async def criar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ModalNovoPersonagem())

    @discord.ui.button(label="Minha ficha", emoji="📋", style=discord.ButtonStyle.primary, custom_id="inicio:ficha")
    async def ficha(self, interaction: discord.Interaction, button: discord.ui.Button):
        char = db.get_active_character(str(interaction.user.id))
        if char is None:
            await interaction.response.send_message(_SEM_PERSONAGEM_NO_BOTAO, ephemeral=True)
            return
        painel = paineis.PainelFicha(interaction.user.id, char["id"], str(interaction.user.display_name))
        await interaction.response.send_message(embed=_embed_ficha(char, interaction.user.display_name), view=painel, ephemeral=True)
        painel.origem = interaction

    @discord.ui.button(label="Dados", emoji="🎲", style=discord.ButtonStyle.secondary, custom_id="inicio:dados")
    async def dados(self, interaction: discord.Interaction, button: discord.ui.Button):
        bandeja = paineis.BandejaDados(interaction.user.id, str(interaction.user.display_name))
        await interaction.response.send_message(embed=bandeja.embed(), view=bandeja, ephemeral=True)
        bandeja.origem = interaction

    @discord.ui.button(label="Como funciona", emoji="❓", style=discord.ButtonStyle.secondary, custom_id="inicio:como")
    async def como(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="❓ Como funciona",
            description=(
                "**1.** Aperta **🆕 Criar personagem** e diz o nome.\n"
                "**2.** A ficha abre com botões: **Raça**, **Classe social**, **Classe** e **Atributos**. Segue na ordem: 🔒 ainda "
                "não abriu, ✅ já foi feito.\n"
                "**3.** Com a ficha pronta, ela ganha abas: **Vitais** (vida, mana...), **Perícias** (toca no ícone e o dado rola "
                "sozinho) e **Habilidades** (você cria, o mestre aprova, e depois é só usar).\n"
                "**4.** Pra rolar dado, aperta **🎲 Dados** ou escreve `d20+5` no chat.\n\n"
                "Se ficar perdido, `/ajuda` mostra o seu passo a passo."
            ),
            color=discord.Color.dark_red(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="niveis", description="Mostra o XP e as vantagens de cada nível, de 1 a 10.")
@app_commands.describe(personagem="Opcional: marcar o nível de qual personagem seu (padrão: o que você está usando)")
@app_commands.autocomplete(personagem=_autocomplete_personagem)
async def niveis(interaction: discord.Interaction, personagem: str | None = None):
    uid = str(interaction.user.id)
    if personagem:
        char = db.find_character(uid, personagem)
        if not char:
            await interaction.response.send_message(
                f"Não achei nenhum personagem seu chamado **{personagem}**. Use `/personagem listar` pra ver os seus.",
                ephemeral=True,
            )
            return
    else:
        char = db.get_active_character(uid)  # sem personagem, mostra a tabela sem marcar nível

    atual = char["level"] if char else None
    raca = char["race"] if char else None
    classe = char["class_name"] if char else None
    descricao = (
        "\n".join(rules.level_table_lines(atual, raca, classe))
        + f"\n\n**Somando tudo, do 1 ao {rules.MAX_LEVEL}:** "
        + rules.describe_gains(rules.total_gains(rules.MAX_LEVEL, raca, classe))
    )
    if raca not in rules.VAMPIRIC_RACES:
        descricao += "\nVampiros e Dhampirs ganham também +1 ponto de Disciplina a cada 2 níveis."
    embed = discord.Embed(title="📈 XP e vantagens de cada nível", description=descricao, color=discord.Color.dark_teal())
    if char:
        xp = char["xp"]
        _, dentro, precisa = rules.xp_progress(xp)
        if precisa is None:
            proximo = "nível máximo, não tem próximo"
        else:
            proximo = (
                f"nível {atual + 1}: {rules.describe_gains(rules.gains_for_level(atual + 1, raca, classe))}"
                f" (faltam {rules.fmt_xp(precisa - dentro)} XP)"
            )
        embed.add_field(
            name=f"{char['name']}: nível {atual}/{rules.MAX_LEVEL}",
            value=(
                f"{_barra_xp(xp)}\n"
                f"XP total: {rules.fmt_xp(xp)}\n"
                f"Já ganhou: {rules.describe_gains(rules.total_gains(atual, raca, classe))}\n"
                f"Próximo, {proximo}"
            ),
            inline=False,
        )
    embed.set_footer(text=(
        "Os mestres dão XP em roleplay importante, missão de mestre e desenvolvimento do personagem, "
        "sempre por roleplay e não por ação avulsa. "
        "Pontos de atributo de nível podem passar do limite da raça."
    ))
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="extrato_xp", description="Mostra de onde veio o XP do seu personagem (últimas entradas).")
@app_commands.describe(personagem="Opcional: qual personagem seu (padrão: o que você está usando)")
@app_commands.autocomplete(personagem=_autocomplete_personagem)
@app_commands.check(_exigir_personagem_pronto)
async def extrato_xp(interaction: discord.Interaction, personagem: str | None = None):
    char, erro = _resolver(str(interaction.user.id), personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return
    entradas = db.get_xp_log(char["id"], 10)
    if not entradas:
        await interaction.response.send_message(f"**{char['name']}** ainda não recebeu XP.", ephemeral=True)
        return
    linhas = [
        f"**{_mais(e['amount'])} XP** · {e['reason'] or 'sem motivo'} · por {e['master_name'] or 'um mestre'}"
        f" · {_quando(e['created_at'])}"
        for e in entradas
    ]
    embed = discord.Embed(
        title=f"📒 Extrato de XP de {char['name']}",
        description="\n".join(linhas),
        color=discord.Color.dark_gold(),
    )
    embed.set_footer(text=f"XP total: {rules.fmt_xp(char['xp'])} · nível {char['level']} · mostrando as últimas 10")
    await interaction.response.send_message(embed=embed, ephemeral=True)


_MEDALHAS = ["🥇", "🥈", "🥉"]


def _posicao(i: int) -> str:
    return _MEDALHAS[i - 1] if i <= len(_MEDALHAS) else f"**{i}.**"


@bot.tree.command(name="rank", description="Mostra o rank de XP total, de personagens ou de jogadores.")
@app_commands.describe(
    tipo="Rank de personagens ou de jogadores (padrão: personagens)",
    limite="Quantas posições mostrar (padrão 10)",
)
@app_commands.choices(tipo=[
    app_commands.Choice(name="Personagens", value="personagens"),
    app_commands.Choice(name="Jogadores (soma dos personagens)", value="jogadores"),
])
@app_commands.check(_exigir_algum_personagem_pronto)
async def rank(interaction: discord.Interaction, tipo: str = "personagens", limite: app_commands.Range[int, 3, 25] = 10):
    uid = str(interaction.user.id)
    if tipo == "jogadores":
        dados = db.rank_players()
    else:
        dados = db.rank_characters()
    if not dados:
        await interaction.response.send_message("Ninguém ganhou XP ainda, então o rank está vazio.", ephemeral=True)
        return

    linhas = []
    for i, r in enumerate(dados[:limite], 1):
        dono = r["owner"] or f"<@{r['user_id']}>"
        if tipo == "jogadores":
            n = r["personagens"]
            linhas.append(
                f"{_posicao(i)} **{dono}** · {rules.fmt_xp(r['total_xp'])} XP · "
                f"{n} {'personagem' if n == 1 else 'personagens'} · melhor nível {r['melhor_nivel']}"
            )
        else:
            linhas.append(f"{_posicao(i)} **{r['name']}** ({dono}) · nível {r['level']} · {rules.fmt_xp(r['xp'])} XP")

    embed = discord.Embed(
        title=f"🏆 Rank de XP: {'jogadores' if tipo == 'jogadores' else 'personagens'}",
        description="\n".join(linhas),
        color=discord.Color.gold(),
    )
    minha = next((i for i, r in enumerate(dados, 1) if r["user_id"] == uid), None)
    if minha is not None:
        embed.set_footer(text=(
            f"Sua posição: {minha}º" if tipo == "jogadores"
            else f"Seu melhor personagem: {minha}º ({dados[minha - 1]['name']})"
        ))
    await interaction.response.send_message(embed=embed)


@bot.tree.command(
    name="calcular_recursos",
    description="Calcula Vida, Sanidade, Mana e Estamina pela classe, pelos atributos e pelo nível.",
)
@app_commands.describe(
    classe="Sua classe (dá o bônus de cada recurso, uma vez só)",
    vitalidade="Seu atributo Vitalidade",
    forca="Seu atributo Força",
    vontade="Seu atributo Vontade",
    alma="Seu atributo Alma",
    nivel="Nível do personagem, de 1 a 10 (padrão 1). A conta usa o mesmo atributo em todos os níveis",
)
@app_commands.choices(classe=[app_commands.Choice(name=n, value=n) for n in rules.CLASS_CHOICES])
async def calcular_recursos(
    interaction: discord.Interaction,
    classe: str,
    vitalidade: app_commands.Range[int, 0, 20],
    forca: app_commands.Range[int, 0, 20],
    vontade: app_commands.Range[int, 0, 20],
    alma: app_commands.Range[int, 0, 20],
    nivel: app_commands.Range[int, 1, 10] = 1,
):
    res = rules.calculate_resources(
        vitalidade=vitalidade, forca=forca, vontade=vontade, alma=alma, classe=classe, nivel=nivel
    )
    sem_classe = classe == rules.CLASS_NONE
    por = "" if nivel == 1 else f" × {nivel} níveis"

    def linha(emoji: str, nome: str, chave: str, conta: str) -> str:
        r = res[chave]
        extra = "" if sem_classe else f", mais {r['bonus']} da classe"
        return f"{emoji} **{nome}: {r['total']}**\n　{conta}{por} = {r['base']}{extra}"

    embed = discord.Embed(
        title=f"🧮 Recursos ({'sem classe' if sem_classe else classe}{'' if nivel == 1 else f', nível {nivel}'})",
        description="\n".join([
            linha("❤️", "Vida", "vida", f"Vitalidade {vitalidade} × 5"),
            linha("🧠", "Sanidade", "sanidade", f"Vontade {vontade} × 5"),
            linha("🔮", "Mana", "mana", f"(Alma {alma} + Vontade {vontade}) × 3"),
            linha("💪", "Estamina", "estamina", f"(Força {forca} + Vitalidade {vitalidade}) × 3"),
        ]),
        color=discord.Color.dark_green(),
    )
    embed.set_footer(text=(
        "Por nível: cada ponto de Vitalidade dá +5 Vida e +3 Estamina, Vontade dá +5 Sanidade e +3 Mana, "
        "Alma dá +3 Mana e Força dá +3 Estamina. Todo nível soma de novo, e o bônus da classe entra uma vez só. "
        "Aqui o mesmo atributo vale em todos os níveis, então a conta exata é a da /minha_ficha. "
        "Destreza e Razão não entram."
    ))
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Ajuda
# ---------------------------------------------------------------------------

async def _autocomplete_comando(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=f"/{nome}", value=nome)
        for nome in ajuda.sugestoes(current, incluir_mestre=False)   # os de mestre ficam no /mestre ajuda
    ]


async def _autocomplete_comando_mestre(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if not _eh_mestre(interaction):
        return []
    return [app_commands.Choice(name=f"/mestre {nome}", value=nome) for nome in ajuda.sugestoes_mestre(current)]


async def _responder_ajuda(interaction: discord.Interaction, comando: str | None):
    if comando:
        chave, parecidos = ajuda.achar(comando)
        if not _eh_mestre(interaction):   # comando de mestre: pra quem não é mestre, é como se não existisse
            parecidos = [p for p in parecidos if not p.startswith("mestre ")]
            if chave and chave.startswith("mestre "):
                chave = None
        if chave is None:
            dica = (
                " Quis dizer: " + ", ".join(f"`/{p}`" for p in parecidos) + "?"
                if parecidos else " Use `/ajuda` pra ver a lista de comandos."
            )
            await interaction.response.send_message(f"Não achei nenhum comando com \"{comando}\".{dica}", ephemeral=True)
            return
        dados = ajuda.detalhe(chave)
    else:
        char = db.get_active_character(str(interaction.user.id))
        dados = ajuda.visao_geral(
            rules.creation_status(char) if char else None, char is not None, _eh_mestre(interaction)
        )
    embed = discord.Embed(title=dados["titulo"], description=dados["descricao"], color=discord.Color.blurple())
    for nome, valor in dados["campos"]:
        embed.add_field(name=nome, value=valor, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="ajuda", description="Ensina a usar o bot e explica cada comando.")
@app_commands.describe(comando="Opcional: o comando que você quer entender (por exemplo: atributos)")
@app_commands.autocomplete(comando=_autocomplete_comando)
async def ajuda_comando(interaction: discord.Interaction, comando: str | None = None):
    await _responder_ajuda(interaction, comando)


@bot.tree.command(name="help", description="Mesma coisa que /ajuda: ensina a usar o bot e explica cada comando.")
@app_commands.describe(comando="Opcional: o comando que você quer entender (por exemplo: atributos)")
@app_commands.autocomplete(comando=_autocomplete_comando)
async def help_comando(interaction: discord.Interaction, comando: str | None = None):
    await _responder_ajuda(interaction, comando)


# ---------------------------------------------------------------------------
# Comandos de mestre
# ---------------------------------------------------------------------------

mestre_grupo = app_commands.Group(
    name="mestre",
    description="Comandos de mestre: XP, níveis, vagas e correções.",
    guild_only=True,
    default_permissions=discord.Permissions(manage_guild=True) if ESCONDER_COMANDOS_DE_MESTRE else None,
)


@mestre_grupo.command(name="ajuda", description="A ajuda só dos comandos de mestre (os jogadores não veem).")
@app_commands.describe(comando="Opcional: o comando de mestre que você quer entender (por exemplo: dar_xp)")
@app_commands.autocomplete(comando=_autocomplete_comando_mestre)
@app_commands.check(_eh_mestre)
async def mestre_ajuda(interaction: discord.Interaction, comando: str | None = None):
    if comando:
        chave, parecidos = ajuda.achar_mestre(comando)
        if chave is None:
            dica = " Quis dizer: " + ", ".join(f"`/mestre {p}`" for p in parecidos) + "?" if parecidos else " Usa `/mestre ajuda` pra ver a lista."
            await interaction.response.send_message(f"Não achei nenhum comando de mestre com \"{comando}\".{dica}", ephemeral=True)
            return
        dados = ajuda.detalhe(chave)
    else:
        dados = ajuda.visao_mestre()
    embed = discord.Embed(title=dados["titulo"], description=dados["descricao"], color=discord.Color.dark_gold())
    for nome, valor in dados["campos"]:
        embed.add_field(name=nome, value=valor, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

_APAGAVEIS = {
    "magic_rank": ["magic_rank"],
    "race": ["race"],
    "social_class": ["social_class"],
    "todas": ["magic_rank", "race", "social_class"],
}
_ROTULO = {"magic_rank": "Rank de Magia", "race": "Raça", "social_class": "Classe Social"}
_ROTULO_COM_ARTIGO = {"magic_rank": "o Rank de Magia", "race": "a Raça", "social_class": "a Classe Social"}
_COMANDO_DE_ROLAR = {"magic_rank": "`/magia_inicial`", "race": "`/raca_inicial`", "social_class": "`/classe_social`"}

_ESTADO_ESCOLHAS = {
    "1-alto": ("1º Estado", "Alto Clero"),
    "1-baixo": ("1º Estado", "Baixo Clero"),
    "2": ("2º Estado", None),
    "3": ("3º Estado", None),
}


def _valor_atual(personagem, campo: str) -> str | None:
    especial = _especial_de(personagem, campo)
    if especial:
        return f"{_QUESTAO} (tirou {especial})"
    return _resumo_estado(personagem) if campo == "social_class" else personagem[campo]


def _auditar(interaction: discord.Interaction, usuario: discord.Member, char, acao: str, detalhe: str) -> None:
    db.log_master_action(
        master_id=str(interaction.user.id),
        master_name=str(interaction.user.display_name),
        target_user_id=str(usuario.id),
        character_id=char["id"],
        character_name=char["name"],
        action=acao,
        detail=detalhe,
    )


@mestre_grupo.command(
    name="apagar",
    description="Apaga magia, raça e/ou classe social de um personagem, pra ele poder rolar de novo.",
)
@app_commands.describe(
    usuario="Jogador dono do personagem",
    definicao="O que apagar",
    personagem="Opcional: personagem dele (padrão: o que ele está usando)",
)
@app_commands.choices(definicao=[
    app_commands.Choice(name="Rank de magia", value="magic_rank"),
    app_commands.Choice(name="Raça", value="race"),
    app_commands.Choice(name="Classe social", value="social_class"),
    app_commands.Choice(name="Tudo (magia, raça e classe social)", value="todas"),
])
@app_commands.autocomplete(personagem=_autocomplete_personagem)
@app_commands.check(_eh_mestre)
async def mestre_apagar(
    interaction: discord.Interaction, usuario: discord.Member, definicao: str, personagem: str | None = None
):
    char, erro = _resolver_do_alvo(usuario, personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return

    apagados = [c for c in _APAGAVEIS[definicao] if _valor_atual(char, c)]  # só o que estava mesmo definido
    antes = [f"{_ROTULO[c]}: {_valor_atual(char, c)}" for c in apagados]
    if not apagados:
        await interaction.response.send_message(
            f"**{char['name']}** não tem nada definido nisso pra apagar.", ephemeral=True
        )
        return

    db.clear_definition(char["id"], definicao)
    _auditar(interaction, usuario, char, "apagar", "; ".join(antes))

    embed = discord.Embed(
        title="🧹 Definição apagada",
        description=(
            f"{interaction.user.display_name} apagou {_juntar([_ROTULO_COM_ARTIGO[c] for c in apagados])} "
            f"de **{char['name']}**.\n"
            f"Antes era: {'; '.join(antes)}\n\n"
            f"{usuario.mention}, você pode rolar de novo com {_juntar([_COMANDO_DE_ROLAR[c] for c in apagados])}."
        ),
        color=discord.Color.orange(),
    )
    embed.set_footer(text="A rolagem antiga continua no histórico.")
    await interaction.response.send_message(
        content=usuario.mention, embed=embed, allowed_mentions=discord.AllowedMentions(users=[usuario])
    )


async def _corrigir(interaction: discord.Interaction, usuario: discord.Member, personagem: str | None,
                    campo: str, novo_valor: str):
    cfg = DEFINICOES[campo]
    char, erro = _resolver_do_alvo(usuario, personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return

    antes = _valor_atual(char, campo) or "nada"
    cfg["salvar"](char["id"], novo_valor, None)  # None = definido na mão, sem rolagem
    _auditar(interaction, usuario, char, f"corrigir_{campo}", f"{antes} -> {novo_valor}")
    nota = _nota_magia(char, db.get_character_by_id(char["id"]))

    embed = discord.Embed(
        title="🛠️ Definição corrigida",
        description=(
            f"{interaction.user.display_name} definiu {_ROTULO_COM_ARTIGO[campo]} de **{char['name']}** "
            f"({usuario.display_name}).\n**{antes}** → **{novo_valor}**" + (f"\n{nota}" if nota else "")
        ),
        color=discord.Color.orange(),
    )
    embed.set_footer(text="Definido por um mestre, sem rolagem.")
    await interaction.response.send_message(embed=embed)


@mestre_grupo.command(name="corrigir_magia", description="Define o Rank de magia de um personagem na mão, sem rolar.")
@app_commands.describe(
    usuario="Jogador dono do personagem",
    rank="O Rank certo",
    personagem="Opcional: personagem dele (padrão: o que ele está usando)",
)
@app_commands.choices(rank=[app_commands.Choice(name=n, value=n) for n in dice.MAGIC_RANKS])
@app_commands.autocomplete(personagem=_autocomplete_personagem)
@app_commands.check(_eh_mestre)
async def mestre_corrigir_magia(
    interaction: discord.Interaction, usuario: discord.Member, rank: str, personagem: str | None = None
):
    await _corrigir(interaction, usuario, personagem, "magic_rank", rank)


@mestre_grupo.command(name="corrigir_raca", description="Define a Raça de um personagem na mão, sem rolar.")
@app_commands.describe(
    usuario="Jogador dono do personagem",
    raca="A Raça certa",
    personagem="Opcional: personagem dele (padrão: o que ele está usando)",
)
@app_commands.choices(raca=[app_commands.Choice(name=n, value=n) for n in dice.RACES])
@app_commands.autocomplete(personagem=_autocomplete_personagem)
@app_commands.check(_eh_mestre)
async def mestre_corrigir_raca(
    interaction: discord.Interaction, usuario: discord.Member, raca: str, personagem: str | None = None
):
    await _corrigir(interaction, usuario, personagem, "race", raca)


@mestre_grupo.command(
    name="corrigir_estado",
    description="Define a Classe Social de um personagem na mão (serve pro 100 do sorteio).",
)
@app_commands.describe(
    usuario="Jogador dono do personagem",
    estado="O Estado certo",
    personagem="Opcional: personagem dele (padrão: o que ele está usando)",
)
@app_commands.choices(estado=[
    app_commands.Choice(name="1º Estado (Clero): Alto Clero", value="1-alto"),
    app_commands.Choice(name="1º Estado (Clero): Baixo Clero", value="1-baixo"),
    app_commands.Choice(name="2º Estado (Nobreza)", value="2"),
    app_commands.Choice(name="3º Estado (Povo)", value="3"),
])
@app_commands.autocomplete(personagem=_autocomplete_personagem)
@app_commands.check(_eh_mestre)
async def mestre_corrigir_estado(
    interaction: discord.Interaction, usuario: discord.Member, estado: str, personagem: str | None = None
):
    char, erro = _resolver_do_alvo(usuario, personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return

    novo_estado, novo_clero = _ESTADO_ESCOLHAS[estado]
    antes = _valor_atual(char, "social_class") or "nada"
    db.set_social_status(char["id"], novo_estado, None, novo_clero, None)  # None = definido na mão
    depois = rules.ESTADO_LABELS[novo_estado] + (f", {novo_clero}" if novo_clero else "")
    _auditar(interaction, usuario, char, "corrigir_social_class", f"{antes} -> {depois}")

    embed = discord.Embed(
        title="🛠️ Definição corrigida",
        description=(
            f"{interaction.user.display_name} definiu a Classe Social de **{char['name']}** "
            f"({usuario.display_name}).\n**{antes}** → **{depois}**"
        ),
        color=discord.Color.orange(),
    )
    embed.set_footer(text="Definido por um mestre, sem rolagem.")
    await interaction.response.send_message(embed=embed)


# --- XP e nível -------------------------------------------------------------

def _embed_xp(char, res: dict, motivo: str | None, mestre: str) -> discord.Embed:
    aplicado, antes, depois = res["applied"], res["before_level"], res["after_level"]
    linhas = [f"XP total: **{rules.fmt_xp(res['after_xp'])}**", _barra_xp(res["after_xp"])]
    if depois > antes:
        titulo = f"⬆️ {char['name']} subiu de nível! ({_mais(aplicado)} XP)"
        g = rules.gains_between(antes, depois, char["race"], char["class_name"])
        linhas.append(f"\nNível **{antes}** → **{depois}**\nGanhos: {rules.describe_gains(g)}")
        if g["atributo"]:
            linhas.append(
                f"Use `/atributos` pra distribuir {'o ponto' if g['atributo'] == 1 else 'os pontos'} de atributo. "
                "Distribui logo: o nível novo já conta com os atributos que você tiver."
            )
        if g["disciplina"]:
            linhas.append(
                f"Você ganhou +{g['disciplina']} ponto de Disciplina: gasta no botão **Disciplinas** do `/minha_ficha`."
            )
        cor = discord.Color.green()
    elif depois < antes:
        titulo = f"⬇️ {char['name']} perdeu nível ({_mais(aplicado)} XP)"
        linhas.append(
            f"\nNível **{antes}** → **{depois}**. Os pontos que vieram desses níveis precisam ser ajustados na ficha."
        )
        cor = discord.Color.orange()
    elif aplicado > 0:
        titulo = f"✨ {_mais(aplicado)} XP para {char['name']}"
        cor = discord.Color.gold()
    else:
        titulo = f"🛠️ {_mais(aplicado)} XP em {char['name']}"
        cor = discord.Color.orange()
    if motivo:
        linhas.append(f"Motivo: {motivo[:100]}")
    embed = discord.Embed(title=titulo, description="\n".join(linhas), color=cor)
    embed.set_footer(text=f"por {mestre}")
    return embed


async def _aplicar_xp(interaction: discord.Interaction, usuario: discord.Member, char, quantidade: int,
                      motivo: str | None, acao: str):
    res = db.add_xp(char["id"], quantidade, motivo, str(interaction.user.id), str(interaction.user.display_name))
    if res is None:
        await interaction.response.send_message("Esse personagem não existe mais.", ephemeral=True)
        return
    if res["applied"] == 0:
        await interaction.response.send_message(
            f"Nada mudou: **{char['name']}** continua com {rules.fmt_xp(res['after_xp'])} XP.", ephemeral=True
        )
        return

    _auditar(
        interaction, usuario, char, acao,
        f"{_mais(res['applied'])} XP, nível {res['before_level']} -> {res['after_level']}"
        + (f" ({motivo[:100]})" if motivo else ""),
    )
    embed = _embed_xp(char, res, motivo, interaction.user.display_name)
    if res["applied"] > 0:  # quem ganha XP é avisado; correção pra baixo vai sem marcar ninguém
        await interaction.response.send_message(
            content=usuario.mention, embed=embed, allowed_mentions=discord.AllowedMentions(users=[usuario])
        )
    else:
        await interaction.response.send_message(embed=embed)


@mestre_grupo.command(
    name="dar_xp",
    description="Dá XP por roleplay importante, missão de mestre ou desenvolvimento. O nível sobe sozinho.",
)
@app_commands.describe(
    usuario="Jogador dono do personagem",
    quantidade="Quanto XP dar (negativo tira, pra corrigir um engano)",
    motivo="Opcional: o roleplay, a missão ou o desenvolvimento (XP é por roleplay, não por ação avulsa)",
    personagem="Opcional: personagem dele (padrão: o que ele está usando)",
)
@app_commands.autocomplete(personagem=_autocomplete_personagem)
@app_commands.check(_eh_mestre)
async def mestre_dar_xp(
    interaction: discord.Interaction,
    usuario: discord.Member,
    quantidade: app_commands.Range[int, -50000, 50000],
    motivo: str | None = None,
    personagem: str | None = None,
):
    if quantidade == 0:
        await interaction.response.send_message("A quantidade precisa ser diferente de zero.", ephemeral=True)
        return
    char, erro = _resolver_do_alvo(usuario, personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return
    await _aplicar_xp(interaction, usuario, char, quantidade, motivo, "dar_xp")


@mestre_grupo.command(
    name="upar",
    description="Atalho: dá o XP que falta pra o personagem subir de nível (máximo 10).",
)
@app_commands.describe(
    usuario="Jogador dono do personagem",
    niveis="Quantos níveis subir (padrão 1)",
    personagem="Opcional: personagem dele (padrão: o que ele está usando)",
    motivo="Opcional: o roleplay, a missão de mestre ou o desenvolvimento",
)
@app_commands.autocomplete(personagem=_autocomplete_personagem)
@app_commands.check(_eh_mestre)
async def mestre_upar(
    interaction: discord.Interaction,
    usuario: discord.Member,
    niveis: app_commands.Range[int, 1, 9] = 1,
    personagem: str | None = None,
    motivo: str | None = None,
):
    char, erro = _resolver_do_alvo(usuario, personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return
    if char["level"] >= rules.MAX_LEVEL:
        await interaction.response.send_message(
            f"**{char['name']}** já está no nível máximo ({rules.MAX_LEVEL}).", ephemeral=True
        )
        return
    alvo = min(char["level"] + niveis, rules.MAX_LEVEL)
    falta = rules.xp_at_level_start(alvo) - char["xp"]
    await _aplicar_xp(interaction, usuario, char, falta, motivo or "atalho /mestre upar", "upar")


@mestre_grupo.command(
    name="corrigir_nivel",
    description="Põe o personagem no começo de um nível (de 1 a 10), com o XP mínimo dele.",
)
@app_commands.describe(
    usuario="Jogador dono do personagem",
    nivel="O nível certo",
    personagem="Opcional: personagem dele (padrão: o que ele está usando)",
)
@app_commands.autocomplete(personagem=_autocomplete_personagem)
@app_commands.check(_eh_mestre)
async def mestre_corrigir_nivel(
    interaction: discord.Interaction,
    usuario: discord.Member,
    nivel: app_commands.Range[int, 1, 10],
    personagem: str | None = None,
):
    char, erro = _resolver_do_alvo(usuario, personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return
    if char["level"] == nivel:
        await interaction.response.send_message(
            f"**{char['name']}** já está no nível {nivel}. Pra mexer só no XP, use `/mestre dar_xp`.", ephemeral=True
        )
        return
    diferenca = rules.xp_at_level_start(nivel) - char["xp"]
    await _aplicar_xp(interaction, usuario, char, diferenca, f"correção de nível pra {nivel}", "corrigir_nivel")


@mestre_grupo.command(name="rank_pericia", description="Define o Rank (0 a 10) de uma perícia especial de um personagem.")
@app_commands.describe(
    usuario="Jogador dono do personagem",
    pericia="Qual perícia especial",
    rank="O Rank novo (0 = nenhum Rank)",
    personagem="Opcional: personagem dele (padrão: o que ele está usando)",
)
@app_commands.choices(pericia=[app_commands.Choice(name=n, value=n) for n in rules.SPECIAL_SKILLS])
@app_commands.autocomplete(personagem=_autocomplete_personagem)
@app_commands.check(_eh_mestre)
async def mestre_rank_pericia(
    interaction: discord.Interaction,
    usuario: discord.Member,
    pericia: str,
    rank: app_commands.Range[int, 0, 10],
    personagem: str | None = None,
):
    char, erro = _resolver_do_alvo(usuario, personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return

    antes = db.get_skill_ranks(char["id"]).get(pericia, 0)
    db.set_skill_rank(char["id"], pericia, rank)
    _auditar(interaction, usuario, char, "rank_pericia", f"{pericia}: {antes} -> {rank}")

    subiu = rank > antes
    embed = discord.Embed(
        title=f"{'⬆️' if subiu else '🛠️'} {pericia}: Rank {rank}/{rules.MAX_SKILL_RANK}",
        description=(
            f"{interaction.user.display_name} definiu o Rank de **{pericia}** de **{char['name']}** "
            f"({usuario.display_name}).\n**{antes}** → **{rank}**\n{rules.bar(rank, rules.MAX_SKILL_RANK)}"
        ),
        color=discord.Color.green() if subiu else discord.Color.orange(),
    )
    await interaction.response.send_message(embed=embed)


@mestre_grupo.command(name="disciplina", description="Define o grau (0 a 5) de uma Disciplina de um personagem, sem conferir pontos.")
@app_commands.describe(
    usuario="Jogador dono do personagem",
    disciplina="Qual Disciplina",
    grau="O grau novo (0 tira a Disciplina; 4 e 5 só o mestre concede)",
    personagem="Opcional: personagem dele (padrão: o que ele está usando)",
)
@app_commands.choices(disciplina=[app_commands.Choice(name=n, value=n) for n in rules.DISCIPLINES])
@app_commands.autocomplete(personagem=_autocomplete_personagem)
@app_commands.check(_eh_mestre)
async def mestre_disciplina(
    interaction: discord.Interaction,
    usuario: discord.Member,
    disciplina: str,
    grau: app_commands.Range[int, 0, 5],
    personagem: str | None = None,
):
    char, erro = _resolver_do_alvo(usuario, personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return
    if not rules.has_disciplines(char["race"]):
        await interaction.response.send_message(
            f"**{char['name']}** é {char['race'] or 'de raça ainda não sorteada'}, e só Vampiros e Dhampirs têm Disciplinas. "
            "Se é uma exceção, corrige a raça antes com `/mestre corrigir_raca`.",
            ephemeral=True,
        )
        return
    if rules.discipline_blocked(disciplina):
        await interaction.response.send_message(paineis.TEXTO_DO_PROBLEMA["bloqueada"], ephemeral=True)
        return

    antes = db.get_disciplines(char["id"]).get(disciplina, 0)
    if grau == antes:
        await interaction.response.send_message(
            f"Nada mudou: **{char['name']}** já está com {disciplina} no grau {grau}.", ephemeral=True
        )
        return
    db.set_discipline_grade(char["id"], disciplina, grau)
    _auditar(interaction, usuario, char, "disciplina", f"{disciplina}: {antes} -> {grau}")

    graus = db.get_disciplines(char["id"])
    subiu = grau > antes
    linhas = [
        f"{interaction.user.display_name} definiu {disciplina} de **{char['name']}** ({usuario.display_name}).",
        f"**{antes}** → **{grau}**  {vitrine.barra_de_grau(grau)}",
        vitrine.linha_de_pontos(char["level"], char["race"], graus),
    ]
    if grau > rules.PLAYER_MAX_DISCIPLINE_GRADE:
        linhas.append("Grau concedido pelo mestre: os graus 4 e 5 não gastam ponto.")
    embed = discord.Embed(
        title=f"{'⬆️' if subiu else '🛠️'} {disciplina}: grau {grau}/{rules.MAX_DISCIPLINE_GRADE}",
        description="\n".join(linhas),
        color=discord.Color.dark_red() if subiu else discord.Color.orange(),
    )
    embed.set_footer(text="Os graus 1 a 3 contam como pontos gastos do jogador; o mestre não é barrado por eles.")
    await interaction.response.send_message(embed=embed)


_ESCOLHAS_DE_SORTE = [
    app_commands.Choice(name="Vantagem (fica o maior de 2 d20)", value="vantagem"),
    app_commands.Choice(name="Desvantagem (fica o menor de 2 d20)", value="desvantagem"),
    app_commands.Choice(name="Bônus no total", value="bonus"),
    app_commands.Choice(name="Penalidade no total", value="penalidade"),
    app_commands.Choice(name="Dado mínimo (o d20 não cai abaixo)", value="minimo"),
    app_commands.Choice(name="Dado máximo (o d20 não passa disso)", value="maximo"),
    app_commands.Choice(name="Dado fixo (o d20 sai sempre esse número)", value="fixo"),
    app_commands.Choice(name="Ver os efeitos ativos", value="ver"),
    app_commands.Choice(name="Limpar todos os efeitos", value="limpar"),
]


def _linha_de_efeito(e) -> str:
    partes = [dice.descrever_efeito(e["kind"], e["value"]), f"{e['uses_left']} {'uso' if e['uses_left'] == 1 else 'usos'}"]
    if e["quiet"]:
        partes.append("discreto")
    if e["note"]:
        partes.append(f"nota: {e['note']}")
    return "• " + " · ".join(partes)


@mestre_grupo.command(name="sorte", description="Mexe na sorte dos d20 de um personagem: vantagem, bônus, dado mínimo...")
@app_commands.describe(
    usuario="Jogador dono do personagem",
    efeito="O que fazer com a sorte dele",
    valor="Pro bônus, a penalidade, o dado mínimo, o máximo e o fixo (de 1 a 20)",
    usos="Quantas rolagens de d20 o efeito afeta (de 1 a 20, padrão 1)",
    discreto="Ligado, o cartão da rolagem NÃO mostra a marca 🍀 (por padrão ela aparece)",
    personagem="Opcional: personagem dele (padrão: o que ele está usando)",
    motivo="Opcional: uma anotação sua (o jogador não vê)",
)
@app_commands.choices(efeito=_ESCOLHAS_DE_SORTE)
@app_commands.autocomplete(personagem=_autocomplete_personagem)
@app_commands.check(_eh_mestre)
async def mestre_sorte(
    interaction: discord.Interaction, usuario: discord.Member, efeito: str,
    valor: app_commands.Range[int, 1, 20] | None = None, usos: app_commands.Range[int, 1, 20] = 1,
    discreto: bool = False, personagem: str | None = None, motivo: app_commands.Range[str, 1, 100] | None = None,
):
    char, erro = _resolver_do_alvo(usuario, personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return
    if efeito == "ver":
        ativos = db.get_dice_effects(char["id"])
        texto = "\n".join(_linha_de_efeito(e) for e in ativos) if ativos else "Nenhum efeito ativo."
        await interaction.response.send_message(f"🍀 **Sorte de {char['name']}**\n{texto}", ephemeral=True)
        return
    if efeito == "limpar":
        quantos = db.clear_dice_effects(char["id"])
        _auditar(interaction, usuario, char, "sorte_limpar", f"{quantos} efeito(s) tirado(s)")
        await interaction.response.send_message(
            f"🍀 Tirei {quantos} {'efeito' if quantos == 1 else 'efeitos'} de sorte de **{char['name']}**.", ephemeral=True
        )
        return
    if efeito in dice.EFEITOS_COM_VALOR and valor is None:
        await interaction.response.send_message(
            f"O efeito **{dice.EFEITO_NOME[efeito]}** precisa do campo `valor` (de 1 a 20).", ephemeral=True
        )
        return
    db.add_dice_effect(char["id"], efeito, valor, usos, discreto, motivo, str(interaction.user.id))
    descrito = dice.descrever_efeito(efeito, valor if efeito in dice.EFEITOS_COM_VALOR else None)
    _auditar(
        interaction, usuario, char, "sorte",
        f"{descrito} x{usos}" + (" (discreto)" if discreto else "") + (f": {motivo}" if motivo else ""),
    )
    await interaction.response.send_message(
        f"🍀 **{char['name']}** agora tem **{descrito}** nas próximas {usos} {'rolagem' if usos == 1 else 'rolagens'} de d20.\n"
        + ("Nada aparece no cartão da rolagem (discreto). " if discreto else "O cartão da rolagem mostra a marca 🍀. ")
        + "Vale só pra um d20 sozinho (`1d20`, `d20+5`, `3#d20`), rolado pelo `/rolar`, pela bandeja ou escrito no chat. "
        "Não mexe nos sorteios da criação nem na iniciativa. Confere com `efeito: Ver`.",
        ephemeral=True,
    )


@mestre_grupo.command(name="habilidades", description="A fila das habilidades que os jogadores criaram: ajusta, aprova ou recusa.")
@app_commands.check(_eh_mestre)
async def mestre_habilidades(interaction: discord.Interaction):
    fila = escudo.FilaDeHabilidades(interaction.user.id)
    await interaction.response.send_message(embed=fila.embed(), view=fila, ephemeral=True)
    fila.origem = interaction


@mestre_grupo.command(name="pericia", description="Define os pontos de uma perícia de um personagem (conserta distribuição).")
@app_commands.describe(
    usuario="Jogador dono do personagem", pericia="A perícia", pontos="Quantos pontos ela passa a ter (de 0 a 20)",
    personagem="Opcional: personagem dele (padrão: o que ele está usando)",
)
@app_commands.choices(pericia=[app_commands.Choice(name=p, value=p) for p in rules.SKILLS])
@app_commands.autocomplete(personagem=_autocomplete_personagem)
@app_commands.check(_eh_mestre)
async def mestre_pericia(
    interaction: discord.Interaction, usuario: discord.Member, pericia: str, pontos: app_commands.Range[int, 0, 20],
    personagem: str | None = None,
):
    char, erro = _resolver_do_alvo(usuario, personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return
    antes = db.get_skills(char["id"]).get(pericia, 0)
    db.set_skill_points(char["id"], pericia, pontos)
    _auditar(interaction, usuario, char, "pericia", f"{pericia}: {antes} -> {pontos}")
    livres = rules.skill_points_free(char["level"], char["class_name"], db.get_skills(char["id"]))
    await interaction.response.send_message(
        f"🎯 **{char['name']}**: {pericia} foi de {antes} pra **{pontos}**. Pontos livres agora: **{livres}**.", ephemeral=True
    )


@mestre_grupo.command(name="comecar_aqui", description="Posta no canal a mensagem de boas-vindas com os botões (criar personagem, ficha, dados).")
@app_commands.check(_eh_mestre)
async def mestre_comecar_aqui(interaction: discord.Interaction):
    await interaction.response.send_message(embed=_embed_comeco(), view=ComecoAqui())
    await interaction.followup.send(
        "📌 Postei. Fixa a mensagem no canal (o pino) pra ela ficar sempre à vista. Os botões continuam funcionando "
        "mesmo se o bot reiniciar.",
        ephemeral=True,
    )


@mestre_grupo.command(name="escudo", description="Abre o Escudo do Mestre: iniciativa e intenções da cena deste canal.")
@app_commands.check(_eh_mestre)
async def mestre_escudo(interaction: discord.Interaction):
    painel = escudo.EscudoDoMestre(interaction.user.id, str(interaction.channel_id))
    await interaction.response.send_message(embed=painel.embed(), view=painel, ephemeral=True)
    painel.origem = interaction


# --- Ver, vagas e excluir ----------------------------------------------------

@mestre_grupo.command(name="ficha", description="Mostra a ficha completa de um personagem de outro jogador.")
@app_commands.describe(
    usuario="Jogador dono do personagem",
    personagem="Opcional: personagem dele (padrão: o que ele está usando)",
)
@app_commands.autocomplete(personagem=_autocomplete_personagem)
@app_commands.check(_eh_mestre)
async def mestre_ficha(interaction: discord.Interaction, usuario: discord.Member, personagem: str | None = None):
    char, erro = _resolver_do_alvo(usuario, personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return
    await interaction.response.send_message(embed=_embed_ficha(char, usuario.display_name, para_mestre=True), ephemeral=True)


@mestre_grupo.command(name="jogador", description="Mostra quantos personagens um jogador tem, as vagas e o XP de cada um.")
@app_commands.describe(usuario="O jogador")
@app_commands.check(_eh_mestre)
async def mestre_jogador(interaction: discord.Interaction, usuario: discord.Member):
    uid = str(usuario.id)
    chars = db.list_characters(uid)
    usadas, permitidas, extras = _vagas(uid)
    excluidos = db.count_deleted(uid)

    linhas = [
        f"Personagens: **{usadas}** de **{permitidas}** vagas ({LIMITE_BASE} padrão + {extras} "
        f"{'extra' if extras == 1 else 'extras'})",
        f"XP somado: **{rules.fmt_xp(sum(c['xp'] for c in chars))}**",
        f"Já excluiu: **{excluidos}** {'personagem' if excluidos == 1 else 'personagens'}",
    ]
    if chars:
        linhas.append("")
        for c in chars:
            linhas.append(
                f"**{c['name']}** · nível {c['level']} · {rules.fmt_xp(c['xp'])} XP · {c['race'] or 'sem raça'}"
            )
    else:
        linhas.append("\nAinda não criou nenhum personagem.")
    embed = discord.Embed(title=f"👤 {usuario.display_name}", description="\n".join(linhas), color=discord.Color.blurple())
    await interaction.response.send_message(embed=embed, ephemeral=True)


@mestre_grupo.command(name="vagas", description="Define quantas vagas EXTRAS de personagem um jogador tem.")
@app_commands.describe(
    usuario="O jogador",
    extras=f"Vagas extras, de 0 a {MAX_VAGAS_EXTRAS} (todo mundo já pode ter {LIMITE_BASE} personagens)",
)
@app_commands.check(_eh_mestre)
async def mestre_vagas(
    interaction: discord.Interaction, usuario: discord.Member, extras: app_commands.Range[int, 0, MAX_VAGAS_EXTRAS]
):
    uid = str(usuario.id)
    antes = db.get_extra_slots(uid)
    db.set_extra_slots(uid, extras)
    usadas, permitidas, _ = _vagas(uid)
    db.log_master_action(
        master_id=str(interaction.user.id),
        master_name=str(interaction.user.display_name),
        target_user_id=uid,
        character_id=None,
        character_name=None,
        action="vagas",
        detail=f"extras {antes} -> {extras}",
    )
    embed = discord.Embed(
        title="🎟️ Vagas de personagem",
        description=(
            f"{interaction.user.display_name} definiu as vagas extras de {usuario.display_name}: "
            f"**{antes}** → **{extras}**.\n"
            f"Agora são {permitidas} vagas ({LIMITE_BASE} padrão + {extras} "
            f"{'extra' if extras == 1 else 'extras'}), {usadas} em uso."
        ),
        color=discord.Color.blurple(),
    )
    await interaction.response.send_message(embed=embed)


@mestre_grupo.command(name="excluir_personagem", description="Exclui pra sempre um personagem de outro jogador.")
@app_commands.describe(usuario="Jogador dono do personagem", personagem="Nome do personagem que vai ser excluído")
@app_commands.autocomplete(personagem=_autocomplete_personagem)
@app_commands.check(_eh_mestre)
async def mestre_excluir_personagem(interaction: discord.Interaction, usuario: discord.Member, personagem: str):
    char, erro = _resolver_do_alvo(usuario, personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return
    view = ConfirmarExclusao(interaction.user, char, str(usuario.id), por_mestre=True)
    await interaction.response.send_message(
        embed=_embed_aviso_exclusao(char, usuario.display_name), view=view, ephemeral=True
    )
    view.origem = interaction


def _rolagens(n: int) -> str:
    return f"{n} {'rolagem' if n == 1 else 'rolagens'}"


class ConfirmarApagarHistorico(discord.ui.View):
    """Botões de confirmação pra apagar o histórico de rolagens de um jogador. Só quem pediu aperta."""

    def __init__(self, executor, alvo):
        super().__init__(timeout=60)
        self.executor = executor
        self.alvo_id = str(alvo.id)
        self.alvo_nome = alvo.display_name
        self.origem: discord.Interaction | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.executor.id:
            await interaction.response.send_message("Só quem pediu pode confirmar.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Apagar histórico", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        if not _eh_mestre(interaction):  # a permissão pode ter mudado nos 60 segundos
            await interaction.response.edit_message(
                content="Você não é mais mestre aqui, então nada foi apagado.", embed=None, view=None
            )
            return
        apagadas = db.delete_rolls(self.alvo_id)
        if not apagadas:
            await interaction.response.edit_message(
                content="Esse histórico já estava vazio, então nada foi apagado.", embed=None, view=None
            )
            return
        db.log_master_action(
            master_id=str(self.executor.id),
            master_name=str(self.executor.display_name),
            target_user_id=self.alvo_id,
            character_id=None,
            character_name=None,
            action="apagar_historico",
            detail=_rolagens(apagadas),
        )
        await interaction.response.edit_message(
            content=f"🧹 O histórico de **{self.alvo_nome}** foi apagado ({_rolagens(apagadas)}).", embed=None, view=None
        )
        aviso = discord.Embed(
            title="🧹 Histórico apagado",
            description=(
                f"{self.executor.display_name} apagou o histórico de rolagens de <@{self.alvo_id}> "
                f"({_rolagens(apagadas)}). A ficha, o XP e os personagens continuam como estavam."
            ),
            color=discord.Color.orange(),
        )
        await interaction.followup.send(embed=aviso)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="Beleza, nada foi apagado.", embed=None, view=None)

    async def on_timeout(self):
        if self.origem is not None:
            try:
                await self.origem.edit_original_response(
                    content="Passou o tempo e nada foi apagado.", embed=None, view=None
                )
            except discord.HTTPException:
                pass


@mestre_grupo.command(name="apagar_historico", description="Apaga o histórico de rolagens de um jogador (pede confirmação).")
@app_commands.describe(usuario="Jogador que vai ter o histórico de rolagens apagado")
@app_commands.check(_eh_mestre)
async def mestre_apagar_historico(interaction: discord.Interaction, usuario: discord.Member):
    total = db.count_rolls(str(usuario.id))
    if not total:
        await interaction.response.send_message(
            f"{usuario.display_name} não tem nenhuma rolagem no histórico.", ephemeral=True
        )
        return
    embed = discord.Embed(
        title=f"🧹 Apagar o histórico de {usuario.display_name}?",
        description=(
            f"Isso apaga **{_rolagens(total)}** do `/historico` de {usuario.display_name}, de todos os personagens "
            "dele. Não tem como desfazer.\n\n"
            "A ficha, o XP e os personagens não mudam. Mas as rolagens dos sorteios de criação (raça, magia e "
            "classe social) também somem, e é por elas que dá pra ver se alguém rolou de novo."
        ),
        color=discord.Color.orange(),
    )
    view = ConfirmarApagarHistorico(interaction.user, usuario)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    view.origem = interaction


@mestre_grupo.command(name="atributos", description="Define atributos de um personagem na mão, sem conferir limites.")
@app_commands.describe(
    usuario="Jogador dono do personagem",
    **{a: f"Novo valor de {rules.ATTRIBUTE_LABELS[a]}" for a in rules.ATTRIBUTES},
    personagem="Opcional: personagem dele (padrão: o que ele está usando)",
)
@app_commands.autocomplete(personagem=_autocomplete_personagem)
@app_commands.check(_eh_mestre)
async def mestre_atributos(
    interaction: discord.Interaction,
    usuario: discord.Member,
    forca: app_commands.Range[int, 0, 30] | None = None,
    destreza: app_commands.Range[int, 0, 30] | None = None,
    vitalidade: app_commands.Range[int, 0, 30] | None = None,
    razao: app_commands.Range[int, 0, 30] | None = None,
    vontade: app_commands.Range[int, 0, 30] | None = None,
    alma: app_commands.Range[int, 0, 30] | None = None,
    personagem: str | None = None,
):
    pedidos = {
        nome: valor
        for nome, valor in [("forca", forca), ("destreza", destreza), ("vitalidade", vitalidade),
                            ("razao", razao), ("vontade", vontade), ("alma", alma)]
        if valor is not None
    }
    if not pedidos:
        await interaction.response.send_message("Preenche pelo menos um atributo.", ephemeral=True)
        return
    char, erro = _resolver_do_alvo(usuario, personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return

    antes = db.attributes_of(char)
    mudancas = {n: v for n, v in pedidos.items() if v != antes[n]}
    if not mudancas:
        await interaction.response.send_message(
            f"Nada mudou: **{char['name']}** já tem esses valores.", ephemeral=True
        )
        return
    db.set_attributes(char["id"], mudancas)
    _auditar(interaction, usuario, char, "atributos", "; ".join(f"{n} {antes[n]} -> {v}" for n, v in mudancas.items()))

    novo = db.get_character_by_id(char["id"])
    linhas = [f"{rules.ATTRIBUTE_LABELS[n]}: **{antes[n]}** → **{v}**" for n, v in mudancas.items()]
    embed = discord.Embed(
        title="🛠️ Atributos corrigidos",
        description=(
            f"{interaction.user.display_name} mexeu nos atributos de **{char['name']}** ({usuario.display_name}).\n"
            + "\n".join(linhas) + "\n" + _texto_pontos(novo)
        ),
        color=discord.Color.orange(),
    )
    embed.set_footer(text="Definido por um mestre, sem conferir os limites.")
    await interaction.response.send_message(embed=embed)


@mestre_grupo.command(name="corrigir_classe", description="Define a classe de um personagem na mão.")
@app_commands.describe(
    usuario="Jogador dono do personagem",
    classe="A classe certa",
    personagem="Opcional: personagem dele (padrão: o que ele está usando)",
)
@app_commands.choices(classe=[app_commands.Choice(name=n, value=n) for n in rules.CLASSES])
@app_commands.autocomplete(personagem=_autocomplete_personagem)
@app_commands.check(_eh_mestre)
async def mestre_corrigir_classe(
    interaction: discord.Interaction, usuario: discord.Member, classe: str, personagem: str | None = None
):
    char, erro = _resolver_do_alvo(usuario, personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return
    antes = char["class_name"] or "nada"
    db.set_class(char["id"], classe)
    _auditar(interaction, usuario, char, "corrigir_class", f"{antes} -> {classe}")
    nota = _nota_magia(char, db.get_character_by_id(char["id"]))
    embed = discord.Embed(
        title="🛠️ Definição corrigida",
        description=(
            f"{interaction.user.display_name} definiu a classe de **{char['name']}** ({usuario.display_name}).\n"
            f"**{antes}** → **{classe}**" + (f"\n{nota}" if nota else "")
        ),
        color=discord.Color.orange(),
    )
    embed.set_footer(text="Definido por um mestre.")
    await interaction.response.send_message(embed=embed)


@mestre_grupo.command(name="exportar", description="Manda uma cópia de segurança do banco de dados (só você vê).")
@app_commands.check(_eh_mestre)
async def mestre_exportar(interaction: discord.Interaction):
    limite = getattr(interaction.guild, "filesize_limit", None) or 8 * 1024 * 1024
    with tempfile.TemporaryDirectory() as pasta:
        nome = f"baptism_of_blood_{datetime.now(timezone.utc):%Y-%m-%d_%H%M}.db"
        destino = os.path.join(pasta, nome)
        db.export_copy(destino)
        tamanho = os.path.getsize(destino)
        if tamanho > limite:
            await interaction.response.send_message(
                f"O banco tem {tamanho / 1048576:.1f} MB e este servidor só aceita arquivo de até "
                f"{limite / 1048576:.0f} MB. Baixa direto pelo Railway (`railway volume files download`).",
                ephemeral=True,
            )
            return
        db.log_master_action(
            master_id=str(interaction.user.id),
            master_name=str(interaction.user.display_name),
            target_user_id=str(interaction.user.id),
            character_id=None,
            character_name=None,
            action="exportar",
            detail=f"{tamanho} bytes",
        )
        arquivo = discord.File(destino, filename=nome)
        try:
            await interaction.response.send_message(
                "Cópia de segurança do banco. Guarda em lugar seguro, porque tem os dados de todos os jogadores.",
                file=arquivo,
                ephemeral=True,
            )
        finally:
            arquivo.close()


bot.tree.add_command(mestre_grupo)


async def _rolar_do_painel(coletor, notacao: str, motivo: str | None):
    """A rolagem da bandeja: a mesma regra de ficha pronta do /rolar (que é um filtro do comando, então aqui
    a checagem é feita na mão) e depois o mesmo código do /rolar."""
    try:
        await _exigir_personagem_pronto(coletor)
    except FichaIncompleta as e:
        coletor.avisar(e.mensagem)
        return
    await rolar.callback(coletor, dado=notacao, motivo=motivo, personagem=None)


async def _painel_sortear(coletor, passo: str, nome: str, repetir: bool = False):
    if passo == "raca":
        await _sortear_definicao(coletor, "race", nome, repetir)
    elif passo == "estado":
        await _sortear_estado(coletor, nome, repetir)
    elif passo == "magia":
        await _sortear_definicao(coletor, "magic_rank", nome)
    else:
        raise ValueError(f"Passo desconhecido: {passo}")


paineis.registrar(paineis.Ganchos(
    embed_ficha=_embed_ficha,
    sortear=_painel_sortear,
    escolher_classe=lambda coletor, classe, nome, habilidade=None: classe_escolher.callback(coletor, classe, habilidade, nome),
    atributos=lambda coletor, valores, nome: atributos.callback(coletor, personagem=nome, **valores),
    rolar=_rolar_do_painel,
    niveis=lambda coletor, nome: niveis.callback(coletor, nome),
    ajuda=lambda coletor: _responder_ajuda(coletor, None),
    ordem_ligada=lambda: ORDEM_DA_CRIACAO,
    recursos=_recursos_do_personagem,
    teste=_teste_de_pericia,
))


escudo.registrar(eh_mestre=_membro_eh_mestre, bloqueio_de_rolagem=_bloqueio_curto)


async def _preparar_bot():
    """Roda uma vez, antes de conectar: registra os botões do quadro da cena, que têm identificador fixo e
    por isso continuam funcionando nas mensagens antigas depois que o bot reinicia."""
    bot.add_view(escudo.QuadroDaCena())
    bot.add_view(ComecoAqui())


bot.setup_hook = _preparar_bot


def main():
    if not TOKEN:
        raise SystemExit("Defina DISCORD_TOKEN no arquivo .env antes de rodar o bot.")
    db.init_db()  # antes de conectar: se o caminho do banco estiver errado, o erro aparece na hora
    try:
        bot.run(TOKEN)
    except discord.PrivilegedIntentsRequired:
        if not DADOS_POR_TEXTO:
            raise
        # O Message Content Intent não está ligado no Portal do Desenvolvedor. Em vez de ficar fora do ar,
        # o bot reinicia sem os dados por texto (os comandos de barra seguem funcionando).
        print(
            "AVISO: o Discord recusou a leitura de mensagens. Pra usar dados por texto (d20+5), ligue o "
            "'Message Content Intent' em discord.com/developers > seu app > Bot > Privileged Gateway Intents "
            "e reinicie o bot. Reiniciando agora SEM os dados por texto.",
            flush=True,
        )
        os.environ["DADOS_POR_TEXTO"] = "0"
        os.execv(sys.executable, [sys.executable, *sys.argv])


if __name__ == "__main__":
    main()
