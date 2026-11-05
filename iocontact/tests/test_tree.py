"""The family tree's layout code (static/app.js, the <kin> block) run under node: labels relative to the viewed
contact, generations and a tree drawn without overlaps."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="node is not installed")

SRC = (Path(__file__).resolve().parent.parent / "static" / "app.js").read_text(encoding="utf-8")
KIN = SRC[SRC.index("// <kin>"):SRC.index("// </kin>")]

PEOPLE = {  # id: (name, gender, born)
    1: ("Bernadette", "F", 1951), 2: ("Paul", "M", 1950), 3: ("Alexandra", "F", 1981), 4: ("Grandpa", "M", 1920),
    5: ("Grandma", "F", 1922), 6: ("Jean", "M", 1948), 7: ("Marie", "F", 1949), 8: ("Alex", "M", 1974),
    9: ("Frederic", "M", 1976), 10: ("Carissa", "F", 1970), 11: ("Wei", "M", 1976), 12: ("LiMing", "M", 1940),
    13: ("Sophie", "F", 1955), 14: ("Laurent", "M", 1976), 15: ("Kid", "F", 2010), 16: ("Godpa", "M", 1930),
    17: ("Ex", "M", 1950),
}
STORED = [  # (from, to, type): "from's <type> is to"; each is stored with its inverse, like the app does
    (1, 2, "spouse"), (1, 3, "child"), (2, 3, "child"), (1, 4, "parent"), (1, 5, "parent"), (4, 5, "spouse"),
    (6, 4, "parent"), (6, 5, "parent"), (1, 6, "sibling"), (6, 7, "spouse"), (6, 8, "child"), (7, 8, "child"),
    (8, 9, "sibling"), (8, 10, "spouse"), (10, 11, "sibling"), (10, 12, "parent"), (1, 13, "sibling"),
    (13, 14, "child"), (8, 15, "child"), (10, 15, "child"), (1, 8, "niece_nephew"), (1, 16, "godparent"),
    (3, 17, "ex_spouse"),
]
INV = {"spouse": "spouse", "child": "parent", "parent": "child", "sibling": "sibling", "niece_nephew": "aunt_uncle",
       "godparent": "godchild", "ex_spouse": "ex_spouse"}
FAM = ["parent", "child", "sibling", "half_sibling", "spouse", "partner", "ex_spouse", "grandparent", "grandchild",
       "great_grandparent", "great_grandchild", "aunt_uncle", "niece_nephew", "cousin", "parent_in_law",
       "child_in_law", "sibling_in_law", "step_parent", "step_child", "step_sibling", "godparent", "godchild", "relative"]


def run(root: int, extra=(), hidden=()) -> dict:
    edges = [{"from": a, "to": b, "type": t} for a, b, t in STORED] + [{"from": b, "to": a, "type": INV[t]} for a, b, t in STORED]
    edges += list(extra)
    g = {"root": root, "nodes": [{"id": i, "fn": n, "gender": s, "birthday": {"year": y}} for i, (n, s, y) in PEOPLE.items()],
         "edges": edges}
    script = KIN + """
const WORDS = { godparent: ['Godfather', 'Godmother', 'Godparent'], godchild: ['Godson', 'Goddaughter', 'Godchild'],
  ex_spouse: ['Former husband', 'Former wife', 'Former spouse'], spouse: ['Husband', 'Wife', 'Spouse'], partner: ['Partner', 'Partner', 'Partner'] };
