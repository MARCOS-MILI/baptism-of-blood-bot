"""Testes dos textos da ajuda (ajuda.py). Não conecta no Discord.
Rodar da pasta do bot: python tests/test_ajuda.py
(O teste de que TODO comando de verdade tem ajuda, e de que os exemplos usam opções que existem, está em test_bot.py.)"""
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import ajuda
import dice
import rules

base = dict(race=None, magic_rank=None, social_class=None, class_name=None, **{f"attr_{a}": 0 for a in rules.ATTRIBUTES})
st = lambda **k: rules.creation_status({**base, **k})

# ---------- passo a passo: um item por passo, com o ícone certo ----------
SORTEIOS = dict(race="Humano", social_class="3º Estado")
l = ajuda.linhas_passo_a_passo(st())
assert l == [
    "✅ Personagem criado",
    "▶️ Sortear a raça: `/raca_inicial`",
    "⬜ Sortear a classe social: `/classe_social`",
    "🔒 Escolher a classe: depois de sortear a raça e a classe social",
    "🔒 Sortear o Rank de magia: depois de sortear a raça e a classe social e de escolher a classe",
    "🔒 Distribuir os pontos de atributo: depois de sortear a raça e a classe social, de escolher a classe e de sortear o Rank de magia",
], l
assert ajuda.proximo_passo(st()) == "Próximo passo: `/raca_inicial`, pra sortear a raça (a raça e a classe social podem ser sorteadas em qualquer ordem)."
l = ajuda.linhas_passo_a_passo(st(race="Humano"))                                                      # o "próximo" pula o que já foi feito
assert l[1] == "✅ Sortear a raça" and l[2] == "▶️ Sortear a classe social: `/classe_social`" and l[3] == "🔒 Escolher a classe: depois de sortear a classe social"
l = ajuda.linhas_passo_a_passo(st(**SORTEIOS))
assert l[3] == "▶️ Escolher a classe: `/classe`" and l[4] == "🔒 Sortear o Rank de magia: depois de escolher a classe"
assert ajuda.proximo_passo(st(**SORTEIOS)) == "Próximo passo: `/classe`, pra escolher a classe."
# quem NÃO tem magia (Humano Mundano): o passo do Rank de magia aparece como "não vale", e os atributos abrem
l = ajuda.linhas_passo_a_passo(st(**SORTEIOS, class_name="Mundano"))
assert l[3] == "✅ Escolher a classe" and l[4] == "➖ Rank de magia: a sua raça e a sua classe não têm magia, então esse passo não vale pra você"
assert l[5] == "▶️ Distribuir os pontos de atributo: `/atributos` (0 de 6 pontos usados)"
assert ajuda.proximo_passo(st(**SORTEIOS, class_name="Mundano")) == "Próximo passo: `/atributos`, pra distribuir os pontos de atributo."
# quem TEM magia: o Rank de magia é o próximo, e os atributos esperam
for dados in (dict(class_name="Feiticeiros"), dict(class_name="Mestre de Forja"), dict(race="Vampiro", class_name="Mundano")):
    c = st(**{**SORTEIOS, **dados}); l = ajuda.linhas_passo_a_passo(c)
    assert l[4] == "▶️ Sortear o Rank de magia: `/magia_inicial`" and l[5] == "🔒 Distribuir os pontos de atributo: depois de sortear o Rank de magia", dados
    assert ajuda.proximo_passo(c) == "Próximo passo: `/magia_inicial`, pra sortear o Rank de magia.", dados
