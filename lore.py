"""Textos e cores dos cartões que o bot mostra quando alguém sorteia raça, classe social, classe ou magia.

É AQUI que se edita o texto de cada resultado. Os textos de raça e de Estado vieram do servidor (os prints do
ProBot); os do Dhampir, do clero e das classes vieram do site. Nada aqui mexe em regra, só em texto e cor.

IMAGENS: o bot procura sozinho um arquivo na pasta assets/ com o nome  <tipo>-<nome>.<extensão>, todo em
minúsculas, sem acento e com hífen no lugar de espaço. Extensões aceitas: gif, png, jpg, jpeg e webp (o gif se
mexe no Discord). Exemplos:
    assets/raca-humano.png      assets/raca-dhampir.gif      assets/estado-3.png       assets/estado-mestre.png
    assets/clero-alto.png       assets/classe-cacador.png    assets/classe-mestre-de-forja.png
    assets/magia-super-raro.png
Se não existir arquivo, o cartão sai sem imagem. Pra usar um link direto (por exemplo, de um gif hospedado em
outro lugar), coloque em IMAGENS_URL abaixo; o link tem que apontar direto pra imagem, não pra uma página.
"""

# Chave: "<tipo>-<nome>" no mesmo formato do nome do arquivo. Valor: link direto da imagem.
IMAGENS_URL: dict[str, str] = {
    # GIFs do Tenor (link direto do arquivo, o que termina em .gif; o link da página /view/ não serve). O bot baixa
    # cada um quando liga e anexa o arquivo no cartão (o Discord às vezes não mostra imagem de link). Se o download
    # falhar, o cartão usa a imagem parada de assets/ e deixa a causa no log ("[imagens] ..."); só sem arquivo nenhum
    # é que o link vai direto.
    "raca-humano": "https://media1.tenor.com/m/BUJrIhFy5hIAAAAC/sypha-castlevania.gif",
    "raca-dhampir": "https://media1.tenor.com/m/bi24o_IvfJoAAAAC/alucard-castlevania-nocturne.gif",
}

# ---------------------------------------------------------------------------
# ESTILO DECORADO (o das mensagens do servidor): cabeçalho enfeitado, texto pequeno em citação e em negrito,
# emojis do servidor e a imagem embaixo. Hoje vale pros cartões de raça e de Estado.
# Os emojis abaixo são do servidor do Marcos: o bot precisa estar nesse servidor (ou ter a permissão "Usar
# emojis externos") pra eles aparecerem. Se aparecer o código escrito, é por isso. Pra trocar, cola o código do
# emoji (<:nome:123456789012345678>) ou um emoji comum (✝️).
# ---------------------------------------------------------------------------
EMOJI_TITULO = "<:cruz2:1467276532916686899>"          # abre o cabeçalho das raças
EMOJI_TEXTO = "<:cruz6:1472548114291364023>"           # abre o texto das raças
EMOJI_TITULO_DHAMPIR = "<:cruz3:1467277925857366066>"  # abre o cabeçalho do Dhampir (o das outras raças é a cruz2)
EMOJI_TITULO_ESTADO = "<:cruz1:1467276278418636953>"   # abre o cabeçalho dos Estados
EMOJI_TEXTO_ESTADO = "<:calicesang:1467277986876358656>"  # abre o texto dos Estados
TEXTO_PEQUENO = True   # o texto sai em letra pequena (-#). Se aparecer o "-#" escrito, troca pra False
# Os caracteres do enfeite (os mesmos das mensagens do servidor):
PREENCHE = "\u3164"        # ㅤ preenchimento que empurra o texto
ORNAMENTO_L = "\U0001D4F5"  # 𝓵
NULO = "\U0001D159"         # 𝅙 (não aparece, só dá espaço)
HIEROGLIFO = "\U00013085"   # 𓂅
TRAVESSAO = "\u2014"        # o traço que o Marcos usa nos rótulos dos Estados

# ENFEITES dos cartões. Dá pra trocar por emojis do seu servidor (os animados também): cola o código do emoji,
# tipo <a:fogo:123456789012345678>. O divisor abre o texto de cada cartão.
DIVISOR = "✦ ━━━━━━━ ⚜️ ━━━━━━━ ✦"
DIVISOR_CURTO = "✦ ━━━ ⚜️ ━━━ ✦"

