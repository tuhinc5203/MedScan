"""MedScan: Streamlit app.   .venv/bin/streamlit run streamlit_app.py"""
import html
import itertools
import os

import streamlit as st

from medscan import advice, pipeline, vision

st.set_page_config(page_title="MedScan", page_icon="🔍", layout="centered")
try:  # Streamlit Cloud keeps the free vision key in Secrets
    if "GEMINI_API_KEY" in st.secrets:
        os.environ.setdefault("GEMINI_API_KEY", st.secrets["GEMINI_API_KEY"])
except Exception:
    pass

st.markdown("""
<style>
#MainMenu, footer, header [data-testid="stToolbar"] {visibility:hidden;}
.block-container {max-width:430px; padding-top:1.2rem; padding-bottom:2rem;}
h2,h3,.serif {font-family: Georgia, 'Times New Roman', serif !important; color:#1c2b2d;}
.brand {font-family: Georgia, serif; font-weight:700; font-size:1.35rem; color:#1c2b2d; margin-bottom:.6rem;}
.hero {font-family: Georgia, serif; font-weight:700; font-size:2.2rem; line-height:1.1; margin:.4rem 0 .6rem;}
.muted {color:#4a5a5c;}
.small {font-size:.8rem; color:#6b7a7c; text-align:center; margin-top:.8rem;}
.card {background:#fff; border:1px solid #e6e2d8; border-radius:14px; padding:14px 16px; margin:8px 0;}
.card.warn {background:#fff8e6; border:2px solid #e6c56a;}
.med-name {font-weight:700; font-size:1.02rem; color:#1c2b2d;}
.med-sub {color:#5a6a6c; font-size:.88rem;}
.med-warn {color:#7a5218; font-size:.88rem; margin-top:6px;}
.banner {border-radius:14px; padding:16px 18px; color:#fff; margin:6px 0 12px;}
.banner .big {font-size:1.25rem; font-weight:700;}
.banner.high {background:#8a2a2a;} .banner.moderate {background:#7a5218;}
.banner.low {background:#4a5a5c;} .banner.none {background:#2b5c63;}
.badge {display:inline-block; font-size:.72rem; font-weight:700; letter-spacing:.04em;
        padding:3px 10px; border-radius:99px; margin-bottom:6px;}
.badge.high {background:#fbe4e2; color:#8a2a2a;} .badge.moderate {background:#fbeed5; color:#7a5218;}
.badge.low {background:#e8ecec; color:#4a5a5c;}
.card h3 {margin:.1rem 0 .5rem; font-size:1.25rem;}
.spacing {border-radius:10px; padding:10px 12px; margin-top:10px; font-size:.92rem;}
.spacing.helps {background:#e6f0f0;} .spacing.no_help {background:#f0eee8;}
.action {background:#eef3f3; border-radius:10px; padding:10px 12px; margin-top:10px; font-size:.92rem;}
.esc {background:#f3efe6; border-radius:10px; padding:10px 12px; margin-top:8px; font-size:.92rem;}
.section {font-size:.75rem; font-weight:700; letter-spacing:.08em; color:#5a6a6c; margin:16px 0 4px;}
.ok {background:#e9f3ee; border:1px solid #bfdccd; border-radius:12px; padding:10px 14px; margin:6px 0;}
.na {background:#f0eee8; border-radius:12px; padding:10px 14px; margin:6px 0; font-size:.9rem;}
.quote {font-size:.85rem; color:#3a4a4c; border-left:3px solid #c9c4b6; padding-left:10px; margin:6px 0;}
.stButton > button {border-radius:12px; font-weight:600; min-height:2.9rem;}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"]
  {background:#2b5c63; color:#fff; border:0;}
</style>
""", unsafe_allow_html=True)
esc = html.escape
ss = st.session_state
ss.setdefault("stage", "scan")
ss.setdefault("meds", [])
ss.setdefault("mode", None)
ss.setdefault("error", None)
ids = ss.setdefault("_ids", itertools.count(1))


def new_med(raw, conf=1.0):
    return dict(id=next(ids), raw=raw, conf=conf, editing=False)


def go(stage):
    ss.stage = stage
    st.rerun()


def load(payload):
    ss.meds = [new_med(b["drug_name"], b["confidence"]) for b in payload["bottles"]]
    ss.error = None
    go("confirm")


@st.cache_data(show_spinner=False)
def plain(quote, a, b):
    return advice.simplify(quote, a, b)


@st.cache_data(show_spinner=False, ttl=3600)
def resolved(raw, conf):
    return pipeline.resolve(raw, conf)


