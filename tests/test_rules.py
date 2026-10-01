"""Testes das regras do sistema (rules.py) e das tabelas de sorteio (dice.py).
Rodar da pasta do bot: python tests/test_rules.py"""
import collections
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import dice
import rules


def conta(tabela_fn):
    return collections.Counter(tabela_fn(n) for n in range(1, 101))


def falha(fn, *args):
    try:
        fn(*args)
    except dice.DiceError:
        return True
    return False


# ---------- tabelas de sorteio: cobrem os 100 resultados, sem buraco, com as chances certas ----------
assert conta(dice.magic_rank_for) == {"Comum": 45, "Raro": 30, "Super Raro": 20, "Lendário": 4, "Mítico": 1}
assert conta(dice.race_for) == {"Humano": 85, "Vampiro": 10, "Dhampir": 5}
assert conta(dice.social_class_for) == {"3º Estado": 80, "2º Estado": 11, "1º Estado": 8, dice.SOCIAL_CLASS_MASTER: 1}
assert conta(dice.clergy_for) == {"Baixo Clero": 49, "Alto Clero": 51}
for n, esperado in [(1, "Humano"), (85, "Humano"), (86, "Vampiro"), (95, "Vampiro"), (96, "Dhampir"), (100, "Dhampir")]:
    assert dice.race_for(n) == esperado, n
for n, esperado in [(1, "3º Estado"), (80, "3º Estado"), (81, "2º Estado"), (91, "2º Estado"), (92, "1º Estado"),
                    (99, "1º Estado"), (100, dice.SOCIAL_CLASS_MASTER)]:
    assert dice.social_class_for(n) == esperado, n
assert dice.clergy_for(49) == "Baixo Clero" and dice.clergy_for(50) == "Alto Clero"        # "50 pra cima é Alto Clero"
for fn in (dice.magic_rank_for, dice.race_for, dice.social_class_for, dice.clergy_for):
    assert falha(fn, 0) and falha(fn, 101)
assert dice.RACES == ["Humano", "Vampiro", "Dhampir"] and dice.MAGIC_RANKS == ["Comum", "Raro", "Super Raro", "Lendário", "Mítico"]
print("1. tabelas de sorteio OK")

# ---------- XP: pra sair do nível N são N x 1000, somado ----------
assert {n: rules.xp_at_level_start(n) for n in range(1, 11)} == {
    1: 0, 2: 1000, 3: 3000, 4: 6000, 5: 10000, 6: 15000, 7: 21000, 8: 28000, 9: 36000, 10: 45000}
assert [rules.xp_to_next(n) for n in range(1, 11)] == [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, None]
for n in range(1, 10):
    assert rules.xp_at_level_start(n + 1) - rules.xp_at_level_start(n) == n * 1000
for xp, nivel in [(0, 1), (999, 1), (1000, 2), (2999, 2), (3000, 3), (5999, 3), (6000, 4), (44999, 9), (45000, 10), (10**9, 10), (-5, 1)]:
    assert rules.level_for_xp(xp) == nivel, (xp, nivel)
assert all(rules.level_for_xp(rules.xp_at_level_start(n)) == n for n in range(1, 11))
assert rules.xp_progress(0) == (1, 0, 1000) and rules.xp_progress(1500) == (2, 500, 2000)
assert rules.xp_progress(45000) == (10, 0, None) and rules.xp_progress(50000) == (10, 5000, None)
assert rules.fmt_xp(0) == "0" and rules.fmt_xp(1250) == "1.250" and rules.fmt_xp(45000) == "45.000" and rules.fmt_xp(1234567) == "1.234.567"
assert rules.xp_bar(0, 1000) == "▱" * 10 and rules.xp_bar(500, 1000) == "▰" * 5 + "▱" * 5 and rules.xp_bar(999, 1000) == "▰" * 9 + "▱"
assert rules.bar(3, 10) == "▰▰▰▱▱▱▱▱▱▱" and rules.bar(99, 10) == "▰" * 10 and rules.bar(-1, 10) == "▱" * 10
print("2. XP e níveis OK")

