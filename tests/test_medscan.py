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


# --- cabinet ----------------------------------------------------------------
from datetime import date, datetime, timezone

from medscan import cabinet


def test_parse_times_accepts_common_forms_and_reports_the_rest():
    good, bad = cabinet.parse_times("8am, 8:30 pm, 20:00, noon, 25:00, 12am")
    assert good == ["00:00", "08:00", "20:00", "20:30"]
    assert bad == ["noon", "25:00"]


def test_add_never_saves_the_same_ingredient_twice():
    cab = cabinet.empty()
    assert cabinet.add(cab, "Advil 200mg", ["ibuprofen"]) == "added"
    assert cabinet.add(cab, "Ibuprofen 400 mg", ["ibuprofen"]) == "exists"
    assert cabinet.add(cab, "Warfarin 5mg", ["warfarin"], ["08:00"]) == "added"
    assert len(cab["meds"]) == 2


def test_remove_also_clears_taken_marks():
    cab = cabinet.empty()
    cabinet.add(cab, "Warfarin 5mg", ["warfarin"], ["08:00"])
    med = cab["meds"][0]
    cabinet.set_taken(cab, date(2026, 9, 26), med, "08:00", True)
    assert cabinet.is_taken(cab, date(2026, 9, 26), med, "08:00")
    cabinet.remove(cab, med["id"])
    assert cab["meds"] == [] and cab["taken"]["2026-09-26"] == []


def test_taken_marks_only_keep_today():
    cab = cabinet.empty()
    cabinet.add(cab, "Warfarin 5mg", ["warfarin"], ["08:00"])
    med = cab["meds"][0]
    cabinet.set_taken(cab, date(2026, 9, 25), med, "08:00", True)
    cabinet.set_taken(cab, date(2026, 9, 26), med, "08:00", True)
    assert list(cab["taken"]) == ["2026-09-26"]


def test_normalize_survives_garbage_from_the_browser():
    assert cabinet.normalize(None) == cabinet.empty()
    assert cabinet.normalize({"meds": "x", "taken": 3}) == cabinet.empty()
    cab = cabinet.normalize({"meds": [{"label": "  Warfarin 5mg ", "times": ["8am", "zz"]}, {"x": 1}, 5]})
    assert [m["label"] for m in cab["meds"]] == ["Warfarin 5mg"]
    assert cab["meds"][0]["times"] == ["08:00"]


def test_ics_has_a_daily_repeating_event_and_an_alarm_per_dose_time():
    cab = cabinet.empty()
    cabinet.add(cab, "Levothyroxine 50 mcg", ["levothyroxine"], ["07:00"])
    cabinet.add(cab, "Metformin 500 mg", ["metformin"], ["08:00", "20:00"])
    cabinet.add(cab, "Ibuprofen 200 mg", ["ibuprofen"])            # no times: no reminder
    ics = cabinet.to_ics(cab, date(2026, 9, 27), datetime(2026, 9, 26, tzinfo=timezone.utc))
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert ics.count("BEGIN:VEVENT") == 3 and ics.count("RRULE:FREQ=DAILY") == 3
    assert ics.count("BEGIN:VALARM") == 3
    assert "DTSTART:20260927T070000" in ics and "SUMMARY:Take Levothyroxine 50 mcg" in ics
    assert "Ibuprofen" not in ics
    assert len({l for l in ics.split("\r\n") if l.startswith("UID:")}) == 3   # unique ids


def test_ics_escapes_and_folds_long_lines():
    cab = cabinet.empty()
    cabinet.add(cab, "Odd, name; with \\ chars " + "x" * 120, ["odd"], ["09:00"])
    ics = cabinet.to_ics(cab, date(2026, 9, 27))
    assert all(len(l.encode()) <= 75 for l in ics.split("\r\n"))
    assert "Odd\\, name\; with" in ics.replace("\r\n ", "")


def test_notify_config_is_plain_json_and_skips_medicines_without_times():
    import json
    cab = cabinet.empty()
    cabinet.add(cab, "Levothyroxine 50 mcg", ["levothyroxine"], ["07:00"])
    cabinet.add(cab, "Ibuprofen 200 mg", ["ibuprofen"])
    med = cab["meds"][0]
    cabinet.set_taken(cab, date(2026, 9, 26), med, "07:00", True)
    cfg = cabinet.notify_config(cab, date(2026, 9, 26))
    json.dumps(cfg)                                            # must serialize for the browser
    assert [m["label"] for m in cfg["meds"]] == ["Levothyroxine 50 mcg"]
    assert cfg["taken"] == [f"{med['id']}@07:00"]
    assert cabinet.notify_config(cab, date(2026, 9, 27))["taken"] == []   # a new day starts clear


def test_contains_matches_by_ingredient_not_by_label():
    cab = cabinet.empty()
    cabinet.add(cab, "Advil 200mg", ["ibuprofen"])
    assert cabinet.contains(cab, "Ibuprofen 400 mg", ["ibuprofen"])
    assert not cabinet.contains(cab, "Warfarin 5 mg", ["warfarin"])
    assert cabinet.contains(cab, "Mystery pill", []) is False
    cabinet.add(cab, "Mystery pill", [])                     # unrecognised: matched by its label
    assert cabinet.contains(cab, "mystery pill", [])
