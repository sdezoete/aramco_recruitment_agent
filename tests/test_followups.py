"""Follow-up suggestion lines (ADR-016): extraction from complete and streamed answers. No LLM, no DB."""
import pytest

from app.agent.followups import MAX_ITEMS, MAX_LABEL, FollowupFilter, split_followups

ANSWER = (
    "**Jeroen Jansen (#180)** is the strongest fit.\n\n"
    "- Matched: Excel, Tableau\n"
    "1. Reem is close behind\n"
    ": a line that starts with a colon\n\n"
    "::followup:: Turn these into a structured interview guide with scoring criteria\n"
    "- ::followup:: Compare Reem Al-Subaie (#127) and Pieter Jansen (#97) on assessments\n"
    "::FOLLOWUP:: اقترح أسئلة مقابلة لريم"
)
CLEAN = (
    "**Jeroen Jansen (#180)** is the strongest fit.\n\n"
    "- Matched: Excel, Tableau\n"
    "1. Reem is close behind\n"
    ": a line that starts with a colon"
)
PROMPTS = [
    "Turn these into a structured interview guide with scoring criteria",
    "Compare Reem Al-Subaie (#127) and Pieter Jansen (#97) on assessments",
    "اقترح أسئلة مقابلة لريم",
]


def stream(text: str, size: int) -> tuple[str, list[dict], list[str]]:
    f = FollowupFilter()
    shown = [f.feed(text[i:i + size]) for i in range(0, len(text), size)]
    rest, items = f.finish()
    return "".join(shown) + rest, items, shown


def test_split_complete_answer():
    text, items = split_followups(ANSWER)
    assert text == CLEAN
    assert [i["prompt"] for i in items] == PROMPTS
    assert all(i["label"] == i["prompt"] for i in items)


@pytest.mark.parametrize("size", [1, 2, 3, 5, 7, 11, 13, 64, 10_000])
def test_streaming_matches_complete_for_any_chunking(size):
    shown, items, chunks = stream(ANSWER, size)
    assert shown.rstrip() == CLEAN
    assert [i["prompt"] for i in items] == PROMPTS
    assert not any("::" in c and "followup" in c.lower() for c in chunks), "a marker never leaks into a chunk"


def test_every_split_point_of_a_marker():
    """A marker cut anywhere between two chunks is still held back."""
    text = "Done.\n::followup:: Next step"
    for cut in range(len(text) + 1):
        f = FollowupFilter()
        out = f.feed(text[:cut]) + f.feed(text[cut:])
        rest, items = f.finish()
        assert (out + rest).rstrip() == "Done.", cut
        assert [i["prompt"] for i in items] == ["Next step"], cut


def test_ordinary_text_is_not_held_back():
    f = FollowupFilter()
    assert f.feed("Hello") == "Hello"
    assert f.feed(" world, more") == " world, more"
    assert f.feed("\nNext line") == "\nNext line"
    assert f.feed(" continues") == " continues"


def test_possible_marker_start_is_held_until_it_diverges():
    f = FollowupFilter()
    assert f.feed("ok\n::") == "ok\n"     # could be a marker: wait
    assert f.feed("follow") == ""
    assert f.feed("ers unite") == "::followers unite"   # it wasn't
    assert f.finish() == ("", [])


def test_no_followups():
    assert split_followups("Plain answer.\n\nWith a list:\n- a\n- b") == ("Plain answer.\n\nWith a list:\n- a\n- b", [])
    assert split_followups("") == ("", [])
    assert split_followups(None) == ("", [])


def test_marker_without_trailing_newline_and_mid_answer():
    text, items = split_followups("Intro\n::followup:: First\nMore text after\n::followup:: Second")
    assert text == "Intro\nMore text after"
    assert [i["prompt"] for i in items] == ["First", "Second"]


def test_limits_cleanup_and_dedupe():
    long = "x" * 500
    raw = "\n".join([
        "::followup::   **Compare   the top 3**  ",
        "::followup:: compare THE top 3",          # duplicate (case-insensitive)
        "::followup::",                            # empty: ignored
        "::followup:: “Quoted request”",
        f"::followup:: {long}",
        "::followup:: one too many",
    ])
    text, items = split_followups(raw)
    assert text == ""
    assert len(items) == MAX_ITEMS
    assert items[0]["prompt"] == "Compare the top 3"
    assert items[1]["prompt"] == "Quoted request"
    assert len(items[2]["prompt"]) == 300
    assert len(items[2]["label"]) == MAX_LABEL and items[2]["label"].endswith("…")


@pytest.mark.parametrize("prefix", ["", "  ", "- ", "* ", "• ", "1. ", "2) "])
def test_bullet_and_indent_prefixes(prefix):
    _, items = split_followups(f"Answer\n{prefix}::followup:: Do the thing")
    assert [i["prompt"] for i in items] == ["Do the thing"]


def test_marker_inside_a_sentence_is_not_a_followup():
    text, items = split_followups("Write ::followup:: lines to suggest steps.")
    assert items == [] and text == "Write ::followup:: lines to suggest steps."


# ---------------------------------------------------------------- fallback: offers written in prose
from app.agent.followups import offers_from_prose  # noqa: E402


def _prompts(text):
    return [i["prompt"] for i in offers_from_prose(text)]


def test_offer_sentence_from_the_user_report():
    text = ("Here are ten questions.\n\n"
            "If you want, I can also turn these into a structured interview guide with scoring criteria.")
    assert _prompts(text) == ["Turn these into a structured interview guide with scoring criteria"]


def test_offer_list_from_a_real_model_answer():
    text = ("### Also strong\n- **Munirah (#299)** solid match.\n\n### Suggested next step\n"
            "If you want, I can now:\n"
            "- compare the **top 2–3 candidates side by side**, or\n"
            "- open full profiles for the strongest candidates to review experience and assessments in detail.")
    assert _prompts(text) == ["Compare the top 2–3 candidates side by side",
                              "Open full profiles for the strongest candidates to review experience and assessments in detail"]


def test_offer_list_after_a_blank_line():
    text = "Summary.\n\nWould you like me to:\n\n1. Compare Reem (#127) and Pieter (#97)\n2. Show a skills chart"
    assert _prompts(text) == ["Compare Reem (#127) and Pieter (#97)", "Show a skills chart"]


@pytest.mark.parametrize("text,expected", [
    ("Done. Would you like me to compare them on assessments?", ["Compare them on assessments"]),
    ("Done. Want me to show the shortlist as cards?", ["Show the shortlist as cards"]),
    ("Done. Let me know if you'd like me to rank the pool for a structural engineer role.",
     ["Rank the pool for a structural engineer role"]),
    ("Done. I can also draft interview questions for Reem, or compare her with Pieter.",
     ["Draft interview questions for Reem", "Compare her with Pieter"]),
    ("Done. If you want, I can compare the top 3 or top 5 candidates.", ["Compare the top 3 or top 5 candidates"]),
])
def test_offer_sentences(text, expected):
    assert _prompts(text) == expected


@pytest.mark.parametrize("text", [
    "Jeroen is the strongest fit. See the ranking above.",
    "If you want the full list, export it from the top bar.\n\nJeroen leads on every criterion.",  # not last paragraph
    "",
    "Shall I?",
])
def test_no_offer_no_buttons(text):
    assert offers_from_prose(text) == []