# ───────────────────────────── 1 · Scan ─────────────────────────────
def scan():
    st.markdown('<div class="brand">🔍 MedScan</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero">Check your medicines in one photo</div>', unsafe_allow_html=True)
    st.markdown('<p class="muted">Take a picture of your pill bottles. We\'ll list them and '
                'flag any that shouldn\'t be taken together.</p>', unsafe_allow_html=True)
    st.info("Hackathon demo. Not medical advice. Please use prop labels, not real "
            "prescription labels.")
    if ss.error:
        st.error(ss.error)
    st.caption("On a phone, choose **Take / choose photo** for the best result. It uses your "
               "rear camera at full quality. On a laptop, use **Webcam**.")
    c1, c2 = st.columns(2)
    if c1.button("📷 Take / choose photo", type="primary", use_container_width=True):
        ss.mode = "upload"
    if c2.button("💻 Webcam", use_container_width=True):
        ss.mode = "camera"

    photo = None
    if ss.mode == "camera":
        photo = st.camera_input("Turn labels to face the camera", label_visibility="collapsed")
        st.caption("If nothing appears, allow camera access in your browser's address bar, "
                   "or use Take / choose photo instead.")
    elif ss.mode == "upload":
        photo = st.file_uploader("Photo of your bottles", type=["jpg", "jpeg", "png"],
                                 label_visibility="collapsed")
    if photo is not None:
        with st.spinner("Reading your labels…"):
            try:
                payload = vision.read_bottles(photo.getvalue(), ss.get("backend", "auto"))
            except vision.VisionError as e:
                ss.error = f"Couldn't read that photo: {e}"
                st.rerun()
        load(payload)

    st.markdown('<div class="card"><b>For the best scan</b><br>✓ Turn labels to face the camera'
                '<br>✓ Use good light, avoid glare<br>✓ Include vitamins and store-bought '
                'medicines too</div>', unsafe_allow_html=True)
    b1, b2 = st.columns(2)
    if b1.button("Try demo bottles", use_container_width=True):
        load(vision.DEMO)
    if b2.button("Type my list", use_container_width=True):
        ss.meds = []
        go("confirm")
    with st.expander("Vision settings"):
        opts = ["auto", "gemini", "ollama", "demo"]
        ss.backend = st.selectbox("Backend", opts, index=opts.index(ss.get("backend", "auto")))
        st.caption(f"Available now: {', '.join(vision.available()) or 'none'}. Free key: "
                   "aistudio.google.com/apikey → GEMINI_API_KEY.")
    st.markdown('<div class="small">For information only. Always check with your pharmacist '
                'or doctor before changing how you take a medicine.</div>', unsafe_allow_html=True)


# ─────────────────────────── 2 · Confirm list ───────────────────────────
def confirm():
    if st.button("‹ Retake photo", type="tertiary"):
        ss.meds = []
        go("scan")
    meds, n = ss.meds, len(ss.meds)
    st.markdown(f'<h2 class="serif">We found {n} medicine{"s" if n != 1 else ""}</h2>' if n
                else '<h2 class="serif">Add your medicines</h2>', unsafe_allow_html=True)
    st.markdown('<p class="muted">Check this list is right before we look for interactions.</p>',
                unsafe_allow_html=True)
    for m in list(meds):
        r = resolved(m["raw"], m["conf"])
        name = m["raw"] or "Couldn't read this label"
        sub = f"Checked as {', '.join(r['names'])}" if r["names"] else ""
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
            f'<div class="card{" warn" if warn else ""}"><div class="med-name">{esc(name)}'
            f'{"?" if warn else ""}</div><div class="med-sub">{esc(sub)}</div>'
            + (f'<div class="med-warn">⚠ {esc(warn)}</div>' if warn else "") + "</div>",
            unsafe_allow_html=True)
        if cols[1].button("✎", key=f"e{m['id']}", help="Edit"):
            m["editing"] = not m["editing"]
            st.rerun()
        if cols[2].button("✕", key=f"x{m['id']}", help="Remove"):
            meds.remove(m)
            st.rerun()
        if m["editing"]:
            with st.form(f"f{m['id']}", border=False):
                v = st.text_input("Medicine name and strength", value=m["raw"] or "",
                                  placeholder="e.g. Simvastatin 40 mg")
                if st.form_submit_button("Save"):
                    m.update(raw=v.strip() or None, conf=1.0, editing=False)
                    st.rerun()
    with st.form("add", clear_on_submit=True, border=True):
        v = st.text_input("Add a medicine we missed", placeholder="e.g. Warfarin 5 mg")
        if st.form_submit_button("＋ Add") and v.strip():
            meds.append(new_med(v.strip()))
            st.rerun()
    named = [m for m in meds if m["raw"]]
    if st.button("Looks right, check interactions", type="primary", use_container_width=True,
                 disabled=not named):
        with st.spinner("Checking FDA labels…"):
            ss.result = pipeline.analyze([m["raw"] for m in named])
        ss.unreadable = len(meds) - len(named)
        go("results")


