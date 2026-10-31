"""SeekDB-compatible service using SQLite + sqlite-vec + FTS5 for local deployment.

This implementation provides the same hybrid search capabilities as SeekDB
(vector similarity + full-text matching + metadata filtering) using local SQLite.
For production, replace with SeekDB D0 cloud or self-hosted SeekDB.
"""

from __future__ import annotations

import json
import re
import sqlite3
import struct
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
import sqlite_vec
from app.config import settings

logger = logging.getLogger(__name__)


class SeekDBUnavailableError(RuntimeError):
    """Raised when database is not initialized."""


_db_path: Path | None = None
_available = False
_doc_counter = 0

# Embedding dimensions (using a simple hash-based approach for demo)
EMBEDDING_DIM = 384


def _get_embedding(text: str) -> list[float]:
    """Generate a hash-based embedding for demonstration.
    
    In production with SeekDB, use AI_EMBED() for server-side embedding.
    For local deployment, replace this with sentence-transformers or similar.
    """
    import hashlib
    h = hashlib.sha256(text.encode()).digest()
    vec = []
    for i in range(EMBEDDING_DIM):
        byte_idx = i % len(h)
        val = (h[byte_idx] + i * 7 + (h[(byte_idx + 1) % len(h)] << 3)) % 256
        vec.append((val / 128.0) - 1.0)
    # Normalize
    magnitude = sum(v * v for v in vec) ** 0.5
    if magnitude > 0:
        vec = [v / magnitude for v in vec]
    return vec


def _serialize_vector(vec: list[float]) -> bytes:
    """Serialize float list to bytes for sqlite-vec."""
    return struct.pack(f'{len(vec)}f', *vec)


def init_client():
    """Initialize SQLite database with vector and FTS support."""
    global _db_path, _available, _doc_counter
    
    db_dir = Path(settings.SEEKDB_DATABASE_PATH) if hasattr(settings, 'SEEKDB_DATABASE_PATH') else Path('.seekdb_data')
    db_dir.mkdir(parents=True, exist_ok=True)
    _db_path = db_dir / 'zhixu.db'
    
    conn = sqlite3.connect(str(_db_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    
    cursor = conn.cursor()
    
    # Create documents table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            course TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            source_type TEXT DEFAULT 'markdown',
            chunk_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create chunks table with vector column
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding BLOB NOT NULL,
            course TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
        )
    ''')
    
    # Create virtual table for full-text search
    cursor.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            content,
            title,
            course,
            tags,
            content='chunks',
            content_rowid='id'
        )
    ''')
    
    # Create vector index table
    cursor.execute(f'''
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
            id INTEGER PRIMARY KEY,
            embedding FLOAT[{EMBEDDING_DIM}]
        )
    ''')
    
    conn.commit()
    
    # Get current doc counter
    cursor.execute('SELECT MAX(id) FROM documents')
    result = cursor.fetchone()
    _doc_counter = result[0] if result[0] else 0
    
    conn.close()
    _available = True
    logger.info(f"SQLite + sqlite-vec initialized at {_db_path}, docs: {_doc_counter}")


def check_available():
    if not _available or _db_path is None:
        raise SeekDBUnavailableError("Database not initialized")


def close_client():
    global _available
    _available = False


