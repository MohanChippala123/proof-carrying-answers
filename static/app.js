// Proof-Carrying Answers — verification workbench

const $ = (s, r = document) => r.querySelector(s);
const api = (p, opts) => fetch(p, opts).then(r => r.json());

let lastResult = null;
let activeFilter = "ALL";
let history = [];
let corpusDocs = [];

// ── Status bar ────────────────────────────────────────────────────────────────

async function loadStatus() {
  const s = await api("/api/status");
  const ms = s.model_state || { enabled: false, state: "disabled" };
  const corpus = ` / corpus: ${s.corpus_docs} sources, ${s.corpus_sentences} sentences`;
  let dot = "off", msg;
  if (!ms.enabled) {
    msg = "Offline mode / deterministic verifier (no model needed)";
  } else if (ms.state === "ready") {
    dot = "on";
    msg = `Local model ready / ${ms.model.split("/").pop()}`;
  } else if (ms.state === "loading" || ms.state === "disabled") {
    msg = `Loading local model — first boot downloads ~1 GB…`;
    setTimeout(loadStatus, 3000);
  } else {
    msg = `Model unavailable (${ms.error?.slice(0, 60) || "load failed"}) / deterministic verifier`;
  }
  $("#status").innerHTML = `<span class="dot ${dot}"></span>${msg}${corpus}`;
  const ready = ms.state === "ready";
  $("#usellm").disabled = !ready;
  $("#usellm").parentElement.style.opacity = ready ? 1 : .5;
}

// ── Demos ─────────────────────────────────────────────────────────────────────

async function loadDemos() {
  const demos = await api("/api/demos");
  const box = $("#demos");
  box.innerHTML = "";
  demos.forEach(d => {
    const el = document.createElement("button");
    el.type = "button"; el.className = "demo";
    el.textContent = d.question; el.title = d.note;
    el.onclick = () => {
      $("#question").value = d.question;
      $("#answer").value = d.answer;
      $("#result").classList.add("hidden");
      $("#compareResult").classList.add("hidden");
      $("#vstatus").textContent = "";
      lastResult = null;
    };
    box.appendChild(el);
  });
}

// ── Corpus management ─────────────────────────────────────────────────────────

async function loadCorpus() {
  const res = await api("/api/corpus");
  corpusDocs = res.docs || [];
  renderCorpusList();
}

function renderCorpusList() {
  const box = $("#corpusList");
  if (!box) return;
  if (!corpusDocs.length) { box.innerHTML = ""; return; }
  box.innerHTML = `<div class="mini-ledger">${
    corpusDocs.map(d => `<div class="source-row">
      <strong>${esc(d.title)}</strong>
      <span>${esc(d.id)} / ${d.sentences} sentences</span>
      <small><a href="${esc(d.source)}" target="_blank" rel="noopener">${esc(d.source.slice(0, 50))}${d.source.length > 50 ? "…" : ""}</a></small>
    </div>`).join("")
  }</div>`;
}

async function addSource() {
  const title = $("#sourceTitle").value.trim() || "User source";
  const source = $("#sourceUrl").value.trim() || "user-provided";
  const text = $("#sourceText").value.trim();
  if (!text) { $("#sourceStatus").textContent = "Paste evidence text first."; return; }
  setStatus("#addSource", "#sourceStatus", "Indexing…");
  const res = await api("/api/corpus", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, source, text }),
  });
  $("#addSource").disabled = false;
  if (res.error) { $("#sourceStatus").textContent = res.error; return; }
  $("#sourceStatus").textContent = `Added — corpus now has ${res.corpus_docs} sources.`;
  $("#sourceTitle").value = ""; $("#sourceUrl").value = ""; $("#sourceText").value = "";
  await Promise.all([loadStatus(), loadCorpus()]);
}

async function resetCorpus() {
  setStatus("#resetCorpus", "#sourceStatus", "Resetting…");
  const res = await api("/api/corpus/reset", { method: "POST" });
  $("#resetCorpus").disabled = false;
  $("#sourceStatus").textContent = `Reset to ${res.corpus_docs} default sources.`;
  await Promise.all([loadStatus(), loadCorpus()]);
}

