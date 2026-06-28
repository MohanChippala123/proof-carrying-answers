"""
Generator layer for Proof-Carrying Answers.
===========================================

This is the *untrusted* generator. It uses a small, local, CPU-only model
(see local_model.py) — cheap enough to run on a Railway box with no GPU and no
paid API. It does two optional jobs:

  (a) decompose an answer into cleaner, pronoun-resolved atomic claims, and
  (b) generate an answer to verify.

Both gracefully return None when the local model isn't enabled or fails to load,
so the app always falls back to the fully-offline deterministic path in
engine.py. Nothing produced here is trusted — every claim is independently
verified against evidence before it can enter the final answer.
"""

from __future__ import annotations

import json
from typing import List, Optional

import local_model

# Reported in the UI status line.
MODEL = local_model.state()["model"]


def available() -> bool:
    return local_model.available()


def warmup():
    local_model.warmup_async()


def llm_decompose(answer: str) -> Optional[List[str]]:
    """Use the local model to split an answer into atomic, self-contained claims.

    Returns None on any failure so the caller falls back to engine.decompose.
    """
    prompt = (
        "Decompose the following answer into atomic, independently checkable "
        "factual claims. Resolve pronouns so each claim stands alone. Return ONLY "
        "a JSON array of strings and nothing else.\n\nANSWER:\n" + answer
    )
    text = local_model.generate(prompt, max_tokens=512)
    if not text:
        return None
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return None
    try:
        claims = json.loads(text[start: end + 1])
    except Exception:
        return None
    return [c.strip() for c in claims if isinstance(c, str) and c.strip()] or None


def llm_answer(question: str) -> Optional[str]:
    """Use the local model to answer a question (the thing we then verify)."""
    return local_model.generate(question, max_tokens=512, temperature=0.4)
