// Profile side panel behaviour with a fake DOM and a stubbed fetch (no browser, no server).
import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { installDom, flush, FakeNode } from "./fake_dom.mjs";

let env, app, asked, panel;
const { createProfilePanel } = await (async () => { installDom(); return import("../../static/js/panel.js"); })();
const { renderBlock } = await import("../../static/js/renderers.js");

const CHAT = "chat_test_1234";
const url = (id) => `/api/candidates/${id}/profile?chat_id=${CHAT}`;
const NAMES = { 11: "Alice Johnson", 22: "ريم تركي السبيعي", 33: "Pieter Jansen" };

function profile(id, name = NAMES[id]) {
  return {
    template: "candidate_profile", title: "Profile", actions: [{ label: "Interview questions", prompt: `Questions for ${id}` }],
    data: { candidate_id: id, ats_id: `A${id}`, full_name: name, skills: ["Excel", "SQL"], matched_skills: ["Excel"],
            missing_skills: ["Tableau"], experience: [], education: [], assessments: {}, criteria: [{ key: "skills", label: "Skills" }],
            score: 80, band: "Strong", breakdown: { skills: 0.8 }, total_experience: 5 },
  };
}

function rowEls(n) {
  return Array.from({ length: n }, () => { const r = new FakeNode("tr"); env.body.appendChild(r); return r; });
}

const heading = () => panel_el().find((n) => n.tagName === "H2");
const panel_el = () => app.find((n) => n.id === "profile-panel");
const pos = () => panel_el().byClass("panel-pos").textContent;
const btn = (label) => panel_el().find((n) => n.tagName === "BUTTON" && n.attributes["aria-label"] === label);

beforeEach(() => {
  env = installDom();
  for (const id of [11, 22, 33]) env.net.routes.set(url(id), { status: 200, body: profile(id) });
  app = new FakeNode("div");
  env.body.appendChild(app);
  asked = [];
  panel = createProfilePanel({ app, getChatId: () => CHAT, ask: (p) => asked.push(p) });
});

test("starts hidden and opens on the chosen candidate", async () => {
  assert.equal(panel_el().hidden, true);
  const rows = rowEls(3);
  panel.open([11, 22, 33], 1, rows);
  await flush();
  assert.equal(panel_el().hidden, false);
  assert.ok(app.classList.contains("panel-open"));
  assert.equal(env.net.calls[0], url(22));
  assert.equal(heading().textContent, NAMES[22]);
  assert.equal(pos(), "2 of 3");
  assert.ok(rows[1].classList.contains("is-open"));
  assert.equal(rows[1].getAttribute("aria-current"), "true");
  assert.ok(!rows[0].classList.contains("is-open"));
  assert.equal(rows[1].scrolledIntoView, 0, "a click never scrolls the chat: the row is already in view");
  assert.equal(env.doc.activeElement, heading(), "focus moves into the panel");
});

test("opening and closing keep the clicked row in the same place on screen", async () => {
  // Docking the panel narrows the chat, text re-wraps and the row moves down 140px: the chat scrolls by
  // exactly that much, without smooth animation, so the row stays where the user clicked it.
  const scroller = new FakeNode("div");
  scroller.scrollTop = 2000;
  scroller.style.scrollBehavior = "smooth";
  const behaviours = [];
  Object.defineProperty(scroller, "scrollTop", {
    get() { return this._st; }, set(v) { behaviours.push(this.style.scrollBehavior); this._st = v; }, configurable: true,
  });
  scroller._st = 2000;
  app = new FakeNode("div");                 // fresh container: one panel per page
  env.body.appendChild(app);
  const p = createProfilePanel({ app, scroller, getChatId: () => CHAT, ask: () => {} });
  const row = rowEls(1)[0];
  row.getBoundingClientRect = () => ({ top: app.classList.contains("panel-open") ? 440 : 300 });
  p.open([11], 0, [row]);
  await flush();
  assert.equal(scroller.scrollTop, 2140);
  assert.deepEqual(behaviours, ["auto"], "jump, not animate");
  assert.equal(scroller.style.scrollBehavior, "smooth", "smooth scrolling restored afterwards");
  p.close();
  assert.equal(scroller.scrollTop, 2000, "and back when the panel closes");
});