async function fetchWikipedia(query) {
  query = query || $("#wikiQuery").value.trim();
  if (!query) { $("#wikiStatus").textContent = "Enter a topic or Wikipedia URL."; return; }
  setStatus("#fetchWiki", "#wikiStatus", `Fetching "${query}"…`);
  const res = await api("/api/wikipedia", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  $("#fetchWiki").disabled = false;
  if (res.error) { $("#wikiStatus").textContent = res.error; return; }
  $("#wikiStatus").textContent = `Added "${res.title}" — ${res.corpus_docs} sources now.`;
  $("#wikiQuery").value = "";
  await Promise.all([loadStatus(), loadCorpus()]);
}

// ── Verification ──────────────────────────────────────────────────────────────

async function verify() {
  const useStream = $("#streamMode").checked;
  if (useStream) await verifyStream();
  else await verifyBatch();
}

async function verifyBatch() {
  const question = $("#question").value.trim();
  const answer = $("#answer").value.trim();
  const use_llm = $("#usellm").checked;
  if (!answer) { $("#vstatus").textContent = "Enter an answer to verify."; return; }
  setStatus("#verify", "#vstatus", "Verifying…");
  const res = await api("/api/verify", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, answer, use_llm_decompose: use_llm }),
  });
  $("#verify").disabled = false;
  if (res.error) { $("#vstatus").textContent = res.error; return; }
  $("#vstatus").textContent = res.llm_decompose_used ? "Local model decomposition used." : "Proof built.";
  lastResult = res; activeFilter = "ALL";
  remember(res); render(res);
}

async function verifyStream() {
  const question = $("#question").value.trim();
  const answer = $("#answer").value.trim();
  const use_llm = $("#usellm").checked;
  if (!answer) { $("#vstatus").textContent = "Enter an answer to verify."; return; }

  $("#verify").disabled = true;
  $("#vstatus").textContent = "Streaming…";

  const box = $("#result");
  box.classList.remove("hidden");
  box.innerHTML = `<div class="stream-banner">
    <span id="streamLabel">Decomposing…</span>
    <div class="stream-track"><div class="stream-fill" id="streamFill" style="width:0%"></div></div>
  </div><div class="claim-list" id="streamClaims"></div>`;

  const claimList = $("#streamClaims");
  let total = 0, done = 0;

  try {
    const resp = await fetch("/api/verify/stream", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, answer, use_llm_decompose: use_llm }),
    });

    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";

    while (true) {
      const { done: eof, value } = await reader.read();
      if (eof) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop();
      for (const chunk of parts) {
        if (!chunk.startsWith("data: ")) continue;
        const ev = JSON.parse(chunk.slice(6));

        if (ev.type === "start") {
          total = ev.total;
          $("#streamLabel").textContent = `0 of ${total} claims verified`;

        } else if (ev.type === "claim") {
          done++;
          const pct = Math.round((done / Math.max(total, 1)) * 100);
          $("#streamFill").style.width = pct + "%";
          $("#streamLabel").textContent = `${done} of ${total} claims verified`;

          const card = document.createElement("div");
          card.className = `claim ${ev.verdict} entering`;
          card.innerHTML = claimCardHTML(ev, done - 1);
          claimList.appendChild(card);
          // Bind "Find evidence" buttons inside this card
          bindFindEvidence(card);

        } else if (ev.type === "done") {
          lastResult = ev; activeFilter = "ALL";
          remember(ev);
          render(ev); // full render replaces streaming UI
          $("#vstatus").textContent = "Proof built.";

        } else if (ev.type === "error") {
          $("#vstatus").textContent = ev.error;
          box.classList.add("hidden");
        }
      }
    }
  } catch (e) {
    $("#vstatus").textContent = "Stream error — try again.";
  }

  $("#verify").disabled = false;
}

