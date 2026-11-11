// Chart.js wrapper: colors from CSS role tokens (so light/dark are selected, not flipped), thin marks,
// recessive grid, hover tooltips, and a table view for every chart. Re-renders on theme change.
import { h } from "./dom.js";

const live = new Set();   // {canvas, build}

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

export function theme() {
  return {
    text: css("--text-secondary"), muted: css("--text-muted"), grid: css("--grid"), surface: css("--surface-1"),
    border: css("--border-strong"), primary: css("--text-primary"),
    series: [css("--series-1"), css("--series-2"), css("--series-3")],
  };
}

function baseOptions(t) {
  return {
    responsive: true, maintainAspectRatio: false, animation: { duration: 450 },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: t.surface, titleColor: t.primary, bodyColor: t.text, borderColor: t.border, borderWidth: 1,
        padding: 10, cornerRadius: 8, displayColors: true, boxPadding: 4,
      },
    },
  };
}

function mount(container, build) {
  const canvas = h("canvas", { role: "img" });
  container.appendChild(canvas);
  const entry = { canvas, build, chart: null };
  entry.chart = new window.Chart(canvas, build(theme()));
  live.add(entry);
  return entry;
}

export function refreshCharts() {
  for (const e of live) {
    if (!e.canvas.isConnected) { e.chart.destroy(); live.delete(e); continue; }
    e.chart.destroy();
    e.chart = new window.Chart(e.canvas, e.build(theme()));
  }
}

export function clearCharts() {
  for (const e of live) e.chart.destroy();
  live.clear();
}

// Single-series bar (horizontal when labels are long or many). One hue, no legend (the title names it).
export function barChart(container, { labels, values, valueLabel = "Candidates", horizontal }) {
  const horiz = horizontal ?? (labels.length > 6 || labels.some((l) => String(l).length > 12));
  container.classList.toggle("short", !horiz && labels.length <= 6);
  if (horiz) container.style.height = `${Math.max(180, labels.length * 34 + 40)}px`;
  return mount(container, (t) => {
    const o = baseOptions(t);
    const valueAxis = { beginAtZero: true, grid: { color: t.grid }, border: { display: false },
                        ticks: { color: t.muted, precision: 0 } };
    const catAxis = { grid: { display: false }, border: { color: t.border }, ticks: { color: t.text } };
    o.indexAxis = horiz ? "y" : "x";
    o.scales = horiz ? { x: valueAxis, y: catAxis } : { x: catAxis, y: valueAxis };
    o.plugins.tooltip.callbacks = { label: (c) => ` ${valueLabel}: ${c.formattedValue}` };
    return {
      type: "bar",
      data: { labels, datasets: [{ label: valueLabel, data: values, backgroundColor: t.series[0],
                                   borderRadius: 4, borderSkipped: "start", maxBarThickness: 28,
                                   borderColor: t.surface, borderWidth: { top: 0, bottom: 0, left: 0, right: 0 } }] },
      options: o,
    };
  });
}

export function lineChart(container, { labels, values, valueLabel = "Value" }) {
  return mount(container, (t) => {
    const o = baseOptions(t);
    o.interaction = { mode: "index", intersect: false };
    o.scales = { x: { grid: { display: false }, ticks: { color: t.text } },
                 y: { beginAtZero: true, grid: { color: t.grid }, border: { display: false }, ticks: { color: t.muted } } };
    return { type: "line", data: { labels, datasets: [{ label: valueLabel, data: values, borderColor: t.series[0],
             backgroundColor: t.series[0], borderWidth: 2, pointRadius: 4, pointHoverRadius: 6, tension: 0.25 }] },
             options: o };
  });
}

// Radar for up to 3 series (categorical slots 1-3 are validated all-pairs). Values are 0-100.
export function radarChart(container, { labels, series }) {
  return mount(container, (t) => {
    const o = baseOptions(t);
    o.scales = { r: { min: 0, max: 100, ticks: { stepSize: 25, color: t.muted, backdropColor: "transparent", showLabelBackdrop: false },
                      grid: { color: t.grid }, angleLines: { color: t.grid }, pointLabels: { color: t.text, font: { size: 12 } } } };
    o.plugins.tooltip.callbacks = { label: (c) => ` ${c.dataset.label}: ${c.formattedValue}%` };
    return {
      type: "radar",
      data: { labels, datasets: series.slice(0, 3).map((s, i) => ({
        label: s.label, data: s.values, borderColor: t.series[i], backgroundColor: t.series[i] + "22",
        borderWidth: 2, pointRadius: 4, pointHoverRadius: 6, pointBackgroundColor: t.series[i],
        pointBorderColor: t.surface, pointBorderWidth: 2,
      })) },
      options: o,
    };
  });
}

export function legend(items) {
  const t = theme();
  return h("div", { class: "legend" }, items.slice(0, 3).map((label, i) =>
    h("span", null, h("i", { style: { background: t.series[i] } }), label)));
}

export function dataTable(headers, rows) {
  return h("table", { class: "data-table" },
    h("thead", null, h("tr", null, headers.map((x, i) => h("th", { class: i ? "num" : null }, x)))),
    h("tbody", null, rows.map((r) => h("tr", null, r.map((c, i) => h("td", { class: i ? "num" : null }, c))))));
}

// Chart <-> table toggle used by every chart block.
export function chartWithTable(drawChart, table) {
  const chartBox = h("div", { class: "chart-wrap" });
  const tableBox = h("div", { hidden: true }, table);
  const bChart = h("button", { type: "button", "aria-pressed": "true" }, "Chart");
  const bTable = h("button", { type: "button", "aria-pressed": "false" }, "Table");
  const set = (showTable) => {
    tableBox.hidden = !showTable; chartBox.hidden = showTable;
    bChart.setAttribute("aria-pressed", String(!showTable)); bTable.setAttribute("aria-pressed", String(showTable));
  };
  bChart.addEventListener("click", () => set(false));
  bTable.addEventListener("click", () => set(true));
  const toggle = h("div", { class: "seg-toggle", role: "group", "aria-label": "View" }, bChart, bTable);
  queueMicrotask(() => drawChart(chartBox));
  return { toggle, body: [chartBox, tableBox] };
}
