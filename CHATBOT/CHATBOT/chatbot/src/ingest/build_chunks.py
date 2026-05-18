import os
import json
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

def build_chunks():
    # 1. Định nghĩa đường dẫn
    raw_dir = "chatbot/data/raw"  
    output_file = "chatbot/data/processed/chunks/chunks.jsonl"
    
    # 2. Cấu hình bộ chia nhỏ văn bản (Đây là kỹ thuật quan trọng trong AI)
    # Chúng ta chia nhỏ để LLM dễ "tiêu hóa" và tìm kiếm chính xác hơn
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,    # Mỗi đoạn khoảng 1000 ký tự
        chunk_overlap=100,  # Gối đầu 100 ký tự để không mất ngữ cảnh giữa 2 đoạn
        separators=["\n\n", "\n", ".", " ", ""]
    )

    all_chunks = []

    # Kiểm tra nếu thư mục tồn tại
    if not os.path.exists(raw_dir):
        print(f"Lỗi: Không tìm thấy thư mục {raw_dir}")
        return

    # 3. Quét tất cả file PDF trong thư mục raw
    for filename in os.listdir(raw_dir):
        if filename.endswith(".pdf"):
            print(f"--- Đang đọc file: {filename} ---")
            path = os.path.join(raw_dir, filename)
            
            try:
                loader = PyPDFLoader(path)
                pages = loader.load()
                
                # Chia nhỏ nội dung của file PDF này
                chunks = text_splitter.split_documents(pages)
                
                for i, chunk in enumerate(chunks):
                    all_chunks.append({
                        "chunk_id": f"{filename}_{i}",
                        "content": chunk.page_content,
                        "source": filename,
                        "page": chunk.metadata.get("page", 0)
                    })
            except Exception as e:
                print(f"Lỗi khi đọc file {filename}: {e}")

    # 4. Lưu kết quả ra file .jsonl (mỗi dòng là một đối tượng JSON)
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        for item in all_chunks:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"\n✅ Xong! Đã tạo ra {len(all_chunks)} đoạn dữ liệu.")
    print(f"Dữ liệu đã lưu tại: {output_file}")

if __name__ == "__main__":
    build_chunks()