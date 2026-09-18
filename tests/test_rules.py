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
site = {"Caçador": (35, 15, 5, 20), "Feiticeiros": (20, 20, 25, 5), "Ladrão": (25, 20, 10, 15),
        "Mestre de Forja": (15, 35, 15, 20), "Mundano": (10, 15, 10, 10), "Sábio": (15, 35, 20, 5)}
for nome, (vida, san, mana, est) in site.items():
    r = rules.calculate_resources(vitalidade=1, forca=1, vontade=1, alma=1, classe=nome)
    assert (r["vida"]["total"], r["sanidade"]["total"], r["mana"]["total"], r["estamina"]["total"]) == (5 + vida, 5 + san, 6 + mana, 6 + est), nome
r = rules.calculate_resources(vitalidade=3, forca=2, vontade=2, alma=1, classe="Caçador")
assert (r["vida"]["total"], r["sanidade"]["total"], r["mana"]["total"], r["estamina"]["total"]) == (50, 25, 14, 35)
assert r["vida"] == {"base": 15, "bonus": 35, "total": 50}
assert all(v["total"] == 0 for v in rules.calculate_resources(vitalidade=0, forca=0, vontade=0, alma=0, classe="Nenhuma").values())
try:
    rules.calculate_resources(vitalidade=1, forca=1, vontade=1, alma=1, classe="Paladino")
    raise SystemExit("classe desconhecida deveria falhar")
except ValueError:
    pass
assert rules.CLASS_CHOICES == ["Nenhuma", *site] and set(rules.CLASS_SKILLS) == set(site)
assert rules.CLASS_SKILLS["Caçador"] == "Religião e Luta ou Pontaria" and rules.CLASS_SKILLS["Mundano"] == "duas à sua escolha"
print("4. classes e recursos OK")

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

print("\nTODOS OS TESTES DAS REGRAS PASSARAM")
