// Profile side panel (ADR-015): opens a candidate profile next to the chat, without an LLM round trip.
// The block comes from GET /api/candidates/{id}/profile (server-hydrated, same renderer as in the chat).
import { h, svgIcon } from "./dom.js";
import { renderContent } from "./renderers.js";
import { ProfileNav, BlockCache, navAction, profileUrl } from "./profile-nav.js";

const OVERLAY = "(max-width: 1199px)";   // below this the panel floats over the chat instead of docking

/**
 * Run a layout change (panel docks or undocks, so the chat column changes width and its text re-wraps)
 * without moving `anchor` on screen: the chat's scroll position is corrected by however far it moved.
 */
export function keepInPlace(scroller, anchor, change) {
  if (!scroller || !anchor || !anchor.isConnected) { change(); return; }
  const before = anchor.getBoundingClientRect().top;
  change();
  const delta = anchor.getBoundingClientRect().top - before;   // reading the rect forces the re-layout now
  if (!delta) return;
  const behavior = scroller.style.scrollBehavior;
  scroller.style.scrollBehavior = "auto";                       // jump, don't animate (.scroller is smooth)
  scroller.scrollTop += delta;
  scroller.style.scrollBehavior = behavior;
}

export function createProfilePanel({ app, scroller = null, getChatId, ask }) {
  const cache = new BlockCache();
  let nav = null, sources = [], returnFocus = null, seq = 0, inflight = null;

  const pos = h("span", { class: "panel-pos", "aria-live": "polite" });
  const prevBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Previous candidate", title: "Previous (↑)",
    onclick: () => step("prev") }, svgIcon("M6 15l6-6 6 6"));
  const nextBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Next candidate", title: "Next (↓)",
    onclick: () => step("next") }, svgIcon("M6 9l6 6 6-6"));
  const closeBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Close profile", title: "Close (Esc)",
    onclick: () => close() }, svgIcon("M6 6l12 12M18 6L6 18"));
  const heading = h("h2", { class: "panel-title", id: "profile-panel-title", tabindex: "-1" }, "Candidate profile");
  const body = h("div", { class: "panel-body" });
  const askBtn = h("button", { class: "btn btn-primary", type: "button", onclick: () => askAbout() }, "Ask about this candidate");
  const foot = h("div", { class: "panel-foot" }, askBtn);
  const el = h("aside", { class: "profile-panel", id: "profile-panel", role: "dialog", "aria-modal": "false",
                          "aria-labelledby": "profile-panel-title", hidden: true },
    h("div", { class: "panel-head" }, heading, pos, h("div", { class: "panel-nav" }, prevBtn, nextBtn, closeBtn)),
    body, foot);
  app.appendChild(el);

  // ---------------------------------------------------------------- state -> DOM
  // Highlight the open candidate in the view it came from. Only when stepping (↑/↓) is the row brought
  // into view; a click never scrolls the chat, since the row is already where the user is looking.
  function markSource(reveal = false) {
    sources.forEach((s, i) => {
      if (!s) return;
      const on = nav && i === nav.index;
      s.classList.toggle("is-open", on);
      if (on) s.setAttribute("aria-current", "true"); else s.removeAttribute("aria-current");
    });
    const cur = nav && sources[nav.index];
    if (reveal && cur && cur.isConnected) cur.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function updateNav() {
    pos.textContent = nav ? nav.label : "";
    prevBtn.disabled = !nav || !nav.hasPrev;
    nextBtn.disabled = !nav || !nav.hasNext;
    prevBtn.hidden = nextBtn.hidden = !nav || nav.ids.length < 2;
  }

  function showBlock(block) {
    const name = block.data && block.data.full_name;
    heading.textContent = name || "Candidate profile";
    heading.setAttribute("dir", "auto");
    body.classList.remove("loading");
    body.replaceChildren(renderContent(block, { ask: askAndMaybeClose }));
    body.scrollTop = 0;
    askBtn.disabled = false;
  }

  function showError(message, retry) {
    body.classList.remove("loading");
    // replaceChildren(null) would render the text "null", so only pass real nodes
    const parts = [h("div", { class: "error-box", role: "alert" }, message)];
    if (retry) parts.push(h("button", { class: "btn", type: "button", style: { marginTop: "12px" }, onclick: retry }, "Try again"));
    body.replaceChildren(...parts);
    askBtn.disabled = true;
  }

  // ---------------------------------------------------------------- data
  async function fetchBlock(chatId, id, signal) {
    const res = await fetch(profileUrl(chatId, id), { signal, headers: { Accept: "application/json" } });
    if (res.status === 404) throw Object.assign(new Error("This candidate was not found."), { final: true });
    if (!res.ok) throw new Error(`Could not load the profile (HTTP ${res.status}).`);
    return res.json();
  }

  async function load({ reveal = false } = {}) {
    if (!nav) return;
    const chatId = getChatId(), id = nav.current, mine = ++seq;
    updateNav();
    markSource(reveal);
    const hit = cache.get(chatId, id);
    if (hit) { showBlock(hit); prefetch(); return; }
    if (inflight) inflight.abort();
    inflight = new AbortController();
    body.classList.add("loading");
    if (!body.firstChild) body.appendChild(h("p", { class: "muted" }, "Loading profile…"));
    try {
      const block = await fetchBlock(chatId, id, inflight.signal);
      cache.set(chatId, id, block);
      if (mine === seq && nav && nav.current === id) { showBlock(block); prefetch(); }
    } catch (e) {
      if (e.name === "AbortError" || mine !== seq) return;
      showError(e.message, e.final ? null : () => load());
    }
  }

  function prefetch() {
    if (!nav) return;
    const chatId = getChatId();
    for (const id of nav.neighbours()) {
      if (cache.get(chatId, id) !== undefined) continue;
      fetchBlock(chatId, id).then((b) => cache.set(chatId, id, b)).catch(() => { /* loaded on demand instead */ });
    }
  }

  // ---------------------------------------------------------------- actions
  function open(ids, index = 0, sourceEls = []) {
    const opener = document.activeElement;
    try { nav = new ProfileNav(ids, index); } catch (e) { return; }
    clearSources();
    sources = sourceEls || [];
    if (el.hidden) returnFocus = opener;
    keepInPlace(scroller, sources[nav.index], () => {
      el.hidden = false;
      app.classList.add("panel-open");
    });
    load();
    heading.focus({ preventScroll: true });
  }

  function step(dir) {
    if (!nav) return;
    const before = nav.current;
    if ((dir === "next" ? nav.next() : nav.prev()) !== before) load({ reveal: true });
  }

  function close() {
    if (el.hidden) return;
    if (inflight) inflight.abort();
    seq++;
    keepInPlace(scroller, nav && sources[nav.index], () => {
      el.hidden = true;
      app.classList.remove("panel-open");
    });
    clearSources();
    nav = null;
    body.replaceChildren();
    if (returnFocus && returnFocus.isConnected) returnFocus.focus({ preventScroll: true });
    returnFocus = null;
  }

  function clearSources() {
    sources.forEach((s) => { if (s) { s.classList.remove("is-open"); s.removeAttribute("aria-current"); } });
    sources = [];
  }

  function isOverlay() { return window.matchMedia(OVERLAY).matches; }

  function askAndMaybeClose(prompt) {
    if (isOverlay()) close();
    ask(prompt);
  }

  function askAbout() {
    if (!nav) return;
    const name = heading.textContent;
    askAndMaybeClose(`Tell me about ${name} (#${nav.current}): strengths and gaps for the active job`);
  }

  /** The active job may have changed (new chat turn): drop cached scores and reload what is open. */
  function invalidate({ reload = false } = {}) {
    cache.clear();
    if (reload && nav) load();
  }

  document.addEventListener("keydown", (e) => {
    if (el.hidden) return;
    const action = navAction(e);
    if (!action) return;
    e.preventDefault();
    if (action === "close") close(); else step(action);
  });

  return { open, close, invalidate, get isOpen() { return !el.hidden; } };
}
