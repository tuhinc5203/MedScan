"""Patient-facing wording. Deliberately boring and fixed: the model-free text never
tells anyone to stop a medicine, and every claim is attributed to an FDA label.

An optional Gemini pass can restate the quoted label passage in plain words; it is
labelled as a simplification, checked for forbidden advice, and the original quote
is always available underneath.
"""
import os
import re

import requests

ACTION = {
    "high": "Keep taking your medicines as prescribed. Call your pharmacist or doctor "
            "today about this combination.",
    "moderate": "Keep taking your medicines as prescribed. Ask your pharmacist about "
                "this combination at your next visit or call.",
    "low": "Mention this to your pharmacist next time you talk. No change needed now.",
}
NEVER_STOP = ("Do not stop or change any medicine on your own. Stopping some medicines "
              "suddenly can be more dangerous than the interaction.")
DEFAULT_ESCALATION = ("If you feel unwell in a new way after starting this combination, "
                      "call your pharmacist or doctor. For severe symptoms call emergency services.")


def _body(pair: dict) -> str:
    f = pair["findings"][0]
    if f["kind"] == "same_ingredient":
        return f["quote"]
    a, b = (x.title() for x in pair["drugs"])
    if f["kind"] == "duplication":
        return (f"{a} and {b} are in the same family of medicines. Taking both usually adds "
                "side effects without extra benefit.")
    src, tgt = f["label_of"].title(), f["mentions"].title()
    by_class = " (or medicines like it)" if f["via"] == "class" else ""
    if pair["severity"] == "high":
        return (f"The FDA label for {src} gives a strong warning about taking it with "
                f"{tgt}{by_class}, such as saying to avoid the combination.")
    if pair["severity"] == "moderate":
        return (f"The FDA label for {src} says {tgt}{by_class} can change how well it works "
                "or raise the risk of side effects, and advises extra care or monitoring.")
    return f"The FDA label for {src} mentions {tgt}{by_class}."


def _spacing(pair: dict) -> dict | None:
    sp = pair.get("spacing")
    if not sp:
        return None
    if sp["kind"] == "helps":
        return dict(kind="helps", title="Spacing doses apart may help",
                    text="Ask your pharmacist how far apart to take them. The label says: "
                         f"“{sp['quote']}”")
    return dict(kind="no_help", title="Spacing doses apart won't help",
                text="Talk to your pharmacist before taking both. Do not stop a prescribed "
                     "medicine on your own.")


def card(pair: dict) -> dict:
    """One screen card for one flagged pair."""
    a, b = pair["drugs"]
    same = pair["findings"][0]["kind"] == "same_ingredient"
    return dict(
        headline=f"{a.title()} appears twice" if same else f"{a.title()} + {b.title()}",
        severity=pair["severity"], minor=bool(pair.get("minor")),
        body=_body(pair), action=ACTION[pair["severity"]], never_stop=NEVER_STOP,
        escalation=("Get help right away for: " + "; or ".join(pair["topics"]) + "."
                    if pair["topics"] else DEFAULT_ESCALATION),
        spacing=_spacing(pair),
        evidence=[dict(quote=f["quote"], source=f["source"], kind=f["kind"]) for f in pair["findings"]],
    )


# --- optional plain-language restatement (Gemini free tier) -----------------
FORBIDDEN = re.compile(r"\bstop\b|discontinu|do not take|don't take|you should not|"
                       r"switch to|instead of|\d+\s?(?:mg|mcg)\b", re.I)


def simplify(quote: str, a: str, b: str) -> str | None:
    """1-2 sentence restatement of a label passage, or None if unavailable/unsafe."""
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key or not quote:
        return None
    prompt = (f"Restate this FDA drug-label passage about {a} and {b} for a patient, in one "
              "or two short sentences at a 6th-grade reading level. Use ONLY facts in the "
              "passage. Do not add advice, do not tell them to stop, avoid or change "
              f"anything, and do not mention doses.\n\nPassage: {quote}")
    try:
        r = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{os.environ.get('MEDLENS_GEMINI_MODEL', 'gemini-2.5-flash')}:generateContent",
            headers={"x-goog-api-key": key}, timeout=30,
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0, "maxOutputTokens": 200}})
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (requests.RequestException, KeyError, IndexError, ValueError):
        return None
    return None if len(text) > 400 or FORBIDDEN.search(text) else text