# ---------------------------------------------------------------------------
# Raças (sorteio de 1d100)
# ---------------------------------------------------------------------------
RACAS = {
    "Humano": {
        "emoji": "🕯️",
        "rotulo": "Humanos",
        "emoji_titulo": EMOJI_TITULO,
        "emoji_texto": EMOJI_TEXTO,
        "cor": 0xC9A66B,
        "texto": (
            "São seres mundanos, sujeitos ao envelhecimento e à morte. Contudo, não se engane: suas vidas podem "
            "ser efêmeras, porém, enquanto caminham sobre a terra ou até mesmo após o tempo ter apagado seu rastro, "
            "seus fantasmas e seus significados ainda podem assombrar seres eternos para sempre. De fato, são "
            "criaturas extraordinárias com a capacidade de ter fé e, ao mesmo tempo, serem corrompidas pelos seus "
            "desejos mais obscuros."
        ),
        "fraquezas": None,
    },
    "Vampiro": {
        "emoji": "🩸",
        "rotulo": "Vampiros",
        "emoji_titulo": EMOJI_TITULO,
        "emoji_texto": EMOJI_TEXTO,
        "cor": 0x8B0000,
        "texto": (
            "Essas criaturas estiveram na terra por anos, se escondendo, presentes em cada momento da história. "
            "O primeiro vampiro de que temos conhecimento é o Conde Drácula, ou Vlad, e precisa ser derrotado a cada "
            "100 anos. Quando você é transformado num vampiro, apesar das vantagens como imortalidade, poderes "
            "mágicos ou feitiçaria e status sobre-humanos, coisas como água corrente, sol e decapitação, além da "
            "sede incessante por sangue, então não se afunde muito nas suas vitórias, aqueles que os fazem são os "
            "primeiros a morrer."
        ),
        "fraquezas": "Sol, Prata, Fome, Estaca, Decapitação, Água Sagrada e Armas Sagradas",
    },
    "Dhampir": {
        "emoji": "🌒",
        "rotulo": "Dhampirs",
        "emoji_titulo": EMOJI_TITULO_DHAMPIR,
        "emoji_texto": EMOJI_TEXTO,
        "cor": 0x6A3D9A,
        "texto": (
            "Trata-se de seres amaldiçoados pela imortalidade desde o seu nascimento, devido à junção antinatural "
            "entre um humano e um vampiro, possuindo todas as forças e habilidades de um vampiro, mas sendo "
            "sujeitos a algumas ou até mesmo a todas as fraquezas de um vampiro comum, dependendo da sua linhagem. Dhampirs "
            "podem viver entre os humanos normalmente, mas ainda assim são um risco à população, já que o sangue "
            "ainda é a sua fonte principal de alimentação e poder."
        ),
        "fraquezas": "Algumas ou até todas as de um vampiro comum, conforme a linhagem (Sol, Prata, Fome, Estaca, Decapitação, Água Sagrada e Armas Sagradas)",
    },
}

# ---------------------------------------------------------------------------
# Classe social (sorteio de 1d100; o 1º Estado rola outro 1d100 pro clero)
# ---------------------------------------------------------------------------
ESTADOS = {
    "3º Estado": {
        "titulo": "3º Estado · Camponeses",
        "rotulo": f"3° Estado {TRAVESSAO}  Camponeses",
        "emoji_titulo": EMOJI_TITULO_ESTADO,
        "emoji_texto": EMOJI_TEXTO_ESTADO,
        "emoji": "⚜️",
        "cor": 0x7C8592,
        "texto": (
            "Por mais que a revolução pareça a luz no fim do túnel, você ainda tem fome, o pão ainda está escasso "
            "e sua vida está ameaçada por um único tiro errado durante um motim, podem fazer quanta propaganda "
            "quiserem, vocês ainda estão na miséria."
        ),
    },
    "2º Estado": {
        "titulo": "2º Estado · Nobreza",
        "rotulo": f"2° Estado {TRAVESSAO}  Nobreza",
        "emoji_titulo": EMOJI_TITULO_ESTADO,
        "emoji_texto": EMOJI_TEXTO_ESTADO,
        "emoji": "⚜️",
        "cor": 0xD4AF37,
        "texto": (
            "Você pode até achar que o dinheiro é uma boa coisa, viver confortável, não? Errado. Eles estão atrás "
            "de cada um de vocês, estão reunindo seus servos, tirando vocês aos poucos de seus confortos, não cante "
            "vitória por muito tempo, em breve vão descobrir você e suas farsas, e você não vai escapar."
        ),
    },
    "1º Estado": {
        "titulo": "1º Estado · Clero",
        "rotulo": f"1° Estado {TRAVESSAO}  Clero",
        "emoji_titulo": EMOJI_TITULO_ESTADO,
        "emoji_texto": EMOJI_TEXTO_ESTADO,
        "emoji": "⚜️",
        "cor": 0x8E6FBF,
        "texto": (
            "Você faz parte do clero, que sorte! Os revolucionários ainda têm respeito por Deus, então vocês não "
            "são o principal alvo deles, mas tome cuidado ao esbanjar suas riquezas, Deus pode tirá-la tão rápido "
            "quanto a deu."
        ),
    },
}

