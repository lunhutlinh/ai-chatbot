# Handoff Checklist: Vector + Graph Team

Ngay chot bo: 2026-04-14

Nguon metric de chot: `data/eval/summary.json` (overall_pass=true).

## 1) Pre-handoff Freeze (Owner: Data Engineer)

- [ ] Khong doi schema chunk sau moc handoff.
- [ ] Chunks da qua validation: `src/ingest/validate_chunks.py`.
- [ ] Collection Qdrant dang dung: `admission_chunks_dnc_2026`.
- [ ] Benchmark hybrid moi nhat da pass gate trong `data/eval/summary.json`.
- [ ] Artifacts benchmark da co day du:
  - `data/eval/questions.jsonl`
  - `data/eval/retrieval_results.jsonl`
  - `data/eval/error_analysis.jsonl`
  - `data/eval/summary.json`

## 2) Checklist Ban Giao Cho Team Vector

- [ ] Xac nhan Qdrant online tai `http://localhost:6333`.
- [ ] Chay lai validation chunks truoc khi upsert:

```powershell
.\.venv\Scripts\python.exe src\ingest\validate_chunks.py
```

- [ ] Upsert tu chunks vao Qdrant bang module mode:

```powershell
.\.venv\Scripts\python.exe -m src.ingest.upsert_qdrant
```

- [ ] Xac nhan embedding model runtime: `sentence-transformers/all-MiniLM-L6-v2`.
- [ ] Xac nhan retrieval runtime mode: `hybrid`.
- [ ] Xac nhan tham so candidate pool cho hybrid: `--hybrid-candidate-pool 20`.
- [ ] Xac nhan payload top1 tra ve co `citations`.
- [ ] Chay lai benchmark hybrid va doi chieu gate:

```powershell
.\.venv\Scripts\python.exe src\eval\benchmark_retrieval.py --collection admission_chunks_dnc_2026 --top-k 5 --retrieval-mode hybrid
```

- [ ] Gate can dat sau khi team vector tiep nhan:
  - Recall@5 >= 0.80
  - Precision@1 >= 0.60
  - Citation Coverage = 1.00
  - Noise Rate@1 <= 0.20
  - Out-of-scope Safe Rate = 1.00

## 3) Checklist Ban Giao Cho Team Graph

- [ ] Xac nhan Neo4j online (`7474`, `7687`) theo `docker-compose.yml`.
- [ ] Dinh nghia mapping tu chunk payload sang graph entity (de nghi):
  - Node `Document` (doc_id, source_url, intake_year, document_type)
  - Node `Chunk` (chunk_id, chunk_index, chunk_text)
  - Node `Major` (major_code, major_name)
  - Node `Method` (admission_method)
  - Node `Campus` (campus)
  - Node `Audience` (target_audience)

- [ ] Dinh nghia quan he (de nghi):
  - `(:Document)-[:HAS_CHUNK]->(:Chunk)`
  - `(:Chunk)-[:MENTIONS_MAJOR]->(:Major)`
  - `(:Chunk)-[:USES_METHOD]->(:Method)`
  - `(:Chunk)-[:AT_CAMPUS]->(:Campus)`
  - `(:Chunk)-[:FOR_AUDIENCE]->(:Audience)`

- [ ] Bao toan truy vet nguon cho moi node/edge suy dien tu chunk:
  - Luu `chunk_id`, `doc_id`, `source_url` de trace-back.
- [ ] Tao script ingest graph idempotent (rerun khong duplicate node/edge).
- [ ] Tao bo query smoke-test graph (VD: tim major, method, campus, contact).
- [ ] Dinh nghia quy uoc merge voi vector retriever (hybrid retrieval + graph hop).

## 4) Joint Integration Checklist (Vector + Graph)

- [ ] Thong nhat contract input retrieval: `question -> top_k_results + decision.abstain`.
- [ ] Thong nhat contract output cho answer layer:
  - `answer_text`
  - `citations[]`
  - `supporting_chunk_ids[]`
  - `confidence`
  - `abstain_reason` (neu co)

- [ ] Test 3 nhom cau hoi:
  - In-scope factual
  - In-scope noisy wording
  - Out-of-scope an toan

- [ ] Doi chieu lai ket qua voi bo benchmark `data/eval/questions.jsonl`.
- [ ] Khong cho phep answer khong co citation trong luong in-scope.

## 5) Sign-off

- [ ] Data Engineer sign-off: chunks + benchmark artifacts da dong bo.
- [ ] Vector Lead sign-off: retrieval runtime dat gate.
- [ ] Graph Lead sign-off: graph ingest + query smoke-test dat.
- [ ] PM/Tech Lead sign-off: san sang giai doan tich hop chatbot.

## 6) Known Note

- `data/eval/error_analysis.jsonl` hien con 2 `recall_miss` (Q010, Q014).
- Bo van dat gate handoff; 2 case tren duoc xep vao backlog toi uu tiep theo, khong chan handoff.