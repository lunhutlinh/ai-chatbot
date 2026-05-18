# Retrieval Evaluation Pack

Muc tieu: kiem thu chat luong retrieval truoc khi ban giao cho team vector/graph.

## Handoff-ready Status (2026-04-14)

Nguon su that: `summary.json`.

- overall_pass: true
- retrieval_mode: hybrid
- collection: `admission_chunks_dnc_2026`
- hybrid_candidate_pool: 20

Metric hien tai:

- Recall@5: 0.9524
- Precision@1: 0.8095
- Citation Coverage: 1.0
- Noise Rate@1: 0.1667
- Out-of-scope Safe Rate: 1.0
- Hard Recall@5: 1.0

Ket luan: bo hien tai dat gate ban giao.

## Files

- `questions.jsonl`: bo cau hoi benchmark (in-scope + out-of-scope).
- `retrieval_results.jsonl`: ket qua top-k cho tung cau hoi.
- `error_analysis.jsonl`: cac cau hoi that bai de phan tich loi.
- `summary.json`: tong hop metric + pass/fail.
- `HANDOFF_CHECKLIST.md`: checklist ban giao cho team vector/graph.

## Quick Runbook

Dry-run bo cau hoi:

```powershell
.\.venv\Scripts\python.exe src\eval\benchmark_retrieval.py --dry-run
```

Run benchmark hybrid (khuyen nghi de xac nhan truoc handoff):

```powershell
.\.venv\Scripts\python.exe src\eval\benchmark_retrieval.py --collection admission_chunks_dnc_2026 --top-k 5 --retrieval-mode hybrid
```

Neu dang dung venv khac, thay `.\.venv\Scripts\python.exe` bang interpreter dung cua project.

## Acceptance Gate

- Recall@5 >= 0.80
- Precision@1 >= 0.60
- Citation Coverage = 1.00
- Noise Rate@1 <= 0.20
- Out-of-scope Safe Rate = 1.00

## Retrieval Mode Note

- `retrieval-mode vector`: don gian, de danh gia baseline.
- `retrieval-mode hybrid`: khuyen nghi cho runtime vi can bang do chinh xac + out-of-scope safety.

## Handoff Checklist

Xem chi tiet tai `HANDOFF_CHECKLIST.md`.