# Resultado 100 no sorteio da classe social: quem decide o Estado é o mestre.
ESTADO_MESTRE = {
    "titulo": "Resultado especial",
    "emoji": "🎲",
    "cor": 0xD4AF37,
    "texto": "Quem decide o Estado desse personagem é o mestre. Fala com um mestre.",
}

# ---------------------------------------------------------------------------
# Resultado especial: um 66 ou um 77 em qualquer sorteio de criação (raça, classe social ou Rank de magia).
# O cartão é todo de interrogações, de propósito: quem sorteia não sabe o que aconteceu, e um mestre decide.
# O significado dos dois números é segredo de quem criou o sistema, então não aparece em texto nenhum.
# 66 é vermelho, 77 é amarelo. Imagem opcional: assets/especial-66.png e assets/especial-77.png.
# ---------------------------------------------------------------------------
ESPECIAL = {
    66: {"cor": 0xC0392B},
    77: {"cor": 0xF1C40F},
}
ESPECIAL_DIVISOR = "❓ ━━━━━━━ ❓ ━━━━━━━ ❓"
ESPECIAL_TITULO = "? ? ? ? ? ? ?"
ESPECIAL_AUTOR = "❓ ??? ?? ??????"
ESPECIAL_TEXTO = (
    "??? ????? ?? ??????? ??? ????, ??? ????? ??? ???? ??????.\n"
    "?? ???? ???? ??? ?????? ?? ?????? ?? ????? ??????? ????.\n"
    "???? ?? ????? ????, ??? ???? ?? ????? ?????."
)
ESPECIAL_CAMPO = ("???", "?????? ??? ????? ?? ??????")
ESPECIAL_RODAPE = "? ? ? ? ?"

CLERO = {
    "Alto Clero": "O Alto Clero, de bispos e abades, vive como príncipes.",
    "Baixo Clero": "O Baixo Clero, de párocos de aldeia, partilha a pobreza do rebanho.",
}

