"""Bot de Discord do Baptism of Blood.

Comandos:
  /rolar dado:1d20+3 [motivo] [personagem]   -> rola e salva no histórico
  /historico [usuario] [limite] [personagem] -> últimas rolagens de alguém (ou de um personagem)
  /personagem criar | usar | listar          -> gerencia os personagens de cada jogador
  /magia_inicial [personagem]                -> rola 1d100 uma vez e define o Rank de magia
  /raca_inicial [personagem]                 -> rola 1d100 uma vez e define a Raça
  /minha_ficha [personagem]                  -> mostra o que já foi definido
  /mestre apagar | corrigir_magia | corrigir_raca  -> só pra mestre

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
            "Próximos passos: `/magia_inicial` e `/raca_inicial`."
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
            f"{marca} **{c['name']}**\n"
            f"　magia: {c['magic_rank'] or 'sem rank'} · raça: {c['race'] or 'sem raça'}"
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


@bot.tree.command(name="minha_ficha", description="Mostra os resultados de definição já salvos do seu personagem.")
@app_commands.describe(personagem="Opcional: qual personagem seu (padrão: o que você está usando)")
@app_commands.autocomplete(personagem=_autocomplete_personagem)
async def minha_ficha(interaction: discord.Interaction, personagem: str | None = None):
    char, erro = _resolver(str(interaction.user.id), personagem)
    if erro:
        await interaction.response.send_message(erro, ephemeral=True)
        return

    embed = discord.Embed(title=f"📖 Ficha de {char['name']}", color=discord.Color.dark_purple())
    embed.add_field(name="Rank de Magia", value=_texto_definicao(char, "magic_rank", "/magia_inicial"), inline=True)
    embed.add_field(name="Raça", value=_texto_definicao(char, "race", "/raca_inicial"), inline=True)
    embed.set_footer(text=f"jogador: {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Comandos de mestre: corrigir ou apagar uma definição errada
# ---------------------------------------------------------------------------

mestre_grupo = app_commands.Group(
    name="mestre",
    description="Comandos de mestre: corrigir ou apagar definições de personagem.",
    guild_only=True,
)

_ROTULO_COM_ARTIGO = {"magic_rank": "o Rank de Magia", "race": "a Raça"}
_COMANDO_DE_ROLAR = {"magic_rank": "`/magia_inicial`", "race": "`/raca_inicial`"}


@mestre_grupo.command(
    name="apagar",
    description="Apaga o Rank de magia e/ou a Raça de um personagem, pra ele poder rolar de novo.",
)
@app_commands.describe(
    usuario="Jogador dono do personagem",
    definicao="O que apagar",
    personagem="Opcional: personagem dele (padrão: o que ele está usando)",
)
@app_commands.choices(definicao=[
    app_commands.Choice(name="Rank de magia", value="magic_rank"),
    app_commands.Choice(name="Raça", value="race"),
    app_commands.Choice(name="Rank de magia e Raça", value="ambos"),
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

    campos = ["magic_rank", "race"] if definicao == "ambos" else [definicao]
    apagados = [c for c in campos if char[c]]  # só o que estava mesmo definido
    antes = [f"{DEFINICOES[c]['rotulo']}: {char[c]}" for c in apagados]
    if not apagados:
        await interaction.response.send_message(
            f"**{char['name']}** não tem nada definido nisso pra apagar.", ephemeral=True
        )
        return

    db.clear_definition(char["id"], definicao)
    db.log_master_action(
        master_id=str(interaction.user.id),
        master_name=str(interaction.user.display_name),
        target_user_id=str(usuario.id),
        character_id=char["id"],
        character_name=char["name"],
        action="apagar",
        detail="; ".join(antes),
    )

    embed = discord.Embed(
        title="🧹 Definição apagada",
        description=(
            f"{interaction.user.display_name} apagou {' e '.join(_ROTULO_COM_ARTIGO[c] for c in apagados)} "
            f"de **{char['name']}**.\n"
            f"Antes era: {'; '.join(antes)}\n\n"
            f"{usuario.mention}, você pode rolar de novo com {' e '.join(_COMANDO_DE_ROLAR[c] for c in apagados)}."
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
    db.log_master_action(
        master_id=str(interaction.user.id),
        master_name=str(interaction.user.display_name),
        target_user_id=str(usuario.id),
        character_id=char["id"],
        character_name=char["name"],
        action=f"corrigir_{campo}",
        detail=f"{antes} -> {novo_valor}",
    )

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


bot.tree.add_command(mestre_grupo)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Defina DISCORD_TOKEN no arquivo .env antes de rodar o bot.")
    db.init_db()  # antes de conectar: se o caminho do banco estiver errado, o erro aparece na hora
    bot.run(TOKEN)
