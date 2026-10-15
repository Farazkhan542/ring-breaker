"use strict";
const BANKS = ["BANK_A", "BANK_B", "BANK_C"];
const SHAPE = { BANK_A: "a", BANK_B: "b", BANK_C: "c" };
const COLOR = { BANK_A: "var(--bank-a)", BANK_B: "var(--bank-b)", BANK_C: "var(--bank-c)" };
const NICE = { BANK_A: "Bank A", BANK_B: "Bank B", BANK_C: "Bank C" };
const TOTAL_TX = 52306; // all transactions in the synthetic three-bank world
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const short = (m) => m.replace(/^M-/, "").slice(0, 6);
let indicatorHelp = {};

/* ---------- tabs ---------- */
document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((x) => x.setAttribute("aria-selected", String(x === t)));
  document.querySelectorAll(".panel-tab").forEach((p) => (p.hidden = p.id !== `tab-${t.dataset.tab}`));
  if (t.dataset.tab === "results") loadMetrics();
  if (t.dataset.tab === "rules") loadRules();
  if (t.dataset.tab === "audit") loadAudit();
  if (t.dataset.tab === "regulator") loadRegulator();
}));

/* ---------- markdown (escaped first, so model output can't inject HTML) ---------- */
function md(text) {
  const lines = esc(text).split(/\r?\n/);
  let html = "", inList = false;
  for (const raw of lines) {
    const l = raw.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/(^|\s)\*(\S.*?)\*/g, "$1<em>$2</em>").replace(/`(.+?)`/g, "<code>$1</code>");
    const li = l.match(/^\s*[-*]\s+(.*)/);
    if (li) { if (!inList) { html += "<ul>"; inList = true; } html += `<li>${li[1]}</li>`; continue; }
    if (inList) { html += "</ul>"; inList = false; }
    const h = l.match(/^(#{1,4})\s+(.*)/);
    if (h) html += `<h4>${h[2]}</h4>`;
    else if (l.trim()) html += `<p>${l}</p>`;
  }
  return html + (inList ? "</ul>" : "");
}

/* ---------- bank views (alone) ---------- */
async function loadBanks() {
  const d = await (await fetch("/api/banks")).json();
  indicatorHelp = d.indicator_help;
  $("#banks").innerHTML = d.banks.map((b) => {
    const rows = b.flagged.slice().sort((x, y) => y.in_demo_case - x.in_demo_case).map((f) =>
      `<li class="${f.in_demo_case ? "case" : ""}"><span class="mono">${esc(f.account)}</span><span class="ind">${f.indicators.map((i) => `<span title="${esc(indicatorHelp[i] || "")}">${esc(i)}</span>`).join(", ")}</span></li>`).join("");
    return `<article class="bank" style="--c:${COLOR[b.bank]}">
      <div class="bank-h"><span class="shape ${SHAPE[b.bank]}" aria-hidden="true"></span><h3>${NICE[b.bank]}</h3></div>
      <p class="facts"><span title="Customers whose data this bank's agent can see">${b.customers.toLocaleString()} customers</span> · <span title="Transactions touching this bank's customers">${b.transactions_visible.toLocaleString()} transactions visible</span> · <span title="Customers with a behaviour red flag plus at least one more indicator">${b.flagged.length} flagged</span></p>
      <ul aria-label="${NICE[b.bank]} flagged customers (internal IDs, never shared)">${rows}</ul>
      <p class="alone"><strong>Alone:</strong> ${b.case_customers_flagged} of its flagged customers belong to today's case, but their transfers lead to other banks. <strong>No ring found.</strong></p>
    </article>`;
  }).join("");
  $("#banks").setAttribute("aria-busy", "false");
}

/* ---------- ring map: three bank lanes ---------- */
const W = 720, H = 300, LANE_X = { BANK_A: 130, BANK_B: 360, BANK_C: 590 };
let graph = { nodes: [], edges: [] }, order = [];
function shapeSvg(bank, x, y, r, cls, fill) {
  if (bank === "BANK_A") return `<circle class="${cls}" cx="${x}" cy="${y}" r="${r}" ${fill}/>`;
  if (bank === "BANK_B") return `<rect class="${cls}" x="${x - r}" y="${y - r}" width="${2 * r}" height="${2 * r}" ${fill}/>`;
  return `<path class="${cls}" d="M${x} ${y - r * 1.15} L${x + r * 1.1} ${y + r * 0.85} L${x - r * 1.1} ${y + r * 0.85} Z" ${fill}/>`;
}
function drawMap(final) {
  const { nodes, edges } = graph;
  nodes.forEach((n) => { if (!order.includes(n.id)) order.push(n.id); });
  const pos = {}, perLane = { BANK_A: 0, BANK_B: 0, BANK_C: 0 };
  order.forEach((id) => {
    const n = nodes.find((x) => x.id === id); if (!n) return;
    const i = perLane[n.bank]++;
    pos[id] = { x: LANE_X[n.bank] + (i % 2 ? 46 : -46), y: 80 + i * 62 };
  });
  const ringIds = new Set(nodes.filter((n) => n.in_ring).map((n) => n.id));
  const seen = new Set();
  const edgeSvg = edges.filter((e) => pos[e.src] && pos[e.dst]).filter((e) => {
    const k = e.src + e.dst; if (seen.has(k)) return false; seen.add(k); return true;
  }).map((e) => {
    const a = pos[e.src], b = pos[e.dst], ring = ringIds.has(e.src) && ringIds.has(e.dst);
    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2 - 28;
    return `<path class="edge ${ring ? "ring" : ""}" d="M${a.x} ${a.y} Q${mx} ${my} ${b.x} ${b.y}" marker-end="url(#arrow${ring ? "R" : ""})"><title>${esc(e.amount_band)} · ${esc(e.time_window)}</title></path>`;
  }).join("");
  const nodeSvg = nodes.filter((n) => pos[n.id]).map((n) => {
    const p = pos[n.id], col = COLOR[n.bank];
    const fill = n.flagged ? `fill="${col}" stroke="#14202b" stroke-width="${n.in_ring ? 2.5 : 0}"` : `fill="#fff" stroke="#4d5b69" stroke-dasharray="4 3" stroke-width="1.5"`;
    const tip = n.flagged ? `${n.id} (${NICE[n.bank]}): ${n.indicators.join(", ")}` : `${n.id} (${NICE[n.bank]}): withheld, not flagged by its bank`;
    return `<g class="node"><title>${esc(tip)}</title>${shapeSvg(n.bank, p.x, p.y, 13, "", fill)}<text class="node-label" x="${p.x}" y="${p.y + 30}" text-anchor="middle">${short(n.id)}${n.hop === 0 ? " ★" : ""}</text></g>`;
  }).join("");
  const lanes = BANKS.map((b) => `<line x1="${LANE_X[b]}" y1="44" x2="${LANE_X[b]}" y2="${H - 10}" stroke="#e3e8ee" stroke-width="90"/>
    <text class="lane-label" x="${LANE_X[b]}" y="30" text-anchor="middle" fill="${COLOR[b]}">${NICE[b]}</text>`).join("");
  const maxY = Math.max(H, ...Object.values(pos).map((p) => p.y + 50));
  $("#map").innerHTML = `<svg viewBox="0 0 ${W} ${maxY}" role="img" aria-label="Ring map: ${ringIds.size} accounts in the ring across ${new Set(nodes.filter((n) => n.in_ring).map((n) => n.bank)).size} banks. A table version follows.">
    <defs>${["", "R"].map((k) => `<marker id="arrow${k}" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="${k ? "#14202b" : "#8a97a6"}"/></marker>`).join("")}</defs>
    ${lanes}${edgeSvg}${nodeSvg}</svg>`;
  $("#ring-table tbody").innerHTML = nodes.filter((n) => n.in_ring || final).map((n) =>
    `<tr><td class="mono">${esc(n.id)}</td><td>${NICE[n.bank]}</td><td>${n.flagged ? esc(n.indicators.join(", ")) : "withheld"}</td><td class="num">${n.hop}</td></tr>`).join("");
}

/* ---------- conversation + sharing counters ---------- */
let q = 0, shared, seedId = null, explanations = {};
function srcModel(x) { return x.source === "fallback" ? "rule-based text" : `${esc(x.model)}${x.source === "cache" ? " · cached" : ""}`; }
function fillExplanations() {
  document.querySelectorAll("[data-explain]").forEach((el) => {
    const x = explanations[el.dataset.explain];
    if (x) el.innerHTML = `${esc(x.text)} <span class="src">${srcModel(x)}</span>`;
  });
}
function resetShared() { shared = Object.fromEntries(BANKS.map((b) => [b, { answers: 0, withheld: 0, ids: new Set(), records: 0 }])); }
function renderShared() {
  let records = 0;
  $("#shared").innerHTML = BANKS.map((b) => {
    const s = shared[b]; records += s.records;
    return `<div><h3><span class="shape ${SHAPE[b]}" aria-hidden="true"></span>${NICE[b]}</h3><dl>
      <dt title="Answers this bank sent to other banks' agents">Answers sent</dt><dd>${s.answers}</dd>
      <dt title="Questions refused because the customer was not flagged by this bank">Answers withheld</dt><dd>${s.withheld}</dd>
      <dt title="Distinct masked account IDs that appeared in this bank's answers">Masked IDs shared</dt><dd>${s.ids.size}</dd>
      <dt title="Transfers described in answers, as amount band and 6-hour window only">Transfer records shared</dt><dd>${s.records}</dd></dl></div>`;
  }).join("") + `<p class="never" style="grid-column:1/-1">Never shared: names, account numbers, addresses, balances, exact amounts, exact times, device or IP data.</p>`;
  $("#shared-pct").textContent = `${(100 * records / TOTAL_TX).toFixed(2)}% of transactions shared`;
}
function addConvo(html, cls) {
  const li = document.createElement("li"); li.className = cls || ""; li.innerHTML = html;
  $("#convo").appendChild(li); li.scrollIntoView({ block: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
}
const QTEXT = { flag_status: "Is this customer flagged by your rules, and why?", linked_counterparties: "Which accounts did this customer send large transfers to, or receive them from?" };
function onEvent(ev) {
  switch (ev.type) {
    case "phase": case "note": addConvo(esc(ev.text), ev.type); break;
    case "case_open":
      seedId = ev.subject;
      addConvo(`<span class="who">${NICE[ev.bank]}</span> opens a case on <span class="mono">${esc(ev.subject)}</span> (${esc(ev.indicators.join(", "))}).<span class="rule">${esc(ev.rule_id)}: ${esc(ev.rule_text)}</span>`, ev.allowed ? "ok" : "blocked"); break;
    case "local_check":
      if (ev.hop > 0) addConvo(`<span class="who">${NICE[ev.bank]}</span> checks its own customer <span class="mono">${esc(ev.masked_id)}</span> locally: ${ev.flagged ? "flagged" : "not flagged"}. Nothing leaves the bank.`, "note"); break;
    case "a2a_request": {
      const p = ev.payload;
      const forbidden = (p.fields || []).filter((f) => ["name", "balance", "address", "account_number", "exact_amount", "transaction_history"].includes(f));
      const ask = forbidden.length ? `Asks for ${forbidden.map((f) => `<span class="redact-label">${esc(f)}</span>`).join(" and ")} of <span class="mono">${esc(p.subject)}</span>` : `${esc(QTEXT[p.type] || p.type)} <span class="mono">${esc(p.subject)}</span>`;
      if (ev.allowed) { q++; $("#qcount").textContent = `${q} question${q === 1 ? "" : "s"}`; }
      addConvo(`<span class="verdict">${ev.allowed ? "✓ allowed" : "✕ blocked"}</span> <span class="who">${NICE[ev.from]} → ${NICE[ev.to]}</span> · A2A<br>${ask}<span class="rule">${esc(ev.rule_id)}: ${esc(ev.detail || ev.rule_text)}</span>`, ev.allowed ? "ok" : "blocked");
      break;
    }
    case "a2a_response": {
      const p = ev.payload, s = shared[ev.from];
      let body;
      if (p.status === "ok" && p.indicators) { body = `Flagged: ${esc(p.indicators.join(", "))}`; s.answers++; s.ids.add(p.masked_id); }
      else if (p.status === "ok" && p.counterparties) {
        s.answers++; s.ids.add(p.masked_id); s.records += p.counterparties.length; p.counterparties.forEach((c) => s.ids.add(c.masked_id));
        body = `${p.counterparties.length} transfers: ` + p.counterparties.slice(0, 4).map((c) => `${c.direction === "out" ? "→" : "←"} <span class="mono">${short(c.masked_id)}</span> (${NICE[c.bank_code] || esc(c.bank_code)}, ${esc(c.amount_band)})`).join("; ") + (p.counterparties.length > 4 ? "; …" : "");
      } else { s.withheld++; body = `Withheld: ${esc(p.reason)}`; }
      addConvo(`<span class="who">${NICE[ev.from]} → ${NICE[ev.to]}</span> · answer<br>${body}<span class="rule">${esc(ev.rule_id)}: ${esc(ev.detail)}</span>`, p.status === "ok" ? "ok" : "");
      renderShared(); break;
    }
    case "thinking": addConvo(esc(ev.text), "note"); break;
    case "plan": {
      const who = ev.source === "live" || ev.source === "cache" ? `Planner · ${esc(ev.model)} via ADK${ev.source === "cache" ? " · cached" : ""}` : "Planner · rule-based fallback";
      addConvo(`<span class="who">${who}</span><br>${esc(ev.reason)}<span class="rule">Follows ${ev.ask.length} of ${ev.leads} lead(s)${ev.drop.length ? `, drops ${ev.drop.length}` : ""}. The policy agent still checks every question.</span>`, "plan");
      break;
    }
    case "explain": {
      explanations[ev.masked_id] = ev;
      if (ev.masked_id === seedId) addConvo(`<span class="who">${NICE[ev.bank]}'s own assistant · ${srcModel(ev)}</span><br>${esc(ev.text)}<span class="rule">Runs inside ${NICE[ev.bank]} on its own data; nothing here is shared.</span>`, "explain");
      fillExplanations(); break;
    }
    case "graph": graph = ev; drawMap(false); break;
    case "ring":
      graph = { nodes: ev.nodes, edges: ev.edges }; drawMap(true);
      addConvo(`Ring found: <strong>${ev.ring.length} accounts across ${ev.banks.length} banks</strong> (${ev.banks.map((b) => NICE[b]).join(", ")}).`, "phase"); break;
    case "case_file": showCase(ev); break;
    case "done":
      $("#status").textContent = `Done in ${ev.seconds}s · ${ev.queries} questions · ${ev.blocked} blocked by policy`;
      $("#run").disabled = false; $("#run").textContent = "Run it again"; break;
    case "error": $("#status").textContent = `The investigation stopped: ${ev.text}. Run it again.`; $("#run").disabled = false; break;
  }
}

