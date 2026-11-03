"""Relation types between contacts, their inverses and how they read for a man, a woman or anyone.

A relation row says "the contact's <type> is the related contact" (Ann's sibling is Bob). Types are gender-neutral;
the label shown comes from the related contact's gender (Bob is a man: "Brother").
"""

# type: (inverse type or None, neutral label, male label, female label, vCard 4 RELATED type)
TYPES = {
    "parent": ("child", "Parent", "Father", "Mother", "parent"),
    "child": ("parent", "Child", "Son", "Daughter", "child"),
    "sibling": ("sibling", "Sibling", "Brother", "Sister", "sibling"),
    "half_sibling": ("half_sibling", "Half-sibling", "Half-brother", "Half-sister", "sibling"),
    "spouse": ("spouse", "Spouse", "Husband", "Wife", "spouse"),
    "partner": ("partner", "Partner", "Partner", "Partner", "sweetheart"),
    "ex_spouse": ("ex_spouse", "Former spouse", "Former husband", "Former wife", "kin"),
    "grandparent": ("grandchild", "Grandparent", "Grandfather", "Grandmother", "kin"),
    "grandchild": ("grandparent", "Grandchild", "Grandson", "Granddaughter", "kin"),
    "great_grandparent": ("great_grandchild", "Great-grandparent", "Great-grandfather", "Great-grandmother", "kin"),
    "great_grandchild": ("great_grandparent", "Great-grandchild", "Great-grandson", "Great-granddaughter", "kin"),
    "aunt_uncle": ("niece_nephew", "Aunt or uncle", "Uncle", "Aunt", "kin"),
    "niece_nephew": ("aunt_uncle", "Niece or nephew", "Nephew", "Niece", "kin"),
    "cousin": ("cousin", "Cousin", "Cousin", "Cousin", "kin"),
    "parent_in_law": ("child_in_law", "Parent-in-law", "Father-in-law", "Mother-in-law", "kin"),
    "child_in_law": ("parent_in_law", "Child-in-law", "Son-in-law", "Daughter-in-law", "kin"),
    "sibling_in_law": ("sibling_in_law", "Sibling-in-law", "Brother-in-law", "Sister-in-law", "kin"),
    "step_parent": ("step_child", "Step-parent", "Stepfather", "Stepmother", "parent"),
    "step_child": ("step_parent", "Step-child", "Stepson", "Stepdaughter", "child"),
    "step_sibling": ("step_sibling", "Step-sibling", "Stepbrother", "Stepsister", "sibling"),
    "godparent": ("godchild", "Godparent", "Godfather", "Godmother", "kin"),
    "godchild": ("godparent", "Godchild", "Godson", "Goddaughter", "kin"),
    "relative": ("relative", "Relative", "Relative", "Relative", "kin"),
    "friend": ("friend", "Friend", "Friend", "Friend", "friend"),
    "neighbor": ("neighbor", "Neighbor", "Neighbor", "Neighbor", "neighbor"),
    "colleague": ("colleague", "Colleague", "Colleague", "Colleague", "colleague"),
    "manager": ("report", "Manager", "Manager", "Manager", "co-worker"),
    "report": ("manager", "Reports to them", "Reports to them", "Reports to them", "co-worker"),
    "assistant": (None, "Assistant", "Assistant", "Assistant", "agent"),
    "emergency": (None, "Emergency contact", "Emergency contact", "Emergency contact", "emergency"),
    "other": (None, "Other", "Other", "Other", "contact"),
}

GROUPS = [
    ("Family", ["parent", "child", "sibling", "half_sibling", "spouse", "partner", "ex_spouse", "grandparent", "grandchild",
                "great_grandparent", "great_grandchild", "aunt_uncle", "niece_nephew", "cousin", "parent_in_law",
                "child_in_law", "sibling_in_law", "step_parent", "step_child", "step_sibling", "godparent", "godchild", "relative"]),
    ("Others", ["friend", "neighbor", "colleague", "manager", "report", "assistant", "emergency", "other"]),
]

# Apple Contacts' built-in labels for X-ABRELATEDNAMES (vCard 3)
APPLE = {"Father": ("parent", "M"), "Mother": ("parent", "F"), "Parent": ("parent", None),
         "Brother": ("sibling", "M"), "Sister": ("sibling", "F"), "Child": ("child", None), "Son": ("child", "M"),
         "Daughter": ("child", "F"), "Friend": ("friend", None), "Spouse": ("spouse", None), "Husband": ("spouse", "M"),
         "Wife": ("spouse", "F"), "Partner": ("partner", None), "Assistant": ("assistant", None),
         "Manager": ("manager", None), "Other": ("other", None)}


def inverse(t: str) -> str | None:
    return TYPES.get(t, (None,))[0]


def label(t: str, gender: str | None) -> str:
    row = TYPES.get(t)
    if not row:
        return t.replace("_", " ").capitalize()
    return row[2] if gender == "M" else row[3] if gender == "F" else row[1]


def vcard4_type(t: str) -> str:
    return TYPES.get(t, (None, None, None, None, "contact"))[4]


def from_label(text: str) -> tuple[str, str | None]:
    """'Brother' / 'mother-in-law' / '_$!<Sister>!$_' / 'sibling' -> (type, gender implied for the related person)."""
    s = (text or "").strip()
    if s.startswith("_$!<") and s.endswith(">!$_"):
        s = s[4:-4]
    if s in APPLE:
        return APPLE[s]
    low = s.lower().replace("-", " ").replace("_", " ").strip()
    for t, row in TYPES.items():
        if low == t.replace("_", " "):
            return t, None
        if low == row[1].lower().replace("-", " "):
            return t, None
        if row[2] != row[3]:
            if low == row[2].lower().replace("-", " "):
                return t, "M"
            if low == row[3].lower().replace("-", " "):
                return t, "F"
    # vCard 4 RELATED types
    v4 = {"contact": "other", "acquaintance": "friend", "met": "friend", "co-worker": "colleague", "co-resident": "neighbor",
          "kin": "relative", "sweetheart": "partner", "date": "partner", "crush": "other", "muse": "other", "me": "other",
          "agent": "assistant"}
    if low.replace(" ", "-") in v4:
        return v4[low.replace(" ", "-")], None
    return "other", None


def catalog() -> dict:
    return {"groups": [{"name": g, "types": [{"type": t, "label": TYPES[t][1], "male": TYPES[t][2], "female": TYPES[t][3],
                                              "inverse": TYPES[t][0]} for t in ts]} for g, ts in GROUPS]}
