"""
Evidence corpus + demo scenarios for Proof-Carrying Answers.

The corpus is a small set of trustworthy source passages with provenance. The
demo answers deliberately contain a mix of true claims, a planted falsehood, and
an unsupported embellishment -- so the verifier visibly does all three things:
confirm, refute, and withhold.

In production the corpus is replaced by a live retrieval index (web, internal
docs, a vetted knowledge base). The verification machinery is identical.
"""

from __future__ import annotations

from typing import List

from engine import Document


def build_default_corpus() -> List[Document]:
    return [
        Document(
            "nobel_einstein", "Albert Einstein - Nobel Prize",
            "https://www.nobelprize.org/prizes/physics/1921/einstein/facts/",
            "Albert Einstein was awarded the Nobel Prize in Physics in 1921. "
            "He received the prize for his discovery of the law of the photoelectric effect. "
            "The 1921 Nobel Prize in Physics was awarded to Albert Einstein alone. "
            "Einstein did not receive the Nobel Prize for his theory of relativity.",
        ),
        Document(
            "penn_capital", "Pennsylvania - State Facts",
            "https://www.pa.gov/",
            "Harrisburg is the capital of Pennsylvania. "
            "Philadelphia is the largest city in Pennsylvania but is not the state capital. "
            "Harrisburg has served as the state capital since 1812.",
        ),
        Document(
            "gw_facts", "George Washington - Biography",
            "https://www.whitehouse.gov/about-the-white-house/presidents/george-washington/",
            "George Washington was the first President of the United States. "
            "He served two terms in office from 1789 to 1797. "
            "Washington presided over the Constitutional Convention of 1787.",
        ),
        Document(
            "speed_light", "Physical Constants",
            "https://physics.nist.gov/cgi-bin/cuu/Value?c",
            "The speed of light in vacuum is exactly 299792458 metres per second. "
            "It is a fundamental physical constant denoted c.",
        ),
        Document(
            "everest", "Mount Everest - Geography",
            "https://en.wikipedia.org/wiki/Mount_Everest",
            "Mount Everest is the highest mountain above sea level, at 8849 metres. "
            "It is located in the Himalayas on the border between Nepal and China.",
        ),
        Document(
            "dna_structure", "DNA - Molecular Biology",
            "https://www.nature.com/scitable/topicpage/dna-structure",
            "The double-helix structure of DNA was described by James Watson and Francis Crick in 1953. "
            "Their model built on X-ray diffraction data produced by Rosalind Franklin. "
            "DNA is composed of four nucleotide bases: adenine, thymine, guanine and cytosine.",
        ),
        Document(
            "great_wall", "Great Wall of China - Facts",
            "https://whc.unesco.org/en/list/438/",
            "The Great Wall of China is not a single continuous wall but a series of fortifications. "
            "It is not visible to the naked eye from space, contrary to popular belief.",
        ),
    ]


# Each demo answer is written as clean sentences so the heuristic decomposer
# yields one atomic claim per sentence. The verifier should mark them as noted.
DEMO = [
    {
        "id": "einstein",
        "question": "What did Albert Einstein win the Nobel Prize for, and when?",
        # T, F, U  -> SUPPORTED, REFUTED, UNSUPPORTED
        "answer": (
            "Albert Einstein won the Nobel Prize in Physics in 1921. "
            "He received the prize for his theory of relativity. "
            "He shared the award with Niels Bohr."
        ),
        "note": "1921 is correct; 'theory of relativity' is false (photoelectric "
                "effect); the shared-with-Bohr claim is an unsupported fabrication.",
    },
    {
        "id": "washington",
        "question": "Tell me about George Washington's presidency.",
        "answer": (
            "George Washington was the first President of the United States. "
            "He served from 1789 to 1797. "
            "He served three terms in office."
        ),
        "note": "First two true; 'three terms' is refuted (two terms).",
    },
    {
        "id": "dna",
        "question": "Who discovered the structure of DNA?",
        "answer": (
            "The double helix structure of DNA was described by Watson and Crick in 1953. "
            "Their work relied on X-ray data from Rosalind Franklin. "
            "Watson and Crick won the Nobel Prize for this work in 1962."
        ),
        "note": "First two supported; the 1962 Nobel claim is not in the corpus, "
                "so it is withheld as UNSUPPORTED (true in reality, but unverifiable "
                "here -- the system never asserts what it cannot check).",
    },
]
