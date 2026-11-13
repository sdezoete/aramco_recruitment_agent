// Recruitment Agent frontend: chat + SSE + rich blocks. Vanilla ES modules, no build step, no CDN.
import { h } from "./dom.js";
import { renderMarkdown } from "./markdown.js";
import { postSSE } from "./sse.js";
import { renderBlock } from "./renderers.js";
import { refreshCharts, clearCharts } from "./charts.js";
import { createProfilePanel } from "./panel.js";

const $ = (id) => document.getElementById(id);
const els = {
  app: $("app"), thread: $("thread"), scroller: $("scroller"), hero: $("hero"), input: $("input"), send: $("send"),
  composer: $("composer"), suggestions: $("suggestions"), promptList: $("prompt-list"), newChat: $("new-chat"),
  activeJob: $("active-job"), statusDot: $("status-dot"), statusText: $("status-text"), version: $("version"),
  theme: $("theme-toggle"), exportBtn: $("export-btn"), envBadge: $("env-badge"), title: $("topbar-title"),
  menu: $("menu-btn"),
};

const SUGGESTIONS = [
  ["Find the best candidates", "for the senior data scientist JD"],
  ["Who are the top business analysts?", "rank them against the business analyst JD"],
  ["Show me the skill supply", "as a chart across the whole pool"],
  ["Which job descriptions do we have?", "list the JDs and documents"],
];
const EXTRA_PROMPTS = [
  "Find candidates with Python and SQL and at least 4 years of experience",
  "Compare the top 3 candidates side by side",
  "Show the experience distribution of the pool",
  "Rank the pool for a structural engineer role",
];

// ------------------------------------------------------------------ storage helpers (never required)
const store = {
  get(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* ignore */ } },
};
const newId = () => (crypto.randomUUID ? crypto.randomUUID().replace(/-/g, "") : String(Date.now()) + Math.random().toString(36).slice(2));

let chatId = store.get("ra-chat-id") || newId();
store.set("ra-chat-id", chatId);
let busy = false;
let controller = null;

const panel = createProfilePanel({ app: els.app, scroller: els.scroller, getChatId: () => chatId, ask: (p) => ask(p) });
const viewCtx = { ask: (p) => ask(p), openProfile: (ids, i, srcEls) => panel.open(ids, i, srcEls) };

// ------------------------------------------------------------------ chat rendering
function scrollToEnd(force = false) {
  const s = els.scroller;
  const near = s.scrollHeight - s.scrollTop - s.clientHeight < 160;
  if (force || near) s.scrollTop = s.scrollHeight;
}

function addUser(text) {
  els.hero.hidden = true;
  els.thread.appendChild(h("div", { class: "msg msg-user" }, h("div", { class: "bubble", dir: "auto" }, text)));
  if (els.title.textContent === "New conversation") els.title.textContent = text.length > 70 ? text.slice(0, 70) + "…" : text;
  scrollToEnd(true);
}

