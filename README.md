# MedScan

Take one photo of your pill bottles. MedScan reads the labels, lets you confirm the
list, and flags combinations that shouldn't be taken together. Every flag quotes the
FDA drug label it came from.

> Hackathon demo. Not medical advice. Use prop labels, not real prescription labels.

## How it works

1. **Read** (`medscan/vision.py`): pick whichever is available. **Gemini** (free tier) or
   **Ollama** (local) transcribe each label with a vision model; unreadable fields come back
   `null`, never guessed. With no key at all, **on-device OCR** (RapidOCR) reads the text and
   RxNav decides which lines are drug names, accepting only lines that resemble an actual
   ingredient name (so "(NSAID)" or "every morning" never become medicines).
2. **Confirm**: you fix or remove anything wrong before any advice is produced.
   Low-confidence readings are flagged.
3. **Resolve** (`medscan/rx.py`): [RxNav](https://rxnav.nlm.nih.gov) turns label text
   ("Metoprolol Succ ER 25mg", "Mobic") into active ingredients and drug classes. A match
   must resemble a word actually printed on the label, otherwise it is "not recognised".
4. **Check** (`medscan/check.py`): for every pair, look for the other drug (by name, brand
   or class, e.g. "NSAIDs", "SSRIs") in each drug's
   [openFDA](https://open.fda.gov/apis/drug/label/) label interaction text. The matching
   sentence is kept as evidence and the severity is read from its wording ("contraindicated"
   / "avoid" → high, "monitor" / "may increase" → moderate). Negations ("no dose adjustment
   needed") are ignored. Two products with the same active ingredient are flagged as possible
   double dosing.
5. **Explain** (`medscan/advice.py`): fixed, plain wording. It never tells anyone to stop a
   medicine. A "spacing doses apart" note appears only when the label itself says so
   (for example levothyroxine and calcium), and says spacing *won't* help when the label
   says the effect happens even 12 hours apart (clopidogrel and omeprazole).

## My Cabinet and reminders

Save medicines from a scan (or add them by hand) to a running **Cabinet**, give each daily dose
times, and tick doses off in a **Today** checklist. **Check my whole cabinet** runs the interaction
check across everything saved, and scanning a new bottle can be checked against the cabinet too.

- **Private by design:** the cabinet is stored in this browser's localStorage
  (`components/cabinet_store`). It is never sent to a server, and another device or browser
  starts empty.
- **Reminders:** *Add daily reminders to my calendar* downloads an `.ics` file with a
  daily-repeating event and an alert at each dose time. It works in Apple, Google and Outlook
  calendars, so the phone alerts you even when the app is closed.
- **Optional in-app notifications:** a *Notify me at dose times* switch (off by default) asks the
  browser for permission and shows a notification at each dose time, skipping doses already
  ticked off. It only works while MedScan is open in a tab (true background push would need
  accounts and a server, which this demo deliberately avoids), and not in iOS Safari outside an
  installed web app. The calendar reminders cover those cases.

## Run it

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
.venv/bin/streamlit run streamlit_app.py
.venv/bin/python -m pytest -q          # offline, uses the committed cache
```

Reading photos works with no setup through the on-device OCR. For better results on curved or
glossy labels, use one of:

- `export GEMINI_API_KEY=...` (free, no card: <https://aistudio.google.com/apikey>), or
- `ollama pull qwen2.5vl:7b` and leave Ollama running.

The demo bottles and **Type my list** still work end to end.
On Streamlit Community Cloud, put `GEMINI_API_KEY` in the app's Secrets.

`scripts/build_cache.py` pre-fetches about 130 common drugs into `data/cache/` so they
answer instantly and offline. Any other drug is fetched live on first use.

## Limits (please read)

- **Severity is a reading of label wording, not a clinical model.** Labels are written for
  clinicians, and a sentence match can miss an interaction or over-read a generic sentence.
  Anything unusual should go to a pharmacist, which is what the app tells users.
- Only interactions the FDA label text mentions are found. Herbal products, foods, doses,
  and a patient's conditions are not considered.
- Drugs with no label interaction text, drugs the name lookup can't resolve, and unreadable
  bottles are listed under **Not checked**; they are never silently dropped.
- Photos are sent to Google when the Gemini backend is used. Use prop labels.

## Built at the hackathon

Everything in this repository was written on the day of the event, starting from an empty
directory. The only inputs are public data: RxNav (NLM) and openFDA drug labels, fetched
that day and cached under `data/cache/`.