const typeWord = (t, g) => { const w = WORDS[t] || [t, t, t]; return g === 'M' ? w[0] : g === 'F' ? w[1] : w[2]; };
const [g, fam, hidden] = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const L = familyLayout(g, new Set(fam), typeWord, new Set(hidden));
const o = (m) => Object.fromEntries([...m]);
console.log(JSON.stringify({ far: [...L.far], from: o(L.from), label: o(L.label), gen: o(L.gen), x: o(L.x), y: o(L.y), couples: L.couples, families: L.families }));
"""
    out = subprocess.run([NODE, "-e", script], input=json.dumps([g, FAM, list(hidden)]), capture_output=True, text=True, check=True)
    r = json.loads(out.stdout)
    r["name"] = {PEOPLE[int(k)][0]: v for k, v in r["label"].items()}
    r["g"] = {PEOPLE[int(k)][0]: v for k, v in r["gen"].items()}
    return r


def test_labels_are_relative_to_the_viewed_contact():
    n = run(1)["name"]
    assert n["Bernadette"] == "This contact"
    assert n["Paul"] == "Husband"
    assert n["Alexandra"] == "Daughter"
    assert n["Grandpa"] == "Father" and n["Grandma"] == "Mother"
    assert n["Jean"] == "Brother" and n["Sophie"] == "Sister"
    assert n["Marie"] == "Sister-in-law"
    assert n["Alex"] == "Nephew" and n["Frederic"] == "Nephew" and n["Laurent"] == "Nephew"
    assert n["Carissa"] == "Nephew's wife"
    assert n["Wei"] == "Nephew's brother-in-law"
    assert n["LiMing"] == "Nephew's father-in-law"
    assert n["Kid"] == "Grandniece"
    assert n["Godpa"] == "Godfather"
    assert n["Ex"] == "Daughter's former husband"


def test_labels_from_another_side():
    n = run(8)["name"]
    assert n["Bernadette"] == "Aunt" and n["Paul"] == "Uncle by marriage"
    assert n["Alexandra"] == "Cousin" and n["Laurent"] == "Cousin"
    assert n["Grandpa"] == "Grandfather"
    assert n["Frederic"] == "Brother" and n["Carissa"] == "Wife"
    assert n["Wei"] == "Brother-in-law" and n["LiMing"] == "Father-in-law"
    assert n["Kid"] == "Daughter"
    n = run(15)["name"]
    assert n["Laurent"] == "First cousin once removed" or n["Laurent"] == "Cousin once removed"
    assert n["Grandpa"] == "Great-grandfather"
    assert n["Bernadette"] == "Great-aunt"


def test_generations_and_layout():
    r = run(1)
    g = r["g"]
    assert g["Grandpa"] == 1 and g["Bernadette"] == 0 and g["Marie"] == 0 and g["Alex"] == -1 and g["Carissa"] == -1
    assert g["Kid"] == -2 and g["Wei"] == -1 and g["LiMing"] == 0
    x, y = {int(k): v for k, v in r["x"].items()}, {int(k): v for k, v in r["y"].items()}
    # rows go down a generation at a time, cards in a row never overlap
    for a in x:
        for b in x:
            if a < b and y[a] == y[b]:
                assert abs(x[a] - x[b]) >= 150, (PEOPLE[a], PEOPLE[b])
    assert y[4] < y[1] < y[8] < y[15]
    # couples sit side by side
    for c in r["couples"]:
        assert y[c["a"]] == y[c["b"]] and abs(abs(x[c["a"]] - x[c["b"]]) - 162) <= 1
    # a family's children sit under (around) their parents
    fam = {tuple(sorted(f["parents"])): sorted(f["children"]) for f in r["families"]}
    assert fam[(4, 5)] == [1, 6, 13] and fam[(6, 7)] == [8, 9] and fam[(1, 2)] == [3]


def test_implied_edges_label_but_do_not_draw():
    r = run(1, [{"from": 1, "to": 14, "type": "niece_nephew", "implied": True}])
    assert r["name"]["Laurent"] == "Nephew"
    assert all(14 not in f["children"] or f["parents"] == [13] for f in r["families"])


def test_folding_hides_a_branch_but_keeps_labels():
    r = run(1)
    assert len(r["x"]) == len(PEOPLE)
    # Carissa married into the family: her father and brother were reached through her, so her branch starts folded
    assert 10 in r["far"] and r["from"]["12"] == 10 and r["from"]["11"] == 10
    r = run(1, hidden=[11, 12])
    assert set(map(int, r["x"])) == set(PEOPLE) - {11, 12}
    assert r["name"]["Wei"] == "Nephew's brother-in-law"  # still labeled


# ---- more family shapes: each child row is centred under its parents, nothing overlaps, couples stay together

def scenario(people, stored, root, hidden=()):
    """people: {id: (name, gender, born)}; stored: [(from, to, type)] with the inverse added, like the app stores them."""
    inv = {"spouse": "spouse", "child": "parent", "parent": "child", "sibling": "sibling", "half_sibling": "half_sibling",
           "ex_spouse": "ex_spouse", "godparent": "godchild", "aunt_uncle": "niece_nephew", "step_parent": "step_child"}
    edges = [{"from": a, "to": b, "type": t} for a, b, t in stored] + [{"from": b, "to": a, "type": inv[t]} for a, b, t in stored]
    g = {"root": root, "nodes": [{"id": i, "fn": n, "gender": s, "birthday": {"year": y}} for i, (n, s, y) in people.items()], "edges": edges}
    script = KIN + """
