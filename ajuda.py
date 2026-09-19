"""Textos do /ajuda. Aqui não tem nada de Discord: só o texto de cada comando e as funções que
montam as respostas, pra ficar fácil de revisar e de testar.

Regra da casa: todo comando do bot tem uma entrada em AJUDA (tests/test_bot.py confere isso, e também
que os nomes de opção usados nos exemplos existem de verdade)."""

import rules

# Grupos que aparecem no /ajuda geral, na ordem: (id, título do campo)
GRUPOS = [
    ("personagem", "Seu personagem"),
    ("sorteios", "Sorteios de criação"),
    ("jogo", "Jogo (só com a ficha pronta)"),
    ("consulta", "Consultas"),
]

AJUDA = {
    # ------------------------------------------------------------------ personagem
    "personagem criar": {
        "grupo": "personagem",
        "resumo": "cria um personagem novo e já passa a usar ele",
        "uso": "/personagem criar nome:Kairon Flagon",
        "detalhes": (
            "É o primeiro passo de tudo. Cada jogador tem 3 vagas de personagem, e um mestre pode liberar "
            "vagas extras. Depois de criar, faz os três sorteios, escolhe a classe e distribui os atributos. "
            "O passo a passo inteiro aparece em `/ajuda`."
        ),
    },
    "personagem usar": {
        "grupo": "personagem",
        "resumo": "troca o personagem que você está jogando",
        "uso": "/personagem usar nome:Akari Amaya",
        "detalhes": "Os próximos comandos e rolagens passam a valer pra esse personagem. O nome aparece na lista enquanto você digita.",
    },
    "personagem listar": {
        "grupo": "personagem",
        "resumo": "lista os seus personagens e quantas vagas você usa",
        "uso": "/personagem listar",
        "detalhes": "Mostra nível, XP, Rank de magia, raça e Estado de cada um, e marca o que você está usando agora.",
    },
    "personagem excluir": {
        "grupo": "personagem",
        "resumo": "exclui um personagem seu, pra sempre",
        "uso": "/personagem excluir nome:Charles de Flagon",
        "detalhes": (
            "O bot pede confirmação com botões. A ficha, o XP e os ranks somem e não voltam, e a vaga é liberada. "
            "As rolagens antigas continuam no histórico."
        ),
    },
    "minha_ficha": {
        "grupo": "personagem",
        "resumo": "mostra a sua ficha completa",
        "uso": "/minha_ficha personagem:Kairon Flagon",
        "detalhes": (
            "Nível, XP, raça, classe social, Rank de magia, classe, atributos, Vida, Sanidade, Mana, Estamina e ranks "
            "das perícias. Só você vê a resposta. Se a ficha ainda não está pronta, ela diz o que falta."
        ),
        "requisito": "Sempre liberado.",
    },
    "classe": {
        "grupo": "personagem",
        "resumo": "escolhe a classe do personagem",
        "uso": "/classe classe:Caçador",
        "detalhes": (
            "Vale uma vez só; depois, só um mestre muda. Mostra a vantagem em perícias e o bônus de Vida, Sanidade, "
            "Mana e Estamina da classe."
        ),
        "requisito": "Só depois dos três sorteios (raça, Rank de magia e classe social).",
    },
    "atributos": {
        "grupo": "personagem",
        "resumo": "distribui os pontos de atributo",
        "uso": "/atributos forca:2 vitalidade:3 vontade:1",
        "detalhes": (
            "Preenche só o que quer mudar; sem números, mostra como está. São 6 pontos na criação e mais 1 a cada 2 "
            "níveis. Atributo só sobe (pra diminuir, chama um mestre), e o bot confere o total e os limites da raça. "
            "Os pontos que vêm de nível podem passar do limite de criação."
        ),
        "requisito": "Só depois de escolher a classe. A ficha só fica pronta com os 6 pontos da criação distribuídos.",
    },
    # ------------------------------------------------------------------ sorteios
    "raca_inicial": {
        "grupo": "sorteios",
        "resumo": "sorteia a raça (1d100)",
        "uso": "/raca_inicial",
        "detalhes": (
            "De 1 a 85 é Humano, de 86 a 95 Vampiro e de 96 a 100 Dhampir. Vale uma vez por personagem e o resultado "
            "aparece pra todo mundo. Rolou errado? Só um mestre apaga."
        ),
        "requisito": "Passo da criação. Os três sorteios podem ser feitos em qualquer ordem.",
    },
    "magia_inicial": {
        "grupo": "sorteios",
        "resumo": "sorteia o Rank de magia (1d100)",
        "uso": "/magia_inicial",
        "detalhes": (
            "De 1 a 45 é Comum, de 46 a 75 Raro, de 76 a 95 Super Raro, de 96 a 99 Lendário e 100 é Mítico. "
            "Vale uma vez por personagem e o resultado aparece pra todo mundo."
        ),
        "requisito": "Passo da criação. Os três sorteios podem ser feitos em qualquer ordem.",
    },
    "classe_social": {
        "grupo": "sorteios",
        "resumo": "sorteia o Estado social (1d100)",
        "uso": "/classe_social",
        "detalhes": (
            "De 1 a 80 é 3º Estado (povo), de 81 a 91 é 2º (nobreza) e de 92 a 99 é 1º (clero). Quem cai no clero rola "
            "outro 1d100 na hora: até 49 é Baixo Clero, de 50 pra cima é Alto Clero. Se der 100, o bot avisa os mestres "
            "e é um deles que define o seu Estado."
        ),
        "requisito": "Passo da criação. Os três sorteios podem ser feitos em qualquer ordem.",
    },
    # ------------------------------------------------------------------ jogo
    "rolar": {
        "grupo": "jogo",
        "resumo": "rola um dado e guarda no histórico",
        "uso": "/rolar dado:1d20+3 motivo:ataque com a espada",
        "detalhes": (
            "Aceita dado e modificador, tipo 1d20, 2d6+3 ou 1d100-2. O motivo e o personagem são opcionais; sem "
            "personagem, vale o que você está usando. A rolagem sai no nome dele e fica no histórico."
        ),
        "requisito": "Só com a ficha do personagem pronta.",
    },
    "historico": {
        "grupo": "jogo",
        "resumo": "mostra as últimas rolagens de alguém",
        "uso": "/historico usuario:@alguém limite:10 personagem:Akari Amaya",
        "detalhes": (
            "Sem nada, mostra as suas. Dá pra ver as de outra pessoa, filtrar por personagem e escolher quantas "
            "aparecem (até 25). A data e a hora aparecem no seu fuso."
        ),
        "requisito": "Só depois que um dos seus personagens estiver com a ficha pronta.",
    },
    "extrato_xp": {
        "grupo": "jogo",
        "resumo": "mostra de onde veio o XP do personagem",
        "uso": "/extrato_xp personagem:Kairon Flagon",
        "detalhes": "Lista as últimas 10 entradas de XP, com o motivo, o mestre que deu e o horário.",
        "requisito": "Só com a ficha do personagem pronta.",
    },
    "rank": {
        "grupo": "jogo",
        "resumo": "mostra o rank público de XP total",
        "uso": "/rank tipo:jogadores limite:10",
        "detalhes": (
            "Em `personagens` ordena cada personagem pelo XP; em `jogadores`, cada um vale a soma do XP de todos os "
            "seus personagens. É público, e quem tem 0 XP não aparece."
        ),
        "requisito": "Só depois que um dos seus personagens estiver com a ficha pronta.",
    },
    # ------------------------------------------------------------------ consultas
    "niveis": {
        "grupo": "consulta",
        "resumo": "mostra o XP e as vantagens de cada nível",
        "uso": "/niveis personagem:Kairon Flagon",
        "detalhes": (
            "A tabela de 1 a 10, com o XP total de cada nível, o que ele dá e qual é o seu. Pra sair do nível N são "
            "N × 1.000 XP, somados."
        ),
    },
    "calcular_recursos": {
        "grupo": "consulta",
        "resumo": "simula Vida, Sanidade, Mana e Estamina",
        "uso": "/calcular_recursos classe:Caçador vitalidade:3 forca:1 vontade:2 alma:1 nivel:5",
        "detalhes": (
            "Mostra a conta por nível, com o mesmo atributo em todos os níveis. Serve pra testar ideias, tipo \"e se eu "
            "botar mais um ponto em Vitalidade?\". A conta exata, nível a nível, é a da `/minha_ficha`."
        ),
    },
    "ajuda": {
        "grupo": "consulta",
        "resumo": "explica como usar o bot e cada comando",
        "uso": "/ajuda comando:atributos",
        "detalhes": (
            "Sem nada, mostra o seu passo a passo e a lista de comandos. Com `comando:`, explica um comando específico, "
            "com exemplo. Também funciona como `/help`."
        ),
    },
    # ------------------------------------------------------------------ mestres
    "mestre dar_xp": {
        "grupo": "mestre",
        "resumo": "dá XP a um personagem",
        "uso": "/mestre dar_xp usuario:@alguém quantidade:500 motivo:missão na catedral",
        "detalhes": (
            "O XP é por roleplay importante, missão de mestre ou desenvolvimento do personagem, nunca por ação avulsa. "
            "O nível sobe sozinho e o bot avisa o que o personagem ganhou. Número negativo tira XP, pra corrigir um "
            "engano. Tudo fica no extrato do jogador."
        ),
    },
    "mestre upar": {
        "grupo": "mestre",
        "resumo": "dá o XP que falta pro personagem subir de nível",
        "uso": "/mestre upar usuario:@alguém niveis:1 motivo:missão na catedral",
        "detalhes": "Atalho pra subir de nível sem contar o XP. Dá pra subir vários de uma vez (até o 10).",
    },
    "mestre corrigir_nivel": {
        "grupo": "mestre",
        "resumo": "põe o personagem no começo de um nível",
        "uso": "/mestre corrigir_nivel usuario:@alguém nivel:3",
        "detalhes": "Ajusta o XP pro mínimo daquele nível e registra no extrato. Serve pra consertar um erro.",
    },
    "mestre rank_pericia": {
        "grupo": "mestre",
        "resumo": "define o Rank de uma perícia especial",
        "uso": "/mestre rank_pericia usuario:@alguém pericia:Forja rank:3",
        "detalhes": "Ritualismo, Alquimia, Forja, Culinária e Fé vão de 0 a 10. Rank 0 é nenhum Rank.",
    },
    "mestre apagar": {
        "grupo": "mestre",
        "resumo": "apaga uma definição pro jogador rolar de novo",
        "uso": "/mestre apagar usuario:@alguém definicao:Raça",
        "detalhes": (
            "Apaga o Rank de magia, a raça, a classe social ou tudo isso. A rolagem antiga continua no histórico. "
            "Não mexe na classe nem nos atributos. Enquanto o jogador não rolar de novo, a ficha dele volta a ficar "
            "incompleta e os comandos de jogo dele fecham."
        ),
    },
    "mestre corrigir_magia": {
        "grupo": "mestre",
        "resumo": "define o Rank de magia na mão, sem rolar",
        "uso": "/mestre corrigir_magia usuario:@alguém rank:Raro",
        "detalhes": "Aparece na ficha como definido por um mestre.",
    },
    "mestre corrigir_raca": {
        "grupo": "mestre",
        "resumo": "define a raça na mão, sem rolar",
        "uso": "/mestre corrigir_raca usuario:@alguém raca:Dhampir",
        "detalhes": "Aparece na ficha como definido por um mestre.",
    },
    "mestre corrigir_estado": {
        "grupo": "mestre",
        "resumo": "define a classe social na mão, sem rolar",
        "uso": "/mestre corrigir_estado usuario:@alguém estado:2º Estado (Nobreza)",
        "detalhes": "É o jeito de resolver quando o jogador tira 100 no sorteio: o bot não escolhe, e o jogador fica esperando você.",
    },
    "mestre corrigir_classe": {
        "grupo": "mestre",
        "resumo": "define a classe na mão",
        "uso": "/mestre corrigir_classe usuario:@alguém classe:Sábio",
        "detalhes": "Funciona mesmo depois de o jogador já ter escolhido, e mesmo que ele ainda não tenha feito os sorteios.",
    },
    "mestre atributos": {
        "grupo": "mestre",
        "resumo": "define atributos na mão, sem conferir limites",
        "uso": "/mestre atributos usuario:@alguém forca:9 vitalidade:2",
        "detalhes": (
            "Preenche só os que quer mudar. Não confere pontos nem limites, e pode diminuir. Serve pra corrigir erro ou "
            "dar pontos por história. Só mexe nos atributos de agora, não nos níveis que já ficaram pra trás."
        ),
    },
    "mestre ficha": {
        "grupo": "mestre",
        "resumo": "mostra a ficha completa de um personagem",
        "uso": "/mestre ficha usuario:@alguém personagem:Akari Amaya",
        "detalhes": "Só você vê a resposta. Sem `personagem:`, vale o que o jogador está usando.",
    },
    "mestre jogador": {
        "grupo": "mestre",
        "resumo": "mostra os personagens e as vagas de um jogador",
        "uso": "/mestre jogador usuario:@alguém",
        "detalhes": "Quantos personagens a pessoa tem, quantas vagas usa, o XP de cada um e quantos ela já excluiu.",
    },
    "mestre vagas": {
        "grupo": "mestre",
        "resumo": "define as vagas extras de personagem de um jogador",
        "uso": "/mestre vagas usuario:@alguém extras:2",
        "detalhes": "O número é o total de extras, não soma com o que já tinha. Além das 3 normais, o teto é de 10 personagens.",
    },
    "mestre excluir_personagem": {
        "grupo": "mestre",
        "resumo": "exclui pra sempre o personagem de outro jogador",
        "uso": "/mestre excluir_personagem usuario:@alguém personagem:Charles de Flagon",
        "detalhes": "Pede confirmação com botões e avisa o jogador no canal. A vaga é liberada.",
    },
    "mestre exportar": {
        "grupo": "mestre",
        "resumo": "manda uma cópia de segurança do banco de dados",
        "uso": "/mestre exportar",
        "detalhes": "Só você vê a resposta. O arquivo tem os dados de todos os jogadores, então guarda em lugar seguro. Fica registrado.",
    },
}

