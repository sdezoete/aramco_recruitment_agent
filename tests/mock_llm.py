"""Mock OpenAI-compatible LLM for development and tests (no key, no internet).

Run:  .venv\\Scripts\\python -m tests.mock_llm --port 8001
Then: RA_LLM_BASE_URL=http://127.0.0.1:8001/v1  RA_LLM_MODEL=mock-harmony  (see .vscode / README)

Scripted behaviour, driven by the last user message and the tool results so far:
- "best/find/match/rank ... <data scientist|business analyst|structural>" ->
  set_job_spec(doc_id) -> match_candidates -> render_view(ranked_table) + render_view(score_radar) -> final
- "chart" / "skills" -> render_view(chart skill_supply) -> final
- "documents" / "jd" -> list_documents -> render_view(document_hits) -> final
- anything else -> a plain final answer
Streams reasoning_content (analysis channel), a preamble (commentary) and tool_calls.
--raw-harmony (or MOCK_RAW_HARMONY=1): leak harmony tokens in `content` instead of using
reasoning_content/tool_calls, to exercise the client's HarmonyStreamParser.
--no-tools: reject requests that include `tools` (exercises the prompted-JSON fallback).
"""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

RAW = os.environ.get("MOCK_RAW_HARMONY") == "1"
NO_TOOLS = os.environ.get("MOCK_NO_TOOLS") == "1"
MODEL = "mock-harmony"

app = FastAPI()


def _last_user(messages: list[dict]) -> tuple[str, list[dict]]:
    """Last user text and the tool results after it (native role=tool or prompted 'TOOL RESULT')."""
    idx = max((i for i, m in enumerate(messages) if m["role"] == "user"
               and not str(m.get("content", "")).startswith("TOOL RESULT")), default=0)
    results = []
    for m in messages[idx + 1:]:
        if m["role"] == "tool":
            results.append(json.loads(m["content"]) if m["content"].startswith("{") else {})
        elif m["role"] == "user" and str(m.get("content", "")).startswith("TOOL RESULT"):
            body = m["content"].split(":", 1)[1].strip()
            results.append(json.loads(body) if body.startswith("{") else {})
    return str(messages[idx].get("content") or "").lower(), results


def _plan(text: str, results: list[dict]) -> tuple[str, list[tuple[str, dict]], str]:
    """Returns (preamble, tool_calls, final_text). Exactly one of tool_calls / final_text is used."""
    n = len(results)
    doc = ("jd_senior_data_scientist" if "data scien" in text else
           "jd_business_analyst" if "business analyst" in text else
           "jd_structural_engineer" if ("structural" in text or "civil" in text) else None)
    if any(k in text for k in ("best", "find", "match", "rank", "shortlist")) and doc:
        if n == 0:
            return "Let me load that job description.", [("set_job_spec", {"doc_id": doc})], ""
        if n == 1:
            return "Now I'll score the pool against it.", [("match_candidates", {"limit": 10})], ""
        if n == 2:
            top = [r["candidate_id"] for r in results[1].get("results", [])[:3]]
            return "Here's the ranking.", [
                ("render_view", {"template": "ranked_table", "title": "Best matches: " + results[0].get("title", "")}),
                ("render_view", {"template": "score_radar", "title": "Top 3 head to head", "candidate_ids": top}),
            ], ""
        res = results[1].get("results", [])
        if not res:
            return "", [], "No candidates could be scored."
        best = res[0]
        return "", [], (f"**{best['full_name']} (#{best['candidate_id']})** is the strongest match with a score "
                        f"of {best['score']}.\n\n- Matched: {', '.join(best['matched_skills']) or 'none'}\n"
                        f"- Missing: {', '.join(best['missing_skills']) or 'none'}\n\n"
                        "See the ranking and radar above. Want me to compare the top three in detail?")
    if "chart" in text or "skill" in text:
        if n == 0:
            return "I'll chart the skill supply.", [("render_view", {"template": "chart", "title": "Skill supply",
                                                                      "metric": "skill_supply"})], ""
        return "", [], "The chart above shows how many candidates have each skill."
    if "document" in text or "jd" in text or "job description" in text:
        if n == 0:
            return "", [("list_documents", {})], ""
        if n == 1:
            return "", [("render_view", {"template": "document_hits", "title": "Available documents"})], ""
        return "", [], f"There are {results[0].get('total', 0)} documents. Pick a JD and I'll find the best candidates."
    return "", [], ("Hello! I'm the mock model. Try: *find the best candidates for the senior data scientist JD*, "
                    "*show a skills chart*, or *which job descriptions do we have?*")