const typeWord = (t, g) => t;
const [g, fam, hidden] = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const L = familyLayout(g, new Set(fam), typeWord, new Set(hidden));
const o = (m) => Object.fromEntries([...m]);
console.log(JSON.stringify({ x: o(L.x), y: o(L.y), gen: o(L.gen), couples: L.couples, families: L.families, sibGroups: L.sibGroups, W: TREE.W, CGAP: TREE.CGAP, GAP: TREE.GAP }));
"""
    out = subprocess.run([NODE, "-e", script], input=json.dumps([g, FAM, list(hidden)]), capture_output=True, text=True, check=True)
    r = json.loads(out.stdout)
    r["x"] = {int(k): v for k, v in r["x"].items()}
    r["y"] = {int(k): v for k, v in r["y"].items()}
    return r


def check_layout(r, people):
    x, y, W = r["x"], r["y"], r["W"]
    assert set(x) == set(people), "everyone is drawn"
    for a in x:
        for b in x:
            if a < b and y[a] == y[b]:
                assert abs(x[a] - x[b]) >= W + r["CGAP"] - 1, f"{people[a][0]} overlaps {people[b][0]}"
    couple_of = {}
    for c in r["couples"]:
        assert y[c["a"]] == y[c["b"]] and abs(abs(x[c["a"]] - x[c["b"]]) - (W + r["CGAP"])) <= 1, "a couple sits side by side"
        couple_of[c["a"]] = couple_of[c["b"]] = (c["a"], c["b"])
    for f in r["families"]:
        ps, kids = f["parents"], f["children"]
        for k in kids:
            assert y[k] > max(y[p] for p in ps), "children sit on the row below their parents"
        if len(ps) == 2 and couple_of.get(ps[0]) == couple_of.get(ps[1]) and couple_of.get(ps[0]):
            join = (x[ps[0]] + x[ps[1]] + W) / 2
            mid = (min(x[k] for k in kids) + max(x[k] for k in kids)) / 2 + W / 2
            yield ps, kids, join, mid


def centred(r, people, strict=True):
    off = [(ps, kids, abs(join - mid)) for ps, kids, join, mid in check_layout(r, people)]
    if strict:
        for ps, kids, d in off:
            assert d <= 1, f"children of {[people[p][0] for p in ps]} are {d}px off centre"
    return off


def test_alexs_screenshot_shape():
    # Célia's view: her father Thibaut and his brothers Alex and Frederic, each married with children, under grandfather Paul
    people = {1: ("Paul", "M", 1947), 2: ("Alex", "M", 1974), 3: ("Carissa", "F", 1970), 4: ("Frederic", "M", 1976), 5: ("Florence", "F", 1979),
              6: ("Thibaut", "M", 1977), 7: ("Allison", "F", 1983), 8: ("Célia", "F", 2012), 9: ("Aline", "F", 2004), 10: ("Maxime", "M", 2006),
              11: ("Philippe", "M", 2004), 12: ("Zoe", "F", 2008), 13: ("Maryse", "F", 1945), 14: ("Bernadette", "F", 1950)}
    stored = [(1, 2, "child"), (1, 4, "child"), (1, 6, "child"), (2, 4, "sibling"), (2, 6, "sibling"), (4, 6, "sibling"),
              (2, 3, "spouse"), (4, 5, "spouse"), (6, 7, "spouse"), (6, 8, "child"), (7, 8, "child"),
              (4, 9, "child"), (5, 9, "child"), (4, 10, "child"), (5, 10, "child"), (9, 10, "sibling"),
              (2, 11, "child"), (3, 11, "child"), (2, 12, "child"), (3, 12, "child"), (11, 12, "sibling"),
              (1, 13, "sibling"), (1, 14, "spouse")]
    r = scenario(people, stored, 8)
    off = centred(r, people)
    assert len(off) == 3  # Alex+Carissa, Frederic+Florence, Thibaut+Allison each centred over their children
    x = r["x"]
    assert x[13] < x[1] < x[14] and r["y"][13] == r["y"][1]  # Paul's sister beside him, his second wife next to him
    assert abs((min(x[2], x[4], x[6]) + max(x[2], x[4], x[6])) / 2 - x[1]) <= 1  # Paul (not his second wife) over the middle of his sons


def test_blended_family():
    # root's parents split up and both remarried; half-siblings on each side; a step-parent's own child
    people = {1: ("Root", "M", 1990), 2: ("Dad", "M", 1960), 3: ("Mom", "F", 1962), 4: ("Stepmom", "F", 1965), 5: ("Stepdad", "M", 1958),
              6: ("HalfD", "F", 1998), 7: ("HalfM", "M", 1996), 8: ("StepKid", "F", 1985), 9: ("Sis", "F", 1992), 10: ("Wife", "F", 1991),
              11: ("Kid", "M", 2018)}
    stored = [(2, 3, "ex_spouse"), (2, 4, "spouse"), (3, 5, "spouse"), (2, 1, "child"), (3, 1, "child"), (2, 9, "child"), (3, 9, "child"),
              (1, 9, "sibling"), (2, 6, "child"), (4, 6, "child"), (3, 7, "child"), (5, 7, "child"), (5, 8, "child"), (1, 6, "half_sibling"),
              (1, 7, "half_sibling"), (1, 10, "spouse"), (1, 11, "child"), (10, 11, "child")]
    r = scenario(people, stored, 1)
    list(check_layout(r, people))
    x, y = r["x"], r["y"]
    assert y[2] == y[3] == y[4] == y[5] < y[1] == y[9] == y[6] == y[7] == y[8] == y[10] < y[11]
    # Dad with his new wife, Mom with her new husband, both couples above the children row
    cp = {tuple(sorted((c["a"], c["b"]))) for c in r["couples"]}
    assert (2, 4) in cp and (3, 5) in cp and (1, 10) in cp
    assert abs((x[1] + x[10] + r["W"]) / 2 - (x[11] + r["W"] / 2)) <= 1  # Kid under Root and Wife


def test_deep_line_and_single_parents():
    # four generations down from a single great-grandmother; a single father with three children; one child unmarried with a child
    people = {1: ("Gran", "F", 1930), 2: ("Son", "M", 1955), 3: ("Dau", "F", 1958), 4: ("GK1", "M", 1980), 5: ("GK2", "F", 1982), 6: ("GK3", "M", 1985),
              7: ("GK4", "F", 1984), 8: ("GGK1", "M", 2010), 9: ("GGK2", "F", 2012), 10: ("SonInLaw", "M", 1983), 11: ("GGK3", "M", 2015)}
    stored = [(1, 2, "child"), (1, 3, "child"), (2, 3, "sibling"), (2, 4, "child"), (2, 5, "child"), (2, 6, "child"), (4, 5, "sibling"),
              (5, 6, "sibling"), (4, 6, "sibling"), (3, 7, "child"), (4, 8, "child"), (4, 9, "child"), (8, 9, "sibling"), (7, 10, "spouse"),
              (7, 11, "child"), (10, 11, "child")]
    r = scenario(people, stored, 1)
    off = centred(r, people)
    x, y = r["x"], r["y"]
    assert len({y[1], y[2], y[4], y[8]}) == 4
    # a single parent is centred over their children too
    for p, kids in ((1, [2, 3]), (2, [4, 5, 6]), (4, [8, 9]), (3, [7])):
        mid = (min(x[k] for k in kids) + max(x[k] for k in kids)) / 2
        assert abs(x[p] - mid) <= 1, f"{people[p][0]} is not over their children"
    assert off == [] or all(d <= 1 for _, _, d in off)


def test_in_laws_hang_above_the_spouse_and_siblings_keep_birth_order():
    people = {1: ("Me", "F", 1980), 2: ("Hub", "M", 1978), 3: ("MIL", "F", 1950), 4: ("FIL", "M", 1948), 5: ("HubBro", "M", 1975),
              6: ("HubSis", "F", 1982), 7: ("Mom", "F", 1955), 8: ("Dad", "M", 1952), 9: ("Bro", "M", 1978), 10: ("Sis", "F", 1985),
              11: ("Kid", "F", 2010), 12: ("HubBroWife", "F", 1976), 13: ("Nephew", "M", 2005)}
    stored = [(1, 2, "spouse"), (3, 4, "spouse"), (3, 2, "child"), (4, 2, "child"), (3, 5, "child"), (4, 5, "child"), (3, 6, "child"), (4, 6, "child"),
              (2, 5, "sibling"), (2, 6, "sibling"), (5, 6, "sibling"), (7, 8, "spouse"), (7, 1, "child"), (8, 1, "child"), (7, 9, "child"),
              (8, 9, "child"), (7, 10, "child"), (8, 10, "child"), (1, 9, "sibling"), (1, 10, "sibling"), (9, 10, "sibling"),
              (1, 11, "child"), (2, 11, "child"), (5, 12, "spouse"), (5, 13, "child"), (12, 13, "child")]
    r = scenario(people, stored, 1)
    centred(r, people)
    x, y = r["x"], r["y"]
    assert x[1] < x[2]  # me on the left, my husband on the right
    assert x[9] < x[10] < x[1]  # my brother and sister on my side (left), in birth order
    assert x[2] < x[5] < x[6]  # my husband's brother and sister on his side (right), in birth order
    assert y[3] == y[4] == y[7] == y[8] < y[1]
    assert x[7] < x[3]  # my parents left of his parents
    assert abs((x[1] + x[2] + r["W"]) / 2 - (x[11] + r["W"] / 2)) <= 1


def test_nothing_overlaps_in_a_big_generated_family():
    import random
    rnd = random.Random(4)
    people, stored, nid = {}, [], [0]

    def person(y):
        nid[0] += 1
        people[nid[0]] = (f"P{nid[0]}", rnd.choice("MF"), y)
        return nid[0]

    def family(a, y, depth):
        sp = person(y + rnd.randint(-3, 3)); stored.append((a, sp, "spouse"))
        kids = [person(y + 25 + i * 2) for i in range(rnd.randint(1, 4))]
        for k in kids:
            stored.append((a, k, "child")); stored.append((sp, k, "child"))
        for i in range(len(kids)):
            for j in range(i + 1, len(kids)):
                stored.append((kids[i], kids[j], "sibling"))
        if depth:
            for k in kids:
                if rnd.random() < .8:
                    family(k, y + 27, depth - 1)
        return kids
    top = person(1900); family(top, 1900, 3)
    root = [i for i, (n, s, y) in people.items() if 1950 < y < 1990][5]
    r = scenario(people, stored, root)
    list(check_layout(r, people))
    assert len(people) > 40


def test_messy_relations_never_hang():
    """Every relation type, missing inverses, implied edges, folded people, cycles: the layout must always finish.
    (0.11.3 froze the browser on real data: a map changed while it was being iterated.)"""
    import random
    types = FAM
    inv = dict(zip(types, ["child", "parent", "sibling", "half_sibling", "spouse", "partner", "ex_spouse", "grandchild", "grandparent",
                           "great_grandchild", "great_grandparent", "niece_nephew", "aunt_uncle", "cousin", "child_in_law", "parent_in_law",
                           "sibling_in_law", "step_child", "step_parent", "step_sibling", "godchild", "godparent", "relative"]))
    script = KIN + """
