import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv(".env")

class RoyalChatbot:
    def __init__(self):
        # Kết nối Neo4j
        self.driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI"), 
            auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
        )

    def search_graph(self, user_query):
        # Tìm kiếm các Entity liên quan trong Graph
        if not user_query or not user_query.strip():
            return []

        key = user_query.strip().split()[-1]
        with self.driver.session() as session:
            query = """
            MATCH (s:Entity)-[r]->(o:Entity)
            WHERE toLower(s.name) CONTAINS toLower($key) OR toLower(o.name) CONTAINS toLower($key)
            RETURN s.name AS subject, r.name AS predicate, o.name AS object
            LIMIT 10
            """
            result = session.run(query, key=key)
            return [f"{record['subject']} {record['predicate']} {record['object']}" for record in result]

    def ask(self, question):
        answers = self.search_graph(question)
        if not answers:
            return "Xin lỗi, tôi không có thông tin về câu hỏi này trong đồ thị tri thức NCTU."
        return "\n".join(answers)

if __name__ == "__main__":
    bot = RoyalChatbot()
    while True:
        user_input = input("Hỏi đi (gõ 'exit' để thoát): ")
        if user_input.lower() == 'exit': break
        print("Bot đang suy nghĩ...")
        print("Trả lời:", bot.ask(user_input))