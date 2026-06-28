# Proof-Carrying Answers

> AI that ships a **receipt** for every claim.

We have spent years trying to make language models hallucinate *less*. That is
the wrong target — you cannot prove a black box won't lie. **Proof-Carrying
Answers** stops trusting the generator and instead **verifies the output**:

1. **Decompose** every answer into atomic, independently checkable claims.
2. **Retrieve** evidence for each claim from a source corpus.
3. **Entail** — label each claim `SUPPORTED`, `REFUTED`, or `UNSUPPORTED`
   against that evidence, with citations.
4. **Withhold** — claims that can't be supported are dropped, not asserted.

The result is a **proof graph** that any third party can re-run. Trust moves
from the model to a verdict you can audit.

## The demonstration

Ask *"What did Einstein win the Nobel Prize for?"* and feed in a plausible,
confidently-wrong answer:

> "Einstein won the Nobel Prize in Physics in 1921. He received it for his
> theory of relativity. He shared the award with Niels Bohr."

The verifier returns:

| Verdict | Claim |
|---|---|
| ✅ SUPPORTED | won the Nobel Prize in Physics in 1921 |
| ❌ REFUTED | received it for his theory of relativity *(it was the photoelectric effect)* |
| ⚠ UNSUPPORTED | shared the award with Niels Bohr *(no evidence — withheld)* |

…and reconstructs a **verified answer** containing only what survived:
*"Albert Einstein won the Nobel Prize in Physics in 1921."*

## Run it

```bash
pip install -r requirements.txt
python app.py
# open http://127.0.0.1:5070
```

`python engine.py` runs a standalone self-test of the verifier on the demo set.

**Optional local model (no API, no GPU, no cost):** set `ENABLE_LOCAL_LLM=1` to
load a small CPU-only quantized model (default **Qwen2.5-1.5B-Instruct**, ~1 GB
Q4) via `llama-cpp-python`. It runs in ~8 GB RAM / 8 vCPU — sized for a Railway
box. It is used to generate answers and to produce cleaner, pronoun-resolved
claims. The app runs **fully offline** without it — the deterministic verifier is
the core contribution, and the model is *never trusted*: every claim it emits is
verified against evidence before it can enter the final answer. Config lives in
[`.env.example`](.env.example).

> The design point: a small, cheap, hallucination-prone model becomes
> *trustworthy* when wrapped in verification. That's the whole thesis, made
> concrete on hardware that costs a few dollars a month.

## Deploy to Railway

1. Push this folder to a Git repo and create a Railway service from it.
2. Railway auto-detects Python via `requirements.txt` and runs the
   [`Procfile`](Procfile) (`gunicorn`, 1 worker so one model copy fits in RAM).
   The `--extra-index-url` in `requirements.txt` pulls **prebuilt CPU wheels** for
   `llama-cpp-python`, so nothing compiles on the box.
3. Set service variables (see `.env.example`): `ENABLE_LOCAL_LLM=1`, optionally
   `MODEL_N_THREADS=8`. Railway injects `PORT` automatically.
4. The model downloads (~1 GB) on first boot; `warmup()` starts it in the
   background so the deterministic verifier is usable immediately and the model
   comes online shortly after. To avoid re-downloading on every restart, mount a
   volume and set `HF_HOME=/data/hf`.

If `llama-cpp-python` ever fails to install, the app still deploys and runs the
deterministic verifier — the model imports are guarded.

## Architecture

```
 answer ─▶ decompose ─▶ [claim, claim, claim]
                              │  each claim
                              ▼
                  retrieve evidence (TF-IDF cosine)
                              │
                  entail: SUPPORTED | REFUTED | UNSUPPORTED
                              │  (subject + predicate gated)
                              ▼
              ProofGraph  ──▶ verified answer (supported only)
                  │
            recheck_proof()  ← any third party re-runs and confirms
```

- `engine.py` — decomposition, TF-IDF retrieval, subject/predicate-gated
  entailment, proof graph, independent re-checker. **Zero ML dependencies** —
  the route from text to verdict is ~300 lines of auditable code.
- `corpus.py` — trustworthy source passages + demo scenarios with planted errors.
- `local_model.py` — optional CPU-only small-model backend (llama-cpp-python).
- `llm.py` — generator interface over the local model (graceful fallback).
- `app.py` — Flask API (local: port 5070; Railway: `$PORT`).
- `Procfile`, `.env.example` — Railway deployment.
- `static/` — single-page verification UI.
- `MOONSHOT.md` — the Moonshot paper.

## Why the entailment is non-trivial

A naive checker refutes any claim whose year/number/name differs from *some*
retrieved sentence — but a *different fact* with a different year is not a
refutation. The verifier gates every conflict on **same-subject + same-predicate
alignment** (with light stemming so "received"/"receive" align), so:

- a wrong year on the *same* fact → REFUTED,
- a true fact the corpus doesn't cover → UNSUPPORTED (withheld, never asserted),
- a correct fact with matching evidence → SUPPORTED.

All 9 verdicts across the 3 demo scenarios are correct, and every proof
re-checks independently.

## Files

| File | Purpose |
|------|---------|
| `engine.py` | Verifier core + `ProofGraph` + `recheck_proof` |
| `corpus.py` | Evidence corpus + demo answers (true / false / unsupported mix) |
| `local_model.py` | CPU-only small-model backend (Qwen2.5-1.5B, GGUF) |
| `llm.py` | Generator interface over the local model (decompose / answer) |
| `Procfile`, `.env.example` | Railway deployment config |
| `app.py` | Flask backend / JSON API |
| `static/` | UI |
| `MOONSHOT.md` | The Moonshot paper |
