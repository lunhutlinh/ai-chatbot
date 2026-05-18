import os
import re
import unicodedata
from typing import Any

from dotenv import load_dotenv
from neo4j import GraphDatabase


load_dotenv(".env")


class Neo4jService:
    def __init__(self) -> None:
        self.uri = os.getenv("NEO4J_URI", "").strip()
        self.username = os.getenv("NEO4J_USERNAME", "").strip()
        self.password = os.getenv("NEO4J_PASSWORD", "").strip()
        self.driver = None
        self.connected = False
        self.last_error = ""

        if not (self.uri and self.username and self.password):
            self.last_error = "Thiếu cấu hình NEO4J_URI/NEO4J_USERNAME/NEO4J_PASSWORD trong .env"
            return

        try:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password),
            )
            self.driver.verify_connectivity()
            self.connected = True
        except Exception as exc:
            self.last_error = str(exc)
            self.connected = False

    @staticmethod
    def _repair_mojibake(text: str) -> str:
        if not isinstance(text, str):
            return str(text)

        value = text
        for _ in range(2):
            try:
                repaired = value.encode("latin1").decode("utf-8")
            except Exception:
                break
            if repaired == value:
                break
            value = repaired

        value = unicodedata.normalize("NFC", value)
        return re.sub(r"\s+", " ", value).strip()

    @classmethod
    def normalize_display_text(cls, text: str) -> str:
        value = cls._repair_mojibake(text)
        return value.replace("_", " ")

    @staticmethod
    def _strip_accents(text: str) -> str:
        value = unicodedata.normalize("NFD", text)
        value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
        value = value.replace("đ", "d").replace("Đ", "D")
        return value

    @classmethod
    def _extract_keywords(cls, user_query: str) -> list[dict[str, str]]:
        tokens = re.findall(r"\w+", (user_query or "").lower())
        stopwords = {
            "la",
            "gi",
            "va",
            "cho",
            "toi",
            "minh",
            "ban",
            "cua",
            "co",
            "khong",
            "nhu",
            "nao",
            "bao",
            "nhieu",
            "thong",
            "tin",
            "ve",
        }

        keyword_items: list[dict[str, str]] = []
        for raw in tokens:
            if len(raw) <= 1:
                continue
            norm = cls._strip_accents(raw)
            if norm in stopwords:
                continue
            keyword_items.append({"raw": raw, "norm": norm})

        # "hoc" is extremely generic and tends to match most triples; drop it when there are other keywords.
        if len(keyword_items) >= 2:
            keyword_items = [k for k in keyword_items if k.get("norm") != "hoc"]

        # Unique by (raw,norm) while preserving order.
        seen: set[tuple[str, str]] = set()
        unique: list[dict[str, str]] = []
        for item in keyword_items:
            key = (item.get("raw", ""), item.get("norm", ""))
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)

        return unique[:6]

    def search_triples(self, user_query: str, limit: int = 8) -> list[dict[str, str]]:
        if not self.connected or self.driver is None:
            return []

        keywords = self._extract_keywords(user_query)
        if not keywords:
            return []

        min_matches = 1
        if len(keywords) >= 3:
            min_matches = 2

        query = """
        MATCH (s:Entity)-[r:RELATION]->(o:Entity)
        WITH s, r, o,
            [k IN $keywords WHERE
                toLower(s.name) CONTAINS k.raw OR
                toLower(o.name) CONTAINS k.raw OR
                toLower(coalesce(r.name, r.type, "")) CONTAINS k.raw OR
                toLower(coalesce(r.name, r.type, "")) CONTAINS k.norm
            ] AS matched
        WHERE size(matched) >= $min_matches
        RETURN
            s.name AS subject,
            coalesce(r.name, r.type, "lien_quan") AS predicate,
            o.name AS object,
            size(matched) AS match_count
        ORDER BY match_count DESC
        LIMIT $limit
        """

        with self.driver.session() as session:
            records = session.run(query, keywords=keywords, min_matches=min_matches, limit=limit)
            rows: list[dict[str, str]] = []
            for record in records:
                rows.append(
                    {
                        "subject": self.normalize_display_text(record["subject"]),
                        "predicate": self.normalize_display_text(record["predicate"]),
                        "object": self.normalize_display_text(record["object"]),
                    }
                )
            return rows

    def fetch_subject_triples(self, subject: str, limit: int = 12) -> list[dict[str, str]]:
        """Fetch outgoing triples for a specific subject entity.

        This is used when the user clearly mentions a major name/alias; it avoids
        noisy keyword matching across many entities.
        """
        if not self.connected or self.driver is None:
            return []

        subj = (subject or "").strip()
        if not subj:
            return []

        query = """
        MATCH (s:Entity)-[r:RELATION]->(o:Entity)
        WHERE toLower(s.name) = toLower($subject)
        RETURN
            s.name AS subject,
            coalesce(r.name, r.type, "lien_quan") AS predicate,
            o.name AS object
        LIMIT $limit
        """

        with self.driver.session() as session:
            records = session.run(query, subject=subj, limit=limit)
            rows: list[dict[str, str]] = []
            for record in records:
                rows.append(
                    {
                        "subject": self.normalize_display_text(record["subject"]),
                        "predicate": self.normalize_display_text(record["predicate"]),
                        "object": self.normalize_display_text(record["object"]),
                    }
                )
            return rows

    def format_triples(self, triples: list[dict[str, str]]) -> str:
        if not triples:
            return ""

        def pretty_predicate(pred: str) -> str:
            p = (pred or "").strip().lower().replace("_", " ")
            mapping = {
                "co diem thpt": "điểm THPT",
                "co diem hoc ba": "điểm học bạ",
                "co hoc phi": "học phí (VND/tín chỉ)",
                "thuoc nhom": "thuộc nhóm",
            }
            return mapping.get(p, p)

        lines = [
            f"- {t['subject']} - {pretty_predicate(t['predicate'])} - {t['object']}"
            for t in triples
        ]
        return "\n".join(lines)

    def get_stats(self) -> dict[str, Any]:
        if not self.connected or self.driver is None:
            return {
                "connected": False,
                "nodes": 0,
                "relationships": 0,
                "error": self.last_error,
            }

        with self.driver.session() as session:
            nodes = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]

        return {
            "connected": True,
            "nodes": int(nodes),
            "relationships": int(rels),
            "error": "",
        }

    def normalize_graph_text(self, apply_changes: bool = False, limit: int = 5000) -> dict[str, Any]:
        if not self.connected or self.driver is None:
            return {
                "connected": False,
                "updated_entities": 0,
                "updated_relations": 0,
                "samples": [],
                "error": self.last_error,
            }

        samples: list[dict[str, str]] = []
        updated_entities = 0
        updated_relations = 0

        with self.driver.session() as session:
            entity_rows = session.run(
                """
                MATCH (e:Entity)
                WHERE e.name IS NOT NULL
                RETURN id(e) AS id, e.name AS name
                LIMIT $limit
                """,
                limit=limit,
            )

            for row in entity_rows:
                old_name = row["name"]
                new_name = self.normalize_display_text(old_name)
                if new_name != old_name:
                    updated_entities += 1
                    if len(samples) < 10:
                        samples.append({"type": "Entity", "old": old_name, "new": new_name})
                    if apply_changes:
                        session.run(
                            "MATCH (e:Entity) WHERE id(e) = $id SET e.name = $name",
                            id=row["id"],
                            name=new_name,
                        )

            relation_rows = session.run(
                """
                MATCH ()-[r:RELATION]->()
                RETURN id(r) AS id, coalesce(r.name, r.type, "") AS name
                LIMIT $limit
                """,
                limit=limit,
            )

            for row in relation_rows:
                old_name = row["name"]
                new_name = self.normalize_display_text(old_name)
                if new_name != old_name:
                    updated_relations += 1
                    if len(samples) < 10:
                        samples.append({"type": "RELATION", "old": old_name, "new": new_name})
                    if apply_changes:
                        session.run(
                            "MATCH ()-[r:RELATION]->() WHERE id(r) = $id SET r.name = $name",
                            id=row["id"],
                            name=new_name,
                        )

        return {
            "connected": True,
            "updated_entities": updated_entities,
            "updated_relations": updated_relations,
            "samples": samples,
            "applied": apply_changes,
            "error": "",
        }
