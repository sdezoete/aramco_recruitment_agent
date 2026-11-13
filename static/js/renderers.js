// UI block renderers: pure render(block, ctx) -> HTMLElement (docs/RESPONSE_TEMPLATES.md).
// ctx.ask(prompt) sends a follow-up message. All text goes through text nodes.
import { h, svgIcon, pct, fmtYears, initials } from "./dom.js";
import { barChart, lineChart, radarChart, legend, dataTable, chartWithTable } from "./charts.js";

const KIND = {
  ranked_table: "Ranking", candidate_cards: "Candidates", candidate_profile: "Profile",
  comparison_matrix: "Comparison", score_radar: "Comparison", chart: "Chart", jd_card: "Job spec",
  document_hits: "Documents", kpi_strip: "Summary",
};

function ring(score, lg = false) {
  return h("div", { class: "ring" + (lg ? " lg" : ""), vars: { "--p": String(score ?? 0) },
                    role: "img", "aria-label": `Score ${score} out of 100` },
    h("span", null, score === null || score === undefined ? "–" : Math.round(score)));
}

function skillChips(all, matched = [], missing = []) {
  const hit = new Set(matched.map((s) => s.toLowerCase()));
  const chips = [];
  for (const s of matched) chips.push(h("span", { class: "chip hit" }, s));
  for (const s of all || []) if (!hit.has(s.toLowerCase())) chips.push(h("span", { class: "chip" }, s));
  for (const s of missing) chips.push(h("span", { class: "chip miss", title: "Required, missing" }, s));
  return h("div", { class: "chips" }, chips);
}

const FLAG_TEXT = {
  below_min_years: "Below minimum years", no_assessment: "No assessment scores",
  hire_type_mismatch: "Hire type differs from requisition", location_mismatch: "Other location",
  status_not_open: "Status not open for matching", below_min_gpa: "Below minimum GPA",
};

function flagChips(flags = []) {
  const text = (f) => f.startsWith("missing_must_have:") ? `Missing must-have: ${f.split(":")[1]}` : (FLAG_TEXT[f] || f);
  return flags.length ? h("div", { class: "chips" }, flags.map((f) => h("span", { class: "chip flag" }, "⚠ " + text(f)))) : null;
}

function miniBars(breakdown, criteria) {
  return h("div", { class: "minibars", role: "img",
                    "aria-label": criteria.map((c) => `${c.label} ${pct(breakdown[c.key])}%`).join(", ") },
    criteria.map((c) => h("div", { class: "minibar", title: `${c.label}: ${pct(breakdown[c.key])}%` },
      h("i", { style: { height: `${pct(breakdown[c.key])}%` } }))));
}

function barRows(breakdown, criteria) {
  return criteria.map((c) => h("div", { class: "bar-row" },
    h("span", null, c.label),
    h("div", { class: "bar-track" }, h("i", { style: { width: `${pct(breakdown[c.key])}%` } })),
    h("span", { class: "val" }, `${pct(breakdown[c.key])}%`)));
}

// Open a profile: the side panel when the host page has one (ctx.openProfile), else a chat prompt.
// people: [{candidate_id, full_name}] in view order; els: the matching elements to highlight (optional).
function openProfile(ctx, people, i, els = []) {
  const p = people[i];
  if (ctx.openProfile) ctx.openProfile(people.map((x) => x.candidate_id), i, els);
  else ctx.ask(`Show the full profile of ${p.full_name} (#${p.candidate_id})`);
}

// ----------------------------------------------------------------------------- templates
const R = {};

R.ranked_table = (b, ctx) => {
  const d = b.data;
  const crit = d.criteria;
  const rows = [];
  const table = h("table", { class: "rtable" },
    h("thead", null, h("tr", null,
      h("th", null, "#"), h("th", null, "Candidate"), h("th", null, "Score"),
      h("th", null, h("span", { title: crit.map((c) => c.label).join(" · ") }, "Breakdown")),
      h("th", null, "Skills"))),
    h("tbody", null, d.rows.map((r, i) => {
      const tr = h("tr", {
        tabindex: "0", title: "Open profile",
        onclick: () => openProfile(ctx, d.rows, i, rows),
        onkeydown: (e) => { if (e.key === "Enter") openProfile(ctx, d.rows, i, rows); },
      },
        h("td", null, h("div", { class: "rank" + (r.rank === 1 ? " r1" : "") }, r.rank)),
        h("td", { class: "who" }, h("b", { dir: "auto" }, r.full_name), h("small", { dir: "auto" },
          [r.last_job_title, fmtYears(r.total_experience), r.location].filter(Boolean).join(" · "))),
        h("td", null, h("div", { class: "score-cell" }, ring(r.score), h("span", { class: "band" }, r.band))),
        h("td", null, miniBars(r.breakdown, crit)),
        h("td", null, skillChips([], r.matched_skills, r.missing_skills), flagChips(r.flags)));
      rows.push(tr);
      return tr;
    })));
  return { body: table, flush: true };
};

