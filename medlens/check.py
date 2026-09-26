"""Interaction checker. For every pair of medicines, look for the other drug (by name,
brand or drug class) in each FDA label's interaction text, keep the sentence as
evidence, and grade severity from the label's own wording.

Nothing here is a clinical model. The severity is a reading of what the label says,
and every finding carries the quote it came from, so it can be audited.
"""
import re
from itertools import combinations

from . import labels, rx
from .store import SourceUnavailable

RANK = {"none": 0, "low": 1, "moderate": 2, "high": 3}

# --- how a drug is referred to inside other drugs' labels ---------------------
# Class name (RxClass EPC, lower-case, matched as a substring) -> phrases labels use for it.
CLASS_TERMS = {
    "nonsteroidal anti-inflammatory drug": [r"nsaids?", r"non-?steroidal anti-inflammatory"],
    "hmg-coa reductase inhibitor": [r"statins?", r"hmg-coa reductase inhibitors?"],
    "serotonin reuptake inhibitor": [r"ssris?", r"snris?", r"serotonin.norepinephrine reuptake inhibitors?",
                                     r"selective serotonin reuptake inhibitors?",
                                     r"serotonergic (?:drugs?|agents?|medications?)"],
    "angiotensin converting enzyme inhibitor": [r"ace inhibitors?", r"angiotensin.converting enzyme inhibitors?"],
    "angiotensin 2 receptor blocker": [r"arbs?", r"angiotensin (?:ii )?receptor blockers?"],
    "proton pump inhibitor": [r"ppis?", r"proton pump inhibitors?"],
    "thiazide diuretic": [r"thiazides?", r"thiazide diuretics?"],
    "beta-adrenergic blocker": [r"beta.?blockers?", r"beta.adrenergic blocking"],
    "calcium channel blocker": [r"calcium channel blockers?"],
    "benzodiazepine": [r"benzodiazepines?"],
    "opioid agonist": [r"opioids?", r"opiate"],
    "vitamin k antagonist": [r"anticoagulants?", r"coumarin", r"vitamin k antagonists?"],
    "factor xa inhibitor": [r"anticoagulants?", r"factor xa inhibitors?"],
    "platelet aggregation inhibitor": [r"antiplatelet", r"platelet aggregation inhibitors?"],
    "azole antifungal": [r"azole antifungals?"],
    "macrolide antimicrobial": [r"macrolides?"],
    "fluoroquinolone antibacterial": [r"fluoroquinolones?", r"quinolones?"],
    "sulfonylurea": [r"sulfonylureas?"],
    "tricyclic antidepressant": [r"tricyclic"],
    "monoamine oxidase inhibitor": [r"maois?", r"monoamine oxidase inhibitors?"],
    "loop diuretic": [r"loop diuretics?"],
    "potassium-sparing diuretic": [r"potassium.sparing"],
}
# Ingredient -> extra phrases (things labels say that are not the generic name).
INGREDIENT_TERMS = {
    "calcium carbonate": [r"calcium(?! channel)", r"antacids?"],
    "calcium acetate": [r"calcium(?! channel)"],
    "aspirin": [r"salicylates?", r"acetylsalicylic"],
    "levothyroxine": [r"thyroid hormones?"],
    "acetaminophen": [r"paracetamol"],
    "magnesium hydroxide": [r"magnesium", r"antacids?"],
    "ferrous sulfate": [r"iron (?:supplements?|preparations?|salts?)"],
}
# Classes where taking two together is itself the problem.
DUPLICATION_CLASSES = {
    "nonsteroidal anti-inflammatory drug": "two NSAID pain relievers",
    "hmg-coa reductase inhibitor": "two statin cholesterol medicines",
    "serotonin reuptake inhibitor": "two serotonin-type antidepressants",
    "proton pump inhibitor": "two acid-reducing (PPI) medicines",
    "benzodiazepine": "two benzodiazepine medicines",
    "opioid agonist": "two opioid pain medicines",
    "angiotensin converting enzyme inhibitor": "two ACE-inhibitor blood pressure medicines",
}

# --- reading severity out of a label sentence --------------------------------
HIGH = re.compile(r"contraindicat|\bdo not (?:use|take|administer|co-?administer)|must not|"
                  r"should not be (?:used|taken|co-?administered)|not recommended|"
                  r"\bavoid\b|prohibited|life-threatening|fatal", re.I)
MODERATE = re.compile(r"monitor|caution|dose (?:reduction|adjustment|modification)|adjust|"
                      r"reduce (?:the )?dose|(?:increase|decrease|reduce)[sd]? (?:the )?"
                      r"(?:risk|exposure|plasma|serum|concentration|level|effect|efficacy|absorption)|"
                      r"may (?:increase|decrease|potentiate|enhance|reduce|impair)|synergistic|"
                      r"bleeding|toxicity|interfere", re.I)
