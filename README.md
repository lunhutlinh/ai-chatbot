---
title: AI Chatbot
emoji: "🤖"
colorFrom: "blue"
colorTo: "pink"
sdk: "docker"
pinned: false
---

# ai-chatbot

## Gioi thieu do an

Chatbot ho tro tuyen sinh DNC, tra loi cau hoi dua tren du lieu thu thap (PDF/HTML/TXT) va he thong RAG (retrieval-augmented generation). Doi tuong: thi sinh, phu huynh, can bo tuyen sinh. Ngon ngu chinh: tieng Viet.

## Cong nghe su dung

- Backend: FastAPI, Uvicorn
- Retrieval: Qdrant (vector DB), hybrid rerank (vector + lexical)
- Graph (tuy chon): Neo4j
- Embedding: sentence-transformers
- LLM (tuy chon): OpenRouter (uu tien), Gemini (fallback)
- Docker: docker compose cho Qdrant/Neo4j

## Tinh nang web (demo)

- Man hinh chao + o nhap cau hoi nhanh
- UI chat theo dang bong bong, tu dong cuon xuong khi co phan hoi
- Goi API `/chude6/chat` de lay cau tra loi tu RAG
- Hien thi cau tra loi theo tung luot hoi/tra loi (khong can tai lai trang)
- Co the chay noi bo qua `/ui` hoac demo tren Hugging Face

## Luong du lieu xu ly

1) Thu thap du lieu vao `data/raw` (PDF/HTML/TXT)
2) Ingest -> tao chunks -> luu vao `data/processed/chunks/*.jsonl`
3) (Tuy chon) Upsert chunks vao Qdrant
4) API nhan cau hoi -> retrieve chunks -> tra loi (LLM hoac extractive)
5) Neu Qdrant khong san sang, he thong fallback doc tu `chunks.jsonl` va `chunks.legacy.jsonl`

## Cau truc du an (rut gon)

```
CHATBOT/CHATBOT/chatbot/
	src/
		api/               # FastAPI endpoints
		ingest/            # build chunks, upsert
		retrieval/         # RAG logic, qdrant, neo4j
	data/
		raw/               # PDF/HTML/TXT
		processed/
			chunks/          # chunks.jsonl, chunks.legacy.jsonl
	web/                 # UI (templates/static)
Giaodien/              # UI demo tinh
```

## Cach khoi dong app (local)

Yeu cau:
- Python 3.12
- Docker Desktop (de chay Qdrant + Neo4j)

Tu thu muc `CHATBOT/CHATBOT/chatbot`:

```powershell
python -m venv .venv312
./.venv312/Scripts/python.exe -m pip install -r requirements.txt
docker compose up -d
./.venv312/Scripts/python.exe -m uvicorn src.api.main:app --reload --port 8000
```

Test nhanh:
- `GET http://localhost:8000/health`
- `POST http://localhost:8000/chude6/chat`

## Huong dan ingest du lieu

Tao chunks va validate:

```powershell
./.venv312/Scripts/python.exe -m src.ingest.build_chunks
./.venv312/Scripts/python.exe -m src.ingest.validate_chunks --chunks data/processed/chunks/chunks.jsonl
```

Upsert vao Qdrant:

```powershell
./.venv312/Scripts/python.exe -m src.ingest.upsert_qdrant --qdrant-url http://localhost:6333 --collection admission_chunks_dnc_2026
```

Tuy chon: benchmark

```powershell
./.venv312/Scripts/python.exe -m src.eval.benchmark_retrieval --retrieval-mode hybrid
```

## Huong dan chay giao dien web

### Cach 1: UI tich hop voi API

Sau khi chay API, mo:

- `http://localhost:8000/ui`

Neu ban build SPA va co `web/dist/`:

- `http://localhost:8000/app`

### Cach 2: UI demo tinh (khong goi API)

Mo `Giaodien/templates/index.html` bang trinh duyet.

## Cau hinh (env vars, keys, model, vector DB)

Tao file `.env` trong `CHATBOT/CHATBOT/chatbot/` neu can:

```
OPENROUTER_API_KEY=or_...
OPENROUTER_MODEL=google/gemini-2.5-flash
GEMINI_API_KEY=...
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=admission_chunks_dnc_2026
```

Ghi chu:
- Neu khong co khoa API, he thong se tra loi theo cach trich xuat (extractive)
- Qdrant/Neo4j chay qua `docker compose` (mac dinh localhost)

## Demo app online (Hugging Face)

- UI: https://lunhutlinh-ai-chatbot.hf.space/ui
<<<<<<< HEAD
- API: https://lunhutlinh-ai-chatbot.hf.space/chude6/chat
=======
- API: https://lunhutlinh-ai-chatbot.hf.space/chude6/chat
>>>>>>> 84e64528 (Update README with web features)
