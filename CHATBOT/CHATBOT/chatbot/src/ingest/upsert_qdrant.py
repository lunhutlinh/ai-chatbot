import json
import os
import sys
import argparse
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

from src.ingest.validate_chunks import validate_chunks_file

CHUNKS_PATH = Path("data/processed/chunks/chunks.jsonl")
COLLECTION = "admission_chunks_dnc_2026"
QDRANT_URL = "http://localhost:6333"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
BATCH_SIZE = 128


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Chunks file not found: {path}")

    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if not item.get("chunk_text"):
                raise ValueError(f"Missing chunk_text at line {line_no}")
            rows.append(item)
    return rows


def ensure_collection(client: QdrantClient, collection: str, dim: int, *, recreate: bool) -> None:
    existing = [c.name for c in client.get_collections().collections]
    if recreate and collection in existing:
        client.recreate_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        return

    if collection not in existing:
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )


def batched(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield i, seq[i : i + size]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate chunks and upsert into Qdrant")
    parser.add_argument("--chunks", type=Path, default=CHUNKS_PATH, help="Path to chunks.jsonl")
    parser.add_argument("--collection", default=COLLECTION, help="Qdrant collection name")
    parser.add_argument("--qdrant-url", default=QDRANT_URL, help="Qdrant base URL")
    parser.add_argument("--embed-model", default=EMBED_MODEL, help="SentenceTransformers model name/path")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help="Upsert batch size")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate the collection before upserting (recommended to avoid mixing old points)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run embeddings in offline mode (requires model already cached locally)",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()

    if args.offline:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    ok, errors, rows = validate_chunks_file(args.chunks)
    if not ok:
        preview = "\n".join(f" - {e}" for e in errors[:20])
        suffix = "" if len(errors) <= 20 else f"\n - ... and {len(errors) - 20} more"
        raise ValueError(
            f"chunks validation failed (rows={rows}, errors={len(errors)}):\n{preview}{suffix}"
        )

    print(f"chunks_validation=ok rows={rows}")
    print(f"qdrant_url={args.qdrant_url} collection={args.collection}")
    print(f"embed_model={args.embed_model} offline={args.offline}")
    sys.stdout.flush()

    client = QdrantClient(url=args.qdrant_url)

    try:
        print("loading_embedding_model...")
        sys.stdout.flush()
        model = SentenceTransformer(args.embed_model)
    except KeyboardInterrupt:
        raise
    except Exception as exc:  # noqa: BLE001
        hint = (
            "Failed to load embedding model. If you're offline, rerun with --offline after "
            "pre-downloading the model (or run once with internet to warm the cache)."
        )
        raise RuntimeError(f"{hint}\nOriginal error: {exc!r}") from exc

    dim = model.get_sentence_embedding_dimension()

    data_rows = load_rows(args.chunks)
    if not data_rows:
        raise ValueError("No rows found in chunks file")

    ensure_collection(client, args.collection, dim, recreate=args.recreate)

    total = 0
    for start_idx, batch_rows in batched(data_rows, args.batch_size):
        texts = [r["chunk_text"] for r in batch_rows]
        vectors = model.encode(texts, normalize_embeddings=True).tolist()

        points = []
        for offset, (row, vector) in enumerate(zip(batch_rows, vectors)):
            payload = dict(row)
            points.append(
                PointStruct(
                    id=start_idx + offset,
                    vector=vector,
                    payload=payload,
                )
            )

        client.upsert(collection_name=args.collection, points=points)
        total += len(points)

    print(f"upserted={total} into {args.collection}")


if __name__ == "__main__":
    main()
