"""Harmony conventions over an OpenAI-compatible chat-completions transport.

See docs/HARMONY.md. In short:
- Roles: system (identity, date, reasoning level, channels), developer (instructions + tools), user,
  assistant, tool.
- Channels: analysis (chain of thought: never shown to users, never sent back after a final answer),
  commentary (tool calls and short preambles), final (the user-facing answer).
- Servers normally do the harmony rendering/parsing themselves and return reasoning in
  `reasoning_content`/`reasoning`, tool calls in `tool_calls`, and the final text in `content`.
  If a gateway leaks raw harmony tokens into `content`, HarmonyStreamParser splits them back into
  channels (including raw `to=functions.x` tool calls). DeepSeek-style `<think>...</think>` leaks are
  routed to the analysis channel the same way.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import date

TOKENS = ("<|start|>", "<|channel|>", "<|message|>", "<|end|>", "<|return|>", "<|call|>", "<|constrain|>")
ALL_TOKENS = TOKENS + ("<think>", "</think>")


def system_message(identity: str, reasoning_effort: str, today: date | None = None) -> dict:
    today = today or date.today()
    effort = reasoning_effort if reasoning_effort in ("low", "medium", "high") else "medium"
    text = (
        f"{identity}\n"
        f"Current date: {today.isoformat()}\n\n"
        f"Reasoning: {effort}\n\n"
        "# Valid channels: analysis, commentary, final. Channel must be included for every message.\n"
        "Calls to these tools must go to the commentary channel: 'functions'."
    )
    return {"role": "system", "content": text}


def developer_message(instructions: str) -> dict:
    return {"role": "developer", "content": "# Instructions\n\n" + instructions.strip()}


def to_wire(messages: list[dict], developer_role: bool) -> list[dict]:
    """Gateways without a developer role get the developer text merged into the system message."""
    if developer_role:
        return messages
    out: list[dict] = []
    for m in messages:
        if m.get("role") == "developer":
            if out and out[0].get("role") == "system":
                out[0] = {**out[0], "content": out[0]["content"] + "\n\n" + m["content"]}
            else:
                out.insert(0, {"role": "system", "content": m["content"]})
        else:
            out.append(m)
    return out


@dataclass
class Piece:
    channel: str            # analysis | commentary | final
    text: str = ""
    recipient: str | None = None   # e.g. "functions.match_candidates" for raw tool calls
    done: bool = False      # message finished (<|end|>, <|return|>, <|call|>)
    is_call: bool = False


class HarmonyStreamParser:
    """Incremental parser for raw harmony text that leaked into `content`.

    feed() returns Pieces. Plain text (no harmony tokens seen) passes through as channel "final".
    Raw tool calls (commentary + to=functions.x + <|call|>) are buffered and returned whole.
    """

    def __init__(self) -> None:
        self.buf = ""
        self.seen_tokens = False
        self.state = "body"            # header | body
        self.header = ""
        self.channel = "final"
        self.recipient: str | None = None
        self.call_buf = ""

    def _header_done(self) -> None:
        h = self.header
        m = re.search(r"\b(analysis|commentary|final)\b", h)
        self.channel = m.group(1) if m else "final"
        r = re.search(r"to=([\w.\-]+)", h)
        self.recipient = r.group(1) if r else None
        self.header = ""
        self.call_buf = ""

    def _emit_text(self, text: str, out: list[Piece]) -> None:
        if not text:
            return
        if self.recipient:
            self.call_buf += text
        else:
            out.append(Piece(self.channel, text))

    def _end_message(self, token: str, out: list[Piece]) -> None:
        if self.recipient:
            out.append(Piece("commentary", self.call_buf, recipient=self.recipient, done=True,
                             is_call=(token == "<|call|>" or self.recipient.startswith("functions."))))
        else:
            out.append(Piece(self.channel, "", done=True))
        self.recipient, self.call_buf = None, ""
        self.channel = "final"

    def feed(self, chunk: str) -> list[Piece]:
        self.buf += chunk
        out: list[Piece] = []
        while self.buf:
            i = self.buf.find("<")
            if i < 0:
                text, self.buf = self.buf, ""
            elif i > 0:
                text, self.buf = self.buf[:i], self.buf[i:]
            else:
                tok = next((t for t in ALL_TOKENS if self.buf.startswith(t)), None)
                if tok is None:
                    if any(t.startswith(self.buf) for t in ALL_TOKENS):
                        break  # a token split across chunks; wait for more
                    text, self.buf = self.buf[:1], self.buf[1:]   # literal "<"
                else:
                    self.buf = self.buf[len(tok):]
                    self.seen_tokens = True
                    if tok == "<think>":          # DeepSeek-style reasoning leak
                        self.state, self.channel, self.recipient = "body", "analysis", None
                    elif tok == "</think>":
                        out.append(Piece("analysis", "", done=True))
                        self.state, self.channel = "body", "final"
                    elif tok in ("<|start|>", "<|channel|>"):
                        if self.state == "body" and tok == "<|start|>":
                            self.header = ""
                        self.state = "header"
                        if tok == "<|channel|>":
                            self.header += " "
                    elif tok == "<|constrain|>":
                        self.header += " <constrain> "
                    elif tok == "<|message|>":
                        self._header_done()
                        self.state = "body"
                    else:  # <|end|>, <|return|>, <|call|>
                        self._end_message(tok, out)
                        self.state = "body"
                    continue
            if self.state == "header":
                self.header += text
            else:
                self._emit_text(text, out)
        return out

    def flush(self) -> list[Piece]:
        out: list[Piece] = []
        if self.buf:
            rest, self.buf = self.buf, ""
            if self.state == "header":
                self.header += rest
            else:
                self._emit_text(rest, out)
        if self.recipient and self.call_buf:
            out.append(Piece("commentary", self.call_buf, recipient=self.recipient, done=True, is_call=True))
            self.recipient, self.call_buf = None, ""
        return out


def raw_call_to_tool_call(piece: Piece) -> dict | None:
    """Convert a raw harmony call (recipient functions.x) to an OpenAI-style tool_call dict."""
    if not piece.recipient or not piece.recipient.startswith("functions."):
        return None
    name = piece.recipient.split(".", 1)[1]
    args = piece.text.strip()
    try:
        json.loads(args or "{}")
    except ValueError:
        pass  # leave as-is; the loop reports invalid JSON back to the model
    return {"id": "call_" + uuid.uuid4().hex[:24], "type": "function",
            "function": {"name": name, "arguments": args or "{}"}}