def _chunk(delta: dict, finish: str | None = None) -> str:
    c = {"id": "mock", "object": "chat.completion.chunk", "created": int(time.time()), "model": MODEL,
         "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    return "data: " + json.dumps(c) + "\n\n"


def _words(text: str):
    for i, w in enumerate(text.split(" ")):
        yield (" " if i else "") + w


@app.get("/v1/models")
async def models():
    return {"object": "list", "data": [{"id": MODEL, "object": "model"}]}


@app.post("/v1/chat/completions")
async def completions(request: Request):
    body = await request.json()
    if NO_TOOLS and body.get("tools"):
        return JSONResponse({"error": {"message": "tools are not supported by this model"}}, status_code=400)
    prompted = not body.get("tools")
    text, results = _last_user(body["messages"])
    preamble, calls, final = _plan(text, results)
    reasoning = "The user wants help with recruiting. I should use the tools and not invent data."

    if prompted:  # compatibility mode: one JSON object per reply
        if calls:
            name, args = calls[0]
            reply = json.dumps({"tool": name, "arguments": args})
        else:
            reply = json.dumps({"final": final})
        if not body.get("stream"):
            return {"choices": [{"index": 0, "message": {"role": "assistant", "content": reply},
                                 "finish_reason": "stop"}]}

        def gen_prompted():
            yield _chunk({"role": "assistant", "content": reply})
            yield _chunk({}, "stop")
            yield "data: [DONE]\n\n"
        return StreamingResponse(gen_prompted(), media_type="text/event-stream")

    def gen():
        if RAW:
            yield _chunk({"role": "assistant", "content": "<|channel|>analysis<|message|>"})
            for w in _words(reasoning):
                yield _chunk({"content": w})
            yield _chunk({"content": "<|end|>"})
            if calls:
                if preamble:
                    yield _chunk({"content": "<|start|>assistant<|channel|>commentary<|message|>" + preamble + "<|end|>"})
                for name, args in calls:
                    raw = (f"<|start|>assistant<|channel|>commentary to=functions.{name} <|constrain|>json"
                           f"<|message|>{json.dumps(args)}<|call|>")
                    for i in range(0, len(raw), 7):   # split tokens across chunks on purpose
                        yield _chunk({"content": raw[i:i + 7]})
                yield _chunk({}, "stop")
            else:
                yield _chunk({"content": "<|start|>assistant<|channel|>final<|message|>"})
                for w in _words(final):
                    yield _chunk({"content": w})
                yield _chunk({"content": "<|return|>"})
                yield _chunk({}, "stop")
            yield "data: [DONE]\n\n"
            return

        yield _chunk({"role": "assistant", "reasoning_content": ""})
        for w in _words(reasoning):
            yield _chunk({"reasoning_content": w})
        if calls:
            for w in _words(preamble) if preamble else []:
                yield _chunk({"content": w})
            for i, (name, args) in enumerate(calls):
                cid = "call_" + uuid.uuid4().hex[:10]
                yield _chunk({"tool_calls": [{"index": i, "id": cid, "type": "function",
                                              "function": {"name": name, "arguments": ""}}]})
                a = json.dumps(args)
                for j in range(0, len(a), 12):
                    yield _chunk({"tool_calls": [{"index": i, "function": {"arguments": a[j:j + 12]}}]})
            yield _chunk({}, "tool_calls")
        else:
            for w in _words(final):
                yield _chunk({"content": w})
            yield _chunk({}, "stop")
        yield "data: [DONE]\n\n"

    if not body.get("stream"):
        msg: dict = {"role": "assistant", "content": final or preamble or None, "reasoning_content": reasoning}
        if calls:
            msg["tool_calls"] = [{"id": f"call_{i}", "type": "function",
                                  "function": {"name": n, "arguments": json.dumps(a)}} for i, (n, a) in enumerate(calls)]
        return {"choices": [{"index": 0, "message": msg, "finish_reason": "tool_calls" if calls else "stop"}]}
    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--raw-harmony", action="store_true")
    ap.add_argument("--no-tools", action="store_true")
    ns = ap.parse_args()
    if ns.raw_harmony:
        os.environ["MOCK_RAW_HARMONY"] = "1"
        RAW = True
    if ns.no_tools:
        os.environ["MOCK_NO_TOOLS"] = "1"
        NO_TOOLS = True
    uvicorn.run(app, host="127.0.0.1", port=ns.port)
