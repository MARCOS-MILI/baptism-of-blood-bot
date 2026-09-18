"""Bot de Discord do Baptism of Blood.

Jogadores:
  /rolar dado:1d20+3 [motivo] [personagem]   -> rola e salva no histórico
  /historico [usuario] [limite] [personagem] -> últimas rolagens de alguém (ou de um personagem)
  /personagem criar | usar | listar          -> gerencia os personagens de cada jogador
  /magia_inicial [personagem]                -> rola 1d100 uma vez e define o Rank de magia
  /raca_inicial [personagem]                 -> rola 1d100 uma vez e define a Raça
  /classe_social [personagem]                -> rola 1d100 (e outro, se cair no clero) e define o Estado
  /minha_ficha [personagem]                  -> nível, raça, classe social, ranks
  /niveis [personagem]                       -> vantagens de cada nível
  /calcular_recursos                         -> calcula Vida, Sanidade, Mana e Estamina

Mestres:
  /mestre apagar | corrigir_magia | corrigir_raca | corrigir_estado
  /mestre upar | corrigir_nivel | rank_pericia | ficha

Setup rápido:
  1. pip install -r requirements.txt
  2. Cria um arquivo .env com DISCORD_TOKEN=seu_token_aqui (veja o README)
  3. python bot.py
"""

import os
import traceback

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

NOME_MIN, NOME_MAX = 2, 60

intents = discord.Intents.default()
# Ninguém consegue fazer o bot marcar @everyone ou cargos através de um nome de personagem.
bot = commands.Bot(command_prefix="!", intents=intents, allowed_mentions=discord.AllowedMentions.none())

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


def _embed_ficha(personagem, jogador: str) -> discord.Embed:
    nivel = personagem["level"]
    embed = discord.Embed(title=f"📖 Ficha de {personagem['name']}", color=discord.Color.dark_purple())
    embed.add_field(name="Nível", value=f"{nivel}/{rules.MAX_LEVEL}\n{rules.bar(nivel, rules.MAX_LEVEL)}", inline=True)
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
        quando = linha["created_at"][:16].replace("T", " ")
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

personagem_grupo = app_commands.Group(name="personagem", description="Cria e troca de personagem.")


