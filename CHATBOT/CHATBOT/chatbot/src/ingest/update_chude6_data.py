import re
import ssl
from pathlib import Path
import urllib.request
import urllib.error
from html import unescape

SOURCE_URL = "https://tuyensinh.nctu.edu.vn/tu-van"
OUTPUT_FILE = Path(__file__).resolve().parents[2] / "data" / "raw" / "chude6_data.txt"


def fetch_html(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        },
    )
    secure_context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=30, context=secure_context) as response:
            return response.read().decode("utf-8", errors="ignore")
    except urllib.error.URLError as err:
        # Fallback cho moi truong Windows thieu CA bundle.
        if "CERTIFICATE_VERIFY_FAILED" not in str(err):
            raise

    insecure_context = ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=30, context=insecure_context) as response:
        return response.read().decode("utf-8", errors="ignore")


def html_to_text(html: str) -> str:
    html = re.sub(r"<script[\\s\\S]*?</script>", " ", html, flags=re.IGNORECASE)
    html = re.sub(r"<style[\\s\\S]*?</style>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def find_first(pattern: str, text: str, fallback: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return fallback
    return re.sub(r"\s+", " ", match.group(0)).strip()


def find_emails(text: str):
    emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}", text)
    unique = []
    for email in emails:
        if email.lower().endswith("@nctu.edu.vn") and email not in unique:
            unique.append(email)
    return unique


def build_knowledge(text: str) -> str:
    hotline = find_first(r"0939\s*257\s*838", text, "0939 257 838")
    phone_1 = find_first(r"0292\s*3798\s*168", text, "0292 3798 168")
    phone_2 = find_first(r"0292\s*3798\s*222", text, "0292 3798 222")
    phone_3 = find_first(r"0292\s*3798\s*333", text, "0292 3798 333")

    address = find_first(
        r"Số\s*168[^.]{0,140}Nguyễn\s*Văn\s*Cừ\s*\(nối\s*dài\)[^.]{0,120}Cần\s*Thơ",
        text,
        "Số 168, Nguyễn Văn Cừ (nối dài), P. An Bình, TP. Cần Thơ",
    )

    scholarship = find_first(
        r"Quỹ\s*22\s*tỷ\s*đồng[^.]{0,220}",
        text,
        "Quỹ học bổng tuyển sinh đại học 2026: 22 tỷ đồng dành cho tân sinh viên theo chương trình công bố.",
    )

    emails = find_emails(text)
    email_1 = "tuyensinhdnc@nctu.edu.vn"
    email_2 = "truyenthong@nctu.edu.vn"
    if emails:
        if len(emails) >= 1:
            email_1 = emails[0]
        if len(emails) >= 2:
            email_2 = emails[1]

    return f"""Trường Đại học Nam Cần Thơ (DNC) tuyển sinh đa ngành, gồm các nhóm: Sức khỏe, Kỹ thuật - Công nghệ, Kinh tế - Quản trị, Luật - Xã hội và Ngoại ngữ.

Phương thức xét tuyển đại học 2026 tại DNC gồm: xét tuyển thẳng theo quy định Bộ GD&ĐT, xét điểm thi tốt nghiệp THPT, xét học bạ THPT, và xét kết quả thi đánh giá năng lực hoặc tư duy.

Trường có xét học bạ THPT. Thí sinh có thể đăng ký theo tổ hợp 3 môn phù hợp với ngành đăng ký.

Hồ sơ xét tuyển thường gồm: phiếu đăng ký xét tuyển, căn cước công dân, học bạ THPT, giấy chứng nhận tốt nghiệp tạm thời hoặc bằng tốt nghiệp.

Học phí được tính theo tín chỉ và khác nhau theo ngành/chương trình đào tạo. Mức học phí cập nhật theo từng năm học.

Để tra cứu học phí mới nhất, tham khảo trang chính thức: https://nctu.edu.vn/hocphi

DNC có hệ thống ký túc xá trong khuôn viên, môi trường an toàn, đầy đủ tiện ích cho sinh viên.

Thông tin tuyển sinh 2026 cho biết ký túc xá có các tiện nghi cơ bản, hỗ trợ sinh viên đăng ký khi làm thủ tục nhập học.

Thông tin học bổng tuyển sinh: {scholarship}

Thông tin liên hệ tuyển sinh chính thức:
- Phòng C2-08 (Khu C)
- {address}
- Hotline/Zalo: {hotline}
- Điện thoại: {phone_1} - {phone_2} - {phone_3}
- Email: {email_1}
- Email: {email_2}

Kênh chính thức để theo dõi tuyển sinh:
- https://tuyensinh.nctu.edu.vn/
- https://dkxettuyen.nctu.edu.vn/

FAQ: Trường có ký túc xá không?
Trả lời: Có. Trường Đại học Nam Cần Thơ có hệ thống ký túc xá phục vụ sinh viên.

FAQ: Trường có xét học bạ không?
Trả lời: Có. Trường có xét tuyển học bạ THPT.

FAQ: Trường tuyển sinh theo phương thức nào?
Trả lời: Gồm xét tuyển thẳng, xét điểm thi tốt nghiệp THPT, xét học bạ THPT, và xét kết quả thi đánh giá năng lực/tư duy.

FAQ: Nếu cần tư vấn trực tiếp thì liên hệ ở đâu?
Trả lời: Liên hệ Phòng C2-08 (Khu C), {address} hoặc gọi Hotline/Zalo {hotline}.
"""


def main():
    print("Đang tải dữ liệu từ website tuyển sinh...")
    html = fetch_html(SOURCE_URL)
    text = html_to_text(html)
    knowledge = build_knowledge(text)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(knowledge.strip() + "\n")

    print(f"Đã cập nhật {OUTPUT_FILE} từ {SOURCE_URL}")


if __name__ == "__main__":
    main()