# ---------------------------------------------------------------------------
# Classes (os textos e as habilidades são os do site, copiados dele; o capítulo Habilidades de Classe do
# site ainda é rascunho em revisão, então isso muda quando ele mudar)
# ---------------------------------------------------------------------------
CLASSES = {  # o texto de cada classe
    "Caçador": (
        "Os caçadores devotam suas vidas ao extermínio das trevas, buscando, de um jeito ou de outro, "
        "purificar o mundo do inferno e dos servos que por ele vagam. Vivem entre a fé e a violência, "
        "treinados pra reconhecer e abater o que a maioria prefere fingir que não existe."
    ),
    "Clérigo": (
        "Cuidam do corpo e da alma de quem chega até eles. Servem à fé, ou ao que sobrou dela, num tempo "
        "em que a própria Igreja se divide: com a mão sobre o ferido e a palavra sobre o moribundo, são o "
        "último abrigo de quem já não sabe em quem confiar. Não precisam vestir batina: cura quem sabe "
        "curar."
    ),
    "Feiticeiros": (
        "Estudiosos do proibido, buscam nas páginas antigas e nos rituais esquecidos um poder que a "
        "maioria teme sequer nomear. Cada segredo aprendido cobra um preço, e nem todo feiticeiro percebe "
        "o quanto já pagou até ser tarde demais."
    ),
    "Ladrão": (
        "Sobrevive pela lâmina afiada da língua e pela sombra que nunca o larga. Não busca glória nem "
        "verdade. Busca o próximo passo, a próxima porta trancada, a próxima chance de sumir antes que "
        "alguém perceba que ele esteve ali."
    ),
    "Mercenário": (
        "Viveu a vida lutando: com a espada, com as mãos, com o corpo inteiro. Cobra pelo serviço, ou "
        "luta de graça por quem precisa, e aprendeu cedo que o mal do mundo não vem só de vampiros e "
        "demônios: os homens dão conta de sobra. Talvez nunca tenha visto o sobrenatural, mas conhece o "
        "perigo como poucos."
    ),
    "Mestre de Forja": (
        "Funde o conhecimento das mãos com o conhecimento proibido: entende que uma lâmina comum não fere "
        "o que espreita na escuridão, e que toda alma pesa, e o que pesa pode ser moldado. Na bigorna, "
        "almas viram lâmina, ferramenta e armadura; no ritual, corpos sem vida voltam como criaturas da "
        "noite, tão fiéis quanto cães a quem os forjou. Cada peça e cada criatura carrega o preço de quem "
        "foi antes."
    ),
    "Mundano": (
        "Você vive um dia de cada vez, cuidando dos seus afazeres cotidianos e se preocupando, no máximo, "
        "com o que vai comer no almoço. Sua vida segue sem muitas preocupações, até que as trevas decidam "
        "o contrário. Ainda não escolheu o seu lugar no mundo, e talvez o encontre: conquistar uma classe "
        "exige RP e conversa com o mestre."
    ),
    "Sábio": (
        "Os sábios buscam o saber que liberta da fome, do medo e da ignorância. Mas, neste mundo de "
        "trevas, quem seria capaz de encontrá-lo? Preferem a biblioteca ao campo de batalha, mas o que "
        "aprendem muitas vezes os arrasta pra lá de qualquer jeito."
    ),
}

CLASSE_FRASE = {  # a frase curta embaixo do nome
    "Caçador": "Fé e violência",
    "Clérigo": "Cura e fé",
    "Feiticeiros": "Estudo proibido",
    "Ladrão": "Sombra e lábia",
    "Mercenário": "Corpo e espada",
    "Mestre de Forja": "Almas na bigorna",
    "Mundano": "Ainda sem lugar",
    "Sábio": "Saber e dúvida",
}

CLASSE_COMBINA = {  # profissões que combinam (exemplos)
    "Caçador": ["Pastor", "Soldado", "Guarda real", "Monge"],
    "Clérigo": ["Padre", "Freira", "Pastor", "Hospedeiro"],
    "Feiticeiros": ["Alfaiate", "Conselheiro real", "Meretriz", "Abade"],
    "Ladrão": ["Criado Doméstico", "Meretriz", "Diplomata", "Dama de Companhia"],
    "Mercenário": ["Soldado", "Coronel", "Ferreiro", "Agricultor"],
    "Mestre de Forja": ["Ferreiro", "Alfaiate", "Marceneiro", "Monge"],
    "Mundano": ["Padeiro", "Comerciante", "Dama de Companhia", "Padre"],
    "Sábio": ["Juiz", "Conselheiro Jurídico", "Monge", "Comerciante"],
}

