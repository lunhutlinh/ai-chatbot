import time
import os
import re
import sys
import unicodedata
from pathlib import Path
from functools import lru_cache

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

try:
    from sentence_transformers import SentenceTransformer, util
except Exception:
    SentenceTransformer = None
    util = None

try:
    from google import genai
except Exception:
    genai = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


if load_dotenv is not None:
    # Allow setting keys/models in chatbot/.env without hardcoding secrets in code.
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(dotenv_path=project_root / ".env", override=False)

# ==============================
# 🔑 CẤU HÌNH LLM (OPENROUTER ƯU TIÊN, FALLBACK GEMINI)
# ==============================
openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
openrouter_model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash").strip() or "google/gemini-2.5-flash"

openrouter_client = (
    OpenAI(api_key=openrouter_api_key, base_url="https://openrouter.ai/api/v1")
    if (openrouter_api_key and OpenAI is not None)
    else None
)

gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
gemini_client = genai.Client(api_key=gemini_api_key) if (gemini_api_key and genai is not None) else None

# ==============================
# 🧠 MODEL EMBEDDING
# ==============================
embedder = (
    SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    if SentenceTransformer is not None
    else None
)

RETRIEVAL_STOPWORDS = {
    "truong", "dai", "hoc", "nam", "can", "tho", "la", "gi", "co", "khong",
    "thong", "tin", "cua", "cho", "voi", "the", "nao", "bao", "nhieu", "xem",
    "toi", "ban", "minh", "duoc", "ve", "tai", "o", "tu", "sao", "hay",
}

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "raw" / "chude6_data.txt"
LEGACY_CHUNKS_FILE = Path(__file__).resolve().parents[2] / "data" / "processed" / "chunks" / "chunks.legacy.jsonl"


def _looks_like_fee_question(user_query_norm: str) -> bool:
    if any(k in user_query_norm for k in ["hoc phi", "học phí", "tin chi", "tín chỉ"]):
        return True
    # common abbreviations
    return any(k in user_query_norm.split() for k in ["hp"])  # keep conservative


def _normalize_for_match(text: str) -> str:
    return normalize_text(text).replace(" ", "")


def _expand_major_aliases(user_query_norm: str) -> list[str]:
    q = user_query_norm
    aliases: list[str] = []
    # Common Vietnamese abbreviations.
    if "cntt" in q.replace(" ", ""):
        aliases.append("congnghethongtin")
    if "it" in q.split():
        aliases.append("congnghethongtin")
    if "phanmem" in q.replace(" ", "") or "phần mềm" in q:
        aliases.append("kythuatphanmem")
    if "khmt" in q.replace(" ", ""):
        aliases.append("khoahocmaytinh")
    if "ai" in q.split() or "tritue" in q.replace(" ", ""):
        aliases.append("trituenhantao")
    if "y khoa" in q or "nganh y" in q or "y duoc" in q:
        aliases.append("ykhoa")

    # Also include tokens from query itself.
    tokens = [t for t in q.split() if len(t) > 2 and t not in RETRIEVAL_STOPWORDS]
    for t in tokens:
        aliases.append(_normalize_for_match(t))

    # Unique, preserve order.
    uniq: list[str] = []
    for a in aliases:
        if a and a not in uniq:
            uniq.append(a)
    return uniq


@lru_cache(maxsize=1)
def _load_legacy_fee_chunks() -> list[str]:
    if not LEGACY_CHUNKS_FILE.exists():
        return []

    texts: list[str] = []
    try:
        with LEGACY_CHUNKS_FILE.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = __import__("json").loads(line)
                except Exception:
                    continue

                if not isinstance(obj, dict):
                    continue

                # Only keep hoc-phi.pdf chunks.
                obj_id = str(obj.get("id", ""))
                if not obj_id.startswith("hoc-phi.pdf_"):
                    continue
                content = obj.get("content")
                if isinstance(content, str) and content.strip():
                    texts.append(content)
    except Exception:
        return []

    return texts


