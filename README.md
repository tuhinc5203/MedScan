# MedLens

Take one photo of your pill bottles. MedLens reads the labels, lets you confirm the
list, and flags combinations that shouldn't be taken together. Every flag quotes the
FDA drug label it came from.

> Hackathon demo. Not medical advice. Use prop labels, not real prescription labels.

## How it works

1. **Read** (`medlens/vision.py`): a free vision model (Gemini free tier, or Ollama
   locally) transcribes each bottle label. Unreadable fields come back `null`, never guessed.
2. **Confirm**: you fix or remove anything wrong before any advice is produced.
   Low-confidence readings are flagged.
3. **Resolve** (`medlens/rx.py`): [RxNav](https://rxnav.nlm.nih.gov) turns label text
   ("Metoprolol Succ ER 25mg", "Mobic") into active ingredients and drug classes. A match
   must resemble a word actually printed on the label, otherwise it is "not recognised".
4. **Check** (`medlens/check.py`): for every pair, look for the other drug (by name, brand
   or class, e.g. "NSAIDs", "SSRIs") in each drug's
   [openFDA](https://open.fda.gov/apis/drug/label/) label interaction text. The matching
   sentence is kept as evidence and the severity is read from its wording ("contraindicated"
   / "avoid" → high, "monitor" / "may increase" → moderate). Negations ("no dose adjustment
   needed") are ignored. Two products with the same active ingredient are flagged as possible
   double dosing.
5. **Explain** (`medlens/advice.py`): fixed, plain wording. It never tells anyone to stop a
   medicine. A "spacing doses apart" note appears only when the label itself says so
   (for example levothyroxine and calcium), and says spacing *won't* help when the label
   says the effect happens even 12 hours apart (clopidogrel and omeprazole).

## Run it

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
.venv/bin/streamlit run streamlit_app.py
.venv/bin/python -m pytest -q          # offline, uses the committed cache
```

Reading photos needs a free vision model. Either:

- `export GEMINI_API_KEY=...` (free, no card: <https://aistudio.google.com/apikey>), or
- `ollama pull qwen2.5vl:7b` and leave Ollama running.

Without either, **Try demo bottles** and **Type my list** still work end to end.
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
