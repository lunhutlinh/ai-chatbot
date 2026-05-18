from __future__ import annotations

import re

from fastapi import APIRouter
from pydantic import BaseModel

from src.retrieval.chude6_rag import (
    answer_from_retrieved_context,
    chatbot_rag_response,
    fee_lookup_from_legacy_pdf,
    load_data,
    build_vector_db,
    supporting_snippet_from_context,
)
from src.retrieval.neo4j_service import Neo4jService
from src.retrieval.qdrant_retriever import retrieve as qdrant_retrieve

router = APIRouter(tags=["chude6"])

kb = load_data()
kb_vectors = build_vector_db(kb)
neo4j_service = Neo4jService()


class ChatRequest(BaseModel):
    message: str


def _is_greeting(message: str) -> bool:
    text = (message or "").strip().lower()
    if not text:
        return True
    text = re.sub(r"\s+", " ", text)
    greetings = {
        "xin chao",
        "xin chào",
        "chao",
        "chào",
        "hello",
        "hi",
        "alo",
    }
    if text in greetings:
        return True
    return any(text.startswith(prefix) for prefix in ["xin chao", "xin chào", "chao", "chào"])


def _strip_accents(text: str) -> str:
    import unicodedata

    value = unicodedata.normalize("NFD", text or "")
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = value.replace("đ", "d").replace("Đ", "D")
    return value


def _resolve_major_subject(message: str) -> str:
    """Best-effort map from user text to the exact Entity.name in Neo4j."""

    raw = (message or "").strip().lower()
    if not raw:
        return ""

    norm = _strip_accents(raw)
    norm = " ".join(norm.split())
    compact = norm.replace(" ", "")

    # Common abbreviations
    if "cntt" in compact or "congnghethongtin" in compact or "it" in norm.split():
        return "Công nghệ thông tin"

    # Health majors
    # Users often type "ngành y" / "học phí y" meaning "Y khoa".
    if (
        "y khoa" in norm
        or "nganh y" in norm
        or re.search(r"\bnganh\s*y\b", norm)
        or re.search(r"\bhoc\s*phi\s*y\b", norm)
        or re.search(r"\bdiem\s*(chuan\s*)?y\b", norm)
    ):
        return "Y khoa"
    if "duoc hoc" in norm or ("duoc" in norm and "duoc" in norm.split()):
        return "Dược học"

    # Software / CS
    if "ky thuat phan mem" in norm or "phan mem" in norm:
        return "Kỹ thuật phần mềm"
    if "khoa hoc may tinh" in norm or "khmt" in compact:
        return "Khoa học máy tính"
    if "tri tue nhan tao" in norm or re.search(r"\bai\b", norm):
        return "Trí tuệ nhân tạo"

    return ""


def _is_official_data_question(message: str) -> bool:
    """Return True when the user asks about official, factual data that must come from the DB/RAG.

    Examples: học phí, điểm chuẩn, ngành, xét tuyển, học bạ, tuyển sinh.
    """
    text = (message or "").strip().lower()
    if not text:
        return False

    keywords = [
        "học phí",
        "hoc phi",
        "tín chỉ",
        "tin chi",
        "điểm chuẩn",
        "diem chuan",
        "điểm",
        "diem",
        "ngành",
        "nganh",
        "xét tuyển",
        "xet tuyen",
        "học bạ",
        "hoc ba",
        "tuyển sinh",
        "tuyen sinh",
    ]

    return any(k in text for k in keywords)


def _graph_fee_override(message: str, triples: list[dict[str, str]]) -> str:
    """If Neo4j contains explicit tuition triples for a major, answer directly."""

    if not triples:
        return ""

    text = (message or "").strip().lower()
    wants_fee = any(k in text for k in ["học phí", "hoc phi", "tín chỉ", "tin chi"])
    if not wants_fee:
        return ""

    subject = _resolve_major_subject(message)
    if subject:
        if not any((t.get("subject") or "").strip().lower() == subject.lower() for t in triples):
            return ""
    else:
        # If user didn't specify a major, don't guess.
        return ""

    amount = ""
    for t in triples:
        if (t.get("subject") or "").strip().lower() != subject.lower():
            continue
        pred = (t.get("predicate") or "").strip().lower().replace("_", " ")
        obj = (t.get("object") or "").strip()
        if not obj:
            continue
        if "co hoc phi" in pred or "học phí" in pred:
            amount = obj
            break

    if not amount:
        return ""

    return f"Học phí ngành {subject} là {amount} VND/tín chỉ."


