// Minimal DOM stand-in for Node unit tests of the vanilla frontend modules (no jsdom: no extra dependency).
// Covers what static/js uses: createElement/TextNode/Fragment, children, attributes, classList, style,
// hidden, textContent, focus, isConnected, events, scrollIntoView, plus fetch and matchMedia stubs.

class ClassList {
  constructor(el) { this.el = el; }
  get set() { return new Set((this.el.className || "").split(/\s+/).filter(Boolean)); }
  contains(c) { return this.set.has(c); }
  add(...cs) { const s = this.set; cs.forEach((c) => s.add(c)); this.el.className = [...s].join(" "); }
  remove(...cs) { const s = this.set; cs.forEach((c) => s.delete(c)); this.el.className = [...s].join(" "); }
  toggle(c, force) { const on = force === undefined ? !this.contains(c) : force; on ? this.add(c) : this.remove(c); return on; }
}

export class FakeNode {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.childNodes = [];
    this.parentNode = null;
    this.attributes = {};
    this.style = { setProperty: (k, v) => { this.style[k] = v; } };
    this.className = "";
    this.classList = new ClassList(this);
    this.dataset = {};
    this.listeners = {};
    this.disabled = false;
    this.scrolledIntoView = 0;
    this.scrollTop = 0;
  }
  get firstChild() { return this.childNodes[0] || null; }
  get lastChild() { return this.childNodes[this.childNodes.length - 1] || null; }
  get children() { return this.childNodes.filter((c) => !(c instanceof FakeText)); }
  get hidden() { return "hidden" in this.attributes; }
  set hidden(v) { if (v) this.attributes.hidden = ""; else delete this.attributes.hidden; }
  get id() { return this.attributes.id || ""; }
  get isConnected() { let n = this; while (n) { if (n === globalThis.document.body) return true; n = n.parentNode; } return false; }
  get textContent() { return this.childNodes.map((c) => c.textContent).join(""); }
  set textContent(v) { this.replaceChildren(); if (v !== "" && v != null) this.appendChild(new FakeText(String(v))); }
  setAttribute(k, v) { if (k === "class") this.className = v; else this.attributes[k] = String(v); }
  getAttribute(k) { return k === "class" ? this.className : (k in this.attributes ? this.attributes[k] : null); }
  removeAttribute(k) { delete this.attributes[k]; }
  hasAttribute(k) { return k in this.attributes; }
  appendChild(c) {
    if (c.tagName === "#FRAGMENT") { [...c.childNodes].forEach((x) => this.appendChild(x)); return c; }
    if (c.parentNode) c.parentNode.removeChild(c);
    c.parentNode = this; this.childNodes.push(c); return c;
  }
  insertBefore(c, ref) {
    if (c.parentNode) c.parentNode.removeChild(c);
    const i = ref ? this.childNodes.indexOf(ref) : -1;
    c.parentNode = this;
    if (i < 0) this.childNodes.push(c); else this.childNodes.splice(i, 0, c);
    return c;
  }
  removeChild(c) { this.childNodes = this.childNodes.filter((x) => x !== c); c.parentNode = null; return c; }
  remove() { if (this.parentNode) this.parentNode.removeChild(this); }
  // like the real DOM: null/strings become text nodes ("null"), so tests catch that bug
  replaceChildren(...cs) { [...this.childNodes].forEach((c) => this.removeChild(c)); cs.forEach((c) => this.appendChild(c instanceof FakeNode ? c : new FakeText(String(c)))); }
  replaceWith(n) { const p = this.parentNode; if (!p) return; p.insertBefore(n, this); p.removeChild(this); }
  addEventListener(t, fn) { (this.listeners[t] ||= []).push(fn); }
  dispatch(t, ev = {}) {
    const e = { type: t, target: this, preventDefault() { this.defaultPrevented = true; }, ...ev };
    (this.listeners[t] || []).forEach((fn) => fn(e));
    return e;
  }
  click() { if (!this.disabled) this.dispatch("click"); }
  focus() { globalThis.document.activeElement = this; }
  scrollIntoView() { this.scrolledIntoView += 1; }
  /** Tests override this to simulate re-layout (e.g. the chat column narrowing when the panel docks). */
  getBoundingClientRect() { return { top: 0, left: 0, width: 0, height: 0 }; }
  /** Depth-first search helpers for assertions. */
  findAll(pred) { const out = []; const walk = (n) => { if (pred(n)) out.push(n); n.childNodes.forEach(walk); }; this.childNodes.forEach(walk); return out; }
  find(pred) { return this.findAll(pred)[0] || null; }
  byClass(c) { return this.find((n) => n.classList && n.classList.contains(c)); }
  /** Innermost element whose text is exactly t (a button, not the wrapper around it). */
  byText(t) { const all = this.findAll((n) => n.tagName !== "#TEXT" && n.childNodes.length && n.textContent.trim() === t); return all[all.length - 1] || null; }
}

export class FakeText extends FakeNode {
  constructor(s) { super("#text"); this.data = s; }
  get textContent() { return this.data; }
  set textContent(v) { this.data = String(v); }
}

/** Install globals. Returns helpers to control fetch and matchMedia from tests. */
export function installDom() {
  const body = new FakeNode("body");
  const docListeners = {};
  const doc = {
    body, activeElement: body, documentElement: new FakeNode("html"),
    createElement: (t) => new FakeNode(t),
    createElementNS: (_ns, t) => new FakeNode(t),
    createTextNode: (s) => new FakeText(s),
    createDocumentFragment: () => new FakeNode("#fragment"),
    addEventListener: (t, fn) => { (docListeners[t] ||= []).push(fn); },
    keydown(key, target = body, extra = {}) {
      const e = { key, target, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, ...extra };
      (docListeners.keydown || []).forEach((fn) => fn(e));
      return e;
    },
  };
  globalThis.document = doc;
  globalThis.Node = FakeNode;
  const media = { overlay: false };
  globalThis.window = { matchMedia: () => ({ matches: media.overlay }) };

  // fetch: tests register responses per URL; requests stay pending until resolved when `manual` is on
  const net = { calls: [], routes: new Map(), manual: false, pending: [] };
  globalThis.fetch = (url, opts = {}) => {
    net.calls.push(url);
    const respond = () => {
      const r = net.routes.get(url) || { status: 404, body: { detail: "not found" } };
      return { ok: r.status >= 200 && r.status < 300, status: r.status, json: async () => r.body };
    };
    if (!net.manual) return Promise.resolve(respond());
    return new Promise((resolve, reject) => {
      const p = { url, resolve: () => resolve(respond()), signal: opts.signal };
      if (opts.signal) opts.signal.addEventListener("abort", () => {
        const err = new Error("aborted"); err.name = "AbortError"; reject(err);
      });
      net.pending.push(p);
    });
  };
  return { body, doc, net, media };
}

/** Let pending promise callbacks run. */
export const flush = () => new Promise((r) => setTimeout(r, 0));
