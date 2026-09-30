"""Testes dos textos (lore.py), das imagens (assets/), dos cartões (vitrine.py) e da leitura de dados
escritos no chat (dice.parse_texto). Rodar da pasta do bot: python tests/test_vitrine.py"""
import io
import os
import re
import sys
import tempfile
import unicodedata

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import discord
from PIL import Image

import dice
import lore
import rules
import vitrine

# ---------- 1. os textos cobrem tudo que o bot sorteia ----------
assert list(lore.RACAS) == dice.RACES
assert set(lore.ESTADOS) == set(dice.SOCIAL_CLASSES) and set(lore.CLERO) == set(dice.CLERGY_LEVELS)
assert set(lore.CLASSES) == set(rules.CLASSES) and list(lore.RANKS_MAGIA) == dice.MAGIC_RANKS
assert lore.RACAS["Humano"]["fraquezas"] is None and lore.RACAS["Vampiro"]["fraquezas"] and lore.RACAS["Dhampir"]["fraquezas"]
for nome, info in lore.RACAS.items():
    assert info["texto"].strip() and 0 <= info["cor"] <= 0xFFFFFF and info["emoji"], nome
for nome, info in lore.ESTADOS.items():
    assert info["texto"].strip() and info["titulo"].startswith(nome) and 0 <= info["cor"] <= 0xFFFFFF, nome
assert all(t.strip() for t in lore.CLERO.values()) and all(t.strip() for t in lore.CLASSES.values())
assert [i["estrelas"] for i in lore.RANKS_MAGIA.values()] == [1, 2, 3, 4, 5]
# nada de travessão nos textos (o projeto escreve sem eles)
tudo = [i["texto"] for i in lore.RACAS.values()] + [i["titulo"] + i["texto"] for i in lore.ESTADOS.values()]
tudo += list(lore.CLERO.values()) + list(lore.CLASSES.values()) + [lore.TEXTO_MAGIA, lore.ESTADO_MESTRE["texto"], lore.ESTADO_MESTRE["titulo"]]
assert not any("—" in t or "–" in t for t in tudo)
print("1. textos cobrem todos os resultados OK")

# ---------- 2. nome dos arquivos de imagem ----------
assert vitrine.slug("Mestre de Forja") == "mestre-de-forja" and vitrine.slug("Super Raro") == "super-raro"
assert vitrine.slug("Lendário") == "lendario" and vitrine.slug("Caçador") == "cacador" and vitrine.slug("  Alto  Clero ") == "alto-clero"
assert vitrine.chave_de_imagem("raca", "Dhampir") == "raca-dhampir" and vitrine.chave_de_imagem("classe", "Sábio") == "classe-sabio"
print("2. nomes dos arquivos OK")

# ---------- 3. as imagens que acompanham o bot ----------
ENVIADAS = [("raca", "Humano"), ("raca", "Vampiro"), ("estado", "3"), ("estado", "2"), ("estado", "1")]
for tipo, nome in ENVIADAS:
    ref = vitrine.achar_imagem(tipo, nome)
    assert ref is not None and ref[0] == "arquivo", (tipo, nome)
    with Image.open(ref[1]) as im:
        assert im.width >= 400 and im.height >= 200 and im.format in ("PNG", "JPEG", "GIF", "WEBP"), ref[1]
    assert os.path.getsize(ref[1]) < 8 * 1024 * 1024                       # cabe folgado no limite de upload do Discord
assert vitrine.achar_imagem("raca", "Dhampir") is None and vitrine.achar_imagem("classe", "Caçador") is None    # ainda sem arte
# nenhum arquivo em assets/ com nome fora da convenção (um nome errado nunca apareceria no cartão)
convencao = ("raca-", "estado-", "clero-", "classe-", "magia-")
for arq in os.listdir(vitrine.PASTA_IMAGENS):
    base, ext = os.path.splitext(arq)
    assert arq.startswith(convencao) and ext.lstrip(".") in vitrine.EXTENSOES and base == base.lower(), arq
print("3. imagens OK:", sorted(os.listdir(vitrine.PASTA_IMAGENS)))

# ---------- 4. achar_imagem: prioridade de extensão, link direto, e arquivo que não existe ----------
pasta_original, urls_original = vitrine.PASTA_IMAGENS, dict(lore.IMAGENS_URL)
try:
    with tempfile.TemporaryDirectory() as tmp:
        vitrine.PASTA_IMAGENS = tmp
        assert vitrine.achar_imagem("raca", "Dhampir") is None
        Image.new("RGB", (10, 10)).save(os.path.join(tmp, "raca-dhampir.png"))
        assert vitrine.achar_imagem("raca", "Dhampir") == ("arquivo", os.path.join(tmp, "raca-dhampir.png"))
        Image.new("RGB", (10, 10)).save(os.path.join(tmp, "raca-dhampir.gif"))
        assert vitrine.achar_imagem("raca", "Dhampir")[1].endswith(".gif")           # o gif tem prioridade sobre o png
        lore.IMAGENS_URL["raca-dhampir"] = "https://exemplo.com/dhampir.gif"
        assert vitrine.achar_imagem("raca", "Dhampir") == ("url", "https://exemplo.com/dhampir.gif")   # o link direto ganha de tudo
        c = vitrine.cartao_raca("Alu", "Dhampir", "Ana")
        assert c.embed.image.url == "https://exemplo.com/dhampir.gif" and c.arquivos == [] and "files" not in c.kwargs()
        del lore.IMAGENS_URL["raca-dhampir"]
        c = vitrine.cartao_raca("Alu", "Dhampir", "Ana")                            # agora o gif do arquivo, anexado
        assert [a.filename for a in c.arquivos] == ["raca-dhampir.gif"] and c.embed.image.url == "attachment://raca-dhampir.gif"
