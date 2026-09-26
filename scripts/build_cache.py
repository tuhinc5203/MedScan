"""Pre-fetch RxNorm + openFDA data for common medicines into data/cache/.

    .venv/bin/python scripts/build_cache.py

Run once (needs network). Afterwards the app answers these drugs with no API calls,
and MEDLENS_OFFLINE=1 works for them. Any other drug is fetched live on first use.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from medlens import labels, rx  # noqa: E402
from medlens.store import SourceUnavailable  # noqa: E402

COMMON = """
simvastatin atorvastatin rosuvastatin pravastatin lovastatin clarithromycin erythromycin azithromycin
warfarin apixaban rivaroxaban clopidogrel aspirin omeprazole esomeprazole pantoprazole
lansoprazole metoprolol atenolol carvedilol propranolol lisinopril enalapril losartan valsartan
amlodipine diltiazem verapamil hydrochlorothiazide furosemide spironolactone digoxin amiodarone
metformin glipizide glimepiride insulin sitagliptin levothyroxine sertraline fluoxetine citalopram
escitalopram paroxetine venlafaxine duloxetine bupropion trazodone amitriptyline tramadol
oxycodone hydrocodone morphine codeine gabapentin pregabalin alprazolam lorazepam diazepam
clonazepam zolpidem ibuprofen naproxen meloxicam diclofenac celecoxib acetaminophen prednisone
methylprednisolone allopurinol colchicine finasteride tamsulosin sildenafil tadalafil fluconazole
ketoconazole ciprofloxacin levofloxacin amoxicillin doxycycline sulfamethoxazole metronidazole
carbamazepine phenytoin lamotrigine levetiracetam topiramate lithium quetiapine risperidone
olanzapine aripiprazole methotrexate tacrolimus cyclosporine rifampin ondansetron
cetirizine loratadine montelukast albuterol
""".split()
EXTRA = ["calcium carbonate", "magnesium hydroxide", "ferrous sulfate", "potassium chloride",
         "cholecalciferol", "sucralfate"]

if __name__ == "__main__":
    names = COMMON + EXTRA
    for i, n in enumerate(names, 1):
        try:
            r = rx.resolve(n)
            for ing in r["ingredients"]:
                rx.classes(ing["rxcui"])
                labels.fetch(ing["name"])
            got = ", ".join(x["name"] for x in r["ingredients"]) or "NO MATCH"
            print(f"[{i:3}/{len(names)}] {n:22} -> {got}")
        except SourceUnavailable as e:
            print(f"[{i:3}/{len(names)}] {n:22} !! {e}")
        time.sleep(0.35)  # stay well under openFDA's 240 requests/minute
