"""
Proof-Carrying Answers -- verification engine
=============================================

The thesis
----------
We have been trying to make language models *hallucinate less*. That is the
wrong target: you cannot prove a black box will not lie. The correct move is to
stop trusting the generator and instead **verify the output**.

Every answer is decomposed into atomic, independently-checkable claims. Each
claim is bound to retrieved evidence and assigned a verdict by a transparent
entailment check. The answer then ships with a **proof graph**: claim ->
evidence -> verdict, which any third party can re-run. Claims that cannot be
supported are *withheld* rather than asserted. An answer becomes a thing you can
audit, not a thing you must trust.

This module is the auditable core. It has zero ML dependencies -- decomposition,
retrieval (TF-IDF cosine), and entailment are all implemented from first
principles so the route from text to verdict is fully transparent. An optional
LLM layer (llm.py) can replace the heuristic decomposer / NLI when an API key is
present, but is never required.

Pipeline:
    answer text
        -> decompose()        atomic claims
        -> Retriever.search()  evidence sentences w/ provenance
        -> verify_claim()      SUPPORTED | REFUTED | UNSUPPORTED + citations
        -> ProofGraph          re-checkable structure
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class Verdict(str, Enum):
    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass
class EvidenceSpan:
    doc_id: str
    title: str
    source: str          # url / citation
    sentence: str
    score: float

    def as_dict(self) -> dict:
        return {
            "doc_id": self.doc_id, "title": self.title, "source": self.source,
            "sentence": self.sentence, "score": round(self.score, 4),
        }


@dataclass
class ClaimVerdict:
    claim: str
    verdict: Verdict
    confidence: float
    support: List[EvidenceSpan] = field(default_factory=list)
    refute: List[EvidenceSpan] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "claim": self.claim,
            "verdict": self.verdict.value,
            "confidence": round(self.confidence, 3),
            "support": [e.as_dict() for e in self.support],
            "refute": [e.as_dict() for e in self.refute],
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------

_STOP = set("""a an the of to in on at for and or but is are was were be been being
as by with from that this these those it its their his her he she they we you i
which who whom whose what when where why how not no nor than then so such into
about over under between among during after before above below up down out
""".split())

_WORD = re.compile(r"[A-Za-z0-9']+")


def tokenize(text: str) -> List[str]:
    return [w.lower() for w in _WORD.findall(text)]


def stem(w: str) -> str:
    """Crude but consistent suffix stripper so 'received'/'receive' and
    'prize'/'prizes' align. Good enough to make predicate comparison robust;
    not meant to be linguistically perfect."""
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            w = w[: -len(suf)]
            break
    if len(w) > 3 and w.endswith("e"):
        w = w[:-1]
    return w


def content_tokens(text: str) -> List[str]:
    return [stem(t) for t in tokenize(text) if t not in _STOP and len(t) > 1]


def split_sentences(text: str) -> List[str]:
    # Lightweight sentence splitter that respects common abbreviations.
    text = re.sub(r"\s+", " ", text.strip())
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    return [p.strip() for p in parts if p.strip()]


# Salient values: years, numbers, and capitalized entity tokens. These are what
# a refutation usually turns on (a wrong year, a wrong name, a wrong quantity).
_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_NUM = re.compile(r"\b\d+(?:\.\d+)?\b")
_ENTITY = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b")

_NEG = set("not no never none cannot can't won't didn't isn't aren't wasn't "
           "weren't doesn't don't without fails false incorrect".split())

# Cardinal word-numbers, so "three terms" can conflict with "two terms".
_WORDNUM = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "eleven": "11", "twelve": "12", "twenty": "20", "thirty": "30",
    "forty": "40", "fifty": "50", "hundred": "100", "thousand": "1000",
}


def salient_values(text: str) -> Dict[str, set]:
    years = set(_YEAR.findall(text))
    nums = set(_NUM.findall(text)) - years
    for tok in tokenize(text):
        if tok in _WORDNUM:
            nums.add(_WORDNUM[tok])
    # Entity tokens, lowercased content words of capitalized spans.
    ents = set()
    for m in _ENTITY.findall(text):
        for tok in content_tokens(m):
            ents.add(tok)
    return {"years": years, "nums": nums, "ents": ents}


def predicate_tokens(text: str, ents: set) -> set:
    """Content tokens that are NOT part of an entity name -- the predicate."""
    return {t for t in content_tokens(text) if t not in ents}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def has_negation(text: str) -> bool:
    toks = tokenize(text)
    return any(t in _NEG for t in toks)


# ---------------------------------------------------------------------------
# Claim decomposition
# ---------------------------------------------------------------------------

# Conjunction / relative-clause boundaries that usually separate atomic claims.
_CLAUSE_SPLIT = re.compile(
    r",\s*(?:and|but|which|who|an award|a prize|where|while)\b|;\s*",
    re.IGNORECASE,
)


def decompose(answer: str) -> List[str]:
    """Split an answer into atomic, independently-checkable claims.

    Heuristic, transparent, and good enough that each output clause carries a
    single assertion. The optional LLM decomposer (llm.py) supersedes this when
    available, but this keeps the system fully functional with no dependencies.
    """
    claims: List[str] = []
    for sent in split_sentences(answer):
        # Further split compound sentences on clause boundaries.
        pieces = _CLAUSE_SPLIT.split(sent)
        pieces = [p.strip(" ,;") for p in pieces if p and p.strip(" ,;")]
        if len(pieces) <= 1:
            claims.append(sent)
            continue
        # Re-attach a subject to trailing clauses that lost it (best-effort).
        subject = pieces[0].split()[0:2]
        for i, p in enumerate(pieces):
            if i == 0:
                claims.append(p if p.endswith((".", "!", "?")) else p + ".")
            else:
                # If clause starts lowercase and lacks a subject noun, prepend.
                first = p.split()[0].lower() if p.split() else ""
                if first in ("for", "in", "with", "to", "the", "it", "an", "a"):
                    p = " ".join(subject) + " " + p
                claims.append(p if p.endswith((".", "!", "?")) else p + ".")
    # Drop trivially short fragments.
    return [c for c in claims if len(content_tokens(c)) >= 2]


# ---------------------------------------------------------------------------
# Evidence retrieval (TF-IDF cosine, pure python)
# ---------------------------------------------------------------------------

@dataclass
class Document:
    doc_id: str
    title: str
    source: str
    text: str


class Retriever:
    """Sentence-level TF-IDF retriever over a document corpus."""

    def __init__(self, docs: List[Document]):
        self.sentences: List[Tuple[Document, str]] = []
        for d in docs:
            for s in split_sentences(d.text):
                self.sentences.append((d, s))
        self._build_index()

    def _build_index(self):
        self.df: Counter = Counter()
        self.tfs: List[Counter] = []
        for _, s in self.sentences:
            tf = Counter(content_tokens(s))
            self.tfs.append(tf)
            for term in tf:
                self.df[term] += 1
        self.N = max(1, len(self.sentences))
        self.idf = {t: math.log(1 + self.N / (1 + df)) for t, df in self.df.items()}
        self.norms = [self._norm(tf) for tf in self.tfs]

    def _vec(self, tf: Counter) -> Dict[str, float]:
        return {t: c * self.idf.get(t, math.log(1 + self.N)) for t, c in tf.items()}

    def _norm(self, tf: Counter) -> float:
        v = self._vec(tf)
        return math.sqrt(sum(x * x for x in v.values())) or 1.0

    def search(self, query: str, k: int = 5) -> List[EvidenceSpan]:
        qtf = Counter(content_tokens(query))
        qv = self._vec(qtf)
        qn = math.sqrt(sum(x * x for x in qv.values())) or 1.0
        scored = []
        for i, (doc, sent) in enumerate(self.sentences):
            dv = self._vec(self.tfs[i])
            dot = sum(qv.get(t, 0.0) * dv.get(t, 0.0) for t in qv)
            sim = dot / (qn * self.norms[i])
            if sim > 0:
                scored.append(EvidenceSpan(doc.doc_id, doc.title, doc.source, sent, sim))
        scored.sort(key=lambda e: e.score, reverse=True)
        return scored[:k]


# ---------------------------------------------------------------------------
# Entailment / verification
# ---------------------------------------------------------------------------

def _overlap(a: str, b: str) -> float:
    ta, tb = set(content_tokens(a)), set(content_tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def verify_claim(claim: str, evidence: List[EvidenceSpan],
                 support_th: float = 0.18) -> ClaimVerdict:
    """Decide SUPPORTED / REFUTED / UNSUPPORTED for a claim against evidence.

    Transparent logic:
      * Find the evidence sentence most topically aligned with the claim.
      * REFUTED if a well-aligned sentence carries a *conflicting salient value*
        (different year/number/entity for the same context) or opposite polarity.
      * SUPPORTED if a well-aligned sentence shares the claim's salient values
        and polarity with sufficient overlap.
      * UNSUPPORTED otherwise (the honest default -- absence of evidence is not
        evidence; the claim is withheld, not asserted).
    """
    if not evidence:
        return ClaimVerdict(claim, Verdict.UNSUPPORTED, 0.0,
                            reason="No evidence retrieved for this claim.")

    cv = salient_values(claim)
    cneg = has_negation(claim)
    cpred = predicate_tokens(claim, cv["ents"])

    best_support: Optional[EvidenceSpan] = None
    best_support_score = 0.0
    best_refute: Optional[EvidenceSpan] = None
    best_refute_score = 0.0
    refute_reason = ""

    for ev in evidence:
        ov = _overlap(claim, ev.sentence)
        ev_vals = salient_values(ev.sentence)
        eneg = has_negation(ev.sentence)
        epred = predicate_tokens(ev.sentence, ev_vals["ents"])

        # Are we even talking about the same thing? A conflict only counts when
        # the evidence shares the claim's SUBJECT (entities) and PREDICATE
        # (the relation being asserted). This is what stops a different fact
        # with a different year from masquerading as a refutation.
        subj = None if not cv["ents"] else len(cv["ents"] & ev_vals["ents"]) / len(cv["ents"])
        pred_ov = _jaccard(cpred, epred)
        same_subject = (subj is None) or (subj >= 0.5)

        year_conflict = (cv["years"] and ev_vals["years"]
                         and not (cv["years"] & ev_vals["years"]))
        num_conflict = (cv["nums"] and ev_vals["nums"]
                        and not (cv["nums"] & ev_vals["nums"]))
        value_conflict = (year_conflict or num_conflict) and same_subject and pred_ov >= 0.30
        polarity_conflict = ((cneg != eneg) and same_subject
                             and pred_ov >= 0.50 and ov >= 0.30)

        if value_conflict or polarity_conflict:
            rscore = ov + 0.25
            if rscore > best_refute_score:
                best_refute_score = rscore
                best_refute = ev
                if year_conflict and value_conflict:
                    refute_reason = (
                        f"Evidence gives a different year "
                        f"({', '.join(sorted(ev_vals['years']))}) for the same fact "
                        f"than the claim ({', '.join(sorted(cv['years']))}).")
                elif num_conflict and value_conflict:
                    refute_reason = (
                        f"Evidence gives a different quantity "
                        f"({', '.join(sorted(ev_vals['nums']))}) for the same fact "
                        f"than the claim ({', '.join(sorted(cv['nums']))}).")
                else:
                    refute_reason = ("Evidence asserts the opposite of the claim for "
                                     "the same subject and relation.")
            continue

        # Supporting alignment. If the claim pins a year, the support must share
        # it -- otherwise it is a different event and cannot count as support.
        if cv["years"] and not (cv["years"] & ev_vals["years"]):
            continue
        val_bonus = 0.0
        if cv["years"] and (cv["years"] & ev_vals["years"]):
            val_bonus += 0.25
        if cv["nums"] and (cv["nums"] & ev_vals["nums"]):
            val_bonus += 0.15
        sscore = ov + val_bonus
        if sscore > best_support_score:
            best_support_score = sscore
            best_support = ev

    # Decision. A confident refutation outranks weak support.
    if best_refute and best_refute_score >= support_th + 0.08:
        conf = min(0.99, best_refute_score)
        return ClaimVerdict(claim, Verdict.REFUTED, conf,
                            support=[best_support] if best_support else [],
                            refute=[best_refute], reason=refute_reason)

    if best_support and best_support_score >= support_th:
        conf = min(0.99, best_support_score + 0.3)
        return ClaimVerdict(claim, Verdict.SUPPORTED, conf,
                            support=[best_support],
                            reason="A retrieved source entails this claim.")

    return ClaimVerdict(claim, Verdict.UNSUPPORTED,
                        min(0.5, best_support_score),
                        support=[best_support] if best_support else [],
                        reason=("No retrieved source sufficiently entails this claim; "
                                "it is withheld rather than asserted."))


# ---------------------------------------------------------------------------
# Proof graph -- the re-checkable artifact
# ---------------------------------------------------------------------------

@dataclass
class ProofGraph:
    question: str
    answer: str
    claims: List[ClaimVerdict]

    @property
    def supported(self) -> int:
        return sum(c.verdict == Verdict.SUPPORTED for c in self.claims)

    @property
    def refuted(self) -> int:
        return sum(c.verdict == Verdict.REFUTED for c in self.claims)

    @property
    def unsupported(self) -> int:
        return sum(c.verdict == Verdict.UNSUPPORTED for c in self.claims)

    def trust_score(self) -> float:
        """Fraction of claims that survive verification, penalizing refutations."""
        n = len(self.claims) or 1
        return round((self.supported - self.refuted) / n, 3)

    def verified_answer(self) -> str:
        """Reconstruct the answer using only SUPPORTED claims -- the part you
        can actually stand behind."""
        kept = [c.claim for c in self.claims if c.verdict == Verdict.SUPPORTED]
        return " ".join(kept) if kept else "(no claim could be verified)"

    def as_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.answer,
            "claims": [c.as_dict() for c in self.claims],
            "summary": {
                "supported": self.supported,
                "refuted": self.refuted,
                "unsupported": self.unsupported,
                "trust_score": self.trust_score(),
            },
            "verified_answer": self.verified_answer(),
        }


def build_proof(question: str, answer: str, retriever: Retriever,
                decomposer=decompose) -> ProofGraph:
    """Full pipeline: answer -> claims -> evidence -> verdicts -> proof graph."""
    claims = decomposer(answer)
    verdicts = []
    for c in claims:
        ev = retriever.search(c, k=5)
        verdicts.append(verify_claim(c, ev))
    return ProofGraph(question, answer, verdicts)


def recheck_proof(proof: ProofGraph, retriever: Retriever) -> bool:
    """Independent re-verification: a third party can re-run the proof and
    confirm every verdict reproduces. This is what makes the answer
    *proof-carrying* rather than merely annotated.
    """
    for cv in proof.claims:
        ev = retriever.search(cv.claim, k=5)
        fresh = verify_claim(cv.claim, ev)
        if fresh.verdict != cv.verdict:
            return False
    return True


if __name__ == "__main__":
    from corpus import build_default_corpus, DEMO

    retr = Retriever(build_default_corpus())
    for demo in DEMO:
        proof = build_proof(demo["question"], demo["answer"], retr)
        print("\nQ:", demo["question"])
        for c in proof.claims:
            print(f"  [{c.verdict.value:11}] {c.claim}")
        print("  trust_score:", proof.trust_score(),
              "| recheck:", recheck_proof(proof, retr))
