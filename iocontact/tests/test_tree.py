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


def run(root: int, extra=()) -> dict:
    edges = [{"from": a, "to": b, "type": t} for a, b, t in STORED] + [{"from": b, "to": a, "type": INV[t]} for a, b, t in STORED]
    edges += list(extra)
    g = {"root": root, "nodes": [{"id": i, "fn": n, "gender": s, "birthday": {"year": y}} for i, (n, s, y) in PEOPLE.items()],
         "edges": edges}
    script = KIN + """
const WORDS = { godparent: ['Godfather', 'Godmother', 'Godparent'], godchild: ['Godson', 'Goddaughter', 'Godchild'],
  ex_spouse: ['Former husband', 'Former wife', 'Former spouse'], spouse: ['Husband', 'Wife', 'Spouse'], partner: ['Partner', 'Partner', 'Partner'] };
const typeWord = (t, g) => { const w = WORDS[t] || [t, t, t]; return g === 'M' ? w[0] : g === 'F' ? w[1] : w[2]; };
const [g, fam] = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const L = familyLayout(g, new Set(fam), typeWord);
const o = (m) => Object.fromEntries([...m]);
console.log(JSON.stringify({ label: o(L.label), gen: o(L.gen), x: o(L.x), y: o(L.y), couples: L.couples, families: L.families }));
"""
    out = subprocess.run([NODE, "-e", script], input=json.dumps([g, FAM]), capture_output=True, text=True, check=True)
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
                assert abs(x[a] - x[b]) >= 220, (PEOPLE[a], PEOPLE[b])
    assert y[4] < y[1] < y[8] < y[15]
    # couples sit side by side
    for c in r["couples"]:
        assert y[c["a"]] == y[c["b"]] and abs(abs(x[c["a"]] - x[c["b"]]) - 236) <= 1
    # a family's children sit under (around) their parents
    fam = {tuple(sorted(f["parents"])): sorted(f["children"]) for f in r["families"]}
    assert fam[(4, 5)] == [1, 6, 13] and fam[(6, 7)] == [8, 9] and fam[(1, 2)] == [3]


def test_implied_edges_label_but_do_not_draw():
    r = run(1, [{"from": 1, "to": 14, "type": "niece_nephew", "implied": True}])
    assert r["name"]["Laurent"] == "Nephew"
    assert all(14 not in f["children"] or f["parents"] == [13] for f in r["families"])