finally:
    vitrine.PASTA_IMAGENS = pasta_original
    lore.IMAGENS_URL.clear(); lore.IMAGENS_URL.update(urls_original)
print("4. procura de imagem OK")


# ---------- 5. os cartões: conteúdo, imagem e limites do Discord ----------
def confere_limites(embed):
    assert len(embed.title or "") <= 256 and len(embed.description or "") <= 4096 and len(embed.author.name or "") <= 256
    assert len(embed.footer.text or "") <= 2048 and len(embed.fields) <= 25 and len(embed) <= 6000
    for f in embed.fields:
        assert len(f.name) <= 256 and len(f.value) <= 1024 and f.name.strip() and f.value.strip()


def nomes(cartao): return [a.filename for a in cartao.arquivos]


def rotulo_do_cartao(e):
    """O rótulo do cabeçalho decorado, sem os enfeites: 'Humanos', '1° Estado —  Clero'."""
    linha = re.sub(r"<a?:\w+:\d+>", "", e.description.split("\n")[0])
    for enfeite in (lore.PREENCHE, lore.ORNAMENTO_L, lore.NULO, lore.HIEROGLIFO): linha = linha.replace(enfeite, "")
    return unicodedata.normalize("NFKC", linha).strip()


def esperado_decorado(emoji_titulo, emoji_texto, rotulo, texto):
    """Como o cartão decorado tem que sair, montado à mão, sem usar as funções da vitrine."""
    cab = f"{emoji_titulo}{' ' * 12}{lore.PREENCHE * 5}{lore.ORNAMENTO_L}{lore.NULO * 8}{vitrine.enfeitar_rotulo(rotulo)}{lore.NULO * 3}{lore.PREENCHE * 2} {lore.PREENCHE * 2}{lore.HIEROGLIFO}"
    return f"{cab}\n\n> -# {emoji_texto}{' ' * 6}{lore.NULO * 4}{lore.ORNAMENTO_L}{lore.NULO * 4}**{texto}**"


todos = []
for raca in dice.RACES:
    c = vitrine.cartao_raca("Kairon Flagon", raca, "Marcos", (1, 3)); todos.append(c); e = c.embed
    assert e.title is None and rotulo_do_cartao(e) == {"Humano": "Humanos", "Vampiro": "Vampiros", "Dhampir": "Dhampirs"}[raca]
    assert e.author.name.endswith("Raça de Kairon Flagon") and e.footer.text == "jogador: Marcos · tentativa 1 de 3"
    assert e.description == esperado_decorado("<:cruz2:1467276532916686899>", "<:cruz6:1472548114291364023>", lore.RACAS[raca]["rotulo"], lore.RACAS[raca]["texto"])
    assert "🎲" not in e.description and "1d100" not in e.description and lore.DIVISOR not in e.description      # sem o dado e sem o divisor antigo
    assert e.color.value == lore.RACAS[raca]["cor"] and [f.name for f in e.fields] == ["Em jogo"]
h, v, d = (vitrine.cartao_raca("X", r, "J") for r in dice.RACES)
assert nomes(h) == ["raca-humano.webp"] and h.embed.image.url == "attachment://raca-humano.webp"
assert nomes(v) == ["raca-vampiro.jpg"] and nomes(d) == [] and d.embed.image.url is None
assert "Sem Disciplinas" in h.embed.fields[0].value and "Razão até 6" in h.embed.fields[0].value and "Fraquezas" not in h.embed.fields[0].value
assert "Sem magia inicial, só as classes Feiticeiros e Mestre de Forja têm" in h.embed.fields[0].value and "Tem magia inicial" not in h.embed.fields[0].value
vf = v.embed.fields[0].value
assert "4 pontos de Disciplina na criação (grau máximo 3)" in vf and "Força, Destreza e Vitalidade até 5" in vf and "Fraquezas: Sol, Prata, Fome" in vf
assert "Tem magia inicial (`/magia_inicial`)" in vf and "Sem magia inicial" not in vf
df = d.embed.fields[0].value
assert "3 pontos de Disciplina na criação (grau máximo 3), pode usar as dez" in df and "Limites de atributo ainda a definir" in df and "Sem Sol e sem Fome" in df
assert "Tem magia inicial (`/magia_inicial`)" in df and "Sem magia inicial" not in df                   # o Dhampir tem magia inicial

for estado, arq, rot in (("3º Estado", "estado-3.png", "3° Estado —  Camponeses"), ("2º Estado", "estado-2.png", "2° Estado —  Nobreza"), ("1º Estado", "estado-1.jpg", "1° Estado —  Clero")):
    c = vitrine.cartao_estado("Ana Ficha", estado, "Ana"); todos.append(c); e = c.embed
    assert e.title is None and rotulo_do_cartao(e) == rot and e.author.name.endswith("Classe Social de Ana Ficha")
    assert e.description == esperado_decorado("<:cruz1:1467276278418636953>", "<:calicesang:1467277986876358656>", lore.ESTADOS[estado]["rotulo"], lore.ESTADOS[estado]["texto"]) and e.fields == [] and e.footer.text == "jogador: Ana"
    assert nomes(c) == [arq] and e.image.url == f"attachment://{arq}" and e.thumbnail.url is None
