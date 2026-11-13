"""Layout guards for static/css/app.css that the fake-DOM JS tests cannot see.

Regression: without a fixed grid row, a long profile in the side panel stretched the page grid past the
screen height, so the whole page scrolled and the panel sat at the top of the page instead of beside the
chat (ADR-015). The page itself must never scroll; the chat and the panel scroll independently.
"""
import re
from pathlib import Path

import pytest

CSS = (Path(__file__).resolve().parents[1] / "static" / "css" / "app.css").read_text(encoding="utf-8")


def rule(selector: str) -> dict[str, str]:
    """Declarations of the first top-level rule whose selector list is exactly `selector`."""
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"rule {selector!r} not found in app.css"
    decls = {}
    for part in m.group(1).split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            decls[k.strip()] = v.strip()   # later duplicates (e.g. 100vh then 100dvh) win, like CSS
    return decls


def test_page_is_one_screen_high_and_never_scrolls():
    app = rule(".app")
    assert app["height"] == "100dvh"
    assert app["grid-template-rows"] == "minmax(0, 1fr)"
    assert app["overflow"] == "hidden"


@pytest.mark.parametrize("selector", [".main", ".scroller", ".profile-panel", ".panel-body"])
def test_scroll_containers_can_shrink(selector):
    # min-height: 0 lets flex/grid children be smaller than their content, so they scroll instead of growing
    assert rule(selector).get("min-height") == "0", selector


@pytest.mark.parametrize("selector", [".scroller", ".panel-body"])
def test_chat_and_panel_scroll_independently(selector):
    assert rule(selector).get("overflow-y") == "auto"


def test_docked_panel_is_a_third_column_on_wide_screens():
    cols = rule(".app.panel-open")["grid-template-columns"]
    assert cols.startswith("280px minmax(0, 1fr)") and "clamp(" in cols


def test_overlay_panel_below_1200px():
    block = CSS[CSS.index("@media (max-width: 1199px)"):]
    block = block[:block.index("\n}\n")]
    assert "position: fixed" in block and ".profile-panel" in block