# ---------- ganhos por nível (site: +2 perícia por nível; +1 atributo e habilidade a cada 2 níveis) ----------
assert rules.total_gains(10) == {"pericia": 18, "atributo": 5, "disciplina": 0, "habilidade": 5}
assert rules.total_gains(1) == {"pericia": 0, "atributo": 0, "disciplina": 0, "habilidade": 0}
assert [rules.gains_for_level(n)["atributo"] for n in range(1, 11)] == [0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
assert all(rules.gains_for_level(n)["pericia"] == 2 for n in range(2, 11))
assert rules.gains_between(3, 6) == {"pericia": 6, "atributo": 2, "disciplina": 0, "habilidade": 2}
assert rules.gains_between(4, 4)["pericia"] == 0
for raca, esperado in [("Vampiro", 5), ("Dhampir", 5), ("Humano", 0), (None, 0)]:      # +1 ponto de Disciplina nos níveis pares
    assert rules.total_gains(10, raca)["disciplina"] == esperado, raca
assert [rules.gains_for_level(n, "Dhampir")["disciplina"] for n in range(1, 11)] == [0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
assert rules.INITIAL_DISCIPLINE_POINTS == {"Vampiro": 4, "Dhampir": 3}
assert rules.describe_gains(rules.gains_between(1, 2, "Dhampir")) == (
    "+2 pontos de Perícia · +1 ponto de Atributo · 1 habilidade nova ou melhorada · +1 ponto de Disciplina")
assert rules.describe_gains(rules.gains_between(2, 3)) == "+2 pontos de Perícia" and rules.describe_gains(rules.total_gains(1)) == "nada (ficha inicial)"
linhas = rules.level_table_lines(3, "Dhampir")
assert len(linhas) == 10 and linhas[2].startswith("▶️ **Nível 3**") and sum(l.startswith("▫️") for l in linhas) == 9
assert "(com 3 pontos de Disciplina)" in linhas[0] and linhas[1].endswith("+1 disciplina") and "**máximo**" in linhas[9]
assert "disciplina" not in " ".join(rules.level_table_lines(None, "Humano")) and "45.000 XP" in rules.level_table_lines()[9]
print("3. ganhos por nível e Disciplina OK")

# ---------- classes e recursos (números do site) ----------
site = {"Caçador": (35, 15, 5, 20), "Clérigo": (20, 30, 15, 10), "Feiticeiros": (20, 20, 25, 5), "Ladrão": (25, 20, 10, 15),
        "Mercenário": (30, 20, 5, 20), "Mestre de Forja": (15, 35, 15, 20), "Mundano": (10, 15, 10, 10), "Sábio": (15, 35, 20, 5)}
for nome, (vida, san, mana, est) in site.items():
    r = rules.calculate_resources(vitalidade=1, forca=1, vontade=1, alma=1, classe=nome)
    assert (r["vida"]["total"], r["sanidade"]["total"], r["mana"]["total"], r["estamina"]["total"]) == (5 + vida, 5 + san, 6 + mana, 6 + est), nome
r = rules.calculate_resources(vitalidade=3, forca=2, vontade=2, alma=1, classe="Caçador")
assert (r["vida"]["total"], r["sanidade"]["total"], r["mana"]["total"], r["estamina"]["total"]) == (50, 25, 14, 35)
assert r["vida"] == {"por_nivel": 15, "base": 15, "bonus": 35, "total": 50}
assert all(v["total"] == 0 for v in rules.calculate_resources(vitalidade=0, forca=0, vontade=0, alma=0, classe="Nenhuma").values())
try:
    rules.calculate_resources(vitalidade=1, forca=1, vontade=1, alma=1, classe="Paladino")
    raise SystemExit("classe desconhecida deveria falhar")
except ValueError:
    pass
assert rules.CLASS_CHOICES == ["Nenhuma", *site] and set(rules.CLASS_SKILLS) == set(site)
assert rules.CLASS_SKILLS["Caçador"] == "Religião e Luta ou Pontaria" and rules.CLASS_SKILLS["Mundano"] == "duas à sua escolha"
assert rules.CLASS_SKILLS["Clérigo"] == "Religião e Medicina" and rules.CLASS_SKILLS["Mercenário"] == "Tática e Luta ou Pontaria"
assert len(rules.CLASSES) == 8 and list(rules.CLASSES) == list(site)                                   # a ordem é a do site
assert rules.magic_access("Humano", "Clérigo") == "nao" and rules.magic_access("Humano", "Mercenário") == "nao"      # as duas novas não têm magia
assert rules.magic_access("Humano", "Feiticeiros") == "sim" and rules.magic_access("Vampiro", "Mercenário") == "sim"
print("4. classes e recursos OK")

# ---------- recursos por nível: a cada nível soma de novo; o bônus da classe entra uma vez só ----------
TOTAIS = ("vida", "sanidade", "mana", "estamina")
tot = lambda x: tuple(x[k]["total"] for k in TOTAIS)
A = dict(forca=1, vitalidade=3, vontade=2, alma=1)
# tabela do prompt: Caçador (bônus 35/15/5/20) com o mesmo atributo em todos os níveis
for nivel, vals in {1: (50, 25, 14, 32), 5: (110, 65, 50, 80), 10: (185, 115, 95, 140)}.items():
    assert tot(rules.calculate_resources(**A, classe="Caçador", nivel=nivel)) == vals, nivel
    assert tot(rules.calculate_resources_by_level([A] * nivel, "Caçador")) == vals, nivel        # somando nível a nível dá o mesmo
c5 = rules.calculate_resources(**A, classe="Caçador", nivel=5)
assert c5["vida"] == {"por_nivel": 15, "base": 75, "bonus": 35, "total": 110}                    # 3 x 5 x 5 níveis = 75, mais 35 da classe
assert c5["mana"] == {"por_nivel": 9, "base": 45, "bonus": 5, "total": 50}
# o bônus da classe é uma vez só, não uma por nível
assert rules.calculate_resources(**A, classe="Mundano", nivel=10)["vida"]["total"] == 150 + 10
assert rules.calculate_resources(**A, classe="Nenhuma", nivel=10)["vida"]["total"] == 150
# todas as classes e níveis: a soma nível a nível com atributo fixo bate com a conta direta
for nome in rules.CLASSES:
    for n in range(1, 11):
        assert rules.calculate_resources(**A, classe=nome, nivel=n) == {
            k: {**v, "por_nivel": rules.calculate_resources(**A, classe=nome)[k]["por_nivel"]}
            for k, v in rules.calculate_resources_by_level([A] * n, nome).items()}, (nome, n)
# atributo mudando: Vitalidade 3 nos níveis 1 a 3 e 4 a partir do 4 (só Vida, Caçador)
vida = lambda lista: rules.calculate_resources_by_level(
    [dict(forca=0, vitalidade=v, vontade=0, alma=0) for v in lista], "Caçador")["vida"]["total"]
assert (vida([3, 3, 3]), vida([3, 3, 3, 4]), vida([3, 3, 3, 4, 4])) == (80, 100, 120)
# o nível 1 é igual ao cálculo antigo (uma vez só)
assert tot(rules.calculate_resources(vitalidade=3, forca=2, vontade=2, alma=1, classe="Caçador")) == (50, 25, 14, 35)
assert rules.calculate_resources(**A, classe="Caçador", nivel=1) == rules.calculate_resources(**A, classe="Caçador")
for ruim in (0, 11, -1):
    try: rules.calculate_resources(**A, nivel=ruim); raise SystemExit("nível inválido deveria falhar")
    except ValueError: pass
for f in (lambda: rules.calculate_resources_by_level([]), lambda: rules.calculate_resources_by_level([A], "Paladino")):
    try: f(); raise SystemExit("deveria falhar")
    except ValueError: pass
assert rules.RESOURCE_ATTRIBUTES == ("forca", "vitalidade", "vontade", "alma")               # Destreza e Razão não entram
D = dict(forca=1, vitalidade=3, vontade=2, alma=1, destreza=9, razao=9)
assert tot(rules.calculate_resources_by_level([D], "Caçador")) == (50, 25, 14, 32)
print("4b. recursos por nível OK")

# ---------- atributos: pontos e limites de criação ----------
assert [rules.attribute_points_total(n) for n in range(1, 11)] == [6, 7, 7, 8, 8, 9, 9, 10, 10, 11]
assert rules.attribute_points_total(10) - rules.attribute_points_total(1) == rules.total_gains(10)["atributo"] == 5
V = lambda **k: {a: k.get(a, 0) for a in rules.ATTRIBUTES}
assert rules.validate_attributes(V(forca=2, vitalidade=3, vontade=1), 1, "Humano") == []
assert len(rules.validate_attributes(V(forca=2, vitalidade=3, vontade=2), 1, "Humano")) == 1            # 7 pontos no nível 1
assert rules.validate_attributes(V(forca=4, vitalidade=2), 1, "Humano")                                # Força 4 passa do limite 3
assert rules.validate_attributes(V(forca=4, vitalidade=2), 2, "Humano") == []                          # 1 ponto de nível cobre o excesso
assert rules.validate_attributes(V(forca=5, vitalidade=2), 2, "Humano")                                # excesso 2 > 1 ponto de nível
assert rules.validate_attributes(V(razao=6), 1, "Humano") == [] and rules.validate_attributes(V(razao=7), 1, "Humano")
assert rules.validate_attributes(V(vontade=6), 1, "Humano") == [] and rules.validate_attributes(V(alma=6), 1, "Humano") == []   # sem limite
assert rules.validate_attributes(V(forca=5, destreza=1), 1, "Vampiro") == [] and rules.validate_attributes(V(forca=6), 1, "Vampiro")
assert rules.validate_attributes(V(forca=6), 1, "Dhampir") == [] and rules.validate_attributes(V(forca=7), 1, "Dhampir")      # Dhampir: só o total
assert rules.validate_attributes(V(forca=6), 1, None) == [] and len(rules.validate_attributes(V(forca=9), 1, "Humano")) == 2
assert rules.describe_attributes(V(forca=2, vitalidade=3, vontade=1)) == "Força 2 · Destreza 0 · Vitalidade 3 · Razão 0 · Vontade 1 · Alma 0"
assert rules.ATTRIBUTES == ("forca", "destreza", "vitalidade", "razao", "vontade", "alma") and set(rules.ATTRIBUTE_LABELS) == set(rules.ATTRIBUTES)
print("5. atributos OK")

# ---------- quem tem magia: Vampiro (qualquer classe) e as classes Feiticeiros e Mestre de Forja ----------
assert rules.MAGIC_RACES == ("Vampiro", "Dhampir") and rules.MAGIC_CLASSES == ("Feiticeiros", "Mestre de Forja")
assert set(rules.MAGIC_CLASSES) <= set(rules.CLASSES)
com_magia = 0
for raca in ("Humano", "Vampiro", "Dhampir"):                          # a tabela inteira: 3 raças x 8 classes
    for classe in rules.CLASSES:
        esperado = "sim" if raca in ("Vampiro", "Dhampir") or classe in ("Feiticeiros", "Mestre de Forja") else "nao"
        assert rules.magic_access(raca, classe) == esperado, (raca, classe)
        com_magia += esperado == "sim"
assert com_magia == 18                                                    # 8 do Vampiro + 8 do Dhampir + 2 classes mágicas no Humano
assert rules.magic_access("Humano", "Mundano") == "nao"                   # o caso que não fazia sentido
assert rules.magic_access("Dhampir", "Sábio") == "sim" and rules.magic_access("Dhampir", "Mundano") == "sim"          # Dhampir tem magia de qualquer classe, como o Vampiro
assert rules.magic_access("Dhampir", None) == "sim" and rules.MAGIC_RACES == ("Vampiro", "Dhampir")
assert rules.magic_access("Vampiro", None) == "sim" and rules.magic_access(None, "Mestre de Forja") == "sim"        # uma das duas já basta
assert [rules.magic_access(a, b) for a, b in (("Humano", None), (None, "Mundano"), (None, None))] == ["indefinido"] * 3
print("6. quem tem magia OK")

# ---------- ordem da criação: raça e classe social (qualquer ordem), classe, Rank de magia (só pra quem tem), atributos ----------
base = dict(race=None, magic_rank=None, social_class=None, class_name=None, **{f"attr_{a}": 0 for a in rules.ATTRIBUTES})
st = lambda **k: rules.creation_status({**base, **k})
SORTEIOS = dict(race="Humano", social_class="3º Estado")
assert [p["id"] for p in rules.CREATION_STEPS] == ["raca", "estado", "classe", "magia", "atributos"]
s0 = st()
assert not s0["pronta"] and rules.creation_next_step(s0) == "raca" and s0["magia_acesso"] == "indefinido" and not s0["sem_magia"]
assert [rules.creation_missing_before(x, s0) for x in ("raca", "estado")] == [[], []]                            # os dois sorteios abrem de cara
assert rules.creation_missing_before("classe", s0) == ["raca", "estado"]
assert rules.creation_missing_before("magia", s0) == ["raca", "estado", "classe"]                                # o Rank de magia vem depois da classe
assert rules.creation_missing_before("atributos", s0) == ["raca", "estado", "classe", "magia"]                    # pré-requisitos dos pré-requisitos
for feito, dados in (("raca", dict(race="Humano")), ("estado", dict(social_class="3º Estado"))):                # qualquer ordem entre os dois
    assert rules.creation_missing_before("classe", st(**dados)) == [x for x in ("raca", "estado") if x != feito]
s1 = st(**SORTEIOS)
assert rules.creation_missing_before("classe", s1) == [] and rules.creation_missing_before("magia", s1) == ["classe"] and rules.creation_next_step(s1) == "classe"
# classe SEM magia (Humano Mundano): o passo do Rank de magia não vale, e os atributos abrem direto
s2 = st(**SORTEIOS, class_name="Mundano")
assert s2["sem_magia"] and s2["magia"] and not s2["magia_sorteada"] and not s2["magia_indevida"] and s2["magia_acesso"] == "nao"
assert rules.creation_missing_before("atributos", s2) == [] and rules.creation_next_step(s2) == "atributos" and not s2["pronta"]
s3 = st(**SORTEIOS, class_name="Mundano", attr_forca=2, attr_vitalidade=3, attr_vontade=1)
assert s3["pronta"] and rules.creation_next_step(s3) is None and s3["pontos_usados"] == 6                        # pronta sem nunca ter sorteado magia
assert st(**SORTEIOS, class_name="Mundano", attr_destreza=6)["pronta"] and not st(**SORTEIOS, class_name="Mundano", attr_forca=5)["pronta"]
# classe COM magia: o Rank de magia fica no caminho até ser sorteado
for dados in (dict(race="Humano", class_name="Feiticeiros"), dict(race="Humano", class_name="Mestre de Forja"),
              dict(race="Vampiro", class_name="Mundano"), dict(race="Vampiro", class_name="Ladrão"), dict(race="Dhampir", class_name="Feiticeiros")):
    c = st(social_class="3º Estado", **dados)
    assert c["magia_acesso"] == "sim" and not c["sem_magia"] and not c["magia"] and rules.creation_next_step(c) == "magia", dados
    assert rules.creation_missing_before("atributos", c) == ["magia"] and not st(social_class="3º Estado", attr_forca=6, **dados)["pronta"]
    assert st(social_class="3º Estado", magic_rank="Raro", attr_forca=6, **dados)["pronta"]
c = st(**SORTEIOS, class_name="Feiticeiros", magic_rank="Raro")
assert c["magia"] and c["magia_sorteada"] and rules.creation_next_step(c) == "atributos" and not c["pronta"]
# Rank guardado de quem não tem magia (dado antigo): conta como feito, mas fica marcado
ind = st(**SORTEIOS, class_name="Mundano", magic_rank="Raro")
assert ind["magia"] and ind["sem_magia"] and ind["magia_sorteada"] and ind["magia_indevida"]
assert not st(**SORTEIOS, class_name="Feiticeiros", magic_rank="Raro")["magia_indevida"]
# Rank sorteado antes de saber a classe (dado antigo): vale, e a ficha não fica presa
assert st(race="Humano", magic_rank="Raro")["magia"] and st(race="Humano", magic_rank="Raro")["magia_acesso"] == "indefinido"
# um 100 na classe social ainda não conta: quem decide é o mestre, e a classe (e tudo depois) fica fechada
s4 = st(race="Humano", social_class=dice.SOCIAL_CLASS_MASTER)
assert s4["aguardando_mestre"] and not s4["estado"] and not s4["pronta"] and rules.creation_next_step(s4) == "estado"
assert rules.creation_missing_before("classe", s4) == ["estado"] and rules.creation_missing_before("magia", s4) == ["estado", "classe"]
assert not st(social_class="3º Estado")["aguardando_mestre"]
# a mesma linha do banco serve (sqlite3.Row)
import sqlite3
cn = sqlite3.connect(":memory:"); cn.row_factory = sqlite3.Row
cn.execute("CREATE TABLE c (race, magic_rank, social_class, class_name, attr_forca, attr_destreza, attr_vitalidade, attr_razao, attr_vontade, attr_alma)")
cn.execute("INSERT INTO c VALUES ('Vampiro','Comum','2º Estado','Ladrão',1,1,2,0,1,1)")
assert rules.creation_status(cn.execute("SELECT * FROM c").fetchone())["pronta"]
print("6. ordem da criação OK")

# ---------- 7. Disciplinas ----------
assert rules.DISCIPLINES == ("Potência", "Celeridade", "Ofuscação", "Presença", "Domínio", "Vidência", "Proteísmo", "Hemomancia", "Sanguessugia", "Regeneração")
assert rules.MAX_DISCIPLINE_GRADE == 5 and rules.PLAYER_MAX_DISCIPLINE_GRADE == 3 and rules.SANGUESSUGIA_LIBERADA is False
import lore
assert list(lore.DISCIPLINAS) == list(rules.DISCIPLINES)                                             # o lore cobre as dez, na mesma ordem
for nome, info in lore.DISCIPLINAS.items():
    assert info["tema"].strip()
    if nome == "Sanguessugia":
        assert info["graus"] is None                                                                  # em desenvolvimento: sem texto inventado
    else:
        assert sorted(info["graus"]) == [1, 2, 3] and all(t.strip() and "—" not in t for t in info["graus"].values()), nome
assert list(lore.DISCIPLINAS["Regeneração"]) == ["tema", "graus", "limite"] and "Sol, Prata, Água Sagrada e Armas Sagradas" in lore.DISCIPLINAS["Regeneração"]["limite"]
assert all("limite" not in i for n, i in lore.DISCIPLINAS.items() if n != "Regeneração")
assert lore.DISCIPLINAS["Potência"]["graus"][3] == "O dano desarmado vira 1d12." and "10 de Mana" in lore.DISCIPLINAS["Proteísmo"]["graus"][2] and "DT fixa 22" in lore.DISCIPLINAS["Vidência"]["graus"][3]
# pontos: Vampiro 4 e Dhampir 3 na criação, +1 nos níveis pares; Humano não tem
assert [rules.discipline_points_total(n, "Vampiro") for n in range(1, 11)] == [4, 5, 5, 6, 6, 7, 7, 8, 8, 9]
assert [rules.discipline_points_total(n, "Dhampir") for n in range(1, 11)] == [3, 4, 4, 5, 5, 6, 6, 7, 7, 8]
assert rules.discipline_points_total(10, "Humano") == 0 and rules.discipline_points_total(5, None) == 0 and rules.has_disciplines("Dhampir") and not rules.has_disciplines("Humano")
# 1 ponto = 1 grau, contando só até o 3; os graus 4 e 5 (do mestre) não gastam ponto
assert rules.discipline_points_used({}) == 0 and rules.discipline_points_used({"Potência": 2, "Celeridade": 1}) == 3
assert rules.discipline_points_used({"Potência": 4, "Domínio": 5}) == 6 and rules.discipline_points_used({"Potência": 3}) == 3
assert rules.discipline_points_free(1, "Vampiro", {"Potência": 3, "Celeridade": 1}) == 0 and rules.discipline_points_free(1, "Dhampir", {"Potência": 3, "Celeridade": 1}) == -1
# quando o jogador pode subir um grau
Q = rules.discipline_raise_problem
assert Q("Humano", 1, {}, "Potência") == "raca" and Q(None, 1, {}, "Potência") == "raca"
assert Q("Vampiro", 1, {}, "Potência") is None and Q("Dhampir", 1, {}, "Regeneração") is None
assert Q("Vampiro", 1, {}, "Sombra") == "desconhecida"
assert Q("Vampiro", 1, {}, "Sanguessugia") == "bloqueada" and rules.discipline_blocked("Sanguessugia") and not rules.discipline_blocked("Potência")
assert Q("Vampiro", 1, {"Potência": 3}, "Potência") == "grau_maximo"                                  # o jogador não passa do 3 sozinho
assert Q("Vampiro", 1, {"Potência": 4}, "Potência") == "grau_maximo"                                  # grau 4 dado pelo mestre também não sobe mais
assert Q("Vampiro", 1, {"Potência": 3, "Celeridade": 1}, "Ofuscação") == "sem_pontos"                # 4 pontos gastos
assert Q("Vampiro", 2, {"Potência": 3, "Celeridade": 1}, "Ofuscação") is None                        # o nível 2 deu +1 ponto
assert Q("Dhampir", 1, {"Potência": 2, "Celeridade": 1}, "Presença") == "sem_pontos" and Q("Dhampir", 2, {"Potência": 2, "Celeridade": 1}, "Presença") is None
# a Sanguessugia liberada vira uma Disciplina como as outras (sem migração de banco)
rules.SANGUESSUGIA_LIBERADA = True
try:
    assert not rules.discipline_blocked("Sanguessugia") and Q("Vampiro", 1, {}, "Sanguessugia") is None
finally:
    rules.SANGUESSUGIA_LIBERADA = False
print("7. Disciplinas OK")

# ---------- 8. resultado especial (66 e 77) ----------
assert rules.SPECIAL_ROLLS == (66, 77) and rules.is_special_roll(66) and rules.is_special_roll(77)
assert not any(rules.is_special_roll(n) for n in (1, 65, 67, 76, 78, 100))
base8 = dict(race=None, magic_rank=None, social_class=None, class_name=None, **{f"attr_{a}": 0 for a in rules.ATTRIBUTES})
assert rules.special_result(base8, "raca") is None and rules.creation_status(base8)["especial"] == {"raca": None, "estado": None, "magia": None}     # dicionário sem a coluna
assert rules.special_result({**base8, "race_special": 66}, "raca") == 66 and rules.special_result({**base8, "social_class_special": 77}, "estado") == 77
assert rules.special_result({**base8, "magic_rank_special": 66}, "magia") == 66 and rules.special_result({**base8, "race_special": 66}, "estado") is None
s8 = rules.creation_status({**base8, "race_special": 66, "social_class": "3º Estado"})
assert s8["raca"] is False and s8["estado"] is True and s8["pronta"] is False and s8["especial"] == {"raca": 66, "estado": None, "magia": None}   # a raça não conta como feita
assert rules.creation_next_step(s8) == "raca"
assert rules.reroll_block({**base8, "race": None, "race_special": 66, "race_attempts": 1}, "race") == "especial"
assert rules.reroll_block({**base8, "social_class_special": 77, "social_class_attempts": 1}, "social_class") == "especial"
assert rules.reroll_block({**base8, "race": "Humano", "race_attempts": 1, "race_special": None}, "race") is None      # sem especial, segue igual
assert rules.reroll_block({**base8, "race": "Humano", "race_attempts": 1}, "race") is None
print("8. resultado especial OK")

# ---------- habilidades de classe e o Sábio (+4 pontos de perícia por nível) ----------
assert list(rules.CLASS_ABILITIES) == list(rules.CLASSES)
assert rules.CLASS_ABILITIES["Clérigo"] == ("Mãos que Curam", "Bênção") and rules.CLASS_ABILITIES["Ladrão"] == ("Mão Leve", "Língua de Prata")
assert [c for c in rules.CLASSES if len(rules.CLASS_ABILITIES[c]) == 2] == ["Clérigo", "Ladrão"]           # só essas duas têm escolha
assert [c for c in rules.CLASSES if rules.class_needs_ability_choice(c)] == ["Clérigo", "Ladrão"] and not rules.class_needs_ability_choice(None) and not rules.class_needs_ability_choice("Nenhuma")
assert rules.class_ability_options(None) == () and rules.class_ability_options("Paladino") == ()
base9 = dict(class_name="Caçador", class_ability=None)
assert rules.class_ability_of(base9) == "Sem Dúvidas"                                                        # classe de uma habilidade só: é ela
assert rules.class_ability_of(dict(class_name="Clérigo", class_ability=None)) is None                        # duas opções e ainda não escolheu
assert rules.class_ability_of(dict(class_name="Clérigo", class_ability="Bênção")) == "Bênção"
assert rules.class_ability_of(dict(class_name="Clérigo", class_ability="Mão Leve")) is None                  # escolha de outra classe não vale
assert rules.class_ability_of(dict(class_name=None, class_ability=None)) is None and rules.class_ability_of(dict(class_name="Mundano")) == "Aprimoração"
assert rules.SKILL_POINTS_BY_CLASS == {"Sábio": 4} and rules.skill_points_per_level("Sábio") == 4
assert rules.skill_points_per_level("Caçador") == 2 and rules.skill_points_per_level(None) == 2 and rules.skill_points_per_level("Nenhuma") == 2
assert rules.gains_for_level(2, None, "Sábio")["pericia"] == 4 and rules.gains_for_level(2)["pericia"] == 2 and rules.gains_for_level(1, None, "Sábio")["pericia"] == 0
assert rules.gains_between(1, 4, "Humano", "Sábio")["pericia"] == 12 and rules.gains_between(1, 4, "Humano", "Mercenário")["pericia"] == 6
assert rules.total_gains(rules.MAX_LEVEL, None, "Sábio")["pericia"] == 36 and rules.total_gains(rules.MAX_LEVEL)["pericia"] == 18          # 9 níveis x 4 e 9 níveis x 2
assert "+4 pontos de Perícia" in rules.describe_gains(rules.gains_for_level(3, None, "Sábio")) and "+2 pontos de Perícia" in rules.describe_gains(rules.gains_for_level(3))
assert "+4 perícia" in rules.level_line(3, None, "Sábio") and "+2 perícia" in rules.level_line(3) and "+4 perícia" in "\n".join(rules.level_table_lines(2, None, "Sábio"))
print("9. habilidades de classe e Sábio OK")

# ---------- 10. vitais: o atual é o máximo menos o que perdeu ----------
assert rules.VITAL_KEYS == ("vida", "sanidade", "mana", "estamina") and set(rules.VITAL_LABELS) == set(rules.VITAL_EMOJI) == set(rules.VITAL_KEYS)
assert [rules.vital_current(100, p) for p in (0, 30, 100, 150, -5)] == [100, 70, 0, 0, 100]                  # nunca abaixo de 0 nem acima do máximo
assert rules.vital_current(0, 0) == 0 and rules.vital_current(50, 0) == 50
assert [rules.vital_lost_after_change(100, 30, d) for d in (-5, -70, -80, 0, 10, 30, 50)] == [35, 100, 100, 30, 20, 0, 0]          # dano chega no 0 e cura para no máximo
assert rules.vital_lost_after_change(100, 0, -1) == 1 and rules.vital_lost_after_change(100, 100, 1) == 99 and rules.vital_lost_after_change(100, 100, -10) == 100
assert [rules.vital_lost_for_value(100, v) for v in (0, 40, 100, 250, -3)] == [100, 60, 0, 0, 100]
assert rules.vital_current(100, rules.vital_lost_for_value(100, 37)) == 37
# o máximo sobe (nível): o atual sobe junto, porque o que se perdeu continua o mesmo
assert rules.vital_current(120, 30) == 90 and rules.vital_current(100, 30) == 70
print("10. vitais OK")

# ---------- 11. perícias ----------
assert len(rules.SKILLS) == 18 == len(set(rules.SKILLS)) and rules.SKILLS[0] == "Acrobacia" and rules.SKILLS[-1] == "Ocultismo" and "Luta" in rules.SKILLS
assert (rules.SKILL_POINTS_CREATION, rules.SKILL_MAX_POINTS, rules.SKILL_BONUS_CREATION) == (25, 7, {"Mundano": 5})
assert [rules.skill_points_total(n, "Caçador") for n in (1, 2, 3, 10)] == [25, 27, 29, 43]
assert [rules.skill_points_total(n, "Sábio") for n in (1, 2, 10)] == [25, 29, 61] and [rules.skill_points_total(n, "Mundano") for n in (1, 3)] == [30, 34]   # Sábio +4 por nível, Mundano +5 na criação
assert rules.skill_points_total(11, "Caçador") == 43 and rules.skill_points_total(0, "Caçador") == 25 and rules.skill_points_total(1, None) == 25 and rules.skill_points_total(2, "Nenhuma") == 27
assert rules.skill_points_free(2, "Caçador", {"Luta": 7, "Pontaria": 5}) == 15 and rules.skill_points_free(1, "Sábio", {}) == 25 and rules.skill_points_free(1, None, {"Luta": 7, "Fortitude": 7, "Reflexos": 7, "Atletismo": 7}) == -3
assert rules.class_skill_hints("Caçador") == ["Pontaria", "Luta", "Religião"] and rules.class_skill_hints("Clérigo") == ["Medicina", "Religião"]
assert rules.class_skill_hints("Mercenário") == ["Pontaria", "Luta", "Tática"] and rules.class_skill_hints("Mestre de Forja") == ["Tática", "Ocultismo"] and rules.class_skill_hints("Sábio") == ["Ciências", "Investigação"]
assert rules.class_skill_hints("Mundano") == [] and rules.class_skill_hints(None) == [] and rules.class_skill_hints("Paladino") == []                 # "duas à sua escolha": nenhuma marcada
assert rules.ABILITY_STATUS == ("pendente", "ajuste", "aprovada", "recusada") and rules.MAX_CUSTOM_ABILITIES == 8 and rules.ABILITY_ROLL_KINDS == ("dano", "cura")
print("11. perícias OK")

print("\nTODOS OS TESTES DAS REGRAS PASSARAM")