const typeWord = (t) => t;
const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = [];
for (const c of cases) {
  const t0 = Date.now();
  const L = familyLayout(c.g, new Set(c.fam), typeWord, new Set(c.hidden));
  const bad = [...L.gen.keys()].filter((id) => !Number.isFinite(L.x.get(id)) || !Number.isFinite(L.y.get(id)));
  out.push({ ms: Date.now() - t0, bad, drawn: L.gen.size, width: L.width });
}
console.log(JSON.stringify(out));
"""
    cases = []
    for seed in range(300):
        rnd = random.Random(seed)
        n = rnd.randint(2, 30)
        nodes = [{"id": i, "fn": f"P{i}", "gender": rnd.choice(["M", "F", None]), "birthday": {"year": rnd.randint(1900, 2020)} if rnd.random() < .7 else None}
                 for i in range(1, n + 1)]
        edges = []
        for _ in range(rnd.randint(0, n * 3)):
            a, b, t = rnd.randint(1, n), rnd.randint(1, n), rnd.choice(types)
            edges.append({"from": a, "to": b, "type": t})
            if rnd.random() < .8:
                edges.append({"from": b, "to": a, "type": inv[t]})
            if rnd.random() < .1:
                edges.append({"from": 1, "to": b, "type": rnd.choice(types), "implied": True})
        hidden = [x["id"] for x in nodes if rnd.random() < .15]
        cases.append({"g": {"root": 1, "nodes": nodes, "edges": edges}, "fam": types, "hidden": hidden})
    out = subprocess.run([NODE, "-e", script], input=json.dumps(cases), capture_output=True, text=True, check=True, timeout=60)
    results = json.loads(out.stdout)
    assert len(results) == 300
    for i, r in enumerate(results):
        assert not r["bad"], f"case {i}: no position for {r['bad']}"
        assert r["ms"] < 1000, f"case {i} took {r['ms']} ms"
