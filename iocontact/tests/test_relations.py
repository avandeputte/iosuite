"""Implied relations: worked out from the stated ones, never overriding them."""
from app.relations import infer


def kinds(edges, root):
    return {(r["type"], r["relatedId"]) for r in infer(edges, root)}


def test_sibling_shares_parents_and_family():
    # 1 Ann sibling of 2 Bob; Bob's mother 3; Mom's sister 5 and her son 4; Bob's wife 6; Mom's mother 7; Ann's kid 8
    e = [(1, "sibling", 2), (2, "parent", 3), (3, "sibling", 5), (5, "child", 4), (2, "spouse", 6), (3, "parent", 7), (1, "child", 8)]
    assert kinds(e, 1) == {("parent", 3), ("aunt_uncle", 5), ("cousin", 4), ("sibling_in_law", 6), ("grandparent", 7)}
    assert kinds(e, 8) == {("aunt_uncle", 2), ("aunt_uncle", 6), ("grandparent", 3), ("great_grandparent", 7)}
    assert kinds(e, 6) == {("sibling_in_law", 1), ("parent_in_law", 3), ("niece_nephew", 8)}
    assert ("sibling", 1) not in kinds(e, 2)  # stated, inverse included
    via = {r["relatedId"]: (r["viaId"], r["viaType"]) for r in infer(e, 1)}
    assert via[3] == (2, "sibling")


def test_shared_parent_makes_siblings_and_siblings_are_transitive():
    assert kinds([(1, "parent", 9), (2, "parent", 9)], 1) == {("sibling", 2)}
    assert kinds([(1, "sibling", 2), (2, "sibling", 3)], 3) == {("sibling", 1)}


def test_stated_relations_win():
    # a half-brother through the same mother stays a half-brother; a spouse's child is not guessed as a step-child
    assert kinds([(1, "parent", 9), (2, "parent", 9), (1, "half_sibling", 2)], 1) == set()
    assert kinds([(1, "spouse", 2), (2, "child", 3)], 1) == set()
    assert kinds([(1, "parent", 9), (2, "parent", 9), (1, "friend", 2)], 1) == set()
