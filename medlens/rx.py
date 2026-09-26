"""RxNorm / RxClass client: label text -> active ingredient(s) + drug classes.

RxNav is a free NLM service (rxnav.nlm.nih.gov). We never guess: a candidate is only
accepted if its name resembles a word that was actually printed on the label.
"""
import re
from difflib import SequenceMatcher

from .store import Cache, get_json

RXNAV = "https://rxnav.nlm.nih.gov/REST"
_cache = Cache("rx")

# Words on a pharmacy label that are not part of the drug's name.
NOISE = re.compile(
    r"\b(\d+(?:\.\d+)?\s*(?:mg|mcg|ug|g|ml|meq|iu|units?|%)\b|tablets?|tabs?|capsules?|caps?|"
    r"er|xr|xl|sr|dr|ec|cr|la|odt|hcl|hydrochloride|succ|succinate|tartrate|"
    r"besylate|maleate|sulfate|oral|film|coated|extended|delayed|release|chewable|generic|for|"
    r"take|by|mouth|daily|twice|once|every|day)\b|[\d.,/()\-]+", re.I)


def clean(raw: str) -> str:
    return re.sub(r"\s+", " ", NOISE.sub(" ", raw or "")).strip().lower()


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _resembles(cleaned: str, names: list[str]) -> float:
    """Best similarity between any printed word and any candidate name word."""
    words = [w for w in re.findall(r"[a-z]{4,}", cleaned)]
    cands = [w for n in names for w in re.findall(r"[a-z]{4,}", n.lower())]
    return max((_sim(w, c) for w in words for c in cands), default=0.0)


def _ingredients(rxcui: str) -> list[dict]:
    d = get_json(f"{RXNAV}/rxcui/{rxcui}/related.json", {"tty": "IN MIN"}) or {}
    out, seen = [], set()
    for grp in d.get("relatedGroup", {}).get("conceptGroup", []):
        for c in grp.get("conceptProperties", []) or []:
            if grp.get("tty") == "MIN":
                continue  # the multi-ingredient wrapper; its IN parts are listed separately
            if c["rxcui"] not in seen:
                seen.add(c["rxcui"])
                out.append({"rxcui": c["rxcui"], "name": c["name"].lower()})
    return out


def resolve(raw: str | None) -> dict:
    """Return {status: matched|no_match|empty, ingredients: [{rxcui,name}], ...}."""
    cleaned = clean(raw or "")
    rec = {"raw": raw, "status": "empty", "ingredients": [], "score": None}
    if not cleaned:
        return rec
    hit = _cache.get(cleaned)
    if hit is None:
        hit = _lookup(cleaned)
        _cache.set(cleaned, hit)
        _cache.save()
    return {**rec, **hit}


def _lookup(cleaned: str) -> dict:
    d = get_json(f"{RXNAV}/approximateTerm.json", {"term": cleaned, "maxEntries": 6}) or {}
    best = None
    for c in d.get("approximateGroup", {}).get("candidate", []) or []:
        if c.get("source") != "RXNORM":
            continue
        ins = _ingredients(c["rxcui"]) or []
        if not ins:
            # The candidate may itself be an ingredient concept.
            p = (get_json(f"{RXNAV}/rxcui/{c['rxcui']}/properties.json") or {}).get("properties", {})
            if p.get("tty") == "IN":
                ins = [{"rxcui": c["rxcui"], "name": p["name"].lower()}]
        if not ins:
            continue
        sim = _resembles(cleaned, [c.get("name", "")] + [i["name"] for i in ins])
        if best is None or sim > best[0]:
            best = (sim, ins)
    if best is None or best[0] < 0.8:
        return {"status": "no_match", "ingredients": [], "score": best[0] if best else None}
    return {"status": "matched", "ingredients": best[1], "score": round(best[0], 3)}


def classes(rxcui: str) -> list[str]:
    """Established Pharmacologic Classes (EPC), e.g. 'Nonsteroidal Anti-inflammatory Drug'."""
    key = f"classes:{rxcui}"
    hit = _cache.get(key)
    if hit is None:
        d = get_json(f"{RXNAV}/rxclass/class/byRxcui.json",
                     {"rxcui": rxcui, "relaSource": "DAILYMED"}) or {}
        hit = sorted({i["rxclassMinConceptItem"]["className"]
                      for i in d.get("rxclassDrugInfoList", {}).get("rxclassDrugInfo", [])
                      if i["rxclassMinConceptItem"]["classType"] == "EPC"})
        _cache.set(key, hit)
        _cache.save()
    return hit