l = ajuda.linhas_passo_a_passo(st(**SORTEIOS, class_name="Feiticeiros", magic_rank="Raro", attr_forca=2))
assert l[4] == "✅ Sortear o Rank de magia" and l[-1] == "▶️ Distribuir os pontos de atributo: `/atributos` (2 de 6 pontos usados)"
# Rank guardado de quem não tem magia (dado antigo): aparece como feito, não como "não vale"
assert ajuda.linhas_passo_a_passo(st(**SORTEIOS, class_name="Mundano", magic_rank="Raro"))[4] == "✅ Sortear o Rank de magia"
pronta = st(**SORTEIOS, class_name="Feiticeiros", magic_rank="Raro", attr_forca=2, attr_vitalidade=3, attr_vontade=1)
assert set(x[0] for x in ajuda.linhas_passo_a_passo(pronta)) == {"✅"} and ajuda.proximo_passo(pronta) == "A ficha está pronta e tudo está liberado."
# classe feita por um mestre sem os sorteios: o resto continua fechado e o texto diz o que falta de verdade
l = ajuda.linhas_passo_a_passo(st(class_name="Sábio"))
assert l[3] == "✅ Escolher a classe" and l[4] == "🔒 Sortear o Rank de magia: depois de sortear a raça e a classe social"
assert l[-1] == "🔒 Distribuir os pontos de atributo: depois de sortear a raça e a classe social e de sortear o Rank de magia"
# 100 na classe social: o mestre decide
s100 = st(race="Humano", social_class=dice.SOCIAL_CLASS_MASTER)
l = ajuda.linhas_passo_a_passo(s100)
assert l[2] == "⏳ Classe social: você tirou 100, então um mestre vai definir o seu Estado" and l[3].startswith("🔒 Escolher a classe")
assert ajuda.proximo_passo(s100) == "Agora é com um mestre: fala com ele pra definir o seu Estado, e aí você segue."
print("1. passo a passo OK")

# ---------- textos de bloqueio ----------
t = ajuda.texto_bloqueio("Kairon Flagon", st())
assert t.startswith("🔒 A ficha de **Kairon Flagon** ainda não está pronta, e esse comando só abre quando ela estiver.")
assert "▶️ Sortear a raça: `/raca_inicial`" in t and "Próximo passo: `/raca_inicial`" in t and t.endswith("use `/ajuda`.") and len(t) < 1500
t = ajuda.texto_falta_para("classe", st())
assert t.startswith("Ainda não dá pra usar `/classe`: a criação tem uma ordem") and "🔒 Escolher a classe: depois de sortear a raça e a classe social" in t
t = ajuda.texto_falta_para("magia", st(**SORTEIOS))
assert t.startswith("Ainda não dá pra usar `/magia_inicial`") and "▶️ Escolher a classe: `/classe`" in t and t.endswith("pra escolher a classe.")
t = ajuda.texto_falta_para("atributos", st(**SORTEIOS, class_name="Feiticeiros"))
assert "`/atributos`" in t and "▶️ Sortear o Rank de magia: `/magia_inicial`" in t
# quem não tem magia tenta o /magia_inicial
t = ajuda.texto_sem_magia("Ana", "Humano", "Mundano", st(**SORTEIOS, class_name="Mundano"))
assert t.startswith("🚫 **Ana** não sorteia o Rank de magia: só tem magia quem é Vampiro ou Dhampir (de qualquer classe) ou das classes Feiticeiros e Mestre de Forja")
assert "essa combinação é Humano com Mundano. Esse passo não vale pra esse personagem." in t and t.endswith("Próximo passo: `/atributos`, pra distribuir os pontos de atributo.")
s100b = st(race="Humano", social_class=dice.SOCIAL_CLASS_MASTER, class_name="Feiticeiros")
t = ajuda.texto_falta_para("classe", st(race="Humano", social_class=dice.SOCIAL_CLASS_MASTER))
assert t == ("Ainda não dá pra usar `/classe`: você tirou 100 no sorteio da classe social, então um mestre precisa definir o seu "
             "Estado primeiro. Fala com ele.")
print("2. textos de bloqueio OK")

# ---------- achar o comando pelo que a pessoa digitou ----------
assert ajuda.achar("atributos") == ("atributos", []) and ajuda.achar("/atributos") == ("atributos", []) and ajuda.achar("  /ROLAR  ") == ("rolar", [])
assert ajuda.achar("mestre dar_xp") == ("mestre dar_xp", []) and ajuda.achar("/mestre   dar_xp") == ("mestre dar_xp", [])
assert ajuda.achar("dar_xp") == ("mestre dar_xp", [])                                       # só o final, se for único
assert ajuda.achar("criar") == ("personagem criar", []) and ajuda.achar("exportar") == ("mestre exportar", [])
assert ajuda.achar("extrato") == ("extrato_xp", [])                                         # um pedaço, se só um combinar
assert ajuda.achar("atributos")[0] == "atributos"                                           # o nome exato ganha de "mestre atributos"
assert ajuda.achar("ficha") == ("minha_ficha", [])                                          # comando de jogador tem preferência
assert ajuda.achar("mestre ficha") == ("mestre ficha", []) and ajuda.achar("excluir") == ("personagem excluir", [])
chave, sug = ajuda.achar("personagem"); assert chave is None and len(sug) == 4 and all(x.startswith("personagem ") for x in sug)   # ambíguo: sugere
chave, sug = ajuda.achar("mestre"); assert chave is None and len(sug) == 5 and all(x.startswith("mestre ") for x in sug)
chave, sug = ajuda.achar("corrigir"); assert chave is None and len(sug) == 5 and all("corrigir" in x for x in sug)   # muitas: no máximo 5
assert ajuda.achar("xyzabc") == (None, []) and ajuda.achar("") == (None, []) and ajuda.achar("   ") == (None, [])
print("3. achar comando OK")

