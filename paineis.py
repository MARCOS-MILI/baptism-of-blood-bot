"""Painéis com botões: a ficha interativa, a escolha de classe, os formulários de atributos e a bandeja de dados.

Nada aqui repete regra. Cada botão chama o MESMO código dos comandos de barra (que já valida ordem da criação,
limites, quem pode o quê). Pra isso os comandos recebem um Coletor no lugar da interação: em vez de mandar a
resposta, ele a guarda, e o painel decide o que fazer (atualizar a própria mensagem e mandar o resto depois).

O bot.py entrega as funções que o painel usa por registrar(), porque este módulo não pode importar o bot.py
(quando o bot roda como 'python bot.py' o módulo se chama __main__, e um 'import bot' criaria uma cópia).
"""

import functools
import traceback
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Callable

import discord

import db
import dice
import rules
import vitrine

# O Discord só deixa editar a resposta original por 15 minutos.
TEMPO_DO_PAINEL = 14 * 60

MSG_ERRO = "⚠️ Deu erro aqui do meu lado. Tenta de novo, e se repetir avisa quem cuida do bot."
MSG_DE_OUTRA_PESSOA = "Esse painel é de outra pessoa. Abre o seu com `/minha_ficha`."


# ---------------------------------------------------------------------------
# O que o bot.py entrega pro painel
# ---------------------------------------------------------------------------
@dataclass
class Ganchos:
    embed_ficha: Callable       # (personagem, jogador) -> discord.Embed
    sortear: Callable           # async (coletor, passo, nome_do_personagem, repetir=False): 'raca', 'estado' ou 'magia'
    escolher_classe: Callable   # async (coletor, classe, nome_do_personagem)
    atributos: Callable         # async (coletor, {atributo: valor}, nome_do_personagem)
    rolar: Callable             # async (coletor, notacao, motivo)
    niveis: Callable            # async (coletor, nome_do_personagem)
    ajuda: Callable             # async (coletor)
    ordem_ligada: Callable      # () -> bool (a chavinha ORDEM_DA_CRIACAO, lida na hora)


GANCHOS: Ganchos | None = None


def registrar(ganchos: Ganchos) -> None:
    global GANCHOS
    GANCHOS = ganchos


# ---------------------------------------------------------------------------
# Coletor: faz de conta de interação pros comandos existentes
# ---------------------------------------------------------------------------
class _Resposta:
    def __init__(self, coletor: "Coletor"):
        self._coletor = coletor

    async def send_message(self, content=None, **kwargs):
        self._coletor.mensagens.append((content, kwargs))

    def is_done(self) -> bool:
        return False


class Coletor:
    """Tem o que os comandos usam de uma interação (user, guild, guild_id, namespace, response.send_message),
    mas guarda as respostas em 'mensagens' (lista de (conteúdo, argumentos)) em vez de enviar."""

    def __init__(self, interacao):
        self.user = interacao.user
        self.guild = interacao.guild
        self.guild_id = interacao.guild_id
        self.namespace = SimpleNamespace()
        self.mensagens: list[tuple] = []
        self.response = _Resposta(self)

    def avisar(self, texto: str) -> None:
        """Uma resposta só pra quem clicou."""
        self.mensagens.append((texto, {"ephemeral": True}))


async def entregar(interacao, coletor: Coletor, embed=None, view=None) -> None:
    """Atualiza a mensagem do painel (a resposta inicial do clique) e só depois manda o que os comandos
    quiseram responder: público (cartões de sorteio) ou privado (avisos)."""
    await interacao.response.edit_message(embed=embed, view=view)
    for conteudo, kwargs in coletor.mensagens:
        await interacao.followup.send(conteudo, **kwargs)


