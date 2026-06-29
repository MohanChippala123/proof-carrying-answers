"""
Evidence corpus + demo scenarios for Proof-Carrying Answers.

Each demo answer deliberately mixes:
  T  = true claim  → verifier marks SUPPORTED
  F  = planted lie → verifier marks REFUTED  (with citation)
  U  = unverifiable embellishment → verifier marks UNSUPPORTED (withheld, not asserted)

This is the core thesis made visceral: confident, fluent, mixed-truth AI output
is decomposed and every claim labelled. The false one is struck through.
The unverifiable one is withheld.
"""

from __future__ import annotations
from typing import List
from engine import Document


def build_default_corpus() -> List[Document]:
    return [
        Document(
            "nobel_einstein", "Albert Einstein – Nobel Prize Facts",
            "https://www.nobelprize.org/prizes/physics/1921/einstein/facts/",
            "Albert Einstein was awarded the Nobel Prize in Physics in 1921. "
            "He received the prize for his discovery of the law of the photoelectric effect. "
            "The 1921 Nobel Prize in Physics was awarded to Albert Einstein alone. "
            "Einstein did not receive the Nobel Prize for his theory of relativity. "
            "Einstein did not share the 1921 prize with any other scientist.",
        ),
        Document(
            "penn_capital", "Pennsylvania – State Capital",
            "https://www.pa.gov/",
            "Harrisburg is the capital of Pennsylvania. "
            "Philadelphia is the largest city in Pennsylvania but is not the state capital. "
            "Harrisburg has served as the state capital since 1812.",
        ),
        Document(
            "gw_facts", "George Washington – Presidency",
            "https://www.whitehouse.gov/about-the-white-house/presidents/george-washington/",
            "George Washington was the first President of the United States. "
            "He served two terms in office from 1789 to 1797. "
            "Washington did not serve three terms. "
            "Washington presided over the Constitutional Convention of 1787.",
        ),
        Document(
            "speed_light", "Speed of Light – Physical Constant",
            "https://physics.nist.gov/cgi-bin/cuu/Value?c",
            "The speed of light in vacuum is exactly 299792458 metres per second. "
            "It is a fundamental physical constant denoted c. "
            "Nothing travels faster than the speed of light in vacuum.",
        ),
        Document(
            "everest", "Mount Everest – Geography",
            "https://en.wikipedia.org/wiki/Mount_Everest",
            "Mount Everest is the highest mountain above sea level, at 8849 metres. "
            "It is located in the Himalayas on the border between Nepal and China. "
            "The height of 8849 metres was confirmed by a 2020 survey.",
        ),
        Document(
            "dna_structure", "DNA – Double Helix Structure",
            "https://www.nature.com/scitable/topicpage/dna-structure",
            "The double-helix structure of DNA was described by James Watson and Francis Crick in 1953. "
            "Their model built on X-ray diffraction data produced by Rosalind Franklin. "
            "DNA is composed of four nucleotide bases: adenine, thymine, guanine and cytosine.",
        ),
        Document(
            "great_wall", "Great Wall of China – Facts",
            "https://whc.unesco.org/en/list/438/",
            "The Great Wall of China is not a single continuous wall but a series of fortifications. "
            "It is not visible to the naked eye from space, contrary to popular belief.",
        ),
        Document(
            "apollo11", "Apollo 11 – Moon Landing 1969",
            "https://www.nasa.gov/mission_pages/apollo/apollo-11.html",
            "Apollo 11 landed on the Moon on July 20, 1969. "
            "Neil Armstrong was the first human to walk on the Moon. "
            "Buzz Aldrin also walked on the lunar surface during the mission. "
            "Michael Collins did not walk on the lunar surface during the mission. "
            "Collins remained in the Command Module and did not walk on the lunar surface. "
            "Armstrong and Aldrin spent about two hours walking on the lunar surface.",
        ),
        Document(
            "marie_curie", "Marie Curie – Nobel Prizes",
            "https://www.nobelprize.org/prizes/themes/marie-and-pierre-curie-and-the-discovery-of-polonium-and-radium/",
            "Marie Curie won the Nobel Prize in Physics in 1903. "
            "She won a second Nobel Prize in Chemistry in 1911. "
            "Marie Curie won Nobel Prizes in two different sciences. "
            "Marie Curie was the first woman to win a Nobel Prize. "
            "Her research focused on radioactivity and she discovered the elements polonium and radium.",
        ),
        Document(
            "titanic", "RMS Titanic – Sinking",
            "https://en.wikipedia.org/wiki/Titanic",
            "The RMS Titanic sank in the North Atlantic Ocean on April 15, 1912, after striking an iceberg. "
            "The Titanic sank in 1912. "
            "The ship sank on its maiden voyage from Southampton to New York City. "
            "More than 1500 people died, making it one of the deadliest peacetime maritime disasters.",
        ),
    ]


DEMO = [
    {
        "id": "einstein",
        "question": "What did Albert Einstein win the Nobel Prize for, and when?",
        "answer": (
            "Albert Einstein won the Nobel Prize in Physics in 1921. "
            "He received the prize for his theory of relativity. "
            "He shared the award with Niels Bohr."
        ),
        "note": "1921 ✓  |  'theory of relativity' ✗ (photoelectric effect)  |  'shared with Bohr' ⚠ withheld",
    },
    {
        "id": "washington",
        "question": "Tell me about George Washington's presidency.",
        "answer": (
            "George Washington was the first President of the United States. "
            "He served from 1789 to 1797. "
            "He served three terms in office."
        ),
        "note": "First two ✓  |  'three terms' ✗ (two terms)",
    },
    {
        "id": "dna",
        "question": "Who discovered the structure of DNA?",
        "answer": (
            "The double helix structure of DNA was described by Watson and Crick in 1953. "
            "Their work relied on X-ray data from Rosalind Franklin. "
            "Watson and Crick won the Nobel Prize for this work in 1962."
        ),
        "note": "First two ✓  |  '1962 Nobel' ⚠ not in corpus — withheld (never asserted without evidence)",
    },
    {
        "id": "apollo11",
        "question": "Who walked on the Moon during Apollo 11?",
        "answer": (
            "Apollo 11 landed on the Moon on July 20, 1969. "
            "Neil Armstrong was the first human to walk on the Moon. "
            "Michael Collins also walked on the lunar surface during the mission."
        ),
        "note": "First two ✓  |  'Collins walked' ✗ (he stayed in the Command Module)",
    },
    {
        "id": "curie",
        "question": "What Nobel Prizes did Marie Curie win?",
        "answer": (
            "Marie Curie was the first woman to win a Nobel Prize. "
            "She won the Nobel Prize in Physics in 1903. "
            "She never won a second Nobel Prize."
        ),
        "note": "First two ✓  |  'never won a second Nobel' ✗ (won Chemistry in 1911)",
    },
    {
        "id": "titanic",
        "question": "When did the Titanic sink?",
        "answer": (
            "The RMS Titanic sank in the North Atlantic Ocean after striking an iceberg. "
            "It was on the ship's maiden voyage from Southampton to New York City. "
            "The Titanic sank in 1911."
        ),
        "note": "First two ✓  |  '1911' ✗ (sank in April 1912)",
    },
]
