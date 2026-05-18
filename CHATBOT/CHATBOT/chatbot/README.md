# CHATBOT (DNC Admissions) — Runbook

This folder contains the FastAPI service + ingestion + evaluation tooling.

## Prerequisites

- Python 3.12 (repo currently uses `.venv312/`)
- Docker Desktop (for Qdrant + Neo4j)

> Note: Embedding models are downloaded from HuggingFace the first time.
> If you are offline, you must pre-download the model (or use `--offline` after it is cached).

## Quick Start (Windows PowerShell)

From this `chatbot/` directory:

### 1) Install dependencies

```powershell
.\.venv312\Scripts\python.exe -m pip install -r requirements.txt
```

### 2) Start services (Qdrant + Neo4j)

```powershell
docker compose up -d
```

### 3) Build + validate chunks (schema-compliant)

Build chunks from the saved homepage HTML:

```powershell
.\.venv312\Scripts\python.exe -m src.ingest.build_home_chunks
.\.venv312\Scripts\python.exe -m src.ingest.validate_chunks --chunks data/processed/chunks/chunks.jsonl
```

### 4) Upsert to Qdrant

```powershell
.\.venv312\Scripts\python.exe -m src.ingest.upsert_qdrant --qdrant-url http://localhost:6333 --collection admission_chunks_dnc_2026
```

Offline mode (only if the model is already cached):

```powershell
.\.venv312\Scripts\python.exe -m src.ingest.upsert_qdrant --offline
```

### 5) Run retrieval benchmark

```powershell
.\.venv312\Scripts\python.exe -m src.eval.benchmark_retrieval --retrieval-mode hybrid
```

Offline mode (only if the model is already cached):

```powershell
.\.venv312\Scripts\python.exe -m src.eval.benchmark_retrieval --offline --retrieval-mode hybrid
```

### 6) Start API

```powershell
.\.venv312\Scripts\python.exe -m uvicorn src.api.main:app --reload --port 8000
```

Then test:

- `GET http://localhost:8000/health`
- `POST http://localhost:8000/chude6/chat`

## Notes

## LLM API keys

Some retrieval flows (e.g. `src/retrieval/chude6_rag.py`) can call an LLM.

- Prefer OpenRouter: set `OPENROUTER_API_KEY` (optional `OPENROUTER_MODEL`, default `google/gemini-2.5-flash`).
- Fallback to Gemini: set `GEMINI_API_KEY`.

If neither key is set, the code will fall back to extractive answers from retrieved context.

Example `.env` (place at `chatbot/.env`):

```
OPENROUTER_API_KEY=or_...
OPENROUTER_MODEL=openai/gpt-4o-mini
```

- `data/raw/tuyen_sinh_nctu_homepage.html` is used as the benchmark source for doc_id `DNC-2026-tuyensinh-home-v1`.
- If Docker isn't running, Qdrant/Neo4j will be unavailable and upsert/benchmark will fail.