def _get_conn() -> sqlite3.Connection:
    check_available()
    conn = sqlite3.connect(str(_db_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.row_factory = sqlite3.Row
    return conn


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks by paragraph/sentence boundaries."""
    paragraphs = re.split(r"\n\s*\n", text.strip())
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 1 <= chunk_size:
            current = f"{current}\n{para}".strip() if current else para
        else:
            if current:
                chunks.append(current)
                tail = current[-overlap:] if len(current) > overlap else ""
                current = f"{tail}\n{para}".strip() if tail else para
            else:
                sentences = re.split(r"(?<=[。！？.!?])\s+", para)
                for sent in sentences:
                    if len(current) + len(sent) + 1 <= chunk_size:
                        current = f"{current} {sent}".strip() if current else sent
                    else:
                        if current:
                            chunks.append(current)
                        current = sent
    if current:
        chunks.append(current)
    return chunks


async def insert_document(
    title: str,
    content: str,
    course: str = "",
    tags: list[str] | None = None,
    source_type: str = "markdown",
) -> int:
    """Insert a document and its chunks with auto-embedding."""
    check_available()
    global _doc_counter
    
    tags_json = json.dumps(tags or [], ensure_ascii=False)
    chunks = chunk_text(content, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
    
    def _do_insert():
        global _doc_counter
        conn = _get_conn()
        cursor = conn.cursor()
        
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "INSERT INTO documents (title, content, course, tags, source_type, chunk_count, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, content, course, tags_json, source_type, len(chunks), now),
        )
        _doc_counter = cursor.lastrowid
        doc_id = _doc_counter
        
        for i, chunk in enumerate(chunks):
            embedding = _get_embedding(chunk)
            emb_blob = _serialize_vector(embedding)
            
            cursor.execute(
                "INSERT INTO chunks (document_id, chunk_index, content, embedding, course, tags) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (doc_id, i, chunk, emb_blob, course, tags_json),
            )
            chunk_id = cursor.lastrowid
            
            # Insert into FTS
            cursor.execute(
                "INSERT INTO chunks_fts (rowid, content, title, course, tags) "
                "VALUES (?, ?, ?, ?, ?)",
                (chunk_id, chunk, title, course, tags_json),
            )
            
            # Insert into vector index
            cursor.execute(
                "INSERT INTO chunks_vec (id, embedding) VALUES (?, ?)",
                (chunk_id, emb_blob),
            )
        
        conn.commit()
        conn.close()
    
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _do_insert)
    return _doc_counter


async def list_documents() -> list[dict]:
    """List all documents."""
    check_available()
    
    def _do_list():
        conn = _get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, title, course, tags, source_type, chunk_count, created_at "
            "FROM documents ORDER BY created_at DESC"
        )
        rows = cursor.fetchall()
        conn.close()
        
        items = []
        for row in rows:
            tags_raw = row["tags"]
            try:
                tags = json.loads(tags_raw) if isinstance(tags_raw, str) else []
            except (json.JSONDecodeError, TypeError):
                tags = []
            items.append({
                "id": row["id"],
                "title": row["title"],
                "course": row["course"],
                "tags": tags,
                "source_type": row["source_type"],
                "chunk_count": row["chunk_count"],
                "created_at": row["created_at"],
            })
        return items
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do_list)


async def get_document(doc_id: int) -> dict | None:
    """Get a single document by ID."""
    check_available()
    
    def _do_get():
        conn = _get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, title, content, course, tags, source_type, chunk_count, created_at "
            "FROM documents WHERE id = ?",
            (doc_id,),
        )
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        tags_raw = row["tags"]
        try:
            tags = json.loads(tags_raw) if isinstance(tags_raw, str) else []
        except (json.JSONDecodeError, TypeError):
            tags = []
        
        return {
            "id": row["id"],
            "title": row["title"],
            "content": row["content"],
            "course": row["course"],
            "tags": tags,
            "source_type": row["source_type"],
            "chunk_count": row["chunk_count"],
            "created_at": row["created_at"],
        }
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do_get)


async def delete_document(doc_id: int) -> bool:
    """Delete a document and its chunks."""
    check_available()
    
    def _do_delete():
        conn = _get_conn()
        cursor = conn.cursor()
        
        # Get chunk IDs first
        cursor.execute("SELECT id FROM chunks WHERE document_id = ?", (doc_id,))
        chunk_ids = [row["id"] for row in cursor.fetchall()]
        
        # Delete from FTS and vector index
        for chunk_id in chunk_ids:
            cursor.execute("DELETE FROM chunks_fts WHERE rowid = ?", (chunk_id,))
            cursor.execute("DELETE FROM chunks_vec WHERE id = ?", (chunk_id,))
        
        # Delete chunks (cascading will handle chunks table)
        cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        return deleted
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do_delete)


async def hybrid_search(
    query: str,
    course: str | None = None,
    tags: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """
    Hybrid search: vector similarity + full-text matching + metadata filtering.
    Combines results from vector search and FTS, then ranks by combined score.
    """
    check_available()
    
    def _do_search():
        conn = _get_conn()
        cursor = conn.cursor()
        
        # Vector search
        query_embedding = _get_embedding(query)
        query_vec = _serialize_vector(query_embedding)
        
        vector_sql = f"""
            SELECT 
                c.id as chunk_id,
                c.document_id,
                c.content as snippet,
                c.course,
                c.tags,
                d.title,
                chunks_vec.distance
            FROM chunks_vec
            JOIN chunks c ON c.id = chunks_vec.id
            JOIN documents d ON d.id = c.document_id
            WHERE chunks_vec.embedding MATCH ?
            AND k = ?
            ORDER BY chunks_vec.distance
        """
        
        cursor.execute(vector_sql, (query_vec, limit * 2))
        vector_results = cursor.fetchall()
        
        # Full-text search - escape special FTS5 characters
        # FTS5 uses special syntax, so we need to sanitize the query
        safe_query = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff\s]', ' ', query).strip()
        if not safe_query:
            safe_query = query.replace('"', '""')
        fts_query = f'"{safe_query}"'
        
        fts_sql = """
            SELECT 
                c.id as chunk_id,
                c.document_id,
                c.content as snippet,
                c.course,
                c.tags,
                d.title,
                chunks_fts.rank as fts_rank
            FROM chunks_fts
            JOIN chunks c ON c.id = chunks_fts.rowid
            JOIN documents d ON d.id = c.document_id
            WHERE chunks_fts MATCH ?
            ORDER BY chunks_fts.rank
            LIMIT ?
        """
        
        try:
            cursor.execute(fts_sql, (fts_query, limit * 2))
            fts_results = cursor.fetchall()
        except Exception as e:
            logger.warning(f"FTS search failed: {e}, falling back to empty results")
            fts_results = []
        
        conn.close()
        
        # Combine and rank results
        scores: dict[int, dict] = {}
        
        # Vector scores (distance is 0-2 for cosine, lower is better)
        for row in vector_results:
            chunk_id = row["chunk_id"]
            vec_score = max(0.0, 1.0 - (row["distance"] or 2.0) / 2.0)
            
            tags_raw = row["tags"]
            try:
                tag_list = json.loads(tags_raw) if isinstance(tags_raw, str) else []
            except (json.JSONDecodeError, TypeError):
                tag_list = []
            
            # Apply filters
            if course and row["course"] != course:
                continue
            if tags:
                if not any(t in tag_list for t in tags):
                    continue
            
            scores[chunk_id] = {
                "chunk_id": chunk_id,
                "document_id": row["document_id"],
                "title": row["title"],
                "snippet": row["snippet"],
                "course": row["course"],
                "tags": tag_list,
                "vec_score": vec_score,
                "fts_score": 0.0,
            }
        
        # FTS scores (rank is negative, higher is better)
        max_fts_rank = 0.001  # Small default
        for row in fts_results:
            chunk_id = row["chunk_id"]
            fts_rank = abs(row["fts_rank"] or 0.001)
            max_fts_rank = max(max_fts_rank, fts_rank)
            
            if chunk_id in scores:
                scores[chunk_id]["fts_score"] = 1.0 / (1.0 + fts_rank)
            else:
                tags_raw = row["tags"]
                try:
                    tag_list = json.loads(tags_raw) if isinstance(tags_raw, str) else []
                except (json.JSONDecodeError, TypeError):
                    tag_list = []
                
                if course and row["course"] != course:
                    continue
                if tags:
                    if not any(t in tag_list for t in tags):
                        continue
                
                scores[chunk_id] = {
                    "chunk_id": chunk_id,
                    "document_id": row["document_id"],
                    "title": row["title"],
                    "snippet": row["snippet"],
                    "course": row["course"],
                    "tags": tag_list,
                    "vec_score": 0.0,
                    "fts_score": 1.0 / (1.0 + fts_rank),
                }
        
        # Combined score: 60% vector, 40% FTS
        results = []
        for chunk_id, data in scores.items():
            combined = data["vec_score"] * 0.6 + data["fts_score"] * 0.4
            data["score"] = round(combined, 4)
            results.append(data)
        
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do_search)
