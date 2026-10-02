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
import habil
import lore
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
    escolher_classe: Callable   # async (coletor, classe, nome_do_personagem, habilidade=None)
    atributos: Callable         # async (coletor, {atributo: valor}, nome_do_personagem)
    rolar: Callable             # async (coletor, notacao, motivo)
    niveis: Callable            # async (coletor, nome_do_personagem)
    ajuda: Callable             # async (coletor)
    ordem_ligada: Callable      # () -> bool (a chavinha ORDEM_DA_CRIACAO, lida na hora)
    recursos: Callable          # (personagem) -> {vida, sanidade, mana, estamina: {total...}} (o máximo de cada vital)
    teste: Callable             # async (coletor, notacao, motivo, nome_do_personagem, modo): rola um teste de perícia


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


ABAS = (("ficha", "📋", "Ficha"), ("vitais", "❤️", "Vitais"), ("pericias", "🎯", "Perícias"), ("habilidades", "✨", "Habilidades"))


def adicionar_abas(view: "_Painel", atual: str) -> None:
    """A linha de cima de todas as telas principais: pra onde ir. A aba onde a pessoa está fica azul e parada."""
    for chave, emoji, rotulo in ABAS:
        aqui = chave == atual
        botao = discord.ui.Button(
            label=rotulo, emoji=emoji, row=0, disabled=aqui,
            style=discord.ButtonStyle.primary if aqui else discord.ButtonStyle.secondary,
        )
        botao.callback = functools.partial(_ir_pra_aba, view, chave)
        view.add_item(botao)


