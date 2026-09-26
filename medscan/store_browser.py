"""Bridge to the browser (components/cabinet_store): localStorage persistence for the cabinet
and opt-in dose-time notifications. Both run client-side; nothing is sent to a server."""
from pathlib import Path

import streamlit.components.v1 as components

_component = components.declare_component(
    "medscan_cabinet_store", path=str(Path(__file__).resolve().parent.parent / "components" / "cabinet_store"))


def sync(write: dict | None, config: dict | None = None, today: str = ""):
    """Invisible, always-rendered instance. `write` is {'v': int, 'data': cabinet} to save (or None);
    `config` is cabinet.notify_config(). Returns {'loaded', 'data', 'today'} once the browser answers.
    This instance also fires the notifications, so it must be rendered on every screen."""
    config = config or {}
    return _component(write=write, meds=config.get("meds", []), taken=config.get("taken", []),
                      today=today, ui=False, key="cabinet_store", default=None)


def notify_switch():
    """The visible opt-in switch (cabinet screen). Handles the permission prompt itself,
    because browsers only allow it from a click inside the same frame. Render it at a fixed
    position: Streamlit re-mounts a component frame that moves, and the new frame can stay blank."""
    _component(write=None, meds=[], taken=[], today="", ui=True, key="cabinet_notify_ui", default=None)