# ---------------------------------------------------------------------------
# Base: só o dono mexe, tempo esgotado desliga os botões, erro vira aviso
# ---------------------------------------------------------------------------
class _Painel(discord.ui.View):
    def __init__(self, dono_id: int):
        super().__init__(timeout=TEMPO_DO_PAINEL)
        self.dono_id = dono_id
        self.origem = None  # a interação que abriu a mensagem, pra desligar os botões quando o tempo acabar

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.dono_id:
            await interaction.response.send_message(MSG_DE_OUTRA_PESSOA, ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.origem is not None:
            try:
                await self.origem.edit_original_response(view=self)
            except discord.HTTPException:
                pass

    async def on_error(self, interaction: discord.Interaction, error: Exception, item) -> None:
        await _avisar_erro(interaction, error)

    def passar_pra(self, nova: "_Painel") -> None:
        """A mensagem passa a ter outra tela: a nova herda o 'origem' e a antiga sai de cena."""
        nova.origem = self.origem
        self.stop()


async def _avisar_erro(interaction: discord.Interaction, error: Exception) -> None:
    print(f"Erro num painel: {error!r}", flush=True)
    traceback.print_exception(type(error), error, error.__traceback__)
    if interaction.response.is_done():
        await interaction.followup.send(MSG_ERRO, ephemeral=True)
    else:
        await interaction.response.send_message(MSG_ERRO, ephemeral=True)


# ---------------------------------------------------------------------------
# A ficha interativa
# ---------------------------------------------------------------------------
# passo da criação -> (emoji, rótulo do botão)
_BOTOES_DE_PASSO = [
    ("raca", "🩸", "Raça"),
    ("estado", "⚜️", "Classe social"),
    ("classe", "🎓", "Classe"),
    ("magia", "✨", "Magia"),
]

GRUPOS_ATRIBUTOS = {
    "fisicos": ("🧬", "Físicos", "Atributos físicos", ("forca", "destreza", "vitalidade")),
    "mentais": ("🧠", "Mentais", "Atributos mentais", ("razao", "vontade", "alma")),
}


_CAMPO_DO_PASSO = {"raca": "race", "estado": "social_class"}


def estado_do_passo(status: dict, passo: str, ordem_ligada: bool, personagem=None) -> str:
    """'feito', 'repetir' (feito, mas ainda dá pra rolar de novo), 'nao_se_aplica', 'aguardando' (o mestre
    decide), 'travado' ou 'livre'."""
    if passo == "magia" and status["sem_magia"] and not status["magia_sorteada"]:
        return "nao_se_aplica"
    if status[passo]:
        campo = _CAMPO_DO_PASSO.get(passo)
        if campo and personagem is not None and rules.reroll_block(personagem, campo) is None:
            return "repetir"
        return "feito"
    if passo == "estado" and status["aguardando_mestre"]:
        return "aguardando"
    if ordem_ligada and rules.creation_missing_before(passo, status):
        return "travado"
    return "livre"


def pontos_livres(personagem) -> int:
    return rules.attribute_points_total(personagem["level"]) - sum(db.attributes_of(personagem).values())


class PainelFicha(_Painel):
    """A ficha de um personagem com os botões: passos da criação, atributos e atalhos. Cada clique refaz a tela."""

    def __init__(self, dono_id: int, personagem_id: int, jogador: str):
        super().__init__(dono_id)
        self.personagem_id = personagem_id
        self.jogador = jogador
        self._montar()

    def personagem(self):
        return db.get_character_by_id(self.personagem_id)

    def _montar(self) -> None:
        char = self.personagem()
        status = rules.creation_status(char)
        ordem = GANCHOS.ordem_ligada()

        for passo, emoji, rotulo in _BOTOES_DE_PASSO:
            situacao = estado_do_passo(status, passo, ordem, char)
            if situacao == "repetir":
                restam = rules.attempts_left(char, _CAMPO_DO_PASSO[passo])
                botao = discord.ui.Button(label=f"{rotulo} ({restam})", emoji="🔄", style=discord.ButtonStyle.secondary, row=0)
                botao.callback = functools.partial(self._clicou_passo, passo)
            elif situacao == "feito":
                botao = discord.ui.Button(label=rotulo, emoji="✅", style=discord.ButtonStyle.success, disabled=True, row=0)
            elif situacao == "nao_se_aplica":
                botao = discord.ui.Button(label="Sem magia", emoji="➖", style=discord.ButtonStyle.secondary, disabled=True, row=0)
            elif situacao == "aguardando":
                botao = discord.ui.Button(label=rotulo, emoji="⏳", style=discord.ButtonStyle.secondary, disabled=True, row=0)
            elif situacao == "travado":
                botao = discord.ui.Button(label=rotulo, emoji="🔒", style=discord.ButtonStyle.secondary, disabled=True, row=0)
            else:
                botao = discord.ui.Button(label=rotulo, emoji=emoji, style=discord.ButtonStyle.primary, row=0)
                botao.callback = functools.partial(self._clicou_passo, passo)
            self.add_item(botao)

        # atributos: liberados depois da classe (e da magia, pra quem tem); só enquanto sobrar ponto
        liberado = not (ordem and rules.creation_missing_before("atributos", status)) and bool(char["race"])
        sobra = pontos_livres(char) > 0
        for grupo, (emoji, rotulo, _, _) in GRUPOS_ATRIBUTOS.items():
            botao = discord.ui.Button(label=rotulo, emoji=emoji, style=discord.ButtonStyle.primary, row=1, disabled=not (liberado and sobra))
            botao.callback = functools.partial(self._abrir_atributos, grupo)
            self.add_item(botao)

        for emoji, rotulo, acao in (("🎲", "Dados", self._abrir_dados), ("📈", "Níveis", self._ver_niveis), ("❓", "Ajuda", self._ver_ajuda)):
            botao = discord.ui.Button(label=rotulo, emoji=emoji, style=discord.ButtonStyle.secondary, row=1)
            botao.callback = acao
            self.add_item(botao)

        personagens = db.list_characters(str(self.dono_id))
        if len(personagens) > 1:
            opcoes = [
                discord.SelectOption(
                    label=p["name"][:100], value=str(p["id"]), default=p["id"] == self.personagem_id,
                    description=f"nível {p['level']} · {p['race'] or 'sem raça'}",
                )
                for p in personagens[:25]
            ]
            seletor = discord.ui.Select(placeholder="Trocar de personagem", options=opcoes, row=2)
            seletor.callback = functools.partial(self._trocar_personagem, seletor)
            self.add_item(seletor)

    # ---- refazer a tela ----
    async def _atualizar(self, interaction: discord.Interaction, coletor: Coletor | None = None) -> None:
        nova = PainelFicha(self.dono_id, self.personagem_id, self.jogador)
        self.passar_pra(nova)
        embed = GANCHOS.embed_ficha(nova.personagem(), self.jogador)
        await entregar(interaction, coletor or Coletor(interaction), embed, nova)

    # ---- os passos da criação ----
    async def _clicou_passo(self, passo: str, interaction: discord.Interaction) -> None:
        if passo == "classe":
            escolha = EscolhaDeClasse(self.dono_id, self.personagem_id, self.jogador)
            self.passar_pra(escolha)
            await interaction.response.edit_message(embed=escolha.embed(), view=escolha)
            return
        char = self.personagem()
        campo = _CAMPO_DO_PASSO.get(passo)
        if campo and char[campo]:  # já tem resultado: rolar de novo troca ele, então pergunta antes
            if rules.reroll_block(char, campo) is None:
                confirmar = ConfirmarRepeticao(self.dono_id, self.personagem_id, self.jogador, passo)
                self.passar_pra(confirmar)
                await interaction.response.edit_message(embed=confirmar.embed(), view=confirmar)
                return
        coletor = Coletor(interaction)
        await GANCHOS.sortear(coletor, passo, char["name"])
        await self._atualizar(interaction, coletor)

    # ---- atributos ----
    async def _abrir_atributos(self, grupo: str, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ModalAtributos(self, grupo))

    async def aplicar_atributos(self, interaction: discord.Interaction, pedidos: dict[str, int]) -> None:
        """Chamado pelo formulário: passa pelo mesmo código do /atributos (só aumenta, confere pontos e limites)."""
        char = self.personagem()
        atuais = db.attributes_of(char)
        mudou = {a: v for a, v in pedidos.items() if v != atuais[a]}
        coletor = Coletor(interaction)
        if not mudou:
            coletor.avisar(f"Nada mudou: **{char['name']}** já tem esses valores.")
        else:
            await GANCHOS.atributos(coletor, mudou, char["name"])
        await self._atualizar(interaction, coletor)

    # ---- atalhos ----
    async def _abrir_dados(self, interaction: discord.Interaction) -> None:
        bandeja = BandejaDados(self.dono_id, self.jogador)
        await interaction.response.send_message(embed=bandeja.embed(), view=bandeja, ephemeral=True)
        bandeja.origem = interaction

    async def _ver_niveis(self, interaction: discord.Interaction) -> None:
        coletor = Coletor(interaction)
        await GANCHOS.niveis(coletor, self.personagem()["name"])
        await self._atualizar(interaction, coletor)

    async def _ver_ajuda(self, interaction: discord.Interaction) -> None:
        coletor = Coletor(interaction)
        await GANCHOS.ajuda(coletor)
        await self._atualizar(interaction, coletor)

    async def _trocar_personagem(self, seletor: discord.ui.Select, interaction: discord.Interaction) -> None:
        escolhido = db.get_character_by_id(int(seletor.values[0]))
        if escolhido is None or escolhido["user_id"] != str(self.dono_id):  # nunca troca pra personagem de outra pessoa
            coletor = Coletor(interaction)
            coletor.avisar("Não achei esse personagem. Abre o painel de novo com `/minha_ficha`.")
            await self._atualizar(interaction, coletor)
            return
        db.set_active_character(str(self.dono_id), escolhido["id"])
        self.personagem_id = escolhido["id"]
        await self._atualizar(interaction)


class ModalAtributos(discord.ui.Modal):
    """Três atributos por formulário (o Discord só aceita 5 campos, e são 6 atributos)."""

    def __init__(self, painel: PainelFicha, grupo: str):
        _, _, titulo, chaves = GRUPOS_ATRIBUTOS[grupo]
        char = painel.personagem()
        super().__init__(title=f"{titulo} de {char['name']}"[:45], timeout=TEMPO_DO_PAINEL)
        self.painel = painel
        self.campos: dict[str, discord.ui.TextInput] = {}
        atuais = db.attributes_of(char)
        for chave in chaves:
            campo = discord.ui.TextInput(
                label=f"{rules.ATTRIBUTE_LABELS[chave]} (só dá pra aumentar)", default=str(atuais[chave]),
                min_length=1, max_length=2, required=True,
            )
            self.campos[chave] = campo
            self.add_item(campo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        pedidos, erros = {}, []
        for chave, campo in self.campos.items():
            texto = campo.value.strip()
            if not texto.isdigit() or not 0 <= int(texto) <= 20:
                erros.append(f"{rules.ATTRIBUTE_LABELS[chave]}: use um número de 0 a 20")
            else:
                pedidos[chave] = int(texto)
        if erros:
            await interaction.response.send_message("⚠️ " + "; ".join(erros) + ".", ephemeral=True)
            return
        await self.painel.aplicar_atributos(interaction, pedidos)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await _avisar_erro(interaction, error)


# ---------------------------------------------------------------------------
# Rolar de novo a raça ou a classe social (até 3 chances; a última vale)
# ---------------------------------------------------------------------------
class ConfirmarRepeticao(_Painel):
    _ROTULO = {"raca": ("raça", "race"), "estado": ("classe social", "social_class")}

    def __init__(self, dono_id: int, personagem_id: int, jogador: str, passo: str):
        super().__init__(dono_id)
        self.personagem_id = personagem_id
        self.jogador = jogador
        self.passo = passo
        rolar = discord.ui.Button(label="Rolar de novo", emoji="🎲", style=discord.ButtonStyle.danger, row=0)
        rolar.callback = self._rolar
        manter = discord.ui.Button(label="Manter", emoji="✅", style=discord.ButtonStyle.success, row=0)
        manter.callback = self._manter
        self.add_item(rolar)
        self.add_item(manter)

    def personagem(self):
        return db.get_character_by_id(self.personagem_id)

    def embed(self) -> discord.Embed:
        char = self.personagem()
        rotulo, campo = self._ROTULO[self.passo]
        usadas = rules.attempts_used(char, campo)
        return discord.Embed(
            title=f"🔄 Rolar a {rotulo} de novo?",
            description=(
                f"**{char['name']}** está com **{vitrine.resultado_atual(char, campo)}**.\n"
                f"Rolar de novo **troca esse resultado** pelo novo, e não dá pra voltar atrás.\n\n"
                f"Você já usou {usadas} de {rules.CREATION_ROLL_ATTEMPTS} chances. "
                f"Rolando de novo, sobram {max(0, rules.CREATION_ROLL_ATTEMPTS - usadas - 1)}."
            ),
            color=discord.Color.orange(),
        )

    async def _voltar_pro_painel(self, interaction: discord.Interaction, coletor: Coletor | None = None) -> None:
        painel = PainelFicha(self.dono_id, self.personagem_id, self.jogador)
        self.passar_pra(painel)
        await entregar(interaction, coletor or Coletor(interaction), GANCHOS.embed_ficha(painel.personagem(), self.jogador), painel)

    async def _rolar(self, interaction: discord.Interaction) -> None:
        coletor = Coletor(interaction)
        await GANCHOS.sortear(coletor, self.passo, self.personagem()["name"], repetir=True)
        await self._voltar_pro_painel(interaction, coletor)

    async def _manter(self, interaction: discord.Interaction) -> None:
        await self._voltar_pro_painel(interaction)


# ---------------------------------------------------------------------------
# Escolha de classe (vale uma vez, então tem menu e confirmação)
# ---------------------------------------------------------------------------
class EscolhaDeClasse(_Painel):
    def __init__(self, dono_id: int, personagem_id: int, jogador: str):
        super().__init__(dono_id)
        self.personagem_id = personagem_id
        self.jogador = jogador
        self.escolhida: str | None = None
        self._montar()

    def personagem(self):
        return db.get_character_by_id(self.personagem_id)

    def _montar(self) -> None:
        self.clear_items()
        opcoes = [
            discord.SelectOption(label=c, value=c, description=f"Vantagem: {rules.CLASS_SKILLS[c]}"[:100], default=c == self.escolhida)
            for c in rules.CLASSES
        ]
        seletor = discord.ui.Select(placeholder="Escolha a classe", options=opcoes, row=0)
        seletor.callback = functools.partial(self._escolheu, seletor)
        self.add_item(seletor)
        confirmar = discord.ui.Button(label="Confirmar classe", emoji="✅", style=discord.ButtonStyle.success, disabled=self.escolhida is None, row=1)
        confirmar.callback = self._confirmar
        voltar = discord.ui.Button(label="Voltar", emoji="⬅️", style=discord.ButtonStyle.secondary, row=1)
        voltar.callback = self._voltar
        self.add_item(confirmar)
        self.add_item(voltar)

    def embed(self) -> discord.Embed:
        nome = self.personagem()["name"]
        if self.escolhida is None:
            embed = discord.Embed(
                title=f"🎓 Escolha a classe de {nome}",
                description="Vale **uma vez só**: depois de confirmar, só um mestre muda. Escolhe no menu pra ver a classe antes.",
                color=discord.Color.dark_green(),
            )
            for classe, b in rules.CLASSES.items():
                embed.add_field(
                    name=classe,
                    value=f"{rules.CLASS_SKILLS[classe]}\nVida +{b['vida']} · Sanidade +{b['sanidade']} · Mana +{b['mana']} · Estamina +{b['estamina']}",
                    inline=False,
                )
            return embed
        return vitrine.previa_classe(nome, self.escolhida)

    async def _escolheu(self, seletor: discord.ui.Select, interaction: discord.Interaction) -> None:
        escolha = seletor.values[0]
        if escolha not in rules.CLASSES:
            await interaction.response.send_message("Não conheço essa classe. Escolhe uma do menu.", ephemeral=True)
            return
        self.escolhida = escolha
        self._montar()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def _voltar(self, interaction: discord.Interaction) -> None:
        painel = PainelFicha(self.dono_id, self.personagem_id, self.jogador)
        self.passar_pra(painel)
        await interaction.response.edit_message(embed=GANCHOS.embed_ficha(painel.personagem(), self.jogador), view=painel)

    async def _confirmar(self, interaction: discord.Interaction) -> None:
        coletor = Coletor(interaction)
        await GANCHOS.escolher_classe(coletor, self.escolhida, self.personagem()["name"])
        painel = PainelFicha(self.dono_id, self.personagem_id, self.jogador)
        self.passar_pra(painel)
        await entregar(interaction, coletor, GANCHOS.embed_ficha(painel.personagem(), self.jogador), painel)


# ---------------------------------------------------------------------------
# Bandeja de dados
# ---------------------------------------------------------------------------
LADOS_DA_BANDEJA = (4, 6, 8, 10, 12, 20, 100)
QTD_MAX_BANDEJA = 10
MOD_MAX_BANDEJA = 30


class BandejaDados(_Painel):
    """Escolhe o dado, a quantidade, o modificador e o motivo por botão; o resultado sai público no canal."""

    def __init__(self, dono_id: int, jogador: str, lados: int = 20, qtd: int = 1, mod: int = 0, motivo: str | None = None):
        super().__init__(dono_id)
        self.jogador = jogador
        self.lados, self.qtd, self.mod, self.motivo = lados, qtd, mod, motivo
        self._montar()

    def notacao(self) -> str:
        return f"{self.qtd}d{self.lados}" + (f"{self.mod:+d}" if self.mod else "")

    def embed(self) -> discord.Embed:
        char = db.get_active_character(str(self.dono_id))
        embed = discord.Embed(
            title="🎲 Bandeja de dados",
            description=f"## {self.notacao()}\nEscolhe o dado e aperta **Rolar**. O resultado sai pra todo mundo ver.",
            color=discord.Color.dark_red(),
        )
        embed.add_field(name="Motivo", value=self.motivo or "nenhum (aperta 📝 pra escrever um)", inline=True)
        embed.add_field(name="Rolando como", value=char["name"] if char else self.jogador, inline=True)
        return embed

    def _botao(self, rotulo, acao, *, row, estilo=discord.ButtonStyle.secondary, emoji=None, disabled=False):
        botao = discord.ui.Button(label=rotulo, style=estilo, emoji=emoji, row=row, disabled=disabled)
        botao.callback = acao
        self.add_item(botao)

    def _montar(self) -> None:
        self.clear_items()
        for i, lados in enumerate(LADOS_DA_BANDEJA):
            estilo = discord.ButtonStyle.primary if lados == self.lados else discord.ButtonStyle.secondary
            self._botao(f"d{lados}", functools.partial(self._escolher_dado, lados), row=0 if i < 5 else 1, estilo=estilo)
        self._botao("Dado", functools.partial(self._mudar_qtd, -1), row=1, emoji="➖", disabled=self.qtd <= 1)
        self._botao("Dado", functools.partial(self._mudar_qtd, +1), row=1, emoji="➕", disabled=self.qtd >= QTD_MAX_BANDEJA)
        self._botao("Rolar", self._rolar, row=1, estilo=discord.ButtonStyle.success, emoji="🎲")
        for valor in (-5, -1, +1, +5):
            self._botao(f"{valor:+d}", functools.partial(self._mudar_mod, valor), row=2)
        self._botao("Zerar", functools.partial(self._mudar_mod, None), row=2, disabled=self.mod == 0)
        self._botao("Motivo", self._abrir_motivo, row=3, emoji="📝")

    async def _redesenhar(self, interaction: discord.Interaction) -> None:
        self._montar()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def _escolher_dado(self, lados: int, interaction: discord.Interaction) -> None:
        self.lados = lados
        await self._redesenhar(interaction)

    async def _mudar_qtd(self, passo: int, interaction: discord.Interaction) -> None:
        self.qtd = max(1, min(QTD_MAX_BANDEJA, self.qtd + passo))
        await self._redesenhar(interaction)

    async def _mudar_mod(self, passo: int | None, interaction: discord.Interaction) -> None:
        self.mod = 0 if passo is None else max(-MOD_MAX_BANDEJA, min(MOD_MAX_BANDEJA, self.mod + passo))
        await self._redesenhar(interaction)

    async def _abrir_motivo(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ModalMotivo(self))

    async def _rolar(self, interaction: discord.Interaction) -> None:
        coletor = Coletor(interaction)
        await GANCHOS.rolar(coletor, self.notacao(), self.motivo)
        await entregar(interaction, coletor, self.embed(), self)


class ModalMotivo(discord.ui.Modal):
    def __init__(self, bandeja: BandejaDados):
        super().__init__(title="Motivo da rolagem", timeout=TEMPO_DO_PAINEL)
        self.bandeja = bandeja
        self.campo = discord.ui.TextInput(
            label="Pra que é essa rolagem?", default=bandeja.motivo, required=False, max_length=80,
            placeholder="ex: ataque com a espada",
        )
        self.add_item(self.campo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.bandeja.motivo = self.campo.value.strip() or None
        await self.bandeja._redesenhar(interaction)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await _avisar_erro(interaction, error)