@personagem_grupo.command(name="criar", description="Cria um personagem novo e já passa a usar ele.")
@app_commands.describe(nome="Nome do personagem")
async def personagem_criar(interaction: discord.Interaction, nome: str):
    limpo = db.normalize_name(nome)
    if not (NOME_MIN <= len(limpo) <= NOME_MAX):
        await interaction.response.send_message(
            f"⚠️ O nome precisa ter entre {NOME_MIN} e {NOME_MAX} letras.", ephemeral=True
        )
        return
    try:
        novo = db.create_character(str(interaction.user.id), limpo)
    except db.CharacterExists:
        existente = db.find_character(str(interaction.user.id), limpo)
        await interaction.response.send_message(
            f"Você já tem um personagem chamado **{existente['name'] if existente else limpo}**. "
            "Use `/personagem usar` pra voltar pra ele.",
            ephemeral=True,
        )
        return
    embed = discord.Embed(
        title="🎭 Personagem criado",
        description=(
            f"**{novo['name']}** agora é o personagem que você está usando.\n"
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
            f"{marca} **{c['name']}** · nível {c['level']}\n"
            f"　magia: {c['magic_rank'] or 'sem rank'} · raça: {c['race'] or 'sem raça'}"
            f" · estado: {_resumo_estado(c) or 'sem estado'}"
        )
    embed = discord.Embed(
        title="🎭 Seus personagens",
        description="\n".join(linhas),
        color=discord.Color.dark_purple(),
    )
    embed.set_footer(text="▶️ = o que você está usando agora")
    await interaction.response.send_message(embed=embed, ephemeral=True)


bot.tree.add_command(personagem_grupo)


# ---------------------------------------------------------------------------
# Definições: Rank de magia e Raça (uma rolagem só por personagem)
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
# Ficha, níveis e calculadora de recursos
# ---------------------------------------------------------------------------

@bot.tree.command(name="minha_ficha", description="Mostra nível, raça, classe social e ranks do seu personagem.")
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


@bot.tree.command(name="niveis", description="Mostra as vantagens de cada nível, de 1 a 10.")
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
    embed = discord.Embed(
        title="📈 Vantagens de cada nível",
        description=(
            "\n".join(rules.level_table_lines(atual))
            + f"\n\n**Somando tudo, do 1 ao {rules.MAX_LEVEL}:** {rules.describe_gains(rules.total_gains(rules.MAX_LEVEL))}"
        ),
        color=discord.Color.dark_teal(),
    )
    if char:
        if atual >= rules.MAX_LEVEL:
            proximo = "nível máximo, não tem próximo"
        else:
            proximo = f"nível {atual + 1}: {rules.describe_gains(rules.gains_for_level(atual + 1))}"
        embed.add_field(
            name=f"{char['name']}: nível {atual}/{rules.MAX_LEVEL}",
            value=(
                f"{rules.bar(atual, rules.MAX_LEVEL)}\n"
                f"Já ganhou: {rules.describe_gains(rules.total_gains(atual))}\n"
                f"Próximo, {proximo}"
            ),
            inline=False,
        )
    embed.set_footer(text=(
        "Quem sobe de nível é decidido pelos mestres: RP marcante, missão secundária ou evento. "
        "Pontos de atributo de nível podem passar do limite da raça."
    ))
    await interaction.response.send_message(embed=embed, ephemeral=True)


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
    description="Comandos de mestre: corrigir definições, subir nível e dar ranks.",
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


def _juntar(itens: list[str]) -> str:
    """['a', 'b', 'c'] vira 'a, b e c'."""
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


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


@mestre_grupo.command(name="upar", description="Sobe o nível de um personagem (máximo 10) e mostra o que ele ganha.")
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

    antes = char["level"]
    if antes >= rules.MAX_LEVEL:
        await interaction.response.send_message(
            f"**{char['name']}** já está no nível máximo ({rules.MAX_LEVEL}).", ephemeral=True
        )
        return

    depois = min(antes + niveis, rules.MAX_LEVEL)
    ganhos = rules.gains_between(antes, depois)
    db.set_level(char["id"], depois)
    detalhe = f"{antes} -> {depois}" + (f" ({motivo[:100]})" if motivo else "")
    _auditar(interaction, usuario, char, "upar", detalhe)

    linhas = [
        f"Nível **{antes}** → **{depois}** (máximo {rules.MAX_LEVEL})",
        f"Ganhos: {rules.describe_gains(ganhos)}",
    ]
    if motivo:
        linhas.append(f"Motivo: {motivo[:100]}")
    linhas.append(
        f"\n{usuario.mention}, veja tudo em `/niveis` e, depois de distribuir os pontos, "
        "use `/calcular_recursos` pra ajustar a sua Vida."
    )
    embed = discord.Embed(
        title=f"⬆️ {char['name']} subiu de nível!",
        description="\n".join(linhas),
        color=discord.Color.green(),
    )
    embed.set_footer(text=f"por {interaction.user.display_name}")
    await interaction.response.send_message(
        content=usuario.mention, embed=embed, allowed_mentions=discord.AllowedMentions(users=[usuario])
    )


@mestre_grupo.command(name="corrigir_nivel", description="Define o nível de um personagem na mão (de 1 a 10).")
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

    antes = char["level"]
    db.set_level(char["id"], nivel)
    _auditar(interaction, usuario, char, "corrigir_nivel", f"{antes} -> {nivel}")

    embed = discord.Embed(
        title="🛠️ Nível corrigido",
        description=(
            f"{interaction.user.display_name} definiu o nível de **{char['name']}** ({usuario.display_name}).\n"
            f"**{antes}** → **{nivel}**"
        ),
        color=discord.Color.orange(),
    )
    await interaction.response.send_message(embed=embed)


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


bot.tree.add_command(mestre_grupo)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Defina DISCORD_TOKEN no arquivo .env antes de rodar o bot.")
    db.init_db()  # antes de conectar: se o caminho do banco estiver errado, o erro aparece na hora
    bot.run(TOKEN)
