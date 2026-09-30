"""O Escudo do Mestre e o quadro da cena: as telas com botões.

A regra (iniciativa, vez, intenções) fica no cena.py. Aqui só se mostra e se edita mensagem.

- QuadroDaCena: a mensagem PÚBLICA da cena, com a ordem da iniciativa e os botões dos jogadores. Os botões têm
  identificador fixo, então continuam funcionando mesmo depois que o bot reinicia (o bot.py registra a tela
  na partida).
- EscudoDoMestre: a tela PRIVADA do mestre (só ele vê): a ordem com as intenções escritas, permitir ou negar,
  próximo turno, NPCs, editar e remover. Como é uma mensagem privada, ela só se atualiza quando o mestre
  aperta algo (o botão Atualizar mostra o que chegou).
"""

import functools
from types import SimpleNamespace

import discord

import cena
import db
from paineis import Coletor, TEMPO_DO_PAINEL, _Painel, _avisar_erro, entregar

# O bot.py entrega as duas funções que dependem dele (quem é mestre e a regra de ficha pronta).
CONFIG = SimpleNamespace(eh_mestre=None, bloqueio_de_rolagem=None)

SEM_CENA = "Não tem cena aberta neste canal. Um mestre abre com `/mestre escudo`."
SEM_PERSONAGEM = "Pra entrar na cena você precisa de um personagem. Começa por `/personagem criar`."
SO_MESTRE = "Só quem é mestre usa o Escudo."


def registrar(eh_mestre, bloqueio_de_rolagem) -> None:
    """eh_mestre(membro) -> bool. bloqueio_de_rolagem(user_id, eh_mestre) -> texto do bloqueio ou None."""
    CONFIG.eh_mestre = eh_mestre
    CONFIG.bloqueio_de_rolagem = bloqueio_de_rolagem


# ---------------------------------------------------------------------------
# Mandar e editar o quadro público
# ---------------------------------------------------------------------------
async def atualizar_quadro(canal, cena_id: int) -> bool:
    """Edita o quadro que já está no canal. False se a cena não tem quadro (ou ele foi apagado)."""
    c = db.get_scene(cena_id)
    if c is None or not c["board_message_id"] or canal is None:
        return False
    try:
        await canal.get_partial_message(int(c["board_message_id"])).edit(
            embed=cena.embed_quadro(cena_id), view=QuadroDaCena() if c["active"] else None
        )
    except discord.NotFound:  # apagaram a mensagem: esquece, o próximo "Mostrar iniciativa" posta outra
        db.set_scene_board(cena_id, None)
        return False
    except discord.HTTPException:
        return False
    return True


async def mostrar_quadro(canal, cena_id: int) -> str:
    """Atualiza o quadro, ou posta um novo. Devolve 'atualizado', 'postado' ou 'erro'."""
    if await atualizar_quadro(canal, cena_id):
        return "atualizado"
    try:
        mensagem = await canal.send(embed=cena.embed_quadro(cena_id), view=QuadroDaCena())
    except (discord.HTTPException, AttributeError):
        return "erro"
    db.set_scene_board(cena_id, str(mensagem.id))
    return "postado"


# ---------------------------------------------------------------------------
# O que os jogadores fazem (pelo comando ou pelo botão do quadro)
# ---------------------------------------------------------------------------
def _cena_do_canal(interaction: discord.Interaction):
    return db.get_active_scene(str(interaction.channel_id))


async def entrar_na_iniciativa(interaction: discord.Interaction) -> None:
    c = _cena_do_canal(interaction)
    if c is None:
        await interaction.response.send_message(SEM_CENA, ephemeral=True)
        return
    uid = str(interaction.user.id)
    bloqueio = CONFIG.bloqueio_de_rolagem(uid, CONFIG.eh_mestre(interaction.user))
    if bloqueio:
        await interaction.response.send_message(bloqueio, ephemeral=True)
        return
    personagem = db.get_active_character(uid)
    if personagem is None:
        await interaction.response.send_message(SEM_PERSONAGEM, ephemeral=True)
        return
    r = cena.entrar_na_cena(
        c, personagem, uid, str(interaction.user.display_name), str(interaction.guild_id) if interaction.guild_id else None
    )
    await interaction.response.send_message(r.texto, ephemeral=True)
    if r.mudou:
        await atualizar_quadro(interaction.channel, c["id"])