def _graph_answer_override(message: str, triples: list[dict[str, str]]) -> str:
    """If Neo4j contains explicit score triples for a major, answer directly."""

    if not triples:
        return ""

    text = (message or "").strip().lower()
    wants_score = any(k in text for k in ["điểm", "diem", "hoc ba", "học bạ", "thpt", "đậu", "dau"])
    if not wants_score:
        return ""

    subject_hint = _resolve_major_subject(message)
    if subject_hint and not any(
        (t.get("subject") or "").strip().lower() == subject_hint.lower() for t in triples
    ):
        return ""

    subject = subject_hint or (triples[0].get("subject") or "").strip()
    if not subject:
        return ""

    thpt = ""
    hoc_ba = ""
    for t in triples:
        if (t.get("subject") or "").strip().lower() != subject.lower():
            continue
        pred = (t.get("predicate") or "").strip().lower().replace("_", " ")
        obj = (t.get("object") or "").strip()
        if not obj:
            continue
        if "co diem thpt" in pred or "điểm thpt" in pred:
            thpt = obj
        if "co diem hoc ba" in pred or "điểm học bạ" in pred:
            hoc_ba = obj

    if not (thpt or hoc_ba):
        return ""

    parts: list[str] = []
    if thpt:
        parts.append(f"THPT: {thpt}")
    if hoc_ba:
        parts.append(f"Học bạ: {hoc_ba}")

    joined = "; ".join(parts)
    
    # Users often say "điểm chuẩn" but the graph stores score references; be explicit.
    if "diem chuan" in _strip_accents(text):
        return f"Ngành {subject} có mức điểm tham khảo theo THPT/học bạ: {joined}."

    return f"Ngành {subject} có mức điểm tham khảo: {joined}."


def _should_append_graph_reply(message: str, triples: list[dict[str, str]]) -> bool:
    """Only attach graph details when they clearly match the question.

    This avoids leaking loosely related triples into the final answer.
    """
    if not triples:
        return False

    subject_hint = _resolve_major_subject(message)
    if subject_hint:
        return any((t.get("subject") or "").strip().lower() == subject_hint.lower() for t in triples)

    # If we do not have a clear subject hint, only append when the graph result set is coherent.
    subjects = {(t.get("subject") or "").strip().lower() for t in triples if (t.get("subject") or "").strip()}
    return len(subjects) == 1


