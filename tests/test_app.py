"""App-level flows through Streamlit's test harness (offline, uses the committed cache)."""
import os
from pathlib import Path

os.environ["MEDSCAN_OFFLINE"] = "1"

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")
SAVED = {"meds": [dict(id="a1", label="Warfarin 5 mg", ingredients=["warfarin"], times=[]),
                  dict(id="a2", label="Ibuprofen 200 mg", ingredients=["ibuprofen"], times=[])],
         "taken": {}}


def start():
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["cabinet"] = {"meds": [dict(m) for m in SAVED["meds"]], "taken": {}}
    at.run()
    return at


def click(at, text):
    [b for b in at.button if text in b.label][0].click().run()


def test_scan_results_cover_only_the_scanned_medicines_by_default():
    at = start()
    click(at, "Try demo bottles")
    assert [c for c in at.checkbox if c.key == "with_cab"][0].value is False
    click(at, "Looks right")
    checked = at.session_state.result["checked"]
    assert "simvastatin" in checked and not {"warfarin", "ibuprofen"} & set(checked)


def test_cabinet_is_included_only_when_the_user_opts_in():
    at = start()
    click(at, "Try demo bottles")
    [c for c in at.checkbox if c.key == "with_cab"][0].check().run()
    click(at, "Looks right")
    assert {"warfarin", "ibuprofen", "simvastatin"} <= set(at.session_state.result["checked"])


def test_saving_from_results_adds_only_what_was_scanned():
    at = start()
    click(at, "Try demo bottles")
    [c for c in at.checkbox if c.key == "with_cab"][0].check().run()
    click(at, "Looks right")
    at.session_state["cabinet"]["meds"] = [m for m in at.session_state["cabinet"]["meds"]
                                           if m["id"] != "a2"]          # ibuprofen no longer saved
    click(at, "Save to my cabinet")
    labels = [m["label"] for m in at.session_state.cabinet["meds"]]
    assert "Ibuprofen 200 mg" not in labels                              # cabinet-only drug not re-added
    assert "SIMVASTATIN 40 MG TAB" in labels


def test_add_scanned_medicines_to_cabinet_from_the_confirm_screen():
    at = start()
    click(at, "Try demo bottles")
    click(at, "Add 5 to my cabinet")
    assert len(at.session_state.cabinet["meds"]) == 7
    assert [b for b in at.button if "All saved" in b.label][0].disabled


def test_clear_cabinet_asks_first_and_can_be_cancelled():
    at = start()
    click(at, "Cabinet")
    click(at, "Clear cabinet")
    assert len(at.session_state.cabinet["meds"]) == 2             # nothing removed yet
    assert any("Yes, clear it" in b.label for b in at.button)
    click(at, "Cancel")
    assert len(at.session_state.cabinet["meds"]) == 2
    assert any("Clear cabinet" in b.label for b in at.button)


def test_clear_cabinet_empties_it_and_queues_the_browser_write():
    at = start()
    click(at, "Cabinet")
    click(at, "Clear cabinet")
    click(at, "Yes, clear it")
    assert at.session_state.cabinet == {"meds": [], "taken": {}}
    assert at.session_state.cab_write["data"] == {"meds": [], "taken": {}}   # so a reload stays empty
    assert not any("Clear cabinet" in b.label for b in at.button)             # nothing left to clear
