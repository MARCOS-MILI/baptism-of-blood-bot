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
            "vagas extras. Depois de criar, sorteia a raça e a classe social, escolhe a classe, sorteia o Rank de "
            "magia (só quem tem magia) e distribui os atributos. O passo a passo inteiro aparece em `/ajuda`. A "
            "mensagem de boas-vindas já vem com botões pra fazer tudo isso só clicando."
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
        "resumo": "mostra a sua ficha completa, com botões",
        "uso": "/minha_ficha personagem:Kairon Flagon",
        "detalhes": (
            "Nível, XP, raça, classe social, Rank de magia, classe, atributos, Vida, Sanidade, Mana, Estamina e ranks "
            "das perícias. Só você vê a resposta. Se a ficha ainda não está pronta, ela diz o que falta. Embaixo tem "
            "botões pra você não precisar digitar comando: sortear a raça, a classe social e a magia, escolher a "
            "classe (com menu e confirmação), distribuir os atributos (num formulário), abrir a bandeja de dados, "
            "ver os níveis e a ajuda, e trocar de personagem. O botão de um passo que ainda não abriu fica trancado 🔒, "
            "e o painel se atualiza sozinho a cada clique."
        ),
        "requisito": "Sempre liberado.",
    },
    "classe": {
        "grupo": "personagem",
        "resumo": "escolhe a classe do personagem",
        "uso": "/classe classe:Caçador",
        "detalhes": (
            "São oito classes. Vale uma vez só; depois, só um mestre muda. Mostra o texto da classe, a vantagem em "
            "perícias, o bônus de Vida, Sanidade, Mana e Estamina e a habilidade inicial dela (ainda em rascunho, os "
            "números vão mudar). O Clérigo e o Ladrão têm duas habilidades: você escolhe a sua junto com a classe, "
            "nos botões do menu da ficha (ou com `habilidade:` no comando)."
        ),
        "requisito": "Só depois de sortear a raça e a classe social.",
    },
    "habilidade": {
        "grupo": "personagem",
        "resumo": "mostra a habilidade da sua classe, ou escolhe uma das duas",
        "uso": "/habilidade escolha:Bênção",
        "detalhes": (
            "Toda classe tem uma habilidade inicial, e o comando mostra o texto dela. Só o Clérigo (Mãos que Curam ou "
            "Bênção) e o Ladrão (Mão Leve ou Língua de Prata) oferecem duas. Normalmente você escolhe junto com a "
            "classe; se faltou, o comando mostra botões pra escolher (ou o botão Habilidade da ficha). A escolha vale "
            "uma vez e fica na ficha; só um mestre muda. A habilidade se soma à Habilidade Própria que você cria com o mestre. O bot mostra o "
            "texto; quem usa e cobra o custo (Estamina ou Mana) é a mesa."
        ),
        "requisito": "Precisa ter escolhido a classe.",
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
        "requisito": "Só depois de escolher a classe e, se você tiver magia, de sortear o Rank de magia. A ficha só fica pronta com os 6 pontos da criação distribuídos.",
    },
    # ------------------------------------------------------------------ sorteios
    "raca_inicial": {
        "grupo": "sorteios",
        "resumo": "sorteia a raça (1d100)",
        "uso": "/raca_inicial",
        "detalhes": (
            "De 1 a 85 é Humano, de 86 a 95 Vampiro e de 96 a 100 Dhampir. Você tem até 3 chances por personagem: "
            "se rolar de novo, o resultado novo troca o antigo (a última vale), e o bot sempre pergunta antes. As "
            "chances acabam quando você usa as 3 ou quando escolhe a classe. O resultado aparece pra todo mundo. "
            "Rolou errado? Só um mestre apaga e devolve as chances."
        ),
        "requisito": "Passo da criação. A raça e a classe social podem ser sorteadas em qualquer ordem.",
    },
    "classe_social": {
        "grupo": "sorteios",
        "resumo": "sorteia o Estado social (1d100)",
        "uso": "/classe_social",
        "detalhes": (
            "De 1 a 80 é 3º Estado (povo), de 81 a 91 é 2º (nobreza) e de 92 a 99 é 1º (clero). Quem cai no clero rola "
            "outro 1d100 na hora: até 49 é Baixo Clero, de 50 pra cima é Alto Clero. Se der 100, o bot avisa os mestres "
            "e é um deles que define o seu Estado. Você tem até 3 chances por personagem: se rolar de novo, o resultado "
            "novo troca o antigo (a última vale), e o bot sempre pergunta antes. As chances acabam quando você usa as 3 "
            "ou quando escolhe a classe."
        ),
        "requisito": "Passo da criação. A raça e a classe social podem ser sorteadas em qualquer ordem.",
    },
    "magia_inicial": {
        "grupo": "sorteios",
        "resumo": "sorteia o Rank de magia (1d100), só pra quem tem magia",
        "uso": "/magia_inicial",
        "detalhes": (
            "Só tem magia quem é Vampiro ou Dhampir (de qualquer classe) ou das classes Feiticeiros e Mestre de Forja. Quem não "
            "tem não sorteia, e esse passo não vale pra ele. De 1 a 45 é Comum, de 46 a 75 Raro, de 76 a 95 Super Raro, "
            "de 96 a 99 Lendário e 100 é Mítico. Aqui é uma rolagem só por personagem (não tem rolar de novo), e o resultado "
            "aparece pra todo mundo. Se você tem uma habilidade que dá vantagem, combina com um mestre."
        ),
        "requisito": "Só depois de sortear a raça e escolher a classe, e só se a sua raça ou a sua classe tiver magia.",
    },
    # ------------------------------------------------------------------ jogo
    "rolar": {
        "grupo": "jogo",
        "resumo": "rola um dado e guarda no histórico",
        "uso": "/rolar dado:1d20+3 motivo:ataque com a espada",
        "detalhes": (
            "Aceita dado e modificador, tipo 1d20, 2d6+3 ou 1d100-2. Com o # na frente ele rola várias vezes, cada "
            "uma separada: 3#d20+5 rola o d20+5 três vezes (de 1 a 10 vezes) e mostra o maior e o menor, como uma "
            "vantagem que você escolhe. O motivo e o personagem são opcionais; sem personagem, vale o que você está "
            "usando. A rolagem sai no nome dele e fica no histórico. Um mestre pode mexer na sorte de um d20 (o cartão mostra "
            "🍀 quando ele não pede pra esconder)."
        ),
        "requisito": "Só com a ficha do personagem pronta.",
    },
    "dados": {
        "grupo": "jogo",
        "resumo": "abre uma bandeja de dados com botões",
        "uso": "/dados",
        "detalhes": (
            "Uma bandeja só sua: escolhe o dado (d4, d6, d8, d10, d12, d20 ou d100), a quantidade nos botões ➖ e ➕, o "
            "modificador (-5, -1, +1, +5 ou zerar) e, se quiser, o motivo no botão 📝. Aperta Rolar e o resultado sai "
            "no canal pra todo mundo ver, no nome do personagem que você está usando, e fica no histórico. A bandeja "
            "continua aberta pra você rolar de novo. Tem o mesmo botão dentro do `/minha_ficha`."
        ),
        "requisito": "Abrir a bandeja é sempre liberado. Rolar só com a ficha do personagem pronta.",
    },
    "iniciativa": {
        "grupo": "jogo",
        "resumo": "entra na iniciativa da cena do canal",
        "uso": "/iniciativa",
        "detalhes": (
            "Rola 1d20 + Destreza pro personagem que você está usando e te coloca na ordem da cena que um mestre abriu "
            "neste canal. Quem tem Celeridade rola com vantagem (dois d20, fica o maior). É uma vez por cena; se "
            "precisar mudar, pede pra um mestre. Só você vê o resultado, e o quadro da cena mostra a ordem. Tem o "
            "mesmo botão 🎲 no quadro."
        ),
        "requisito": "Precisa de uma cena aberta no canal e da ficha pronta.",
    },
    "intencao": {
        "grupo": "jogo",
        "resumo": "manda pro mestre o que o personagem quer fazer",
        "uso": "/intencao texto:atacar o guarda pela retaguarda",
        "detalhes": (
            "Numa cena com muita gente, em vez de várias mensagens no canal, você escreve numa frase (até 200 letras) o que o "
            "seu personagem quer fazer. Só o mestre lê. Ele permite ou nega, e o quadro mostra 📝 aguardando, ✅ permitida ou "
            "❌ negada. Você age na sua vez, seguindo a iniciativa. É uma por rodada: mandar outra troca a anterior (menos se "
            "já foi permitida). Sem texto, mostra a sua atual e o motivo, se negada. Tem os botões 📝 e 👁 no quadro."
        ),
        "requisito": "Precisa estar na iniciativa da cena do canal (`/iniciativa`).",
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
    "disciplinas": {
        "grupo": "consulta",
        "resumo": "lê o texto das Disciplinas e gasta os pontos (Vampiro e Dhampir)",
        "uso": "/disciplinas",
        "detalhes": (
            "Abre um menu com as dez Disciplinas: Potência, Celeridade, Ofuscação, Presença, Domínio, Vidência, "
            "Proteísmo, Hemomancia, Sanguessugia e Regeneração. Escolhe uma pra ler o texto de cada grau. Quem é "
            "Vampiro ou Dhampir também vê o próprio grau e gasta os pontos no botão Subir: 1 ponto por grau, só "
            "aumenta, e só até o grau 3 (os graus 4 e 5 só um mestre concede). O Vampiro começa com 4 pontos, o "
            "Dhampir com 3, e os dois ganham +1 a cada 2 níveis. A Sanguessugia ainda está em desenvolvimento e não "
            "recebe ponto. O mesmo painel abre no botão Disciplinas do `/minha_ficha`."
        ),
        "requisito": "Qualquer um pode ler. Só Vampiro e Dhampir gastam pontos.",
    },
    "niveis": {
        "grupo": "consulta",
        "resumo": "mostra o XP e as vantagens de cada nível",
        "uso": "/niveis personagem:Kairon Flagon",
        "detalhes": (
            "A tabela de 1 a 10, com o XP total de cada nível, o que ele dá e qual é o seu. Pra sair do nível N são "
            "N × 1.000 XP, somados. O Sábio ganha o dobro de pontos de perícia por nível (+4)."
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
    "mestre escudo": {
        "grupo": "mestre",
        "resumo": "abre o Escudo do Mestre da cena deste canal",
        "uso": "/mestre escudo",
        "detalhes": (
            "A tela privada do mestre pra conduzir uma cena com muita gente. Inicia a cena, mostra a ordem com o texto das "
            "intenções que os jogadores mandaram com `/intencao` e deixa Permitir ou Negar (com motivo). Próximo turno passa "
            "a vez e marca o jogador; ➕ põe NPC; o menu de baixo edita a iniciativa de alguém ou o tira. Mostrar iniciativa "
            "posta o quadro público, que nunca mostra o texto das intenções. A tela é privada e só atualiza quando você "
            "aperta algo: 🔄 mostra o que chegou. Uma cena por canal."
        ),
        "requisito": "Só mestres.",
    },
    "mestre habilidades": {
        "grupo": "mestre",
        "resumo": "a fila das habilidades que os jogadores criaram",
        "uso": "/mestre habilidades",
        "detalhes": (
            "Mostra as habilidades que os jogadores criaram, as que esperam você primeiro. Escolhe uma no primeiro menu, "
            "lê o que o jogador pediu e ajusta nos menus: dado (dano ou cura), o que custa (Mana, Estamina, Sanidade ou "
            "Vida) e um atributo pra somar. Depois aperta Aprovar, Pedir ajuste (com uma nota que ele lê) ou Recusar. "
            "Corrigir texto muda nome, descrição e efeito; Valores exatos deixa digitar o dado, o custo e o atributo. "
            "Aprovada, o jogador usa com um botão: o custo sai da barra e o dado rola sozinho."
        ),
        "requisito": "Só mestres.",
    },
    "mestre pericia": {
        "grupo": "mestre",
        "resumo": "define os pontos de uma perícia (conserta a distribuição)",
        "uso": "/mestre pericia usuario:@alguém pericia:Luta pontos:4",
        "detalhes": (
            "Muda os pontos de uma perícia de um personagem pra um valor exato (de 0 a 20), sem conferir o limite. Serve "
            "pra consertar uma distribuição errada ou dar pontos de recompensa. Mostra quantos pontos livres sobram. "
            "Fica no registro das ações de mestre."
        ),
        "requisito": "Só mestres.",
    },
    "mestre ajuda": {
        "grupo": "mestre",
        "resumo": "a ajuda só dos comandos de mestre",
        "uso": "/mestre ajuda comando:dar_xp",
        "detalhes": (
            "Lista os comandos de mestre por assunto e explica cada um, com exemplo. É separada do `/ajuda` de "
            "propósito: os jogadores não veem os comandos de mestre nem esta ajuda. Sem `comando`, mostra a lista toda."
        ),
        "requisito": "Só mestres.",
    },
    "pericias": {
        "grupo": "personagem",
        "resumo": "distribui os pontos das perícias e testa com um clique",
        "uso": "/pericias",
        "detalhes": (
            "Abre a aba Perícias da ficha. Escolhe a perícia e aperta +1 ou -1 pra distribuir os pontos (25 na criação, "
            "no máximo 7 em cada). Pra testar, escolhe também o atributo (ele depende da ação) e aperta Testar: rola 1d20 "
            "+ atributo + perícia no canal. O botão Modo troca entre normal, vantagem e desvantagem. ⭐ marca as "
            "perícias em que a sua classe tem vantagem."
        ),
        "requisito": "Precisa de um personagem.",
    },
    "habilidades": {
        "grupo": "personagem",
        "resumo": "cria as suas habilidades e usa as aprovadas",
        "uso": "/habilidades",
        "detalhes": (
            "Abre a aba Habilidades da ficha. Aperta Criar habilidade e preenche o formulário: nome, descrição e o que "
            "você quer que ela faça. O mestre vê, ajusta e aprova, e define o custo (Mana, Estamina...) e o dado de dano "
            "ou cura. Aprovada, é só escolher e apertar Usar: o custo sai da sua barra e o dado rola sozinho no canal. "
            "Você pode editar ou apagar as que ainda não foram aprovadas."
        ),
        "requisito": "Precisa de um personagem.",
    },
    "mestre sorte": {
        "grupo": "mestre",
        "resumo": "mexe na sorte dos d20 de um personagem",
        "uso": "/mestre sorte usuario:@alguém efeito:Vantagem usos:2",
        "detalhes": (
            "Põe um efeito nos próximos d20 do personagem: vantagem (fica o maior de 2), desvantagem, bônus ou "
            "penalidade no total, dado mínimo, dado máximo ou dado fixo. `usos` diz em quantas rolagens ele vale (de 1 "
            "a 20). O cartão da rolagem mostra a marca 🍀 pra todo mundo, a menos que você ligue `discreto`. Só afeta um "
            "d20 sozinho (1d20, d20+5, 3#d20), rolado pelo `/rolar`, pela bandeja ou escrito no chat; não mexe nos "
            "sorteios da criação nem na iniciativa. `Ver` lista os efeitos ativos e `Limpar` tira todos. Fica no "
            "registro das ações de mestre."
        ),
        "requisito": "Só mestres.",
    },
    "mestre disciplina": {
        "grupo": "mestre",
        "resumo": "define o grau de uma Disciplina (0 a 5)",
        "uso": "/mestre disciplina usuario:@alguém disciplina:Potência grau:4",
        "detalhes": (
            "Só pra Vampiro e Dhampir. Define o grau na mão, sem conferir pontos: os graus 1 a 3 contam como pontos "
            "gastos do jogador, e os graus 4 e 5 (que só o mestre concede) não gastam ponto. Grau 0 tira a Disciplina. "
            "A Sanguessugia fica bloqueada pra todo mundo enquanto os graus 1 a 3 dela não estiverem definidos."
        ),
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
        "detalhes": "Aparece na ficha como definido por um mestre. Não confere se a raça e a classe dele têm magia.",
    },
    "mestre corrigir_raca": {
        "grupo": "mestre",
        "resumo": "define a raça na mão, sem rolar",
        "uso": "/mestre corrigir_raca usuario:@alguém raca:Dhampir",
        "detalhes": (
            "Aparece na ficha como definido por um mestre. Se a raça nova der magia (Vampiro) e o jogador ainda não "
            "tiver sorteado o Rank de magia, o bot avisa, e ele passa a precisar do `/magia_inicial`."
        ),
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
        "detalhes": (
            "Funciona mesmo depois de o jogador já ter escolhido, e mesmo que ele ainda não tenha feito os sorteios. "
            "Se a classe nova der magia (Feiticeiros ou Mestre de Forja) e ele ainda não tiver sorteado o Rank de "
            "magia, o bot avisa, e ele passa a precisar do `/magia_inicial`."
        ),
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
    "mestre apagar_historico": {
        "grupo": "mestre",
        "resumo": "apaga o histórico de rolagens de um jogador",
        "uso": "/mestre apagar_historico usuario:@alguém",
        "detalhes": (
            "Apaga todas as rolagens que o `/historico` mostra pra esse jogador, de todos os personagens dele, inclusive "
            "as dos sorteios de criação (raça, magia e classe social). Pede confirmação com botões, avisa no canal e fica "
            "registrado. Não mexe na ficha, no XP nem nos personagens, e não tem como desfazer."
        ),
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
    ("Ficha", ["ficha", "atributos", "corrigir_classe", "rank_pericia", "disciplina"]),
    ("Dados", ["sorte"]),
    ("Sorteios", ["apagar", "corrigir_magia", "corrigir_raca", "corrigir_estado"]),
    ("Cena", ["escudo"]),
    ("Habilidades e perícias", ["habilidades", "pericia"]),
    ("Ajuda", ["ajuda"]),
    ("Jogadores", ["jogador", "vagas", "excluir_personagem", "apagar_historico", "exportar"]),
]

# Só comandos, em ordem, pra sugerir no autocomplete quando a pessoa ainda não digitou nada.
ORDEM_SUGESTAO = [
    "personagem criar", "raca_inicial", "classe_social", "classe", "habilidade", "magia_inicial", "atributos", "minha_ficha",
    "rolar", "dados", "iniciativa", "intencao", "niveis", "rank", "calcular_recursos", "historico", "extrato_xp", "personagem usar",
    "personagem listar", "personagem excluir", "disciplinas", "pericias", "habilidades", "ajuda",
]


# ---------------------------------------------------------------------------
# Passo a passo da criação
# ---------------------------------------------------------------------------
def _juntar(itens: list[str]) -> str:
    """['a', 'b', 'c'] vira 'a, b e c'."""
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


def _depois(passo_id: str, status: dict) -> str:
    """'depois de sortear a raça e a classe social, escolher a classe...' (o que ainda falta antes desse passo)."""
    faltam = rules.creation_missing_before(passo_id, status)
    partes = []
    sorteios = [{"raca": "a raça", "estado": "a classe social"}[x] for x in faltam if x in ("raca", "estado")]
    if sorteios:
        partes.append("sortear " + _juntar(sorteios))
    if "classe" in faltam:
        partes.append("escolher a classe")
    if "magia" in faltam:
        partes.append("sortear o Rank de magia")
    # 'depois de sortear a raça e a classe social, de escolher a classe e de sortear o Rank de magia'
    return "depois de " + _juntar([partes[0]] + [f"de {p}" for p in partes[1:]])


def linhas_passo_a_passo(status: dict) -> list[str]:
    """Um item por passo: ✅ feito, ▶️ próximo, ⬜ liberado, ⏳ com o mestre, 🔒 ainda fechado,
    ➖ não vale pra você (Rank de magia de quem não tem magia)."""
    proximo = rules.creation_next_step(status)
    linhas = ["✅ Personagem criado"]
    for passo in rules.CREATION_STEPS:
        pid = passo["id"]
        if pid == "magia" and status["sem_magia"] and not status["magia_sorteada"]:
            linhas.append("➖ Rank de magia: a sua raça e a sua classe não têm magia, então esse passo não vale pra você")
        elif status[pid]:
            linhas.append(f"✅ {passo['rotulo']}")
        elif status["especial"].get(pid):
            linhas.append(f"❓ {passo['rotulo']}: algo diferente aconteceu no seu sorteio, então um mestre vai decidir")
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
    if status["especial"].get(proximo):
        return "Agora é com um mestre: algo diferente aconteceu no seu sorteio, fala com ele pra decidir, e aí você segue."
    if proximo == "estado" and status["aguardando_mestre"]:
        return "Agora é com um mestre: fala com ele pra definir o seu Estado, e aí você segue."
    passo = next(p for p in rules.CREATION_STEPS if p["id"] == proximo)
    dica = " (a raça e a classe social podem ser sorteadas em qualquer ordem)" if proximo in ("raca", "estado") else ""
    return f"Próximo passo: `{passo['comando']}`, pra {passo['rotulo'][0].lower() + passo['rotulo'][1:]}{dica}."


def texto_sem_magia(nome: str, raca: str | None, classe: str | None, status: dict) -> str:
    """Resposta de quando alguém sem magia tenta o /magia_inicial."""
    return (
        f"🚫 **{nome}** não sorteia o Rank de magia: só tem magia quem é Vampiro ou Dhampir (de qualquer classe) ou das "
        f"classes Feiticeiros e Mestre de Forja, e essa combinação é {raca} com {classe}. Esse passo não vale pra esse personagem.\n\n"
        + proximo_passo(status)
    )


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
    if any(status["especial"].get(p) for p in faltam):
        return (
            f"Ainda não dá pra usar `{passo['comando']}`: algo diferente aconteceu num dos seus sorteios, então um "
            "mestre precisa decidir antes. Fala com ele."
        )
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


# O bot liga isso na partida só se a leitura de mensagens estiver funcionando (veja bot.py).
DICA_DADOS_POR_TEXTO = (
    "Também dá pra rolar sem barra: escreve o dado direto no chat, tipo `d20`, `d20+5` ou `2d6-1`. "
    "Com um `+` na frente, o que vem depois do dado vira o motivo: `+d20+5 ataque com a espada`."
)
_dados_por_texto = False


def ativar_dados_por_texto(ligado: bool) -> None:
    global _dados_por_texto
    _dados_por_texto = bool(ligado)


def detalhe(chave: str) -> dict:
    """Título, descrição e campos da ajuda de um comando."""
    e = AJUDA[chave]
    if chave == "rolar" and _dados_por_texto:
        e = {**e, "detalhes": f"{e['detalhes']}\n\n{DICA_DADOS_POR_TEXTO}"}
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
    return {
        "titulo": "📖 Ajuda do bot",
        "descricao": (
            "É só digitar `/` e escolher o comando. Pra ver como usar um deles, com exemplo, usa "
            "`/ajuda comando:nome`, tipo `/ajuda comando:atributos`."
            + ("\n\n🎲 Pra rolar dado, nem precisa de barra: escreve `d20+5` no chat." if _dados_por_texto else "")
            + ("\n\n🛡️ Você é mestre: os comandos de mestre ficam separados, em `/mestre ajuda`." if mestre else "")
        ),
        "campos": campos,
    }


def visao_mestre() -> dict:
    """O /mestre ajuda: só os comandos de mestre, por assunto. Quem não é mestre nunca vê isso."""
    campos = []
    for rotulo, cmds in MESTRE_SUBGRUPOS:
        linhas = [f"`/mestre {c}` {AJUDA[f'mestre {c}']['resumo']}" for c in cmds]
        campos.append((rotulo, "\n".join(linhas)))
    return {
        "titulo": "🛡️ Ajuda do mestre",
        "descricao": (
            "Só quem é mestre vê esta ajuda e os comandos `/mestre`. Pra ver como usar um deles, com exemplo, usa "
            "`/mestre ajuda comando:nome`, tipo `/mestre ajuda comando:dar_xp`."
        ),
        "campos": campos,
    }


def sugestoes_mestre(texto: str) -> list[str]:
    """Os nomes dos comandos de mestre (sem o 'mestre ') pro autocomplete do /mestre ajuda."""
    t = _normalizar(texto)
    nomes = [k.split(" ", 1)[1] for k in AJUDA if k.startswith("mestre ")]
    return [n for n in nomes if not t or t in n][:25]


def achar_mestre(texto: str) -> tuple[str | None, list[str]]:
    """Acha um comando de mestre pelo que foi digitado (com ou sem o 'mestre '). Devolve (chave, sugestões)."""
    t = _normalizar(texto)
    t = t[len("mestre "):] if t.startswith("mestre ") else t
    nomes = [k.split(" ", 1)[1] for k in AJUDA if k.startswith("mestre ")]
    if t in nomes:
        return f"mestre {t}", []
    achados = [n for n in nomes if t and t in n]
    return (f"mestre {achados[0]}", []) if len(achados) == 1 else (None, achados[:5])