for clero, r2 in (("Alto Clero", 63), ("Baixo Clero", 10)):
    c = vitrine.cartao_estado("Padre", "1º Estado", "Ana", clero, (2, 3)); todos.append(c); e = c.embed
    assert rotulo_do_cartao(e) == "1° Estado —  Clero" and "🎲" not in e.description and "1d100" not in e.description      # nenhum dos dois dados aparece
    assert [(f.name, f.value) for f in e.fields] == [(f"✝ {clero}", lore.CLERO[clero])] and nomes(c) == ["estado-1.jpg"] and e.footer.text == "jogador: Ana · tentativa 2 de 3"
c = vitrine.cartao_estado("Rara", dice.SOCIAL_CLASS_MASTER, "Ana", None, (3, 3)); todos.append(c); e = c.embed
assert e.title == "🎲 Resultado especial" and "Quem decide o Estado desse personagem é o mestre" in e.description and nomes(c) == [] and "100" not in e.description and e.footer.text.endswith("última chance")

CAMPOS_DA_HABILIDADE = {  # escritos à mão: os campos da habilidade que o cartão de cada classe tem (duas opções = tem o aviso de escolha)
    "Caçador": ["✨ Sem Dúvidas"], "Clérigo": ["Habilidade de classe", "✨ Mãos que Curam", "✨ Bênção"], "Feiticeiros": ["✨ Dom Nato"],
    "Ladrão": ["Habilidade de classe", "✨ Mão Leve", "✨ Língua de Prata"], "Mercenário": ["✨ Ombro a Ombro"],
    "Mestre de Forja": ["✨ Forja de Almas"], "Mundano": ["✨ Aprimoração"], "Sábio": ["✨ Saber e Poder"],
}
assert list(CAMPOS_DA_HABILIDADE) == list(rules.CLASSES)
for classe in rules.CLASSES:
    c = vitrine.cartao_classe("Ana Ficha", classe, "Próximo passo: `/atributos`, pra distribuir os pontos de atributo.", "Ana"); todos.append(c); e = c.embed
    b = rules.CLASSES[classe]
    assert e.title == classe and e.description == f"**{lore.CLASSE_FRASE[classe]}**\n{lore.DIVISOR}\n\n> *{lore.CLASSES[classe]}*" and nomes(c) == []
    assert [f.name for f in e.fields] == ["Vantagem nas perícias", "Bônus", "Combina com (exemplos)", *CAMPOS_DA_HABILIDADE[classe], "Continue a criação"]
    assert e.fields[2].value == " · ".join(lore.CLASSE_COMBINA[classe])
    assert e.fields[0].value == rules.CLASS_SKILLS[classe]
    assert e.fields[1].value == f"Vida +{b['vida']} · Sanidade +{b['sanidade']} · Mana +{b['mana']} · Estamina +{b['estamina']}"
for rank in dice.MAGIC_RANKS:
    c = vitrine.cartao_magia("Ana Ficha", rank, 50, "Ana"); todos.append(c); e = c.embed
    assert e.title == f"Rank {rank}" and e.color.value == lore.RANKS_MAGIA[rank]["cor"] and lore.TEXTO_MAGIA in e.description
chances = {r: vitrine._chance_do_rank(r) for r in dice.MAGIC_RANKS}
assert chances == {"Comum": 45, "Raro": 30, "Super Raro": 20, "Lendário": 4, "Mítico": 1} and sum(chances.values()) == 100
assert "★☆☆☆☆ · 45% de chance" in vitrine.cartao_magia("A", "Comum", 10, "J").embed.description
assert "🎲 1d100 = **10**" in vitrine.cartao_magia("A", "Comum", 10, "J").embed.description and vitrine.cartao_magia("A", "Comum", 10, "J").embed.description.startswith(lore.DIVISOR_CURTO)
assert "★★★★★ · 1% de chance" in vitrine.cartao_magia("A", "Mítico", 100, "J").embed.description
assert "★★★☆☆ · 20% de chance" in vitrine.cartao_magia("A", "Super Raro", 80, "J").embed.description
for c in todos: confere_limites(c.embed)
print("5. cartões OK:", len(todos), "cartões dentro dos limites do Discord")

# ---------- 6. o cartão de rolagem ----------
R = dice.RollResult
c = vitrine.cartao_rolagem("Kairon", "1d20+3", R("1d20+3", [12], 3, 20), "ataque", "Marcos", True); e = c.embed
assert e.title == "🎲 Kairon rolou 1d20+3" and e.description == "**12 + 3 = 15**" and e.footer.text == "ataque · jogador: Marcos" and c.arquivos == []
assert e.color == discord.Color.dark_red() and "files" not in c.kwargs()
e = vitrine.cartao_rolagem("Marcos", "1d6", R("1d6", [4], 0, 6), None, "Marcos", False).embed
assert e.footer.text is None and e.description == "**4 = 4**"
e = vitrine.cartao_rolagem("K", "1d20", R("1d20", [20], 0, 20), None, "M", True).embed
assert e.description == "**20 = 20**\n🌟 **20 natural!**" and e.color == discord.Color.gold()
e = vitrine.cartao_rolagem("K", "1d20+5", R("1d20+5", [1], 5, 20), None, "M", True).embed
assert e.description == "**1 + 5 = 6**\n💀 **1 natural!**" and e.color == discord.Color.dark_grey()
for r in (R("1d20", [20], 0, None), R("1d100", [20], 0, 100), R("1d6", [1], 0, 6), R("2d20", [20, 20], 0, 20), R("1d12", [12], 0, 12)):
    e = vitrine.cartao_rolagem("K", r.notation, r, None, "M", True).embed
    assert "natural" not in e.description, r.notation                    # o destaque é só do d20 sozinho