test("clicking another row while the panel is open does not scroll", async () => {
  const scroller = new FakeNode("div");
  scroller.scrollTop = 500;
  app = new FakeNode("div");                 // fresh container: one panel per page
  env.body.appendChild(app);
  const p = createProfilePanel({ app, scroller, getChatId: () => CHAT, ask: () => {} });
  const rows = rowEls(3);
  p.open([11, 22, 33], 0, rows);
  await flush();
  p.open([11, 22, 33], 2, rows);   // e.g. a row in an earlier answer, far up the chat
  await flush();
  assert.equal(heading().textContent, NAMES[33]);
  assert.equal(scroller.scrollTop, 500);
  assert.equal(rows[2].scrolledIntoView, 0);
});

test("arrow keys step through the list and move the highlight", async () => {
  const rows = rowEls(3);
  panel.open([11, 22, 33], 0, rows);
  await flush();
  assert.equal(btn("Previous candidate").disabled, true);
  env.doc.keydown("ArrowDown");
  await flush();
  assert.equal(heading().textContent, NAMES[22]);
  assert.ok(rows[1].classList.contains("is-open") && !rows[0].classList.contains("is-open"));
  assert.ok(rows[1].scrolledIntoView > 0, "stepping keeps the highlighted row in view");
  btn("Next candidate").click();
  await flush();
  assert.equal(heading().textContent, NAMES[33]);
  assert.equal(btn("Next candidate").disabled, true);
  env.doc.keydown("ArrowDown");   // at the end: nothing happens
  await flush();
  assert.equal(pos(), "3 of 3");
  env.doc.keydown("ArrowUp");
  await flush();
  assert.equal(heading().textContent, NAMES[22]);
});

test("neighbours are prefetched, so stepping needs no new request", async () => {
  panel.open([11, 22, 33], 0, []);
  await flush(); await flush();
  assert.deepEqual(env.net.calls.sort(), [url(11), url(22)].sort());
  env.doc.keydown("ArrowDown");
  await flush();
  assert.equal(heading().textContent, NAMES[22]);
  assert.equal(env.net.calls.filter((u) => u === url(22)).length, 1, "served from the cache");
});

test("a late response for a candidate you already left is ignored", async () => {
  env.net.manual = true;
  panel.open([11, 22], 0, []);
  env.doc.keydown("ArrowDown");               // leave 11 before it loaded (its request is aborted)
  const p22 = env.net.pending.find((p) => p.url === url(22));
  p22.resolve();
  await flush(); await flush();
  assert.equal(heading().textContent, NAMES[22]);
  const p11 = env.net.pending.find((p) => p.url === url(11));
  p11.resolve();                               // arrives late: must not replace the view
  await flush(); await flush();
  assert.equal(heading().textContent, NAMES[22]);
});

test("not found shows a message without retry; a server error offers retry", async () => {
  env.net.routes.set(url(11), { status: 404, body: {} });
  panel.open([11], 0, []);
  await flush();
  assert.match(panel_el().byClass("error-box").textContent, /not found/i);
  assert.equal(panel_el().byText("Try again"), null);
  assert.ok(!panel_el().byClass("panel-body").textContent.includes("null"), "no stray 'null' text");

  env.net.routes.set(url(22), { status: 500, body: {} });
  panel.open([22], 0, []);
  await flush();
  assert.match(panel_el().byClass("error-box").textContent, /HTTP 500/);
  env.net.routes.set(url(22), { status: 200, body: profile(22) });
  panel_el().byText("Try again").click();
  await flush();
  assert.equal(heading().textContent, NAMES[22]);
  assert.equal(panel_el().byClass("error-box"), null);
});

test("Escape closes, clears the highlight and returns focus", async () => {
  const rows = rowEls(2);
  rows[0].focus();
  panel.open([11, 22], 0, rows);
  await flush();
  env.doc.keydown("Escape");
  assert.equal(panel_el().hidden, true);
  assert.ok(!app.classList.contains("panel-open"));
  assert.ok(!rows[0].classList.contains("is-open"));
  assert.equal(rows[0].getAttribute("aria-current"), null);
  assert.equal(env.doc.activeElement, rows[0]);
  assert.equal(panel.isOpen, false);
  env.doc.keydown("ArrowDown");   // closed: keys do nothing
  assert.equal(panel_el().hidden, true);
});

test("arrow keys are ignored while typing in the composer", async () => {
  panel.open([11, 22], 0, []);
  await flush();
  const e = env.doc.keydown("ArrowDown", { tagName: "TEXTAREA" });
  await flush();
  assert.equal(e.defaultPrevented, false);
  assert.equal(pos(), "1 of 2");
});

