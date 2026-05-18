import argparse
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.retrieval.hybrid_retriever import rerank_hits, should_abstain

DEFAULT_QUESTIONS_PATH = BASE_DIR / "data/eval/questions.jsonl"
DEFAULT_RESULTS_PATH = BASE_DIR / "data/eval/retrieval_results.jsonl"
DEFAULT_ERRORS_PATH = BASE_DIR / "data/eval/error_analysis.jsonl"
DEFAULT_SUMMARY_PATH = BASE_DIR / "data/eval/summary.json"

DEFAULT_COLLECTION = "admission_chunks_dnc_2026"
DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

NOISE_TERMS = [
    "dang ky ngay",
    "xem them",
    "truy cap nhanh",
    "tu khoa pho bien",
    "dang tai",
    "all rights reserved",
    "tin tuc",
    "su kien",
]


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_noise_text(text: str) -> bool:
    normalized = normalize_text(text)
    return any(term in normalized for term in NOISE_TERMS)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at line {line_no}: {exc}") from exc
    return rows


def validate_questions(questions: list[dict[str, Any]]) -> None:
    required = {
        "question_id",
        "question",
        "intent",
        "difficulty",
        "manual_review",
        "out_of_scope",
        "expected_doc_id",
        "expected_keywords",
    }

    seen_ids: set[str] = set()
    for idx, item in enumerate(questions, start=1):
        missing = required - set(item.keys())
        if missing:
            raise ValueError(f"Question {idx} is missing keys: {sorted(missing)}")

        qid = item["question_id"]
        if qid in seen_ids:
            raise ValueError(f"Duplicated question_id: {qid}")
        seen_ids.add(qid)

        if not isinstance(item["expected_keywords"], list):
            raise ValueError(f"question_id={qid}: expected_keywords must be a list")


def summarize_question_set(questions: list[dict[str, Any]]) -> dict[str, Any]:
    intent_counter = Counter(item["intent"] for item in questions)
    difficulty_counter = Counter(item["difficulty"] for item in questions)

    return {
        "total": len(questions),
        "in_scope": sum(1 for item in questions if not item["out_of_scope"]),
        "out_of_scope": sum(1 for item in questions if item["out_of_scope"]),
        "manual_review": sum(1 for item in questions if item["manual_review"]),
        "by_intent": dict(sorted(intent_counter.items())),
        "by_difficulty": dict(sorted(difficulty_counter.items())),
    }


def extract_hit_fields(hit: Any) -> tuple[dict[str, Any], float, Any]:
    if isinstance(hit, dict):
        payload = hit.get("payload") or {}
        score = float(hit.get("score", 0.0))
        point_id = hit.get("id")
        return payload, score, point_id

    payload = getattr(hit, "payload", {}) or {}
    score = float(getattr(hit, "score", 0.0))
    point_id = getattr(hit, "id", None)
    return payload, score, point_id


def query_qdrant(
    client: Any,
    collection: str,
    vector: list[float],
    top_k: int,
) -> list[Any]:
    if hasattr(client, "query_points"):
        response = client.query_points(
            collection_name=collection,
            query=vector,
            limit=top_k,
            with_payload=True,
        )
        points = getattr(response, "points", response)
        return list(points)

    response = client.search(
        collection_name=collection,
        query_vector=vector,
        limit=top_k,
        with_payload=True,
    )
    return list(response)