print("6. cartão de rolagem OK")

# ---------- 7. dados escritos no chat ----------
P = dice.parse_texto
casos = [
    ("d20", ("1d20", None, False)), ("D20", ("1d20", None, False)), ("1d20+5", ("1d20+5", None, False)),
    ("d20+5", ("1d20+5", None, False)), ("d20 + 5", ("1d20+5", None, False)), ("  d20 +5  ", ("1d20+5", None, False)),
    ("2d6-1", ("2d6-1", None, False)), ("2d6 - 1 + 3", ("2d6-1+3", None, False)), ("d100", ("1d100", None, False)),
    ("+d20+5", ("1d20+5", None, True)), ("+ d20 + 5", ("1d20+5", None, True)),
    ("+d20+5 ataque com a espada", ("1d20+5", "ataque com a espada", True)), ("+d20 ataque", ("1d20", "ataque", True)),
    ("+2d6 +1 dano\nda espada", ("2d6+1", "dano\nda espada", True)),
    # conversa normal NÃO pode rolar
    ("d20 é o melhor dado", None), ("d20+5 ataque", None), ("adoro d20", None), ("vou rolar d20", None), ("d20+5x", None),
    ("dado", None), ("d", None), ("d20d20", None), ("+", None), ("+5", None), ("bom dia", None), ("", None), (None, None), ("1d", None),
    ("https://exemplo.com/d20", None), ("d20?", None), ("d20!", None), ("@Ana d20", None), ("/rolar d20", None),
]
for texto, esperado in casos:
    got = P(texto); got = None if got is None else (got.notacao, got.motivo, got.explicito)
    assert got == esperado, (texto, got, esperado)
# a rolagem em si: vários modificadores, e o formato antigo continua igual
r = dice.roll("1d20+5-1"); assert r.modifier == 4 and r.sides == 20 and r.total == r.rolls[0] + 4
r = dice.roll("2d6 - 1 + 3"); assert r.modifier == 2 and len(r.rolls) == 2 and r.sides == 6
r = dice.roll("1d100-2"); assert r.modifier == -2 and r.describe().endswith("- 2")
r = dice.roll("d8"); assert r.modifier == 0 and len(r.rolls) == 1 and r.describe() == str(r.rolls[0])
for ruim in ("d1", "0d20", "101d6", "d1001", "abc", "d20++5", "1d20+", "d20 5"):
    try:
        dice.roll(ruim); raise SystemExit("deveria falhar: " + ruim)
    except dice.DiceError:
        pass
# tudo que parse_texto aceita ou é rolável, ou é recusado pelo dice.roll com mensagem clara (nunca estoura)
for lixo in ("d1", "0d20", "999d6", "d5000", "d0"):
    pedido = P(lixo)
    if pedido is None:
        continue
    try:
        dice.roll(pedido.notacao); raise SystemExit("deveria falhar: " + lixo)
    except dice.DiceError:
        pass
# a distribuição do d20 escrito no chat é a de um d20 de verdade
import collections
contagem = collections.Counter(dice.roll(P("d20").notacao).total for _ in range(20000))
assert set(contagem) == set(range(1, 21)) and min(contagem.values()) > 800
print("7. dados escritos no chat OK:", len(casos), "casos")

# ---------- 8. prévia de classe e resumo da ficha (mensagens privadas: nunca levam anexo) ----------
for classe in rules.CLASSES:
    e = vitrine.previa_classe("Ana Ficha", classe); confere_limites(e)
    assert e.title == f"🎓 {classe}" and e.author.name == "Classe de Ana Ficha" and e.description.startswith(f"**{lore.CLASSE_FRASE[classe]}**\n{lore.DIVISOR}\n\n> *{lore.CLASSES[classe][:40]}")
    assert [f.name for f in e.fields] == ["Vantagem nas perícias", "Bônus", "Combina com (exemplos)", *CAMPOS_DA_HABILIDADE[classe]] and e.image.url is None
    if rules.class_needs_ability_choice(classe): assert e.description.endswith("Escolhe a habilidade nos botões e depois confirma. Vale uma vez só, a classe e a habilidade juntas.")
    else: assert e.description.endswith("Se for essa, aperta **Confirmar classe**. Vale uma vez só.")
lore.IMAGENS_URL["classe-cacador"] = "https://exemplo.com/cacador.gif"
try:
    assert vitrine.previa_classe("A", "Caçador").image.url == "https://exemplo.com/cacador.gif"
finally:
    lore.IMAGENS_URL.pop("classe-cacador", None)
nova_ficha = dict(race=None, class_name=None, level=1)
assert vitrine.resumo_da_ficha(nova_ficha) == "Nível 1" and vitrine.cor_da_ficha(nova_ficha) == discord.Color.dark_purple().value
assert vitrine.resumo_da_ficha(dict(race="Vampiro", class_name="Caçador", level=4)) == "🩸 Vampiro · 🎓 Caçador · Nível 4"
assert vitrine.resumo_da_ficha(dict(race="Humano", class_name=None, level=2)) == "🕯️ Humano · Nível 2"
assert vitrine.cor_da_ficha(dict(race="Dhampir", class_name=None, level=1)) == lore.RACAS["Dhampir"]["cor"]
assert vitrine.miniatura_da_ficha(dict(race="Humano")) is None and vitrine.miniatura_da_ficha(dict(race=None)) is None    # arquivo de assets/ não vira miniatura
print("8. prévia de classe e resumo da ficha OK")

