"""Glue used by the app: list of label strings -> resolved items -> interaction cards."""
from . import advice, check, rx
from .store import SourceUnavailable

CONFIRM_BELOW = 0.85  # below this OCR confidence the confirm screen asks "is this right?"


def resolve(raw: str | None, confidence: float = 1.0) -> dict:
    """One list entry -> what the confirm screen needs."""
    try:
        rec = rx.resolve(raw)
    except SourceUnavailable:
        rec = {"status": "unavailable", "ingredients": [], "score": None}
    return dict(raw=raw, status=rec["status"], ingredients=rec["ingredients"],
                names=[i["name"] for i in rec["ingredients"]],
                unclear=confidence < CONFIRM_BELOW)


def analyze(labels: list[str]) -> dict:
    """Run every confirmed label through RxNorm + the label checker."""
    items = [dict(label=l, **resolve(l)) for l in labels if l and l.strip()]
    ok = [i for i in items if i["ingredients"]]
    res = check.check([dict(label=i["label"], ingredients=i["ingredients"]) for i in ok])
    cards = [advice.card(p) for p in res["pairs"]]
    return dict(items=items, cards=cards,
                checked=res["checked"], clear=res["clear"],
                not_checked=[i["label"] for i in items if not i["ingredients"]],
                no_label=res["no_label"], unavailable=res["unavailable"])


def merge_bottles(existing: list[str | None], bottles: list[dict]) -> tuple[list[dict], int, int]:
    """Bottles read from an extra photo -> (the ones to append, n duplicates, n unreadable).
    A bottle is a duplicate if its text, or its active ingredient, is already on the list."""
    have_text = {e.strip().lower() for e in existing if e}
    have_ing = {frozenset(resolve(e)["names"]) for e in existing if e} - {frozenset()}
    new, dupes, unreadable = [], 0, 0
    for b in bottles:
        name = b.get("drug_name")
        if not name:
            unreadable += 1
            continue
        names = frozenset(resolve(name, b.get("confidence", 1.0))["names"])
        if name.strip().lower() in have_text or (names and names in have_ing):
            dupes += 1
            continue
        new.append(b)
        have_text.add(name.strip().lower())
        if names:
            have_ing.add(names)
    return new, dupes, unreadable