R.candidate_cards = (b, ctx) => {
  const cards = b.data.cards;
  const cardEls = [];
  const card = (c, i) => h("article", { class: "card" },
    h("div", { class: "card-top" },
      h("div", { class: "initials", "aria-hidden": "true" }, initials(c.full_name)),
      h("div", { class: "grow" }, h("div", { class: "card-name", dir: "auto" }, c.full_name),
        h("div", { class: "card-sub", dir: "auto" }, [c.last_job_title, c.last_company].filter(Boolean).join(" @ "))),
      c.score !== null && c.score !== undefined ? ring(c.score) : null),
    h("div", { class: "card-meta" },
      c.location ? h("span", null, "📍 ", c.location) : null,
      c.hire_type ? h("span", null, c.hire_type) : null,
      h("span", null, "⏱ ", fmtYears(c.total_experience)),
      c.highest_degree ? h("span", { dir: "auto" }, "🎓 ", [c.highest_degree, c.primary_major].filter(Boolean).join(", ")) : null,
      c.application_status ? h("span", null, "Status: ", c.application_status) : null),
    c.summary ? h("p", { class: "card-summary", dir: "auto" }, c.summary) : null,
    skillChips(c.skills.filter((s) => !(c.matched_skills || []).includes(s)), c.matched_skills || []),
    h("button", { class: "btn", type: "button", onclick: () => openProfile(ctx, cards, i, cardEls) }, "View profile"));
  cards.forEach((c, i) => cardEls.push(card(c, i)));
  return { body: h("div", { class: "cards" }, cardEls) };
};

const ASSESS = [["inductive", "Inductive reasoning"], ["numerical", "Numerical reasoning"], ["verbal", "Verbal reasoning"]];

function assessmentRows(a = {}) {
  const have = ASSESS.filter(([k]) => typeof a[k] === "number");
  if (!have.length) return h("p", { class: "muted" }, "No assessment scores on file.");
  return ASSESS.map(([k, label]) => h("div", { class: "bar-row" },
    h("span", null, label),
    h("div", { class: "bar-track" }, typeof a[k] === "number" ? h("i", { style: { width: `${a[k]}%` } }) : null),
    h("span", { class: "val" }, typeof a[k] === "number" ? String(a[k]) : "–")));
}