NEGATED = re.compile(r"\bno (?:clinically )?(?:significant |relevant |dose )?[\w\s]{0,30}?"
                     r"(?:interaction|adjustment|effect|change)|did not (?:alter|affect|change|"
                     r"significantly)|not (?:expected|been shown) to|without (?:dose )?adjustment|"
                     r"no evidence|co-?administration with certain drugs|with other drugs can lead", re.I)

TOPICS = [  # (evidence regex, "get help right away if..." text)
    (r"bleed|hemorrh|anticoag|antiplatelet",
     "black or bloody stools, vomiting blood, unusual bruising, or bleeding that won't stop"),
    (r"serotonin syndrome|serotonergic",
     "agitation, shaking, sweating, fever, or a racing heartbeat"),
    (r"\bQT\b|arrhythm|torsade|bradycardia|heart block",
     "fainting, or a very slow, fast or irregular heartbeat"),
    (r"myopathy|rhabdomyolysis|muscle (?:pain|weakness|tenderness)",
     "unexplained muscle pain, weakness, or dark urine"),
    (r"hypotension|blood pressure",
     "dizziness, fainting, or a very low blood pressure reading"),
    (r"renal|kidney|nephro",
     "much less urine than usual, or new swelling in your legs or face"),
    (r"hepat|liver",
     "yellow skin or eyes, or dark urine"),
    (r"sedat|respiratory depression|CNS depression",
     "extreme sleepiness, or slow or shallow breathing"),
    (r"hypoglyc",
     "shakiness, sweating, confusion, or a very low blood sugar reading"),
    (r"hyperkal|potassium",
     "muscle weakness or a slow or irregular heartbeat"),
]


def _sentences(text: str) -> list[str]:
    t = re.sub(r"\b(e\.g|i\.e|vs|approx|Dr|St)\.", lambda m: m.group(1) + "<dot>", text)
    t = re.sub(r"\[\s*see[^\]]*\]", "", t, flags=re.I)              # [see Warnings ( 5.2 )]
    t = re.sub(r"\(\s*\d+(?:\.\d+)*(?:\s*,\s*\d+(?:\.\d+)*)*\s*\)", "", t)  # ( 5.2 , 5.6 )
    t = re.sub(r"\s(?=\d{1,2}\.\d{1,2}\s+[A-Z])", ". ", t)     # '... 7.4 Tacrolimus' starts a new topic
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(\[\d])", t)
    return [re.sub(r"\s+", " ", p.replace("<dot>", ".")).strip() for p in parts if p.strip()]


SPACING = re.compile(r"\b(?:at least|separat\w+|apart|hours? (?:before|after)|stagger\w*)\b"
                     r"[^.]{0,80}\bhours?\b|\bhours? apart\b|\bat least \d+ (?:hours?|minutes?)\b", re.I)
NO_SPACING_HELP = re.compile(r"\beven\b[^.]{0,120}\bapart\b|\bor (?:\d+ )?hours? apart\b|regardless of (?:the )?timing|"
                             r"separat\w+[^.]{0,40}(?:does|will) not", re.I)


def _spacing(text: str) -> str:
    """'' | 'helps' | 'no_help' -- only when the label's own words say so."""
    if NO_SPACING_HELP.search(text):
        return "no_help"
    return "helps" if SPACING.search(text) else ""


def grade(sents: list[str], i: int) -> tuple[str, str]:
    """Severity of the mention in sents[i], read from that sentence and its neighbours
    (labels put 'Contraindicated' one sentence away from the drug list). Returns
    (severity, the sentence whose wording decided it)."""
    if NEGATED.search(sents[i]):
        return "none", sents[i]
    around = sents[max(0, i - 1):i + 2]
    for pattern, sev in ((HIGH, "high"), (MODERATE, "moderate")):
        # the mention's own sentence first, then the nearest neighbour
        for s in sorted(range(len(around)), key=lambda k: abs(max(0, i - 1) + k - i)):
            if pattern.search(around[s]) and not NEGATED.search(around[s]):
                own = max(0, i - 1) + s == i
                # A strong word in a *neighbouring* sentence may be about another drug:
                # only the mention's own sentence can make it "high".
                return (sev if own or sev != "high" else "moderate"), around[s]
    return "low", sents[i]


def _trim(s: str, n: int = 380) -> str:
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + " …"


