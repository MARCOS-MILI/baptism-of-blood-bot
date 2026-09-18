"""Bot de Discord do Baptism of Blood.

Jogadores:
  /rolar dado:1d20+3 [motivo] [personagem]   -> rola e salva no histórico
  /historico [usuario] [limite] [personagem] -> últimas rolagens de alguém (ou de um personagem)
  /personagem criar | usar | listar | excluir -> gerencia os personagens (limite de vagas por jogador)
  /magia_inicial | /raca_inicial | /classe_social -> sorteios de criação, uma vez por personagem
  /minha_ficha [personagem]                  -> nível, XP, raça, classe social, ranks
  /niveis [personagem]                       -> XP e vantagens de cada nível
  /extrato_xp [personagem]                   -> de onde veio o XP do personagem
  /rank [tipo] [limite]                      -> rank público de XP total (personagens ou jogadores)
  /calcular_recursos                         -> calcula Vida, Sanidade, Mana e Estamina

Mestres:
  /mestre dar_xp | upar | corrigir_nivel | rank_pericia
  /mestre apagar | corrigir_magia | corrigir_raca | corrigir_estado
  /mestre ficha | jogador | vagas | excluir_personagem

Setup rápido:
  1. pip install -r requirements.txt
  2. Cria um arquivo .env com DISCORD_TOKEN=seu_token_aqui (veja o README)
  3. python bot.py
"""

import os
import traceback
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

import db
import dice
import rules

load_dotenv()
TOKEN = os.environ.get("DISCORD_TOKEN")

# Quem tem esse cargo (ou a permissão de Gerenciar Servidor) pode usar os comandos /mestre.
MESTRE_ROLE = os.environ.get("MESTRE_ROLE", "Mestre")

# Quantos personagens cada jogador pode ter. Os mestres liberam vagas extras na mão, até o teto.
LIMITE_BASE = int(os.environ.get("LIMITE_PERSONAGENS", "3"))
LIMITE_MAXIMO = max(LIMITE_BASE, int(os.environ.get("LIMITE_MAXIMO_PERSONAGENS", "10")))
MAX_VAGAS_EXTRAS = LIMITE_MAXIMO - LIMITE_BASE

NOME_MIN, NOME_MAX = 2, 60