// ── Comparison ────────────────────────────────────────────────────────────────

async function compareAnswers() {
  const question = $("#question").value.trim();
  const first = $("#answer").value.trim();
  const second = $("#answerB")?.value.trim();
  const use_llm = $("#usellm").checked;
  if (!first || !second) { $("#vstatus").textContent = "Add two answers to compare."; return; }
  setStatus("#compare", "#vstatus", "Comparing proofs…");
  const res = await api("/api/compare", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question, use_llm_decompose: use_llm,
      answers: [{ label: "Answer A", answer: first }, { label: "Answer B", answer: second }],
    }),
  });
  $("#compare").disabled = false;
  if (res.error) { $("#vstatus").textContent = res.error; return; }
  $("#vstatus").textContent = `${res.winner} wins by proof quality.`;
  renderComparison(res);
}

// ── Rendering ─────────────────────────────────────────────────────────────────

function render(res) {
  const box = $("#result");
  box.classList.remove("hidden");
  const s = res.summary;
  const total = Math.max(res.claims.length, 1);
  const supportedPct = Math.round((s.supported / total) * 100);
  const refutedPct = Math.round((s.refuted / total) * 100);
  const unsupportedPct = Math.max(0, 100 - supportedPct - refutedPct);
  const audit = res.audit || {};
  const filtered = activeFilter === "ALL" ? res.claims
    : res.claims.filter(c => c.verdict === activeFilter);

  let html = `<div class="result-top">
    <div>
      <p class="kicker">Proof ledger</p>
      <h3>${esc(res.question || "Untitled verification")}</h3>
    </div>
    <div class="result-actions">
      <button class="secondary small" type="button" data-action="copy">Copy proof</button>
      <button class="secondary small" type="button" data-action="markdown">Export .md</button>
      <button class="secondary small" type="button" data-action="download">Download JSON</button>
      <button class="secondary small" type="button" data-action="share">Share link</button>
    </div>
  </div>

  <div class="meter" aria-label="Verdict composition">
    <span class="meter-ok" style="width:${supportedPct}%"></span>
    <span class="meter-no" style="width:${refutedPct}%"></span>
    <span class="meter-hold" style="width:${unsupportedPct}%"></span>
  </div>

  <div class="audit-grid">
    <div><strong>${audit.claim_count ?? res.claims.length}</strong><span>atomic claims</span></div>
    <div><strong>${audit.evidence_spans ?? countEvidence(res)}</strong><span>evidence links</span></div>
    <div><strong>${res.recheck_passed ? "PASS" : "FAIL"}</strong><span>deterministic recheck</span></div>
    <div><strong>${riskLabel(res)}</strong><span>deployment risk</span></div>
  </div>

  <div class="scorebar">
    ${filterPill("ALL", `ALL ${res.claims.length}`)}
    ${filterPill("SUPPORTED", `OK ${s.supported} supported`)}
    ${filterPill("REFUTED", `NO ${s.refuted} refuted`)}
    ${filterPill("UNSUPPORTED", `HOLD ${s.unsupported} withheld`)}
    <span class="pill trust">trust ${s.trust_score}</span>
    ${res.recheck_passed ? '<span class="pill recheck">proof re-checks</span>' : ''}
  </div>

  <div class="claim-list">`;

  filtered.forEach((c, i) => {
    html += claimCardHTML(c, i);
  });

  if (!filtered.length) html += `<div class="empty-state">No claims match this filter.</div>`;
  html += `</div>`;

  html += `<div class="verified">
    <h4>Verified answer / supported claims only</h4>
    <p>${esc(res.verified_answer)}</p>
  </div>`;

  box.innerHTML = html;
  bindResultActions();
  bindFindEvidence(box);
}