# Como o /ajuda geral mostra os comandos de mestre (só pra quem é mestre): (rótulo, comandos)
MESTRE_SUBGRUPOS = [
    ("XP e nível", ["dar_xp", "upar", "corrigir_nivel"]),
    ("Ficha", ["ficha", "atributos", "corrigir_classe", "rank_pericia"]),
    ("Sorteios", ["apagar", "corrigir_magia", "corrigir_raca", "corrigir_estado"]),
    ("Jogadores", ["jogador", "vagas", "excluir_personagem", "exportar"]),
]

# Só comandos, em ordem, pra sugerir no autocomplete quando a pessoa ainda não digitou nada.
ORDEM_SUGESTAO = [
    "personagem criar", "raca_inicial", "magia_inicial", "classe_social", "classe", "atributos", "minha_ficha",
    "rolar", "niveis", "rank", "calcular_recursos", "historico", "extrato_xp", "personagem usar",
    "personagem listar", "personagem excluir", "ajuda",
]


# ---------------------------------------------------------------------------
# Passo a passo da criação
# ---------------------------------------------------------------------------
def _depois(passo_id: str, status: dict) -> str:
    faltam = rules.creation_missing_before(passo_id, status)
    partes = []
    if any(x in faltam for x in ("raca", "magia", "estado")):
        partes.append("dos sorteios")
    if "classe" in faltam:
        partes.append("de escolher a classe")
    return "depois " + " e ".join(partes)


