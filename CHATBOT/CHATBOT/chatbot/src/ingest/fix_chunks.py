import html
import json
import re
import urllib.request
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_PATH = BASE_DIR / "data/processed/chunks/chunks.jsonl"
DOCUMENTS_PATH = BASE_DIR / "data/processed/metadata/documents.jsonl"

DOC_ID = "DNC-2026-daihoc-chinhquy-nganh"
SOURCE_URL = (
    "https://tuyensinh.nctu.edu.vn/news/2026/"
    "thong-tin-tuyen-sinh-trinh-do-dai-hoc-nam-2026-hinh-thuc-dao-tao-chinh-quy"
)
SCHOOL = "dai_hoc_nam_can_tho"
SCHOOL_CODE = "DNC"
INTAKE_YEAR = 2026
DOCUMENT_TYPE = "admissions_notice"


TABLE_RE = re.compile(
    r'<thead class="table-primary">.*?<tbody>(?P<tbody>.*?)</tbody>',
    re.IGNORECASE | re.DOTALL,
)
ROW_RE = re.compile(r"<tr>(?P<row>.*?)</tr>", re.IGNORECASE | re.DOTALL)
CELL_RE = re.compile(r"<t[dh](?P<attrs>[^>]*)>(?P<body>.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
LI_RE = re.compile(r"<li[^>]*>(.*?)</li>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")


def fetch_html(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def html_to_lines(fragment: str) -> list[str]:
    fragment = BR_RE.sub("\n", fragment)
    fragment = TAG_RE.sub("", fragment)
    fragment = html.unescape(fragment)
    lines = [normalize_spaces(line) for line in fragment.splitlines()]
    return [line for line in lines if line]


def html_to_text(fragment: str) -> str:
    return normalize_spaces(" ".join(html_to_lines(fragment)))


def extract_table(html_source: str) -> str:
    match = TABLE_RE.search(html_source)
    if not match:
        raise RuntimeError("Could not locate the admissions table in the source HTML")
    return match.group("tbody")


def extract_rowspan(attrs: str) -> int:
    match = re.search(r'rowspan="(\d+)"', attrs, flags=re.IGNORECASE)
    return int(match.group(1)) if match else 1


def parse_name_cell(cell_html: str) -> tuple[str, list[str]]:
    aliases = [html_to_text(item) for item in LI_RE.findall(cell_html)]
    summary_html = re.sub(r"<ul.*?</ul>", "", cell_html, flags=re.IGNORECASE | re.DOTALL)
    summary_lines = html_to_lines(summary_html)
    summary = summary_lines[0] if summary_lines else ""
    return summary, aliases


def parse_subject_groups(cell_html: str) -> list[str]:
    lines = html_to_lines(cell_html)
    return [line for line in lines if line]


def build_chunk_text(major_name: str, major_codes: list[str], aliases: list[str], subject_groups: list[str]) -> str:
    parts = [f"Ngành {major_name}"]
    if aliases:
        parts.append("Biến thể: " + "; ".join(aliases))
    if major_codes:
        parts.append("Mã ngành: " + ", ".join(major_codes))
    if subject_groups:
        parts.append("Tổ hợp xét tuyển: " + "; ".join(subject_groups))
    return ". ".join(parts)


def slugify(text: str) -> str:
    text = text.lower()
    text = html.unescape(text)
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text.strip())
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def token_count(text: str) -> int:
    return len([token for token in re.split(r"\s+", text.strip()) if token])


def parse_rows(tbody_html: str) -> list[dict]:
    rows = []
    current_subject_groups: list[str] = []
    subject_rows_remaining = 0

    for row_match in ROW_RE.finditer(tbody_html):
        row_html = row_match.group("row")
        cell_matches = list(CELL_RE.finditer(row_html))
        if len(cell_matches) < 3:
            continue

        tt_text = html_to_text(cell_matches[0].group("body"))
        if not tt_text.isdigit():
            continue

        order = int(tt_text)
        code_cell = cell_matches[1]
        name_cell = cell_matches[2]

        major_codes = html_to_lines(code_cell.group("body"))
        major_name, aliases = parse_name_cell(name_cell.group("body"))

        subject_groups: list[str] = []
        if len(cell_matches) >= 4:
            subject_cell = cell_matches[3]
            subject_groups = parse_subject_groups(subject_cell.group("body"))
            subject_rows_remaining = extract_rowspan(subject_cell.group("attrs")) - 1
            current_subject_groups = subject_groups
        elif subject_rows_remaining > 0:
            subject_groups = current_subject_groups
            subject_rows_remaining -= 1

        chunk_text = build_chunk_text(major_name, major_codes, aliases, subject_groups)
        rows.append(
            {
                "chunk_id": f"{DOC_ID}-major-{order:02d}",
                "chunk_index": order - 1,
                "chunk_text": chunk_text,
                "token_count": token_count(chunk_text),
                "source_url": SOURCE_URL,
                "school": SCHOOL,
                "school_code": SCHOOL_CODE,
                "doc_id": DOC_ID,
                "intake_year": INTAKE_YEAR,
                "document_type": DOCUMENT_TYPE,
                "major_order": order,
                "major_code": major_codes[0] if major_codes else "",
                "major_codes": major_codes,
                "major_name": major_name,
                "major_aliases": aliases,
                "subject_groups": subject_groups,
                "quality_flags": [],
                "citations": [
                    {
                        "source_url": SOURCE_URL,
                        "selector": f"tbody tr:nth-child({order})",
                    }
                ],
            }
        )

    return rows


def load_documents() -> list[dict]:
    if not DOCUMENTS_PATH.exists():
        return []

    with DOCUMENTS_PATH.open("r", encoding="utf-8") as handle:
        content = handle.read().strip()

    if not content:
        return []

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []

    return data if isinstance(data, list) else []


def sync_documents_metadata(chunk_count: int) -> None:
    documents = load_documents()

    updated_doc = {
        "doc_id": DOC_ID,
        "source_type": "official_website",
        "source_format": "html",
        "source_name": "thong-tin-tuyen-sinh-trinh-do-dai-hoc-nam-2026-hinh-thuc-dao-tao-chinh-quy",
        "source_path": "",
        "source_url": SOURCE_URL,
        "school": SCHOOL,
        "school_code": SCHOOL_CODE,
        "document_type": DOCUMENT_TYPE,
        "document_scope": "tuyen_sinh_dai_hoc_chinh_quy",
        "academic_year": "2025-2026",
        "intake_year": INTAKE_YEAR,
        "language": "vi",
        "chunk_count": chunk_count,
        "crawl_time": "2026-04-15T00:00:00+07:00",
        "version": "v1",
        "is_official": True,
        "trust_score": 0.95,
    }

    index = next((i for i, doc in enumerate(documents) if doc.get("doc_id") == DOC_ID), None)
    if index is None:
        index = next((i for i, doc in enumerate(documents) if doc.get("source_url") == SOURCE_URL), None)

    if index is None:
        documents.insert(0, updated_doc)
    else:
        documents[index] = {**documents[index], **updated_doc}

    DOCUMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DOCUMENTS_PATH.open("w", encoding="utf-8") as handle:
        json.dump(documents, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main() -> None:
    html_source = fetch_html(SOURCE_URL)
    tbody_html = extract_table(html_source)
    rows = parse_rows(tbody_html)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    sync_documents_metadata(chunk_count=len(rows))

    print(f"Generated {len(rows)} valid chunks")


if __name__ == "__main__":
    main()