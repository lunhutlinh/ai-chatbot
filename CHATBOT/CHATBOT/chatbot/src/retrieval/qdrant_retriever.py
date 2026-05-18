import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from src.retrieval.hybrid_retriever import rerank_hits, should_abstain


@dataclass(frozen=True)
class RetrievalConfig:
    qdrant_url: str
    collection: str
    embed_model: str
    top_k: int = 5
    retrieval_mode: str = "hybrid"
    hybrid_candidate_pool: int = 20
    intake_year: int = 2026


DEFAULT_COLLECTION = "admission_chunks_dnc_2026"
DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip() or default


@lru_cache(maxsize=1)
def get_config() -> RetrievalConfig:
    return RetrievalConfig(
        qdrant_url=_env("QDRANT_URL", DEFAULT_QDRANT_URL),
        collection=_env("QDRANT_COLLECTION", DEFAULT_COLLECTION),
        embed_model=_env("EMBED_MODEL", DEFAULT_EMBED_MODEL),
        top_k=int(os.getenv("TOP_K", "5")),
        retrieval_mode=_env("RETRIEVAL_MODE", "hybrid"),
        hybrid_candidate_pool=int(os.getenv("HYBRID_CANDIDATE_POOL", "20")),
        intake_year=int(os.getenv("INTAKE_YEAR", "2026")),
    )


@lru_cache(maxsize=1)
def get_embedder() -> Any:
    from sentence_transformers import SentenceTransformer

    cfg = get_config()
    return SentenceTransformer(cfg.embed_model)


@lru_cache(maxsize=1)
def get_qdrant_client() -> Any:
    from qdrant_client import QdrantClient

    cfg = get_config()
    return QdrantClient(url=cfg.qdrant_url)


def _extract_hit_fields(hit: Any) -> tuple[dict[str, Any], float, Any]:
    if isinstance(hit, dict):
        payload = hit.get("payload") or {}
        score = float(hit.get("score", 0.0))
        point_id = hit.get("id")
        return payload, score, point_id

    payload = getattr(hit, "payload", {}) or {}
    score = float(getattr(hit, "score", 0.0))
    point_id = getattr(hit, "id", None)
    return payload, score, point_id


def query_qdrant(client: Any, collection: str, vector: list[float], limit: int) -> list[Any]:
    if hasattr(client, "query_points"):
        response = client.query_points(
            collection_name=collection,
            query=vector,
            limit=limit,
            with_payload=True,
        )
        points = getattr(response, "points", response)
        return list(points)

    response = client.search(
        collection_name=collection,
        query_vector=vector,
        limit=limit,
        with_payload=True,
    )
    return list(response)


def retrieve(question: str) -> dict[str, Any]:
    cfg = get_config()
    embedder = get_embedder()
    client = get_qdrant_client()

    vector = embedder.encode([question], normalize_embeddings=True)[0].tolist()

    candidate_limit = cfg.top_k
    if cfg.retrieval_mode == "hybrid":
        candidate_limit = max(cfg.top_k, cfg.hybrid_candidate_pool)

    hits = query_qdrant(client, cfg.collection, vector, candidate_limit)

    candidates: list[dict[str, Any]] = []
    for hit in hits:
        payload, score, point_id = _extract_hit_fields(hit)
        candidates.append(
            {
                "point_id": point_id,
                "score": float(score),
                "chunk_id": payload.get("chunk_id"),
                "doc_id": payload.get("doc_id"),
                "citations": payload.get("citations") or [],
                "chunk_text": str(payload.get("chunk_text", "")),
            }
        )

    if cfg.retrieval_mode == "hybrid":
        ranked = rerank_hits(question, candidates)
        abstain, reason = should_abstain(question, ranked, intake_year=cfg.intake_year)
    else:
        ranked = sorted(candidates, key=lambda x: x.get("score", 0.0), reverse=True)
        abstain, reason = False, "answerable"

    top_k = ranked[: cfg.top_k]

    citations: list[dict[str, Any]] = []
    supporting_chunk_ids: list[str] = []
    for item in top_k:
        cid = item.get("chunk_id")
        if isinstance(cid, str) and cid:
            supporting_chunk_ids.append(cid)
        item_citations = item.get("citations") or []
        if isinstance(item_citations, list):
            for c in item_citations:
                if isinstance(c, dict) and c not in citations:
                    citations.append(c)

    return {
        "config": cfg,
        "abstain": abstain,
        "reason": reason,
        "hits": top_k,
        "citations": citations,
        "supporting_chunk_ids": supporting_chunk_ids,
    }
