"""A mesa dos mestres: o painel do mestre e os NPCs e criaturas (telas com botões, só pra quem é mestre)."""

import functools

import discord

import ajuda
import db
import escudo
import npcs
import rules
import vitrine
from escudo import _Formulario, _SoMestre
from paineis import Coletor, TEMPO_DO_PAINEL, entregar

_ICONE_DO_TIPO = {"npc": "🧑", "criatura": "🐺"}
_SEM_NPC = "Esse NPC não existe mais. Volta pra lista."
_CICLO_DE_ATRIBUTO = (None,) + rules.ATTRIBUTES
_PROXIMO_MODO = {"normal": "vantagem", "vantagem": "desvantagem", "desvantagem": "normal"}


def _embed_de_ajuda(dados: dict) -> discord.Embed:
    embed = vitrine.tela(title=dados["titulo"], description=dados["descricao"], color=discord.Color.dark_gold())
    for nome, valor in dados["campos"]:
        embed.add_field(name=nome, value=valor, inline=False)
    return embed


# ---------------------------------------------------------------------------
# O painel do mestre: onde está cada ferramenta
# ---------------------------------------------------------------------------
class PainelDoMestre(_SoMestre):
    def __init__(self, dono_id: int):
        super().__init__(dono_id)
        for rotulo, emoji, acao in (
            ("Habilidades", "📜", self._habilidades), ("NPCs e criaturas", "🐺", self._npcs), ("Ajuda do mestre", "📖", self._ajuda),
        ):
            botao = discord.ui.Button(label=rotulo, emoji=emoji, style=discord.ButtonStyle.primary, row=0)
            botao.callback = acao
            self.add_item(botao)

    def embed(self) -> discord.Embed:
        return vitrine.embed_painel_do_mestre()

    async def _ir(self, interaction: discord.Interaction, nova, embed: discord.Embed) -> None:
        self.passar_pra(nova)
        await interaction.response.edit_message(embed=embed, view=nova)

    async def _habilidades(self, interaction: discord.Interaction) -> None:
        fila = escudo.FilaDeHabilidades(self.dono_id)
        await self._ir(interaction, fila, fila.embed())

    async def _npcs(self, interaction: discord.Interaction) -> None:
        livro = LivroDeNpcs(self.dono_id)
        await self._ir(interaction, livro, livro.embed())

    async def _ajuda(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=_embed_de_ajuda(ajuda.visao_mestre()), ephemeral=True)


# ---------------------------------------------------------------------------
# O livro de NPCs e criaturas
# ---------------------------------------------------------------------------
class LivroDeNpcs(_SoMestre):
    def __init__(self, dono_id: int):
        super().__init__(dono_id)
        self._montar()

    def _linhas(self) -> list:
        return [(n, npcs.recursos(n), db.get_npc_lost(n["id"])) for n in db.list_npcs()]

    def embed(self) -> discord.Embed:
        return vitrine.embed_livro_de_npcs(self._linhas())

    def _montar(self) -> None:
        self.clear_items()
        lista = db.list_npcs()
        if lista:
            opcoes = [
                discord.SelectOption(
                    label=n["name"][:100], value=str(n["id"]), emoji=_ICONE_DO_TIPO[n["kind"]],
                    description=f"{rules.NPC_KIND_LABELS[n['kind']]} · nível {n['level']}",
                )
                for n in lista
            ]
            seletor = discord.ui.Select(placeholder="Escolhe um pra abrir a ficha", options=opcoes, row=0)
            seletor.callback = functools.partial(self._abrir, seletor)
            self.add_item(seletor)
        for tipo, rotulo in (("npc", "Novo NPC"), ("criatura", "Nova criatura")):
            botao = discord.ui.Button(label=rotulo, emoji=_ICONE_DO_TIPO[tipo], style=discord.ButtonStyle.success, row=1)
            botao.callback = functools.partial(self._novo, tipo)
            self.add_item(botao)
        painel = discord.ui.Button(label="Painel do mestre", emoji="🛡️", style=discord.ButtonStyle.secondary, row=1)
        painel.callback = self._painel
        self.add_item(painel)

    async def _abrir(self, seletor: discord.ui.Select, interaction: discord.Interaction) -> None:
        await self.abrir_ficha(interaction, int(seletor.values[0]))

    async def abrir_ficha(self, interaction: discord.Interaction, npc_id: int) -> None:
        if db.get_npc(npc_id) is None:
            self._montar()
            await interaction.response.edit_message(embed=self.embed(), view=self)
            return
        ficha = PainelNpc(self.dono_id, npc_id)
        self.passar_pra(ficha)
        await interaction.response.edit_message(embed=ficha.embed(), view=ficha)

    async def _novo(self, tipo: str, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ModalNovoNpc(self, tipo))

    async def _painel(self, interaction: discord.Interaction) -> None:
        painel = PainelDoMestre(self.dono_id)
        self.passar_pra(painel)
        await interaction.response.edit_message(embed=painel.embed(), view=painel)


