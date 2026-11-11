from app.llm import harmony


def feed_all(chunks):
    p = harmony.HarmonyStreamParser()
    out = []
    for c in chunks:
        out += p.feed(c)
    out += p.flush()
    return p, out


def text_of(pieces, channel):
    return "".join(x.text for x in pieces if x.channel == channel and not x.is_call)


def test_plain_text_passthrough():
    p, out = feed_all(["Hello ", "world <b> 5 < 6"])
    assert not p.seen_tokens
    assert text_of(out, "final") == "Hello world <b> 5 < 6"


def test_channels_split_across_chunks():
    raw = ("<|channel|>analysis<|message|>think hard<|end|>"
           "<|start|>assistant<|channel|>final<|message|>The answer.<|return|>")
    chunks = [raw[i:i + 5] for i in range(0, len(raw), 5)]
    _, out = feed_all(chunks)
    assert text_of(out, "analysis") == "think hard"
    assert text_of(out, "final") == "The answer."


def test_raw_tool_call():
    raw = ('<|start|>assistant<|channel|>commentary to=functions.match_candidates <|constrain|>json'
           '<|message|>{"limit": 5}<|call|>')
    _, out = feed_all([raw[i:i + 3] for i in range(0, len(raw), 3)])
    calls = [x for x in out if x.is_call]
    assert len(calls) == 1
    tc = harmony.raw_call_to_tool_call(calls[0])
    assert tc["function"]["name"] == "match_candidates"
    assert tc["function"]["arguments"] == '{"limit": 5}'


def test_commentary_preamble_is_not_a_call():
    _, out = feed_all(["<|start|>assistant<|channel|>commentary<|message|>Let me check.<|end|>"])
    assert text_of(out, "commentary") == "Let me check."
    assert not any(x.is_call for x in out)


def test_deepseek_think_tags():
    _, out = feed_all(["<thi", "nk>reasoning here</th", "ink>Final text"])
    assert text_of(out, "analysis") == "reasoning here"
    assert text_of(out, "final") == "Final text"


def test_developer_role_merge():
    msgs = [harmony.system_message("I am X", "high"), harmony.developer_message("Do Y"),
            {"role": "user", "content": "hi"}]
    wire = harmony.to_wire(msgs, developer_role=False)
    assert [m["role"] for m in wire] == ["system", "user"]
    assert "Reasoning: high" in wire[0]["content"] and "Do Y" in wire[0]["content"]
    assert harmony.to_wire(msgs, developer_role=True) == msgs
