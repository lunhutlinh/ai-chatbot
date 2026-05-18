import re
import unicodedata
from typing import Any

NOISE_MARKERS = [
    "dang ky ngay",
    "tu khoa pho bien",
    "xem them",
    "dang tai",
    "all rights reserved",
    "truy cap nhanh",
    "tin tuc",
    "su kien",
]

PROGRAM_QUERY_MARKERS = [
    "he quoc te",
    "lien thong",
    "vb2",
    "vua lam vua hoc",
    "thac si",
    "tien si",
]

PROGRAM_CHUNK_MARKERS = [
    "he quoc te",
    "lien thong",
    "vb2",
    "vua lam vua hoc",
    "thac si",
    "tien si",
]

CRITICAL_OOS_PATTERNS = [
    "2027",
    "ha noi",
    "cong nghe thong tin",
    "cntt",
    "tri tue nhan tao",
    "lich thi",
    "hoc ky",
    "le phi",
    "qua buu dien",
    "ngay nhap hoc",
    "tung nganh",
    "sinh vien quoc te",
]

CONTACT_QUERY_MARKERS = [
    "email",
    "hotline",
    "zalo",
    "so dien thoai",
    "dien thoai",
    "lien he",
    "dia chi",
    "phong",
]

DIGITAL_QUERY_MARKERS = [
    "online",
    "truc tuyen",
    "ho tro",
    "vtour",
    "tham quan",
]

CONTACT_CHUNK_MARKERS = [
    "@",
    "hotline",
    "zalo",
    "dien thoai",
    "thong tin lien he",
    "phong c2-08",
    "nguyen van cu",
    "an binh",
]

DIGITAL_CHUNK_MARKERS = [
    "truc tuyen",
    "ho tro 24/7",
    "vtour",
    "tham quan truong",
    "dang ky xet tuyen",
]

STOPWORDS = {
    "la",
    "co",
    "khong",
    "va",
    "cua",
    "cho",
    "nhung",
    "nam",
    "truong",
    "dai",
    "hoc",
    "bao",
    "nhieu",
    "the",
    "nao",
    "tai",
    "ve",
    "duoc",
    "hay",
    "hoi",
    "cho",
    "em",
    "minh",
    "a",
    "oi",
    "voi",
    "khai",
}


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = text.replace("đ", "d")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize(text: str) -> list[str]:
    normalized = normalize_text(text)
    tokens = re.findall(r"[a-z0-9]+", normalized)
    return [t for t in tokens if len(t) >= 2 and t not in STOPWORDS]


def lexical_overlap_score(query: str, chunk_text: str) -> float:
    q_tokens = set(tokenize(query))
    if not q_tokens:
        return 0.0

    c_tokens = set(tokenize(chunk_text))
    overlap = len(q_tokens & c_tokens)
    return overlap / len(q_tokens)


def noise_penalty(chunk_text: str) -> float:
    normalized = normalize_text(chunk_text)
    hits = sum(1 for marker in NOISE_MARKERS if marker in normalized)

    penalty = 0.0
    if hits >= 1:
        penalty += 0.05
    if hits >= 2:
        penalty += 0.05

    if len(normalized) < 80:
        penalty += 0.06

    if len(normalized) < 40:
        penalty += 0.04

    return min(penalty, 0.2)


def intent_bonus(query: str, chunk_text: str) -> float:
    q = normalize_text(query)
    c = normalize_text(chunk_text)

    bonus = 0.0

    if any(marker in q for marker in CONTACT_QUERY_MARKERS):
        if any(marker in c for marker in CONTACT_CHUNK_MARKERS):
            bonus += 0.18
        if "@" in c:
            bonus += 0.08

    if any(marker in q for marker in DIGITAL_QUERY_MARKERS):
        if any(marker in c for marker in DIGITAL_CHUNK_MARKERS):
            bonus += 0.12

        if "24/7" in c or "vtour" in c:
            bonus += 0.06

    if any(marker in q for marker in PROGRAM_QUERY_MARKERS):
        if any(marker in c for marker in PROGRAM_CHUNK_MARKERS):
            bonus += 0.12

    return min(bonus, 0.2)


def blended_score(query: str, chunk_text: str, vector_score: float) -> tuple[float, float, float, float]:
    lex = lexical_overlap_score(query, chunk_text)
    bonus = intent_bonus(query, chunk_text)
    penalty = noise_penalty(chunk_text)

    # Blend dense semantic signal with lexical relevance and heuristic bonuses.
    score = 0.68 * vector_score + 0.32 * lex + bonus - penalty
    return score, lex, bonus, penalty


def rerank_hits(query: str, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []

    for item in hits:
        chunk_text = str(item.get("chunk_text", ""))
        vector_score = float(item.get("score", 0.0))
        hybrid_score, lexical_score, bonus, penalty = blended_score(query, chunk_text, vector_score)

        enriched = dict(item)
        enriched["vector_score"] = vector_score
        enriched["lexical_score"] = round(lexical_score, 4)
        enriched["intent_bonus"] = round(bonus, 4)
        enriched["noise_penalty"] = round(penalty, 4)
        enriched["hybrid_score"] = round(hybrid_score, 6)
        scored.append(enriched)

    scored.sort(key=lambda x: x["hybrid_score"], reverse=True)
    return scored


def extract_years(query: str) -> set[int]:
    years = re.findall(r"\b(20\d{2})\b", query)
    return {int(y) for y in years}


def _critical_mismatch(query: str, chunk_text: str) -> tuple[bool, str]:
    q = normalize_text(query)
    c = normalize_text(chunk_text)
    triggered = [p for p in CRITICAL_OOS_PATTERNS if p in q]
    if not triggered:
        return False, ""

    alias_map: dict[str, list[str]] = {
        "cntt": ["cong nghe thong tin"],
        "cong nghe thong tin": ["cntt"],
    }

    for pattern in triggered:
        candidates = [pattern] + alias_map.get(pattern, [])
        if not any(candidate in c for candidate in candidates):
            return True, pattern
    return False, ""


def should_abstain(query: str, ranked_hits: list[dict[str, Any]], intake_year: int = 2026) -> tuple[bool, str]:
    if not ranked_hits:
        return True, "no_hit"

    top = ranked_hits[0]
    top_hybrid = float(top.get("hybrid_score", 0.0))
    top_vector = float(top.get("vector_score", 0.0))
    top_lex = float(top.get("lexical_score", 0.0))

    mismatch, pattern = _critical_mismatch(query, str(top.get("chunk_text", "")))
    if mismatch:
        return True, f"critical_mismatch:{pattern}"

    # Keep this as a strict false-positive guard only for very weak lexical grounding.
    if top_vector >= 0.66 and top_lex < 0.10:
        return True, "semantic_only_low_lex"

    q = normalize_text(query)
    # Threshold is a guardrail, not a primary decision-maker. We keep it conservative
    # but not so strict that clearly relevant tuition/admissions chunks get rejected.
    min_hybrid = 0.40
    if any(marker in q for marker in CONTACT_QUERY_MARKERS + DIGITAL_QUERY_MARKERS):
        min_hybrid = 0.38

    if top_hybrid < min_hybrid:
        return True, "low_hybrid_score"

    return False, "answerable"