// One assistant message = ordered segments (thinking, preamble, tools, text, blocks, notices).
class AssistantMessage {
  constructor() {
    this.body = h("div", { class: "msg-body" });
    this.el = h("div", { class: "msg msg-assistant" }, h("div", { class: "avatar", "aria-hidden": "true" }), this.body);
    els.thread.appendChild(this.el);
    this.text = null; this.textSrc = ""; this.tools = null; this.toolChips = {}; this.thinking = null;
    this.showThinking();
  }
  showThinking() {
    this.thinking = h("div", { class: "thinking" }, h("span", { class: "pulse" }), h("span", { class: "label" }, "Thinking…"));
    this.body.appendChild(this.thinking);
  }
  endThinking(seconds) {
    if (!this.thinking) return;
    if (seconds) {
      this.thinking.classList.add("done");
      this.thinking.querySelector(".label").textContent = `Thought for ${seconds}s`;
    } else {
      this.thinking.remove();
    }
    this.thinking = null;
  }
  appendText(t) {
    if (this.thinking && !this.thinking.classList.contains("done")) this.endThinking(0);
    if (!this.text) {
      this.text = h("div", { class: "md streaming" });
      this.body.appendChild(this.text);
      this.textSrc = "";
      this.tools = null;   // tool chips after this text start a new row below it
    }
    this.textSrc += t;
    this.text.replaceChildren(renderMarkdown(this.textSrc));
  }
  endSegment(kind) {
    if (!this.text) return;
    this.text.classList.remove("streaming");
    if (kind === "preamble") {
      const p = h("div", { class: "preamble" }, h("span", null, this.textSrc.trim()));
      this.text.replaceWith(p);
    }
    this.text = null; this.textSrc = "";
  }
  toolStart(d) {
    if (this.thinking && !this.thinking.classList.contains("done")) this.endThinking(0);
    if (!this.tools) { this.tools = h("div", { class: "tools" }); this.body.appendChild(this.tools); }
    const chip = h("span", { class: "tool-chip", title: d.name },
      h("span", { class: "spin" }), h("span", { class: "state" }, "✓"), h("span", null, d.label), h("span", { class: "summary" }));
    this.toolChips[d.id] = chip;
    this.tools.appendChild(chip);
  }
  toolEnd(d) {
    const chip = this.toolChips[d.id];
    if (!chip) return;
    chip.classList.add(d.ok ? "ok" : "err");
    if (!d.ok) chip.querySelector(".state").textContent = "!";
    chip.querySelector(".summary").textContent = d.summary ? `· ${d.summary}` : "";
    chip.title = `${chip.title} (${d.seconds}s)`;
  }
  block(b) {
    this.tools = null;   // next tool calls start a new chip row below the block
    this.body.appendChild(renderBlock(b, viewCtx));
    if (b.template === "ranked_table") enableExport();
    if (b.template === "jd_card") setActiveJob(b.data.title, b.data);
  }
  notice(m) { this.body.appendChild(h("div", { class: "notice" }, m)); }
  error(m) { this.endThinking(0); this.body.appendChild(h("div", { class: "error-box", role: "alert" }, m)); }
  done() {
    this.endThinking(0);
    if (this.text) this.endSegment("final");
  }
}

function setActiveJob(title, spec) {
  // replaceChildren() would render a null child as the text "null", so filter first.
  const parts = [h("strong", null, title || "Job spec")];
  if (spec && spec.required_skills) parts.push(h("span", { class: "muted" }, spec.required_skills.join(" · ") || "no required skills"));
  els.activeJob.replaceChildren(...parts);
}

function enableExport() {
  els.exportBtn.href = `/api/export/shortlist.csv?chat_id=${encodeURIComponent(chatId)}`;
  els.exportBtn.setAttribute("aria-disabled", "false");
}

// ------------------------------------------------------------------ sending
async function ask(text) {
  text = (text || "").trim();
  if (!text || busy) return;
  busy = true;
  els.send.disabled = true;
  els.input.value = "";
  autosize();
  closeMenu();
  panel.invalidate();   // this turn may change the active job, and so the scores in cached profiles
  addUser(text);
  const msg = new AssistantMessage();
  scrollToEnd(true);
  controller = new AbortController();
  try {
    await postSSE("/api/chat", { chat_id: chatId, message: text }, (ev, d) => {
      switch (ev) {
        case "thinking": if (d.state === "end") msg.endThinking(d.seconds); break;
        case "text_delta": msg.appendText(d.text); break;
        case "segment_end": msg.endSegment(d.kind); break;
        case "tool_start":
          msg.toolStart(d);
          break;
        case "tool_end":
          msg.toolEnd(d);
          if (d.ok && d.summary && msg.toolChips[d.id] && msg.toolChips[d.id].title.startsWith("set_job_spec")) setActiveJob(d.summary);
          break;
        case "ui_block": msg.block(d); break;
        case "notice": msg.notice(d.message); break;
        case "error": msg.error(d.message); break;
        case "done": msg.done(); break;
      }
      scrollToEnd();
    }, controller.signal);
  } catch (e) {
    msg.error(`Connection problem: ${e.message}`);
  } finally {
    msg.done();
    panel.invalidate({ reload: true });
    busy = false;
    els.send.disabled = false;
    els.input.focus();
    scrollToEnd();
  }
}