async def mandar_intencao(interaction: discord.Interaction, texto: str | None) -> None:
    """Com texto, manda a intenção. Sem texto, mostra a situação da que já foi mandada."""
    c = _cena_do_canal(interaction)
    if c is None:
        await interaction.response.send_message(SEM_CENA, ephemeral=True)
        return
    uid = str(interaction.user.id)
    r = cena.enviar_intencao(c, uid, texto) if texto is not None else cena.ver_minha_intencao(c, uid)
    await interaction.response.send_message(r.texto, ephemeral=True)
    if r.mudou:
        await atualizar_quadro(interaction.channel, c["id"])


class ModalIntencao(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Sua intenção", timeout=TEMPO_DO_PAINEL)
        self.campo = discord.ui.TextInput(
            label="O que o seu personagem quer fazer?", style=discord.TextStyle.paragraph, required=True,
            max_length=cena.TAMANHO_MAX_INTENCAO, placeholder="Uma frase. Só o mestre lê.",
        )
        self.add_item(self.campo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await mandar_intencao(interaction, self.campo.value)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await _avisar_erro(interaction, error)


class QuadroDaCena(discord.ui.View):
    """Os botões do quadro público. Qualquer jogador aperta; o bot descobre a cena pelo canal."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Entrar na iniciativa", emoji="🎲", style=discord.ButtonStyle.primary, custom_id="cena:iniciativa")
    async def entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await entrar_na_iniciativa(interaction)

    @discord.ui.button(label="Enviar intenção", emoji="📝", style=discord.ButtonStyle.success, custom_id="cena:intencao")
    async def mandar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if _cena_do_canal(interaction) is None:
            await interaction.response.send_message(SEM_CENA, ephemeral=True)
            return
        await interaction.response.send_modal(ModalIntencao())

    @discord.ui.button(label="Minha intenção", emoji="👁", style=discord.ButtonStyle.secondary, custom_id="cena:minha")
    async def minha(self, interaction: discord.Interaction, button: discord.ui.Button):
        await mandar_intencao(interaction, None)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item) -> None:
        await _avisar_erro(interaction, error)


# ---------------------------------------------------------------------------
# O Escudo do Mestre
# ---------------------------------------------------------------------------
class _SoMestre(_Painel):
    """Painel que só o dono usa, e só enquanto ele continuar sendo mestre."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if not CONFIG.eh_mestre(interaction.user):
            await interaction.response.send_message(SO_MESTRE, ephemeral=True)
            return False
        return True


class EscudoDoMestre(_SoMestre):
    def __init__(self, dono_id: int, channel_id: str, intencao_sel: int | None = None, participante_sel: int | None = None):
        super().__init__(dono_id)
        self.channel_id = channel_id
        self.intencao_sel = intencao_sel
        self.participante_sel = participante_sel
        self._montar()

    def cena(self):
        return db.get_active_scene(self.channel_id)

    def embed(self) -> discord.Embed:
        c = self.cena()
        return cena.embed_escudo(c["id"], self.intencao_sel) if c else cena.embed_sem_cena()

    def _montar(self) -> None:
        self.clear_items()
        c = self.cena()
        if c is None:
            self.intencao_sel = self.participante_sel = None
            iniciar = discord.ui.Button(label="Iniciar cena", emoji="⚔️", style=discord.ButtonStyle.success, row=0)
            iniciar.callback = self._iniciar
            self.add_item(iniciar)
            return

        partes = db.get_participants(c["id"])
        pendentes = cena.opcoes_de_intencoes(c["id"])
        if self.intencao_sel is not None and str(self.intencao_sel) not in {v for _, v, _ in pendentes}:
            self.intencao_sel = None                      # já decidida, ou a rodada mudou
        if self.participante_sel is not None and self.participante_sel not in {p["id"] for p in partes}:
            self.participante_sel = None                  # já saiu da cena

        for rotulo, emoji, estilo, acao in (
            ("Próximo turno", "▶️", discord.ButtonStyle.primary, self._proximo),
            ("Mostrar iniciativa", "📢", discord.ButtonStyle.secondary, self._mostrar),
            ("NPC", "➕", discord.ButtonStyle.secondary, self._npc),
            ("Atualizar", "🔄", discord.ButtonStyle.secondary, self._atualizar),
            ("Encerrar", "⛔", discord.ButtonStyle.danger, self._encerrar),
        ):
            botao = discord.ui.Button(label=rotulo, emoji=emoji, style=estilo, row=0)
            botao.callback = acao
            self.add_item(botao)

        if pendentes:
            opcoes = [
                discord.SelectOption(label=rot, value=val, description=desc, default=val == str(self.intencao_sel))
                for rot, val, desc in pendentes
            ]
            seletor = discord.ui.Select(placeholder=f"Intenções aguardando ({len(pendentes)})", options=opcoes, row=1)
            seletor.callback = functools.partial(self._escolheu_intencao, seletor)
            self.add_item(seletor)
        if partes:
            opcoes = [
                discord.SelectOption(
                    label=f"{i}. {p['name']}"[:100], value=str(p["id"]), default=p["id"] == self.participante_sel,
                    description=f"iniciativa {p['initiative']}" + (" · NPC" if p["kind"] == "npc" else ""),
                )
                for i, p in enumerate(partes, 1)
            ]
            seletor = discord.ui.Select(placeholder="Editar ou remover alguém", options=opcoes, row=2)
            seletor.callback = functools.partial(self._escolheu_participante, seletor)
            self.add_item(seletor)

        if self.intencao_sel is not None:
            for rotulo, emoji, estilo, acao in (
                ("Permitir", "✅", discord.ButtonStyle.success, self._permitir),
                ("Negar", "❌", discord.ButtonStyle.danger, self._negar),
            ):
                botao = discord.ui.Button(label=rotulo, emoji=emoji, style=estilo, row=3)
                botao.callback = acao
                self.add_item(botao)
        elif self.participante_sel is not None:
            for rotulo, emoji, estilo, acao in (
                ("Iniciativa", "✏️", discord.ButtonStyle.secondary, self._editar),
                ("Remover", "🗑", discord.ButtonStyle.danger, self._remover),
            ):
                botao = discord.ui.Button(label=rotulo, emoji=emoji, style=estilo, row=3)
                botao.callback = acao
                self.add_item(botao)

    async def _redesenhar(self, interaction: discord.Interaction, coletor: Coletor | None = None) -> None:
        self._montar()
        await entregar(interaction, coletor or Coletor(interaction), self.embed(), self)

    async def _e_atualizar_quadro(self, interaction: discord.Interaction) -> None:
        c = self.cena()
        if c is not None:
            await atualizar_quadro(interaction.channel, c["id"])

    # ---- cena ----
    async def _iniciar(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ModalCena(self))

    async def _encerrar(self, interaction: discord.Interaction) -> None:
        confirmar = ConfirmarEncerrar(self.dono_id, self.channel_id)
        self.passar_pra(confirmar)
        await interaction.response.edit_message(embed=confirmar.embed(), view=confirmar)

    async def _atualizar(self, interaction: discord.Interaction) -> None:
        await self._redesenhar(interaction)

    async def _mostrar(self, interaction: discord.Interaction) -> None:
        coletor = Coletor(interaction)
        c = self.cena()
        if c is None:
            coletor.avisar("Essa cena já foi encerrada.")
        else:
            resultado = await mostrar_quadro(interaction.channel, c["id"])
            coletor.avisar({
                "postado": "📢 Quadro da iniciativa postado no canal. Ele se atualiza sozinho a cada mudança.",
                "atualizado": "📢 Quadro atualizado.",
                "erro": "Não consegui postar o quadro aqui. Confere se o bot pode ver e escrever neste canal.",
            }[resultado])
        await self._redesenhar(interaction, coletor)

    # ---- a vez ----
    async def _proximo(self, interaction: discord.Interaction) -> None:
        coletor = Coletor(interaction)
        c = self.cena()
        if c is None:
            coletor.avisar("Essa cena já foi encerrada.")
            await self._redesenhar(interaction, coletor)
            return
        evento, participante, _ = cena.proximo_turno(c["id"])
        if evento == "vazio":
            coletor.avisar("Ninguém entrou na iniciativa ainda. Os jogadores entram com `/iniciativa`, e você põe NPCs no botão ➕.")
        else:
            texto, permitidas = cena.mensagem_da_vez(c["id"], evento, participante)
            coletor.mensagens.append((texto, {"allowed_mentions": permitidas} if permitidas else {}))
        await self._redesenhar(interaction, coletor)
        await self._e_atualizar_quadro(interaction)

    # ---- NPC ----
    async def _npc(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ModalNpc(self))

    # ---- intenções ----
    async def _escolheu_intencao(self, seletor: discord.ui.Select, interaction: discord.Interaction) -> None:
        self.intencao_sel = int(seletor.values[0])
        self.participante_sel = None
        await self._redesenhar(interaction)

    async def _permitir(self, interaction: discord.Interaction) -> None:
        await self.decidir(interaction, self.intencao_sel, "permitida", None)

    async def _negar(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ModalNegar(self, self.intencao_sel))

    async def decidir(self, interaction: discord.Interaction, intencao_id: int | None, status: str, nota: str | None) -> None:
        """Permite ou nega (chamado pelo botão Permitir e pelo formulário do Negar)."""
        coletor = Coletor(interaction)
        intencao = db.get_intention_by_id(intencao_id) if intencao_id is not None else None
        dono = db.get_participant(intencao["participant_id"]) if intencao else None
        if intencao is None or dono is None or not db.decide_intention(intencao_id, status, nota, str(interaction.user.id)):
            coletor.avisar("Essa intenção já foi decidida (ou saiu da cena). Atualizei a tela.")
        elif status == "permitida":
            coletor.avisar(f"✅ Intenção de **{dono['name']}** permitida.")
        elif nota:
            coletor.avisar(f"❌ Intenção de **{dono['name']}** negada: {nota.rstrip('.')}. O jogador vê o motivo em 👁 Minha intenção.")
        else:
            coletor.avisar(f"❌ Intenção de **{dono['name']}** negada.")
        self.intencao_sel = None
        await self._redesenhar(interaction, coletor)
        await self._e_atualizar_quadro(interaction)

    # ---- participantes ----
    async def _escolheu_participante(self, seletor: discord.ui.Select, interaction: discord.Interaction) -> None:
        self.participante_sel = int(seletor.values[0])
        self.intencao_sel = None
        await self._redesenhar(interaction)

    async def _editar(self, interaction: discord.Interaction) -> None:
        participante = db.get_participant(self.participante_sel) if self.participante_sel is not None else None
        if participante is None:
            coletor = Coletor(interaction)
            coletor.avisar("Esse participante já saiu da cena.")
            await self._redesenhar(interaction, coletor)
            return
        await interaction.response.send_modal(ModalIniciativa(self, participante))

    async def _remover(self, interaction: discord.Interaction) -> None:
        coletor = Coletor(interaction)
        c = self.cena()
        r = cena.remover_participante(c, self.participante_sel) if c and self.participante_sel is not None else None
        coletor.avisar(r.texto if r else "Esse participante já saiu da cena.")
        self.participante_sel = None
        await self._redesenhar(interaction, coletor)
        await self._e_atualizar_quadro(interaction)


class ConfirmarEncerrar(_SoMestre):
    def __init__(self, dono_id: int, channel_id: str):
        super().__init__(dono_id)
        self.channel_id = channel_id
        confirmar = discord.ui.Button(label="Encerrar a cena", emoji="⛔", style=discord.ButtonStyle.danger, row=0)
        confirmar.callback = self._confirmar
        voltar = discord.ui.Button(label="Voltar", emoji="⬅️", style=discord.ButtonStyle.secondary, row=0)
        voltar.callback = self._voltar
        self.add_item(confirmar)
        self.add_item(voltar)

    def embed(self) -> discord.Embed:
        c = db.get_active_scene(self.channel_id)
        nome = c["name"] if c else "a cena"
        return discord.Embed(
            title=f"⛔ Encerrar {nome}?",
            description=(
                "O quadro do canal fica só como registro (sem os botões) e os jogadores não conseguem mais mandar "
                "intenção nem entrar na iniciativa. Uma cena nova começa do zero."
            ),
            color=discord.Color.orange(),
        )

    async def _voltar(self, interaction: discord.Interaction) -> None:
        escudo = EscudoDoMestre(self.dono_id, self.channel_id)
        self.passar_pra(escudo)
        await interaction.response.edit_message(embed=escudo.embed(), view=escudo)

    async def _confirmar(self, interaction: discord.Interaction) -> None:
        coletor = Coletor(interaction)
        c = db.get_active_scene(self.channel_id)
        if c is None:
            coletor.avisar("Essa cena já tinha sido encerrada.")
        else:
            db.end_scene(c["id"])
            await atualizar_quadro(interaction.channel, c["id"])
            coletor.avisar(f"⛔ Cena **{c['name']}** encerrada.")
        escudo = EscudoDoMestre(self.dono_id, self.channel_id)
        self.passar_pra(escudo)
        await entregar(interaction, coletor, escudo.embed(), escudo)


# ---------------------------------------------------------------------------
# Formulários do Escudo
# ---------------------------------------------------------------------------
class _Formulario(discord.ui.Modal):
    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await _avisar_erro(interaction, error)


class ModalCena(_Formulario):
    def __init__(self, escudo: EscudoDoMestre):
        super().__init__(title="Nova cena", timeout=TEMPO_DO_PAINEL)
        self.escudo = escudo
        self.campo = discord.ui.TextInput(label="Nome da cena", required=True, max_length=60, placeholder="ex: Motim na praça")
        self.add_item(self.campo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        nome = " ".join(self.campo.value.split()) or "Cena"
        nova = db.create_scene(
            str(interaction.guild_id) if interaction.guild_id else None, self.escudo.channel_id, nome, str(interaction.user.id)
        )
        coletor = Coletor(interaction)
        if nova is None:
            coletor.avisar("Já tem uma cena aberta neste canal. Encerra a atual antes.")
        else:
            coletor.avisar(
                f"⚔️ Cena **{nome}** aberta. Aperta 📢 Mostrar iniciativa pra postar o quadro no canal; os jogadores "
                "entram com `/iniciativa` (ou pelo botão do quadro) e mandam a intenção com `/intencao`."
            )
        await self.escudo._redesenhar(interaction, coletor)


class ModalNpc(_Formulario):
    def __init__(self, escudo: EscudoDoMestre):
        super().__init__(title="NPC na cena", timeout=TEMPO_DO_PAINEL)
        self.escudo = escudo
        self.nome = discord.ui.TextInput(label="Nome", required=True, max_length=cena.TAMANHO_MAX_NOME, placeholder="ex: Guarda")
        self.iniciativa = discord.ui.TextInput(label="Iniciativa (número ou rolagem)", required=True, max_length=12, placeholder="12 ou 1d20+3")
        self.add_item(self.nome)
        self.add_item(self.iniciativa)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        coletor = Coletor(interaction)
        c = self.escudo.cena()
        r = cena.adicionar_npc(c, self.nome.value, self.iniciativa.value) if c else cena.Resultado(False, "Essa cena já foi encerrada.")
        coletor.avisar(r.texto)
        await self.escudo._redesenhar(interaction, coletor)
        if r.mudou:
            await self.escudo._e_atualizar_quadro(interaction)


class ModalIniciativa(_Formulario):
    def __init__(self, escudo: EscudoDoMestre, participante):
        super().__init__(title=f"Iniciativa de {participante['name']}"[:45], timeout=TEMPO_DO_PAINEL)
        self.escudo = escudo
        self.participante_id = participante["id"]
        self.campo = discord.ui.TextInput(
            label="Iniciativa (número ou rolagem)", required=True, max_length=12, default=str(participante["initiative"])
        )
        self.add_item(self.campo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        coletor = Coletor(interaction)
        r = cena.mudar_iniciativa(self.participante_id, self.campo.value)
        coletor.avisar(r.texto)
        await self.escudo._redesenhar(interaction, coletor)
        if r.mudou:
            await self.escudo._e_atualizar_quadro(interaction)


class ModalNegar(_Formulario):
    def __init__(self, escudo: EscudoDoMestre, intencao_id: int | None):
        super().__init__(title="Negar a intenção", timeout=TEMPO_DO_PAINEL)
        self.escudo = escudo
        self.intencao_id = intencao_id
        self.campo = discord.ui.TextInput(
            label="Motivo (opcional, o jogador vê)", required=False, max_length=cena.TAMANHO_MAX_MOTIVO,
            placeholder="ex: tem um guarda na janela",
        )
        self.add_item(self.campo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        nota = " ".join(self.campo.value.split()) or None
        await self.escudo.decidir(interaction, self.intencao_id, "negada", nota)
