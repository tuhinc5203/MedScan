"""The user's medicine cabinet: a saved list with daily dose times, plus calendar reminders.

Pure functions over plain dicts so they are easy to test. Persistence is the browser's
localStorage (see components/cabinet_store); nothing here touches a server or a disk.

    cabinet = {"meds":  [{"id", "label", "ingredients": [...], "times": ["08:00", ...]}],
               "taken": {"2026-09-26": ["<id>@08:00", ...]}}
"""
import re
import uuid
from datetime import date, datetime, timezone


def empty() -> dict:
    return {"meds": [], "taken": {}}


def normalize(data) -> dict:
    """Whatever came back from the browser -> a well-formed cabinet (never raises)."""
    out = empty()
    if not isinstance(data, dict):
        return out
    for m in data.get("meds") if isinstance(data.get("meds"), list) else []:
        if isinstance(m, dict) and isinstance(m.get("label"), str) and m["label"].strip():
            times = m.get("times") if isinstance(m.get("times"), list) else []
            out["meds"].append(dict(
                id=str(m.get("id") or uuid.uuid4().hex[:8]),
                label=m["label"].strip(),
                ingredients=[str(i) for i in m.get("ingredients", []) if isinstance(i, str)]
                if isinstance(m.get("ingredients"), list) else [],
                times=parse_times(",".join(str(t) for t in times))[0]))
    if isinstance(data.get("taken"), dict):
        out["taken"] = {str(k): [str(x) for x in v] for k, v in data["taken"].items()
                        if isinstance(v, list)}
    return out


def parse_times(text: str) -> tuple[list[str], list[str]]:
    """'8am, 8:30 pm, 20:00' -> (['08:00', '20:00', '20:30'], []). Second item lists what
    could not be understood, so the UI can say so instead of silently dropping it."""
    good, bad = set(), []
    for tok in [t.strip() for t in re.split(r"[,;\n]+", text or "") if t.strip()]:
        m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?", tok.lower())
        if not m:
            bad.append(tok)
            continue
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "")[:1]
        if ap:
            if not 1 <= h <= 12:
                bad.append(tok)
                continue
            h = h % 12 + (12 if ap == "p" else 0)
        if h > 23 or mi > 59:
            bad.append(tok)
            continue
        good.add(f"{h:02d}:{mi:02d}")
    return sorted(good), bad


def nice_time(hhmm: str) -> str:
    h, m = int(hhmm[:2]), hhmm[3:]
    return f"{(h % 12) or 12}:{m} {'AM' if h < 12 else 'PM'}"


def add(cab: dict, label: str, ingredients: list[str], times: list[str] | None = None) -> str:
    """Returns 'added' or 'exists'. The same active ingredient is never saved twice."""
    key = frozenset(ingredients) or frozenset([label.strip().lower()])
    for m in cab["meds"]:
        if (frozenset(m["ingredients"]) or frozenset([m["label"].lower()])) == key:
            return "exists"
    cab["meds"].append(dict(id=uuid.uuid4().hex[:8], label=label.strip(),
                            ingredients=list(ingredients), times=sorted(times or [])))
    return "added"


def remove(cab: dict, med_id: str) -> None:
    cab["meds"] = [m for m in cab["meds"] if m["id"] != med_id]
    for day, keys in cab["taken"].items():
        cab["taken"][day] = [k for k in keys if not k.startswith(med_id + "@")]


def due(cab: dict) -> list[tuple[dict, str]]:
    """Every (medicine, time) pair for today, in clock order."""
    return sorted(((m, t) for m in cab["meds"] for t in m["times"]),
                  key=lambda x: (x[1], x[0]["label"]))


def taken_key(med: dict, t: str) -> str:
    return f"{med['id']}@{t}"


def set_taken(cab: dict, today: date, med: dict, t: str, value: bool) -> None:
    day = today.isoformat()
    keys = set(cab["taken"].get(day, []))
    (keys.add if value else keys.discard)(taken_key(med, t))
    cab["taken"] = {day: sorted(keys)}  # only today is kept; old days are dropped


def is_taken(cab: dict, today: date, med: dict, t: str) -> bool:
    return taken_key(med, t) in cab["taken"].get(today.isoformat(), [])


# --- calendar reminders --------------------------------------------------------
def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545: lines longer than 75 octets are folded with CRLF + space."""
    raw, out = line.encode(), []
    while len(raw) > 75:
        cut = 75
        while cut and (raw[cut] & 0xC0) == 0x80:  # don't split a multibyte character
            cut -= 1
        out.append(raw[:cut].decode())
        raw = b" " + raw[cut:]
    out.append(raw.decode())
    return "\r\n".join(out)


def to_ics(cab: dict, start: date | None = None, now: datetime | None = None) -> str:
    """A calendar file with one daily-repeating event (and an alert at the time) per
    medicine per dose time. Times are 'floating': they follow the phone's own timezone."""
    start = start or date.today()
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//MedScan//Reminders//EN",
             "CALSCALE:GREGORIAN", "X-WR-CALNAME:MedScan reminders"]
    for med, t in due(cab):
        lines += ["BEGIN:VEVENT", f"UID:{med['id']}-{t.replace(':', '')}@medscan",
                  f"DTSTAMP:{stamp}", f"DTSTART:{start:%Y%m%d}T{t.replace(':', '')}00",
                  "DURATION:PT15M", "RRULE:FREQ=DAILY",
                  f"SUMMARY:{_esc('Take ' + med['label'])}",
                  "DESCRIPTION:" + _esc("Reminder from MedScan. Follow the directions on your "
                                        "label and from your prescriber."),
                  "BEGIN:VALARM", "ACTION:DISPLAY", "TRIGGER:PT0M",
                  f"DESCRIPTION:{_esc('Take ' + med['label'])}", "END:VALARM", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"


def notify_config(cab: dict, today: date) -> dict:
    """What the browser needs to fire dose-time notifications: plain JSON, no extras."""
    return dict(meds=[dict(id=m["id"], label=m["label"], times=list(m["times"]))
                      for m in cab["meds"] if m["times"]],
                taken=list(cab["taken"].get(today.isoformat(), [])))
