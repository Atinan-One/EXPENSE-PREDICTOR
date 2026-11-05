"use strict";

const $ = (s) => document.querySelector(s);
const SVG = "http://www.w3.org/2000/svg";
const PALETTE = ["#4f46e5", "#f59e0b", "#10b981", "#ef4444", "#06b6d4", "#8b5cf6", "#ec4899", "#84cc16"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const el = (tag, text, cls) => {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;      // textContent only: never inject raw HTML
  if (cls) e.className = cls;
  return e;
};
const money = (n) => `Rs ${Math.round(n).toLocaleString("en-US")}`;
const monthLabel = (m) => `${MONTHS[parseInt(m.slice(5), 10) - 1]} '${m.slice(2, 4)}`;

let budget = null;
try { budget = parseFloat(localStorage.getItem("budget")) || null; } catch { /* storage may be blocked */ }

async function api(path, options) {
  let res;
  try { res = await fetch(path, options); }
  catch { throw new Error("Cannot reach the server. Is it running?"); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Something went wrong.");
  return data;
}
const withBudget = (path) => (budget ? `${path}?budget=${budget}` : path);

function setMsg(node, text) { node.textContent = text; node.hidden = !text; }
const globalError = (t) => setMsg($("#global-error"), t);

/* ---------------- Rendering ---------------- */
function render(r) {
  globalError("");
  const has = r.has_data;
  $("#welcome").hidden = has;
  $("#dashboard").hidden = !has;
  $("#bar-actions").hidden = !has;
  if (!has) return;

  const s = r.summary;
  $("#s-avg").textContent = money(s.avg_monthly);
  $("#s-last-lbl").textContent = `Last full month (${monthLabel(s.last_month)})`;
  $("#s-last").textContent = money(s.last_month_total);
  $("#s-fc-lbl").textContent = `Forecast for ${monthLabel(s.forecast_month)}`;
  $("#s-fc").textContent = s.forecast_total === null ? "Need more data" : money(s.forecast_total);
  $("#s-cur-box").hidden = !r.current;
  if (r.current) {
    $("#s-cur-lbl").textContent = `So far in ${monthLabel(r.current.month)}`;
    $("#s-cur").textContent = money(r.current.total);
  }
  $("#s-count").textContent = s.transactions.toLocaleString("en-US");

  const notes = $("#notes");
  notes.replaceChildren();
  r.notes.forEach((n) => notes.appendChild(el("div", n, "note")));
  if (r.import_info && r.import_info.rows_dropped > 0) {
    notes.appendChild(el("div",
      `Imported ${r.import_info.rows_kept} of ${r.import_info.rows_read} rows. ` +
      `${r.import_info.rows_dropped} were skipped (bad dates, zero or negative amounts, or duplicates).`, "note"));
  }
  if (s.auto_categorised > 0) {
    const acc = s.model_accuracy === null ? "" : ` (model accuracy about ${Math.round(s.model_accuracy * 100)}%)`;
    notes.appendChild(el("div", `${s.auto_categorised} expenses were categorised automatically from their descriptions${acc}.`, "note"));
  }

  renderBudget(r);
  renderAlerts(r);
  drawChart(r);
  renderCategories(r);
  renderRecent(r);
}

function renderBudget(r) {
  const box = $("#budget-result");
  const b = r.budget;
  if (!b) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  box.className = `budget-result ${b.status}`;
  box.replaceChildren(el("p", b.message));
  if (b.tip) box.appendChild(el("p", b.tip, "muted"));
}

function renderAlerts(r) {
  const ul = $("#alerts");
  ul.replaceChildren();
  if (!r.alerts.length) {
    ul.appendChild(el("li", "No sudden jumps in spending last month.", "ok"));
    return;
  }
  r.alerts.forEach((a) => ul.appendChild(el("li", `${a.category}: up ${Math.round(a.change * 100)}% vs the previous 3-month average`)));
}

function renderCategories(r) {
  const body = $("#cat-body");
  body.replaceChildren();
  document.querySelectorAll(".col-sofar").forEach((n) => { n.hidden = !r.current; });
  r.category_table.forEach((c) => {
    const tr = document.createElement("tr");
    let change = el("td", "-", "r");
    if (c.change !== null) {
      const pct = Math.round(c.change * 100);
      change = el("td", `${pct > 0 ? "+" : ""}${pct}%`, `r ${pct > 0 ? "up" : "down"}`);
    }
    tr.append(el("td", c.category), el("td", money(c.last_month), "r"));
    if (r.current) tr.append(el("td", money(c.so_far), "r"));
    tr.append(el("td", c.forecast === null ? "-" : money(c.forecast), "r"), change);
    body.appendChild(tr);
  });
}

function renderRecent(r) {
  const body = $("#recent-body");
  body.replaceChildren();
  r.recent.forEach((x) => {
    const tr = document.createElement("tr");
    const cat = el("td", x.category);
    if (x.auto) cat.appendChild(el("span", "auto", "tag"));
    tr.append(el("td", x.date), el("td", x.description), cat, el("td", money(x.amount), "r"));
    body.appendChild(tr);
  });
}

/* ---------------- Stacked bar chart (plain SVG, no libraries) ---------------- */
function svgEl(name, attrs) {
  const e = document.createElementNS(SVG, name);
  Object.entries(attrs || {}).forEach(([k, v]) => e.setAttribute(k, v));
  return e;
}

function drawChart(r) {
  const svg = $("#chart");
  svg.replaceChildren();
  const W = 900, H = 340, m = { l: 62, r: 10, t: 10, b: 58 };
  const cats = r.categories;
  const colors = Object.fromEntries(cats.map((c, i) => [c, PALETTE[i % PALETTE.length]]));
  const columns = r.months.map((mo, i) => ({ label: monthLabel(mo), forecast: false, values: cats.map((c) => r.monthly[c][i]) }));
  if (r.current) columns.push({ label: `${monthLabel(r.current.month)} (so far)`, forecast: false, values: cats.map((c) => r.current.values[c]) });
  if (r.forecast) columns.push({ label: `${monthLabel(r.summary.forecast_month)} (forecast)`, forecast: true, values: cats.map((c) => r.forecast[c]) });

  const maxTotal = Math.max(...columns.map((c) => c.values.reduce((a, b) => a + b, 0)), 1);
  const step = Math.pow(10, Math.floor(Math.log10(maxTotal))) / 2;
  const top = Math.ceil(maxTotal / step) * step;
  const plotW = W - m.l - m.r, plotH = H - m.t - m.b;
  const y = (v) => m.t + plotH - (v / top) * plotH;

  for (let i = 0; i <= 4; i++) {                      // gridlines + y labels
    const v = (top / 4) * i;
    svg.appendChild(svgEl("line", { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), stroke: "#e5e7eb" }));
    const t = svgEl("text", { x: m.l - 8, y: y(v) + 4, "text-anchor": "end", "font-size": 11, fill: "#6b7280" });
    t.textContent = v >= 1000 ? `${Math.round(v / 1000)}k` : String(Math.round(v));
    svg.appendChild(t);
  }

  const slot = plotW / columns.length, barW = Math.min(46, slot * 0.7);
  columns.forEach((col, i) => {
    const x = m.l + slot * i + (slot - barW) / 2;
    let acc = 0;
    col.values.forEach((v, k) => {
      if (v <= 0) return;
      const rect = svgEl("rect", {
        x, width: barW, y: y(acc + v), height: Math.max(0, y(acc) - y(acc + v)),
        fill: colors[cats[k]], "fill-opacity": col.forecast ? 0.5 : 1,
        stroke: col.forecast ? "#374151" : "none", "stroke-dasharray": col.forecast ? "3 2" : "0",
      });
      const tip = svgEl("title");
      tip.textContent = `${col.label} - ${cats[k]}: ${money(v)}`;
      rect.appendChild(tip);
      svg.appendChild(rect);
      acc += v;
    });
    const lx = x + barW / 2, ly = H - m.b + 16;
    const label = svgEl("text", { x: lx, y: ly, "text-anchor": "end", "font-size": 11, fill: "#374151",
      transform: `rotate(-40 ${lx} ${ly})` });
    label.textContent = col.label;
    svg.appendChild(label);
  });

  const legend = $("#legend");
  legend.replaceChildren();
  cats.forEach((c) => {
    const item = el("span");
    const sw = el("i");
    sw.style.background = colors[c];
    item.append(sw, document.createTextNode(c));
    legend.appendChild(item);
  });
}

/* ---------------- Actions ---------------- */
async function loadReport() {
  try { render(await api(withBudget("/api/report"))); }
  catch (e) { $("#welcome").hidden = false; globalError(e.message); }
}

$("#sample-btn").addEventListener("click", async (e) => {
  e.target.disabled = true;
  try { render(await api(withBudget("/api/sample"), { method: "POST" })); }
  catch (err) { globalError(err.message); }
  finally { e.target.disabled = false; }
});

$("#upload-btn").addEventListener("click", async (e) => {
  const file = $("#csv-file").files[0];
  if (!file) { globalError("Choose a CSV file first."); return; }
  const fd = new FormData();
  fd.append("file", file);
  e.target.disabled = true;
  try { render(await api(withBudget("/api/upload"), { method: "POST", body: fd })); }
  catch (err) { globalError(err.message); }
  finally { e.target.disabled = false; }
});

$("#clear-btn").addEventListener("click", async () => {
  if (!confirm("Delete all your expense data? This cannot be undone.")) return;
  try { render(await api("/api/clear", { method: "POST" })); }
  catch (err) { globalError(err.message); }
});

let budgetTimer;
$("#budget").value = budget || "";
$("#budget").addEventListener("input", (e) => {
  clearTimeout(budgetTimer);
  budgetTimer = setTimeout(async () => {
    const v = parseFloat(e.target.value);
    budget = v > 0 ? v : null;
    try { localStorage.setItem("budget", budget || ""); } catch { /* ignore */ }
    try { render(await api(withBudget("/api/report"))); } catch (err) { globalError(err.message); }
  }, 350);
});

/* Add expense: live category suggestion + submit */
const form = $("#add-form");
form.elements.date.value = new Date().toISOString().slice(0, 10);

form.elements.description.addEventListener("blur", async () => {
  const text = form.elements.description.value.trim();
  const box = $("#suggestion");
  if (!text) { box.hidden = true; return; }
  try {
    const r = await api("/api/predict-category", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ description: text }),
    });
    if (r.category) { box.textContent = `Suggested category: ${r.category} (${Math.round(r.confidence * 100)}% sure)`; box.hidden = false; }
    else box.hidden = true;
  } catch { box.hidden = true; }
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#add-btn"), errBox = $("#add-error"), okBox = $("#add-msg");
  setMsg(errBox, ""); setMsg(okBox, "");
  const f = form.elements;
  const payload = { date: f.date.value, description: f.description.value, amount: f.amount.value, category: f.category.value };
  btn.disabled = true;
  try {
    const r = await api(withBudget("/api/expenses"), {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    render(r);
    setMsg(okBox, `Added to ${r.added.category}${r.added.auto ? " (detected automatically)" : ""}.`);
    f.description.value = ""; f.amount.value = ""; f.category.value = ""; $("#suggestion").hidden = true;
  } catch (err) { setMsg(errBox, err.message); }
  finally { btn.disabled = false; }
});

loadReport();
