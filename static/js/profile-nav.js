// Profile panel logic without DOM (unit-tested in tests/js/): which candidate is open, stepping through
// the list it was opened from, the keyboard map, and a small cache of fetched profile blocks.

const MAX_ID = 2147483647;

/** Candidate ids as positive ints, in order, without duplicates or junk. */
export function cleanIds(ids) {
  const seen = new Set();
  const out = [];
  for (const raw of ids || []) {
    const n = Number(raw);
    if (!Number.isInteger(n) || n <= 0 || n > MAX_ID || seen.has(n)) continue;
    seen.add(n);
    out.push(n);
  }
  return out;
}

/** Position in the list a profile was opened from (ranking rows, cards, comparison columns). */
export class ProfileNav {
  constructor(ids, index = 0) {
    this.ids = cleanIds(ids);
    if (!this.ids.length) throw new Error("ProfileNav needs at least one candidate id");
    const i = Number.isInteger(index) ? index : 0;
    this.index = Math.min(Math.max(i, 0), this.ids.length - 1);
  }
  get current() { return this.ids[this.index]; }
  get hasPrev() { return this.index > 0; }
  get hasNext() { return this.index < this.ids.length - 1; }
  get label() { return this.ids.length > 1 ? `${this.index + 1} of ${this.ids.length}` : ""; }
  next() { if (this.hasNext) this.index += 1; return this.current; }
  prev() { if (this.hasPrev) this.index -= 1; return this.current; }
  /** Jump to a candidate already in the list; returns false if it isn't there. */
  goTo(id) {
    const i = this.ids.indexOf(Number(id));
    if (i < 0) return false;
    this.index = i;
    return true;
  }
  /** Ids worth prefetching after the current one loads. */
  neighbours() {
    return [this.hasNext ? this.ids[this.index + 1] : null, this.hasPrev ? this.ids[this.index - 1] : null]
      .filter((x) => x !== null);
  }
}

const EDITABLE = new Set(["INPUT", "TEXTAREA", "SELECT"]);

/**
 * Keyboard action while the panel is open: "next", "prev", "close" or null.
 * Arrow keys are left alone while the user types (composer, inputs) or holds a modifier.
 */
export function navAction(e) {
  if (!e || e.isComposing || e.altKey || e.ctrlKey || e.metaKey) return null;
  if (e.key === "Escape") return "close";
  const t = e.target || {};
  if (EDITABLE.has(String(t.tagName || "").toUpperCase()) || t.isContentEditable) return null;
  if (e.key === "ArrowDown" || e.key === "j") return "next";
  if (e.key === "ArrowUp" || e.key === "k") return "prev";
  return null;
}

/** Small LRU of profile blocks per chat. Cleared whenever a chat turn may have changed the active job. */
export class BlockCache {
  constructor(max = 40) { this.max = max; this.map = new Map(); }
  key(chatId, id) { return `${chatId}:${id}`; }
  get(chatId, id) {
    const k = this.key(chatId, id);
    if (!this.map.has(k)) return undefined;
    const v = this.map.get(k);
    this.map.delete(k);
    this.map.set(k, v);
    return v;
  }
  set(chatId, id, block) {
    const k = this.key(chatId, id);
    this.map.delete(k);
    this.map.set(k, block);
    while (this.map.size > this.max) this.map.delete(this.map.keys().next().value);
  }
  clear() { this.map.clear(); }
  get size() { return this.map.size; }
}

export function profileUrl(chatId, id) {
  return `/api/candidates/${encodeURIComponent(id)}/profile?chat_id=${encodeURIComponent(chatId)}`;
}