function claimCardHTML(c, index) {
  return `<div class="claim ${c.verdict}${c.verdict === "SUPPORTED" ? "" : ""}">
    <div class="claim-head">
      <span class="tag ${c.verdict}">${c.verdict}</span>
      <span class="claim-text">${esc(c.claim)}</span>
      <span class="confidence">${Math.round((c.confidence || 0) * 100)}%</span>
    </div>
    <div class="claim-reason">${esc(c.reason)}</div>
    ${evidenceBlock(c, index)}
    ${c.verdict === "UNSUPPORTED"
      ? `<button class="find-evidence-btn" type="button" data-claim="${esc(c.claim)}">
           Find Wikipedia evidence for this claim →
         </button>`
      : ""}
  </div>`;
}

function renderComparison(res) {
  const box = $("#compareResult");
  box.classList.remove("hidden");
  box.innerHTML = `<div class="section-heading compact">
    <p class="kicker">Comparison</p>
    <h2>Proof-ranked answers</h2>
    <p class="sub">${esc(res.winner)} has the strongest surviving proof graph.</p>
  </div>
  <div class="compare-grid">
    ${res.results.map((r, i) => comparisonCard(r, i)).join("")}
  </div>`;
  box.querySelectorAll("[data-open-result]").forEach(btn => {
    btn.onclick = () => {
      const r = res.results[Number(btn.dataset.openResult)];
      lastResult = r; activeFilter = "ALL";
      remember(r); render(r);
      $("#result").scrollIntoView({ behavior: "smooth", block: "start" });
    };
  });
}

function comparisonCard(result, index) {
  const s = result.summary;
  return `<article class="compare-card ${index === 0 ? "winner" : ""}">
    <p class="kicker">${esc(result.label)} ${index === 0 ? "/ winner" : ""}</p>
    <div class="compare-score">${s.trust_score}</div>
    <div class="mini-bars">
      <span class="ok" style="width:${barWidth(s.supported, result.claims.length)}%"></span>
      <span class="no" style="width:${barWidth(s.refuted, result.claims.length)}%"></span>
      <span class="hold" style="width:${barWidth(s.unsupported, result.claims.length)}%"></span>
    </div>
    <p>${s.supported} supported / ${s.refuted} refuted / ${s.unsupported} withheld</p>
    <button class="secondary small" type="button" data-open-result="${index}">Open proof</button>
  </article>`;
}

// ── History + sparkline ────────────────────────────────────────────────────────

function remember(res) {
  history = [{
    question: res.question || "Untitled verification",
    trust: res.summary.trust_score,
    supported: res.summary.supported,
    refuted: res.summary.refuted,
    unsupported: res.summary.unsupported,
    result: res,
  }, ...history].slice(0, 8);
  renderHistory();
}

function renderHistory() {
  const box = $("#history");
  if (!history.length) {
    box.className = "history empty";
    box.textContent = "No runs yet.";
    return;
  }
  box.className = "history";
  box.innerHTML = history.map((h, i) => `<button type="button" class="history-item" data-history="${i}">
    <span>${esc(h.question)}</span>
    <strong>trust ${h.trust}</strong>
    <small>${h.supported} ok / ${h.refuted} no / ${h.unsupported} hold</small>
    ${sparklineSVG(history.slice(i))}
  </button>`).join("");
  box.querySelectorAll("[data-history]").forEach(btn => {
    btn.onclick = () => {
      lastResult = history[Number(btn.dataset.history)].result;
      activeFilter = "ALL"; render(lastResult);
      $("#result").scrollIntoView({ behavior: "smooth", block: "start" });
    };
  });
}

function sparklineSVG(items) {
  if (items.length < 2) return "";
  const vals = items.map(h => parseFloat(h.trust)).reverse();
  const max = Math.max(...vals, 0.01);
  const W = 80, H = 26;
  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * W;
    const y = H - (v / max) * (H - 4);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const last = vals[vals.length - 1];
  const color = last > 0.6 ? "var(--green)" : last > 0.3 ? "var(--amber)" : "var(--red)";
  return `<svg class="sparkline" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" aria-hidden="true">
    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>
  </svg>`;
}

// ── Evidence + filter helpers ─────────────────────────────────────────────────