@router.post("/chat")
def chat(req: ChatRequest):
    retrieval = None

    # High-precision override for tuition questions (from bundled hoc-phi.pdf legacy chunks).
    fee_answer = fee_lookup_from_legacy_pdf(req.message)
    if fee_answer:
        return {
            "reply": fee_answer,  # This is what the user sees
            "_debug": {  # Internal debugging only
                "rag_reply": fee_answer,
                "graph_reply": "",
                "graph_connected": neo4j_service.connected,
                "graph_results": [],
                "retrieval": {
                    "mode": "local_fee_lookup",
                    "abstain": None,
                    "reason": "fee_answer_from_legacy_pdf",
                    "citations": [],
                    "supporting_chunk_ids": [],
                    "top_k": None,
                    "collection": None,
                },
            },
        }

    # For greetings/smalltalk, prefer rule-based local handling.
    official = _is_official_data_question(req.message)

    if _is_greeting(req.message):
        rag_reply = chatbot_rag_response(req.message, kb, kb_vectors)
        retrieval = None
    else:
        try:
            retrieval = qdrant_retrieve(req.message)
        except Exception:
            retrieval = None

        # Prepare a conservative abstain message for official-data questions.
        base_official_missing = (
            "Mình chưa tìm thấy dữ liệu chính thức đủ rõ cho câu hỏi này. "
            "Bạn thử hỏi cụ thể hơn về học phí, ngành, điểm chuẩn, xét học bạ hoặc liên hệ bộ phận tuyển sinh nhé."
        )

        if retrieval and not retrieval.get("abstain"):
            contexts = [
                h.get("chunk_text", "")
                for h in retrieval.get("hits", [])
                if h.get("chunk_text")
            ]
            rag_reply = answer_from_retrieved_context(req.message, contexts)
        elif retrieval and retrieval.get("abstain"):
            # If vector retrieval abstains: for official-data questions, DO NOT let LLM invent answers.
            if official:
                contexts = [
                    h.get("chunk_text", "")
                    for h in retrieval.get("hits", [])
                    if h.get("chunk_text")
                ]
                snippet = supporting_snippet_from_context(req.message, contexts)
                rag_reply = base_official_missing
                if snippet:
                    rag_reply = f"{base_official_missing}\n\nThông tin gần nhất mình tìm được:\n{snippet}"
            else:
                # Non-official questions: allow LLM/local KB fallback.
                local_reply = chatbot_rag_response(req.message, kb, kb_vectors)
                if local_reply and not local_reply.lower().startswith("mình chưa tìm thấy"):
                    rag_reply = local_reply
                else:
                    contexts = [
                        h.get("chunk_text", "")
                        for h in retrieval.get("hits", [])
                        if h.get("chunk_text")
                    ]
                    snippet = supporting_snippet_from_context(req.message, contexts)
                    rag_reply = (
                        "Mình chưa tìm thấy thông tin đủ rõ trong dữ liệu chính thức cho câu hỏi này. "
                        "Bạn thử hỏi cụ thể hơn về tuyển sinh, học bạ, học phí, học bổng hoặc liên hệ nhé."
                    )
                    if snippet:
                        rag_reply = f"{rag_reply}\n\nThông tin gần nhất mình tìm được:\n{snippet}"
        else:
            # No retrieval results at all
            if official:
                rag_reply = base_official_missing
                retrieval = None
            else:
                rag_reply = chatbot_rag_response(req.message, kb, kb_vectors)

    # Graph lookup (prefer exact subject if user mentions a major).
    subject_hint = _resolve_major_subject(req.message)
    if subject_hint:
        triples = neo4j_service.fetch_subject_triples(subject_hint, limit=12)
    else:
        triples = neo4j_service.search_triples(req.message, limit=6)

    graph_reply = neo4j_service.format_triples(triples) if triples and _should_append_graph_reply(req.message, triples) else ""

    graph_fee = _graph_fee_override(req.message, triples)
    if graph_fee:
        rag_reply = graph_fee

    graph_override = _graph_answer_override(req.message, triples)
    if graph_override:
        rag_reply = graph_override

    reply = rag_reply
    if graph_reply:
        # Combine graph info naturally without exposing technical details
        reply = f"{rag_reply}\n\n{graph_reply}"

    # Only expose user-facing content, keep backend debug info separate
    return {
        "reply": reply,  # This is what the user sees
        "_debug": {  # Internal debugging only
            "rag_reply": rag_reply,
            "graph_reply": graph_reply,
            "graph_connected": neo4j_service.connected,
            "graph_results": triples,
            "retrieval": {
                "mode": (
                    retrieval.get("config").retrieval_mode
                    if retrieval and retrieval.get("config")
                    else "local"
                ),
                "abstain": (retrieval.get("abstain") if retrieval else None),
                "reason": (retrieval.get("reason") if retrieval else None),
                "citations": (retrieval.get("citations") if retrieval else []),
                "supporting_chunk_ids": (
                    retrieval.get("supporting_chunk_ids") if retrieval else []
                ),
                "top_k": (
                    retrieval.get("config").top_k
                    if retrieval and retrieval.get("config")
                    else None
                ),
                "collection": (
                    retrieval.get("config").collection
                    if retrieval and retrieval.get("config")
                    else None
                ),
            },
        },
    }


@router.get("/graph/stats")
def graph_stats():
    return neo4j_service.get_stats()


@router.get("/graph/search")
def graph_search(q: str, limit: int = 10):
    safe_limit = max(1, min(limit, 50))

    subject_hint = _resolve_major_subject(q)
    if subject_hint:
        triples = neo4j_service.fetch_subject_triples(subject_hint, limit=safe_limit)
    else:
        triples = neo4j_service.search_triples(q, limit=safe_limit)

    return {
        "query": q,
        "count": len(triples),
        "graph_connected": neo4j_service.connected,
        "results": triples,
        "formatted": neo4j_service.format_triples(triples),
    }


@router.post("/graph/normalize")
def graph_normalize(apply_changes: bool = False, limit: int = 5000):
    safe_limit = max(1, min(limit, 100000))
    return neo4j_service.normalize_graph_text(
        apply_changes=apply_changes,
        limit=safe_limit,
    )