R.candidate_profile = (b) => {
  const p = b.data;
  const head = h("div", { class: "profile-head" },
    p.score !== null && p.score !== undefined ? ring(p.score, true) : h("div", { class: "initials" }, initials(p.full_name)),
    h("div", null, h("h3", { dir: "auto" }, p.full_name),
      h("div", { class: "card-sub", dir: "auto" }, [p.last_job_title, p.last_company].filter(Boolean).join(" · ")),
      h("div", { class: "card-meta" }, h("span", null, fmtYears(p.total_experience)),
        p.highest_degree ? h("span", { dir: "auto" }, [p.highest_degree, p.primary_major].filter(Boolean).join(", ")) : null,
        p.location ? h("span", null, "📍 ", p.location) : null,
        p.hire_type ? h("span", null, p.hire_type) : null,
        p.application_status ? h("span", null, "Status: ", p.application_status, p.pipeline_stage ? ` (${p.pipeline_stage})` : "") : null,
        p.ats_id ? h("span", { class: "muted" }, `ATS ${p.ats_id}`) : null,
        p.band ? h("span", { class: "band" }, p.band + " match") : null)));
  const left = h("div", null,
    p.summary ? h("p", { class: "card-summary", dir: "auto" }, p.summary) : null,
    h("h4", null, "Skills"), skillChips(p.skills.filter((s) => !p.matched_skills.includes(s)), p.matched_skills, p.missing_skills),
    p.breakdown ? [h("h4", { style: { marginTop: "14px" } }, "Fit for the active job"), barRows(p.breakdown, p.criteria)] : null);
  const right = h("div", null,
    h("h4", null, "Experience"),
    p.experience.length ? h("ul", { class: "timeline" }, p.experience.map((e) => h("li", null,
      h("b", { dir: "auto" }, e.job_title || "Role"), h("small", { dir: "auto" },
        [e.company, e.location, [e.start, e.end].filter(Boolean).join(" – "), fmtYears(e.years_experience)].filter(Boolean).join(" · "))))) : h("p", { class: "muted" }, "No experience records."),
    h("h4", { style: { marginTop: "14px" } }, "Education"),
    p.education.length ? h("ul", { class: "plain-list" }, p.education.map((e) =>
      h("li", { dir: "auto" }, [e.degree, e.major].filter(Boolean).join(", "), e.institute ? ` · ${e.institute}` : "", e.end ? ` · ${e.end}` : ""))) : h("p", { class: "muted" }, "None recorded."),
    p.gpa ? h("p", { class: "muted" }, `GPA ${Number(p.gpa).toFixed(2)} / 4`) : null,
    h("h4", { style: { marginTop: "14px" } }, "Assessments (0–100)"),
    assessmentRows(p.assessments));
  return { body: [head, h("div", { class: "profile-grid" }, left, right)] };
};

R.comparison_matrix = (b, ctx) => {
  const { criteria, candidates } = b.data;
  const heads = [];
  const nameHead = (c, i) => {
    const th = h("th", { dir: "auto" },
      h("button", { class: "linkish", type: "button", title: "Open profile", onclick: () => openProfile(ctx, candidates, i, heads) },
        c.full_name),
      h("div", { class: "band" }, `#${c.candidate_id}`));
    heads.push(th);
    return th;
  };
  const best = {};
  for (const c of criteria) best[c.key] = Math.max(...candidates.map((x) => x.breakdown[c.key]));
  const cell = (v, isBest) => h("td", { class: isBest ? "best" : null },
    h("div", { class: "cell-val" }, h("div", { class: "bar-track" }, h("i", { style: { width: `${pct(v)}%` } })),
      h("span", null, `${pct(v)}%`), isBest ? h("span", { class: "sr-only" }, "(best)") : null));
  const table = h("table", { class: "matrix" },
    h("thead", null, h("tr", null, h("th", null, ""), candidates.map(nameHead))),
    h("tbody", null,
      h("tr", null, h("th", null, "Overall score"), candidates.map((c) => h("td", null, h("div", { class: "score-cell" }, ring(c.score), h("span", { class: "band" }, c.band))))),
      criteria.map((cr) => h("tr", null, h("th", null, cr.label),
        candidates.map((c) => cell(c.breakdown[cr.key], candidates.length > 1 && c.breakdown[cr.key] === best[cr.key])))),
      h("tr", null, h("th", null, "Missing skills"), candidates.map((c) => h("td", null,
        c.missing_skills.length ? skillChips([], [], c.missing_skills) : h("span", { class: "muted" }, "none"))))));
  return { body: h("div", { style: { overflowX: "auto" } }, table), flush: true };
};

R.score_radar = (b) => {
  const { criteria, candidates } = b.data;
  const shown = candidates.slice(0, 3);
  const labels = criteria.map((c) => c.label);
  const series = shown.map((c) => ({ label: c.full_name, values: criteria.map((cr) => pct(c.breakdown[cr.key])) }));
  const table = dataTable(["Criterion", ...shown.map((c) => c.full_name)],
    criteria.map((cr) => [cr.label, ...shown.map((c) => `${pct(c.breakdown[cr.key])}%`)]));
  const { toggle, body } = chartWithTable((box) => radarChart(box, { labels, series }), table);
  const note = candidates.length > 3 ? h("p", { class: "muted" }, `Showing the first 3 of ${candidates.length}. Use the comparison table for more.`) : null;
  return { tools: toggle, body: [legend(shown.map((c) => c.full_name)), ...body, note] };
};

