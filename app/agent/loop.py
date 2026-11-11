"""Agent loop: LLM <-> tools, yielding SSE events (docs/ARCHITECTURE.md, SSE event protocol).

Harmony history policy (docs/HARMONY.md): analysis (reasoning) is never stored or sent back; assistant
messages with tool_calls (commentary) and tool results are kept; only the final answer text is stored
for completed turns.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import AsyncIterator, Callable

from app.agent import prompts, registry
from app.config import Settings
from app.db.repository import Repository
from app.llm import harmony
from app.llm.client import LLMClient, LLMError, ToolsUnsupported
from app.tools.context import ChatState, ToolContext

log = logging.getLogger("ra.agent")

Event = tuple[str, dict]
HISTORY_LIMIT = 40   # messages kept per chat (older ones are dropped at a user-message boundary)


def _prefix(settings: Settings, prompted: bool) -> list[dict]:
    instructions = prompts.INSTRUCTIONS
    if prompted:
        instructions += "\n" + prompts.PROMPTED_TOOLS.format(catalog=registry.catalog_text())
    return [harmony.system_message(prompts.IDENTITY.format(name=settings.LLM_DISPLAY_NAME or "ARIF"),
                                   settings.LLM_REASONING_EFFORT),
            harmony.developer_message(instructions)]


def _trim(history: list[dict]) -> None:
    if len(history) <= HISTORY_LIMIT:
        return
    cut = len(history) - HISTORY_LIMIT
    while cut < len(history) and history[cut].get("role") != "user":
        cut += 1
    del history[:cut]


_JSON_OBJ = re.compile(r"\{.*\}", re.S)


def _parse_prompted(text: str) -> dict | None:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{"):] if "{" in t else t
    m = _JSON_OBJ.search(t)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except ValueError:
        return None
    return obj if isinstance(obj, dict) and ("tool" in obj or "final" in obj) else None


async def run_turn(*, settings: Settings, client: LLMClient, repo_factory: Callable[[], Repository],
                   chat: ChatState, user_text: str) -> AsyncIterator[Event]:
    try:
        repo = await asyncio.to_thread(repo_factory)
        await asyncio.to_thread(chat.load, repo)
    except Exception as e:
        log.exception("database unavailable")
        yield "error", {"message": "The candidate database is not reachable."
                        + ("" if settings.PRODUCTION else f" ({type(e).__name__}: {e})")}
        return
    try:
        async for ev in _run(settings, client, repo, chat, user_text):
            yield ev
    finally:
        try:
            repo.conn.close()
        except Exception:
            pass


async def _run(settings: Settings, client: LLMClient, repo: Repository, chat: ChatState,
               user_text: str) -> AsyncIterator[Event]:
    ctx = ToolContext(repo=repo, settings=settings, chat=chat)
    chat.history.append({"role": "user", "content": user_text})
    _trim(chat.history)
    turn_msgs: list[dict] = []        # tool-call chain of this turn (kept only until the final answer)
    prompted = client.caps.native_tools is False
    started = time.time()

    for step in range(1, settings.AGENT_MAX_STEPS + 1):
        messages = _prefix(settings, prompted) + chat.history + turn_msgs
        thinking_since: float | None = None
        streamed_text = False
        turn = None
        try:
            async for ev in client.chat(messages, None if prompted else registry.definitions()):
                if ev.kind == "reasoning":
                    if thinking_since is None:
                        thinking_since = time.time()
                        yield "thinking", {"state": "start"}
                elif ev.kind in ("content", "commentary"):
                    if thinking_since is not None:
                        yield "thinking", {"state": "end", "seconds": round(time.time() - thinking_since, 1)}
                        thinking_since = None
                    if not prompted:
                        streamed_text = True
                        yield "text_delta", {"text": ev.text}
                elif ev.kind == "end":
                    turn = ev.turn
        except ToolsUnsupported:
            log.warning("Endpoint has no native function calling; switching to prompted-JSON tools")
            prompted = True
            yield "notice", {"message": "The model endpoint has no native tool calling; using compatibility mode."}
            continue
        except LLMError as e:
            log.error("LLM error: %s", e)
            msg = str(e) if not settings.PRODUCTION else "The AI model could not be reached or rejected the request."
            yield "error", {"message": msg}
            return
        if thinking_since is not None:
            yield "thinking", {"state": "end", "seconds": round(time.time() - thinking_since, 1)}
        if turn is None:
            yield "error", {"message": "The AI model returned no response."}
            return

        tool_calls = list(turn.tool_calls)
        final_text = turn.content

        if prompted:
            obj = _parse_prompted(turn.content)
            if obj and "tool" in obj:
                tool_calls = [{"id": "p_" + uuid.uuid4().hex[:12], "type": "function",
                               "function": {"name": str(obj["tool"]),
                                            "arguments": json.dumps(obj.get("arguments") or {})}}]
            else:
                final_text = str(obj["final"]) if obj and "final" in obj else turn.content
                yield "text_delta", {"text": final_text}
                streamed_text = True

        if not tool_calls:
            if streamed_text:
                yield "segment_end", {"kind": "final"}
            if turn.finish_reason == "length":
                yield "notice", {"message": "The answer was cut off at the token limit (LLM_MAX_TOKENS)."}
            chat.history.append({"role": "assistant", "content": final_text})
            yield "done", {"steps": step, "seconds": round(time.time() - started, 1), "usage": turn.usage}
            return

        # ---- tool calls (harmony commentary channel)
        if streamed_text:
            yield "segment_end", {"kind": "preamble"}
        if prompted:
            turn_msgs.append({"role": "assistant", "content": turn.content})
        else:
            turn_msgs.append({"role": "assistant", "content": turn.content or None, "tool_calls": tool_calls})

        for tc in tool_calls:
            yield "tool_start", {"id": tc["id"], "name": tc["function"]["name"],
                                 "label": registry.label(tc["function"]["name"])}

        def run_all() -> list:
            # One pyodbc connection per turn, so calls run in order on one worker thread.
            out = []
            for tc in tool_calls:
                t0 = time.time()
                ok, result = registry.execute(ctx, tc["function"]["name"], tc["function"]["arguments"])
                out.append((tc, ok, result, round(time.time() - t0, 2)))
            return out

        try:
            outcomes = await asyncio.to_thread(run_all)
        except Exception as e:   # DB down etc.
            log.exception("tool execution failed")
            msg = "A data source failed while running a tool." if settings.PRODUCTION else f"Tool failure: {e}"
            yield "error", {"message": msg}
            return

        for block in ctx.blocks:
            yield "ui_block", block
        ctx.blocks.clear()

        for tc, ok, result, secs in outcomes:
            summary = _summary(tc["function"]["name"], ok, result)
            yield "tool_end", {"id": tc["id"], "ok": ok, "summary": summary, "seconds": secs}
            content = registry.to_message_content(result)
            if prompted:
                turn_msgs.append({"role": "user", "content": f"TOOL RESULT {tc['function']['name']}: {content}"})
            else:
                turn_msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": content})

    yield "notice", {"message": f"Stopped after {settings.AGENT_MAX_STEPS} steps (AGENT_MAX_STEPS)."}
    chat.history.append({"role": "assistant", "content": "(stopped: step limit reached)"})
    yield "done", {"steps": settings.AGENT_MAX_STEPS, "seconds": round(time.time() - started, 1)}


def _summary(name: str, ok: bool, r: dict) -> str:
    if not ok:
        return "error: " + str(r.get("error", ""))[:120]
    if "total_scored" in r:
        return f"{r['total_scored']} scored"
    if "total" in r:
        return f"{r['total']} found"
    if name == "set_job_spec":
        return r.get("title") or "spec set"
    if name == "render_view":
        return r.get("template", "view")
    if name == "get_candidate_profile":
        return r.get("full_name") or "profile"
    return "done"
