"""Tests run offline against the committed cache (data/cache/), captured from
RxNav and openFDA on the day of the build. Run: .venv/bin/python -m pytest -q"""
import os
import re

os.environ["MEDSCAN_OFFLINE"] = "1"

import pytest

from medscan import advice, check, pipeline, rx, vision


def items(*names):
    return [dict(label=n, ingredients=rx.resolve(n)["ingredients"]) for n in names]


def pair(result, a, b):
    return next((p for p in result["pairs"] if set(p["drugs"]) == {a, b}), None)


# --- name resolution -------------------------------------------------------
@pytest.mark.parametrize("raw,expected", [
    ("SIMVASTATIN 40 MG TAB", ["simvastatin"]),
    ("Metoprolol Succ ER 25mg", ["metoprolol"]),
    ("Mobic 15mg", ["meloxicam"]),
    ("Advil", ["ibuprofen"]),
])
def test_resolves_names_and_brands(raw, expected):
    assert [i["name"] for i in rx.resolve(raw)["ingredients"]] == expected


def test_gibberish_is_not_guessed():
    assert rx.resolve("zzqxv 5mg")["status"] in ("no_match", "empty")
    assert rx.resolve(None)["status"] == "empty"


# --- the interactions the app is demonstrated with -------------------------
def test_simvastatin_clarithromycin_is_high():
    p = pair(check.check(items("Simvastatin 40mg", "Clarithromycin 500mg")),
             "simvastatin", "clarithromycin")
    assert p and p["severity"] == "high"


def test_clopidogrel_omeprazole_high_and_spacing_does_not_help():
    p = pair(check.check(items("Clopidogrel 75mg", "Omeprazole 20mg")), "clopidogrel", "omeprazole")
    assert p["severity"] == "high"
    assert p["spacing"]["kind"] == "no_help"  # the label says 12 hours apart did not fix it


def test_levothyroxine_calcium_spacing_helps():
    p = pair(check.check(items("Levothyroxine 50 mcg", "Calcium carbonate 500 mg")),
             "levothyroxine", "calcium carbonate")
    assert p and p["spacing"]["kind"] == "helps"


def test_two_nsaids_flagged_as_same_family():
    p = pair(check.check(items("Meloxicam 15 mg", "Ibuprofen 200 mg")), "meloxicam", "ibuprofen")
    assert p and p["severity"] == "high"


def test_sertraline_tramadol_serotonin():
    p = pair(check.check(items("Sertraline 50mg", "Tramadol 50mg")), "sertraline", "tramadol")
    assert p and any("serotonin" in t or "agitation" in t for t in p["topics"])


def test_same_ingredient_in_two_products_is_flagged():
    r = check.check(items("Ibuprofen 200mg", "Advil 200mg"))
    assert any(p["findings"][0]["kind"] == "same_ingredient" for p in r["pairs"])


def test_combination_pill_parts_do_not_flag_each_other():
    r = check.check(items("Lisinopril-HCTZ 20/12.5"))
    assert r["pairs"] == []


# --- grading rules ---------------------------------------------------------
def test_grade_reads_label_wording():
    assert check.grade(["Avoid concomitant use of X with Y."], 0)[0] == "high"
    assert check.grade(["Monitor patients receiving X with Y."], 0)[0] == "moderate"
    assert check.grade(["Y is a CYP3A substrate."], 0)[0] == "low"
    assert check.grade(["No dose adjustment of Y is needed with X."], 0)[0] == "none"


def test_strong_word_in_neighbour_sentence_is_capped_at_moderate():
    sents = ["Drug Z is contraindicated with many agents.", "Y is listed here.", "Other text."]
    assert check.grade(sents, 1)[0] == "moderate"


# --- patient wording safety ------------------------------------------------
def test_no_card_ever_tells_the_patient_to_stop():
    r = check.check(items("Simvastatin 40mg", "Clarithromycin 500mg", "Warfarin 5mg",
                          "Ibuprofen 200mg", "Sertraline 50mg", "Tramadol 50mg"))
    assert r["pairs"]
    for p in r["pairs"]:
        c = advice.card(p)
        text = " ".join([c["body"], c["action"], c["escalation"]]).lower()
        assert not re.search(r"stop (?:taking|using|your|the|any)|discontinu", text)
        assert "do not stop" in c["never_stop"].lower()


def test_simplifier_output_with_advice_is_rejected():
    assert advice.FORBIDDEN.search("You should stop taking it.")
    assert advice.FORBIDDEN.search("Take 40 mg less.")
    assert not advice.FORBIDDEN.search("It can make side effects more likely.")


# --- vision parsing: model output is untrusted -----------------------------
def test_vision_parse_coerces_and_never_invents():
    out = vision.parse('```json\n{"bottles":[{"drug_name":"Warfarin 5mg","strength":"5",'
                       '"unit":"tabs","confidence":1.7},{"drug_name":null},"junk"]}\n```')
    b = out["bottles"]
    assert len(b) == 2
    assert b[0]["drug_name"] == "Warfarin 5mg" and b[0]["strength"] is None
    assert b[0]["unit"] is None and b[0]["confidence"] == 1.0
    assert b[1]["drug_name"] is None and b[1]["confidence"] == 0.0


def test_vision_parse_rejects_non_json():
    with pytest.raises(vision.VisionError):
        vision.parse("I can see three bottles.")


def test_low_confidence_reading_is_flagged_for_confirmation():
    assert pipeline.resolve("Metoprolol 25mg", 0.72)["unclear"] is True
    assert pipeline.resolve("Metoprolol 25mg", 0.97)["unclear"] is False


def test_prepare_rotates_downsizes_and_survives_junk():
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (4000, 3000), "white").save(buf, "JPEG")
    assert max(Image.open(io.BytesIO(vision.prepare(buf.getvalue()))).size) == 1800
    assert vision.prepare(b"junk") == b"junk"


# --- OCR route: free text goes in, so only real ingredient names may come out ---
@pytest.mark.parametrize("line", ["(NSAID)", "Take 1 tablet every morning", "Refills: 3",
                                  "Dr. A. Rivera", "Dietary Supplement"])
def test_ocr_lines_that_are_not_drugs_are_rejected(line):
    assert vision._resolve_printed(line) is None


@pytest.mark.parametrize("line,name", [("SIMVASTATIN 40 MG", "simvastatin"),
                                       ("WARFARINSODIUM 5 MG", "warfarin"),
                                       ("LEVOTHYROXINE 75 MCG", "levothyroxine")])
def test_ocr_lines_with_drug_names_resolve_even_when_glued(line, name):
    assert [i["name"] for i in vision._resolve_printed(line)["ingredients"]] == [name]


@pytest.mark.parametrize("line", ["DEMO PHARMACY", "Qty:30 Refills:3", "Dr.A.Rivera", "Rx#000-4521"])
def test_ocr_skips_pharmacy_boilerplate_before_any_lookup(line):
    assert vision._SKIP.search(line)
