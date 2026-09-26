"""MedScan: Streamlit app.   .venv/bin/streamlit run streamlit_app.py"""
import html
import itertools
import os
from datetime import date

import streamlit as st

from medscan import advice, cabinet, pipeline, vision
from medscan.store_browser import notify_switch, sync
from medscan.theme import CSS

st.set_page_config(page_title="MedScan", layout="centered")
try:  # Streamlit Cloud keeps the free vision key in Secrets
    if "GEMINI_API_KEY" in st.secrets:
        os.environ.setdefault("GEMINI_API_KEY", st.secrets["GEMINI_API_KEY"])
except Exception:
    pass

st.markdown(CSS, unsafe_allow_html=True)
esc = html.escape
ss = st.session_state
ss.setdefault("stage", "scan")
ss.setdefault("back", "scan")
ss.setdefault("meds", [])
ss.setdefault("mode", None)
ss.setdefault("error", None)
ss.setdefault("cabinet", cabinet.empty())
ss.setdefault("cab_loaded", False)
ss.setdefault("cab_ver", 0)
ss.setdefault("today", date.today())
ids = ss.setdefault("_ids", itertools.count(1))


# ── persistence: the cabinet lives in this browser's localStorage, never on a server ──
def cab_save():
    ss.cab_ver += 1
    ss.cab_write = {"v": ss.cab_ver, "data": ss.cabinet}


saved = sync(ss.get("cab_write"), cabinet.notify_config(ss.cabinet, ss.today), ss.today.isoformat())
if saved and not ss.cab_loaded:
    ss.cab_loaded = True
    try:
        ss.today = date.fromisoformat(saved.get("today", ""))  # the user's own calendar day
    except ValueError:
        pass
    if saved.get("data") and ss.get("cab_write") is None:  # don't clobber edits made meanwhile
        ss.cabinet = cabinet.normalize(saved["data"])
        st.rerun()


def save_to_cabinet(pairs):
    """pairs: [(label, ingredient names)]. Skips anything already saved."""
    added = sum(cabinet.add(ss.cabinet, label, names) == "added" for label, names in pairs)
    cab_save()
    st.toast(f"Added {added} to your cabinet." if added else "Already in your cabinet.")


def new_med(raw, conf=1.0):
    return dict(id=next(ids), raw=raw, conf=conf, editing=False)


def go(stage, back=None):
    ss.stage = stage
    if back:
        ss.back = back
    st.rerun()


def load(payload):
    ss.meds = [new_med(b["drug_name"], b["confidence"]) for b in payload["bottles"]]
    ss.error = None
    go("confirm", back="confirm")


@st.cache_data(show_spinner=False)
def plain(quote, a, b):
    return advice.simplify(quote, a, b)


@st.cache_data(show_spinner=False, ttl=3600)
def resolved(raw, conf):
    return pipeline.resolve(raw, conf)


def nav():
    n = len(ss.cabinet["meds"])
    in_cabinet = ss.stage == "cabinet" or (ss.stage == "results" and ss.back == "cabinet")
    st.markdown('<div class="wordmark"><i></i>MedScan</div>', unsafe_allow_html=True)
    a, b = st.columns(2)
    if a.button("Scan", icon=":material/photo_camera:", use_container_width=True,
                type="secondary" if in_cabinet else "primary", key="nav_scan"):
        go("scan")
    if b.button(f"Cabinet ({n})" if n else "Cabinet", icon=":material/medication:",
                use_container_width=True, type="primary" if in_cabinet else "secondary",
                key="nav_cab"):
        go("cabinet")