async def _ir_pra_aba(view: "_Painel", chave: str, interaction: discord.Interaction) -> None:
    if chave == "vitais":
        nova = PainelVitais(view.dono_id, view.personagem_id, view.jogador)
        embed = nova.embed()
    elif chave == "pericias":
        nova = PainelPericias(view.dono_id, view.personagem_id, view.jogador)
        embed = nova.embed()
    elif chave == "habilidades":
        nova = PainelHabilidades(view.dono_id, view.personagem_id, view.jogador)
        embed = nova.embed()
    else:
        nova = PainelFicha(view.dono_id, view.personagem_id, view.jogador)
        embed = GANCHOS.embed_ficha(nova.personagem(), view.jogador)
    view.passar_pra(nova)
    await interaction.response.edit_message(embed=embed, view=nova)


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
    decide o 100 da classe social), 'especial' (caiu 66 ou 77 e o mestre decide), 'travado' ou 'livre'."""
    if passo == "magia" and status["sem_magia"] and not status["magia_sorteada"]:
        return "nao_se_aplica"
    if status[passo]:
        campo = _CAMPO_DO_PASSO.get(passo)
        if campo and personagem is not None and rules.reroll_block(personagem, campo) is None:
            return "repetir"
        return "feito"
    if status["especial"].get(passo):
        return "especial"
    if passo == "estado" and status["aguardando_mestre"]:
        return "aguardando"
    if ordem_ligada and rules.creation_missing_before(passo, status):
        return "travado"
    return "livre"


def habilidade_pendente(personagem) -> bool:
    """A classe oferece duas habilidades e o jogador ainda não escolheu nenhuma."""
    return rules.class_needs_ability_choice(personagem["class_name"]) and rules.class_ability_of(personagem) is None


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
        adicionar_abas(self, "ficha")

        for passo, emoji, rotulo in _BOTOES_DE_PASSO:
            situacao = estado_do_passo(status, passo, ordem, char)
            if situacao == "repetir":
                restam = rules.attempts_left(char, _CAMPO_DO_PASSO[passo])
                botao = discord.ui.Button(label=f"{rotulo} ({restam})", emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
                botao.callback = functools.partial(self._clicou_passo, passo)
            elif situacao == "feito" and passo == "classe" and habilidade_pendente(char):
                botao = discord.ui.Button(label="Habilidade de classe", emoji="✨", style=discord.ButtonStyle.primary, row=1)
                botao.callback = self._abrir_habilidade
            elif situacao == "feito":
                botao = discord.ui.Button(label=rotulo, emoji="✅", style=discord.ButtonStyle.success, disabled=True, row=1)
            elif situacao == "nao_se_aplica":
                botao = discord.ui.Button(label="Sem magia", emoji="➖", style=discord.ButtonStyle.secondary, disabled=True, row=1)
            elif situacao == "especial":
                botao = discord.ui.Button(label=rotulo, emoji="❓", style=discord.ButtonStyle.secondary, disabled=True, row=1)
            elif situacao == "aguardando":
                botao = discord.ui.Button(label=rotulo, emoji="⏳", style=discord.ButtonStyle.secondary, disabled=True, row=1)
            elif situacao == "travado":
                botao = discord.ui.Button(label=rotulo, emoji="🔒", style=discord.ButtonStyle.secondary, disabled=True, row=1)
            else:
                botao = discord.ui.Button(label=rotulo, emoji=emoji, style=discord.ButtonStyle.primary, row=1)
                botao.callback = functools.partial(self._clicou_passo, passo)
            self.add_item(botao)

        if rules.has_disciplines(char["race"]):
            livres = rules.discipline_points_free(char["level"], char["race"], db.get_disciplines(char["id"]))
            botao = discord.ui.Button(
                label="Disciplinas", emoji="🩸", row=1,
                style=discord.ButtonStyle.primary if livres > 0 else discord.ButtonStyle.secondary,
            )
            botao.callback = self._abrir_disciplinas
            self.add_item(botao)

        # atributos: liberados depois da classe (e da magia, pra quem tem); só enquanto sobrar ponto
        liberado = not (ordem and rules.creation_missing_before("atributos", status)) and bool(char["race"])
        sobra = pontos_livres(char) > 0
        for grupo, (emoji, rotulo, _, _) in GRUPOS_ATRIBUTOS.items():
            botao = discord.ui.Button(label=rotulo, emoji=emoji, style=discord.ButtonStyle.primary, row=2, disabled=not (liberado and sobra))
            botao.callback = functools.partial(self._abrir_atributos, grupo)
            self.add_item(botao)

        for emoji, rotulo, acao in (("🎲", "Dados", self._abrir_dados), ("📈", "Níveis", self._ver_niveis), ("❓", "Ajuda", self._ver_ajuda)):
            botao = discord.ui.Button(label=rotulo, emoji=emoji, style=discord.ButtonStyle.secondary, row=2)
            botao.callback = acao
            self.add_item(botao)

        personagens = db.list_characters(str(self.dono_id))
        if len(personagens) > 1:
            opcoes = [
                discord.SelectOption(
                    label=p["name"][:100], value=str(p["id"]), default=p["id"] == self.personagem_id,
                    description=f"nível {p['level']} · {p['race'] or ('❓ ???' if rules.special_result(p, 'raca') else 'sem raça')}",
                )
                for p in personagens[:25]
            ]
            seletor = discord.ui.Select(placeholder="Trocar de personagem", options=opcoes, row=3)
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

    # ---- habilidade de classe ----
    async def _abrir_habilidade(self, interaction: discord.Interaction) -> None:
        escolha = EscolhaDeHabilidade(self.dono_id, self.personagem_id, self.jogador, com_voltar=True)
        self.passar_pra(escolha)
        await interaction.response.edit_message(embed=escolha.embed(), view=escolha)

    # ---- Disciplinas ----
    async def _abrir_disciplinas(self, interaction: discord.Interaction) -> None:
        painel = PainelDisciplinas(self.dono_id, self.personagem_id, self.jogador)
        self.passar_pra(painel)
        await interaction.response.edit_message(embed=painel.embed(), view=painel)

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
        self.habilidade: str | None = None   # só nas classes com duas habilidades (Clérigo e Ladrão)
        self._montar()

    def personagem(self):
        return db.get_character_by_id(self.personagem_id)

    def _precisa_de_habilidade(self) -> bool:
        return self.escolhida is not None and rules.class_needs_ability_choice(self.escolhida)

    def _montar(self) -> None:
        self.clear_items()
        opcoes = [
            discord.SelectOption(label=c, value=c, description=f"Vantagem: {rules.CLASS_SKILLS[c]}"[:100], default=c == self.escolhida)
            for c in rules.CLASSES
        ]
        seletor = discord.ui.Select(placeholder="Escolha a classe", options=opcoes, row=0)
        seletor.callback = functools.partial(self._escolheu, seletor)
        self.add_item(seletor)
        if self._precisa_de_habilidade():
            _botoes_de_habilidade(self, rules.class_ability_options(self.escolhida), self.habilidade, self._escolheu_habilidade, row=1)
        pronto = self.escolhida is not None and (not self._precisa_de_habilidade() or self.habilidade is not None)
        confirmar = discord.ui.Button(
            label="Confirmar classe e habilidade" if self._precisa_de_habilidade() else "Confirmar classe",
            emoji="✅", style=discord.ButtonStyle.success, disabled=not pronto, row=2,
        )
        confirmar.callback = self._confirmar
        voltar = discord.ui.Button(label="Voltar", emoji="⬅️", style=discord.ButtonStyle.secondary, row=2)
        voltar.callback = self._voltar
        self.add_item(confirmar)
        self.add_item(voltar)

    def embed(self) -> discord.Embed:
        nome = self.personagem()["name"]
        if self.escolhida is None:
            embed = discord.Embed(
                title=f"🎓 Escolha a classe de {nome}",
                description=(
                "Vale **uma vez só**: depois de confirmar, só um mestre muda. Escolhe no menu pra ver a classe antes. "
                "O Clérigo e o Ladrão têm duas habilidades: você escolhe a sua nos botões, junto com a classe."
            ),
                color=discord.Color.dark_green(),
            )
            for classe, b in rules.CLASSES.items():
                habilidades = " ou ".join(rules.class_ability_options(classe))
                embed.add_field(
                    name=classe,
                    value=(
                        f"{rules.CLASS_SKILLS[classe]}\nVida +{b['vida']} · Sanidade +{b['sanidade']} · Mana +{b['mana']} · Estamina +{b['estamina']}"
                        f"\n✨ {habilidades}"
                    ),
                    inline=False,
                )
            return embed
        return vitrine.previa_classe(nome, self.escolhida, self.habilidade)

    async def _escolheu(self, seletor: discord.ui.Select, interaction: discord.Interaction) -> None:
        escolha = seletor.values[0]
        if escolha not in rules.CLASSES:
            await interaction.response.send_message("Não conheço essa classe. Escolhe uma do menu.", ephemeral=True)
            return
        if escolha != self.escolhida:
            self.habilidade = None   # outra classe, outras habilidades: a marcação anterior não vale
        self.escolhida = escolha
        self._montar()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def _escolheu_habilidade(self, nome: str, interaction: discord.Interaction) -> None:
        if not self._precisa_de_habilidade() or nome not in rules.class_ability_options(self.escolhida):
            await interaction.response.send_message("Essa habilidade não é da classe escolhida. Escolhe uma dos botões.", ephemeral=True)
            return
        self.habilidade = nome
        self._montar()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def _voltar(self, interaction: discord.Interaction) -> None:
        painel = PainelFicha(self.dono_id, self.personagem_id, self.jogador)
        self.passar_pra(painel)
        await interaction.response.edit_message(embed=GANCHOS.embed_ficha(painel.personagem(), self.jogador), view=painel)

    async def _confirmar(self, interaction: discord.Interaction) -> None:
        if self._precisa_de_habilidade() and self.habilidade is None:   # o botão já vem desligado, mas confere
            await interaction.response.send_message("Escolhe a habilidade nos botões antes de confirmar.", ephemeral=True)
            return
        coletor = Coletor(interaction)
        await GANCHOS.escolher_classe(coletor, self.escolhida, self.personagem()["name"], self.habilidade)
        painel = PainelFicha(self.dono_id, self.personagem_id, self.jogador)
        self.passar_pra(painel)
        await entregar(interaction, coletor, GANCHOS.embed_ficha(painel.personagem(), self.jogador), painel)


def _botoes_de_habilidade(view: discord.ui.View, opcoes, escolhida: str | None, acao, row: int) -> None:
    """Um botão por habilidade (o escolhido fica verde)."""
    for nome in opcoes:
        botao = discord.ui.Button(
            label=nome, emoji="✨", row=row,
            style=discord.ButtonStyle.success if nome == escolhida else discord.ButtonStyle.primary,
        )
        botao.callback = functools.partial(acao, nome)
        view.add_item(botao)


class EscolhaDeHabilidade(_Painel):
    """Escolher uma das duas habilidades da classe (Clérigo e Ladrão) com botões: marca uma e confirma, porque
    vale uma vez só. Usada na ficha (com Voltar) e depois do /classe e do /habilidade (sem Voltar)."""

    def __init__(self, dono_id: int, personagem_id: int, jogador: str, com_voltar: bool = True):
        super().__init__(dono_id)
        self.personagem_id = personagem_id
        self.jogador = jogador
        self.com_voltar = com_voltar
        self.escolhida: str | None = None
        self._montar()

    def personagem(self):
        return db.get_character_by_id(self.personagem_id)

    def _montar(self) -> None:
        self.clear_items()
        char = self.personagem()
        _botoes_de_habilidade(self, rules.class_ability_options(char["class_name"]) if char else (), self.escolhida, self._marcou, row=0)
        confirmar = discord.ui.Button(label="Confirmar habilidade", emoji="✅", style=discord.ButtonStyle.success, disabled=self.escolhida is None, row=1)
        confirmar.callback = self._confirmar
        self.add_item(confirmar)
        if self.com_voltar:
            voltar = discord.ui.Button(label="Voltar", emoji="⬅️", style=discord.ButtonStyle.secondary, row=1)
            voltar.callback = self._voltar
            self.add_item(voltar)

    def embed(self) -> discord.Embed:
        char = self.personagem()
        embed = vitrine.cartao_habilidade(char["name"], char["class_name"], self.escolhida, self.jogador, "previa").embed
        embed.description += "\n\nVale **uma vez só**: depois de confirmar, só um mestre muda."
        return embed

    async def _marcou(self, nome: str, interaction: discord.Interaction) -> None:
        char = self.personagem()
        if char is None or nome not in rules.class_ability_options(char["class_name"]):
            await interaction.response.send_message("Essa habilidade não é da sua classe. Escolhe uma dos botões.", ephemeral=True)
            return
        self.escolhida = nome
        self._montar()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def _voltar(self, interaction: discord.Interaction) -> None:
        painel = PainelFicha(self.dono_id, self.personagem_id, self.jogador)
        self.passar_pra(painel)
        await interaction.response.edit_message(embed=GANCHOS.embed_ficha(painel.personagem(), self.jogador), view=painel)

    async def _confirmar(self, interaction: discord.Interaction) -> None:
        char = self.personagem()
        classe = char["class_name"] if char else None
        valida = (
            char is not None and rules.class_needs_ability_choice(classe) and rules.class_ability_of(char) is None
            and self.escolhida in rules.class_ability_options(classe)
        )
        coletor = Coletor(interaction)
        if valida:
            db.set_class_ability(char["id"], self.escolhida)
            cartao = vitrine.cartao_habilidade(char["name"], classe, self.escolhida, self.jogador)
            if self.com_voltar:
                coletor.mensagens.append((None, {"embed": cartao.embed, "ephemeral": True}))
            else:
                self.stop()
                await interaction.response.edit_message(embed=cartao.embed, view=None)
                return
        else:
            coletor.avisar("Não deu pra confirmar: a habilidade já foi escolhida ou a classe mudou. Abre a ficha de novo com `/minha_ficha`.")
            if not self.com_voltar:
                self.stop()
                await interaction.response.edit_message(view=None)
                for conteudo, kwargs in coletor.mensagens:
                    await interaction.followup.send(conteudo, **kwargs)
                return
        painel = PainelFicha(self.dono_id, self.personagem_id, self.jogador)
        self.passar_pra(painel)
        await entregar(interaction, coletor, GANCHOS.embed_ficha(painel.personagem(), self.jogador), painel)


# ---------------------------------------------------------------------------
# Vitais: as barras de Vida, Sanidade, Mana e Estamina, pra subir e descer com botões
# ---------------------------------------------------------------------------
class PainelVitais(_Painel):
    """Escolhe a barra no menu e aperta os botões. O bot guarda quanto o personagem perdeu de cada uma."""

    def __init__(self, dono_id: int, personagem_id: int, jogador: str, selecionado: str = "vida"):
        super().__init__(dono_id)
        self.personagem_id = personagem_id
        self.jogador = jogador
        self.selecionado = selecionado if selecionado in rules.VITAL_KEYS else "vida"
        self._montar()

    def personagem(self):
        return db.get_character_by_id(self.personagem_id)

    def _dados(self):
        char = self.personagem()
        return char, GANCHOS.recursos(char), db.get_vitals_lost(char["id"])

    def embed(self) -> discord.Embed:
        char, recursos, perdidos = self._dados()
        if recursos is None:
            return vitrine.embed_decorado(
                "Vitais", None,
                f"As barras de Vida, Sanidade, Mana e Estamina dependem da classe, e **{char['name']}** ainda não tem. "
                "Vai na aba **Ficha** e aperta **Classe**.",
                discord.Color.dark_grey(), autor=char["name"],
            )
        return vitrine.embed_vitais(char["name"], recursos, perdidos, self.jogador, self.selecionado)

    def _montar(self) -> None:
        self.clear_items()
        adicionar_abas(self, "vitais")
        _, recursos, perdidos = self._dados()
        if recursos is None:   # sem classe não há máximo: só as abas
            return
        opcoes = [
            discord.SelectOption(
                label=rules.VITAL_LABELS[k], value=k, emoji=rules.VITAL_EMOJI[k], default=k == self.selecionado,
                description=f"{rules.vital_current(recursos[k]['total'], perdidos.get(k, 0))}/{recursos[k]['total']}",
            )
            for k in rules.VITAL_KEYS
        ]
        seletor = discord.ui.Select(placeholder="1. Escolhe a barra", options=opcoes, row=1)
        seletor.callback = functools.partial(self._escolheu, seletor)
        self.add_item(seletor)
        for delta, linha in ((-10, 2), (-5, 2), (-1, 2), (1, 2), (5, 2), (10, 3)):
            botao = discord.ui.Button(
                label=f"{delta:+d}", row=linha,
                style=discord.ButtonStyle.danger if delta < 0 else discord.ButtonStyle.success,
            )
            botao.callback = functools.partial(self._mudar, delta)
            self.add_item(botao)
        exato = discord.ui.Button(label="Valor exato", emoji="✏️", style=discord.ButtonStyle.secondary, row=3)
        exato.callback = self._valor_exato
        restaurar = discord.ui.Button(label="Restaurar tudo", emoji="♻️", style=discord.ButtonStyle.secondary, row=3)
        restaurar.callback = self._restaurar
        self.add_item(exato)
        self.add_item(restaurar)

    async def _redesenhar(self, interaction: discord.Interaction) -> None:
        self._montar()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def _escolheu(self, seletor: discord.ui.Select, interaction: discord.Interaction) -> None:
        if seletor.values[0] not in rules.VITAL_KEYS:
            await interaction.response.send_message("Não conheço essa barra. Escolhe uma do menu.", ephemeral=True)
            return
        self.selecionado = seletor.values[0]
        await self._redesenhar(interaction)

    async def _mudar(self, delta: int, interaction: discord.Interaction) -> None:
        char, recursos, perdidos = self._dados()
        if recursos is None:
            await self._redesenhar(interaction)
            return
        maximo = recursos[self.selecionado]["total"]
        db.set_vital_lost(char["id"], self.selecionado, rules.vital_lost_after_change(maximo, perdidos[self.selecionado], delta))
        await self._redesenhar(interaction)

    async def _valor_exato(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ModalValorExato(self))

    async def aplicar_valor(self, interaction: discord.Interaction, valor: int) -> None:
        """Chamado pelo formulário do Valor exato."""
        char, recursos, _ = self._dados()
        if recursos is None:
            await self._redesenhar(interaction)
            return
        maximo = recursos[self.selecionado]["total"]
        db.set_vital_lost(char["id"], self.selecionado, rules.vital_lost_for_value(maximo, valor))
        await self._redesenhar(interaction)

    async def _restaurar(self, interaction: discord.Interaction) -> None:
        db.reset_vitals(self.personagem_id)
        await self._redesenhar(interaction)


class ModalValorExato(discord.ui.Modal):
    def __init__(self, painel: PainelVitais):
        char, recursos, perdidos = painel._dados()
        chave = painel.selecionado
        maximo = recursos[chave]["total"]
        super().__init__(title=f"{rules.VITAL_LABELS[chave]}: valor exato", timeout=TEMPO_DO_PAINEL)
        self.painel = painel
        self.campo = discord.ui.TextInput(
            label=f"Quanto de {rules.VITAL_LABELS[chave]} você tem agora? (0 a {maximo})"[:45],
            default=str(rules.vital_current(maximo, perdidos.get(chave, 0))), max_length=6, required=True,
        )
        self.add_item(self.campo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        texto = self.campo.value.strip()
        if not texto.isdigit():
            await interaction.response.send_message("Escreve só um número, tipo 12.", ephemeral=True)
            return
        await self.painel.aplicar_valor(interaction, int(texto))

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await _avisar_erro(interaction, error)


# ---------------------------------------------------------------------------
# Perícias: distribuir os pontos e testar com um clique
# ---------------------------------------------------------------------------
_PROXIMO_MODO = {"normal": "vantagem", "vantagem": "desvantagem", "desvantagem": "normal"}
_CICLO_DE_ATRIBUTO = (None,) + rules.ATTRIBUTES


class PainelPericias(_Painel):
    """Um ícone por perícia: toca e o bot rola 1d20 + atributo + perícia sozinho. A vantagem da classe entra sozinha."""

    def __init__(self, dono_id: int, personagem_id: int, jogador: str, modo: str = "normal", atributo: str | None = None):
        super().__init__(dono_id)
        self.personagem_id = personagem_id
        self.jogador = jogador
        self.modo = modo if modo in _PROXIMO_MODO else "normal"
        self.atributo = atributo if atributo in rules.ATTRIBUTES else None   # None = o padrão de cada perícia
        self._montar()

    def personagem(self):
        return db.get_character_by_id(self.personagem_id)

    def _dados(self):
        char = self.personagem()
        escolhidas = db.get_skill_picks(char["id"])
        return char, db.get_skills(char["id"]), escolhidas, rules.skills_with_advantage(char["class_name"], escolhidas)

    def embed(self) -> discord.Embed:
        char, pontos, escolhidas, _ = self._dados()
        return vitrine.embed_rolar_pericias(char["name"], pontos, db.attributes_of(char), char["class_name"], escolhidas, self.modo, self.atributo, self.jogador)

    def _montar(self) -> None:
        self.clear_items()
        adicionar_abas(self, "pericias")
        _, _, _, vantagens = self._dados()
        emoji, rotulo = vitrine.MODOS_DE_TESTE[self.modo]
        modo = discord.ui.Button(label=rotulo, emoji=emoji, style=discord.ButtonStyle.secondary, row=0)
        modo.callback = self._trocar_modo
        self.add_item(modo)
        for i, pericia in enumerate(rules.SKILLS):   # 18 ícones: 5, 5, 5 e 3 (a última linha divide com os dois botões)
            botao = discord.ui.Button(
                emoji=rules.SKILL_ICONS[pericia], row=1 + i // 5,
                style=discord.ButtonStyle.primary if pericia in vantagens else discord.ButtonStyle.secondary,
            )
            botao.callback = functools.partial(self._rolar, pericia)
            self.add_item(botao)
        distribuir = discord.ui.Button(label="Distribuir", emoji="🎯", style=discord.ButtonStyle.secondary, row=4)
        distribuir.callback = self._ir_distribuir
        atributo = discord.ui.Button(
            label="Atributo", emoji="🧬", row=4,
            style=discord.ButtonStyle.success if self.atributo else discord.ButtonStyle.secondary,
        )
        atributo.callback = self._trocar_atributo
        self.add_item(distribuir)
        self.add_item(atributo)

    async def _redesenhar(self, interaction: discord.Interaction, coletor: Coletor | None = None) -> None:
        self._montar()
        await entregar(interaction, coletor or Coletor(interaction), self.embed(), self)

    async def _rolar(self, pericia: str, interaction: discord.Interaction) -> None:
        coletor = Coletor(interaction)
        char, pontos, _, vantagens = self._dados()
        atributo = self.atributo or rules.SKILL_DEFAULT_ATTRIBUTE[pericia]
        bonus = db.attributes_of(char)[atributo] + pontos.get(pericia, 0)
        notacao = f"1d20{bonus:+d}" if bonus else "1d20"
        motivo = f"{pericia} ({rules.ATTRIBUTE_LABELS[atributo]})"
        await GANCHOS.teste(coletor, notacao, motivo, char["name"], rules.effective_roll_mode(self.modo, pericia in vantagens))
        await self._redesenhar(interaction, coletor)

    async def _trocar_modo(self, interaction: discord.Interaction) -> None:
        self.modo = _PROXIMO_MODO[self.modo]
        await self._redesenhar(interaction)

    async def _trocar_atributo(self, interaction: discord.Interaction) -> None:
        self.atributo = _CICLO_DE_ATRIBUTO[(_CICLO_DE_ATRIBUTO.index(self.atributo) + 1) % len(_CICLO_DE_ATRIBUTO)]
        await self._redesenhar(interaction)

    async def _ir_distribuir(self, interaction: discord.Interaction) -> None:
        nova = PainelDistribuirPericias(self.dono_id, self.personagem_id, self.jogador)
        self.passar_pra(nova)
        await interaction.response.edit_message(embed=nova.embed(), view=nova)


class PainelDistribuirPericias(_Painel):
    """Escolhe a perícia e soma ou tira pontos; também é onde se escolhe a vantagem da classe (Luta ou Pontaria...)."""

    def __init__(self, dono_id: int, personagem_id: int, jogador: str, selecionada: str = rules.SKILLS[0]):
        super().__init__(dono_id)
        self.personagem_id = personagem_id
        self.jogador = jogador
        self.selecionada = selecionada if selecionada in rules.SKILLS else rules.SKILLS[0]
        self._montar()

    def personagem(self):
        return db.get_character_by_id(self.personagem_id)

    def _dados(self):
        char = self.personagem()
        return char, db.get_skills(char["id"]), rules.skill_points_total(char["level"], char["class_name"]), db.get_skill_picks(char["id"])

    def embed(self) -> discord.Embed:
        char, pontos, total, escolhidas = self._dados()
        return vitrine.embed_pericias(char["name"], pontos, total, self.selecionada, char["class_name"], escolhidas, self.jogador)

    def _montar(self) -> None:
        self.clear_items()
        adicionar_abas(self, "pericias")
        char, pontos, total, escolhidas = self._dados()
        livres = total - sum(pontos.values())
        vantagens = rules.skills_with_advantage(char["class_name"], escolhidas)
        opcoes = [
            discord.SelectOption(
                label=p, value=p, emoji=rules.SKILL_ICONS[p], default=p == self.selecionada,
                description=f"{pontos.get(p, 0)} pontos" + (" · ⭐ vantagem da classe" if p in vantagens else ""),
            )
            for p in rules.SKILLS
        ]
        seletor = discord.ui.Select(placeholder="1. Escolhe a perícia", options=opcoes, row=1)
        seletor.callback = functools.partial(self._escolheu_pericia, seletor)
        self.add_item(seletor)
        pts = pontos.get(self.selecionada, 0)
        menos = discord.ui.Button(label="-1", style=discord.ButtonStyle.danger, disabled=pts <= 0, row=2)
        menos.callback = functools.partial(self._mudar, -1)
        mais = discord.ui.Button(label="+1", style=discord.ButtonStyle.success, disabled=pts >= rules.SKILL_MAX_POINTS or livres <= 0, row=2)
        mais.callback = functools.partial(self._mudar, 1)
        rolar = discord.ui.Button(label="Rolar perícias", emoji="🎲", style=discord.ButtonStyle.primary, row=2)
        rolar.callback = self._ir_rolar
        for botao in (menos, mais, rolar):
            self.add_item(botao)
        info = rules.CLASS_SKILL_ADVANTAGES.get(char["class_name"] or "", {})
        if info.get("escolha") or info.get("livres"):
            permitidas = list(info["escolha"]) if info.get("escolha") else list(rules.SKILLS)
            limite = 1 if info.get("escolha") else info["livres"]
            atuais = rules._picks_validos(char["class_name"], escolhidas)
            vantagem = discord.ui.Select(
                placeholder="⭐ Escolhe a vantagem da classe" + (f" ({' ou '.join(permitidas)})" if info.get("escolha") else f" ({limite} perícias)"),
                min_values=1, max_values=limite, row=3,
                options=[discord.SelectOption(label=p, value=p, emoji=rules.SKILL_ICONS[p], default=p in atuais) for p in permitidas],
            )
            vantagem.callback = functools.partial(self._escolheu_vantagem, vantagem)
            self.add_item(vantagem)

    async def _redesenhar(self, interaction: discord.Interaction) -> None:
        self._montar()
        await entregar(interaction, Coletor(interaction), self.embed(), self)

    async def _escolheu_pericia(self, seletor: discord.ui.Select, interaction: discord.Interaction) -> None:
        if seletor.values[0] in rules.SKILLS:
            self.selecionada = seletor.values[0]
        await self._redesenhar(interaction)

    async def _escolheu_vantagem(self, seletor: discord.ui.Select, interaction: discord.Interaction) -> None:
        char = self.personagem()
        validas = rules._picks_validos(char["class_name"], seletor.values)   # só vale o que cabe na classe
        if validas:
            db.set_skill_picks(char["id"], validas)
        await self._redesenhar(interaction)

    async def _mudar(self, delta: int, interaction: discord.Interaction) -> None:
        char, pontos, total, _ = self._dados()
        novo = pontos.get(self.selecionada, 0) + delta
        livres = total - sum(pontos.values())
        if 0 <= novo <= rules.SKILL_MAX_POINTS and (delta < 0 or livres > 0):   # os botões já vêm desligados, mas confere
            db.set_skill_points(char["id"], self.selecionada, novo)
        await self._redesenhar(interaction)

    async def _ir_rolar(self, interaction: discord.Interaction) -> None:
        nova = PainelPericias(self.dono_id, self.personagem_id, self.jogador)
        self.passar_pra(nova)
        await interaction.response.edit_message(embed=nova.embed(), view=nova)


# ---------------------------------------------------------------------------
# Habilidades criadas pelo jogador
# ---------------------------------------------------------------------------
class PainelHabilidades(_Painel):
    """Cria a habilidade num formulário, acompanha o que o mestre decidiu e usa com um botão."""

    def __init__(self, dono_id: int, personagem_id: int, jogador: str, selecionada: int | None = None):
        super().__init__(dono_id)
        self.personagem_id = personagem_id
        self.jogador = jogador
        self.selecionada = selecionada
        self._montar()

    def personagem(self):
        return db.get_character_by_id(self.personagem_id)

    def _escolhida(self):
        return next((a for a in db.list_abilities(self.personagem_id) if a["id"] == self.selecionada), None)

    def embed(self) -> discord.Embed:
        return vitrine.embed_habilidades(self.personagem()["name"], db.list_abilities(self.personagem_id), self.selecionada, self.jogador)

    def _montar(self) -> None:
        self.clear_items()
        adicionar_abas(self, "habilidades")
        lista = db.list_abilities(self.personagem_id)
        if self.selecionada not in {a["id"] for a in lista}:
            self.selecionada = None
        if lista:
            opcoes = [
                discord.SelectOption(
                    label=a["name"][:100], value=str(a["id"]), emoji=habil.MARCA[a["status"]],
                    description=habil.FRASE[a["status"]], default=a["id"] == self.selecionada,
                )
                for a in lista[:25]
            ]
            seletor = discord.ui.Select(placeholder="Escolhe uma habilidade", options=opcoes, row=1)
            seletor.callback = functools.partial(self._escolheu, seletor)
            self.add_item(seletor)
        escolhida = self._escolhida()
        criar = discord.ui.Button(
            label="Criar habilidade", emoji="➕", style=discord.ButtonStyle.success, row=2,
            disabled=db.count_active_abilities(self.personagem_id) >= rules.MAX_CUSTOM_ABILITIES,
        )
        criar.callback = self._criar
        usar = discord.ui.Button(
            label="Usar", emoji="⚡", style=discord.ButtonStyle.primary, row=2,
            disabled=not (escolhida and escolhida["status"] == "aprovada"),
        )
        usar.callback = self._usar
        mexivel = bool(escolhida and escolhida["status"] in habil.PODE_EDITAR)
        editar = discord.ui.Button(label="Editar", emoji="✏️", style=discord.ButtonStyle.secondary, row=2, disabled=not mexivel)
        editar.callback = self._editar
        apagar = discord.ui.Button(label="Apagar", emoji="🗑", style=discord.ButtonStyle.danger, row=2, disabled=not mexivel)
        apagar.callback = self._apagar
        for botao in (criar, usar, editar, apagar):
            self.add_item(botao)

    async def _redesenhar(self, interaction: discord.Interaction, coletor: Coletor | None = None) -> None:
        self._montar()
        await entregar(interaction, coletor or Coletor(interaction), self.embed(), self)

    async def _escolheu(self, seletor: discord.ui.Select, interaction: discord.Interaction) -> None:
        self.selecionada = int(seletor.values[0])
        await self._redesenhar(interaction)

    async def _criar(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ModalHabilidade(self))

    async def _editar(self, interaction: discord.Interaction) -> None:
        ab = self._escolhida()
        if ab is None:
            await self._redesenhar(interaction)
            return
        await interaction.response.send_modal(ModalHabilidade(self, ab))

    async def aplicar_formulario(self, interaction: discord.Interaction, nome: str, descricao: str, efeito: str,
                                 ability_id: int | None) -> None:
        """Chamado pelo formulário: cria a habilidade (ou refaz o texto) e avisa o que aconteceu."""
        r = habil.criar(self.personagem_id, nome, descricao, efeito) if ability_id is None else habil.editar(ability_id, nome, descricao, efeito)
        coletor = Coletor(interaction)
        coletor.avisar(r.texto)
        if r.ok and r.id is not None:
            self.selecionada = r.id
        await self._redesenhar(interaction, coletor)

    async def _apagar(self, interaction: discord.Interaction) -> None:
        coletor = Coletor(interaction)
        ab = self._escolhida()
        coletor.avisar(habil.apagar(ab["id"]).texto if ab else "Essa habilidade já não existe.")
        self.selecionada = None
        await self._redesenhar(interaction, coletor)

    async def _usar(self, interaction: discord.Interaction) -> None:
        coletor = Coletor(interaction)
        ab = self._escolhida()
        char = self.personagem()
        if ab is None:
            coletor.avisar("Essa habilidade já não existe.")
        else:
            uso = habil.usar(char, ab, GANCHOS.recursos(char))
            if not uso.ok:
                coletor.avisar(uso.erro)
            else:
                if uso.rolagem is not None:
                    db.log_roll(
                        user_id=str(self.dono_id), username=self.jogador,
                        guild_id=str(interaction.guild_id) if interaction.guild_id else None,
                        notation=ab["roll_dice"], rolls=uso.rolagem.rolls, total=uso.total,
                        purpose=f"habilidade: {ab['name']}", character_id=char["id"], character_name=char["name"],
                    )
                coletor.mensagens.append((None, {"embed": vitrine.cartao_uso_habilidade(char["name"], ab, uso, self.jogador).embed}))
        await self._redesenhar(interaction, coletor)


class ModalHabilidade(discord.ui.Modal):
    """O formulário da habilidade: nome, descrição e o efeito que o jogador quer."""

    def __init__(self, painel: PainelHabilidades, habilidade=None):
        super().__init__(title="Editar habilidade" if habilidade else "Nova habilidade", timeout=TEMPO_DO_PAINEL)
        self.painel = painel
        self.ability_id = habilidade["id"] if habilidade else None
        self.nome = discord.ui.TextInput(
            label="Nome da habilidade", required=True, max_length=habil.TAMANHO_NOME, placeholder="ex: Bola de Fogo",
            default=habilidade["name"] if habilidade else None,
        )
        self.descricao = discord.ui.TextInput(
            label="Descrição (o que é e como funciona)", style=discord.TextStyle.paragraph, required=True,
            max_length=habil.TAMANHO_DESCRICAO, placeholder="Conta como a habilidade é, na história.",
            default=habilidade["description"] if habilidade else None,
        )
        self.efeito = discord.ui.TextInput(
            label="O que você quer que ela faça", style=discord.TextStyle.paragraph, required=True,
            max_length=habil.TAMANHO_EFEITO, placeholder="ex: causa 2d8 de dano e gasta 15 de Mana",
            default=habilidade["effect_text"] if habilidade else None,
        )
        for campo in (self.nome, self.descricao, self.efeito):
            self.add_item(campo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.painel.aplicar_formulario(interaction, self.nome.value, self.descricao.value, self.efeito.value, self.ability_id)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await _avisar_erro(interaction, error)


# ---------------------------------------------------------------------------
# Disciplinas (só Vampiro e Dhampir sobem; qualquer um pode ler)
# ---------------------------------------------------------------------------
TEXTO_DO_PROBLEMA = {
    "raca": "Só Vampiros e Dhampirs têm Disciplinas.",
    "desconhecida": "Não conheço essa Disciplina. Escolhe uma do menu.",
    "bloqueada": (
        "A Sanguessugia ainda está em desenvolvimento (os graus 1 a 3 não foram definidos), então ninguém pode "
        "gastar ponto nela por enquanto."
    ),
    "grau_maximo": "Essa Disciplina já está no grau {grau}. Os graus 4 e 5 só um mestre concede.",
    "sem_pontos": "Você não tem pontos de Disciplina sobrando. Vem +1 a cada 2 níveis (2, 4, 6, 8 e 10).",
}


class PainelDisciplinas(_Painel):
    """Menu das dez Disciplinas: mostra o texto de cada grau e, pra Vampiro e Dhampir, deixa gastar os pontos
    (um grau por clique). O jogador só aumenta, e só até o grau 3; os graus 4 e 5 são do mestre."""

    def __init__(self, dono_id: int, personagem_id: int | None, jogador: str, selecionada: str | None = None):
        super().__init__(dono_id)
        self.personagem_id = personagem_id
        self.jogador = jogador
        self.selecionada = selecionada
        self._montar()

    def personagem(self):
        return db.get_character_by_id(self.personagem_id) if self.personagem_id else None

    def _graus(self) -> dict[str, int]:
        return db.get_disciplines(self.personagem_id) if self.personagem_id else {}

    def _pode_gastar(self) -> bool:
        char = self.personagem()
        return char is not None and rules.has_disciplines(char["race"])

    def _problema(self) -> str | None:
        char = self.personagem()
        return rules.discipline_raise_problem(char["race"], char["level"], self._graus(), self.selecionada)

    def embed(self) -> discord.Embed:
        char, graus = self.personagem(), self._graus()
        pode = self._pode_gastar()
        if self.selecionada is None:
            return vitrine.embed_disciplinas(char["name"] if char else None, char["race"] if char else None,
                                             char["level"] if char else 1, graus)
        if not pode:
            return vitrine.embed_disciplina(self.selecionada)
        problema = self._problema()
        grau = graus.get(self.selecionada, 0)
        aviso = (
            TEXTO_DO_PROBLEMA[problema].format(grau=grau)
            if problema else f"Aperta o botão pra gastar 1 ponto e subir pro grau {grau + 1}. Não dá pra desfazer."
        )
        return vitrine.embed_disciplina(
            self.selecionada, grau, vitrine.linha_de_pontos(char["level"], char["race"], graus), aviso
        )

    def _montar(self) -> None:
        self.clear_items()
        graus = self._graus()
        pode = self._pode_gastar()
        opcoes = []
        for disciplina in rules.DISCIPLINES:
            tema = lore.DISCIPLINAS[disciplina]["tema"]
            if rules.discipline_blocked(disciplina):
                descricao = "em desenvolvimento"
            elif pode:
                descricao = f"grau {graus.get(disciplina, 0)}/{rules.MAX_DISCIPLINE_GRADE} · {tema}"
            else:
                descricao = tema
            opcoes.append(discord.SelectOption(label=disciplina, value=disciplina, description=descricao[:100],
                                               default=disciplina == self.selecionada))
        seletor = discord.ui.Select(placeholder="Escolhe uma Disciplina", options=opcoes, row=0)
        seletor.callback = functools.partial(self._escolheu, seletor)
        self.add_item(seletor)

        if pode and self.selecionada:
            problema = self._problema()
            grau = graus.get(self.selecionada, 0)
            rotulo = f"Subir pro grau {grau + 1}" if problema is None else "Subir"
            subir = discord.ui.Button(label=rotulo, emoji="⬆️", style=discord.ButtonStyle.success, disabled=problema is not None, row=1)
            subir.callback = self._subir
            self.add_item(subir)
        if self.selecionada:
            todas = discord.ui.Button(label="Ver todas", emoji="📜", style=discord.ButtonStyle.secondary, row=1)
            todas.callback = self._ver_todas
            self.add_item(todas)
        if self.personagem_id:
            voltar = discord.ui.Button(label="Voltar", emoji="⬅️", style=discord.ButtonStyle.secondary, row=1)
            voltar.callback = self._voltar
            self.add_item(voltar)

    async def _redesenhar(self, interaction: discord.Interaction, coletor: Coletor | None = None) -> None:
        self._montar()
        await entregar(interaction, coletor or Coletor(interaction), self.embed(), self)

    async def _escolheu(self, seletor: discord.ui.Select, interaction: discord.Interaction) -> None:
        escolha = seletor.values[0]
        if escolha not in rules.DISCIPLINES:
            await interaction.response.send_message(TEXTO_DO_PROBLEMA["desconhecida"], ephemeral=True)
            return
        self.selecionada = escolha
        await self._redesenhar(interaction)

    async def _ver_todas(self, interaction: discord.Interaction) -> None:
        self.selecionada = None
        await self._redesenhar(interaction)

    async def _subir(self, interaction: discord.Interaction) -> None:
        coletor = Coletor(interaction)
        char = self.personagem()
        problema = self._problema() if (char and self.selecionada) else "raca"
        if problema:  # o painel pode estar velho: confere de novo na hora
            grau = self._graus().get(self.selecionada, 0) if self.selecionada else 0
            coletor.avisar(TEXTO_DO_PROBLEMA[problema].format(grau=grau))
        else:
            novo = self._graus().get(self.selecionada, 0) + 1
            db.set_discipline_grade(char["id"], self.selecionada, novo)
            livres = rules.discipline_points_free(char["level"], char["race"], self._graus())
            sobra = "Não sobrou ponto." if livres <= 0 else ("Sobra 1 ponto." if livres == 1 else f"Sobram {livres} pontos.")
            coletor.avisar(f"🩸 **{self.selecionada}** subiu pro grau {novo}. {sobra}")
        await self._redesenhar(interaction, coletor)

    async def _voltar(self, interaction: discord.Interaction) -> None:
        painel = PainelFicha(self.dono_id, self.personagem_id, self.jogador)
        self.passar_pra(painel)
        await interaction.response.edit_message(embed=GANCHOS.embed_ficha(painel.personagem(), self.jogador), view=painel)


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