class Drug:
    """One active ingredient plus how to find it in other drugs' labels."""

    def __init__(self, name: str, rxcui: str):
        self.name, self.rxcui = name, rxcui
        self.classes = [c.lower() for c in rx.classes(rxcui)]
        self.label = labels.fetch(name)
        pats = [re.escape(name)] + INGREDIENT_TERMS.get(name, [])
        pats += [re.escape(b) for b in self.label["brands"] if name not in b and len(b) > 3]
        self.name_re = re.compile(r"\b(?:" + "|".join(pats) + r")", re.I)
        cpats = [p for key, terms in CLASS_TERMS.items()
                 if any(key in c for c in self.classes) for p in terms]
        self.class_re = re.compile(r"\b(?:" + "|".join(cpats) + r")\b", re.I) if cpats else None


def _mentions(source: Drug, target: Drug) -> list[dict]:
    """Sentences in source's label that refer to target."""
    sents = _sentences(source.label["text"])
    out = []
    for i, s in enumerate(sents):
        via = "name" if target.name_re.search(s) else (
            "class" if target.class_re and target.class_re.search(s) else None)
        if not via:
            continue
        sev, why = grade(sents, i)
        if sev != "none":
            quote = _trim(s if why == s else f"{s} {why}" if sents.index(why) > i else f"{why} {s}")
            out.append(dict(kind="label", severity=sev, via=via, quote=quote,
                            spacing=_spacing(s + " " + why),
                            label_of=source.name, mentions=target.name,
                            source=source.label["source"]))
    return out


def check_pair(a: Drug, b: Drug) -> dict | None:
    finds = _mentions(a, b) + _mentions(b, a)
    for c in set(a.classes) & set(b.classes):
        c = next((k for k in DUPLICATION_CLASSES if k in c), None)
        if c:
            finds.append(dict(kind="duplication", severity="moderate", via="class",
                              quote=f"{a.name.title()} and {b.name.title()} are both in the "
                                    f"class '{c}'. Taking {DUPLICATION_CLASSES[c]} together is "
                                    "usually not intended.",
                              label_of="", mentions="", source="RxClass (DailyMed EPC)"))
    if not finds:
        return None
    # Name mentions outrank class mentions; then by severity. Keep the best few.
    finds.sort(key=lambda f: (-RANK[f["severity"]], f["via"] != "name"))
    worst = finds[0]["severity"]
    seen, keep = set(), []
    for f in finds:
        if f["quote"] not in seen:
            seen.add(f["quote"])
            keep.append(f)
    return dict(drugs=[a.name, b.name], severity=worst, findings=keep[:3],
                spacing=_pair_spacing(keep),
                topics=_topics(" ".join(f["quote"] for f in keep[:3])))


def _pair_spacing(finds: list[dict]) -> dict | None:
    """'won't help' wins over 'helps': never promise a fix the label denies."""
    for kind in ("no_help", "helps"):
        f = next((f for f in finds if f.get("spacing") == kind), None)
        if f:
            return dict(kind=kind, quote=f["quote"])
    return None


def _topics(text: str) -> list[str]:
    return [msg for pat, msg in TOPICS if re.search(pat, text, re.I)][:2]


def check(items: list[dict]) -> dict:
    """items: [{'label': 'Meloxicam 15 mg', 'ingredients': [{'rxcui','name'}, ...]}]
    Returns pairs (flagged), the ingredients actually checked, and what could not be."""
    drugs, unavailable, no_label = {}, [], []
    for it in items:
        for ing in it["ingredients"]:
            if ing["name"] in drugs:
                continue
            try:
                d = Drug(ing["name"], ing["rxcui"])
            except SourceUnavailable:
                unavailable.append(ing["name"])
                continue
            drugs[d.name] = d
            if not d.label["text"]:
                no_label.append(d.name)
    pairs = []
    same_product = [{i["name"] for i in it["ingredients"]} for it in items]
    for a, b in combinations(drugs.values(), 2):
        if any({a.name, b.name} <= grp for grp in same_product):
            continue  # both are parts of one combination pill
        p = check_pair(a, b)
        if p and p["severity"] != "low":
            pairs.append(p)
        elif p:
            p["minor"] = True
            pairs.append(p)
    # The same ingredient in two different products: possible double dosing.
    counts = {}
    for it in items:
        for name in {i["name"] for i in it["ingredients"]}:
            counts.setdefault(name, []).append(it["label"])
    for name, labels_ in counts.items():
        if len(labels_) > 1:
            pairs.append(dict(drugs=[name, name], severity="high", topics=[],
                              findings=[dict(kind="same_ingredient", severity="high", via="name",
                                             quote=f"{name.title()} is the active ingredient in "
                                                   f"more than one item on your list: "
                                                   f"{'; '.join(labels_)}. You may be taking it twice.",
                                             label_of="", mentions="", source="Your medicine list")]))
    pairs.sort(key=lambda p: -RANK[p["severity"]])
    flagged = {n for p in pairs if not p.get("minor") for n in p["drugs"]}
    return dict(pairs=pairs, checked=list(drugs), clear=[n for n in drugs if n not in flagged],
                no_label=no_label, unavailable=unavailable)