def linhas_passo_a_passo(status: dict) -> list[str]:
    """Um item por passo: ✅ feito, ▶️ próximo, ⬜ liberado, ⏳ com o mestre, 🔒 ainda fechado."""
    proximo = rules.creation_next_step(status)
    linhas = ["✅ Personagem criado"]
    for passo in rules.CREATION_STEPS:
        pid = passo["id"]
        if status[pid]:
            linhas.append(f"✅ {passo['rotulo']}")
        elif pid == "estado" and status["aguardando_mestre"]:
            linhas.append("⏳ Classe social: você tirou 100, então um mestre vai definir o seu Estado")
        elif rules.creation_missing_before(pid, status):
            linhas.append(f"🔒 {passo['rotulo']}: {_depois(pid, status)}")
        else:
            marca = "▶️" if pid == proximo else "⬜"
            extra = ""
            if pid == "atributos":
                extra = f" ({status['pontos_usados']} de {rules.CREATION_ATTRIBUTE_POINTS} pontos usados)"
            linhas.append(f"{marca} {passo['rotulo']}: `{passo['comando']}`{extra}")
    return linhas


def proximo_passo(status: dict) -> str:
    proximo = rules.creation_next_step(status)
    if proximo is None:
        return "A ficha está pronta e tudo está liberado."
    if proximo == "estado" and status["aguardando_mestre"]:
        return "Agora é com um mestre: fala com ele pra definir o seu Estado, e aí você segue."
    passo = next(p for p in rules.CREATION_STEPS if p["id"] == proximo)
    dica = " (os três sorteios podem ser feitos em qualquer ordem)" if proximo in ("raca", "magia", "estado") else ""
    return f"Próximo passo: `{passo['comando']}`, pra {passo['rotulo'][0].lower() + passo['rotulo'][1:]}{dica}."