# ---------- 9. enfeites, itálico, rodapé com a tentativa e o resultado atual ----------
assert all("*" not in t for t in tudo)                                                                  # os textos não têm asterisco (senão quebrava o itálico)
assert vitrine._citar("um\n\ndois", True) == "> *um*\n>\n> *dois*" and vitrine._citar("um") == "> um"
assert vitrine._rodape("Ana") == "jogador: Ana" and vitrine._rodape("Ana", (1, 3)) == "jogador: Ana · tentativa 1 de 3"
assert vitrine._rodape("Ana", (2, 3)) == "jogador: Ana · tentativa 2 de 3" and vitrine._rodape("Ana", (3, 3)) == "jogador: Ana · última chance"
assert lore.DIVISOR.startswith("✦") and lore.DIVISOR.endswith("✦") and len(lore.DIVISOR) <= 30 and len(lore.DIVISOR_CURTO) < len(lore.DIVISOR)
assert vitrine.resultado_atual(dict(race="Vampiro"), "race") == "Vampiro"
assert vitrine.resultado_atual(dict(social_class="3º Estado", clergy=None), "social_class") == "3º Estado · Camponeses"
assert vitrine.resultado_atual(dict(social_class="1º Estado", clergy="Alto Clero"), "social_class") == "1º Estado · Clero (Alto Clero)"
assert vitrine.resultado_atual(dict(social_class=dice.SOCIAL_CLASS_MASTER, clergy=None), "social_class") == "a decidir pelo mestre"
print("9. enfeites, rodapé e resultado atual OK")

# ---------- 10. Disciplinas: lista, detalhe e resumo da ficha ----------
graus = {"Potência": 2, "Celeridade": 1, "Regeneração": 2}
assert vitrine.barra_de_grau(0) == "▱" * 5 and vitrine.barra_de_grau(2) == "▰▰▱▱▱" and vitrine.barra_de_grau(5) == "▰" * 5
assert vitrine.linha_de_pontos(1, "Vampiro", {}) == "Pontos: 0 de 4 usados (4 livres)" and vitrine.linha_de_pontos(1, "Dhampir", {"Potência": 2, "Celeridade": 1}) == "Pontos: 3 de 3 usados"
assert vitrine.linha_de_pontos(1, "Vampiro", {"Potência": 3, "Celeridade": 1}) == "Pontos: 4 de 4 usados" and vitrine.linha_de_pontos(1, "Vampiro", {"Potência": 3, "Celeridade": 1, "Domínio": 1}) == "Pontos: 5 de 4 usados (passou 1)"
assert vitrine.linha_de_pontos(1, "Vampiro", {"Potência": 3}) == "Pontos: 3 de 4 usados (1 livre)"
f = dict(level=3, race="Vampiro")
assert vitrine.texto_disciplinas_da_ficha(f, {}) == "Pontos: 0 de 5 usados (5 livres)\nnenhuma ainda (o botão **Disciplinas** do `/minha_ficha` abre o painel)"
assert vitrine.texto_disciplinas_da_ficha(f, graus) == "Pontos: 5 de 5 usados\n**Potência** 2/5 ▰▰▱▱▱\n**Celeridade** 1/5 ▰▱▱▱▱\n**Regeneração** 2/5 ▰▰▱▱▱"
# a lista: quem tem Disciplinas vê os graus; quem não tem só lê o tema
e = vitrine.embed_disciplinas("Vlad", "Vampiro", 3, graus); confere_limites(e)
assert e.title == "🩸 Disciplinas de Vlad" and "Pontos: 5 de 5 usados" in e.description and [x.name for x in e.fields] == list(rules.DISCIPLINES) and all(x.inline for x in e.fields)
por_nome = {x.name: x.value for x in e.fields}
assert por_nome["Potência"] == "▰▰▱▱▱ 2/5\nForça sobrenatural bruta" and por_nome["Ofuscação"].startswith("▱▱▱▱▱ 0/5") and por_nome["Sanguessugia"] == "⏳ em desenvolvimento"
e = vitrine.embed_disciplinas("Ana", "Humano", 1, {}); confere_limites(e)
assert e.title == "🩸 Disciplinas" and "Só **Vampiros e Dhampirs** têm Disciplinas" in e.description and "0/5" not in " ".join(x.value for x in e.fields)
assert {x.name: x.value for x in e.fields}["Potência"] == "Força sobrenatural bruta"
assert vitrine.embed_disciplinas(None, None, 1, {}).title == "🩸 Disciplinas"
# o detalhe de cada Disciplina: os três graus, o 4 e 5 em aberto, e a marcação do que o personagem já tem
for disciplina in rules.DISCIPLINES:
    e = vitrine.embed_disciplina(disciplina, 1, "Pontos: 1 de 4 usados (3 livres)", "🔒 exemplo"); confere_limites(e)
    assert e.title == f"🩸 {disciplina}" and e.footer.text == "Pontos: 1 de 4 usados (3 livres)" and e.fields[-1].name == "Pra subir"
    assert e.description.startswith(f"{lore.DIVISOR_CURTO}\n\n> *") and any(x.name == "Graus 4 e 5" and x.value == lore.GRAUS_4_E_5 for x in e.fields)