// ------------------------------------------------------------------ composer
function autosize() {
  els.input.style.height = "auto";
  els.input.style.height = Math.min(els.input.scrollHeight, 220) + "px";
}
els.input.addEventListener("input", autosize);
els.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); ask(els.input.value); }
});
els.composer.addEventListener("submit", (e) => { e.preventDefault(); ask(els.input.value); });

// ------------------------------------------------------------------ suggestions / new chat
function buildSuggestions() {
  els.suggestions.replaceChildren(...SUGGESTIONS.map(([a, b]) =>
    h("button", { class: "suggestion", type: "button", onclick: () => ask(`${a} ${b}`) }, h("b", null, a), h("span", null, b))));
  els.promptList.replaceChildren(...EXTRA_PROMPTS.map((p) => h("li", null, h("button", { type: "button", onclick: () => ask(p) }, p))));
}

async function newChat() {
  if (controller) controller.abort();
  panel.close();
  panel.invalidate();
  try { await fetch("/api/chat/reset", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ chat_id: chatId }) }); } catch (e) { /* offline */ }
  chatId = newId();
  store.set("ra-chat-id", chatId);
  clearCharts();
  els.thread.replaceChildren(els.hero);
  els.hero.hidden = false;
  els.title.textContent = "New conversation";
  els.activeJob.replaceChildren(h("span", { class: "muted" }, "None yet. Name a JD or describe the role."));
  els.exportBtn.setAttribute("aria-disabled", "true");
  els.exportBtn.href = "#";
  closeMenu();
  els.input.focus();
}
els.newChat.addEventListener("click", newChat);

// ------------------------------------------------------------------ theme
function currentTheme() {
  const t = document.documentElement.getAttribute("data-theme");
  if (t) return t;
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
els.theme.addEventListener("click", () => {
  const next = currentTheme() === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try { localStorage.setItem("ra-theme", next); } catch (e) { /* ignore */ }
  refreshCharts();
});
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => refreshCharts());

// ------------------------------------------------------------------ mobile menu
function closeMenu() { els.app.classList.remove("menu-open"); }
els.menu.addEventListener("click", () => els.app.classList.toggle("menu-open"));
els.thread.addEventListener("click", closeMenu);

// ------------------------------------------------------------------ status
async function loadMeta() {
  try {
    const m = await (await fetch("/api/meta")).json();
    els.version.textContent = `v${m.version}`;
    if (!m.production) { els.envBadge.hidden = false; els.envBadge.textContent = "Development"; }
    document.title = m.production ? `Recruitment Agent · ${m.display_name}` : "Recruitment Agent (dev)";
  } catch (e) { /* server down: status shows it */ }
}

async function checkHealth() {
  try {
    const hres = await (await fetch("/api/health")).json();
    const llm = hres.llm || {}, db = hres.db || {};
    const ok = llm.reachable && db.reachable;
    els.statusDot.className = "dot " + (ok ? "dot-ok" : "dot-bad");
    const parts = [];
    parts.push(llm.reachable ? `${llm.label}` : `Model unreachable: ${llm.detail || "unknown"}`);
    parts.push(db.reachable ? `DB ${db.database} · ${db.candidates} candidates` : "Database unreachable");
    if (llm.native_tools === false) parts.push("compatibility tool mode");
    els.statusText.replaceChildren(...parts.flatMap((p, i) => (i ? [h("br"), p] : [p])));
  } catch (e) {
    els.statusDot.className = "dot dot-bad";
    els.statusText.textContent = "Server unreachable";
  }
}

buildSuggestions();
loadMeta();
checkHealth();
setInterval(checkHealth, 60000);
els.input.focus();

// Deep link: /?q=<prompt> sends the prompt on load (bookmarks, demos).
const deepLink = new URLSearchParams(location.search).get("q");
if (deepLink) { history.replaceState(null, "", location.pathname); ask(deepLink); }
