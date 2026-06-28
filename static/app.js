// Front-end for the proof verification workbench.

const $ = (s, r = document) => r.querySelector(s);
const api = (p, opts) => fetch(p, opts).then(r => r.json());

async function loadStatus() {
  const s = await api("/api/status");
  const ms = s.model_state || { enabled: false, state: "disabled" };
  const corpus = ` / corpus: ${s.corpus_docs} sources, ${s.corpus_sentences} evidence sentences`;

  let dot = "off", msg;
  if (!ms.enabled) {
    msg = "Offline mode / deterministic verifier";
  } else if (ms.state === "ready") {
    dot = "on";
    msg = `Local model ready / ${ms.model}`;
  } else if (ms.state === "loading" || ms.state === "disabled") {
    msg = `Loading local model (${ms.model})... first boot downloads about 1 GB`;
    setTimeout(loadStatus, 3000);
  } else if (ms.state === "error") {
    msg = `Model unavailable (${ms.error || "load failed"}) / deterministic verifier`;
  }
  $("#status").innerHTML = `<span class="dot ${dot}"></span>${msg}${corpus}`;

  const ready = ms.state === "ready";
  $("#usellm").disabled = !ready;
  $("#usellm").parentElement.style.opacity = ready ? 1 : .5;
}

async function loadDemos() {
  const demos = await api("/api/demos");
  const box = $("#demos");
  box.innerHTML = "";
  demos.forEach(d => {
    const el = document.createElement("button");
    el.type = "button";
    el.className = "demo";
    el.textContent = d.question;
    el.title = d.note;
    el.onclick = () => {
      $("#question").value = d.question;
      $("#answer").value = d.answer;
      $("#result").classList.add("hidden");
      $("#vstatus").textContent = "";
    };
    box.appendChild(el);
  });
}

async function verify() {
  const question = $("#question").value.trim();
  const answer = $("#answer").value.trim();
  const use_llm = $("#usellm").checked;
  if (!answer) { $("#vstatus").textContent = "Enter an answer to verify."; return; }

  $("#vstatus").textContent = "Verifying...";
  const res = await api("/api/verify", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, answer, use_llm_decompose: use_llm }),
  });
  if (res.error) { $("#vstatus").textContent = res.error; return; }
  $("#vstatus").textContent = res.llm_decompose_used ? "Claude decomposition used." : "";
  render(res);
}

function render(res) {
  const box = $("#result");
  box.classList.remove("hidden");
  const s = res.summary;

  let html = `<div class="scorebar">
    <span class="pill s">OK ${s.supported} supported</span>
    <span class="pill r">NO ${s.refuted} refuted</span>
    <span class="pill u">HOLD ${s.unsupported} withheld</span>
    <span class="pill trust">trust ${s.trust_score}</span>
    ${res.recheck_passed ? '<span class="pill recheck">proof re-checks</span>' : ''}
  </div>`;

  res.claims.forEach(c => {
    html += `<div class="claim ${c.verdict}">
      <div class="claim-head">
        <span class="tag ${c.verdict}">${c.verdict}</span>
        <span class="claim-text">${esc(c.claim)}</span>
      </div>
      <div class="claim-reason">${esc(c.reason)}</div>`;
    if (c.refute && c.refute.length) html += evidence(c.refute[0], "refute", "Refuting evidence");
    else if (c.support && c.support.length) html += evidence(c.support[0], "support", "Supporting evidence");
    html += `</div>`;
  });

  html += `<div class="verified">
    <h4>Verified answer / supported claims only</h4>
    <p>${esc(res.verified_answer)}</p>
  </div>`;

  box.innerHTML = html;
}

function evidence(ev, cls, label) {
  return `<div class="evidence ${cls}">
    <div class="ev-label">${label} / score ${ev.score}</div>
    <div class="quote">"${esc(ev.sentence)}"</div>
    <a href="${esc(ev.source)}" target="_blank" rel="noopener">${esc(ev.title)} -></a>
  </div>`;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

$("#verify").onclick = verify;
loadStatus();
loadDemos();
