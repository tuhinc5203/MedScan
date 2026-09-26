"""Visual design: a quiet, airy palette (white, pale blue, pale green) with soft warnings."""

CSS = """
<style>
:root {
  --bg:#f6fafc; --surface:#ffffff; --line:#e2ecf2; --ink:#1e2f3d; --muted:#5b7080;
  --blue:#e8f2fa; --blue-ink:#2c6a91; --blue-btn:#2f7396;
  --green:#e8f5ee; --green-ink:#2a7350; --green-line:#c9e6d6;
  --red:#fdeeee; --red-ink:#a1443f; --red-line:#f0c9c6;
  --amber:#fff7e2; --amber-ink:#856416; --amber-line:#f0dfae;
}
html, body, [class*="css"], .stApp {
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif;
  color:var(--ink);
}
.stApp {background:var(--bg);}
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] {visibility:hidden; height:0;}
.block-container {max-width:440px; padding:.8rem 1.1rem 3rem;}
/* Streamlit stacks columns below 640px; keep button pairs and edit/remove rows side by side */
[data-testid="stHorizontalBlock"] {flex-wrap:nowrap !important; gap:.6rem !important;}
[data-testid="stColumn"] {min-width:0 !important;}
h1,h2,h3 {font-family:inherit !important; color:var(--ink); letter-spacing:-.01em;}

/* type */
.wordmark {font-weight:650; font-size:1.05rem; letter-spacing:-.01em; color:var(--ink);}
.wordmark i {display:inline-block; width:9px; height:9px; border-radius:50%; background:#7fb8d9;
             margin-right:8px; vertical-align:1px;}
.title {font-size:1.75rem; line-height:1.2; font-weight:650; margin:1.1rem 0 .4rem;}
.lead {color:var(--muted); font-size:1rem; line-height:1.5; margin:0 0 1rem;}
.h2 {font-size:1.25rem; font-weight:650; margin:.6rem 0 .2rem;}
.eyebrow {font-size:.72rem; font-weight:650; letter-spacing:.08em; text-transform:uppercase;
          color:var(--muted); margin:1.5rem 0 .4rem;}
.fine {font-size:.8rem; color:var(--muted); text-align:center; margin-top:1.2rem; line-height:1.5;}
.sub {color:var(--muted); font-size:.88rem;}

/* surfaces */
.card {background:var(--surface); border:1px solid var(--line); border-radius:14px;
       padding:14px 16px; margin:8px 0;}
.card.note {background:var(--blue); border-color:#d3e6f3;}
.card.flag {background:var(--amber); border-color:var(--amber-line);}
.med-name {font-weight:600; font-size:1rem;}
.flag-text {color:var(--amber-ink); font-size:.86rem; margin-top:5px;}
.tips {margin:0; padding:0; list-style:none; color:var(--muted); font-size:.92rem; line-height:1.9;}
.tips li::before {content:""; display:inline-block; width:6px; height:6px; border-radius:50%;
                  background:#9ccfb4; margin-right:10px; vertical-align:2px;}

/* result summary */
.summary {border-radius:14px; padding:16px 18px; margin:6px 0 14px; border:1px solid;}
.summary .big {font-size:1.2rem; font-weight:650;}
.summary .sub {color:inherit; opacity:.85;}
.summary.high {background:var(--red); border-color:var(--red-line); color:var(--red-ink);}
.summary.moderate {background:var(--amber); border-color:var(--amber-line); color:var(--amber-ink);}
.summary.low {background:var(--blue); border-color:#d3e6f3; color:var(--blue-ink);}
.summary.none {background:var(--green); border-color:var(--green-line); color:var(--green-ink);}

/* an interaction */
.pair {background:var(--surface); border:1px solid var(--line); border-left-width:4px;
       border-radius:14px; padding:14px 16px 12px; margin:10px 0;}
.pair.high {border-left-color:#e29a94;} .pair.moderate {border-left-color:#e6c46e;}
.pair.low {border-left-color:#9ec4dd;}
.pair h3 {margin:.35rem 0 .45rem; font-size:1.12rem; font-weight:650;}
.pair p {margin:.2rem 0; font-size:.95rem; line-height:1.5;}
.tag {display:inline-block; font-size:.72rem; font-weight:650; padding:2px 9px; border-radius:99px;}
.tag.high {background:var(--red); color:var(--red-ink);}
.tag.moderate {background:var(--amber); color:var(--amber-ink);}
.tag.low {background:var(--blue); color:var(--blue-ink);}
.inset {border-radius:10px; padding:9px 12px; margin-top:10px; font-size:.9rem; line-height:1.45;}
.inset.helps {background:var(--green); color:#25573f;}
.inset.no_help {background:#f1f4f6; color:#3f5160;}
.inset.watch {background:var(--red); color:#7c3733;}
.inset.general {background:#f1f5f8; color:#40556a;}
.inset b {font-weight:650;}
.steps {font-size:.9rem; line-height:1.5; color:#33475a; margin-top:10px;}
.quote {font-size:.85rem; color:#3d5163; border-left:3px solid #d5e3ec; padding-left:10px; margin:8px 0;}

.ok {background:var(--green); border:1px solid var(--green-line); border-radius:12px;
     padding:10px 14px; margin:6px 0; color:var(--green-ink);}
.ok b {color:#1f5a3d;}
.na {background:#f1f5f8; border:1px solid var(--line); border-radius:12px; padding:11px 14px;
     margin:6px 0; font-size:.9rem; color:#40556a;}

/* cabinet */
.dose {display:flex; justify-content:space-between; gap:10px; align-items:baseline;}
.chip {display:inline-block; background:var(--blue); color:var(--blue-ink); border-radius:99px;
       padding:2px 10px; font-size:.78rem; margin:6px 6px 0 0;}
.chip.off {background:#eef2f5; color:#7a8b99;}
.due {background:var(--surface); border:1px solid var(--line); border-radius:12px;
      padding:10px 14px; margin:6px 0;}
.due.done {background:var(--green); border-color:var(--green-line); color:var(--green-ink);}

/* controls */
.stButton > button, .stDownloadButton > button {
  border-radius:12px; font-weight:600; min-height:2.8rem; border:1px solid var(--line);
  background:var(--surface); color:var(--ink); box-shadow:none;}
.stButton > button:hover, .stDownloadButton > button:hover {border-color:#b9d3e4; color:var(--blue-ink);
  background:#fbfdfe;}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
  background:var(--blue-btn); color:#fff; border-color:var(--blue-btn);}
.stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover {
  background:#27637f; color:#fff; border-color:#27637f;}
.stButton > button[kind="tertiary"] {border:0; background:transparent; color:var(--blue-ink);
  min-height:auto; padding:.2rem 0; font-weight:550;}
.stButton > button:disabled {opacity:.5;}
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea {
  border-radius:10px; border:1px solid var(--line); background:#fff;}
[data-testid="stExpander"] {border:1px solid var(--line); border-radius:12px; background:var(--surface);}
[data-testid="stExpander"] summary {font-size:.9rem; color:var(--blue-ink); font-weight:550;}
[data-testid="stFileUploaderDropzone"] {background:#fff; border:1px dashed #bcd5e5; border-radius:12px;}
[data-testid="stAlert"] {border-radius:12px; border:1px solid var(--line);}
[data-testid="stCheckbox"] label p {font-size:.95rem;}
</style>
"""
