import argparse
import json
import re
from html import unescape
from pathlib import Path
from typing import Iterable

BASE_DIR = Path(__file__).resolve().parents[2]

DEFAULT_INPUT = BASE_DIR / "data" / "raw" / "tuyen_sinh_nctu_homepage.html"
DEFAULT_OUTPUT = BASE_DIR / "data" / "processed" / "chunks" / "chunks.jsonl"

DEFAULT_DOC_ID = "DNC-2026-tuyensinh-home-v1"
DEFAULT_SOURCE_URL = "https://tuyensinh.nctu.edu.vn/"
DEFAULT_SOURCE_NAME = "tuyensinh.nctu.edu.vn"


def token_count(text: str) -> int:
    return len([t for t in re.split(r"\s+", text.strip()) if t])


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_paragraphs(text: str) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    cleaned: list[str] = []
    seen: set[str] = set()
    for p in paragraphs:
        p = p.replace("\u00a0", " ")
        p = _normalize_spaces(p)
        if not p or len(p) < 40:
            continue
        if p in seen:
            continue
        seen.add(p)
        cleaned.append(p)
    return cleaned


def html_to_text(html: str) -> str:
    # Remove scripts/styles (large and not useful for retrieval).
    html = re.sub(r"<script[\s\S]*?</script>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<style[\s\S]*?</style>", "\n", html, flags=re.IGNORECASE)

    # Remove HTML comments (including Next.js placeholders).
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)

    # Preserve some boundaries before stripping tags.
    html = re.sub(
        r"</(p|div|section|header|footer|li|h\d|tr|td)>",
        "\n",
        html,
        flags=re.IGNORECASE,
    )
    html = re.sub(r"<(br\s*/?)>", "\n", html, flags=re.IGNORECASE)

    # Strip remaining tags.
    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)

    # Normalize whitespace.
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def split_sentences(paragraph: str) -> list[str]:
    # Simple rule: keep punctuation as sentence boundary.
    parts = re.split(r"(?<=[.!?])\s+", paragraph)
    sentences = [_normalize_spaces(p) for p in parts if _normalize_spaces(p)]
    return sentences


def pack_chunks(paragraphs: list[str], min_chars: int = 120, max_chars: int = 900) -> list[str]:
    chunks: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        if not buf:
            return
        merged = _normalize_spaces(" ".join(buf))
        if merged:
            chunks.append(merged)
        buf = []

    for p in paragraphs:
        if len(p) > max_chars:
            # Split long paragraph by sentences.
            flush()
            for s in split_sentences(p):
                if len(s) <= max_chars:
                    chunks.append(s)
                else:
                    # Hard split.
                    for i in range(0, len(s), max_chars):
                        chunks.append(_normalize_spaces(s[i : i + max_chars]))
            continue

        candidate = " ".join(buf + [p]) if buf else p
        if len(candidate) <= max_chars:
            buf.append(p)
            if len(candidate) >= min_chars:
                flush()
        else:
            flush()
            buf.append(p)
            if len(p) >= min_chars:
                flush()

    flush()
    return [c for c in chunks if len(c) >= 30]


def detect_admission_methods(text: str) -> list[str]:
    lower = text.lower()
    methods: list[str] = []
    if "học bạ" in lower or "hoc ba" in lower:
        methods.append("hoc_ba")
    if "tốt nghiệp thpt" in lower or "tot nghiep thpt" in lower or "thpt" in lower:
        methods.append("diem_thi_thpt")
    if "đánh giá năng lực" in lower or "danh gia nang luc" in lower or "tư duy" in lower or "tu duy" in lower:
        methods.append("danh_gia_nang_luc")
    # Unique while preserving order.
    dedup: list[str] = []
    for m in methods:
        if m not in dedup:
            dedup.append(m)
    return dedup


def extract_required_documents(text: str) -> list[str]:
    lower = text.lower()
    docs: list[str] = []
    patterns = [
        (r"căn cước công dân|cccd", "cccd"),
        (r"học bạ", "hoc_ba_thpt"),
        (r"phiếu đăng ký", "phieu_dang_ky"),
        (r"giấy chứng nhận tốt nghiệp|bằng tốt nghiệp", "giay_tot_nghiep"),
    ]
    if "hồ sơ" not in lower and "ho so" not in lower:
        return []
    for pat, key in patterns:
        if re.search(pat, lower):
            docs.append(key)
    # Unique
    unique: list[str] = []
    for d in docs:
        if d not in unique:
            unique.append(d)
    return unique


def build_chunk_payload(
    chunk_text: str,
    *,
    chunk_index: int,
    doc_id: str,
    source_url: str,
    source_name: str,
    school_code: str,
    intake_year: int,
) -> dict:
    # IMPORTANT: Must match chunk.schema.json (additionalProperties=false)
    methods = detect_admission_methods(chunk_text)
    required_documents = extract_required_documents(chunk_text)

    payload = {
        "chunk_id": f"DNC-2026-TUYENSINH-HOME-V1-CHUNK-{chunk_index + 1:04d}",
        "doc_id": doc_id,
        "chunk_index": chunk_index,
        "chunk_text": chunk_text,
        "token_count": token_count(chunk_text),
        "source_url": source_url,
        "school_code": school_code,
        "intake_year": intake_year,
        "document_type": "tuyen_sinh_homepage",
        "admission_method": methods,
        "major_codes": [],
        "major_names": [],
        "faculty": None,
        "degree_level": "dai_hoc",
        "training_form": "tong_quat",
        "subject_groups": [],
        "campus": ["can_tho"],
        "deadline_type": None,
        "deadline_date": None,
        "fee_min": None,
        "fee_max": None,
        "fee_unit": "VND",
        "required_documents": required_documents,
        "target_audience": ["thi_sinh"],
        "citations": [
            {
                "source_url": source_url,
                "source_name": source_name,
            }
        ],
        "quality_flags": [],
    }
    return payload


def read_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in {".html", ".htm"}:
        return html_to_text(raw)
    return raw


def maybe_backup_legacy(output_path: Path) -> None:
    if not output_path.exists():
        return

    try:
        first_line = output_path.read_text(encoding="utf-8").splitlines()[0].strip()
    except Exception:
        return

    if not first_line:
        return

    try:
        obj = json.loads(first_line)
    except Exception:
        return

    # Legacy format had keys like id/content/metadata.
    if isinstance(obj, dict) and ("content" in obj and "metadata" in obj):
        backup_path = output_path.with_name("chunks.legacy.jsonl")
        if not backup_path.exists():
            output_path.replace(backup_path)


def generate_rows(text: str, doc_id: str, source_url: str, source_name: str) -> Iterable[dict]:
    paragraphs = split_paragraphs(text)
    chunk_texts = pack_chunks(paragraphs)

    for idx, chunk_text in enumerate(chunk_texts):
        yield build_chunk_payload(
            chunk_text,
            chunk_index=idx,
            doc_id=doc_id,
            source_url=source_url,
            source_name=source_name,
            school_code="DNC",
            intake_year=2026,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build schema-compliant chunks for DNC admissions homepage")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--doc-id", default=DEFAULT_DOC_ID)
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--source-name", default=DEFAULT_SOURCE_NAME)
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"Input not found: {args.input}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    maybe_backup_legacy(args.output)

    text = read_text(args.input)
    rows = list(generate_rows(text, args.doc_id, args.source_url, args.source_name))
    if not rows:
        raise SystemExit("No chunks generated")

    with args.output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"generated={len(rows)} output={args.output}")


if __name__ == "__main__":
    main()