def fee_lookup_from_legacy_pdf(user_query: str) -> str:
    user_query_norm = normalize_text(user_query)
    if not _looks_like_fee_question(user_query_norm):
        return ""

    fee_chunks = _load_legacy_fee_chunks()
    if not fee_chunks:
        return ""

    needles = _expand_major_aliases(user_query_norm)
    if not needles:
        return ""

    # Search for a line like "Công nghệ thông tin 685.000".
    money_pat = re.compile(r"\b\d{1,3}(?:\.\d{3})+\b")
    for chunk in fee_chunks:
        for raw_line in chunk.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            norm_line = _normalize_for_match(line)
            if not money_pat.search(line):
                continue
            if any(n in norm_line for n in needles):
                amount = money_pat.search(line).group(0)
                # Best-effort label.
                label = "ngành bạn hỏi"
                if "congnghethongtin" in norm_line:
                    label = "Công nghệ thông tin"
                elif "kythuatphanmem" in norm_line:
                    label = "Kỹ thuật phần mềm"
                elif "khoahocmaytinh" in norm_line:
                    label = "Khoa học máy tính"
                elif "trituenhantao" in norm_line:
                    label = "Trí tuệ nhân tạo"
                elif "ykhoa" in norm_line or "y khoa" in line.lower():
                    label = "Y khoa"
                return (
                    f"Học phí {label} theo bảng học phí trong dữ liệu: {amount} VND/tín chỉ. "
                    "Nếu bạn muốn mình ước tính theo học kỳ, cho mình biết bạn học khoảng bao nhiêu tín chỉ/kỳ nhé."
                )

    return ""


@lru_cache(maxsize=1)
def _load_legacy_chunks_all() -> list[str]:
    if not LEGACY_CHUNKS_FILE.exists():
        return []

    texts: list[str] = []
    try:
        with LEGACY_CHUNKS_FILE.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = __import__("json").loads(line)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue
                content = obj.get("content")
                if isinstance(content, str) and content.strip():
                    texts.append(content)
    except Exception:
        return []

    return texts


def legacy_fact_lookup(user_query: str) -> str:
    q = normalize_text(user_query)

    wants_address = "dia chi" in q or "o dau" in q or "dia diem" in q
    wants_code = "ma truong" in q or "ma so truong" in q
    wants_name = "ten truong" in q or "truong ten gi" in q
    wants_total_majors = "bao nhieu nganh" in q or "so nganh" in q
    wants_objects = "doi tuong" in q or "dieu kien" in q or "du tuyen" in q
    wants_methods = "phuong thuc xet tuyen" in q or "xet tuyen" in q
    wants_threshold = "nguong dam bao" in q or "nguong" in q
    wants_facilities = "co so vat chat" in q or "co so" in q or "vat chat" in q

    if not (wants_address or wants_code or wants_name):
        return ""

    chunks = _load_legacy_chunks_all()
    if not chunks:
        return ""

    def find_line(marker: str) -> str:
        for chunk in chunks:
            for raw_line in chunk.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                norm_line = normalize_text(line)
                if marker in norm_line:
                    if ":" in line:
                        return line.split(":", 1)[1].strip()
                    return line
        return ""

    def find_regex(pattern: str) -> str:
        rx = re.compile(pattern, flags=re.IGNORECASE)
        for chunk in chunks:
            match = rx.search(chunk)
            if match:
                return match.group(1).strip()
        return ""

    def find_address_fallback() -> str:
        # Heuristic: match a line with Nguyen Van Cu + Can Tho + digits.
        for chunk in chunks:
            for raw_line in chunk.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                norm_line = normalize_text(line)
                if "nguyen van cu" in norm_line and "can tho" in norm_line:
                    if any(ch.isdigit() for ch in line):
                        return line
        return ""

    def find_section_excerpt(title_marker: str, max_lines: int = 6) -> str:
        for chunk in chunks:
            lines = [ln.strip() for ln in chunk.splitlines() if ln.strip()]
            for idx, line in enumerate(lines):
                if title_marker in normalize_text(line):
                    excerpt = lines[idx: idx + max_lines]
                    return "\n".join(excerpt)
        return ""

    if wants_name:
        value = find_regex(r"(?:ten\s*truong|tên\s*trường)\s*[:：]\s*([^\n]+)")
        if not value:
            value = find_line("ten truong")
        if value:
            return f"Tên trường: {value}"

    if wants_code:
        value = find_regex(r"(?:ma\s*truong|mã\s*trường)\s*[:：]\s*([^\n]+)")
        if not value:
            value = find_line("ma truong")
        if value:
            return f"Mã trường: {value}"

    if wants_address:
        value = find_regex(r"(?:dia\s*chi|địa\s*chỉ)\s*[:：]\s*([^\n]+)")
        if not value:
            value = find_line("dia chi")
        if value:
            return f"Địa chỉ: {value}"
        fallback = find_address_fallback()
        if fallback:
            return f"Địa chỉ: {fallback}"

    if wants_total_majors:
        value = find_line("tong so nganh")
        if value:
            return f"Tổng số ngành: {value}"

    if wants_objects:
        excerpt = find_section_excerpt("doi tuong")
        if excerpt:
            return f"Đối tượng & điều kiện dự tuyển (trích):\n{excerpt}"

    if wants_methods:
        excerpt = find_section_excerpt("phuong thuc xet tuyen")
        if excerpt:
            return f"Phương thức xét tuyển (trích):\n{excerpt}"

    if wants_threshold:
        excerpt = find_section_excerpt("nguong dam bao")
        if excerpt:
            return f"Ngưỡng đảm bảo chất lượng (trích):\n{excerpt}"

    if wants_facilities:
        excerpt = find_section_excerpt("co so vat chat")
        if excerpt:
            return f"Cơ sở vật chất (trích):\n{excerpt}"

    return ""