e = vitrine.embed_disciplina("Potência", 2)
assert [x.name for x in e.fields] == ["✅ Grau 1", "✅ Grau 2", "▫️ Grau 3", "Graus 4 e 5"] and e.fields[0].value == "Dobra o modificador de Força no dano das armas." and e.footer.text is None
assert [x.name for x in vitrine.embed_disciplina("Potência", 0).fields][:3] == ["▫️ Grau 1", "▫️ Grau 2", "▫️ Grau 3"]
assert [x.name for x in vitrine.embed_disciplina("Potência", None).fields][:3] == ["Grau 1", "Grau 2", "Grau 3"]           # quem só lê: sem marcação
assert [x.name for x in vitrine.embed_disciplina("Regeneração", 3).fields] == ["✅ Grau 1", "✅ Grau 2", "✅ Grau 3", "Graus 4 e 5", "Limite"]
assert vitrine.embed_disciplina("Regeneração", 0).fields[-1].value == "Dano de Sol, Prata, Água Sagrada e Armas Sagradas não se regenera."
e = vitrine.embed_disciplina("Sanguessugia", 0)                                                                              # bloqueada: nada inventado
assert [x.name for x in e.fields] == ["⏳ Em desenvolvimento", "Graus 4 e 5"] and "Grau 1" not in " ".join(x.name for x in e.fields) and "ainda não foram definidos" in e.fields[0].value
import rules as _r
_r.SANGUESSUGIA_LIBERADA = True
try:
    lore.DISCIPLINAS["Sanguessugia"]["graus"] = {1: "x", 2: "y", 3: "z"}
    assert [x.name for x in vitrine.embed_disciplina("Sanguessugia", 1).fields][:3] == ["✅ Grau 1", "▫️ Grau 2", "▫️ Grau 3"]
    assert "em desenvolvimento" not in {x.name: x.value for x in vitrine.embed_disciplinas("A", "Vampiro", 1, {}).fields}["Sanguessugia"]
finally:
    _r.SANGUESSUGIA_LIBERADA = False; lore.DISCIPLINAS["Sanguessugia"]["graus"] = None
print("10. Disciplinas (cartões) OK")

# ---------- 11. cartão do resultado especial (66 e 77): tudo interrogação ----------
def texto_do_cartao(e): return " ".join([e.title or "", e.author.name or "", e.description or "", e.footer.text or ""] + [f.name + f.value for f in e.fields])
for valor, cor in ((66, 0xC0392B), (77, 0xF1C40F)):
    ct = vitrine.cartao_especial(valor); e = ct.embed; tudo = texto_do_cartao(e)
    assert e.color.value == cor and lore.ESPECIAL[valor]["cor"] == cor and nomes(ct) == []              # 66 vermelho, 77 amarelo, sem imagem enquanto não existir
    assert "?" in tudo and not any(ch.isalnum() for ch in tudo)                                       # nenhuma letra nem número: só interrogação e enfeite
    assert "—" not in tudo and "–" not in tudo
    confere_limites(e)
a, b = vitrine.cartao_especial(66).embed, vitrine.cartao_especial(77).embed
assert texto_do_cartao(a) == texto_do_cartao(b) and a.color.value != b.color.value                    # o texto é o mesmo, só a cor muda
assert vitrine.chave_de_imagem("especial", "66") == "especial-66"
lore.IMAGENS_URL["especial-77"] = "https://exemplo.com/especial.png"                                  # com o desenho, ele entra no cartão
try: assert vitrine.cartao_especial(77).embed.image.url == "https://exemplo.com/especial.png" and vitrine.cartao_especial(66).embed.image.url is None
finally: del lore.IMAGENS_URL["especial-77"]
try: vitrine.cartao_especial(65); raise SystemExit("65 não é especial")
except KeyError: pass
print("11. cartão especial OK")

# ---------- 12. estilo decorado: o rótulo enfeitado e a chave do texto pequeno ----------
E = vitrine.enfeitar_rotulo
assert E("Humanos") == "\U0001D407umanos" and E("Vampiros") == "\U0001D415ampiros"                        # só a inicial vira negrito matemático
assert E(f"1° Estado {lore.TRAVESSAO}  Clero") == "\U0001D7CF° \U0001D404stado " + lore.TRAVESSAO + "  \U0001D402lero"     # o número também, e os dois espaços do meio ficam
assert E("Mestre de Forja") == "\U0001D40Cestre de \U0001D405orja" and E("ação livre") == "ação livre"      # sem maiúscula ASCII, não muda
assert E("") == "" and E("3º Estado") == "\U0001D7D1º \U0001D404stado"
assert unicodedata.normalize("NFKC", E("Mestre de Forja")) == "Mestre de Forja"                            # some o enfeite, sobra o texto
# a chave TEXTO_PEQUENO: sem ela, o "-#" some e o resto fica igual
texto_pequeno = lore.TEXTO_PEQUENO
try:
    lore.TEXTO_PEQUENO = True; com = vitrine.cartao_raca("X", "Humano", "J").embed.description
    lore.TEXTO_PEQUENO = False; sem = vitrine.cartao_raca("X", "Humano", "J").embed.description
finally:
    lore.TEXTO_PEQUENO = texto_pequeno
assert "> -# " in com and "-#" not in sem and com.replace("> -# ", "> ") == sem
# texto de mais de um parágrafo: cada linha vira uma citação, e só a primeira leva o emoji
duas = vitrine._citar_decorado("Primeira linha.\nSegunda linha.", "<:x:1>").split("\n")
assert len(duas) == 2 and duas[0].startswith("> -# <:x:1>      ") and duas[1].startswith("> -# ") and "<:x:1>" not in duas[1] and duas[1].endswith("**Segunda linha.**")
# o cabeçalho tem o emoji na frente e o ornamento no fim
cab = vitrine._cabecalho("Humanos", "<:cruz2:1>")
assert cab.startswith("<:cruz2:1>" + " " * 12 + lore.PREENCHE * 5 + lore.ORNAMENTO_L + lore.NULO * 8) and cab.endswith(lore.NULO * 3 + lore.PREENCHE * 2 + " " + lore.PREENCHE * 2 + lore.HIEROGLIFO)
# as classes, a magia e o 100 continuam no estilo de antes (o estilo novo vale só pra raça e Estado, por enquanto)
assert vitrine.cartao_classe("X", "Sábio", "p", "J").embed.title == "Sábio" and vitrine.cartao_estado("X", dice.SOCIAL_CLASS_MASTER, "J").embed.title == "🎲 Resultado especial"
print("12. estilo decorado OK")