class ModalNovoNpc(_Formulario):
    """Nome, modelo de partida, nível e espécie: o resto o mestre ajusta na ficha."""

    def __init__(self, livro: LivroDeNpcs, tipo: str):
        super().__init__(title="Novo NPC" if tipo == "npc" else "Nova criatura", timeout=TEMPO_DO_PAINEL)
        self.livro = livro
        self.tipo = tipo
        self.nome = discord.ui.TextInput(label="Nome", required=True, max_length=rules.NPC_NAME_MAX, placeholder="ex: Capitão Dubois")
        self.modelo = discord.ui.TextInput(
            label="Modelo de partida", required=False, max_length=12, default="Soldado",
            placeholder="Ralé, Soldado, Veterano, Elite, Chefe ou Lenda",
        )
        self.nivel = discord.ui.TextInput(label="Nível (1 a 10, vazio = o do modelo)", required=False, max_length=2)
        self.especie = discord.ui.TextInput(label="Espécie (opcional)", required=False, max_length=rules.NPC_SPECIES_MAX, placeholder="ex: Humano, Demônio")
        for campo in (self.nome, self.modelo, self.nivel, self.especie):
            self.add_item(campo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        modelo, erro = npcs.achar_modelo(self.modelo.value)
        nivel = None
        if not erro and self.nivel.value.strip():
            nivel, erro = npcs.ler_inteiro(self.nivel.value, 1, rules.MAX_LEVEL, "Nível")
        if not erro and not self.nome.value.strip():
            erro = "Dá um nome ao NPC."
        if erro:
            await interaction.response.send_message(erro, ephemeral=True)
            return
        npc_id = npcs.criar_do_modelo(str(interaction.user.id), self.nome.value.strip(), modelo, self.tipo, self.especie.value.strip())
        if nivel:
            db.update_npc(npc_id, level=nivel)
        await self.livro.abrir_ficha(interaction, npc_id)


# ---------------------------------------------------------------------------
# A ficha de um NPC: barras, atributos, perícias, notas
# ---------------------------------------------------------------------------
class PainelNpc(_SoMestre):
    def __init__(self, dono_id: int, npc_id: int, selecionado: str = "vida"):
        super().__init__(dono_id)
        self.npc_id = npc_id
        self.selecionado = selecionado if selecionado in rules.VITAL_KEYS else "vida"
        self._montar()

    def npc(self):
        return db.get_npc(self.npc_id)

    def embed(self) -> discord.Embed:
        r = npcs.resumo(self.npc_id) if self.npc() else None
        if r is None:
            return vitrine.embed_decorado("NPC apagado", None, _SEM_NPC, discord.Color.dark_grey())
        return vitrine.embed_npc(r["npc"], r["recursos"], r["perdidos"], r["pericias"], self.selecionado)

    def _montar(self) -> None:
        self.clear_items()
        if self.npc() is None:
            lista = discord.ui.Button(label="Lista", emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
            lista.callback = self._lista
            self.add_item(lista)
            return
        r = npcs.resumo(self.npc_id)
        opcoes = [
            discord.SelectOption(
                label=rules.VITAL_LABELS[k], value=k, emoji=rules.VITAL_EMOJI[k], default=k == self.selecionado,
                description=f"{rules.vital_current(r['recursos'][k]['total'], r['perdidos'][k])}/{r['recursos'][k]['total']}",
            )
            for k in rules.VITAL_KEYS
        ]
        seletor = discord.ui.Select(placeholder="Escolhe a barra", options=opcoes, row=0)
        seletor.callback = functools.partial(self._escolheu, seletor)
        self.add_item(seletor)
        for delta, linha in ((-10, 1), (-5, 1), (-1, 1), (1, 1), (5, 1), (10, 2)):
            botao = discord.ui.Button(label=f"{delta:+d}", row=linha, style=discord.ButtonStyle.danger if delta < 0 else discord.ButtonStyle.success)
            botao.callback = functools.partial(self._mudar, delta)
            self.add_item(botao)
        for rotulo, emoji, linha, acao in (
            ("Valor exato", "✏️", 2, self._valor_exato), ("Restaurar", "♻️", 2, self._restaurar), ("Bônus", "📈", 2, self._bonus), ("Rolar", "🎲", 2, self._rolar),
            ("Dados", "🪪", 3, self._dados), ("Atributos", "🧬", 3, self._atributos), ("Perícias", "🎯", 3, self._pericias), ("Notas", "📝", 3, self._notas),
            ("Apagar", "🗑", 3, self._apagar), ("Lista", "◀️", 4, self._lista), ("No canal", "📣", 4, self._no_canal),
        ):
            estilo = discord.ButtonStyle.danger if rotulo == "Apagar" else discord.ButtonStyle.primary if rotulo == "Rolar" else discord.ButtonStyle.secondary
            botao = discord.ui.Button(label=rotulo, emoji=emoji, style=estilo, row=linha)
            botao.callback = acao
            self.add_item(botao)

    async def _redesenhar(self, interaction: discord.Interaction, coletor: Coletor | None = None) -> None:
        self._montar()
        await entregar(interaction, coletor or Coletor(interaction), self.embed(), self)

    async def _escolheu(self, seletor: discord.ui.Select, interaction: discord.Interaction) -> None:
        if seletor.values[0] in rules.VITAL_KEYS:
            self.selecionado = seletor.values[0]
        await self._redesenhar(interaction)

    async def _mudar(self, delta: int, interaction: discord.Interaction) -> None:
        if self.npc() is not None:
            npcs.ajustar(self.npc_id, self.selecionado, delta)
        await self._redesenhar(interaction)

    async def _valor_exato(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ModalValorExatoNpc(self))

    async def aplicar_valor(self, interaction: discord.Interaction, valor: int) -> None:
        if self.npc() is not None:
            npcs.definir(self.npc_id, self.selecionado, valor)
        await self._redesenhar(interaction)

    async def _restaurar(self, interaction: discord.Interaction) -> None:
        if self.npc() is not None:
            npcs.restaurar(self.npc_id)
        await self._redesenhar(interaction)

    async def _bonus(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ModalBonusDoNpc(self))

    async def _dados(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ModalDadosDoNpc(self))

    async def _atributos(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ModalAtributosDoNpc(self))

    async def _pericias(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ModalPericiasDoNpc(self))

    async def _notas(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ModalNotasDoNpc(self))

    async def _rolar(self, interaction: discord.Interaction) -> None:
        rolagem = RolagemDoNpc(self.dono_id, self.npc_id)
        self.passar_pra(rolagem)
        await interaction.response.edit_message(embed=rolagem.embed(), view=rolagem)

    async def _apagar(self, interaction: discord.Interaction) -> None:
        confirmar = ConfirmarApagarNpc(self.dono_id, self.npc_id)
        self.passar_pra(confirmar)
        await interaction.response.edit_message(embed=confirmar.embed(), view=confirmar)

    async def _lista(self, interaction: discord.Interaction) -> None:
        livro = LivroDeNpcs(self.dono_id)
        self.passar_pra(livro)
        await interaction.response.edit_message(embed=livro.embed(), view=livro)

    async def _no_canal(self, interaction: discord.Interaction) -> None:
        """Mostra no canal só o estado da criatura, em palavras (sem número)."""
        if self.npc() is None:
            await self._redesenhar(interaction)
            return
        r = npcs.resumo(self.npc_id)
        await interaction.response.send_message(**vitrine.cartao_estado_do_npc(r["npc"], r["recursos"], r["perdidos"]).kwargs())


# ---------------------------------------------------------------------------
# Os formulários da ficha
# ---------------------------------------------------------------------------
class _FormularioDoNpc(_Formulario):
    def __init__(self, painel: PainelNpc, titulo: str):
        super().__init__(title=titulo, timeout=TEMPO_DO_PAINEL)
        self.painel = painel

    async def _recusar(self, interaction: discord.Interaction, erro: str) -> None:
        await interaction.response.send_message(erro, ephemeral=True)

    async def _salvo(self, interaction: discord.Interaction) -> None:
        await self.painel._redesenhar(interaction)


class ModalValorExatoNpc(_FormularioDoNpc):
    def __init__(self, painel: PainelNpc):
        r = npcs.resumo(painel.npc_id)
        chave = painel.selecionado
        maximo = r["recursos"][chave]["total"]
        super().__init__(painel, f"{rules.VITAL_LABELS[chave]}: valor exato")
        self.campo = discord.ui.TextInput(
            label=f"Quanto de {rules.VITAL_LABELS[chave]} agora? (0 a {maximo})"[:45],
            default=str(rules.vital_current(maximo, r["perdidos"][chave])), max_length=6, required=True,
        )
        self.add_item(self.campo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        texto = self.campo.value.strip()
        if not texto.isdigit():
            await self._recusar(interaction, "Escreve só um número, tipo 12.")
            return
        await self.painel.aplicar_valor(interaction, int(texto))


class ModalBonusDoNpc(_FormularioDoNpc):
    """O bônus manual que soma ao máximo de cada recurso (pode ser negativo). É assim que se aumenta a vida de um NPC."""

    def __init__(self, painel: PainelNpc):
        super().__init__(painel, "Bônus nos recursos")
        npc = painel.npc()
        self.campos = {
            k: discord.ui.TextInput(label=f"Bônus de {rules.VITAL_LABELS[k]} (soma ao máximo)"[:45], required=False, max_length=5, default=str(npc[f"bonus_{k}"]))
            for k in rules.VITAL_KEYS
        }
        for campo in self.campos.values():
            self.add_item(campo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        novos = {}
        for chave, campo in self.campos.items():
            valor, erro = npcs.ler_inteiro(campo.value or "0", rules.NPC_BONUS_MIN, rules.NPC_BONUS_MAX, f"Bônus de {rules.VITAL_LABELS[chave]}")
            if erro:
                await self._recusar(interaction, erro)
                return
            novos[f"bonus_{chave}"] = valor
        db.update_npc(self.painel.npc_id, **novos)
        await self._salvo(interaction)


class ModalDadosDoNpc(_FormularioDoNpc):
    def __init__(self, painel: PainelNpc):
        super().__init__(painel, "Dados do NPC")
        npc = painel.npc()
        self.nome = discord.ui.TextInput(label="Nome", required=True, max_length=rules.NPC_NAME_MAX, default=npc["name"])
        self.tipo = discord.ui.TextInput(label="Tipo (npc ou criatura)", required=True, max_length=8, default=npc["kind"])
        self.nivel = discord.ui.TextInput(label="Nível (1 a 10)", required=True, max_length=2, default=str(npc["level"]))
        self.especie = discord.ui.TextInput(label="Espécie (opcional)", required=False, max_length=rules.NPC_SPECIES_MAX, default=npc["species"] or None)
        self.classes = discord.ui.TextInput(
            label="Classes (até 3, separadas por vírgula)", required=False, max_length=80, default=", ".join(npcs.classes_de(npc)) or None,
            placeholder="ex: Mercenário, Caçador",
        )
        for campo in (self.nome, self.tipo, self.nivel, self.especie, self.classes):
            self.add_item(campo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        tipo = npcs._norm(self.tipo.value)
        tipo = {"npc": "npc", "criatura": "criatura", "monstro": "criatura"}.get(tipo)
        nivel, erro = npcs.ler_inteiro(self.nivel.value, 1, rules.MAX_LEVEL, "Nível")
        classes, erro_classes = npcs.ler_classes(self.classes.value)
        erro = erro or ("Tipo: escreve npc ou criatura." if tipo is None else None) or erro_classes or (None if self.nome.value.strip() else "Dá um nome ao NPC.")
        if erro:
            await self._recusar(interaction, erro)
            return
        db.update_npc(self.painel.npc_id, name=self.nome.value, kind=tipo, level=nivel, species=self.especie.value.strip(), classes=",".join(classes))
        await self._salvo(interaction)


class ModalAtributosDoNpc(_FormularioDoNpc):
    def __init__(self, painel: PainelNpc):
        super().__init__(painel, "Atributos do NPC")
        npc = painel.npc()
        self.campo = discord.ui.TextInput(
            label="Atributos (sem limite, até 99)", style=discord.TextStyle.paragraph, required=True, max_length=200,
            default=", ".join(f"{rules.ATTRIBUTE_LABELS[a]} {npc[a]}" for a in rules.ATTRIBUTES),
        )
        self.add_item(self.campo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        novos, erro = npcs.ler_atributos(self.campo.value, npcs.atributos_de(self.painel.npc()))
        if erro:
            await self._recusar(interaction, erro)
            return
        db.update_npc(self.painel.npc_id, **novos)
        await self._salvo(interaction)


class ModalPericiasDoNpc(_FormularioDoNpc):
    def __init__(self, painel: PainelNpc):
        super().__init__(painel, "Perícias do NPC")
        atuais = db.get_npc_skills(painel.npc_id)
        self.campo = discord.ui.TextInput(
            label="Perícias e pontos (sem limite de 7, até 30)", style=discord.TextStyle.paragraph, required=False, max_length=400,
            default=", ".join(f"{p} {v}" for p, v in atuais.items()) or None, placeholder="ex: Luta 8, Furtividade 5, Percepção 6",
        )
        self.add_item(self.campo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        novas, erro = npcs.ler_pericias(self.campo.value)
        if erro:
            await self._recusar(interaction, erro)
            return
        db.set_npc_skills(self.painel.npc_id, novas)
        await self._salvo(interaction)


class ModalNotasDoNpc(_FormularioDoNpc):
    def __init__(self, painel: PainelNpc):
        super().__init__(painel, "Notas do NPC")
        self.campo = discord.ui.TextInput(
            label="Habilidades, fraquezas, táticas, segredos", style=discord.TextStyle.paragraph, required=False,
            max_length=rules.NPC_NOTES_MAX, default=painel.npc()["notes"] or None,
        )
        self.add_item(self.campo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        db.update_npc(self.painel.npc_id, notes=self.campo.value.strip())
        await self._salvo(interaction)


# ---------------------------------------------------------------------------
# Rolar como o NPC
# ---------------------------------------------------------------------------
class RolagemDoNpc(_SoMestre):
    """Escolhe a perícia e rola 1d20 + atributo + perícia pelo NPC: só pra você, ou no canal."""

    def __init__(self, dono_id: int, npc_id: int, pericia: str = "Luta", modo: str = "normal", atributo: str | None = None):
        super().__init__(dono_id)
        self.npc_id = npc_id
        self.pericia = pericia if pericia in rules.SKILLS else "Luta"
        self.modo = modo if modo in _PROXIMO_MODO else "normal"
        self.atributo = atributo if atributo in rules.ATTRIBUTES else None
        self._montar()

    def embed(self) -> discord.Embed:
        npc = db.get_npc(self.npc_id)
        if npc is None:
            return vitrine.embed_decorado("NPC apagado", None, _SEM_NPC, discord.Color.dark_grey())
        bonus, usado = npcs.modificador(npc, db.get_npc_skills(self.npc_id), self.pericia, self.atributo)
        _, rotulo = vitrine.MODOS_DE_TESTE[self.modo]
        corpo = (
            f"{rules.SKILL_ICONS[self.pericia]} **{self.pericia}** {bonus:+d} · {rules.ATTRIBUTE_LABELS[usado]} + perícia\n\n"
            "**Só eu** mostra o resultado só pra vós. **No canal** mostra pra todos."
        )
        return vitrine.embed_decorado(
            f"{npc['name']} rola", "Escolhei a perícia e rolai pelo NPC.", corpo, discord.Color.dark_red(),
            rodape=f"Modo: {rotulo.lower()} · Atributo: {rules.ATTRIBUTE_LABELS[self.atributo] if self.atributo else 'automático'}",
        )

    def _montar(self) -> None:
        self.clear_items()
        npc = db.get_npc(self.npc_id)
        pericias = db.get_npc_skills(self.npc_id) if npc else {}
        if npc is not None:
            opcoes = [
                discord.SelectOption(
                    label=p, value=p, emoji=rules.SKILL_ICONS[p], default=p == self.pericia,
                    description=f"{npcs.modificador(npc, pericias, p, self.atributo)[0]:+d}",
                )
                for p in rules.SKILLS
            ]
            seletor = discord.ui.Select(placeholder="Escolhe a perícia", options=opcoes, row=0)
            seletor.callback = functools.partial(self._escolheu, seletor)
            self.add_item(seletor)
            for rotulo, emoji, publico in (("Só eu", "🎲", False), ("No canal", "📣", True)):
                botao = discord.ui.Button(label=rotulo, emoji=emoji, style=discord.ButtonStyle.primary, row=1)
                botao.callback = functools.partial(self._lancar, publico)
                self.add_item(botao)
            emoji, rotulo = vitrine.MODOS_DE_TESTE[self.modo]
            modo = discord.ui.Button(label=rotulo, emoji=emoji, style=discord.ButtonStyle.secondary, row=1)
            modo.callback = self._trocar_modo
            atributo = discord.ui.Button(label="Atributo", emoji="🧬", style=discord.ButtonStyle.success if self.atributo else discord.ButtonStyle.secondary, row=1)
            atributo.callback = self._trocar_atributo
            self.add_item(modo)
            self.add_item(atributo)
        ficha = discord.ui.Button(label="Ficha", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
        ficha.callback = self._ficha
        self.add_item(ficha)

    async def _redesenhar(self, interaction: discord.Interaction) -> None:
        self._montar()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def _escolheu(self, seletor: discord.ui.Select, interaction: discord.Interaction) -> None:
        if seletor.values[0] in rules.SKILLS:
            self.pericia = seletor.values[0]
        await self._redesenhar(interaction)

    async def _trocar_modo(self, interaction: discord.Interaction) -> None:
        self.modo = _PROXIMO_MODO[self.modo]
        await self._redesenhar(interaction)

    async def _trocar_atributo(self, interaction: discord.Interaction) -> None:
        self.atributo = _CICLO_DE_ATRIBUTO[(_CICLO_DE_ATRIBUTO.index(self.atributo) + 1) % len(_CICLO_DE_ATRIBUTO)]
        await self._redesenhar(interaction)

    async def _lancar(self, publico: bool, interaction: discord.Interaction) -> None:
        npc = db.get_npc(self.npc_id)
        if npc is None:
            await self._redesenhar(interaction)
            return
        notacao, resultados, marcas, motivo = npcs.lancar(npc, db.get_npc_skills(self.npc_id), self.pericia, self.modo, self.atributo)
        cartao = vitrine.cartao_rolagem(npc["name"], notacao, resultados[0], motivo, str(interaction.user.display_name), True, marcas)
        argumentos = cartao.kwargs()
        if not publico:
            argumentos["ephemeral"] = True
        await interaction.response.send_message(**argumentos)

    async def _ficha(self, interaction: discord.Interaction) -> None:
        ficha = PainelNpc(self.dono_id, self.npc_id)
        self.passar_pra(ficha)
        await interaction.response.edit_message(embed=ficha.embed(), view=ficha)


# ---------------------------------------------------------------------------
# Apagar
# ---------------------------------------------------------------------------
class ConfirmarApagarNpc(_SoMestre):
    def __init__(self, dono_id: int, npc_id: int):
        super().__init__(dono_id)
        self.npc_id = npc_id
        apagar = discord.ui.Button(label="Apagar de vez", emoji="🗑", style=discord.ButtonStyle.danger, row=0)
        apagar.callback = self._apagar
        cancelar = discord.ui.Button(label="Cancelar", style=discord.ButtonStyle.secondary, row=0)
        cancelar.callback = self._cancelar
        self.add_item(apagar)
        self.add_item(cancelar)

    def embed(self) -> discord.Embed:
        npc = db.get_npc(self.npc_id)
        nome = npc["name"] if npc else "este NPC"
        return vitrine.tela(title=f"Excluir {nome}?", description="A ficha, as perícias e a vida atual somem. **Não tem como desfazer.**", color=discord.Color.dark_red())

    async def _apagar(self, interaction: discord.Interaction) -> None:
        db.delete_npc(self.npc_id)
        livro = LivroDeNpcs(self.dono_id)
        self.passar_pra(livro)
        await interaction.response.edit_message(embed=livro.embed(), view=livro)

    async def _cancelar(self, interaction: discord.Interaction) -> None:
        ficha = PainelNpc(self.dono_id, self.npc_id)
        self.passar_pra(ficha)
        await interaction.response.edit_message(embed=ficha.embed(), view=ficha)