/* ---------- case file + approvals ---------- */
function srcLabel(x) { return x.source === "fallback" ? "precomputed text (Gemini unavailable)" : `${esc(x.model)} via ADK${x.source === "cache" ? " · cached" : ""}`; }
function showCase(ev) {
  $("#case").hidden = false;
  $("#case-meta").textContent = ev.case_id;
  $("#casefile").innerHTML = md(ev.case_file.text); $("#writer-src").textContent = srcLabel(ev.case_file);
  $("#skeptic").innerHTML = md(ev.skeptic.text); $("#skeptic-src").textContent = srcLabel(ev.skeptic);
  $("#confidence").innerHTML = `<strong title="Rule-based score computed in code; Gemini explains it but never computes it">Confidence ${ev.confidence.score}/100</strong><div class="meter" aria-hidden="true"><span style="width:${ev.confidence.score}%"></span></div>${ev.confidence.reasons.map(esc).join(" · ")}`;
  const byBank = ev.facts.accounts_by_bank;
  $("#approvals").innerHTML = BANKS.filter((b) => byBank[b]).map((b) => `<div class="approval" style="--c:${COLOR[b]}" data-bank="${b}">
    <h4><span class="shape ${SHAPE[b]}" aria-hidden="true"></span>${NICE[b]} officer</h4>
    <ul>${byBank[b].map((a) => `<li><span class="mono">${esc(a.masked_id)}</span><p class="why" data-explain="${esc(a.masked_id)}">Your assistant is explaining this flag…</p></li>`).join("")}</ul>
    <label for="r-${b}">Reason (stored with the decision)</label><input id="r-${b}" maxlength="500" placeholder="e.g. matches our own alert history">
    <div class="btns"><button data-d="approve">Approve filing</button><button data-d="reject">Reject</button><button data-d="more_evidence">Ask for more evidence</button></div>
    <p class="decided" aria-live="polite"></p></div>`).join("");
  fillExplanations();
  $("#approvals").querySelectorAll("button").forEach((btn) => btn.addEventListener("click", async () => {
    const box = btn.closest(".approval"), bank = box.dataset.bank;
    const r = await fetch(`/api/cases/${ev.case_id}/decisions`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bank, decision: btn.dataset.d, reason: box.querySelector("input").value }) });
    const d = await r.json(), mine = d.decisions[bank];
    box.querySelector(".decided").textContent = mine ? `Saved: ${mine.decision.replace("_", " ")} at ${mine.ts.slice(11, 19)} UTC` : "Could not save the decision. Try again.";
  }));
}

