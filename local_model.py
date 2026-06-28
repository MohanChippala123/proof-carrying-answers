"""
Local small-model backend for Proof-Carrying Answers.
=====================================================

Runs a small, CPU-only, quantized GGUF model via llama-cpp-python — sized to fit
a Railway box (8 vCPU / 8 GB RAM) with no GPU and no paid API. Default model is
Qwen2.5-1.5B-Instruct (Apache-2.0), ~1 GB at Q4_K_M, which generates and
decomposes comfortably on CPU.

The point this makes for the project: the local model is *cheap and unreliable*
— it will hallucinate. That is fine, because nothing it produces enters the final
answer until the deterministic verifier in engine.py has checked it against
evidence. A small hallucinating model wrapped in verification is more trustworthy
than a large one without it. This module is the generator; it is never trusted.

Everything here is lazy and guarded: if llama-cpp-python isn't installed, the
model can't be fetched, or ENABLE_LOCAL_LLM isn't set, every function returns
None and the app falls back to the fully-offline deterministic path.

Configuration (env vars):
    ENABLE_LOCAL_LLM   "1" to turn the model on (default off → deterministic only)
    LOCAL_MODEL_REPO   HF repo with the GGUF   (default Qwen/Qwen2.5-1.5B-Instruct-GGUF)
    LOCAL_MODEL_FILE   GGUF filename           (default qwen2.5-1.5b-instruct-q4_k_m.gguf)
    MODEL_N_CTX        context window          (default 4096)
    MODEL_N_THREADS    CPU threads             (default: all cores)
"""

from __future__ import annotations

import os
import threading
from typing import Optional

_REPO = os.environ.get("LOCAL_MODEL_REPO", "Qwen/Qwen2.5-1.5B-Instruct-GGUF")
_FILE = os.environ.get("LOCAL_MODEL_FILE", "qwen2.5-1.5b-instruct-q4_k_m.gguf")
_N_CTX = int(os.environ.get("MODEL_N_CTX", "4096"))
_N_THREADS = int(os.environ.get("MODEL_N_THREADS", str(os.cpu_count() or 4)))

_LOCK = threading.Lock()
_LLM = None          # the loaded Llama instance
_STATE = "disabled"  # disabled | loading | ready | error
_ERROR = ""


def enabled() -> bool:
    return os.environ.get("ENABLE_LOCAL_LLM", "") in ("1", "true", "True", "yes")


def state() -> dict:
    return {"enabled": enabled(), "state": _STATE, "model": f"{_REPO}/{_FILE}",
            "error": _ERROR, "threads": _N_THREADS, "n_ctx": _N_CTX}


def _load():
    """Load the model once (downloads the GGUF on first call). Guarded."""
    global _LLM, _STATE, _ERROR
    if _LLM is not None or _STATE == "error":
        return _LLM
    with _LOCK:
        if _LLM is not None or _STATE == "error":
            return _LLM
        if not enabled():
            return None
        _STATE = "loading"
        try:
            from llama_cpp import Llama
            _LLM = Llama.from_pretrained(
                repo_id=_REPO,
                filename=_FILE,
                n_ctx=_N_CTX,
                n_threads=_N_THREADS,
                verbose=False,
            )
            _STATE = "ready"
        except Exception as e:  # missing lib, download failure, OOM, etc.
            _STATE = "error"
            _ERROR = f"{type(e).__name__}: {e}"
            _LLM = None
        return _LLM


def warmup_async():
    """Kick off model loading in the background so the first request is fast."""
    if enabled() and _STATE == "disabled":
        threading.Thread(target=_load, daemon=True).start()


def available() -> bool:
    if not enabled():
        return False
    return _load() is not None


def generate(prompt: str, max_tokens: int = 512, temperature: float = 0.2) -> Optional[str]:
    """Run a chat completion on the local model. Returns None on any failure."""
    llm = _load()
    if llm is None:
        return None
    try:
        out = llm.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return (out["choices"][0]["message"]["content"] or "").strip() or None
    except Exception:
        return None
