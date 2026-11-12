// Small, safe Markdown subset -> DOM: headings, paragraphs, bullet/numbered lists, **bold**, *italic*, `code`.
// No raw HTML and no links: everything becomes text nodes.
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

export function renderMarkdown(src) {
  const frag = document.createDocumentFragment();
  const lines = String(src || "").replace(/\r/g, "").split("\n");
  let para = [], list = null;
  const flushPara = () => { if (para.length) { frag.appendChild(h("p", { dir: "auto" }, inline(para.join(" ")))); para = []; } };
  const flushList = () => { if (list) { frag.appendChild(list); list = null; } };
  for (const raw of lines) {
    const line = raw.trimEnd();
    const bullet = /^\s*[-*•]\s+(.*)$/.exec(line);
    const num = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    const head = /^(#{1,4})\s+(.*)$/.exec(line);
    if (!line.trim()) { flushPara(); flushList(); continue; }
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