def texto_bloqueio(nome: str, status: dict) -> str:
    """Resposta de quando um comando de jogo é usado com a ficha ainda incompleta."""
    return (
        f"🔒 A ficha de **{nome}** ainda não está pronta, e esse comando só abre quando ela estiver.\n\n"
        + "\n".join(linhas_passo_a_passo(status))
        + f"\n\n{proximo_passo(status)}\nSe quiser ver como cada coisa funciona, use `/ajuda`."
    )


def texto_falta_para(passo_id: str, status: dict) -> str:
    """Resposta de quando um passo da criação é tentado antes dos que ele exige."""
    passo = next(p for p in rules.CREATION_STEPS if p["id"] == passo_id)
    faltam = rules.creation_missing_before(passo_id, status)
    if status["aguardando_mestre"] and set(faltam) <= {"estado"}:
        return (
            f"Ainda não dá pra usar `{passo['comando']}`: você tirou 100 no sorteio da classe social, então um mestre "
            "precisa definir o seu Estado primeiro. Fala com ele."
        )
    return (
        f"Ainda não dá pra usar `{passo['comando']}`: a criação tem uma ordem e ainda faltam passos antes.\n\n"
        + "\n".join(linhas_passo_a_passo(status))
        + f"\n\n{proximo_passo(status)}"
    )