# ---------- sugestões do autocomplete ----------
tudo = ajuda.sugestoes("", incluir_mestre=True)
assert len(tudo) == 25 and tudo[:6] == ["personagem criar", "raca_inicial", "classe_social", "classe", "habilidade", "magia_inicial"]           # sem digitar, começa pelo passo a passo
jogador = ajuda.sugestoes("", incluir_mestre=False)
assert jogador == [k for k in ajuda.ORDEM_SUGESTAO if k in ajuda.AJUDA] and not any(k.startswith("mestre ") for k in jogador)
assert ajuda.sugestoes("atrib", False) == ["atributos"] and ajuda.sugestoes("atrib", True) == ["atributos", "mestre atributos"]
assert ajuda.sugestoes("dar_xp", False) == [] and ajuda.sugestoes("dar_xp", True) == ["mestre dar_xp"]      # mestre só aparece pra mestre
assert ajuda.sugestoes("/PERSONAGEM", False) == ["personagem criar", "personagem usar", "personagem listar", "personagem excluir"]
assert ajuda.sugestoes("zzz", True) == [] and all(len(x) <= 25 for x in (tudo, jogador))
todos = set(ajuda.sugestoes("", True)) | set(ajuda.sugestoes("mestre", True)) | set(ajuda.sugestoes("personagem", True))
print("4. sugestões OK")

# ---------- as entradas em si ----------
for chave, e in ajuda.AJUDA.items():
    assert set(e) >= {"grupo", "resumo", "uso", "detalhes"} and set(e) <= {"grupo", "resumo", "uso", "detalhes", "requisito"}, chave
    assert e["grupo"] in {g for g, _ in ajuda.GRUPOS} | {"mestre"}, chave
    assert (e["grupo"] == "mestre") == chave.startswith("mestre "), chave
    assert e["uso"].startswith("/" + chave) and not e["resumo"].endswith(".") and 10 <= len(e["resumo"]) <= 90, chave
    assert len(e["detalhes"]) <= 600 and e["detalhes"].strip() == e["detalhes"], chave
    for t in (e["resumo"], e["uso"], e["detalhes"], e.get("requisito", "")):
        assert "—" not in t and "–" not in t, (chave, t)                                    # sem travessão
# todo comando de mestre aparece em exatamente um subgrupo do /ajuda geral
listados = [f"mestre {c}" for _, cmds in ajuda.MESTRE_SUBGRUPOS for c in cmds]
assert sorted(listados) == sorted(k for k in ajuda.AJUDA if k.startswith("mestre ")) and len(set(listados)) == len(listados)
assert set(ajuda.ORDEM_SUGESTAO) <= set(ajuda.AJUDA)
print("5. entradas OK:", len(ajuda.AJUDA), "comandos")

# ---------- detalhe de um comando ----------
d = ajuda.detalhe("atributos")
assert d["titulo"] == "📖 /atributos" and d["descricao"].startswith("Distribui os pontos de atributo.\n\n")
assert d["campos"][0] == ("Como usar", "`/atributos forca:2 vitalidade:3 vontade:1`") and d["campos"][1][0] == "Quando dá pra usar"
assert [c[0] for c in ajuda.detalhe("ajuda")["campos"]] == ["Como usar"]                       # sem requisito, sem campo extra
m = ajuda.detalhe("mestre dar_xp"); assert m["campos"][-1] == ("Quem usa", "Só quem tem o cargo de mestre ou a permissão de Gerenciar Servidor.")
assert "Quem usa" not in [c[0] for c in ajuda.detalhe("rolar")["campos"]]
print("6. detalhe OK")

# ---------- visão geral: cabe nos limites do Discord em qualquer situação ----------
def cabe(v):
    assert len(v["titulo"]) <= 256 and len(v["descricao"]) <= 4096
    total = len(v["titulo"]) + len(v["descricao"])
    for nome, valor in v["campos"]:
        assert 0 < len(nome) <= 256 and 0 < len(valor) <= 1024, (nome, len(valor))
        total += len(nome) + len(valor)
    assert len(v["campos"]) <= 25 and total <= 6000, total
    return total