class Arvore(app_commands.CommandTree):
    """Antes de cada comando, guarda o nome atual do jogador (o rank usa isso pra mostrar o dono)."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        try:
            db.remember_player(str(interaction.user.id), str(interaction.user.display_name))
        except Exception as e:  # nunca deixar de responder um comando por causa disso
            print(f"Não consegui guardar o nome do jogador: {e!r}", flush=True)
        return True


intents = discord.Intents.default()
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
    if not db.storage_is_persistent():
        print(
            "AVISO: o banco está na pasta do bot e some a cada redeploy. "
            "No Railway, anexe um Volume ao serviço (veja o README).",
            flush=True,
        )


# ---------------------------------------------------------------------------
# Erros e permissão de mestre
# ---------------------------------------------------------------------------

def _eh_mestre(interaction: discord.Interaction) -> bool:
    membro = interaction.user
    perms = getattr(membro, "guild_permissions", None)
    if perms and (perms.administrator or perms.manage_guild):
        return True
    cargo = MESTRE_ROLE.casefold()
    return any(r.name.casefold() == cargo for r in getattr(membro, "roles", []))


def _cargo_mestre(guild: discord.Guild | None):
    """O cargo de mestre do servidor, se existir (usado pra avisar os mestres)."""
    if guild is None:
        return None
    cargo = MESTRE_ROLE.casefold()
    return next((r for r in guild.roles if r.name.casefold() == cargo), None)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
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


def _texto_definicao(personagem, campo: str, comando: str) -> str:
    valor = personagem[campo]
    if not valor:
        return f"ainda não definido\n(use `{comando}`)"
    rolagem = personagem[f"{campo}_roll"]
    origem = "definido por um mestre" if rolagem is None else f"1d100: {rolagem}"
    return f"{valor}\n({origem})"


def _resumo_estado(personagem) -> str | None:
    """'2º Estado (Nobreza)', '1º Estado (Clero), Alto Clero' ou 'aguardando o mestre'."""
    estado = personagem["social_class"]
    if not estado:
        return None
    if estado == dice.SOCIAL_CLASS_MASTER:
        return "aguardando o mestre"
    texto = rules.ESTADO_LABELS.get(estado, estado)
    if personagem["clergy"]:
        texto += f", {personagem['clergy']}"
    return texto


def _texto_estado(personagem) -> str:
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


def _embed_ficha(personagem, jogador: str) -> discord.Embed:
    nivel, xp = personagem["level"], personagem["xp"]
    _, dentro, precisa = rules.xp_progress(xp)
    embed = discord.Embed(title=f"📖 Ficha de {personagem['name']}", color=discord.Color.dark_purple())
    nivel_txt = f"{nivel}/{rules.MAX_LEVEL}\n{rules.bar(nivel, rules.MAX_LEVEL)}\nXP total: {rules.fmt_xp(xp)}"
    if precisa is not None:
        nivel_txt += f"\nFaltam {rules.fmt_xp(precisa - dentro)} pro nível {nivel + 1}"
    embed.add_field(name="Nível", value=nivel_txt, inline=True)
    embed.add_field(name="Raça", value=_texto_definicao(personagem, "race", "/raca_inicial"), inline=True)
    embed.add_field(name="Classe Social", value=_texto_estado(personagem), inline=True)
    embed.add_field(name="Rank de Magia", value=_texto_definicao(personagem, "magic_rank", "/magia_inicial"), inline=True)
    ranks = db.get_skill_ranks(personagem["id"])
    linhas = [
        f"**{pericia}** {ranks[pericia]}/{rules.MAX_SKILL_RANK} {rules.bar(ranks[pericia], rules.MAX_SKILL_RANK)}"
        for pericia in rules.SPECIAL_SKILLS
        if ranks.get(pericia)
    ]
    embed.add_field(
        name="Ranks das perícias especiais",
        value="\n".join(linhas) or "nenhum grau ainda",
        inline=False,
    )
    embed.set_footer(text=f"jogador: {jogador}")
    return embed


# ---------------------------------------------------------------------------
# Rolagens e histórico
# ---------------------------------------------------------------------------

@bot.tree.command(name="rolar", description="Rola um dado (ex: 1d20, 2d6+3) e guarda no histórico.")
@app_commands.describe(
    dado="Notação do dado, tipo 1d20 ou 2d6+3",
    motivo="Opcional: pra que é essa rolagem",
    personagem="Opcional: rolar por outro personagem seu (padrão: o que você está usando)",
)
@app_commands.autocomplete(personagem=_autocomplete_personagem)
async def rolar(interaction: discord.Interaction, dado: str, motivo: str | None = None, personagem: str | None = None):
    uid = str(interaction.user.id)
    try:
        resultado = dice.roll(dado)
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

    db.log_roll(
        user_id=uid,
        username=str(interaction.user.display_name),
        guild_id=str(interaction.guild_id) if interaction.guild_id else None,
        notation=dado,
        rolls=resultado.rolls,
        total=resultado.total,
        purpose=motivo,
        character_id=char["id"] if char else None,
        character_name=char["name"] if char else None,
    )

    quem = char["name"] if char else interaction.user.display_name
    embed = discord.Embed(
        title=f"🎲 {quem} rolou {dado}",
        description=f"**{resultado.describe()} = {resultado.total}**",
        color=discord.Color.dark_red(),
    )
    rodape = []
    if motivo:
        rodape.append(motivo)
    if char:
        rodape.append(f"jogador: {interaction.user.display_name}")
    if rodape:
        embed.set_footer(text=" · ".join(rodape))
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="historico", description="Mostra as últimas rolagens de um usuário (ou de um personagem dele).")
@app_commands.describe(
    usuario="De quem ver o histórico (padrão: você mesmo)",
    limite="Quantas rolagens mostrar (padrão 10)",
    personagem="Opcional: só as rolagens desse personagem",
)
@app_commands.autocomplete(personagem=_autocomplete_personagem)
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
            name=f"{linha['notation']} = {linha['total']}{motivo}",
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
            "Próximos passos: `/magia_inicial`, `/raca_inicial` e `/classe_social`."
        ),
        color=discord.Color.dark_purple(),
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


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
            f"　magia: {c['magic_rank'] or 'sem rank'} · raça: {c['race'] or 'sem raça'}"
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


async def _sortear_definicao(interaction: discord.Interaction, campo: str, personagem_nome: str | None):
    cfg = DEFINICOES[campo]
    uid = str(interaction.user.id)

    char, erro = _resolver(uid, personagem_nome)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return

    if char[campo]:
        rolagem = char[f"{campo}_roll"]
        detalhe = "definido por um mestre" if rolagem is None else f"resultado {rolagem} no 1d100"
        await interaction.response.send_message(
            f"**{char['name']}** já tem {cfg['rotulo']}: **{char[campo]}** ({detalhe}). "
            "Fala com um mestre se precisar rolar de novo.",
            ephemeral=True,
        )
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
    cfg["salvar"](char["id"], definido, valor)

    embed = discord.Embed(
        title=f"{cfg['emoji']} {cfg['titulo']} de {char['name']}",
        description=f"1d100 = **{valor}**\n{cfg['resultado']}: **{definido}**",
        color=cfg["cor"],
    )
    embed.set_footer(text=f"jogador: {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="magia_inicial", description="Rola 1d100 e define o Rank de magia inicial do seu personagem.")
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
    uid = str(interaction.user.id)
    char, erro = _resolver(uid, personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return

    if char["social_class"]:
        if char["social_class"] == dice.SOCIAL_CLASS_MASTER:
            msg = (
                f"**{char['name']}** tirou 100 no sorteio da Classe Social, então quem decide o Estado é o mestre. "
                "Fala com um mestre."
            )
        else:
            msg = (
                f"**{char['name']}** já tem Classe Social: **{_resumo_estado(char)}**. "
                "Fala com um mestre se precisar rolar de novo."
            )
        await interaction.response.send_message(msg, ephemeral=True)
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
    db.set_social_status(char["id"], estado, r1.total, clero, r2.total if r2 else None)

    embed = discord.Embed(title=f"⚜️ Classe Social de {char['name']}", color=discord.Color.gold())
    linhas = [f"1d100 = **{r1.total}**"]
    ping = {}
    if estado == dice.SOCIAL_CLASS_MASTER:
        linhas.append("Resultado especial! Quem decide o Estado desse personagem é o mestre. Fala com um mestre.")
        cargo = _cargo_mestre(interaction.guild)
        if cargo:
            ping = {"content": cargo.mention, "allowed_mentions": discord.AllowedMentions(roles=[cargo])}
    else:
        linhas.append(f"Estado: **{rules.ESTADO_LABELS[estado]}**")
        if clero:
            linhas.append(f"Outro 1d100 = **{r2.total}**\nClero: **{clero}**")
    embed.description = "\n".join(linhas)
    embed.set_footer(text=f"jogador: {nome_jogador}")
    await interaction.response.send_message(embed=embed, **ping)


# ---------------------------------------------------------------------------
# Ficha, XP, níveis, rank e calculadora de recursos
# ---------------------------------------------------------------------------

@bot.tree.command(name="minha_ficha", description="Mostra nível, XP, raça, classe social e ranks do seu personagem.")
@app_commands.describe(personagem="Opcional: qual personagem seu (padrão: o que você está usando)")
@app_commands.autocomplete(personagem=_autocomplete_personagem)
async def minha_ficha(interaction: discord.Interaction, personagem: str | None = None):
    char, erro = _resolver(str(interaction.user.id), personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return
    await interaction.response.send_message(
        embed=_embed_ficha(char, interaction.user.display_name), ephemeral=True
    )


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
    descricao = (
        "\n".join(rules.level_table_lines(atual, raca))
        + f"\n\n**Somando tudo, do 1 ao {rules.MAX_LEVEL}:** "
        + rules.describe_gains(rules.total_gains(rules.MAX_LEVEL, raca))
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
                f"nível {atual + 1}: {rules.describe_gains(rules.gains_for_level(atual + 1, raca))}"
                f" (faltam {rules.fmt_xp(precisa - dentro)} XP)"
            )
        embed.add_field(
            name=f"{char['name']}: nível {atual}/{rules.MAX_LEVEL}",
            value=(
                f"{_barra_xp(xp)}\n"
                f"XP total: {rules.fmt_xp(xp)}\n"
                f"Já ganhou: {rules.describe_gains(rules.total_gains(atual, raca))}\n"
                f"Próximo, {proximo}"
            ),
            inline=False,
        )
    embed.set_footer(text=(
        "Os mestres dão XP em roleplay importante, missão ou evento. "
        "Pontos de atributo de nível podem passar do limite da raça."
    ))
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="extrato_xp", description="Mostra de onde veio o XP do seu personagem (últimas entradas).")
@app_commands.describe(personagem="Opcional: qual personagem seu (padrão: o que você está usando)")
@app_commands.autocomplete(personagem=_autocomplete_personagem)
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


@bot.tree.command(name="calcular_recursos", description="Calcula Vida, Sanidade, Mana e Estamina pelos atributos e pela classe.")
@app_commands.describe(
    classe="Sua classe (dá o bônus de cada recurso)",
    vitalidade="Seu atributo Vitalidade",
    forca="Seu atributo Força",
    vontade="Seu atributo Vontade",
    alma="Seu atributo Alma",
)
@app_commands.choices(classe=[app_commands.Choice(name=n, value=n) for n in rules.CLASS_CHOICES])
async def calcular_recursos(
    interaction: discord.Interaction,
    classe: str,
    vitalidade: app_commands.Range[int, 0, 20],
    forca: app_commands.Range[int, 0, 20],
    vontade: app_commands.Range[int, 0, 20],
    alma: app_commands.Range[int, 0, 20],
):
    res = rules.calculate_resources(vitalidade=vitalidade, forca=forca, vontade=vontade, alma=alma, classe=classe)
    sem_classe = classe == rules.CLASS_NONE

    def linha(emoji: str, nome: str, chave: str, conta: str) -> str:
        r = res[chave]
        extra = "" if sem_classe else f", mais {r['bonus']} da classe"
        return f"{emoji} **{nome}: {r['total']}**\n　{conta} = {r['base']}{extra}"

    embed = discord.Embed(
        title=f"🧮 Recursos ({'sem classe' if sem_classe else classe})",
        description="\n".join([
            linha("❤️", "Vida", "vida", f"Vitalidade {vitalidade} × 5"),
            linha("🧠", "Sanidade", "sanidade", f"Vontade {vontade} × 5"),
            linha("🔮", "Mana", "mana", f"(Alma {alma} + Vontade {vontade}) × 3"),
            linha("💪", "Estamina", "estamina", f"(Força {forca} + Vitalidade {vitalidade}) × 3"),
        ]),
        color=discord.Color.dark_green(),
    )
    embed.set_footer(text=(
        "Cada ponto de Vitalidade dá +5 Vida e +3 Estamina. Vontade dá +5 Sanidade e +3 Mana. "
        "Alma dá +3 Mana. Força dá +3 Estamina. Destreza e Razão não entram nessas contas."
    ))
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Comandos de mestre
# ---------------------------------------------------------------------------

mestre_grupo = app_commands.Group(
    name="mestre",
    description="Comandos de mestre: XP, níveis, vagas e correções.",
    guild_only=True,
)

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

    antes = char[campo] or "nada"
    cfg["salvar"](char["id"], novo_valor, None)  # None = definido na mão, sem rolagem
    _auditar(interaction, usuario, char, f"corrigir_{campo}", f"{antes} -> {novo_valor}")

    embed = discord.Embed(
        title="🛠️ Definição corrigida",
        description=(
            f"{interaction.user.display_name} definiu {_ROTULO_COM_ARTIGO[campo]} de **{char['name']}** "
            f"({usuario.display_name}).\n**{antes}** → **{novo_valor}**"
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
    antes = _resumo_estado(char) or "nada"
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
        ganhos = rules.describe_gains(rules.gains_between(antes, depois, char["race"]))
        linhas.append(f"\nNível **{antes}** → **{depois}**\nGanhos: {ganhos}")
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
    description="Dá XP a um personagem (roleplay importante, missão ou evento). O nível sobe sozinho.",
)
@app_commands.describe(
    usuario="Jogador dono do personagem",
    quantidade="Quanto XP dar (negativo tira, pra corrigir um engano)",
    motivo="Opcional: o roleplay, a missão ou o evento",
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
    motivo="Opcional: RP marcante, missão secundária ou evento",
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
    rank="O Rank novo (0 = nenhum grau)",
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
    await interaction.response.send_message(embed=_embed_ficha(char, usuario.display_name), ephemeral=True)


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


bot.tree.add_command(mestre_grupo)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Defina DISCORD_TOKEN no arquivo .env antes de rodar o bot.")
    db.init_db()  # antes de conectar: se o caminho do banco estiver errado, o erro aparece na hora
    bot.run(TOKEN)