# A habilidade inicial de cada classe. "escolha": a classe oferece duas e o jogador leva uma.
# Cada habilidade: nome, marcas (tipo e custo), frase e a lista de efeitos (rótulo, texto).
HABILIDADES = {
    "Caçador": {
        "escolha": False,
        "opcoes": [
            {
                "nome": "Sem Dúvidas",
                "marcas": ["Inicial", "Passiva", "Físico", "Custo: 10 Estamina no Efeito²"],
                "frase": (
                    "Antes de iniciar uma caçada, o caçador precisa saber separar o que é mundano do que "
                    "é profano: o que é obra do homem e da natureza e o que vem de bruxos e demônios. Uma "
                    "vez confirmada a presença das trevas, a investigação começa."
                ),
                "efeitos": [
                    ("Efeito¹", (
                        "Ao iniciar uma cena de investigação, recebe vantagem para descobrir se algo é "
                        "profano ou não natural. Não gasta nada."
                    )),
                    ("Efeito² (Presa Marcada)", (
                        "Ao confirmar que um alvo é sobrenatural, o caçador o marca, gastando 10 de "
                        "Estamina. Tem vantagem nos ataques e em Percepção contra ele até o fim da cena, "
                        "e só mantém uma marca por vez."
                    )),
                ],
            },
        ],
    },
    "Clérigo": {
        "escolha": True,
        "opcoes": [
            {
                "nome": "Mãos que Curam",
                "marcas": ["Inicial", "Ativa", "Fé", "Custo: 15 Mana"],
                "frase": "Onde os outros veem uma ferida, o clérigo vê alguém que ainda pode ser salvo.",
                "efeitos": [
                    ("Efeito¹", (
                        "Gasta 15 de Mana e toca um aliado. Faz um teste de Fé (DT 15): se passar, o "
                        "aliado recupera Vida igual a Alma × 5. Pode repetir quantas vezes a Mana "
                        "aguentar."
                    )),
                    ("Efeito²", "Estabilizar quem está com a Vida em 0 custa 20 de Mana e não precisa de teste."),
                ],
            },
            {
                "nome": "Bênção",
                "marcas": ["Inicial", "Ativa", "Fé", "Custo: 10 Mana"],
                "frase": "Um gesto, uma palavra, e a arma passa a servir a algo maior do que quem a empunha.",
                "efeitos": [
                    ("Efeito¹", (
                        "Gasta 10 de Mana e abençoa um alvo ao alcance do toque: um aliado ou o próprio "
                        "clérigo (teste de Fé, DT 15). Até o fim da cena, o dano do abençoado se torna "
                        "sagrado."
                    )),
                    ("Efeito²", "O dano sagrado segue a regra de Armas Sagradas (ver Fraquezas)."),
                ],
            },
        ],
    },
    "Feiticeiros": {
        "escolha": False,
        "opcoes": [
            {
                "nome": "Dom Nato",
                "marcas": ["Inicial", "Passiva", "Magia"],
                "frase": (
                    "Nascidos pra criar e aprimorar o que os outros só temem, os feiticeiros dobram a mão "
                    "no que já sabem fazer."
                ),
                "efeitos": [
                    ("Efeito¹", "Toda magia do feiticeiro recebe +1 dado de efeito (dano, cura etc.)."),
                    ("Efeito²", (
                        "Gasta menos Mana pra lançar magias: cada magia custa Razão × 5 de Mana a menos, "
                        "com custo mínimo de 1."
                    )),
                ],
            },
        ],
    },
    "Ladrão": {
        "escolha": True,
        "opcoes": [
            {
                "nome": "Mão Leve",
                "marcas": ["Inicial", "Ativa", "Físico", "Custo: 10 Estamina"],
                "frase": (
                    "Uma mão tão suave quanto uma pluma. O que o ladrão deseja, ele consegue, desde que "
                    "ninguém o note."
                ),
                "efeitos": [
                    ("Efeito¹", (
                        "Gasta 10 de Estamina e faz um teste de Furtividade com vantagem contra a "
                        "Percepção do alvo. Se passar, rouba um item pequeno ou médio do inventário dele, "
                        "ou coloca um no lugar."
                    )),
                    ("Efeito²", "Cada tentativa gasta a Estamina, dê certo ou não."),
                ],
            },
            {
                "nome": "Língua de Prata",
                "marcas": ["Inicial", "Ativa", "Social", "Custo: 10 Estamina"],
                "frase": "A arma mais afiada que o ladrão carrega não tem cabo.",
                "efeitos": [
                    ("Efeito¹", (
                        "Gasta 10 de Estamina e faz um teste de Enganação com vantagem pra vender uma "
                        "mentira, distrair um guarda ou sair de uma conversa que ia mal."
                    )),
                ],
            },
        ],
    },
    "Mercenário": {
        "escolha": False,
        "opcoes": [
            {
                "nome": "Ombro a Ombro",
                "marcas": ["Inicial", "Ativa", "Físico", "Custo: 10 Estamina"],
                "frase": (
                    "Quem vive de espada sabe que o perigo mais comum tem rosto de homem, e que o corpo é "
                    "o escudo mais barato que existe."
                ),
                "efeitos": [
                    ("Efeito¹", (
                        "Quando um aliado ao alcance é atacado, gasta a sua reação e 10 de Estamina pra "
                        "se colocar na frente e receber o ataque no lugar dele, com vantagem no teste de "
                        "defesa."
                    )),
                ],
            },
        ],
    },
    "Mestre de Forja": {
        "escolha": False,
        "opcoes": [
            {
                "nome": "Forja de Almas",
                "marcas": ["Inicial", "Ativa", "Ritual", "Custo: Mana por Rank"],
                "frase": "Toda alma pesa, e o que pesa pode ser moldado.",
                "efeitos": [
                    ("Efeito¹ (Catalisador)", (
                        "Todo ritual pede um instrumento, que serve de catalisador: um martelo, uma faca, "
                        "até uma dama de ferro. Pede também um recipiente pra alma: um corpo já morto, "
                        "que vira uma criatura da noite, ou um objeto, que vira arma, ferramenta ou peça."
                    )),
                    ("Efeito² (A alma)", (
                        "A alma que o mestre de forja prende decide o resultado. Quanto mais forte foi a "
                        "alma em vida, mais alto o Rank da criatura ou do objeto que ela consegue "
                        "sustentar. Um corpo comum rende pouco."
                    )),
                    ("Efeito³ (O preço)", (
                        "O ritual gasta Mana conforme o Rank do que se quer forjar, com o custo definido "
                        "pelo mestre, como nas magias. Faz um teste de Ritualismo: falhar gasta a Mana do "
                        "mesmo jeito, e um 1 natural faz a alma reagir. A criatura se volta contra quem a "
                        "forjou, ou o objeto sai amaldiçoado."
                    )),
                ],
            },
        ],
    },
    "Mundano": {
        "escolha": False,
        "opcoes": [
            {
                "nome": "Aprimoração",
                "marcas": ["Inicial", "Passiva"],
                "frase": (
                    "Quem vive no mundo comum ainda não escolheu o seu lugar nele. Quando as trevas "
                    "chegam, algo desperta, e a rotina vira aprendizado."
                ),
                "efeitos": [
                    ("Efeito¹ (Vida vivida)", (
                        "+5 pontos de perícia na criação, além dos 25 comuns (30 no total), porque o "
                        "Mundano vive a vida e aprende de tudo um pouco."
                    )),
                    ("Efeito² (Aprimoração)", (
                        "Durante o RP, o Mundano pode se aprimorar pra uma das classes existentes. Não é "
                        "automático: só acontece por RP, em conversa com o mestre. Ao trocar, passa a ter "
                        "os recursos, a vantagem de perícias e a habilidade da nova classe no lugar dos "
                        "de Mundano, e os 5 pontos ficam. Se a nova classe tem magia inicial, sorteia na "
                        "hora."
                    )),
                ],
            },
        ],
    },
    "Sábio": {
        "escolha": False,
        "opcoes": [
            {
                "nome": "Saber e Poder",
                "marcas": ["Inicial", "Passiva", "Ativa", "Saber", "Custo: 10 Mana no Efeito²"],
                "frase": (
                    "Quem sabe mais aprende mais depressa, e quem aprende depressa passa a mandar no que "
                    "sabe."
                ),
                "efeitos": [
                    ("Efeito¹", "Ganha o dobro de pontos de perícia por nível: +4 em vez de +2."),
                    ("Efeito²", (
                        "Pode gastar 10 de Mana pra ganhar vantagem em um teste de Razão. O custo vale "
                        "por teste."
                    )),
                ],
            },
        ],
    },
}
COR_CLASSE = 0x2E7D5B

