"""
Proof-Carrying Answers — Flask backend.

Run locally:
    pip install -r requirements.txt
    python app.py          →  http://127.0.0.1:5070

Railway: gunicorn reads PORT from env; ENABLE_LOCAL_LLM=1 turns the model on.
"""

from __future__ import annotations

import json

from flask import Flask, Response, jsonify, request, send_from_directory

import llm
import wiki
from corpus import DEMO, build_default_corpus
from engine import Document, Retriever, build_proof, decompose, recheck_proof, verify_claim

app = Flask(__name__, static_folder="static", static_url_path="")

BASE_CORPUS = build_default_corpus()
LIVE_DOCS = list(BASE_CORPUS)


def rebuild_retriever() -> Retriever:
    return Retriever(LIVE_DOCS)


RETRIEVER = rebuild_retriever()

# Start loading the local model in the background (no-op if ENABLE_LOCAL_LLM not set).
llm.warmup()


# ── Static ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ── Status / demos ───────────────────────────────────────────────────────────

@app.get("/api/status")
def status():
    import local_model
    return jsonify({
        "llm_available": llm.available(),
        "model": llm.MODEL,
        "model_state": local_model.state(),
        "corpus_docs": len(LIVE_DOCS),
        "corpus_sentences": len(RETRIEVER.sentences),
    })


@app.get("/api/demos")
def demos():
    return jsonify([
        {"id": d["id"], "question": d["question"],
         "answer": d["answer"], "note": d["note"]}
        for d in DEMO
    ])


# ── Core verification ────────────────────────────────────────────────────────

def _build_result(question: str, answer: str, use_llm: bool = False) -> dict:
    """Full verification pipeline → result dict suitable for JSON response."""
    decomposer = decompose
    llm_used = False
    if use_llm:
        claims = llm.llm_decompose(answer)
        if claims is not None:
            llm_used = True
            decomposer = lambda _a, _c=claims: list(_c)

    proof = build_proof(question, answer, RETRIEVER, decomposer=decomposer)
    result = proof.as_dict()
    result["recheck_passed"] = recheck_proof(proof, RETRIEVER)
    result["llm_decompose_used"] = llm_used
    result["audit"] = {
        "claim_count": len(result["claims"]),
        "evidence_spans": sum(
            len(c["support"]) + len(c["refute"]) for c in result["claims"]
        ),
        "withheld_claims": result["summary"]["unsupported"],
    }
    return result


@app.post("/api/verify")
def verify():
    """Batch verify — returns the full proof graph in one response."""
    data = request.get_json(force=True) or {}
    question = (data.get("question") or "").strip()
    answer = (data.get("answer") or "").strip()
    use_llm = bool(data.get("use_llm_decompose"))

    if not answer:
        if question and llm.available():
            answer = llm.llm_answer(question) or ""
        if not answer:
            return jsonify({"error": "Provide an answer to verify."}), 400

    return jsonify(_build_result(question, answer, use_llm))