# ───────────────────────────── Scan ─────────────────────────────
def scan():
    nav()
    st.markdown('<div class="title">Check your medicines in one photo</div>'
                '<p class="lead">Photograph your pill bottles. MedScan lists them and flags '
                'combinations that shouldn\'t be taken together.</p>', unsafe_allow_html=True)
    st.markdown('<div class="card note sub">Hackathon demo, not medical advice. Please use '
                'prop labels, not real prescription labels.</div>', unsafe_allow_html=True)
    if ss.error:
        st.error(ss.error)

    c1, c2 = st.columns(2)
    if c1.button("Take or choose photo", icon=":material/photo_camera:", type="primary",
                 use_container_width=True):
        ss.mode = "upload"
    if c2.button("Use webcam", icon=":material/videocam:", use_container_width=True):
        ss.mode = "camera"
    photo = None
    if ss.mode == "camera":
        photo = st.camera_input("Turn labels to face the camera", label_visibility="collapsed")
        st.caption("If nothing appears, allow camera access in your browser's address bar, or "
                   "use Take or choose photo instead.")
    elif ss.mode == "upload":
        photo = st.file_uploader("Photo of your bottles", type=["jpg", "jpeg", "png"],
                                 label_visibility="collapsed")
        st.caption("On a phone this opens your camera, using the rear lens at full quality.")
    if photo is not None:
        with st.spinner("Reading your labels…"):
            try:
                payload = vision.read_bottles(photo.getvalue(), ss.get("backend", "auto"))
            except vision.VisionError as e:
                ss.error = f"Couldn't read that photo: {e}"
                st.rerun()
        if not payload["bottles"]:
            ss.error = ("We couldn't find any medicine names in that photo. Try a closer, "
                        "well-lit photo of the label, or type your list.")
            st.rerun()
        load(payload)

    st.markdown('<div class="eyebrow">For the best scan</div><ul class="tips">'
                '<li>Turn labels to face the camera</li><li>Use good light and avoid glare</li>'
                '<li>Include vitamins and store-bought medicines too</li></ul>',
                unsafe_allow_html=True)
    b1, b2 = st.columns(2)
    if b1.button("Try demo bottles", use_container_width=True):
        load(vision.DEMO)
    if b2.button("Type my list", use_container_width=True):
        ss.meds = []
        go("confirm", back="confirm")
    with st.expander("Photo reading options"):
        opts = ["auto", "gemini", "ollama", "ocr", "demo"]
        ss.backend = st.selectbox("Reader", opts, index=opts.index(ss.get("backend", "auto")))
        st.caption(f"Available now: {', '.join(vision.available()) or 'none'}. **ocr** needs no key "
                   "and reads the text on the server; **gemini** handles curved or glossy labels "
                   "better (free key: aistudio.google.com/apikey).")
    st.markdown('<div class="fine">For information only. Always check with your pharmacist or '
                'doctor before changing how you take a medicine.</div>', unsafe_allow_html=True)


# ─────────────────────────── Confirm list ───────────────────────────
def add_photo_block(meds):
    """Read one more photo and append its bottles to the list (nothing is replaced)."""
    ss.setdefault("more_n", 0)
    with st.expander("Missed one? Add another photo"):
        c1, c2 = st.columns(2)
        if c1.button("Take or choose photo", key="more_up", icon=":material/photo_camera:",
                     use_container_width=True):
            ss.more_mode = "upload"
        if c2.button("Use webcam", key="more_cam", icon=":material/videocam:",
                     use_container_width=True):
            ss.more_mode = "camera"
        key = f"more_{ss.more_n}"     # a new key empties the widget after each photo
        photo = None
        if ss.get("more_mode") == "camera":
            photo = st.camera_input("Photo of the extra bottle", key=key, label_visibility="collapsed")
        elif ss.get("more_mode") == "upload":
            photo = st.file_uploader("Photo of the extra bottle", type=["jpg", "jpeg", "png"],
                                     key=key, label_visibility="collapsed")
        if photo is None:
            return
        with st.spinner("Reading the new photo…"):
            try:
                payload = vision.read_bottles(photo.getvalue(), ss.get("backend", "auto"))
            except vision.VisionError as e:
                ss.flash = f"Couldn't read that photo: {e}"
                ss.more_n += 1
                st.rerun()
        new, dupes, unreadable = pipeline.merge_bottles([m["raw"] for m in meds], payload["bottles"])
        meds.extend(new_med(b["drug_name"], b["confidence"]) for b in new)
        parts = [f"Added {len(new)} from the new photo" if new else
                 "No new medicine names found in that photo"]
        if dupes:
            parts.append(f"{dupes} already on your list")
        if unreadable:
            parts.append(f"{unreadable} unreadable")
        ss.flash = ". ".join(parts) + "."
        ss.more_n += 1
        st.rerun()