# ───────────────────────────── 3 · Results ─────────────────────────────
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


def results():
    r = ss.result
    if st.button("‹ Edit list", type="tertiary"):
        go("confirm")
    shown = [c for c in r["cards"] if not c["minor"]]
    minor = [c for c in r["cards"] if c["minor"]]
    sev = shown[0]["severity"] if shown else "none"
    n_chk = len(r["checked"]) - len(r["no_label"])
    head = (f"{len(shown)} interaction{'s' if len(shown) != 1 else ''} found" if shown
            else "No interactions found")
    icon = {"high": "⚠", "moderate": "ⓘ", "low": "ⓘ", "none": "✓"}[sev]
    st.markdown(f'<div class="banner {sev}"><div class="big">{icon} {head}</div>in {n_chk} '
                f'medicine{"s" if n_chk != 1 else ""} checked</div>', unsafe_allow_html=True)

    for c in shown:
        sp = c["spacing"]
        st.markdown(
            f'<div class="card"><span class="badge {c["severity"]}">{c["severity"].upper()} '
            f'RISK</span><h3>{esc(c["headline"])}</h3><p>{esc(c["body"])}</p>'
            + (f'<div class="spacing {sp["kind"]}"><b>{esc(sp["title"])}</b><br>{esc(sp["text"])}</div>'
               if sp else "")
            + f'<div class="action"><b>What to do</b><br>{esc(c["action"])}<br>'
              f'{esc(c["never_stop"])}</div><div class="esc">{esc(c["escalation"])}</div></div>',
            unsafe_allow_html=True)
        with st.expander("Why is this flagged?"):
            top = c["evidence"][0]
            a, b = (c["headline"].split(" + ") + [""])[:2]
            simple = plain(top["quote"], a, b) if top["kind"] == "label" else None
            if simple:
                st.markdown(f"**In plain words** (AI restatement of the label): {simple}")
            for e in c["evidence"]:
                st.markdown(f'<div class="quote">“{esc(e["quote"])}”<br><span class="med-sub">'
                            f'Source: {esc(e["source"])}</span></div>', unsafe_allow_html=True)

    if r["clear"]:
        st.markdown('<div class="section">NO INTERACTIONS FOUND</div>', unsafe_allow_html=True)
        for k in r["clear"]:
            if k not in r["no_label"]:
                st.markdown(f'<div class="ok">✓ <b>{esc(k.title())}</b><br><span class="med-sub">'
                            'No interaction with your other medicines in the FDA labels.'
                            '</span></div>', unsafe_allow_html=True)
    if minor:
        with st.expander(f"{len(minor)} minor mention{'s' if len(minor) != 1 else ''} in labels"):
            for c in minor:
                st.markdown(f"**{c['headline']}**: {c['body']}")

    missed = r["not_checked"] + [f"{n.title()} (no FDA interaction text found)" for n in r["no_label"]] \
        + [f"{n.title()} (data source unreachable)" for n in r["unavailable"]]
    if missed or ss.get("unreadable"):
        st.markdown('<div class="section">NOT CHECKED</div>', unsafe_allow_html=True)
        st.markdown('<div class="na"><b>These were not checked for interactions.</b> Ask your '
                    'pharmacist about them.<br>' + "<br>".join("• " + esc(m) for m in missed)
                    + (f"<br>• {ss.unreadable} unreadable label(s)" if ss.get("unreadable") else "")
                    + "</div>", unsafe_allow_html=True)

    st.download_button("Share with my pharmacist", summary_text(r), "medscan_summary.txt",
                       type="primary", use_container_width=True)
    if st.button("Scan again", use_container_width=True):
        ss.meds = []
        go("scan")
    st.markdown('<div class="small">For information only. Not a substitute for advice from your '
                'pharmacist or doctor. Findings are read from FDA drug labels and may be '
                'incomplete.</div>', unsafe_allow_html=True)


{"scan": scan, "confirm": confirm, "results": results}[ss.stage]()