situacoes = [(None, False), (st(), True), (st(**SORTEIOS), True), (s100, True), (pronta, True),
             (st(**SORTEIOS, class_name="Mundano"), True), (st(race="Vampiro", social_class="3º Estado", class_name="Ladrão"), True)]
for status, tem in situacoes:
    for mestre in (False, True):
        cabe(ajuda.visao_geral(status, tem, mestre))
v = ajuda.visao_geral(None, False, False)
assert [c[0] for c in v["campos"]] == ["Seu passo a passo"] + [t for _, t in ajuda.GRUPOS]
assert "/personagem criar" in v["campos"][0][1] and "/ajuda comando:atributos" in v["descricao"]
assert ajuda.visao_geral(pronta, True, False)["campos"][0][1] == "✅ Ficha pronta. Todos os comandos estão liberados."
assert "▶️ Sortear a raça: `/raca_inicial`" in ajuda.visao_geral(st(), True, False)["campos"][0][1]
vm = ajuda.visao_geral(pronta, True, True); assert "Comandos de mestre" not in [c[0] for c in vm["campos"]] and "/mestre dar_xp" not in str(vm) and "`/mestre ajuda`" in vm["descricao"]      # a ajuda geral não lista mais os comandos de mestre
assert "/mestre" not in str(ajuda.visao_geral(pronta, True, False)) and "omandos de mestre" not in str(ajuda.visao_geral(pronta, True, False))      # e quem não é mestre nem vê que eles existem
assert "Comandos de mestre" not in [c[0] for c in ajuda.visao_geral(pronta, True, False)["campos"]]
print("7. visão geral OK (maior resposta:", max(cabe(ajuda.visao_geral(s, t, m)) for s, t in situacoes for m in (False, True)), "de 6000 caracteres)")

# ---------- 8. resultado especial (66 e 77): o passo espera o mestre, sem dizer o que saiu ----------
AGUARDA = "algo diferente aconteceu no seu sorteio, então um mestre vai decidir"
PROXIMO_MESTRE = "Agora é com um mestre: algo diferente aconteceu no seu sorteio, fala com ele pra decidir, e aí você segue."
e1 = st(**{**SORTEIOS, "race": None, "race_special": 66}); l = ajuda.linhas_passo_a_passo(e1)
assert l[1] == f"❓ Sortear a raça: {AGUARDA}" and l[2] == "✅ Sortear a classe social" and l[3] == "🔒 Escolher a classe: depois de sortear a raça"
assert ajuda.proximo_passo(e1) == PROXIMO_MESTRE
assert ajuda.texto_falta_para("classe", e1) == "Ainda não dá pra usar `/classe`: algo diferente aconteceu num dos seus sorteios, então um mestre precisa decidir antes. Fala com ele."
e2 = st(race="Humano", social_class_special=77); l = ajuda.linhas_passo_a_passo(e2)
assert l[1] == "✅ Sortear a raça" and l[2] == f"❓ Sortear a classe social: {AGUARDA}" and ajuda.proximo_passo(e2) == PROXIMO_MESTRE
e3 = st(**SORTEIOS, class_name="Feiticeiros", magic_rank_special=77); l = ajuda.linhas_passo_a_passo(e3)
assert l[4] == f"❓ Sortear o Rank de magia: {AGUARDA}" and l[5] == "🔒 Distribuir os pontos de atributo: depois de sortear o Rank de magia" and ajuda.proximo_passo(e3) == PROXIMO_MESTRE
assert ajuda.texto_falta_para("atributos", e3).startswith("Ainda não dá pra usar `/atributos`: algo diferente aconteceu num dos seus sorteios")
assert ajuda.texto_bloqueio("Sombra", e1).startswith("🔒 A ficha de **Sombra** ainda não está pronta") and PROXIMO_MESTRE in ajuda.texto_bloqueio("Sombra", e1)
for texto in (*l, *ajuda.linhas_passo_a_passo(e1), *ajuda.linhas_passo_a_passo(e2), ajuda.proximo_passo(e3), ajuda.texto_bloqueio("Sombra", e2)):
    assert "66" not in texto and "77" not in texto, texto                                            # nada diz o número que saiu
print("8. resultado especial OK")