def confirm():
    nav()
    if st.button("Back", icon=":material/arrow_back:", type="tertiary"):
        ss.meds = []
        go("scan")
    meds, n = ss.meds, len(ss.meds)
    if ss.get("flash"):
        st.toast(ss.pop("flash"))
    st.markdown(f'<div class="h2">We found {n} medicine{"s" if n != 1 else ""}</div>' if n
                else '<div class="h2">Add your medicines</div>', unsafe_allow_html=True)
    st.markdown('<p class="lead">Check the list is right before we look for interactions.</p>',
                unsafe_allow_html=True)
    for m in list(meds):
        r = resolved(m["raw"], m["conf"])
        name = m["raw"] or "Couldn't read this label"
        sub = f"Checked as {', '.join(r['names'])}" if r["names"] else ""
        if m["raw"] and cabinet.contains(ss.cabinet, m["raw"], r["names"]):
            sub = (sub + " · " if sub else "") + "Saved in your cabinet"
        if m["raw"] is None or r["status"] == "no_match":
            warn = "We couldn't read or recognise this one. Please fix it or remove it."
        elif r["status"] == "unavailable":
            warn = "Couldn't reach the drug-name service. Try again in a moment."
        elif r["unclear"]:
            warn = "Part of this label was hard to read. Is this right?"
        else:
            warn = ""
        cols = st.columns([6, 1, 1], vertical_alignment="center")
        cols[0].markdown(
            f'<div class="card{" flag" if warn else ""}"><div class="med-name">{esc(name)}</div>'
            f'<div class="sub">{esc(sub)}</div>'
            + (f'<div class="flag-text">{esc(warn)}</div>' if warn else "") + "</div>",
            unsafe_allow_html=True)
        if cols[1].button("", key=f"e{m['id']}", help="Edit", icon=":material/edit:"):
            m["editing"] = not m["editing"]
            st.rerun()
        if cols[2].button("", key=f"x{m['id']}", help="Remove", icon=":material/close:"):
            meds.remove(m)
            st.rerun()
        if m["editing"]:
            with st.form(f"f{m['id']}", border=False):
                v = st.text_input("Medicine name and strength", value=m["raw"] or "",
                                  placeholder="e.g. Simvastatin 40 mg")
                if st.form_submit_button("Save"):
                    m.update(raw=v.strip() or None, conf=1.0, editing=False)
                    st.rerun()
    add_photo_block(meds)
    with st.form("add", clear_on_submit=True, border=True):
        v = st.text_input("Or type a medicine we missed", placeholder="e.g. Warfarin 5 mg")
        if st.form_submit_button("Add") and v.strip():
            meds.append(new_med(v.strip()))
            st.rerun()

    named = [m for m in meds if m["raw"]]
    cab_meds = ss.cabinet["meds"]
    with_cab = False
    if cab_meds:
        with_cab = st.checkbox(f"Also include my cabinet in this check ({len(cab_meds)} saved)",
                               value=False, key="with_cab")
    pending = [(m["raw"], resolved(m["raw"], m["conf"])["names"]) for m in named
               if not cabinet.contains(ss.cabinet, m["raw"], resolved(m["raw"], m["conf"])["names"])]
    if named:
        st.button(f"Add {len(pending)} to my cabinet" if pending else "All saved in your cabinet",
                  icon=":material/add_circle:" if pending else ":material/check_circle:",
                  use_container_width=True, disabled=not pending, key="save_confirm",
                  on_click=save_to_cabinet, args=(pending,))
    if st.button("Looks right, check interactions", type="primary", use_container_width=True,
                 disabled=not named):
        labels = [m["raw"] for m in named]
        if with_cab:  # a saved medicine that is the same drug as a scanned one isn't added twice
            have = {frozenset(resolved(m["raw"], 1.0)["names"]) for m in named}
            labels += [c["label"] for c in cab_meds if frozenset(c["ingredients"]) not in have]
        with st.spinner("Checking FDA labels…"):
            ss.result = pipeline.analyze(labels)
        ss.scanned = [m["raw"] for m in named]  # what "Save to my cabinet" will offer to save
        ss.unreadable = len(meds) - len(named)
        go("results", back="confirm")


