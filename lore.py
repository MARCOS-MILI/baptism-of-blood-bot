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
IMAGENS_URL: dict[str, str] = {}

# ---------------------------------------------------------------------------
# Raças (sorteio de 1d100)
# ---------------------------------------------------------------------------
RACAS = {
    "Humano": {
        "emoji": "🕯️",
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
        "cor": 0x8B0000,
        "texto": (
            "Essas criaturas estiveram na terra por anos, se escondendo, presentes em cada momento da história. "
            "O primeiro vampiro que temos conhecimento é o Conde Drácula, ou Vlad, e precisa ser derrotado a cada "
            "100 anos. Quando você é transformado num vampiro, apesar das vantagens como imortalidade, poderes "
            "mágicos ou feitiçaria e status sobre-humanos, coisas como água corrente, sol e decapitação, além da "
            "sede incessante por sangue, então não se afunde muito nas suas vitórias. Aqueles que os fazem são os "
            "primeiros a morrer."
        ),
        "fraquezas": "Sol, Prata, Fome, Estaca, Decapitação, Água Sagrada e Armas Sagradas",
    },
    "Dhampir": {
        "emoji": "🌒",
        "cor": 0x6A3D9A,
        "texto": (
            "A junção de humano com vampiro. Alucard é um Dhampir. É um meio termo: perde algumas fraquezas do "
            "vampiro, mas nasce com menos poder sobrenatural. É uma raça forte e difícil de conseguir, e por isso "
            "rara."
        ),
        "fraquezas": "Prata, Estaca, Decapitação, Armas Sagradas e Água Sagrada (algumas mais fracas que no vampiro). Sem Sol e sem Fome",
    },
}

# ---------------------------------------------------------------------------
# Classe social (sorteio de 1d100; o 1º Estado rola outro 1d100 pro clero)
# ---------------------------------------------------------------------------
ESTADOS = {
    "3º Estado": {
        "titulo": "3º Estado · Camponeses",
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
        "emoji": "⚜️",
        "cor": 0x8E6FBF,
        "texto": (
            "Você é do primeiro estado, parabéns! Representando cerca de 1% a 2% da população francesa, são a "
            "ponta da pirâmide. Conhecido como a Igreja católica, temos o Clero, mais detentor de imensas riquezas, "
            "terras e privilégios da sociedade atual. Junto com a Nobreza, o clero compunha a aristocracia que "
            "sustenta o sistema, tendo mais de 10% das terras da França..."
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

CLERO = {
    "Alto Clero": "O Alto Clero, de bispos e abades, vive como príncipes.",
    "Baixo Clero": "O Baixo Clero, de párocos de aldeia, partilha a pobreza do rebanho.",
}

# ---------------------------------------------------------------------------
# Classes (o texto de cada uma é o do site)
# ---------------------------------------------------------------------------
CLASSES = {
    "Caçador": (
        "Os caçadores devotam suas vidas ao extermínio das trevas, buscando, de um jeito ou de outro, purificar o "
        "mundo do inferno e dos servos que por ele vagam. Vivem entre a fé e a violência, treinados pra reconhecer "
        "e abater o que a maioria prefere fingir que não existe."
    ),
    "Feiticeiros": (
        "Estudiosos do proibido, buscam nas páginas antigas e nos rituais esquecidos um poder que a maioria teme "
        "sequer nomear. Cada segredo aprendido cobra um preço, e nem todo feiticeiro percebe o quanto já pagou "
        "até ser tarde demais."
    ),
    "Ladrão": (
        "Sobrevive pela lâmina afiada da língua e pela sombra que nunca o larga. Não busca glória nem verdade. "
        "Busca o próximo passo, a próxima porta trancada, a próxima chance de sumir antes que alguém perceba que "
        "ele esteve ali."
    ),
    "Mestre de Forja": (
        "Funde o conhecimento das mãos com o conhecimento proibido: entende que uma lâmina comum não fere o que "
        "espreita na escuridão, e dedica a vida a forjar o que realmente pode. Cada peça que sai da sua bigorna "
        "carrega um propósito."
    ),
    "Mundano": (
        "Você vive um dia de cada vez, cuidando dos seus afazeres cotidianos e se preocupando, no máximo, com o "
        "que vai comer no almoço. Sua vida segue sem muitas preocupações, até que as trevas decidam o contrário."
    ),
    "Sábio": (
        "Os sábios buscam o saber que liberta da fome, do medo e da ignorância. Mas, neste mundo de trevas, quem "
        "seria capaz de encontrá-lo? Preferem a biblioteca ao campo de batalha, mas o que aprendem muitas vezes "
        "os arrasta pra lá de qualquer jeito."
    ),
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