# ---------- 13. a habilidade de classe ----------
cacador = vitrine.cartao_classe("Ana", "Caçador", "x", "Ana").embed
assert cacador.fields[3].value == "\n".join([
    "*Inicial · Passiva · Físico · Custo: 10 Estamina no Efeito²*",
    "*Antes de iniciar uma caçada, o caçador precisa saber separar o que é mundano do que é profano: o que é obra do homem e da natureza e o que vem de bruxos e demônios. Uma vez confirmada a presença das trevas, a investigação começa.*",
    "**Efeito¹** Ao iniciar uma cena de investigação, recebe vantagem para descobrir se algo é profano ou não natural. Não gasta nada.",
    "**Efeito² (Presa Marcada)** Ao confirmar que um alvo é sobrenatural, o caçador o marca, gastando 10 de Estamina. Tem vantagem nos ataques e em Percepção contra ele até o fim da cena, e só mantém uma marca por vez.",
])
sem = vitrine.cartao_classe("Ana", "Clérigo", "x", "Ana").embed
assert sem.fields[3].value == "Escolha uma das duas: **Mãos que Curam** ou **Bênção**. Use `/habilidade` pra escolher." and not any("✅" in f.name for f in sem.fields)
com = vitrine.cartao_classe("Ana", "Clérigo", "x", "Ana", "Bênção").embed
assert com.fields[3].value == "Você levou **Bênção**." and [f.name for f in com.fields[4:6]] == ["✨ Mãos que Curam", "✨ Bênção ✅"]
assert com.fields[5].value.startswith("*Inicial · Ativa · Fé · Custo: 10 Mana*\n*Um gesto, uma palavra, e a arma passa a servir a algo maior do que quem a empunha.*\n**Efeito¹** Gasta 10 de Mana")
h = vitrine.cartao_habilidade("Padre", "Mestre de Forja", None, "Ana"); e = h.embed
assert e.title == "Mestre de Forja" and e.author.name == "✨ Habilidade de Padre" and e.footer.text == "jogador: Ana" and nomes(h) == []
assert e.description == f"**Almas na bigorna**\n{lore.DIVISOR}" and [f.name for f in e.fields] == ["✨ Forja de Almas"] and "**Efeito³ (O preço)**" in e.fields[0].value
assert [f.name for f in vitrine.cartao_habilidade("P", "Ladrão", "Mão Leve").embed.fields] == ["Habilidade de classe", "✨ Mão Leve ✅", "✨ Língua de Prata"]
assert vitrine.cartao_habilidade("P", "Sábio", None).embed.footer.text is None
# um campo nunca passa dos 1024 do Discord: um texto mais comprido continua no campo seguinte
lore.HABILIDADES["Teste"] = {"escolha": False, "opcoes": [{"nome": "Longa", "marcas": ["Inicial"], "frase": "f" * 300, "efeitos": [("Efeito¹", "a" * 400), ("Efeito²", "b" * 400), ("Efeito³", "c" * 400), ("Efeito⁴", "d" * 400)]}]}
try:
    campos = vitrine._campos_da_habilidade("Teste")
    assert [c[0] for c in campos] == ["✨ Longa", "✨ Longa (continua)", "✨ Longa (continua)"]
    assert [len(c[1]) for c in campos] == [725, 825, 412]                                                    # marcas + frase + Efeito¹ / Efeito² + Efeito³ / Efeito⁴
    assert all(c[1].startswith("*Inicial*\n*fff") for c in campos[:1]) and campos[1][1].startswith("**Efeito²**") and campos[2][1].startswith("**Efeito⁴**")
    assert all(letra * 400 in "".join(c[1] for c in campos) for letra in "abcd")                             # nada se perdeu no corte
finally:
    del lore.HABILIDADES["Teste"]
for classe in rules.CLASSES:                                                                                  # os dados do lore batem com as regras
    hab = lore.HABILIDADES[classe]
    assert [o["nome"] for o in hab["opcoes"]] == list(rules.CLASS_ABILITIES[classe]) and hab["escolha"] == rules.class_needs_ability_choice(classe), classe
    assert lore.CLASSE_FRASE[classe].strip() and lore.CLASSE_COMBINA[classe] and all(o["marcas"] and o["frase"].strip() and o["efeitos"] for o in hab["opcoes"])
    assert all(rot.startswith("Efeito") and txt.strip() for o in hab["opcoes"] for rot, txt in o["efeitos"]), classe
    assert "—" not in str(hab) and "—" not in lore.CLASSES[classe]
    for e in (vitrine.cartao_classe("X", classe, "p", "J").embed, vitrine.cartao_habilidade("X", classe, None, "J").embed, vitrine.previa_classe("X", classe)): confere_limites(e)