# ---------------------------------------------------------------------------
# /ajuda
# ---------------------------------------------------------------------------
def _normalizar(texto: str) -> str:
    return " ".join(texto.strip().lstrip("/").casefold().split())


def achar(texto: str) -> tuple[str | None, list[str]]:
    """Acha a entrada de ajuda pelo que a pessoa digitou. Devolve (chave, sugestões).
    Aceita o nome completo ('mestre dar_xp'), só o final ('dar_xp') ou um pedaço, se só um combinar.
    Se o texto casa com comandos de jogador, eles têm preferência (a não ser que a pessoa escreva 'mestre')."""
    t = _normalizar(texto)
    if not t:
        return None, []
    if t in AJUDA:
        return t, []
    final = [k for k in AJUDA if k.split(" ")[-1] == t]
    candidatos = final + [k for k in AJUDA if t in k and k not in final]
    jogo = [k for k in candidatos if not k.startswith("mestre ")]
    escolhidos = jogo if jogo and "mestre" not in t else candidatos
    if len(escolhidos) == 1:
        return escolhidos[0], []
    exatos = [k for k in escolhidos if k.split(" ")[-1] == t]
    if len(exatos) == 1:
        return exatos[0], []
    return None, escolhidos[:5]


def sugestoes(texto: str, incluir_mestre: bool) -> list[str]:
    """Nomes de comando pro autocomplete (até 25)."""
    t = _normalizar(texto)
    nomes = [k for k in ORDEM_SUGESTAO + sorted(k for k in AJUDA if k not in ORDEM_SUGESTAO)
             if incluir_mestre or not k.startswith("mestre ")]
    if not t:
        return nomes[:25]
    return [k for k in nomes if t in k][:25]


def detalhe(chave: str) -> dict:
    """Título, descrição e campos da ajuda de um comando."""
    e = AJUDA[chave]
    campos = [("Como usar", f"`{e['uso']}`")]
    if e.get("requisito"):
        campos.append(("Quando dá pra usar", e["requisito"]))
    if chave.startswith("mestre "):
        campos.append(("Quem usa", "Só quem tem o cargo de mestre ou a permissão de Gerenciar Servidor."))
    return {
        "titulo": f"📖 /{chave}",
        "descricao": f"{e['resumo'][0].upper()}{e['resumo'][1:]}.\n\n{e['detalhes']}",
        "campos": campos,
    }


def visao_geral(status: dict | None, tem_personagem: bool, mestre: bool) -> dict:
    """O /ajuda sem nada: o passo a passo de quem está usando e a lista de comandos.
    'status' é o creation_status do personagem em uso (None se não tem personagem)."""
    if not tem_personagem:
        passo = ["Você ainda não tem personagem. Começa por `/personagem criar`, e depois é só seguir o passo a passo."]
    elif status["pronta"]:
        passo = ["✅ Ficha pronta. Todos os comandos estão liberados."]
    else:
        passo = linhas_passo_a_passo(status) + ["", proximo_passo(status)]
    campos = [("Seu passo a passo", "\n".join(passo))]
    for gid, titulo in GRUPOS:
        linhas = [f"`/{k}` {e['resumo']}" for k, e in AJUDA.items() if e["grupo"] == gid]
        campos.append((titulo, "\n".join(linhas)))
    if mestre:
        linhas = [
            f"**{rotulo}:** " + ", ".join(f"`/mestre {c}`" for c in cmds) for rotulo, cmds in MESTRE_SUBGRUPOS
        ]
        campos.append(("Comandos de mestre", "\n".join(linhas)))
    return {
        "titulo": "📖 Ajuda do bot",
        "descricao": (
            "É só digitar `/` e escolher o comando. Pra ver como usar um deles, com exemplo, usa "
            "`/ajuda comando:nome`, tipo `/ajuda comando:atributos`."
        ),
        "campos": campos,
    }
