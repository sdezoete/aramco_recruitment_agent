# Harmony conventions

The production model, DeepSeek 4.1 Flash on the air-gapped server, is reached through the corporate gateway's OpenAI-compatible chat-completions API with an API key. During development, OpenAI stands in for it through the same API. The app follows the **harmony** response format in both environments. Code: `app/llm/harmony.py` and `app/llm/client.py`. Agent history handling: `app/agent/loop.py`.

## Roles

| Role | What we put there |
|---|---|
| `system` | Identity, `Current date`, `Reasoning: <low/medium/high>` (from `LLM_REASONING_EFFORT`), the valid channels, and "tool calls go to the commentary channel" |
| `developer` | The instructions (`app/agent/prompts.py`). Tools are sent through the API's `tools` field. If the endpoint rejects the `developer` role, its text is merged into `system` automatically |
| `user` | The recruiter's message |
| `assistant` | Model output (see channels below) |
| `tool` | Tool results, `{"role":"tool","tool_call_id":…,"content":json}` |

## Channels and how the app treats them

| Channel | Comes back as | App behaviour |
|---|---|---|
| `analysis` (chain of thought) | `reasoning_content` / `reasoning` deltas; or leaked `<\|channel\|>analysis…` or `<think>…</think>` in `content` | **Never shown to users and never sent back to the model.** The UI shows only "Thinking… / Thought for Ns" |
| `commentary` | `tool_calls`, plus short preamble text before tool calls; or leaked `to=functions.x … <\|call\|>` | Tool calls run. Preamble text is shown as a muted status line |
| `final` | `content` | Rendered as Markdown and stored in history |

## History policy

- Within a turn, the assistant messages that carry `tool_calls`, and their tool results, are sent back so the model can continue the chain.
- When a turn ends with a final answer, only the **user message and final answer text** stay in the chat history. The tool-call chain and all analysis are dropped. Facts the next turn needs (the active job spec and the shortlist) live in `T_IIR_ARIF_AGENT_MEMORY` and are reached through tools.

## Robustness: the gateway's behaviour is not assumed

- **Leaked tokens:** if raw harmony tokens or DeepSeek `<think>` tags appear in `content`, `HarmonyStreamParser` splits them back into channels, even when the tokens are split across stream chunks. Tests: `tests/test_harmony.py`.
- **Parameters the endpoint rejects** are adapted on a 400 response and remembered:
  - `max_tokens` is swapped for `max_completion_tokens` (OpenAI reasoning models need this)
  - `reasoning_effort` and `stream_options` are dropped
  - the `developer` role is merged into `system`
  - `stream` is turned off
- **No native function calling:** the app switches to prompted-JSON tool calls (`{"tool":…}` / `{"final":…}`) with the same registry and validation. `/api/health` reports this as `native_tools: false`.

## Checking on the server

With `PRODUCTION=True`, open `/api/health` after the first chat. `llm.native_tools`, `llm.stream`, `llm.developer_role`, `llm.max_tokens_param` and `llm.dropped_params` show what the gateway accepted. The mock LLM can reproduce each mode locally:
- `python -m tests.mock_llm --raw-harmony` for leaked harmony tokens
- `python -m tests.mock_llm --no-tools` for an endpoint without native function calling