R.chart = (b) => {
  const d = b.data;
  const valueLabel = d.metric === "shortlist_scores" ? "Score" : "Candidates";
  const table = dataTable(["Category", valueLabel], d.labels.map((l, i) => [l, d.values[i]]));
  const draw = (box) => d.chart_type === "line"
    ? lineChart(box, { labels: d.labels, values: d.values, valueLabel })
    : barChart(box, { labels: d.labels, values: d.values, valueLabel });   // part-to-whole shown as bars too
  const { toggle, body } = chartWithTable(draw, table);
  return { tools: toggle, body };
};

R.jd_card = (b) => {
  const d = b.data;
  const fact = (label, value) => h("div", { class: "jd-fact" }, h("small", null, label), h("b", null, value));
  const section = (title, items, cls) => items && items.length
    ? h("div", { class: "jd-section" }, h("h4", null, title), h("div", { class: "chips" }, items.map((s) => h("span", { class: "chip " + (cls || "") }, s))))
    : null;
  const weights = Object.entries(d.weights || {}).map(([k, v]) => ({ key: k, label: k[0].toUpperCase() + k.slice(1) }));
  return { body: [
    h("div", { class: "jd-grid" }, fact("Role", d.title || "–"), fact("Minimum experience", d.min_years ? `${d.min_years} yrs` : "Any"),
      fact("Minimum degree", d.degree || "Any"), fact("Hire type", d.hire_type_label || "Any"),
      d.min_gpa ? fact("Minimum GPA", `${d.min_gpa} / 4`) : null,
      fact("Locations", d.locations && d.locations.length ? d.locations.join(", ") : "Any")),
    section("Required skills", d.required_skills, "hit"),
    section("Preferred skills", d.preferred_skills),
    section("Majors", d.majors),
    section("Not in candidate data (can't be scored)", d.unmapped_skills, "miss"),
    h("div", { class: "jd-section" }, h("h4", null, "Scoring weights"), barRows(d.weights || {}, weights)),
    d.doc_title ? h("p", { class: "muted" }, `Source: ${d.doc_title}`) : null,
  ] };
};

R.document_hits = (b, ctx) => ({
  body: b.data.docs.length ? h("ul", { class: "doc-list" }, b.data.docs.map((d) => h("li", null,
    h("div", { class: "doc-icon" }, svgIcon(["M7 3h7l5 5v13H7z", "M14 3v5h5", "M10 13h6M10 17h6"])),
    h("div", { class: "grow" }, h("div", null, d.title), h("div", { class: "doc-type" }, `${d.doc_type.replace("_", " ")} · ${d.format}`)),
    d.doc_type === "jd" ? h("button", { class: "btn", type: "button", onclick: () => ctx.ask(`Find the best candidates for ${d.doc_id}`) }, "Find candidates") : null)))
    : h("p", { class: "muted" }, "No documents found."),
});

R.kpi_strip = (b) => ({
  body: h("div", { class: "kpis" }, b.data.kpis.map((k) => h("div", { class: "kpi" }, h("small", null, k.label), h("b", null, String(k.value))))),
});

function renderParts(block, ctx) {
  const fn = R[block.template];
  try {
    return fn ? fn(block, ctx) : { body: h("pre", null, JSON.stringify(block.data, null, 2)) };
  } catch (e) {
    console.error(e);
    return { body: h("p", { class: "muted" }, "This view could not be displayed.") };
  }
}

const actionChips = (block, ctx) => block.actions && block.actions.length
  ? h("div", { class: "block-actions" }, block.actions.map((a) =>
      h("button", { class: "action-chip", type: "button", onclick: () => ctx.ask(a.prompt) }, a.label)))
  : null;

export function renderBlock(block, ctx) {
  const head = h("div", { class: "block-head" },
    h("div", { class: "block-title" }, block.title || ""), null, h("span", { class: "block-kind" }, KIND[block.template] || block.template));
  const out = renderParts(block, ctx);
  if (out.tools) head.insertBefore(out.tools, head.lastChild);
  return h("section", { class: "block", "data-template": block.template },
    head, h("div", { class: "block-body" + (out.flush ? " flush" : "") }, out.body), actionChips(block, ctx));
}

/** A block's content without the card frame (used by the profile side panel). */
export function renderContent(block, ctx) {
  const out = renderParts(block, ctx);
  return h("div", { class: "panel-content", "data-template": block.template }, out.body, actionChips(block, ctx));
}