function filterPill(verdict, label) {
  const kind = { SUPPORTED: "s", REFUTED: "r", UNSUPPORTED: "u", ALL: "all" }[verdict] ?? "all";
  const active = activeFilter === verdict ? " active" : "";
  return `<button class="pill ${kind}${active}" type="button" data-filter="${verdict}">${label}</button>`;
}

function evidenceBlock(claim, index) {
  const support = claim.support || [];
  const refute = claim.refute || [];
  const rows = [
    ...refute.map(e => evidenceRow(e, "refute", "Refuting evidence")),
    ...support.map(e => evidenceRow(e, "support", "Supporting evidence")),
  ];
  if (!rows.length) return "";
  return `<details class="evidence-drawer" ${index < 2 ? "open" : ""}>
    <summary>Evidence packet / ${rows.length} source match${rows.length === 1 ? "" : "es"}</summary>
    ${rows.join("")}
  </details>`;
}

function evidenceRow(ev, cls, label) {
  return `<div class="evidence ${cls}">
    <div class="ev-label">${label} / score ${ev.score}</div>
    <div class="quote">"${esc(ev.sentence)}"</div>
    <a href="${esc(ev.source)}" target="_blank" rel="noopener">${esc(ev.title)} -&gt;</a>
  </div>`;
}

function bindFindEvidence(container) {
  container.querySelectorAll(".find-evidence-btn").forEach(btn => {
    btn.onclick = async () => {
      const claim = btn.dataset.claim;
      btn.disabled = true;
      btn.textContent = "Fetching Wikipedia…";
      await fetchWikipedia(claim.split(" ").slice(0, 5).join(" "));
      btn.textContent = "Evidence fetched — re-verify to check this claim →";
    };
  });
}

function bindResultActions() {
  $("#result").querySelectorAll("[data-filter]").forEach(btn => {
    btn.onclick = () => { activeFilter = btn.dataset.filter; render(lastResult); };
  });
  const r = $("#result");
  r.querySelector("[data-action='copy']")?.addEventListener("click", copyProof);
  r.querySelector("[data-action='markdown']")?.addEventListener("click", exportMarkdown);
  r.querySelector("[data-action='download']")?.addEventListener("click", downloadProof);
  r.querySelector("[data-action='share']")?.addEventListener("click", shareResult);
}

// ── Export / share ────────────────────────────────────────────────────────────

async function copyProof() {
  if (!lastResult) return;
  try {
    await navigator.clipboard.writeText(formatProof(lastResult));
    $("#vstatus").textContent = "Proof copied.";
  } catch { $("#vstatus").textContent = "Clipboard unavailable — try Download JSON."; }
}

function downloadProof() {
  if (!lastResult) return;
  const blob = new Blob([JSON.stringify(lastResult, null, 2)], { type: "application/json" });
  const a = Object.assign(document.createElement("a"),
    { href: URL.createObjectURL(blob), download: `proof-${Date.now()}.json` });
  a.click(); URL.revokeObjectURL(a.href);
}

function exportMarkdown() {
  if (!lastResult) return;
  const res = lastResult;
  const s = res.summary;
  const lines = [
    `# Proof — ${res.question || "Untitled verification"}`,
    ``,
    `**Trust score:** ${s.trust_score} &nbsp;|&nbsp; **Risk:** ${riskLabel(res)} &nbsp;|&nbsp; **Recheck:** ${res.recheck_passed ? "PASS" : "FAIL"}`,
    ``,
    `| Verdict | Count |`,
    `|---|---|`,
    `| ✅ Supported | ${s.supported} |`,
    `| ❌ Refuted   | ${s.refuted}   |`,
    `| ⚠ Withheld  | ${s.unsupported} |`,
    ``,
    `## Claims`,
    ``,
  ];
  res.claims.forEach((c, i) => {
    const icon = { SUPPORTED: "✅", REFUTED: "❌", UNSUPPORTED: "⚠" }[c.verdict] ?? "?";
    lines.push(`### ${i + 1}. ${icon} ${c.verdict}`);
    lines.push(`**${c.claim}**`);
    lines.push(`*${c.reason}*`);
    (c.support || []).forEach(e => lines.push(`> [SUPPORT] "${e.sentence}" — [${e.title}](${e.source})`));
    (c.refute || []).forEach(e => lines.push(`> [REFUTE] "${e.sentence}" — [${e.title}](${e.source})`));
    lines.push("");
  });
  lines.push(`## Verified answer`, ``, `> ${res.verified_answer}`);

  const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
  const a = Object.assign(document.createElement("a"),
    { href: URL.createObjectURL(blob), download: `proof-${Date.now()}.md` });
  a.click(); URL.revokeObjectURL(a.href);
}

