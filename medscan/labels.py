"""openFDA drug-label client: the interaction text FDA-approved labels contain."""
import re

from .store import Cache, get_json

URL = "https://api.fda.gov/drug/label.json"
_cache = Cache("labels")

# OTC labels have no drug_interactions section; these fields carry the equivalent warnings.
OTC_FIELDS = ["do_not_use", "ask_doctor", "ask_doctor_or_pharmacist", "stop_use", "warnings"]


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def fetch(ingredient: str) -> dict:
    """Interaction text for one ingredient. Cached. Returns
    {name, text, source, brands, set_id, effective, kind} with text == '' if none found."""
    key = ingredient.lower()
    hit = _cache.get(key)
    if hit is None:
        hit = _fetch(key)
        _cache.set(key, hit)
        _cache.save()
    return hit


def _search(query: str, limit: int = 8) -> list[dict]:
    d = get_json(URL, {"search": query, "limit": limit}) or {}
    return d.get("results", [])


def _single(r: dict, name: str) -> bool:
    """A label for this ingredient alone (not a combination product)."""
    o = r.get("openfda", {})
    gens = {g.lower() for g in o.get("generic_name", [])}
    if len(gens) != 1 or name not in next(iter(gens)):
        return False  # kits/co-packs list several generic names
    return len(o.get("substance_name", [])) <= 1


def _fetch(name: str) -> dict:
    base = {"name": name, "text": "", "source": "", "brands": [], "set_id": "",
            "effective": "", "kind": "none"}
    q = f'openfda.generic_name:"{name}"'
    for kind, extra in (("rx", " AND _exists_:drug_interactions"),
                        ("otc", ' AND openfda.product_type:"HUMAN OTC DRUG"')):
        results = [r for r in _search(q + extra, limit=25) if _single(r, name)]
        if kind == "rx":
            texts = [(_clean(" ".join(r["drug_interactions"])), r) for r in results
                     if r.get("drug_interactions")]
        else:
            texts = [(_clean(" ".join(" ".join(r.get(f, [])) for f in OTC_FIELDS)), r)
                     for r in results if any(r.get(f) for f in OTC_FIELDS)]
        if not texts:
            continue
        text, r = max(texts, key=lambda t: len(t[0]))  # the most complete label
        brands = sorted({b.lower() for _, x in texts for b in x.get("openfda", {}).get("brand_name", [])})
        return {**base, "text": text, "kind": kind,
                "brands": brands[:12] if kind == "rx" else [],
                "set_id": r.get("set_id", ""), "effective": r.get("effective_time", ""),
                "source": f"FDA label ({name}), openFDA set_id {r.get('set_id', '')[:8]}"}
    return base
