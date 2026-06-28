# Proof-Carrying Answers: Verifiable AI
### A Moonshot Paper

---

## 1. The problem humanity has misunderstood

The defining anxiety of the AI era is that the machine lies — confidently,
fluently, and unpredictably. The entire field's response has been to make models
that hallucinate *less*: better training data, RLHF, retrieval augmentation,
constitutional methods, ever-larger models. Billions of dollars are spent
chasing a single asymptote — a model so truthful you can finally trust it.

This is the wrong target, and it is wrong at the level of *kind*, not degree.

A language model is a black box. Its output is a sample from a distribution we
cannot inspect, over a process we cannot audit. "Truthfulness" is therefore not
a property you can ever *prove* about a given answer — only a probability you can
push toward 1 and hope. No matter how good the model gets, every individual
answer still arrives as an article of faith. You are asked to trust the speaker
because the speaker is usually right. In medicine, law, finance, and science,
"usually right, no way to check which" is not a foundation you can build on. It
is the precise property that makes AI inadmissible in exactly the domains where
it would matter most.

We have been trying to build a more trustworthy oracle. The oracle is the
problem.

## 2. Why existing solutions are insufficient

Every mainstream approach accepts the premise that the *generator* must be the
locus of trust, and tries to make it more trustworthy:

- **RLHF and fine-tuning** shift the output distribution toward truthful-sounding
  text. They cannot certify any single output, and they make the model *more*
  confidently wrong when it is wrong — fluency is optimized alongside accuracy.
- **Retrieval-augmented generation** puts sources *into* the prompt, but the
  model is still free to ignore, misread, or contradict them in its answer.
  Retrieval improves the odds; it proves nothing about the result.
- **Confidence scores and "I'm not sure" calibration** ask the black box to
  grade its own homework. A system that hallucinates facts can hallucinate its
  confidence in them.
- **Citations bolted onto chatbots** are notoriously unfaithful — the link is
  often real and the claim it supposedly supports is not in it. A citation that
  is never checked is decoration.

All of these are optimizations of the *trust-the-generator* paradigm. None
produces an artifact you can independently verify. The output of GPT-class
systems is, structurally, an assertion without a proof.

## 3. The first-principles insight

Start from the objective: we want answers we can *trust*, and trust at scale
means *verifiability*, not faith. Now ask what verifiability actually requires —
and notice that it does **not** require a trustworthy generator at all.

Cryptography solved an analogous problem decades ago. You do not trust a
certificate authority because it is honest; you trust a TLS connection because it
carries a **proof** you can check. Mathematics is not believed because
mathematicians are reliable; a theorem carries a **proof** any skeptic can
re-run. In both cases, trust was relocated from a fallible *speaker* to a
verifiable *artifact*.

Apply the same move to AI. An answer should not be a bare assertion — it should
be **proof-carrying**:

1. **Decompose** the answer into atomic claims, each independently checkable.
2. **Bind** each claim to retrieved evidence.
3. **Verify** each claim against its evidence — `SUPPORTED`, `REFUTED`, or
   `UNSUPPORTED` — by an explicit, auditable entailment procedure.
4. **Withhold** what cannot be supported. Absence of evidence is not evidence;
   an unverifiable claim is dropped from the final answer rather than asserted.

The generator becomes untrusted by design. It can be as creative, as fallible,
as black-box as you like — because nothing it says enters the final answer until
it has been independently checked, and the check ships *with* the answer as a
graph anyone can re-run. The hallucination problem is not *reduced*; it is
*contained*, the way memory-safety contains an entire class of bugs rather than
patching them one at a time.

## 4. Scientific and technical foundations

The prototype implements the full pipeline from first principles, with zero ML
dependencies, so the route from text to verdict is auditable end to end:

- **Decomposition** (`decompose`) splits an answer into atomic claims at sentence
  and clause boundaries; the optional Claude layer produces cleaner,
  pronoun-resolved claims but is never required.
- **Retrieval** (`Retriever`) is a sentence-level TF-IDF cosine index over a
  source corpus — pure-Python, inspectable.
- **Entailment** (`verify_claim`) is the heart of the system. The key insight is
  that a refutation must concern *the same fact*: a conflict only counts when the
  evidence shares the claim's **subject** (entities) *and* **predicate** (the
  asserted relation). This is what stops a different fact with a different year
  from masquerading as a refutation. Light stemming aligns morphological variants
  ("received"/"receive"); salient-value comparison (years, quantities, word- and
  digit-numbers) drives the conflict test; year-consistency gates support.
- **Proof graph** (`ProofGraph`) records claim → evidence → verdict, computes a
  trust score, and reconstructs a *verified answer* from supported claims only.
- **Independent re-check** (`recheck_proof`) re-runs every verdict from scratch —
  the property that makes the answer *proof-carrying* rather than merely
  annotated. On the demo set, all nine verdicts are correct and every proof
  reproduces.

## 5. Long-term implications of success

If answers can carry proofs, the consequences compound across every domain
currently locked out of AI by the trust problem:

- **Medicine** — a clinical decision-support answer where every claim is bound to
  a citation and a verdict, and unverifiable claims are withheld rather than
  hallucinated, is something a regulator and a physician can actually accept.
- **Law and finance** — AI output becomes admissible when each assertion arrives
  with a checkable evidentiary basis. "The model said so" is replaced by "here is
  the proof, re-run it."
- **Science** — automated literature synthesis that *withholds* what the
  literature doesn't support is the difference between a research accelerant and
  a citation-laundering machine.
- **The information ecosystem** — proof-carrying becomes a *format*. A verified
  answer can be re-checked by anyone, the way a TLS certificate or a signed
  commit can. Verifiability stops being a feature and becomes an expectation —
  the way HTTPS went from optional to assumed.

The deepest implication is cultural: we stop asking "is the AI trustworthy?" — an
unanswerable question about a black box — and start asking "does this answer
carry a proof?" — a decidable question about an artifact.

## 6. The future this attempts to create

A world where an AI answer is not a thing you believe but a thing you can
**check**. Where the burden of trust sits on a portable, re-runnable proof
instead of on the reputation of a model vendor. Where the most powerful
generators can be deployed in the highest-stakes settings precisely *because*
they are never trusted — only verified.

The trust-the-oracle paradigm gave us fluency without accountability. This is a
bet that the opposite is the real frontier: not a model that asks for your faith,
but an answer that earns your verification — and hands you the receipt.

---

*Prototype: `engine.py` (verifier + proof graph + re-checker), `app.py`
(verification API), `static/` (UI). Run `python app.py`.*
