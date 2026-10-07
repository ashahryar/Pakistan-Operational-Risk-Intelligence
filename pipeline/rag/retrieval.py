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


# Function words. Removed from the query for the hybrid mode's lexical side (Task 31) and from the relevance signal (Task 35); standalone BM25 ranking is unchanged.
STOPWORDS = frozenset("""a an and are as at be been but by can did do does for from had has have how i if in into is it its of on or our
so than that the their them then there these they this to was we were what when where which who whom why will with would you your""".split())


def content_terms(query: str) -> list[str]:
    """Distinct query words with stop words removed, in order."""
    return [t for t in dict.fromkeys(tokenize(query)) if t not in STOPWORDS]


# Question-framing words: they describe HOW a question about reports is asked ("what was reported about ...", "official evidence", "current situation"), not WHAT it
# asks about. Used ONLY by the relevance signal (never by BM25 ranking). Fixed from generic question wording before the iteration-3 holdout was run; agency names are
# included because the source is a metadata filter, not a topic.
FRAMING_WORDS = frozenset("""report reports reported reporting about advise advised advice document documents documented official officially evidence supports support
supported situation event events affected affect affects happened happen happens occurred occur details detail information info status condition conditions current
currently latest recent recently update updates issued issue announce announced say says said stated state states mention mentioned mentions regarding concerning
related relating tell show give list provide find any all some there news operational risk classified classification many much number numbers during according
sitrep sitreps ndma pdma pmd ffc suparco hazards""".split())


def signal_terms(query: str) -> list[str]:
    """The topic-bearing words of a query for the relevance signal: content words minus question-framing words. If nothing is left (a question made only of framing
    words) the content words are used, so the signal is never computed on an empty set."""
    terms = [t for t in content_terms(query) if t not in FRAMING_WORDS]
    return terms or content_terms(query)


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
    model_version: Optional[str] = None        # set only by semantic (and hybrid) retrieval
    lexical_rank: Optional[int] = None         # hybrid only: 1-based rank in the BM25 list (None = not retrieved lexically)
    semantic_rank: Optional[int] = None        # hybrid only: 1-based rank in the semantic list (None = below the floor / not retrieved)
    lexical_score: Optional[float] = None
    semantic_score: Optional[float] = None
    fused_rank: Optional[int] = None           # hybrid only: 1-based position in the fused list


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
        self.idf_absent = math.log(1 + (n + 0.5) / 0.5)           # idf of a word that occurs in no chunk (df = 0): the rarest possible
        self._index = {c["chunk_id"]: i for i, c in enumerate(self.chunks)}

    def coverage(self, query: str, chunk_id: str) -> float:
        """Task 35 relevance signal: the share of the query's CONTENT words (stop words removed), weighted by IDF, that occur in the chunk. 0..1.
        A word that occurs nowhere in the corpus counts as unmatched with the highest weight, so a query built around a concept the corpus
        never mentions (plus a few frequent words such as 'NDMA' or 'Sindh') scores low even though BM25 still returns chunks for the frequent words."""
        terms = signal_terms(query)
        i = self._index.get(chunk_id)
        if not terms or i is None:
            return 0.0
        weight = {t: self.idf.get(t, self.idf_absent) for t in terms}
        total = sum(weight.values())
        return round(sum(w for t, w in weight.items() if self.tf[i].get(t, 0)) / total, 6) if total else 0.0

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

    def absent_share(self, query: str) -> float:
        """Task 35 relevance signal (query level): the IDF-weighted share of the query's content words that occur in NO chunk of the corpus. BM25 can only match
        literal words, so a query whose weight is mostly such words cannot be answered by keyword matching however well the remaining frequent words match."""
        terms = signal_terms(query)
        if not terms:
            return 0.0
        weight = {t: self.idf.get(t, self.idf_absent) for t in terms}
        total = sum(weight.values())
        return round(sum(w for t, w in weight.items() if t not in self.idf) / total, 6) if total else 0.0
