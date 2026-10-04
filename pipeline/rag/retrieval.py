"""Retrieval abstraction + a deterministic LEXICAL baseline (BM25 over chunk text).

This is keyword retrieval, NOT semantic/vector search: it only matches words that literally occur in the text (no
synonyms, no translation, no stemming). A semantic retriever can implement the same `Retriever.search` contract later.
Metadata filters are applied before ranking; IDF statistics come from the whole corpus so scores do not depend on filters.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Optional, Protocol

from pipeline.rag.contracts import RETRIEVAL_METHOD

_TOKEN = re.compile(r"\w+", re.UNICODE)
K1, B = 1.5, 0.75


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@dataclass(frozen=True)
class SearchFilters:
    source: Optional[str] = None
    source_type: Optional[str] = None
    province: Optional[str] = None
    admin_unit_id: Optional[int] = None
    event_type: Optional[str] = None
    date_from: Optional[str] = None      # ISO date; documents WITHOUT a date never match a date filter
    date_to: Optional[str] = None


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    document_id: str
    score: float
    method: str
    matched_terms: tuple[str, ...]
    model_version: Optional[str] = None        # set only by semantic retrieval


class Retriever(Protocol):
    def search(self, query: str, filters: SearchFilters, limit: int) -> list[Hit]: ...


def matches(doc: dict, f: SearchFilters) -> bool:
    """Metadata filter over a canonical document dict."""
    if f.source and doc["source"] != f.source:
        return False
    if f.source_type and doc["source_type"] != f.source_type:
        return False
    if f.province and f.province.lower() not in [p.lower() for p in doc.get("provinces") or []]:
        return False
    if f.admin_unit_id is not None and f.admin_unit_id not in (doc.get("admin_unit_ids") or []) and doc.get("admin_unit_id") != f.admin_unit_id:
        return False
    if f.event_type and f.event_type.lower() not in [e.lower() for e in doc.get("event_types") or []]:
        return False
    if f.date_from or f.date_to:
        d = doc.get("document_date")
        if d is None:
            return False
        if f.date_from and d < f.date_from:
            return False
        if f.date_to and d > f.date_to:
            return False
    return True


class LexicalRetriever:
    method = RETRIEVAL_METHOD

    def __init__(self, documents: list[dict], chunks: list[dict]):
        self.docs = {d["document_id"]: d for d in documents}
        self.chunks = [c for c in chunks if c["document_id"] in self.docs]
        self.tf = [Counter(tokenize(c["chunk_text"])) for c in self.chunks]
        self.len = [sum(t.values()) for t in self.tf]
        self.avg = (sum(self.len) / len(self.len)) if self.len else 0.0
        df: Counter = Counter()
        for t in self.tf:
            df.update(t.keys())
        n = len(self.chunks)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}

    def search(self, query: str, filters: SearchFilters = SearchFilters(), limit: int = 10) -> list[Hit]:  # noqa: B008
        terms = list(dict.fromkeys(tokenize(query)))
        if not terms or limit <= 0:
            return []
        hits = []
        for i, c in enumerate(self.chunks):
            doc = self.docs[c["document_id"]]
            if not matches(doc, filters):
                continue
            tf, dl = self.tf[i], self.len[i]
            score, found = 0.0, []
            for w in terms:
                f = tf.get(w, 0)
                if f:
                    found.append(w)
                    score += self.idf[w] * f * (K1 + 1) / (f + K1 * (1 - B + B * dl / (self.avg or 1)))
            if score > 0:
                hits.append((score, doc.get("document_date") or "", c["chunk_id"], c, tuple(found)))
        hits.sort(key=lambda h: (-h[0], h[2]))            # score desc, then chunk_id: fully deterministic
        return [Hit(c["chunk_id"], c["document_id"], round(s, 6), self.method, found) for s, _, _, c, found in hits[:limit]]