# ───────────────────────────── Results ─────────────────────────────
def summary_text(r):
    lines = ["MedScan summary (hackathon demo; information only, not medical advice)", "",
             "Medicines listed: " + ", ".join(i["label"] for i in r["items"]), ""]
    shown = [c for c in r["cards"] if not c["minor"]]
    for c in shown:
        lines.append(f"- {c['headline']} [{c['severity'].upper()}]: {c['body']}")
        lines += [f"    FDA label: {e['quote']}" for e in c["evidence"][:1]]
    if not shown:
        lines.append("No interactions found among the medicines we could check.")
    if r["not_checked"] or r["no_label"]:
        lines += ["", "NOT checked: " + ", ".join(r["not_checked"] + r["no_label"])]
    lines += ["", "Please review with your pharmacist or doctor. Do not stop any medicine "
                  "on your own."]
    return "\n".join(lines)


def save_scanned():
    scanned = set(ss.get("scanned", []))
    save_to_cabinet([(it["label"], it["names"]) for it in ss.result["items"]
                     if it["label"] in scanned])


def results():
    nav()
    r = ss.result
    if st.button("Back", icon=":material/arrow_back:", type="tertiary"):
        go(ss.back if ss.back in ("confirm", "cabinet") else "scan")
    shown = [c for c in r["cards"] if not c["minor"]]
    minor = [c for c in r["cards"] if c["minor"]]
    sev = shown[0]["severity"] if shown else "none"
    n_chk = len(r["checked"]) - len(r["no_label"])
    head = (f"{len(shown)} interaction{'s' if len(shown) != 1 else ''} found" if shown
            else "No interactions found")
    st.markdown(f'<div class="summary {sev}"><div class="big">{head}</div>'
                f'<div class="sub">in {n_chk} medicine{"s" if n_chk != 1 else ""} checked</div></div>',
                unsafe_allow_html=True)

    for c in shown:
        sp = c["spacing"]
        st.markdown(
            f'<div class="pair {c["severity"]}"><span class="tag {c["severity"]}">'
            f'{c["severity"].capitalize()} risk</span><h3>{esc(c["headline"])}</h3>'
            f'<p>{esc(c["body"])}</p>'
            + (f'<div class="inset {sp["kind"]}"><b>{esc(sp["title"])}</b><br>{esc(sp["text"])}</div>'
               if sp else "")
            + f'<div class="steps"><b>What to do.</b> {esc(c["action"])} {esc(c["never_stop"])}</div>'
              f'<div class="inset {"watch" if c["urgent"] else "general"}">{esc(c["escalation"])}</div></div>',
            unsafe_allow_html=True)
        with st.expander("Why is this flagged?"):
            top = c["evidence"][0]
            a, b = (c["headline"].split(" + ") + [""])[:2]
            simple = plain(top["quote"], a, b) if top["kind"] == "label" else None
            if simple:
                st.markdown(f"**In plain words** (AI restatement of the label): {simple}")
            for e in c["evidence"]:
                st.markdown(f'<div class="quote">“{esc(e["quote"])}”<br><span class="sub">'
                            f'Source: {esc(e["source"])}</span></div>', unsafe_allow_html=True)

    clear = [k for k in r["clear"] if k not in r["no_label"]]
    if clear:
        st.markdown('<div class="eyebrow">No interactions found</div>', unsafe_allow_html=True)
        for k in clear:
            st.markdown(f'<div class="ok"><b>{esc(k.title())}</b><br><span class="sub" '
                        'style="color:inherit">No interaction with your other medicines in the FDA '
                        'labels.</span></div>', unsafe_allow_html=True)
    if minor:
        with st.expander(f"{len(minor)} minor mention{'s' if len(minor) != 1 else ''} in labels"):
            for c in minor:
                st.markdown(f"**{c['headline']}**: {c['body']}")

    missed = r["not_checked"] + [f"{n.title()} (no FDA interaction text found)" for n in r["no_label"]] \
        + [f"{n.title()} (data source unreachable)" for n in r["unavailable"]]
    if missed or ss.get("unreadable"):
        st.markdown('<div class="eyebrow">Not checked</div>', unsafe_allow_html=True)
        st.markdown('<div class="na"><b>These were not checked for interactions.</b> Ask your '
                    'pharmacist about them.<br>' + "<br>".join("• " + esc(m) for m in missed)
                    + (f"<br>• {ss.unreadable} unreadable label(s)" if ss.get("unreadable") else "")
                    + "</div>", unsafe_allow_html=True)

    st.write("")
    if ss.back == "confirm" and any(i["ingredients"] for i in r["items"]):
        st.button("Save to my cabinet", icon=":material/add_circle:", type="primary",
                  use_container_width=True, on_click=save_scanned)
    st.download_button("Share with my pharmacist", summary_text(r), "medscan_summary.txt",
                       use_container_width=True, icon=":material/ios_share:")
    if st.button("Scan again", use_container_width=True):
        ss.meds = []
        go("scan")
    st.markdown('<div class="fine">For information only. Not a substitute for advice from your '
                'pharmacist or doctor. Findings are read from FDA drug labels and may be '
                'incomplete.</div>', unsafe_allow_html=True)


