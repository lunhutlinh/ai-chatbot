# ai-chatbot

## Gioi thieu ngan

Chatbot ho tro tuyen sinh DNC, tra loi cau hoi dua tren du lieu thu thap va he thong RAG (retrieval-augmented generation). Phu hop cho sinh vien, phu huynh, va can bo tuyen sinh. Ngon ngu chinh: tieng Viet.

## Cach cai dat va chay

Yeu cau:
- Python 3.12
- Docker Desktop (de chay Qdrant + Neo4j)

Tu thu muc `CHATBOT/CHATBOT/chatbot`:

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
docker compose up -d
./.venv/Scripts/python.exe -m uvicorn src.api.main:app --reload --port 8000
```

Test nhanh:
- `GET http://localhost:8000/health`
- `POST http://localhost:8000/chude6/chat`

## Huong dan chay chi tiet

Tu thu muc `CHATBOT/CHATBOT/chatbot`:

1) Bat dich vu Qdrant + Neo4j

```powershell
docker compose up -d
```

2) Tao chunks (neu chua co du lieu)

```powershell
./.venv/Scripts/python.exe -m src.ingest.build_home_chunks
./.venv/Scripts/python.exe -m src.ingest.validate_chunks --chunks data/processed/chunks/chunks.jsonl
```

3) Day du lieu len Qdrant

```powershell
./.venv/Scripts/python.exe -m src.ingest.upsert_qdrant --qdrant-url http://localhost:6333 --collection admission_chunks_dnc_2026
```

4) Chay API

```powershell
./.venv/Scripts/python.exe -m uvicorn src.api.main:app --reload --port 8000
```

Tuy chon: benchmark

```powershell
./.venv/Scripts/python.exe -m src.eval.benchmark_retrieval --retrieval-mode hybrid
```

## Huong dan chay giao dien web

### Cach 1: UI tich hop voi API

Sau khi chay API (buoc 4 o tren), mo trinh duyet:

- `http://localhost:8000/ui`

Giao dien nay goi API `/chude6/chat` truc tiep.

Neu ban co build SPA va co thu muc `web/dist/`, co the thu:

- `http://localhost:8000/app`

### Cach 2: Giao dien demo tinh (khong goi API)

Mo file giao dien trong thu muc `Giaodien/templates/index.html` bang trinh duyet. Day la demo tinh, khong ket noi API.

## Cau hinh (env vars, keys, model, vector DB)

Tao file `.env` trong `CHATBOT/CHATBOT/chatbot/` neu can:

```
OPENROUTER_API_KEY=or_...
OPENROUTER_MODEL=google/gemini-2.5-flash
GEMINI_API_KEY=...
```

Ghi chu:
- Neu khong co khoa API, he thong se tra loi theo cach trich xuat tu van ban (extractive) tu du lieu truy hoi.
- Qdrant va Neo4j chay qua `docker compose` (mac dinh localhost).