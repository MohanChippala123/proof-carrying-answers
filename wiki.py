"""
Wikipedia live evidence fetching for Proof-Carrying Answers.

Uses only the Python standard library (urllib). No API key required.
Wikipedia is CC BY-SA — cite the source URL returned by search_wikipedia().
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

_UA = "ProofCarryingAnswers/1.0 (hackathon demo; contact via github)"
_TIMEOUT = 9


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        return json.load(r)


def search_wikipedia(query: str, sentences: int = 18) -> Optional[dict]:
    """Return {title, source, text} for the best matching Wikipedia article.

    Accepts either a search term ("Marie Curie") or a full Wikipedia URL.
    Returns None on any failure (no article found, network error, etc.).
    """
    # Accept a pasted Wikipedia URL directly.
    if "wikipedia.org/wiki/" in query:
        raw = query.split("/wiki/")[-1].split("#")[0]
        title = urllib.parse.unquote(raw.replace("_", " "))
    else:
        # OpenSearch to resolve the best-matching article title.
        url = (
            "https://en.wikipedia.org/w/api.php?action=opensearch"
            "&search=" + urllib.parse.quote(query)
            + "&limit=1&format=json&namespace=0"
        )
        try:
            data = _get(url)
            if not data[1]:
                return None
            title = data[1][0]
        except Exception:
            return None

    # Fetch plain-text intro extract.
    url = (
        "https://en.wikipedia.org/w/api.php?"
        "action=query&prop=extracts"
        "&exsentences=" + str(sentences)
        + "&explaintext=1&exintro=1"
        + "&titles=" + urllib.parse.quote(title)
        + "&format=json"
    )
    try:
        data = _get(url)
        pages = data["query"]["pages"]
        page = next(iter(pages.values()))
        if "missing" in page:
            return None
        extract = (page.get("extract") or "").strip()
        if len(extract) < 60:
            return None
        canon_title = page.get("title", title)
        source = ("https://en.wikipedia.org/wiki/"
                  + urllib.parse.quote(canon_title.replace(" ", "_")))
        return {"title": canon_title, "source": source, "text": extract}
    except Exception:
        return None