# ---------------------------------------------------------------------------
# Rank de magia (a chance de cada um vem da tabela do sorteio, em dice.py)
# ---------------------------------------------------------------------------
TEXTO_MAGIA = "Quanto maior o Rank, mais Mana a magia gasta e mais forte é o efeito."
RANKS_MAGIA = {
    "Comum":      {"estrelas": 1, "cor": 0x9AA0A6},
    "Raro":       {"estrelas": 2, "cor": 0x3B82F6},
    "Super Raro": {"estrelas": 3, "cor": 0x8B5CF6},
    "Lendário":   {"estrelas": 4, "cor": 0xF59E0B},
    "Mítico":     {"estrelas": 5, "cor": 0xDC2626},
}

# ---------------------------------------------------------------------------
# Disciplinas vampíricas (só Vampiro e Dhampir). O texto de cada grau é o do sistema; os graus 4 e 5 de
# todas as Disciplinas estão sempre em aberto e só entram em jogo quando um mestre concede.
# 'graus' None = ainda em desenvolvimento (Sanguessugia). 'limite' é uma nota que vale pra Disciplina toda.
# ---------------------------------------------------------------------------
GRAUS_4_E_5 = "Em aberto. Só entram em jogo quando um mestre concede."
DISCIPLINA_EM_DESENVOLVIMENTO = "Em desenvolvimento: os graus 1 a 3 ainda não foram definidos."

