import os
import json
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv(".env")

class KnowledgeIngestor:
    def __init__(self):
        uri = os.getenv("NEO4J_URI")
        user = os.getenv("NEO4J_USERNAME")
        password = os.getenv("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def ingest_triples(self):
        # Đường dẫn tới file graph_data.json có 226 dòng của Phi
        file_path = "data/processed/graph/graph_data.json"
        
        with self.driver.session() as session:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    # Câu lệnh Cypher để nối Subject -> Predicate -> Object
                    query = """
                    MERGE (s:Entity {name: $subject})
                    MERGE (o:Entity {name: $object})
                    WITH s, o
                    CALL apoc.create.relationship(s, $predicate, {}, o) YIELD rel
                    RETURN rel
                    """
                    # Nếu máy chưa cài plugin APOC, ta dùng cách thủ công hơn bên dưới:
                    query_manual = f"""
                    MERGE (s:Entity {{name: $subject}})
                    MERGE (o:Entity {{name: $object}})
                    MERGE (s)-[r:RELATION {{type: $predicate}}]->(o)
                    SET r.name = $predicate
                    """
                    session.run(query_manual, 
                                subject=item["subject"], 
                                predicate=item["predicate"], 
                                object=item["object"])
        
        print(f"✅ Đã nạp thành công các quan hệ từ graph_data.json!")

if __name__ == "__main__":
    ingestor = KnowledgeIngestor()
    ingestor.ingest_triples()
    ingestor.close()