# ───────────────────────────── Cabinet ─────────────────────────────
def _toggle_taken(med, t, key):
    cabinet.set_taken(ss.cabinet, ss.today, med, t, bool(ss[key]))
    cab_save()


def _remove(med_id):
    cabinet.remove(ss.cabinet, med_id)
    cab_save()


def _save_times(med, key):
    good, bad = cabinet.parse_times(ss[key])
    if bad:
        st.toast("Couldn't read: " + ", ".join(bad) + ". Use times like 8am or 20:30.")
        return
    med["times"] = good
    cab_save()
    st.toast("Times saved.")


def _add_med():
    label = (ss.get("cab_name") or "").strip()
    if not label:
        return
    good, bad = cabinet.parse_times(ss.get("cab_times") or "")
    if bad:
        st.toast("Couldn't read: " + ", ".join(bad) + ". Use times like 8am or 20:30.")
        return
    r = pipeline.resolve(label)
    if r["status"] == "unavailable":
        st.toast("Couldn't reach the drug-name service. Try again in a moment.")
        return
    status = cabinet.add(ss.cabinet, label, r["names"], good)
    cab_save()
    st.toast("Added to your cabinet." if status == "added" else "That medicine is already saved.")
    ss.cab_name, ss.cab_times = "", ""


def cabinet_screen():
    nav()
    cab = ss.cabinet
    st.markdown('<div class="title">My cabinet</div><p class="lead">Your running list of '
                'medicines. It is saved in this browser only. Nothing is sent to a server.</p>',
                unsafe_allow_html=True)
    # Fixed position, above everything that grows or shrinks: a frame that moves gets re-mounted
    # by Streamlit and can miss its first render.
    notify_switch()
    if not cab["meds"]:
        st.markdown('<div class="card note">Nothing saved yet. Scan your bottles and choose '
                    '<b>Save to my cabinet</b>, or add a medicine below.</div>',
                    unsafe_allow_html=True)

    today = cabinet.due(cab)
    if today:
        done = sum(cabinet.is_taken(cab, ss.today, m, t) for m, t in today)
        st.markdown(f'<div class="eyebrow">Today · {done} of {len(today)} taken</div>',
                    unsafe_allow_html=True)
        for m, t in today:
            key = f"tk-{m['id']}-{t}-{ss.today}"
            st.checkbox(f"{cabinet.nice_time(t)}  ·  {m['label']}", key=key,
                        value=cabinet.is_taken(cab, ss.today, m, t),
                        on_change=_toggle_taken, args=(m, t, key))

    if cab["meds"]:
        st.markdown('<div class="eyebrow">Medicines</div>', unsafe_allow_html=True)
    for m in cab["meds"]:
        chips = "".join(f'<span class="chip">{cabinet.nice_time(t)}</span>' for t in m["times"]) \
            or '<span class="chip off">No reminder times</span>'
        sub = f"Checked as {', '.join(m['ingredients'])}" if m["ingredients"] else "Not in our checked list"
        st.markdown(f'<div class="card"><div class="med-name">{esc(m["label"])}</div>'
                    f'<div class="sub">{esc(sub)}</div>{chips}</div>', unsafe_allow_html=True)
        with st.expander("Edit times or remove"):
            k = f"times-{m['id']}"
            st.text_input("Daily dose times", key=k, placeholder="e.g. 8am, 8:30pm",
                          value=", ".join(cabinet.nice_time(t).replace(" ", "").lower()
                                          for t in m["times"]))
            c1, c2 = st.columns(2)
            c1.button("Save times", key=f"st-{m['id']}", use_container_width=True,
                      on_click=_save_times, args=(m, k))
            c2.button("Remove", key=f"rm-{m['id']}", use_container_width=True,
                      on_click=_remove, args=(m["id"],))

    st.markdown('<div class="eyebrow">Add a medicine</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.text_input("Medicine name and strength", key="cab_name",
                      placeholder="e.g. Levothyroxine 50 mcg")
        st.text_input("Daily dose times (optional)", key="cab_times", placeholder="e.g. 7am, 8pm")
        st.button("Add to cabinet", icon=":material/add:", use_container_width=True,
                  on_click=_add_med)

    if cab["meds"]:
        st.markdown('<div class="eyebrow">Tools</div>', unsafe_allow_html=True)
        if st.button("Check my whole cabinet for interactions", type="primary",
                     use_container_width=True, disabled=len(cab["meds"]) < 2):
            with st.spinner("Checking FDA labels…"):
                ss.result = pipeline.analyze([m["label"] for m in cab["meds"]])
            ss.unreadable = 0
            go("results", back="cabinet")
        has_times = any(m["times"] for m in cab["meds"])
        st.download_button("Add daily reminders to my calendar", cabinet.to_ics(cab, ss.today),
                           "medscan_reminders.ics", "text/calendar", use_container_width=True,
                           icon=":material/notifications:", disabled=not has_times)
        st.markdown('<div class="fine">The reminder file repeats every day and works in Apple, '
                    'Google and Outlook calendars, so your phone alerts you even when MedScan is '
                    'closed. Open the file, or tap it after downloading, to add it.</div>',
                    unsafe_allow_html=True)

    st.markdown('<div class="fine">MedScan is a hackathon demo. Reminders help you remember; they '
                'are not a substitute for your prescriber\'s directions.</div>',
                unsafe_allow_html=True)


{"scan": scan, "confirm": confirm, "results": results, "cabinet": cabinet_screen}[ss.stage]()