DISCIPLINAS = {
    "Potência": {
        "tema": "força sobrenatural bruta",
        "graus": {
            1: "Dobra o modificador de Força no dano das armas.",
            2: "Aumenta em um dado o dano de armas corpo a corpo.",
            3: "O dano desarmado vira 1d12.",
        },
    },
    "Celeridade": {
        "tema": "velocidade sobrenatural",
        "graus": {
            1: "Reage antes de qualquer humano numa cena, com vantagem em iniciativa.",
            2: "Ganha uma reação extra.",
            3: "Ganha uma ação de movimento extra.",
        },
    },
    "Ofuscação": {
        "tema": "passar despercebido",
        "graus": {
            1: "Vantagem em testes de Furtividade.",
            2: "Consegue se esconder mesmo em lugares iluminados.",
            3: "Oculta a presença por completo, com DT fixa 22 pra quem tentar percebê-lo (ou rola Furtividade normal, o que for melhor).",
        },
    },
    "Presença": {
        "tema": "a sua presença perante outros seres, a sua intenção x a intenção do outro",
        "graus": {
            1: "Vantagem em Enganação e Intimidação.",
            2: "Consegue intimidar com DT fixa 20 (ou Intimidação normal, o que for melhor).",
            3: "Ao vencer um teste de Intimidação, paralisa por 1d3 turnos quem falhou (Intimidação x Vontade do oponente), 1 vez por combate.",
        },
    },
    "Domínio": {
        "tema": "controle mental direto, exige contato visual e que a vítima entenda o comando",
        "graus": {
            1: "Impõe a sua vontade sobre outros seres gastando 5 de Mana (Vontade x Vontade do alvo).",
            2: "Manipula e controla mentes de seres pequenos, tipo animais e ratos, à vontade.",
            3: "Controla seres gastando 15 de Mana (Vontade x Vontade do alvo).",
        },
    },
    "Vidência": {
        "tema": "sentidos aguçados além do humano",
        "graus": {
            1: "Enxerga no escuro, com vantagem em testes de Percepção.",
            2: "Escuta batimentos e respiração de quem está por perto, mesmo atrás de paredes. Sabe quantos seres vivos há.",
            3: "Sente a presença dos seres ao seu redor, com DT fixa 22 no teste de perceber seres alheios, e distingue o estado deles (a vida).",
        },
    },
    "Proteísmo": {
        "tema": "transformação corporal",
        "graus": {
            1: "Consegue se comunicar com animais e dar sugestões a eles.",
            2: "Se transforma em animais pequenos, como ratos e morcegos, gastando 10 de Mana.",
            3: "Se transforma em animais de porte médio, como cachorros e lobos, gastando 15 de Mana.",
        },
    },
    "Hemomancia": {
        "tema": "magia do próprio sangue, libera o acesso à magia Vampírica",
        "graus": {
            1: "Ganha acesso à magia de sangue, podendo fazer magias ligadas a controlar sangue e coisas relacionadas.",
            2: "As suas magias de sangue recebem +1 dado de efeito (dano etc.).",
            3: "Manipula o próprio sangue por dentro pra mudar os órgãos de lugar e outras capacidades parecidas.",
        },
    },
    "Sanguessugia": {
        "tema": "talento voltado ao ato de se alimentar",
        "graus": None,
    },
    "Regeneração": {
        "tema": "cura acelerada do corpo vampírico",
        "graus": {
            1: "Recupera Vida gastando Estamina (3 ST = 1 PV).",
            2: "Recupera Vida gastando Estamina (2 ST = 1 PV), e a capacidade regenerativa dá vantagem pra resistir a efeitos adversos.",
            3: "Também usa Mana pra recuperar Vida (2 PM = 1 PV) e recupera membros depois de um tempo.",
        },
        "limite": "Dano de Sol, Prata, Água Sagrada e Armas Sagradas não se regenera.",
    },
}
