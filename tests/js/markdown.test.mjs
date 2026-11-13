// Chat Markdown subset: pipe tables (the "ugly comparison" fix) and safety.
import { test } from "node:test";
import assert from "node:assert/strict";
import { installDom } from "./fake_dom.mjs";

installDom();
const { renderMarkdown } = await import("../../static/js/markdown.js");

const render = (src) => { const host = document.createElement("div"); host.appendChild(renderMarkdown(src)); return host; };
const cellsOf = (row) => row.children.map((c) => c.textContent);

test("a pipe table becomes a real table with header, rows and alignment", () => {
  const host = render(`Intro line

| Candidate | Score | Matched skills |
|---|---:|:---:|
| Jeroen Jansen (#180) | 97.9 | Excel, **Tableau** |
| ريم تركي السبيعي (#127) | 96.6 | Excel |

After`);
  const table = host.find((n) => n.tagName === "TABLE");
  assert.ok(table, "table rendered");
  assert.ok(table.parentNode.classList.contains("md-table"), "wrapped for horizontal scroll");
  const [head, ...rows] = table.findAll((n) => n.tagName === "TR");
  assert.deepEqual(cellsOf(head), ["Candidate", "Score", "Matched skills"]);
  assert.deepEqual(cellsOf(rows[0]), ["Jeroen Jansen (#180)", "97.9", "Excel, Tableau"]);
  assert.equal(rows[1].children[0].textContent, "ريم تركي السبيعي (#127)");
  assert.equal(rows[1].children[0].getAttribute("dir"), "auto");
  assert.equal(rows[0].children[1].style.textAlign, "right");
  assert.equal(rows[0].children[2].style.textAlign, "center");
  assert.ok(rows[0].children[2].find((n) => n.tagName === "STRONG"), "inline formatting inside cells");
  const paras = host.findAll((n) => n.tagName === "P").map((p) => p.textContent);
  assert.deepEqual(paras, ["Intro line", "After"]);
});

test("short rows are padded and escaped pipes stay in the cell", () => {
  const host = render("| a | b |\n|---|---|\n| only |\n| x \\| y | z |");
  const rows = host.findAll((n) => n.tagName === "TR");
  assert.deepEqual(cellsOf(rows[1]), ["only", ""]);
  assert.deepEqual(cellsOf(rows[2]), ["x | y", "z"]);
});

test("pipes without a separator row stay a paragraph", () => {
  const host = render("a | b | c\nnext line");
  assert.equal(host.find((n) => n.tagName === "TABLE"), null);
  assert.equal(host.find((n) => n.tagName === "P").textContent, "a | b | c next line");
});

test("a table being streamed (header only so far) does not break", () => {
  const host = render("| Candidate | Score |\n|---|---|");
  const table = host.find((n) => n.tagName === "TABLE");
  assert.ok(table);
  assert.equal(table.find((n) => n.tagName === "TBODY").children.length, 0);
});

test("lists and headings still work; markup in text stays text", () => {
  const host = render("## Takeaways\n- one <b>x</b>\n- two\n1. first");
  assert.equal(host.find((n) => n.tagName === "H3").textContent, "Takeaways");
  assert.equal(host.findAll((n) => n.tagName === "LI").length, 3);
  assert.equal(host.find((n) => n.tagName === "B"), null);
  assert.ok(host.textContent.includes("<b>x</b>"));
});