assert "secreto" not in str(lore.HABILIDADES).casefold() and "sanguessugia" not in str(lore.HABILIDADES).casefold()     # o combo secreto dos Feiticeiros não aparece em texto de jogador
assert [lore.CLASSE_FRASE[c] for c in rules.CLASSES] == ["Fé e violência", "Cura e fé", "Estudo proibido", "Sombra e lábia", "Corpo e espada", "Almas na bigorna", "Ainda sem lugar", "Saber e dúvida"]
print("13. habilidades de classe OK")

# ---------- 14. cartões de rolagem: a marca de sorte e o N#dado ----------
e = vitrine.cartao_rolagem("Kairon", "1d20+5", R("1d20+5", [15], 5, 20), None, "Marcos", True, ["vantagem (4 e 15)"]).embed
assert e.description == "**15 + 5 = 20**\n🍀 vantagem (4 e 15)"
e = vitrine.cartao_rolagem("Kairon", "1d20", R("1d20", [20], 0, 20), None, "Marcos", True, ["dado fixo em 20", "+3"]).embed
assert e.description == "**20 = 20**\n🌟 **20 natural!**\n🍀 dado fixo em 20 · +3"
assert vitrine.cartao_rolagem("K", "1d20", R("1d20", [9], 0, 20), None, "M", True, []).embed.description == "**9 = 9**" and vitrine.cartao_rolagem("K", "1d20", R("1d20", [9], 0, 20), None, "M", True).embed.description == "**9 = 9**"
tres = [R("d20+5", [14], 5, 20), R("d20+5", [1], 5, 20), R("d20+5", [20], 5, 20)]
c = vitrine.cartao_rolagens("Kairon", "3#d20+5", tres, "ataque", "Marcos", True); e = c.embed; confere_limites(e)
assert e.title == "🎲 Kairon rolou 3#d20+5" and e.footer.text == "ataque · jogador: Marcos" and nomes(c) == [] and e.color == discord.Color.gold()
assert e.description == "**1.** 14 + 5 = **19**\n**2.** 1 + 5 = **6** 💀\n**3.** 20 + 5 = **25** 🌟\n\n⬆️ Maior **25** · ⬇️ Menor **6**"
e = vitrine.cartao_rolagens("K", "2#d20", [R("d20", [10], 0, 20), R("d20", [2], 0, 20)], None, "M", False, [["vantagem (4 e 10)"], []]).embed
assert e.description == "**1.** 10 = **10** · 🍀 vantagem (4 e 10)\n**2.** 2 = **2**\n\n⬆️ Maior **10** · ⬇️ Menor **2**" and e.footer.text is None and e.color == discord.Color.dark_red()
e = vitrine.cartao_rolagens("K", "2#1d6", [R("1d6", [6], 0, 6), R("1d6", [1], 0, 6)], None, "M", True).embed
assert "🌟" not in e.description and "💀" not in e.description and e.color == discord.Color.dark_red()        # o destaque é só de d20
e = vitrine.cartao_rolagens("K", "10#d20", [R("d20", [10], 0, 20)] * 10, None, "M", True).embed; confere_limites(e); assert e.description.count("**") == 10 * 4 + 4
print("14. cartões de rolagem OK")

# ---------- 15. classe e habilidade escolhidas juntas (botões) ----------
pv = vitrine.previa_classe("Ana", "Clérigo"); confere_limites(pv)
assert [f.name for f in pv.fields][3:] == ["Habilidade de classe", "✨ Mãos que Curam", "✨ Bênção"]
assert pv.fields[3].value == "Escolha uma das duas: **Mãos que Curam** ou **Bênção**. Aperta um dos botões abaixo."              # sem marcar: manda apertar os botões
pv = vitrine.previa_classe("Ana", "Clérigo", "Bênção"); confere_limites(pv)
assert pv.fields[3].value == "Você vai levar **Bênção**. Confirma nos botões abaixo." and [f.name for f in pv.fields][4:] == ["✨ Mãos que Curam", "✨ Bênção ✅"]
assert pv.description.endswith("Se for essa, aperta **Confirmar classe e habilidade**. Vale uma vez só.")
assert vitrine.previa_classe("Ana", "Caçador", "Sem Dúvidas").fields[3].name == "✨ Sem Dúvidas" and "✅" not in " ".join(f.name for f in vitrine.previa_classe("Ana", "Caçador").fields)   # uma habilidade só: nada a marcar
# o cartão da classe: com botões (falta escolher), sem botões, e já escolhida
assert vitrine.cartao_classe("Ana", "Ladrão", "p", "J", None, com_botoes=True).embed.fields[3].value == "Escolha uma das duas: **Mão Leve** ou **Língua de Prata**. Aperta um dos botões abaixo."
assert vitrine.cartao_classe("Ana", "Ladrão", "p", "J").embed.fields[3].value == "Escolha uma das duas: **Mão Leve** ou **Língua de Prata**. Use `/habilidade` pra escolher."
assert vitrine.cartao_classe("Ana", "Ladrão", "p", "J", "Mão Leve", com_botoes=False).embed.fields[3].value == "Você levou **Mão Leve**."
assert vitrine.cartao_habilidade("Ana", "Clérigo", None, "J", "botao").embed.fields[0].value == "Escolha uma das duas: **Mãos que Curam** ou **Bênção**. Aperta um dos botões abaixo."
assert vitrine.cartao_habilidade("Ana", "Clérigo", "Bênção", "J", "previa").embed.fields[0].value == "Você vai levar **Bênção**. Confirma nos botões abaixo."
assert vitrine.cartao_habilidade("Ana", "Clérigo", "Bênção", "J").embed.fields[0].value == "Você levou **Bênção**."
print("15. classe e habilidade juntas OK")

print("\nTODOS OS TESTES DA VITRINE PASSARAM")
