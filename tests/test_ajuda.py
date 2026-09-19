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
SORTEADOS = dict(race="Humano", magic_rank="Raro", social_class="3º Estado")

# ---------- passo a passo: um item por passo, com o ícone certo ----------
l = ajuda.linhas_passo_a_passo(st())
assert l == [
    "✅ Personagem criado",
    "▶️ Sortear a raça: `/raca_inicial`",
    "⬜ Sortear o Rank de magia: `/magia_inicial`",
    "⬜ Sortear a classe social: `/classe_social`",
    "🔒 Escolher a classe: depois dos sorteios",
    "🔒 Distribuir os pontos de atributo: depois dos sorteios e de escolher a classe",
], l
assert ajuda.proximo_passo(st()) == "Próximo passo: `/raca_inicial`, pra sortear a raça (os três sorteios podem ser feitos em qualquer ordem)."
l = ajuda.linhas_passo_a_passo(st(race="Humano", magic_rank="Raro"))                                # o "próximo" pula o que já foi feito
assert l[1] == "✅ Sortear a raça" and l[2] == "✅ Sortear o Rank de magia" and l[3] == "▶️ Sortear a classe social: `/classe_social`"
l = ajuda.linhas_passo_a_passo(st(**SORTEADOS))
assert l[-2:] == ["▶️ Escolher a classe: `/classe`", "🔒 Distribuir os pontos de atributo: depois de escolher a classe"]
assert ajuda.proximo_passo(st(**SORTEADOS)) == "Próximo passo: `/classe`, pra escolher a classe."
l = ajuda.linhas_passo_a_passo(st(**SORTEADOS, class_name="Sábio", attr_forca=2))
assert l[-1] == "▶️ Distribuir os pontos de atributo: `/atributos` (2 de 6 pontos usados)"
pronta = st(**SORTEADOS, class_name="Sábio", attr_forca=2, attr_vitalidade=3, attr_vontade=1)
assert set(x[0] for x in ajuda.linhas_passo_a_passo(pronta)) == {"✅"} and ajuda.proximo_passo(pronta) == "A ficha está pronta e tudo está liberado."
# classe feita por um mestre sem os sorteios: o atributo continua fechado e o texto diz o que falta de verdade
l = ajuda.linhas_passo_a_passo(st(class_name="Sábio"))
assert l[-2] == "✅ Escolher a classe" and l[-1] == "🔒 Distribuir os pontos de atributo: depois dos sorteios"
# 100 na classe social: o mestre decide
s100 = st(race="Humano", magic_rank="Raro", social_class=dice.SOCIAL_CLASS_MASTER)
l = ajuda.linhas_passo_a_passo(s100)
assert l[3] == "⏳ Classe social: você tirou 100, então um mestre vai definir o seu Estado" and l[4].startswith("🔒 Escolher a classe")
assert ajuda.proximo_passo(s100) == "Agora é com um mestre: fala com ele pra definir o seu Estado, e aí você segue."
print("1. passo a passo OK")

# ---------- textos de bloqueio ----------
t = ajuda.texto_bloqueio("Kairon Flagon", st())
assert t.startswith("🔒 A ficha de **Kairon Flagon** ainda não está pronta, e esse comando só abre quando ela estiver.")
assert "▶️ Sortear a raça: `/raca_inicial`" in t and "Próximo passo: `/raca_inicial`" in t and t.endswith("use `/ajuda`.") and len(t) < 1500
t = ajuda.texto_falta_para("classe", st())
assert t.startswith("Ainda não dá pra usar `/classe`: a criação tem uma ordem") and "🔒 Escolher a classe: depois dos sorteios" in t
t = ajuda.texto_falta_para("atributos", st(**SORTEADOS)); assert "`/atributos`" in t and "▶️ Escolher a classe: `/classe`" in t
t = ajuda.texto_falta_para("classe", s100)
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
assert len(tudo) == 25 and tudo[:3] == ["personagem criar", "raca_inicial", "magia_inicial"]           # sem digitar, começa pelo passo a passo
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
situacoes = [(None, False), (st(), True), (st(**SORTEADOS), True), (s100, True), (pronta, True)]
for status, tem in situacoes:
    for mestre in (False, True):
        cabe(ajuda.visao_geral(status, tem, mestre))
v = ajuda.visao_geral(None, False, False)
assert [c[0] for c in v["campos"]] == ["Seu passo a passo"] + [t for _, t in ajuda.GRUPOS]
assert "/personagem criar" in v["campos"][0][1] and "/ajuda comando:atributos" in v["descricao"]
assert ajuda.visao_geral(pronta, True, False)["campos"][0][1] == "✅ Ficha pronta. Todos os comandos estão liberados."
assert "▶️ Sortear a raça: `/raca_inicial`" in ajuda.visao_geral(st(), True, False)["campos"][0][1]
vm = ajuda.visao_geral(pronta, True, True); assert vm["campos"][-1][0] == "Comandos de mestre" and "`/mestre dar_xp`" in vm["campos"][-1][1]
assert "Comandos de mestre" not in [c[0] for c in ajuda.visao_geral(pronta, True, False)["campos"]]
print("7. visão geral OK (maior resposta:", max(cabe(ajuda.visao_geral(s, t, m)) for s, t in situacoes for m in (False, True)), "de 6000 caracteres)")

print("\nTODOS OS TESTES DA AJUDA PASSARAM")