# ---------- 9. os comandos novos desta rodada ----------
for chave in ("habilidade", "mestre sorte"):
    e = ajuda.AJUDA[chave]; assert e["resumo"] and e["uso"].startswith("/") and 0 < len(e["detalhes"]) <= 600 and "—" not in e["detalhes"], chave
assert ajuda.AJUDA["habilidade"]["grupo"] == "personagem" and ajuda.AJUDA["mestre sorte"]["grupo"] == "mestre" and ajuda.AJUDA["mestre sorte"]["requisito"] == "Só mestres."
assert ("Dados", ["sorte"]) in ajuda.MESTRE_SUBGRUPOS and "habilidade" in ajuda.ORDEM_SUGESTAO and len(ajuda.ORDEM_SUGESTAO) == 22
assert "3#d20+5" in ajuda.AJUDA["rolar"]["detalhes"] and "🍀" in ajuda.AJUDA["rolar"]["detalhes"] and "botões" in ajuda.AJUDA["classe"]["detalhes"] and "`habilidade:`" in ajuda.AJUDA["classe"]["detalhes"] and "botões" in ajuda.AJUDA["habilidade"]["detalhes"] and "+4" in ajuda.AJUDA["niveis"]["detalhes"]
assert "discreto" in ajuda.AJUDA["mestre sorte"]["detalhes"] and "não mexe nos sorteios da criação nem na iniciativa" in ajuda.AJUDA["mestre sorte"]["detalhes"]   # o que o comando NÃO faz está dito
print("9. comandos novos OK")

# ---------- 10. a ajuda de mestre é separada ----------
vm = ajuda.visao_mestre(); assert vm["titulo"] == "🛡️ Ajuda do mestre" and "/mestre ajuda comando:dar_xp" in vm["descricao"]
assert [c[0] for c in vm["campos"]] == [r for r, _ in ajuda.MESTRE_SUBGRUPOS] == ["XP e nível", "Ficha", "Dados", "Sorteios", "Cena", "Ajuda", "Jogadores"]
todos_mestre = [k.split(" ", 1)[1] for k in ajuda.AJUDA if k.startswith("mestre ")]
assert sorted(c for _, cmds in ajuda.MESTRE_SUBGRUPOS for c in cmds) == sorted(todos_mestre) and len(todos_mestre) == 20            # nenhum comando de mestre fica de fora
linhas = [l for _, v in vm["campos"] for l in v.split("\n")]; assert len(linhas) == 20 and all(l.startswith("`/mestre ") for l in linhas) and all(len(v) <= 1024 for _, v in vm["campos"])
assert "`/mestre dar_xp` " + ajuda.AJUDA["mestre dar_xp"]["resumo"] in linhas and "`/mestre ajuda` a ajuda só dos comandos de mestre" in linhas
assert ajuda.sugestoes_mestre("")[:4] == ["dar_xp", "upar", "corrigir_nivel", "escudo"] and len(ajuda.sugestoes_mestre("")) == 20
assert ajuda.sugestoes_mestre("xp") == ["dar_xp", "exportar"] and ajuda.sugestoes_mestre(" /ESCUDO ") == ["escudo"] and ajuda.sugestoes_mestre("zzz") == []
assert ajuda.sugestoes_mestre("corrigir") == ["corrigir_nivel", "corrigir_magia", "corrigir_raca", "corrigir_estado", "corrigir_classe"]
assert ajuda.achar_mestre("dar_xp") == ("mestre dar_xp", []) and ajuda.achar_mestre("mestre escudo") == ("mestre escudo", []) and ajuda.achar_mestre("/Mestre Sorte") == ("mestre sorte", [])
assert ajuda.achar_mestre("escud") == ("mestre escudo", [])                                                      # um pedaço que só combina com um
assert ajuda.achar_mestre("corrigir") == (None, ["corrigir_nivel", "corrigir_magia", "corrigir_raca", "corrigir_estado", "corrigir_classe"])
assert ajuda.achar_mestre("zzz") == (None, []) and ajuda.achar_mestre("") == (None, []) and ajuda.achar_mestre("rolar") == (None, [])      # comando de jogador não vale aqui
assert ajuda.AJUDA["mestre ajuda"]["requisito"] == "Só mestres." and 0 < len(ajuda.AJUDA["mestre ajuda"]["detalhes"]) <= 600 and "jogadores não veem" in ajuda.AJUDA["mestre ajuda"]["detalhes"]
print("10. ajuda de mestre OK")

print("\nTODOS OS TESTES DA AJUDA PASSARAM")
