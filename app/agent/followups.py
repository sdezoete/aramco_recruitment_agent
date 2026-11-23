"""Follow-up suggestions (ADR-016): the model ends its final answer with lines like

    ::followup:: Turn these into a structured interview guide with scoring criteria

The UI shows them as buttons under the answer; a click sends the text as the next user message.
`FollowupFilter` removes those lines from the streamed text as it arrives (a marker split across stream
chunks is held back, never shown), and `split_followups` does the same for a complete text.
Pure functions, no I/O: tested in tests/test_followups.py.
"""
from __future__ import annotations

import re

MARKER = "::followup::"
MAX_ITEMS = 3
MAX_PROMPT = 300
MAX_LABEL = 90

_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])?\s*")


def _body(line: str) -> str:
    """The line without leading whitespace and an optional list bullet, lower-cased for matching."""
    return _BULLET.sub("", line, count=1).lower()


def _is_marker(line: str) -> bool:
    return _body(line).startswith(MARKER)


def _could_become_marker(partial: str) -> bool:
    """True while an unfinished line could still turn out to be a marker line (so hold it back)."""
    stripped = partial.lstrip()
    if stripped in ("", "-", "*", "•") or re.fullmatch(r"\d+[.)]?", stripped):
        return True
    body = _body(partial)
    return MARKER.startswith(body) or body.startswith(MARKER)


def _clean(text: str) -> str:
    t = text.strip().strip("*_`\"'“”‘’").strip()
    t = re.sub(r"\s+", " ", t)
    return t[:MAX_PROMPT].rstrip()


def _item(line: str) -> dict | None:
    body = _BULLET.sub("", line, count=1)
    prompt = _clean(body[len(MARKER):])
    if not prompt:
        return None
    label = prompt if len(prompt) <= MAX_LABEL else prompt[:MAX_LABEL - 1].rstrip() + "…"
    return {"label": label, "prompt": prompt}


class FollowupFilter:
    """Streaming filter. feed() returns the text to show now; finish() returns the rest plus the items."""

    def __init__(self) -> None:
        self._held = ""          # start of the current line, not yet known to be text or a marker
        self._in_text = False    # the current line is already known to be ordinary text
        self._items: list[dict] = []

    def feed(self, text: str) -> str:
        out: list[str] = []
        i = 0
        while i < len(text):
            nl = text.find("\n", i)
            if self._in_text:
                if nl < 0:
                    out.append(text[i:])
                    break
                out.append(text[i:nl + 1])
                self._in_text = False
                i = nl + 1
                continue
            if nl < 0:
                self._held += text[i:]
                if not _could_become_marker(self._held):
                    out.append(self._held)
                    self._held, self._in_text = "", True
                break
            line = self._held + text[i:nl]
            self._held = ""
            if _is_marker(line):
                self._add(line)
            else:
                out.append(line + "\n")
            i = nl + 1
        return "".join(out)

    def finish(self) -> tuple[str, list[dict]]:
        rest, self._held = self._held, ""
        if rest and _is_marker(rest):
            self._add(rest)
            rest = ""
        return rest, list(self._items)

    def _add(self, line: str) -> None:
        item = _item(line)
        if not item or len(self._items) >= MAX_ITEMS:
            return
        if any(x["prompt"].lower() == item["prompt"].lower() for x in self._items):
            return
        self._items.append(item)


# ---------------------------------------------------------------------------- fallback: offers in prose
# Models sometimes ignore the format and end with "If you want, I can ..." anyway. Then the offer stays
# visible as text and its options also become buttons. English phrasing only; conservative on purpose:
# only an offer in the last paragraph of the answer counts.
_OFFER = re.compile(
    r"(?:if you(?:'d| would)? (?:want|like)(?: me to)?|would you like(?: me)? to|do you want me to|want me to|"
    r"shall i|should i|let me know if you(?:'d| would)? like(?: me to)?|i can also|i could also|"
    r"happy to|next,? i can)\b[,:]?[ \t]*(?:i can(?: also| now| then)?|i could(?: also)?)?[,:]?[ \t]*",
    re.I)
_LIST_ITEM = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.+?)\s*$")
_TRAIL = re.compile(r"(?:[\s,;:.!?—–-]+|\s+(?:or|and)\s*)+$", re.I)


def _offer_prompt(fragment: str) -> str | None:
    t = re.sub(r"[*_`]+", "", fragment)
    t = re.sub(r"^\s*(?:also|now|then|either|for example|e\.g\.)[,:]?\s+", "", t, flags=re.I)
    t = _TRAIL.sub("", t.strip())
    if len(t) < 6 or len(t.split()) < 2:
        return None
    return t[0].upper() + t[1:]


def offers_from_prose(text: str) -> list[dict]:
    """Suggestions from a trailing 'If you want, I can ...' offer (sentence or bullet list)."""
    paras = [p for p in re.split(r"\n\s*\n", (text or "").strip()) if p.strip()]
    if not paras:
        return []
    # the offer sentence and its list may be split by a blank line: look at the last two paragraphs
    tail = "\n".join(paras[-2:]) if len(paras) > 1 and _LIST_ITEM.match(paras[-1].splitlines()[0]) else paras[-1]
    matches = list(_OFFER.finditer(tail))
    if not matches:
        return []
    after = tail[matches[-1].end():]
    lines = after.splitlines()
    head = lines[0].strip() if lines else ""
    items_text = [m.group(1) for m in (_LIST_ITEM.match(l) for l in lines[1:]) if m]
    prompts: list[str] = []
    if items_text and (not head or head.endswith(":")):
        prompts = [p for p in (_offer_prompt(x) for x in items_text) if p]
    elif head:
        # one sentence, possibly "A, or B": split on a top-level " or "
        sentence = re.split(r"(?<=[.?!])\s", head, maxsplit=1)[0]
        parts = re.split(r",\s+or\s+", sentence, flags=re.I)   # "do A, or do B" (not "top 3 or top 5")
        prompts = [p for p in (_offer_prompt(x) for x in parts) if p]
    out: list[dict] = []
    for p in prompts:
        item = _item(MARKER + " " + p)
        if item and not any(x["prompt"].lower() == item["prompt"].lower() for x in out):
            out.append(item)
        if len(out) >= MAX_ITEMS:
            break
    return out


def split_followups(text: str) -> tuple[str, list[dict]]:
    """Complete text -> (text without follow-up lines, trailing whitespace trimmed; items)."""
    f = FollowupFilter()
    shown = f.feed(text or "")
    rest, items = f.finish()
    return (shown + rest).rstrip(), items
