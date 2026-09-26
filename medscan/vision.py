"""Read medicine bottle labels from a photo with a free vision model.

Backends (MEDSCAN_VISION, default "auto"):
  gemini  Google Gemini free tier. Needs GEMINI_API_KEY (free, no card:
          https://aistudio.google.com/apikey). Model: MEDSCAN_GEMINI_MODEL.
  ollama  Local model, no key, nothing leaves the machine. MEDSCAN_OLLAMA_MODEL
          (default qwen2.5vl:7b).
  ocr     No key, no model download: an on-device OCR engine reads the text and RxNav
          decides which lines are drug names. Works anywhere, including Streamlit Cloud.
  demo    A fixed example list, for trying the app without a model.

Model output is untrusted: parse() coerces it and nulls anything malformed.
A wrong drug name is worse than a missing one.
"""
import base64
import json
import os
import re
from io import BytesIO

import requests

PROMPT = """Look at this photo of pharmacy medicine bottles or boxes and list every
distinct medicine whose drug name you can read.

Reply with a single JSON object and nothing else:
{"bottles": [{"drug_name": string or null,
              "strength": number or null,
              "unit": "mg" | "mcg" | "g" | "mL" | null,
              "directions": string or null,
              "confidence": number from 0 to 1}]}

How to fill it in:
- One entry per physical bottle or box. Never merge two bottles, never add one you cannot see.
- drug_name is copied letter for letter as printed (keep abbreviations like "ER" or "SUCC").
  Do not correct spelling, expand abbreviations, or swap a brand for its generic.
- If a label is blurry, glared out, cut off or turned away, set that field to null.
  Never fill a gap with a plausible drug name; null is the right answer.
- confidence is how sure you are of your own reading of that bottle: low for curved,
  glossy or shadowed labels, high only for crisp text.
- Only the drug panel matters. Leave out patient names, addresses, prescriber, pharmacy,
  Rx and refill numbers and barcodes.
- Loose pills with no label are not identifiable: return {"bottles": []}."""

DEMO = {"bottles": [
    {"drug_name": "SIMVASTATIN 40 MG TAB", "strength": 40, "unit": "mg",
     "directions": "Take 1 tablet by mouth at bedtime", "confidence": 0.97},
    {"drug_name": "Clarithromycin 500mg", "strength": 500, "unit": "mg",
     "directions": "Take 1 tablet twice daily", "confidence": 0.94},
    {"drug_name": "Levothyroxine 50 mcg", "strength": 50, "unit": "mcg",
     "directions": "Take 1 tablet on an empty stomach", "confidence": 0.95},
    {"drug_name": "Calcium carbonate 500 mg", "strength": 500, "unit": "mg",
     "directions": "Take 1 tablet daily", "confidence": 0.93},
    {"drug_name": "Metoprolol Succ ER 25mg", "strength": 25, "unit": "mg",
     "directions": "Take 1 tablet daily", "confidence": 0.72},
]}


class VisionError(RuntimeError):
    pass


def _key() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def _ocr_installed() -> bool:
    import importlib.util
    return importlib.util.find_spec("rapidocr_onnxruntime") is not None


def available() -> list[str]:
    out = ["gemini"] if _key() else []
    try:
        requests.get("http://localhost:11434/api/tags", timeout=0.4).raise_for_status()
        out.append("ollama")
    except requests.RequestException:
        pass
    if _ocr_installed():
        out.append("ocr")
    return out


def prepare(image: bytes, max_side: int = 1800) -> bytes:
    """Apply the phone's EXIF rotation, downscale, re-encode as JPEG (which also drops
    EXIF/GPS). Undecodable input is returned untouched."""
    try:
        from PIL import Image, ImageOps
        img = ImageOps.exif_transpose(Image.open(BytesIO(image))).convert("RGB")
        img.thumbnail((max_side, max_side))
        out = BytesIO()
        img.save(out, "JPEG", quality=90)
        return out.getvalue()
    except Exception:
        return image


def read_bottles(image: bytes, backend: str = "auto") -> dict:
    if backend == "auto":
        backend = os.environ.get("MEDSCAN_VISION", "auto")
    if backend == "auto":
        found = available()
        if not found:
            raise VisionError("No photo reader is available. Add a free GEMINI_API_KEY, "
                              "or install rapidocr-onnxruntime.")
        backend = found[0]
    if backend == "demo":
        return DEMO
    jpeg = prepare(image)
    if backend == "gemini":
        return parse(_gemini(jpeg))
    if backend == "ollama":
        return parse(_ollama(jpeg))
    if backend == "ocr":
        return _ocr(jpeg)
    raise VisionError(f"Unknown vision backend: {backend}")


