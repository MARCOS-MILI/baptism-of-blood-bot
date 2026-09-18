"""Bot de Discord do Baptism of Blood.

Comandos:
  /rolar dado:1d20+3           -> rola e salva no histórico
  /historico [usuario] [limite] -> mostra as últimas rolagens de alguém
  /magia_inicial                -> rola 1d100 uma vez e define o Rank de magia do personagem
  /minha_ficha                   -> mostra os resultados de definição já salvos

Setup rápido:
  1. pip install -r requirements.txt
  2. Cria um arquivo .env com DISCORD_TOKEN=seu_token_aqui (veja o README)
  3. python bot.py
"""

import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

import db
import dice

load_dotenv()
TOKEN = os.environ.get("DISCORD_TOKEN")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    db.init_db()
    await bot.tree.sync()
    print(f"Conectado como {bot.user} — histórico salvo em {db.DB_PATH}")


@bot.tree.command(name="rolar", description="Rola um dado (ex: 1d20, 2d6+3) e guarda no histórico.")
@app_commands.describe(dado="Notação do dado, tipo 1d20 ou 2d6+3", motivo="Opcional: pra que é essa rolagem")
async def rolar(interaction: discord.Interaction, dado: str, motivo: str | None = None):
    try:
        resultado = dice.roll(dado)
    except dice.DiceError as e:
        await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
        return

    db.log_roll(
        user_id=str(interaction.user.id),
        username=str(interaction.user.display_name),
        guild_id=str(interaction.guild_id) if interaction.guild_id else None,
        notation=dado,
        rolls=resultado.rolls,
        total=resultado.total,
        purpose=motivo,
    )

    embed = discord.Embed(
        title=f"🎲 {interaction.user.display_name} rolou {dado}",
        description=f"**{resultado.describe()} = {resultado.total}**",
        color=discord.Color.dark_red(),
    )
    if motivo:
        embed.set_footer(text=motivo)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="historico", description="Mostra as últimas rolagens de um usuário.")
@app_commands.describe(usuario="De quem ver o histórico (padrão: você mesmo)", limite="Quantas rolagens mostrar (padrão 10)")
async def historico(interaction: discord.Interaction, usuario: discord.Member | None = None, limite: int = 10):
    alvo = usuario or interaction.user
    limite = max(1, min(limite, 25))
    linhas = db.get_history(str(alvo.id), limit=limite)

    if not linhas:
        await interaction.response.send_message(f"Nenhuma rolagem registrada pra {alvo.display_name} ainda.", ephemeral=True)
        return

    embed = discord.Embed(title=f"📜 Histórico de {alvo.display_name}", color=discord.Color.dark_gold())
    for linha in linhas:
        quando = linha["created_at"][:16].replace("T", " ")
        motivo = f" ({linha['purpose']})" if linha["purpose"] else ""
        embed.add_field(
            name=f"{linha['notation']} = {linha['total']}{motivo}",
            value=quando,
            inline=False,
        )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="magia_inicial", description="Rola 1d100 e define o Rank de magia inicial do seu personagem.")
async def magia_inicial(interaction: discord.Interaction):
    existente = db.get_character(str(interaction.user.id))
    if existente and existente["magic_rank"]:
        await interaction.response.send_message(
            f"Você já rolou antes: Rank **{existente['magic_rank']}** (resultado {existente['magic_rank_roll']} no 1d100). "
            "Fala com um mestre se precisar rolar de novo.",
            ephemeral=True,
        )
        return

    resultado = dice.roll("1d100")
    valor = resultado.total
    rank = dice.magic_rank_for(valor)

    db.log_roll(
        user_id=str(interaction.user.id),
        username=str(interaction.user.display_name),
        guild_id=str(interaction.guild_id) if interaction.guild_id else None,
        notation="1d100",
        rolls=resultado.rolls,
        total=valor,
        purpose="magia_inicial",
    )
    db.set_magic_rank(str(interaction.user.id), str(interaction.user.display_name), rank, valor)

    embed = discord.Embed(
        title=f"✨ Magia Inicial de {interaction.user.display_name}",
        description=f"1d100 = **{valor}**\nRank: **{rank}**",
        color=discord.Color.purple(),
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="minha_ficha", description="Mostra os resultados de definição já salvos do seu personagem.")
async def minha_ficha(interaction: discord.Interaction):
    dados = db.get_character(str(interaction.user.id))
    if not dados:
        await interaction.response.send_message("Ainda não há nenhum resultado de definição salvo pra você.", ephemeral=True)
        return

    embed = discord.Embed(title=f"📖 Ficha de {interaction.user.display_name}", color=discord.Color.dark_purple())
    embed.add_field(name="Rank de Magia", value=dados["magic_rank"] or "—", inline=True)
    embed.add_field(name="Raça", value=dados["race"] or "— (ainda sem regra de sorteio)", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Defina DISCORD_TOKEN no arquivo .env antes de rodar o bot.")
    bot.run(TOKEN)
