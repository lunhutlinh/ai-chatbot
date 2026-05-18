import os
import json
from neo4j import GraphDatabase
from dotenv import load_dotenv

# Load cấu hình Neo4j từ file .env ở thư mục chatbot
load_dotenv(".env")

class Neo4jIngestor:
    def __init__(self):
        uri = os.getenv("NEO4J_URI")
        user = os.getenv("NEO4J_USERNAME", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")

        if not uri or not password:
            raise ValueError("Thiếu biến môi trường NEO4J_URI hoặc NEO4J_PASSWORD trong .env")

        self.driver = GraphDatabase.driver(str(uri), auth=(str(user), str(password)))

    def close(self):
        self.driver.close()

    def ingest_data(self):
        file_path = "data/processed/chunks/chunks.jsonl"

        with self.driver.session() as session:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    chunk = json.loads(line)
                    # MERGE Chunk theo id để tránh tạo trùng khi chạy lại
                    query = """
                    MERGE (d:Document {name: $source})
                    MERGE (c:Chunk {id: $chunk_id})
                    SET c.content = $content, c.page = $page
                    MERGE (c)-[:PART_OF]->(d)
                    """
                    session.run(
                        query,
                        chunk_id=chunk["id"],
                        content=chunk["content"],
                        source=chunk["metadata"]["source"],
                        page=chunk["metadata"].get("page", 0),
                    )
        print("✅ Đã đẩy toàn bộ dữ liệu vào Neo4j thành công!")

    def count_graph(self):
        with self.driver.session() as session:
            node_count = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            rel_count = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        print(f"📊 Tổng node: {node_count}, tổng relationship: {rel_count}")

if __name__ == "__main__":
    ingestor = Neo4jIngestor()
    try:
        ingestor.ingest_data()
        ingestor.count_graph()
    finally:
        ingestor.close()