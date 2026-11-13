# Response Templates (UI blocks)

Claude chooses a template through `render_view`. The server hydrates it into a **UI block**, sends it as an SSE `ui_block` event, and `static/js/renderers/<template>.js` renders it.

## Common envelope

```json
{
  "block_id": "blk_01",
  "template": "ranked_table",
  "title": "Top 5 for Senior Reservoir Engineer (JOB-1042)",
  "data": { ... template-specific ... },
  "actions": [ { "label": "Compare top 3", "prompt": "Compare the top 3 candidates" } ]
}
```

`actions` are suggested follow-ups that appear as clickable chips. A click sends `prompt` as the next user message.

## Templates

| template            | use when                                   | data shape (summary) |
|---------------------|--------------------------------------------|----------------------|
| `ranked_table`      | a shortlist with scores                    | `columns[]`, `rows[]: {candidate_id, name, score, breakdown, matched_skills, missing_skills}` |
| `candidate_cards`   | 1 to 6 candidates shown visually           | `cards[]: {id, name, title, years, location, score?, top_skills[], highlights[]}` |
| `candidate_profile` | full view of one candidate                 | header (location, hire type, status, ATS id), summary, skills, fit bars, experience timeline, education, assessment bars (0–100) |
| `comparison_matrix` | head-to-head comparison                    | `criteria[]`, `candidates[]`, `cells[criterion][candidate] = {score, note}` |
| `score_radar`       | visual comparison per criterion            | Chart.js radar: `labels[]`, `datasets[]: {label, data[]}` |
| `chart`             | analytics (funnel, distribution, mix)      | `chart_type`, `labels[]`, `datasets[]` |
| `jd_card`           | summary of a job description               | title, department, must-haves, nice-to-haves, weights |
| `document_hits`     | document search results                    | `hits[]: {doc_id, title, doc_type, snippet}` |
| `kpi_strip`         | headline numbers                           | `kpis[]: {label, value, delta?}` |

Plain chat text needs no template: Markdown in `text_delta` is rendered with a small, safe Markdown subset (headings, bold, italics, lists, inline code, pipe tables; no links). Tables are a fallback only: the prompt tells the model to show candidate/score data through `render_view`, and `compare_candidates` returns a `next` hint pointing at `comparison_matrix`. We do not use a raw-HTML Markdown renderer.

## Implementation notes

- All renderers live in `static/js/renderers.js` (one function per template). Charts go through `static/js/charts.js`, which uses the vendored Chart.js 4.4.7.
- Every chart has a **Chart / Table** toggle. Single-series charts use one hue and no legend. The radar shows at most 3 series (categorical slots 1–3 are colour-blind safe as a set) with a legend. Part-to-whole metrics (`*_mix`) are drawn as bars, not pies.
- Chart colours come from CSS role tokens and are rebuilt when the theme changes. Dark mode has its own selected values, not an automatic inversion.
- **Profile side panel (ADR-015):** clicking a candidate in `ranked_table` (row, or Enter on a focused row), `candidate_cards` ("View profile") or `comparison_matrix` (the name in the header) opens the profile in a panel next to the chat instead of sending a chat prompt. The panel fetches `GET /api/candidates/{id}/profile` and renders the same `candidate_profile` renderer through `renderContent()`. ↑/↓ (or j/k) and the arrow buttons step through the list the panel was opened from, and the matching row stays highlighted and in view. Esc closes the panel and returns focus. The panel docks as a third column at 1200px and wider, and floats over the chat below that. The page itself never scrolls. The chat and the panel each scroll on their own (one screen-high grid row; `tests/test_frontend_layout.py` guards it), so a profile opens beside whichever answer you clicked in, even far up the chat. A click never scrolls the chat. Docking and undocking re-wrap the chat, so the scroll position is corrected to keep the clicked row in the same place on screen (`keepInPlace`). Only ↑/↓ stepping brings the highlighted row into view. Neighbours are prefetched, and the cache is cleared on every chat turn, because the active job and so the scores may change. "Ask about this candidate" hands the candidate over to the chat. Renderers call `ctx.openProfile(ids, index, elements)` and fall back to `ctx.ask(...)` when the host page has no panel (the dev gallery). Code: `static/js/panel.js` (DOM) and `static/js/profile-nav.js` (logic, unit-tested).
- **Frontend tests:** `tests/js/*.test.mjs` run on Node's built-in test runner against a small fake DOM (`tests/js/fake_dom.mjs`, no jsdom). pytest runs them through `tests/test_frontend_js.py`, which skips them when `node` is not installed. Node is a dev-only tool and is never shipped.
- **Dev gallery:** `/dev/gallery` (404 when `PRODUCTION=True`) renders every template from the local DB with a sample JD. Use it after changing a renderer or the CSS. `?theme=dark` and `?doc=jd_business_analyst` are supported.

## Design language ("very fancy", but readable)

- Dark and light themes using CSS custom properties on `:root`, following `prefers-color-scheme`, with a manual toggle.
- Cards with soft elevation. Score shown as a ring or pill, colored by band (≥85 excellent, 70–84 strong, 50–69 partial, <50 weak).
- Skill chips: green when matched, muted when missing, outlined when preferred.
- Blocks animate in as they arrive (fade and slide, kept subtle). Respect `prefers-reduced-motion`.
- Responsive: tables switch to stacked cards below 640px.
- Chart colors come from one shared palette defined in CSS variables, so charts match the theme.

## Adding a template

1. Add a row above and document the data shape.
2. Add the hydration function in `app/tools/render.py`.
3. Add `static/js/renderers/<template>.js` exporting `render(block) -> HTMLElement`. Build the DOM with `textContent`, not `innerHTML`.
4. Add the template to the `render_view` enum in the registry.