@app.post("/api/verify/stream")
def verify_stream():
    """SSE endpoint — streams one claim verdict at a time.

    Events:
      {type:"start",  total:N, question, answer}
      {type:"claim",  index, total, claim, verdict, confidence, reason, support, refute}
      {type:"done",   ...full proof graph...}
      {type:"error",  error}
    """
    data = request.get_json(force=True) or {}
    question = (data.get("question") or "").strip()
    answer = (data.get("answer") or "").strip()
    use_llm = bool(data.get("use_llm_decompose"))

    if not answer:
        if question and llm.available():
            answer = llm.llm_answer(question) or ""

    if not answer:
        def _err():
            yield "data: " + json.dumps({"type": "error",
                                          "error": "No answer provided."}) + "\n\n"
        return Response(_err(), mimetype="text/event-stream")

    def _generate():
        # Decompose
        decomposer = decompose
        if use_llm:
            llm_claims = llm.llm_decompose(answer)
            if llm_claims is not None:
                decomposer = lambda _a, _c=llm_claims: list(_c)

        claims_list = decomposer(answer)
        total = len(claims_list)

        yield "data: " + json.dumps({
            "type": "start", "total": total,
            "question": question, "answer": answer,
        }) + "\n\n"

        for i, claim in enumerate(claims_list):
            evidence = RETRIEVER.search(claim)
            verdict = verify_claim(claim, evidence)
            payload = {
                "type": "claim",
                "index": i, "total": total,
                "claim": verdict.claim,
                "verdict": verdict.verdict.name,
                "confidence": round(verdict.confidence, 3),
                "reason": verdict.reason,
                "support": [
                    {"sentence": e.sentence, "score": round(e.score, 3),
                     "source": e.source, "title": e.title}
                    for e in verdict.support
                ],
                "refute": [
                    {"sentence": e.sentence, "score": round(e.score, 3),
                     "source": e.source, "title": e.title}
                    for e in verdict.refute
                ],
            }
            yield "data: " + json.dumps(payload) + "\n\n"

        # Final event: full proof graph identical to /api/verify
        result = _build_result(question, answer, use_llm)
        result["type"] = "done"
        yield "data: " + json.dumps(result) + "\n\n"

    return Response(
        _generate(), mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Comparison ───────────────────────────────────────────────────────────────

@app.post("/api/compare")
def compare():
    """Verify multiple candidate answers and rank by proof quality."""
    data = request.get_json(force=True) or {}
    question = (data.get("question") or "").strip()
    answers = data.get("answers") or []
    use_llm = bool(data.get("use_llm_decompose"))

    cleaned = []
    for i, ans in enumerate(answers):
        text = (ans.get("answer") if isinstance(ans, dict) else ans or "").strip()
        label = (ans.get("label") if isinstance(ans, dict) else "") or f"Answer {i + 1}"
        if text:
            cleaned.append({"label": label, "answer": text})

    if len(cleaned) < 2:
        return jsonify({"error": "Provide at least two answers to compare."}), 400

    results = []
    for item in cleaned[:4]:
        r = _build_result(question, item["answer"], use_llm)
        r["label"] = item["label"]
        results.append(r)

    def rank_key(r):
        s = r["summary"]
        return (s["trust_score"], s["supported"], -s["refuted"], -s["unsupported"])

    ranked = sorted(results, key=rank_key, reverse=True)
    return jsonify({"question": question, "winner": ranked[0]["label"], "results": ranked})


# ── Corpus management ────────────────────────────────────────────────────────

@app.get("/api/corpus")
def get_corpus():
    return jsonify({
        "docs": [
            {
                "id": d.doc_id, "title": d.title, "source": d.source,
                "sentences": sum(1 for doc, _ in RETRIEVER.sentences
                                 if doc.doc_id == d.doc_id),
            }
            for d in LIVE_DOCS
        ],
        "corpus_docs": len(LIVE_DOCS),
        "corpus_sentences": len(RETRIEVER.sentences),
    })


@app.post("/api/corpus")
def add_doc():
    """Add a plain-text source document."""
    global RETRIEVER
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "empty document"}), 400
    new_id = "user_" + str(sum(1 for d in LIVE_DOCS if d.doc_id.startswith("user_")))
    LIVE_DOCS.append(Document(
        new_id,
        data.get("title", "User source"),
        data.get("source", "user-provided"),
        text,
    ))
    RETRIEVER = rebuild_retriever()
    return jsonify({"added": new_id, "corpus_docs": len(LIVE_DOCS),
                    "corpus_sentences": len(RETRIEVER.sentences)})


@app.post("/api/corpus/reset")
def reset_corpus():
    global LIVE_DOCS, RETRIEVER
    LIVE_DOCS = list(BASE_CORPUS)
    RETRIEVER = rebuild_retriever()
    return jsonify({"reset": True, "corpus_docs": len(LIVE_DOCS),
                    "corpus_sentences": len(RETRIEVER.sentences)})


@app.post("/api/wikipedia")
def fetch_wikipedia():
    """Fetch a Wikipedia article and add it to the live corpus."""
    global RETRIEVER
    data = request.get_json(force=True) or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"error": "Provide a search query or Wikipedia URL."}), 400

    article = wiki.search_wikipedia(query)
    if not article:
        return jsonify({"error": f"No Wikipedia article found for: {query}"}), 404

    new_id = "wiki_" + str(sum(1 for d in LIVE_DOCS if d.doc_id.startswith("wiki_")))
    LIVE_DOCS.append(Document(new_id, article["title"], article["source"], article["text"]))
    RETRIEVER = rebuild_retriever()
    return jsonify({
        "added": new_id,
        "title": article["title"],
        "source": article["source"],
        "preview": article["text"][:300] + "…",
        "corpus_docs": len(LIVE_DOCS),
        "corpus_sentences": len(RETRIEVER.sentences),
    })


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", "5070"))
    debug = os.environ.get("FLASK_DEBUG", "") in ("1", "true", "True")
    app.run(host="0.0.0.0", port=port, debug=debug)