def _gemini(jpeg: bytes) -> str:
    if not _key():
        raise VisionError("GEMINI_API_KEY is not set.")
    model = os.environ.get("MEDSCAN_GEMINI_MODEL", "gemini-2.5-flash")
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": _key()}, timeout=60,
        json={"contents": [{"parts": [
                  {"text": PROMPT},
                  {"inline_data": {"mime_type": "image/jpeg",
                                   "data": base64.b64encode(jpeg).decode()}}]}],
              "generationConfig": {"responseMimeType": "application/json",
                                   "temperature": 0}})
    if r.status_code != 200:
        raise VisionError(f"Gemini returned {r.status_code}: {r.text[:160]}")
    try:
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise VisionError("Gemini returned no text (the photo may have been blocked).")


def _ollama(jpeg: bytes) -> str:
    model = os.environ.get("MEDSCAN_OLLAMA_MODEL", "qwen2.5vl:7b")
    try:
        r = requests.post("http://localhost:11434/api/chat", timeout=180, json={
            "model": model, "stream": False, "format": "json", "options": {"temperature": 0},
            "messages": [{"role": "user", "content": PROMPT,
                          "images": [base64.b64encode(jpeg).decode()]}]})
        r.raise_for_status()
        return r.json()["message"]["content"]
    except (requests.RequestException, KeyError) as e:
        raise VisionError(f"Ollama failed: {e}")


_engine = None
_SKIP = re.compile(r"refill|qty|quantity|pharmacy|patient|rx\s*#|\bdr\b|\bdr\.|warning|"
                   r"testing|demo|mock|discard|expires?|\bnpi\b", re.I)


def _resolve_printed(spaced: str) -> dict | None:
    """Resolve an OCR line, but only if the printed text resembles an INGREDIENT name.
    Free text is being fed in, so a brand-only or class-only match ('(NSAID)',
    'every morning') must not become a medicine."""
    from . import rx
    rec = rx.resolve(spaced)
    if rec["status"] != "matched":
        return None
    names = [i["name"] for i in rec["ingredients"]]
    return rec if rx._resembles(rx.clean(spaced), names, names) >= 0.85 else None


def _ocr(jpeg: bytes) -> dict:
    """OCR every text line, keep the lines RxNav can resolve to a real drug name.
    rx.resolve() refuses to guess, so ordinary label text (addresses, directions,
    'Refills: 3') is dropped and never shown as a medicine."""
    global _engine
    from . import rx
    from .store import SourceUnavailable
    try:
        from rapidocr_onnxruntime import RapidOCR
        _engine = _engine or RapidOCR()
        lines, _ = _engine(jpeg)
    except Exception as e:
        raise VisionError(f"On-device OCR failed: {e}")
    bottles, seen = [], set()
    for _box, text, score in lines or []:
        # OCR glues tokens: 'SIMVASTATIN40MG' -> 'SIMVASTATIN 40 MG'
        spaced = re.sub(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])", " ", text).strip()
        if _SKIP.search(spaced) or not re.search(r"[A-Za-z]{5,}", spaced):
            continue
        try:
            rec = _resolve_printed(spaced)
        except SourceUnavailable as e:
            raise VisionError(f"Drug-name service unreachable: {e}")
        if rec is None:
            continue
        key = tuple(sorted(i["name"] for i in rec["ingredients"]))
        if key in seen:
            continue
        seen.add(key)
        m = re.search(r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml)\b", spaced, re.I)
        conf = float(score) * (1.0 if (rec["score"] or 0) >= 0.9 else 0.8)
        bottles.append(dict(drug_name=spaced, strength=float(m.group(1)) if m else None,
                            unit={"ml": "mL"}.get(m.group(2).lower(), m.group(2).lower()) if m else None,
                            directions=None, confidence=round(min(conf, 0.99), 2)))
    return {"bottles": bottles}


def parse(text: str) -> dict:
    """Model text -> {"bottles": [{drug_name, strength, unit, directions, confidence}]}."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        data = json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        try:
            data = json.loads(m.group(0)) if m else None
        except ValueError:
            data = None
    if not isinstance(data, dict):
        raise VisionError("The model did not return usable JSON.")
    num = lambda v: v if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    txt = lambda v: v.strip() if isinstance(v, str) and v.strip() else None
    bottles = []
    for b in data.get("bottles") if isinstance(data.get("bottles"), list) else []:
        if isinstance(b, dict):
            conf = num(b.get("confidence"))
            bottles.append(dict(
                drug_name=txt(b.get("drug_name")), strength=num(b.get("strength")),
                unit=b.get("unit") if b.get("unit") in ("mg", "mcg", "g", "mL") else None,
                directions=txt(b.get("directions")),
                confidence=min(max(float(conf), 0.0), 1.0) if conf is not None else 0.0))
    return {"bottles": bottles}