def keyword_match(chunk_text: str, expected_keywords: list[str]) -> tuple[bool, list[str]]:
    if not expected_keywords:
        return True, []

    normalized_chunk = normalize_text(chunk_text)
    matched = [kw for kw in expected_keywords if normalize_text(kw) in normalized_chunk]
    return len(matched) > 0, matched


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark retrieval quality before handoff")
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS_PATH)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS_PATH)
    parser.add_argument("--errors", type=Path, default=DEFAULT_ERRORS_PATH)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--qdrant-url", default=DEFAULT_QDRANT_URL)
    parser.add_argument("--embed-model", default=DEFAULT_EMBED_MODEL)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run embeddings in offline mode (requires model already cached locally)",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--retrieval-mode", choices=["vector", "hybrid"], default="hybrid")
    parser.add_argument(
        "--hybrid-candidate-pool",
        type=int,
        default=20,
        help="Number of dense candidates fetched before hybrid reranking.",
    )
    parser.add_argument("--out-scope-threshold", type=float, default=0.45)
    parser.add_argument("--intake-year", type=int, default=2026)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.offline:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    questions = load_jsonl(args.questions)
    validate_questions(questions)

    question_stats = summarize_question_set(questions)
    if args.dry_run:
        print(json.dumps({"status": "ok", "question_stats": question_stats}, ensure_ascii=False, indent=2))
        return

    try:
        from qdrant_client import QdrantClient
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: qdrant-client. Install with `pip install qdrant-client`."
        ) from exc

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: sentence-transformers. Install with `pip install sentence-transformers`."
        ) from exc

    print(f"loading_embedding_model={args.embed_model} offline={args.offline}")
    sys.stdout.flush()
    model = SentenceTransformer(args.embed_model)
    client = QdrantClient(url=args.qdrant_url)

    args.results.parent.mkdir(parents=True, exist_ok=True)
    args.errors.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)

    in_scope_total = 0
    in_scope_recall_hits = 0
    in_scope_precision_hits = 0
    in_scope_citation_hits = 0
    in_scope_noise_hits = 0
    out_scope_total = 0
    out_scope_safe_hits = 0

    hard_total = 0
    hard_recall_hits = 0

    error_rows: list[dict[str, Any]] = []

    with args.results.open("w", encoding="utf-8") as results_file:
        for item in questions:
            vector = model.encode([item["question"]], normalize_embeddings=True)[0].tolist()
            candidate_limit = args.top_k
            if args.retrieval_mode == "hybrid":
                candidate_limit = max(args.top_k, args.hybrid_candidate_pool)

            hits = query_qdrant(client, args.collection, vector, candidate_limit)

            candidates: list[dict[str, Any]] = []
            any_relevant = False
            top1_relevant = False
            top1_has_citation = False
            top1_noise = False
            abstain = False
            abstain_reason = "n/a"

            for hit in hits:
                payload, score, point_id = extract_hit_fields(hit)
                chunk_text = str(payload.get("chunk_text", ""))
                citation_ok = bool(payload.get("citations"))
                noise_flag = is_noise_text(chunk_text)

                candidates.append(
                    {
                        "point_id": point_id,
                        "score": score,
                        "chunk_id": payload.get("chunk_id"),
                        "doc_id": payload.get("doc_id"),
                        "has_citation": citation_ok,
                        "noise_flag": noise_flag,
                        "chunk_text": chunk_text,
                    }
                )

            if args.retrieval_mode == "hybrid":
                ranked_candidates = rerank_hits(item["question"], candidates)
                abstain, abstain_reason = should_abstain(
                    item["question"],
                    ranked_candidates,
                    intake_year=args.intake_year,
                )
            else:
                ranked_candidates = sorted(candidates, key=lambda x: x.get("score", 0.0), reverse=True)

            top_k_results: list[dict[str, Any]] = []
            for rank, candidate in enumerate(ranked_candidates[: args.top_k], start=1):
                chunk_text = str(candidate.get("chunk_text", ""))
                expected_keywords = item["expected_keywords"]
                kw_ok, matched_keywords = keyword_match(chunk_text, expected_keywords)
                doc_ok = candidate.get("doc_id") == item["expected_doc_id"]
                relevant = (doc_ok and kw_ok) if not item["out_of_scope"] else False

                if relevant:
                    any_relevant = True
                if rank == 1:
                    top1_relevant = relevant
                    top1_has_citation = bool(candidate.get("has_citation", False))
                    top1_noise = bool(candidate.get("noise_flag", False))

                score_value = candidate.get("hybrid_score", candidate.get("score", 0.0))

                top_k_results.append(
                    {
                        "rank": rank,
                        "point_id": candidate.get("point_id"),
                        "score": score_value,
                        "vector_score": candidate.get("score"),
                        "hybrid_score": candidate.get("hybrid_score", None),
                        "lexical_score": candidate.get("lexical_score", None),
                        "intent_bonus": candidate.get("intent_bonus", None),
                        "noise_penalty": candidate.get("noise_penalty", None),
                        "chunk_id": candidate.get("chunk_id"),
                        "doc_id": candidate.get("doc_id"),
                        "matched_keywords": matched_keywords,
                        "has_citation": bool(candidate.get("has_citation", False)),
                        "noise_flag": bool(candidate.get("noise_flag", False)),
                        "snippet": chunk_text[:260],
                    }
                )

            effective_recall_hit = any_relevant and not abstain
            effective_top1_hit = top1_relevant and not abstain
            effective_top1_has_citation = top1_has_citation and not abstain
            effective_top1_noise = top1_noise and not abstain

            if item["out_of_scope"]:
                out_scope_total += 1
                top1_score = top_k_results[0]["score"] if top_k_results else 0.0

                if args.retrieval_mode == "hybrid":
                    out_scope_ok = abstain
                else:
                    out_scope_ok = (not top_k_results) or (top1_score < args.out_scope_threshold)

                if out_scope_ok:
                    out_scope_safe_hits += 1
                else:
                    error_rows.append(
                        {
                            "question_id": item["question_id"],
                            "intent": item["intent"],
                            "reason": "out_of_scope_not_safe",
                            "top1_score": top1_score,
                            "abstain": abstain,
                            "abstain_reason": abstain_reason,
                            "question": item["question"],
                        }
                    )
            else:
                in_scope_total += 1
                if effective_recall_hit:
                    in_scope_recall_hits += 1
                else:
                    reason = "over_reject" if abstain else "recall_miss"
                    error_rows.append(
                        {
                            "question_id": item["question_id"],
                            "intent": item["intent"],
                            "reason": reason,
                            "question": item["question"],
                            "expected_keywords": item["expected_keywords"],
                            "abstain": abstain,
                            "abstain_reason": abstain_reason,
                        }
                    )

                if effective_top1_hit:
                    in_scope_precision_hits += 1
                if effective_top1_has_citation:
                    in_scope_citation_hits += 1
                if effective_top1_noise:
                    in_scope_noise_hits += 1

                if item["difficulty"] == "hard":
                    hard_total += 1
                    if effective_recall_hit:
                        hard_recall_hits += 1

            result_row = {
                "question_id": item["question_id"],
                "question": item["question"],
                "intent": item["intent"],
                "difficulty": item["difficulty"],
                "manual_review": item["manual_review"],
                "out_of_scope": item["out_of_scope"],
                "expected_doc_id": item["expected_doc_id"],
                "expected_keywords": item["expected_keywords"],
                "retrieval_mode": args.retrieval_mode,
                "top_k_results": top_k_results,
                "decision": {
                    "abstain": abstain,
                    "reason": abstain_reason,
                },
                "metrics": {
                    "raw_recall_hit": any_relevant,
                    "raw_top1_hit": top1_relevant,
                    "recall_hit": effective_recall_hit,
                    "top1_hit": effective_top1_hit,
                    "top1_has_citation": effective_top1_has_citation,
                    "top1_noise": effective_top1_noise,
                },
            }
            results_file.write(json.dumps(result_row, ensure_ascii=False) + "\n")

    with args.errors.open("w", encoding="utf-8") as errors_file:
        for row in error_rows:
            errors_file.write(json.dumps(row, ensure_ascii=False) + "\n")

    recall_at_k = (in_scope_recall_hits / in_scope_total) if in_scope_total else 0.0
    precision_at_1 = (in_scope_precision_hits / in_scope_total) if in_scope_total else 0.0
    citation_coverage = (in_scope_citation_hits / in_scope_total) if in_scope_total else 0.0
    noise_rate_top1 = (in_scope_noise_hits / in_scope_total) if in_scope_total else 0.0
    out_scope_safe_rate = (out_scope_safe_hits / out_scope_total) if out_scope_total else 0.0
    hard_recall_at_k = (hard_recall_hits / hard_total) if hard_total else 0.0

    thresholds = {
        "recall_at_k": 0.8,
        "precision_at_1": 0.6,
        "citation_coverage": 1.0,
        "noise_rate_top1_max": 0.2,
        "out_scope_safe_rate": 1.0,
    }

    pass_fail = {
        "recall_at_k": recall_at_k >= thresholds["recall_at_k"],
        "precision_at_1": precision_at_1 >= thresholds["precision_at_1"],
        "citation_coverage": citation_coverage >= thresholds["citation_coverage"],
        "noise_rate_top1": noise_rate_top1 <= thresholds["noise_rate_top1_max"],
        "out_scope_safe_rate": out_scope_safe_rate >= thresholds["out_scope_safe_rate"],
    }

    summary = {
        "status": "ok",
        "collection": args.collection,
        "top_k": args.top_k,
        "retrieval_mode": args.retrieval_mode,
        "hybrid_candidate_pool": args.hybrid_candidate_pool if args.retrieval_mode == "hybrid" else None,
        "question_stats": question_stats,
        "metrics": {
            "recall_at_k": round(recall_at_k, 4),
            "precision_at_1": round(precision_at_1, 4),
            "citation_coverage": round(citation_coverage, 4),
            "noise_rate_top1": round(noise_rate_top1, 4),
            "out_scope_safe_rate": round(out_scope_safe_rate, 4),
            "hard_recall_at_k": round(hard_recall_at_k, 4),
        },
        "thresholds": thresholds,
        "pass_fail": pass_fail,
        "overall_pass": all(pass_fail.values()),
        "artifacts": {
            "results_jsonl": str(args.results),
            "errors_jsonl": str(args.errors),
        },
    }

    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
