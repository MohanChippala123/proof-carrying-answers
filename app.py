"""
Proof-Carrying Answers -- Flask backend.

Serves the UI and exposes the verification pipeline over a small JSON API.

Run:
    pip install -r requirements.txt
    python app.py
    open http://127.0.0.1:5070

The server runs on port 5070 (5000 is blocked on some Windows setups).
"""

from __future__ import annotations

from flask import Flask, jsonify, request, send_from_directory

import llm
from corpus import DEMO, build_default_corpus
from engine import Document, Retriever, build_proof, decompose, recheck_proof

app = Flask(__name__, static_folder="static", static_url_path="")

# Build the retriever once over the default corpus.
RETRIEVER = Retriever(build_default_corpus())

# Begin loading the local model in the background (no-op unless ENABLE_LOCAL_LLM).
llm.warmup()


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/demos")
def demos():
    return jsonify([
        {"id": d["id"], "question": d["question"], "answer": d["answer"],
         "note": d["note"]}
        for d in DEMO
    ])


@app.get("/api/status")
def status():
    import local_model
    return jsonify({
        "llm_available": llm.available(),
        "model": llm.MODEL,
        "model_state": local_model.state(),
        "corpus_docs": len({s[0].doc_id for s in RETRIEVER.sentences}),
        "corpus_sentences": len(RETRIEVER.sentences),
    })


@app.post("/api/verify")
def verify():
    """Verify an answer against the corpus, producing a re-checkable proof graph.

    Body: { question, answer, use_llm_decompose?: bool }
    If `answer` is omitted and the LLM is available, Claude generates one first.
    """
    data = request.get_json(force=True) or {}
    question = (data.get("question") or "").strip()
    answer = (data.get("answer") or "").strip()
    use_llm = bool(data.get("use_llm_decompose"))

    if not answer:
        if question and llm.available():
            answer = llm.llm_answer(question) or ""
        if not answer:
            return jsonify({"error": "Provide an answer to verify (or set an "
                                     "ANTHROPIC_API_KEY to generate one)."}), 400

    # Choose the decomposer: Claude (cleaner, pronoun-resolved) or heuristic.
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
    return jsonify(result)


@app.post("/api/corpus")
def add_doc():
    """Add a source document to the live corpus (rebuilds the index)."""
    global RETRIEVER
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "empty document"}), 400
    docs = [Document(s[0].doc_id, s[0].title, s[0].source, s[1])
            for s in RETRIEVER.sentences]
    # Re-derive unique source docs, then append the new one.
    seen, uniq = set(), []
    for d in docs:
        if d.doc_id not in seen:
            seen.add(d.doc_id)
            # reconstruct full text from sentences of that doc
            full = " ".join(s[1] for s in RETRIEVER.sentences if s[0].doc_id == d.doc_id)
            uniq.append(Document(d.doc_id, d.title, d.source, full))
    new_id = "user_" + str(len(seen))
    uniq.append(Document(new_id, data.get("title", "User source"),
                         data.get("source", "user-provided"), text))
    RETRIEVER = Retriever(uniq)
    return jsonify({"added": new_id,
                    "corpus_docs": len({s[0].doc_id for s in RETRIEVER.sentences})})


if __name__ == "__main__":
    import os
    # Railway (and most PaaS) inject PORT and need 0.0.0.0. Local dev → 5070.
    port = int(os.environ.get("PORT", "5070"))
    debug = os.environ.get("FLASK_DEBUG", "") in ("1", "true", "True")
    app.run(host="0.0.0.0", port=port, debug=debug)