/* ---------- run ---------- */
$("#run").addEventListener("click", () => {
  $("#run").disabled = true; $("#status").textContent = "Agents are talking…";
  $("#convo").innerHTML = ""; $("#case").hidden = true; q = 0; $("#qcount").textContent = "0 questions";
  graph = { nodes: [], edges: [] }; order = []; seedId = null; explanations = {}; resetShared(); renderShared();
  const es = new EventSource("/api/demo/run");
  es.onmessage = (m) => { const ev = JSON.parse(m.data); onEvent(ev); if (ev.type === "done" || ev.type === "error") es.close(); };
  es.onerror = () => { es.close(); if ($("#run").disabled) { $("#status").textContent = "Connection lost. Run it again."; $("#run").disabled = false; } };
});

/* ---------- other tabs ---------- */
async function loadRules() {
  const d = await (await fetch("/api/policy")).json();
  $("#rules").innerHTML = d.rules.map((r) => `<li><span class="rid">${esc(r.id)}</span><p>${esc(r.text)}</p></li>`).join("");
}
async function loadAudit() {
  const d = await (await fetch("/api/audit")).json();
  $("#audit tbody").innerHTML = d.entries.slice().reverse().map((e) => `<tr><td class="mono">${esc(e.ts.slice(11, 19))}</td><td>${esc(e.from)} → ${esc(e.to)}</td><td>${esc(e.kind)}</td><td class="mono">${esc(JSON.stringify(e.payload)).slice(0, 220)}</td><td>${e.allowed ? "allowed" : "<strong>blocked</strong>"} · ${esc(e.rule_id)}</td></tr>`).join("") || `<tr><td colspan="5">No cross-bank messages yet. Run the investigation first.</td></tr>`;
}
const MARK = { BANK_A: "#009688", BANK_B: "#9a5800", BANK_C: "#6a3fb5" }; // chart fills, validated for colour-blind separation
async function loadRegulator() {
  const r = await fetch("/api/regulator");
  if (!r.ok) { $("#reg-source").textContent = "The regulator view isn't available right now. Reload the page."; return; }
  const d = await r.json();
  $("#reg-source").innerHTML = d.source === "bigquery"
    ? `Live from BigQuery · dataset <code>${esc(d.dataset)}</code>${d.looker_url ? ` · <a href="${esc(d.looker_url)}" target="_blank" rel="noopener">Open the Looker Studio report</a>` : ""}`
    : "From this server's memory (BigQuery is not connected here).";
  const banks = d.by_bank || [], sum = (k) => banks.reduce((a, b) => a + (b[k] || 0), 0);
  const blocked = (d.blocked_by_rule || []).reduce((a, b) => a + b.blocked, 0);
  const tiles = [
    [sum("questions_received"), "questions answered between banks", "Allowed questions across all cases"],
    [sum("answers_withheld"), "answers withheld", "Questions about customers the bank had not flagged: nothing shared"],
    [blocked, "requests blocked by policy", "Requests the policy agent refused, such as asking for a name or balance"],
    [sum("masked_ids_shared"), "masked IDs shared", "Distinct masked account IDs that appeared in answers"],
  ];
  $("#reg-tiles").innerHTML = tiles.map(([v, k, t]) => `<div class="tile" title="${esc(t)}"><span class="v">${Number(v).toLocaleString()}</span><span class="k">${esc(k)}</span></div>`).join("");
  drawSharedChart(banks);
  $("#reg-blocked tbody").innerHTML = (d.blocked_by_rule || []).map((b) => `<tr><td>${esc(b.rule_id)}</td><td class="num">${b.blocked}</td></tr>`).join("") || `<tr><td colspan="2">Nothing blocked yet.</td></tr>`;
  $("#reg-banks tbody").innerHTML = banks.map((b) => `<tr><td><span class="shape ${SHAPE[b.bank] || ""}" aria-hidden="true" style="display:inline-block;vertical-align:-2px;margin-right:6px"></span>${NICE[b.bank] || esc(b.bank)}</td>${["questions_received", "answers_sent", "answers_withheld", "masked_ids_shared", "records_shared"].map((k) => `<td class="num">${b[k] ?? 0}</td>`).join("")}</tr>`).join("") || `<tr><td colspan="6">No cross-bank messages yet. Run the investigation first.</td></tr>`;
  $("#reg-cases tbody").innerHTML = (d.cases || []).map((c) => `<tr><td class="mono">${esc(String(c.ts).slice(0, 19).replace("T", " "))}</td><td class="mono">${esc(c.case_id)}</td><td>${NICE[c.lead_bank] || esc(c.lead_bank)}</td><td class="num">${c.ring_size}</td><td class="num">${c.questions}</td><td class="num">${c.blocked}</td><td class="num">${c.confidence}</td></tr>`).join("") || `<tr><td colspan="7">No cases yet. Run the investigation first.</td></tr>`;
}
function drawSharedChart(banks) {
  const rows = BANKS.map((b) => ({ bank: b, v: (banks.find((x) => x.bank === b) || {}).masked_ids_shared || 0, rec: (banks.find((x) => x.bank === b) || {}).records_shared || 0 }));
  const max = Math.max(1, ...rows.map((r) => r.v)), W = 560, L = 84, R = 48, BH = 18, ROW = 44, H = rows.length * ROW + 24;
  const x = (v) => L + (W - L - R) * v / max;
  const ticks = [0, Math.round(max / 2), max].filter((v, i, a) => a.indexOf(v) === i);
  const bars = rows.map((r, i) => {
    const y = 12 + i * ROW, w = Math.max(0, x(r.v) - L), rad = Math.min(4, w / 2);
    const path = w > 0 ? `M${L} ${y} H${L + w - rad} Q${L + w} ${y} ${L + w} ${y + rad} V${y + BH - rad} Q${L + w} ${y + BH} ${L + w - rad} ${y + BH} H${L} Z` : "";
    return `<g class="bar" tabindex="0" data-i="${i}" aria-label="${NICE[r.bank]}: ${r.v} masked IDs, ${r.rec} transfer records shared">
      <rect class="hit" x="0" y="${y - 12}" width="${W}" height="${ROW}" fill="transparent"/>
      <text x="${L - 10}" y="${y + 13}" text-anchor="end">${NICE[r.bank]}</text>
      <path d="${path}" fill="${MARK[r.bank]}"/>
      <text class="muted" x="${L + w + 6}" y="${y + 13}">${r.v}</text></g>`;
  }).join("");
  const grid = ticks.map((t) => `<line x1="${x(t)}" y1="4" x2="${x(t)}" y2="${H - 18}" stroke="#e3e8ee"/><text class="muted" x="${x(t)}" y="${H - 2}" text-anchor="middle">${t}</text>`).join("");
  $("#reg-chart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Masked IDs shared by each bank; the activity table below has the same numbers">${grid}<line x1="${L}" y1="4" x2="${L}" y2="${H - 18}" stroke="#8a97a6"/>${bars}</svg>`;
  const box = $("#reg-chart");
  box.insertAdjacentHTML("beforeend", `<div class="tip" role="status" hidden></div>`);
  const tip = box.querySelector(".tip");
  const show = (g) => {
    const r = rows[+g.dataset.i], b = g.getBoundingClientRect(), c = box.getBoundingClientRect();
    tip.textContent = `${NICE[r.bank]}: ${r.v} masked IDs, ${r.rec} transfer records`;
    tip.hidden = false; tip.style.left = `${Math.min(b.left - c.left + 90, c.width - 220)}px`; tip.style.top = `${b.top - c.top + 40}px`;
  };
  box.querySelectorAll(".bar").forEach((g) => {
    g.addEventListener("mouseenter", () => show(g)); g.addEventListener("focus", () => show(g));
    g.addEventListener("mouseleave", () => (tip.hidden = true)); g.addEventListener("blur", () => (tip.hidden = true));
  });
}
async function loadMetrics() {
  const r = await fetch("/api/metrics");
  if (!r.ok) { $("#metrics").innerHTML = `<p class="note">Results aren't published yet.</p>`; return; }
  const m = await r.json();
  let html = "";
  for (const sec of m.sections) {
    html += `<h2>${esc(sec.title)}</h2><p class="note">${esc(sec.note)}</p><div class="table-wrap"><table><thead><tr>${sec.columns.map((c) => `<th${c.num ? ' class="num"' : ""} title="${esc(c.help || "")}">${esc(c.label)}</th>`).join("")}</tr></thead><tbody>` +
      sec.rows.map((row) => `<tr>${sec.columns.map((c) => `<td${c.num ? ' class="num"' : ""}>${esc(row[c.key])}</td>`).join("")}</tr>`).join("") + `</tbody></table></div>`;
  }
  $("#metrics").innerHTML = html + `<p class="note">Generated ${esc(m.generated)}. ${esc(m.caveat || "")}</p>`;
}

resetShared(); renderShared();
loadBanks().catch(() => { $("#banks").innerHTML = `<p>Bank agents are starting. Reload in a few seconds.</p>`; });