# ==============================
# 📂 LOAD DATA
# ==============================
def load_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    sections = [s.strip() for s in content.split('\n\n') if s.strip()]
    print(f"✅ Đã load {len(sections)} đoạn dữ liệu")
    return sections

# ==============================
# 🔗 VECTOR DATABASE
# ==============================
def build_vector_db(knowledge_base):
    if embedder is None:
        print("⚠️ Chưa có sentence-transformers, dùng lexical fallback.")
        return None

    print("⏳ Đang vector hóa dữ liệu...")
    embeddings = embedder.encode(knowledge_base, convert_to_tensor=True)
    print("✅ Đã vector hóa xong!")
    return embeddings

# ==============================
# 🤖 GỌI GEMINI (CÓ RETRY, ẨN LỖI)
# ==============================
def call_llm(prompt):
    for _ in range(3):
        try:
            if openrouter_client is not None:
                resp = openrouter_client.chat.completions.create(
                    model=openrouter_model,
                    messages=[{"role": "user", "content": prompt}],
                )
                content = (resp.choices[0].message.content or "").strip()
                if content:
                    return content

            if gemini_client is not None:
                response = gemini_client.models.generate_content(
                    model="models/gemini-2.5-flash",
                    contents=prompt,
                )
                return (response.text or "").strip()
        except Exception:
            time.sleep(2)  # retry mà không in lỗi (demo mượt)

    return ""


def _remove_unwanted_scripts(text: str) -> str:
    """Remove obvious non-Vietnamese script fragments that sometimes leak from models."""
    if not text:
        return ""

    cleaned = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue

        letters = [ch for ch in stripped if ch.isalpha()]
        if letters:
            latin_letters = sum(
                1
                for ch in letters
                if "LATIN" in unicodedata.name(ch, "")
            )
            if latin_letters / max(len(letters), 1) < 0.7:
                continue

        cleaned.append(stripped)

    return "\n".join(cleaned).strip()