test("Ask about this candidate sends a chat prompt; docked panel stays open", async () => {
  panel.open([11, 22], 1, []);
  await flush();
  panel_el().byText("Ask about this candidate").click();
  assert.equal(asked.length, 1);
  assert.ok(asked[0].includes(NAMES[22]) && asked[0].includes("#22"));
  assert.equal(panel_el().hidden, false);
});

test("in overlay mode (narrow screens) asking closes the panel", async () => {
  env.media.overlay = true;
  panel.open([11], 0, []);
  await flush();
  panel_el().byText("Interview questions").click();   // the block's own action chip
  assert.deepEqual(asked, ["Questions for 11"]);
  assert.equal(panel_el().hidden, true);
});

test("invalidate drops cached scores and reloads the open profile", async () => {
  panel.open([11], 0, []);
  await flush();
  env.net.routes.set(url(11), { status: 200, body: { ...profile(11), data: { ...profile(11).data, full_name: "Alice J. (rescored)" } } });
  panel.invalidate({ reload: true });
  await flush();
  assert.equal(env.net.calls.filter((u) => u === url(11)).length, 2);
  assert.equal(heading().textContent, "Alice J. (rescored)");
});

test("names are rendered as text, never as markup", async () => {
  const evil = '<img src=x onerror="alert(1)">';
  env.net.routes.set(url(11), { status: 200, body: profile(11, evil) });
  panel.open([11], 0, []);
  await flush();
  assert.equal(heading().textContent, evil);
  assert.equal(app.find((n) => n.tagName === "IMG"), null);
});

test("single candidate: no position label and no prev/next buttons", async () => {
  panel.open([11], 0, []);
  await flush();
  assert.equal(pos(), "");
  assert.equal(btn("Next candidate").hidden, true);
});

// ------------------------------------------------------------- renderer wiring (views -> panel)
const criteria = [{ key: "skills", label: "Skills" }];
const ranked = { template: "ranked_table", title: "Best", actions: [], data: { criteria, rows: [11, 22, 33].map((id, i) => ({
  rank: i + 1, candidate_id: id, full_name: NAMES[id], score: 90 - i, band: "Strong", breakdown: { skills: 0.9 },
  matched_skills: [], missing_skills: [], flags: [] })) } };

test("ranking rows open the panel with the whole list and the clicked index", () => {
  const calls = [];
  const el = renderBlock(ranked, { ask: () => assert.fail("should not ask"), openProfile: (...a) => calls.push(a) });
  const trs = el.findAll((n) => n.tagName === "TR" && n.attributes.tabindex === "0");
  trs[2].click();
  assert.deepEqual(calls[0][0], [11, 22, 33]);
  assert.equal(calls[0][1], 2);
  assert.equal(calls[0][2][2], trs[2], "row elements are passed for highlighting");
  trs[0].dispatch("keydown", { key: "Enter" });
  assert.equal(calls[1][1], 0);
});

test("without a panel (dev gallery) a row falls back to a chat prompt", () => {
  const asked2 = [];
  const el = renderBlock(ranked, { ask: (p) => asked2.push(p) });
  el.findAll((n) => n.tagName === "TR" && n.attributes.tabindex === "0")[1].click();
  assert.deepEqual(asked2, [`Show the full profile of ${NAMES[22]} (#22)`]);
});

test("comparison headers and candidate cards open the panel too", () => {
  const calls = [];
  const ctx = { ask: () => {}, openProfile: (...a) => calls.push(a) };
  const cmp = renderBlock({ template: "comparison_matrix", title: "C", actions: [], data: { criteria, candidates: [11, 22].map((id) => ({
    candidate_id: id, full_name: NAMES[id], score: 80, band: "Strong", breakdown: { skills: 0.8 }, matched_skills: [], missing_skills: [] })) } }, ctx);
  cmp.find((n) => n.tagName === "BUTTON" && n.textContent === NAMES[22]).click();
  assert.deepEqual(calls[0].slice(0, 2), [[11, 22], 1]);

  const cards = renderBlock({ template: "candidate_cards", title: "K", actions: [], data: { cards: [11, 33].map((id) => ({
    candidate_id: id, full_name: NAMES[id], skills: [], matched_skills: [], score: null })) } }, ctx);
  cards.findAll((n) => n.tagName === "BUTTON" && n.textContent === "View profile")[1].click();
  assert.deepEqual(calls[1].slice(0, 2), [[11, 33], 1]);
  assert.ok(calls[1][2][1].classList.contains("card"));
});
