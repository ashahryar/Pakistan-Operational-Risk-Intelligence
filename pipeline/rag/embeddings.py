"""Real text embeddings for RAG chunks.

The only production embedder is FastEmbedEmbedder: ONNX Runtime executing the pinned, quantized BAAI/bge-small-en-v1.5 weights
(Hugging Face repo Qdrant/bge-small-en-v1.5-onnx-Q at a fixed revision). Nothing here fabricates vectors: no random, zero,
hash-based or TF-IDF "embeddings" exist in this module. Tests that need a stand-in define it inside the test code.

Query and document vectors must come from the same (model_name, model_version); vectors of different models are never mixed.
"""

from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol, Sequence

MODEL_NAME = "BAAI/bge-small-en-v1.5"
HF_REPO = "Qdrant/bge-small-en-v1.5-onnx-Q"
HF_REVISION = "aa8f8b060edb00e03bfdd08813a2949946c8ba55"        # immutable commit of the exact weights
MODEL_VERSION = f"hf:{HF_REPO}@{HF_REVISION}"
DIMENSION = 384
DEFAULT_CACHE = "data/models/embedding_cache"
NORM_TOLERANCE = 1e-3


@dataclass(frozen=True)
class ModelInfo:
    name: str
    version: str
    dimension: int
    normalized: bool = True
    metadata: dict = field(default_factory=dict, compare=False)


class Embedder(Protocol):
    info: ModelInfo

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class EmbeddingUnavailable(RuntimeError):
    """The embedding runtime or model weights are not installed/obtainable in this environment."""


def runtime_available() -> bool:
    try:
        import fastembed  # noqa: F401
        return True
    except Exception:
        return False


def cache_dir() -> str:
    """PORI_EMBEDDING_CACHE if set, else <repository root>/data/models/embedding_cache (independent of the working directory)."""
    return os.environ.get("PORI_EMBEDDING_CACHE") or str(Path(__file__).resolve().parents[2] / DEFAULT_CACHE)


def ensure_model(cache: Optional[str] = None) -> str:
    """Download (once) and return the local directory of the pinned model revision."""
    try:
        from huggingface_hub import snapshot_download
    except Exception as exc:                                            # pragma: no cover - depends on environment
        raise EmbeddingUnavailable("huggingface_hub is not installed (pip install -r requirements/embeddings.txt)") from exc
    try:
        return snapshot_download(repo_id=HF_REPO, revision=HF_REVISION, cache_dir=cache or cache_dir())
    except Exception as exc:                                            # pragma: no cover - depends on network
        raise EmbeddingUnavailable(f"model weights {HF_REPO}@{HF_REVISION} are not available: {exc}") from exc


def validate_vector(vec: Sequence[float], dimension: int, normalized: bool = True) -> None:
    if len(vec) != dimension:
        raise ValueError(f"embedding has {len(vec)} dimensions, expected {dimension}")
    if not all(isinstance(x, float) or isinstance(x, int) for x in vec) or not all(math.isfinite(x) for x in vec):
        raise ValueError("embedding contains non-finite or non-numeric values")
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        raise ValueError("zero vector is not an embedding")
    if normalized and abs(norm - 1.0) > NORM_TOLERANCE:
        raise ValueError(f"embedding is declared normalized but has norm {norm:.4f}")


class FastEmbedEmbedder:
    """Lazy-loading wrapper; loading happens on first use so importing this module costs nothing."""

    def __init__(self, cache: Optional[str] = None):
        self._cache = cache
        self._model = None
        self.info = ModelInfo(MODEL_NAME, MODEL_VERSION, DIMENSION, True, {})

    def _load(self):
        if self._model is None:
            try:
                import fastembed
                import onnxruntime
            except Exception as exc:
                raise EmbeddingUnavailable("embedding runtime not installed (pip install -r requirements/embeddings.txt)") from exc
            path = ensure_model(self._cache)
            weights = Path(path) / "model_optimized.onnx"
            self._model = fastembed.TextEmbedding(MODEL_NAME, specific_model_path=path)
            self.info = ModelInfo(MODEL_NAME, MODEL_VERSION, DIMENSION, True, {
                "library": "fastembed", "library_version": fastembed.__version__, "onnxruntime_version": onnxruntime.__version__,
                "hf_repo": HF_REPO, "hf_revision": HF_REVISION, "weights_file": weights.name, "quantized": True,
                "weights_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
                "query_instruction": "none (bge-small-en-v1.5 retrieval without instruction)"})
        return self._model

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(x) for x in v] for v in self._load().embed(list(texts))]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def build_embedding_records(chunks: Sequence[dict], embedder: Embedder, batch_size: int = 32) -> tuple[list[dict], list[dict]]:
    """-> (records, failures). Each record names its chunk, model, version and dimension; a chunk whose text is empty or whose
    vector fails validation is reported in `failures` (never stored, never replaced by a placeholder)."""
    records, failures = [], []
    for i in range(0, len(chunks), batch_size):
        batch = list(chunks[i:i + batch_size])
        good = [c for c in batch if (c.get("chunk_text") or "").strip()]
        failures += [{"chunk_id": c["chunk_id"], "error": "empty chunk text"} for c in batch if c not in good]
        if not good:
            continue
        try:
            vectors = embedder.embed_documents([c["chunk_text"] for c in good])
            if len(vectors) != len(good):
                raise ValueError(f"model returned {len(vectors)} vectors for {len(good)} chunks")
        except Exception as exc:                                         # isolate: retry one by one so one bad chunk cannot hide the rest
            vectors = []
            for c in good:
                try:
                    vectors.append(embedder.embed_documents([c["chunk_text"]])[0])
                except Exception as inner:
                    vectors.append(None)
                    failures.append({"chunk_id": c["chunk_id"], "error": f"{type(inner).__name__}: {inner}"})
            _ = exc
        info = embedder.info                       # read after embedding: a lazily loaded model fills in its run metadata on first use
        for c, v in zip(good, vectors):
            if v is None:
                continue
            try:
                validate_vector(v, info.dimension, info.normalized)
            except ValueError as exc:
                failures.append({"chunk_id": c["chunk_id"], "error": str(exc)})
                continue
            records.append({"chunk_id": c["chunk_id"], "model_name": info.name, "model_version": info.version,
                            "embedding_dimension": info.dimension, "embedding": v, "normalized": info.normalized,
                            "chunk_sha256": c["chunk_sha256"], "metadata": dict(info.metadata)})
    return records, failures