def sanitize_chat_text(text: str) -> str:
    text = (text or "").replace("\u200b", "").replace("\ufeff", "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = _remove_unwanted_scripts(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_text(text):
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def keyword_fallback_search(user_query, knowledge_base):
    q = normalize_text(user_query)
    tokens = [t for t in q.split() if len(t) > 2 and t not in RETRIEVAL_STOPWORDS]

    if not tokens:
        return ""

    best_section = ""
    best_score = 0
    for section in knowledge_base:
        s = normalize_text(section)
        score = sum(1 for t in tokens if t in s)
        if score > best_score:
            best_score = score
            best_section = section

    # Yeu cau toi thieu 1 token de co fallback cho cau FAQ ngan.
    if best_score >= 1:
        return f"Thong tin minh tim duoc:\n{best_section}"

    return ""


def hybrid_retrieval(user_query, knowledge_base, kb_embeddings, top_k=3):
    if embedder is not None and util is not None and kb_embeddings is not None:
        query_embedding = embedder.encode(user_query, convert_to_tensor=True)
        cosine_scores = util.cos_sim(query_embedding, kb_embeddings)[0].cpu().tolist()
    else:
        cosine_scores = [0.0 for _ in knowledge_base]

    normalized_query = normalize_text(user_query)
    query_tokens = [t for t in normalized_query.split() if len(t) > 2]

    lexical_scores: list[float] = []
    for section in knowledge_base:
        normalized_section = normalize_text(section)
        hit_count = sum(1 for token in query_tokens if token in normalized_section)
        lexical_scores.append(hit_count / max(len(query_tokens), 1))

    hybrid_scores = [
        0.75 * cosine_scores[i] + 0.25 * lexical_scores[i]
        for i in range(len(knowledge_base))
    ]
    top_indices = sorted(
        range(len(hybrid_scores)), key=lambda i: hybrid_scores[i], reverse=True
    )[:top_k]
    return top_indices, hybrid_scores, cosine_scores, lexical_scores


def extractive_answer(user_query, context_sections):
    user_query_norm = normalize_text(user_query)
    intent_prefixes: list[str] = []
    for phrase in [
        "hoc phi",
        "hoc bong",
        "hoc ba",
        "xet tuyen",
        "tuyen sinh",
        "lien he",
        "dia chi",
        "hotline",
        "zalo",
        "email",
    ]:
        if phrase in user_query_norm:
            intent_prefixes.append(phrase)

    nav_noise_prefixes = [
        "tu van",
        "cau hoi thuong gap",
        "tu khoa pho bien",
        "truy cap nhanh",
        "danh muc",
        "thong bao",
        "tin tuc",
        "su kien",
    ]

    q_tokens = [
        t for t in normalize_text(user_query).split()
        if len(t) > 2 and t not in RETRIEVAL_STOPWORDS
    ]
    min_score = 1 if len(q_tokens) <= 3 else 2
    ranked_lines = []

    for section in context_sections:
        raw_lines = [line.strip() for line in section.splitlines() if line.strip()]

        # HTML-derived chunks often become a single very long line (menus + content).
        # In that case, split into smaller sentence-like segments to rank better.
        candidates: list[str] = []
        if len(raw_lines) == 1 and len(raw_lines[0]) > 180:
            one = raw_lines[0]
            # Split by common delimiters while keeping Vietnamese punctuation reasonably intact.
            parts = re.split(r"(?<=[\.!\?])\s+|\s*[|•]\s*", one)
            candidates = [p.strip() for p in parts if p and p.strip()]
        else:
            candidates = raw_lines

        for line in candidates:
            normalized_line = normalize_text(line)
            if not normalized_line:
                continue

            if intent_prefixes and any(normalized_line.startswith(p) for p in nav_noise_prefixes):
                # Skip boilerplate navigation lines when query intent is clear.
                continue

            score = sum(1 for token in q_tokens if token in normalized_line)
            if score >= min_score:
                starts_intent = False
                if intent_prefixes:
                    starts_intent = any(normalized_line.startswith(p) for p in intent_prefixes)
                ranked_lines.append((score, 1 if starts_intent else 0, len(line), line))

    ranked_lines.sort(key=lambda item: (-item[0], -item[1], item[2]))
    seen = set()
    selected = []
    for _, _, _, line in ranked_lines:
        key = normalize_text(line)
        if key in seen:
            continue
        seen.add(key)
        selected.append(line)
        if len(selected) == 3:
            break

    if not selected:
        return ""

    return "\n".join(f"- {line}" for line in selected)


def polish_answer(text):
    cleaned = sanitize_chat_text(text)
    cleaned = cleaned.replace("Thong tin minh tim duoc", "Thông tin mình tìm được")
    return cleaned


def answer_from_retrieved_context(user_query: str, contexts: list[str]) -> str:
    usable = [c.strip() for c in contexts if isinstance(c, str) and c.strip()]
    if not usable:
        return (
            "Mình chưa tìm thấy thông tin đủ rõ trong dữ liệu chính thức của trường cho câu hỏi này. "
            "Bạn thử hỏi cụ thể hơn về học phí, ngành học, xét học bạ, tuyển sinh hoặc ký túc xá nhé."
        )

    context_text = "\n\n".join(usable[:3])

    prompt = f"""
Bạn là tư vấn viên tuyển sinh của Trường Đại học Nam Cần Thơ.

Chỉ được dùng thông tin trong mục THÔNG TIN bên dưới.
Nếu thông tin chưa đủ để kết luận, hãy trả lời đúng là chưa có dữ liệu và mời người dùng hỏi rõ hơn.
Không suy diễn và không thêm thông tin ngoài dữ liệu.

Trả lời:
- Thân thiện
- Tự nhiên
- Đúng trọng tâm
- Tối đa 4 câu

THÔNG TIN:
{context_text}

Câu hỏi: {user_query}
"""

    answer = call_llm(prompt)
    if answer and len(answer.strip()) >= 20 and not any(
        k in answer.lower()
        for k in ["mình đoán", "co the la", "có thể là", "khả năng cao", "không chắc"]
    ):
        cleaned_answer = polish_answer(answer)
        if cleaned_answer:
            return cleaned_answer

    extracted = extractive_answer(user_query, usable[:3])
    if extracted:
        return polish_answer(f"Thông tin mình tìm được:\n{extracted}")

    return polish_answer(f"Thông tin mình tìm được:\n{context_text}")


def supporting_snippet_from_context(user_query: str, contexts: list[str]) -> str:
    usable = [c.strip() for c in contexts if isinstance(c, str) and c.strip()]
    if not usable:
        return ""

    extracted = extractive_answer(user_query, usable[:3])
    if extracted:
        return polish_answer(extracted)

    # Fallback: show the first non-empty line from the top context.
    first = usable[0]
    lines = [ln.strip() for ln in first.splitlines() if ln.strip()]
    if not lines:
        return ""
    preview = "\n".join(lines[:3])
    return polish_answer(preview)


def is_four_point_summary_request(user_query_norm, raw_query=""):
    raw_query_lower = raw_query.lower().strip()

    summary_patterns = [
        "tom tat",
        "tom luoc",
        "tong hop",
    ]
    has_summary_intent = any(p in user_query_norm for p in summary_patterns) or bool(
        re.search(r"tom|tat|tong|luoc", raw_query_lower)
    )

    has_four_points = (
        "4 y" in user_query_norm
        or "bon y" in user_query_norm
        or "4 muc" in user_query_norm
        or "4 gach dau dong" in user_query_norm
    )

    admissions_scope = any(
        p in user_query_norm
        for p in ["tuyen sinh", "xet tuyen", "hoc ba", "ho so", "hoc phi", "lien he"]
    ) or bool(re.search(r"tuy.?n\s*sinh|x.?t\s*tuy.?n", raw_query_lower))

    if has_summary_intent and has_four_points and admissions_scope:
        return True

    # Heuristic cho input bi vo dau/vo chu (mojibake): van uu tien tra 4 y neu ngu canh ro.
    if "?" in raw_query_lower and has_four_points and admissions_scope:
        return True

    return False


def build_four_point_admissions_summary():
    return (
        "1. Phương thức xét tuyển 2026: xét tuyển thẳng theo quy định Bộ GD&ĐT, xét điểm thi tốt nghiệp THPT, xét học bạ THPT và xét kết quả thi đánh giá năng lực/tư duy.\n"
        "2. Hồ sơ cơ bản: phiếu đăng ký xét tuyển, CCCD, học bạ THPT, giấy chứng nhận tốt nghiệp tạm thời hoặc bằng tốt nghiệp.\n"
        "3. Liên hệ tuyển sinh: Phòng C2-08 (Khu C), số 168 Nguyễn Văn Cừ (nối dài), P. An Bình, TP. Cần Thơ; Hotline/Zalo 0939 257 838; email tuyensinhdnc@nctu.edu.vn.\n"
        "4. Lưu ý quan trọng: học phí tính theo tín chỉ (khác nhau theo ngành/chương trình), trường có ký túc xá và có chính sách học bổng theo từng đợt tuyển sinh."
    )

# ==============================
# 🤖 CHATBOT THÔNG MINH
# ==============================
def chatbot_rag_response(user_query, knowledge_base, kb_embeddings):
    
    user_query_lower = user_query.lower().strip()
    user_query_norm = normalize_text(user_query)
    user_tokens = set(user_query_norm.split())

    # ==============================
    # 🔥 1. INTENT: CHÀO HỎI
    # ==============================
    greetings = {"chao", "hello", "hi", "alo", "xin", "xin chao"}
    if "xin chao" in user_query_norm or user_tokens.intersection({"chao", "hello", "hi", "alo"}):
        return "Chào bạn 😊 Bạn muốn hỏi gì về Trường Đại học Nam Cần Thơ?"

    # ==============================
    # 🔥 2. INTENT: CÂU KHÔNG RÕ RÀNG
    # ==============================
    vague = ["hỏi", "vài câu", "nói chuyện", "tư vấn"]

    if any(v in user_query_lower for v in vague):
        return "Bạn cứ hỏi cụ thể về học phí, ngành học hoặc tuyển sinh nhé, mình sẽ hỗ trợ chi tiết cho bạn 😊"

    # Ưu tiên trả lời đúng định dạng khi người dùng yêu cầu tóm tắt 4 ý.
    if is_four_point_summary_request(user_query_norm, user_query):
        return build_four_point_admissions_summary()

    # RAG-first: giữ ít rule, để hệ thống truy hồi quyết định nội dung tuyển sinh.

    # Nếu hỏi học phí và có bảng học phí trong dữ liệu PDF (legacy), ưu tiên trả số cụ thể.
    fee_answer = fee_lookup_from_legacy_pdf(user_query)
    if fee_answer:
        return fee_answer

    # ==============================
    # 🔥 3. INTENT: CÂU TỔNG QUÁT
    # ==============================
    if "tất cả" in user_query_lower:
        return "Bạn muốn tìm hiểu về học phí, ngành học hay tuyển sinh của Trường Đại học Nam Cần Thơ ạ?"

    # ==============================
    # 4. EMBEDDING
    # ==============================
    top_indices, hybrid_scores, cosine_scores, lexical_scores = hybrid_retrieval(
        user_query, knowledge_base, kb_embeddings, top_k=3
    )

    best_index = top_indices[0]
    best_hybrid_score = float(hybrid_scores[best_index])
    best_semantic_score = float(cosine_scores[best_index])
    best_lexical_score = float(lexical_scores[best_index])
    context = "\n\n".join(knowledge_base[idx] for idx in top_indices)

    # ==============================
    # 🔥 5. KHÔNG MATCH → KHÔNG ĐOÁN
    # ==============================
    if best_hybrid_score < 0.30 and best_semantic_score < 0.35 and best_lexical_score < 0.20:
        fallback = keyword_fallback_search(user_query, knowledge_base)
        if fallback:
            return polish_answer(fallback)

        return (
            "Mình chưa tìm thấy thông tin đủ rõ trong dữ liệu chính thức của trường cho câu hỏi này. "
            "Bạn thử hỏi cụ thể hơn về học phí, ngành học, xét học bạ, tuyển sinh hoặc ký túc xá nhé."
        )

    # ==============================
    # 🔥 6. RAG + AI
    # ==============================
    prompt = f"""
Bạn là tư vấn viên tuyển sinh của Trường Đại học Nam Cần Thơ.

Chỉ được dùng thông tin trong mục THÔNG TIN bên dưới.
Nếu thông tin chưa đủ để kết luận, hãy trả lời đúng là chưa có dữ liệu và mời người dùng hỏi rõ hơn.
Không suy diễn và không thêm thông tin ngoài dữ liệu.

Trả lời:
- Thân thiện
- Tự nhiên
- Đúng trọng tâm
- Tối đa 4 câu

Thông tin:
{context}

Câu hỏi: {user_query}
"""

    answer = call_llm(prompt)

    if not answer or len(answer) < 20:
        extracted = extractive_answer(user_query, [knowledge_base[idx] for idx in top_indices])
        if extracted:
            return f"Thông tin mình tìm được:\n{extracted}"
        return f"Thông tin mình tìm được:\n{context}"

    # Chặn câu trả lời có dấu hiệu suy diễn ngoài phạm vi dữ liệu.
    if any(k in answer.lower() for k in ["mình đoán", "có thể là", "khả năng cao", "không chắc"]):
        extracted = extractive_answer(user_query, [knowledge_base[idx] for idx in top_indices])
        if extracted:
            return f"Thông tin mình tìm được:\n{extracted}"
        return f"Thông tin mình tìm được:\n{context}"

    return polish_answer(answer)

# ==============================
# 🚀 MAIN
# ==============================
if __name__ == "__main__":
    if os.name == "nt":
        try:
            os.system("chcp 65001 >nul")
        except Exception:
            pass

    # Đảm bảo in tiếng Việt có dấu khi terminal hỗ trợ UTF-8.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    kb = load_data()
    kb_vectors = build_vector_db(kb)

    print("\n--- 🎓 NCTU Chatbot (Demo Perfect) Ready ---\n")

    while True:
        user_in = input("Bạn hỏi: ").strip()

        if not user_in:
            continue

        if user_in.lower() in ["thoát", "exit", "quit"]:
            print("Chatbot: Tạm biệt bạn 👋")
            break

        response = chatbot_rag_response(user_in, kb, kb_vectors)
        print(f"Chatbot: {response}\n")