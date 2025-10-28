"""
Inspired by ChainCache class.
CuratorCache should clear whenever you add a new cosmo export.
"""

from pydantic import BaseModel
import sqlite3
from collections import defaultdict
from pathlib import Path

dir_path = Path(__file__).parent.resolve()
db_path = dir_path / ".curator_cache.db"


# Define a dataclass to store the cached response
class CachedResponse(BaseModel):
    """
    Course_title and similarity score.
    """

    course_title: str
    similarity: float


# Define a dataclass to store the cached query
class CachedQuery(BaseModel):
    """
    Simple dataclass to store the cached request.
    """

    query: str
    responses: list[CachedResponse]


class CuratorCache:
    """
    Class to handle the caching of queries.
    """

    def __init__(
        self,
        db_path: str | Path = db_path,
    ):
        self.db_path = db_path
        self.conn, self.cursor = self.load_db()
        self.cached_requests = self.retrieve_cached_queries()
        self.cache_dict = self.generate_in_memory_dict(self.cached_requests)

    def load_db(self) -> tuple[sqlite3.Connection, sqlite3.Cursor]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS cached_queries (query TEXT, course_title TEXT, similarity REAL)"
        )
        return conn, cursor

    def insert_cached_query(self, cached_query: CachedQuery):
        """
        Insert a row for each response.
        """
        for response in cached_query.responses:
            self.cursor.execute(
                "INSERT INTO cached_queries (query, course_title, similarity) VALUES (?, ?, ?)",
                (
                    cached_query.query,
                    response.course_title,
                    response.similarity,
                ),
            )
        self.conn.commit()
        self.cache_dict[cached_query.query] = cached_query.responses

    def retrieve_cached_queries(self) -> list[CachedQuery]:
        """
        Retrieve all cached queries from the database and return them as a list of CachedQuery objects.
        """
        self.cursor.execute("SELECT * FROM cached_queries")
        data = self.cursor.fetchall()
        query_dict = defaultdict(list)
        for row in data:
            query, course_title, similarity = row
            query_dict[query].append(
                CachedResponse(course_title=course_title, similarity=similarity)
            )
        cached_queries = [
            CachedQuery(query=query, responses=responses)
            for query, responses in query_dict.items()
        ]
        return cached_queries

    def generate_in_memory_dict(self, cachedqueries: list[CachedQuery]) -> dict:
        return {cq.query: cq.responses for cq in cachedqueries}

    def cache_lookup(self, user_input: str) -> list[CachedResponse] | None:
        """
        Checks if there is a match for the CacheEntry, returns if yes, returns None if no.
        """
        # Regularize this, like we do with CachedRequest class
        user_input = str(user_input).strip()
        try:
            value = self.cache_dict[user_input]
        except:
            value = None
        return value

    def clear_cache(self, verbose=False):
        self.cursor.execute("DROP TABLE IF EXISTS cached_queries")
        self.conn.commit()
        self.cache_dict = {}
        if verbose:
            print("Cache cleared.")

    def __bool__(self):
        """
        We want this to return True if the object is initialized.
        We wouldn't need this if we didn't also want a __len__ method.
        (If __len__ returns 0, bool() returns False for your average object).
        """
        return True

    def __len__(self):
        """
        Note: see the __bool__ method above for extra context.
        """
        return len(self.cache_dict)
