"""Bridge to the browser's localStorage (components/cabinet_store)."""
from pathlib import Path

import streamlit.components.v1 as components

_component = components.declare_component(
    "medscan_cabinet_store", path=str(Path(__file__).resolve().parent.parent / "components" / "cabinet_store"))


def sync(write: dict | None):
    """Render the invisible component. `write` is {'v': int, 'data': cabinet} to save, or None.
    Returns {'loaded': True, 'data': <saved cabinet or None>} once the browser has answered."""
    return _component(write=write, key="cabinet_store", default=None)
