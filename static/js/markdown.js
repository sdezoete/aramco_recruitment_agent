// Small, safe Markdown subset -> DOM: headings, paragraphs, bullet/numbered lists, pipe tables,
// **bold**, *italic*, `code`. No raw HTML and no links: everything becomes text nodes.
import { h } from "./dom.js";

function inline(text) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*|_[^_\s][^_]*_)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0];
    if (t.startsWith("**")) out.push(h("strong", null, t.slice(2, -2)));
    else if (t.startsWith("`")) out.push(h("code", null, t.slice(1, -1)));
    else out.push(h("em", null, t.slice(1, -1)));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

// --- pipe tables (GitHub style): header row, separator row (|---|:--:|), body rows
const SEP = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;
const isRow = (line) => /^\s*\|.*\|\s*$/.test(line) || (line.includes("|") && !SEP.test(line) && /\S\s*\|\s*\S/.test(line));

function cells(line) {
  let s = line.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|") && !s.endsWith("\\|")) s = s.slice(0, -1);
  return s.split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, "|"));
}

function align(spec) {
  const l = spec.startsWith(":"), r = spec.endsWith(":");
  return l && r ? "center" : r ? "right" : l ? "left" : null;
}

function table(headLine, sepLine, bodyLines) {
  const head = cells(headLine);
  const aligns = cells(sepLine).map(align);
  const cell = (tag, text, i) => {
    const el = h(tag, { dir: "auto" }, inline(text));
    if (aligns[i]) el.style.textAlign = aligns[i];
    return el;
  };
  const thead = h("thead", null, h("tr", null, head.map((t, i) => cell("th", t, i))));
  const tbody = h("tbody", null, bodyLines.map((line) => {
    const row = cells(line);
    return h("tr", null, head.map((_, i) => cell("td", row[i] ?? "", i)));
  }));
  return h("div", { class: "md-table" }, h("table", null, [thead, tbody]));
}

export function renderMarkdown(src) {
  const frag = document.createDocumentFragment();
  const lines = String(src || "").replace(/\r/g, "").split("\n");
  let para = [], list = null;
  const flushPara = () => { if (para.length) { frag.appendChild(h("p", { dir: "auto" }, inline(para.join(" ")))); para = []; } };
  const flushList = () => { if (list) { frag.appendChild(list); list = null; } };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trimEnd();
    if (!line.trim()) { flushPara(); flushList(); continue; }
    if (isRow(line) && i + 1 < lines.length && SEP.test(lines[i + 1])) {
      flushPara(); flushList();
      const body = [];
      let j = i + 2;
      while (j < lines.length && lines[j].trim() && isRow(lines[j])) body.push(lines[j++]);
      frag.appendChild(table(line, lines[i + 1], body));
      i = j - 1;
      continue;
    }
    const bullet = /^\s*[-*•]\s+(.*)$/.exec(line);
    const num = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    const head = /^(#{1,4})\s+(.*)$/.exec(line);
    if (head) { flushPara(); flushList(); frag.appendChild(h(head[1].length <= 2 ? "h3" : "h4", null, inline(head[2]))); continue; }
    if (bullet || num) {
      flushPara();
      const tag = bullet ? "ul" : "ol";
      if (!list || list.tagName.toLowerCase() !== tag) { flushList(); list = h(tag); }
      list.appendChild(h("li", { dir: "auto" }, inline((bullet || num)[1])));
      continue;
    }
    flushList();
    para.push(line.trim());
  }
  flushPara(); flushList();
  return frag;
}