async function shareResult() {
  if (!lastResult) return;
  const packed = {
    q: lastResult.question,
    s: lastResult.summary,
    v: lastResult.verified_answer,
    t: Date.now(),
  };
  try {
    const hash = btoa(unescape(encodeURIComponent(JSON.stringify(packed))));
    const url = `${location.origin}${location.pathname}#proof=${hash}`;
    await navigator.clipboard.writeText(url);
    $("#vstatus").textContent = "Share link copied.";
  } catch { $("#vstatus").textContent = "Clipboard unavailable."; }
}

function formatProof(res) {
  const lines = [
    `Question: ${res.question || "Untitled verification"}`,
    `Trust score: ${res.summary.trust_score} / Risk: ${riskLabel(res)} / Recheck: ${res.recheck_passed}`,
    "",
    "Claims:",
  ];
  res.claims.forEach((c, i) => {
    lines.push(`${i + 1}. [${c.verdict}] ${c.claim}`);
    lines.push(`   ${c.reason}`);
  });
  lines.push("", `Verified answer: ${res.verified_answer}`);
  return lines.join("\n");
}

// ── Misc helpers ──────────────────────────────────────────────────────────────

function countEvidence(res) {
  return res.claims.reduce((n, c) => n + (c.support || []).length + (c.refute || []).length, 0);
}

function riskLabel(res) {
  const s = res.summary;
  if (s.refuted > 0) return "HIGH";
  if (s.unsupported > 0) return "REVIEW";
  return "LOW";
}

function barWidth(count, total) {
  return Math.round((count / Math.max(total, 1)) * 100);
}

function setStatus(btnSel, msgSel, msg) {
  const btn = $(btnSel);
  if (btn) btn.disabled = true;
  const el = $(msgSel);
  if (el) el.textContent = msg;
}

function clearWorkbench() {
  $("#question").value = "";
  $("#answer").value = "";
  const b = $("#answerB"); if (b) b.value = "";
  $("#vstatus").textContent = "";
  $("#result").classList.add("hidden");
  $("#compareResult").classList.add("hidden");
  lastResult = null; activeFilter = "ALL";
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ── Load permalink from hash ──────────────────────────────────────────────────

function maybeLoadHash() {
  try {
    const m = location.hash.match(/^#proof=(.+)/);
    if (!m) return;
    const data = JSON.parse(decodeURIComponent(escape(atob(m[1]))));
    if (data.q && data.v) {
      $("#vstatus").textContent = `Shared proof: "${data.q}"`;
    }
  } catch { /* invalid hash — ignore */ }
}

// ── Keyboard shortcuts ────────────────────────────────────────────────────────

document.addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    verify();
  }
});

// ── Init ──────────────────────────────────────────────────────────────────────

$("#verify").onclick = verify;
$("#compare").onclick = compareAnswers;
$("#clear").onclick = clearWorkbench;
$("#addSource").onclick = addSource;
$("#resetCorpus").onclick = resetCorpus;
$("#fetchWiki").onclick = () => fetchWikipedia();
$("#wikiQuery").addEventListener("keydown", e => {
  if (e.key === "Enter") fetchWikipedia();
});

loadStatus();
loadDemos();
loadCorpus();
maybeLoadHash();
