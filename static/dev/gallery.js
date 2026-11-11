import { renderBlock } from "../js/renderers.js";
import { refreshCharts } from "../js/charts.js";
import { h } from "../js/dom.js";

const thread = document.getElementById("thread");
const params = new URLSearchParams(location.search);
const ctx = { ask: (p) => alert(`Would send: ${p}`) };

document.getElementById("theme-toggle").addEventListener("click", () => {
  const dark = document.documentElement.getAttribute("data-theme") === "dark"
    || (!document.documentElement.hasAttribute("data-theme") && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.setAttribute("data-theme", dark ? "light" : "dark");
  refreshCharts();
});
if (params.get("theme")) document.documentElement.setAttribute("data-theme", params.get("theme"));

try {
  const res = await fetch(`/api/dev/sample-blocks?doc_id=${encodeURIComponent(params.get("doc") || "jd_senior_data_scientist")}`);
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  for (const b of await res.json()) thread.appendChild(renderBlock(b, ctx));
} catch (e) {
  thread.appendChild(h("div", { class: "error-box" }, String(e)));
}
