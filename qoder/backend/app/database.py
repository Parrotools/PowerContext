"""Database schema initialization for SeekDB."""

import aiomysql
from app.config import settings


SCHEMA_SQL = """
CREATE DATABASE IF NOT EXISTS `{db}`;

USE `{db}`;

CREATE TABLE IF NOT EXISTS documents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    content LONGTEXT NOT NULL,
    course VARCHAR(200) DEFAULT '',
    tags JSON,
    source_type VARCHAR(50) DEFAULT 'markdown',
    chunk_count INT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chunks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    document_id INT NOT NULL,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1024),
    course VARCHAR(200) DEFAULT '',
    tags JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FULLTEXT INDEX ft_content (content),
    VECTOR INDEX vec_embedding (embedding) WITH (distance=cosine),
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);
"""


async def init_database():
    conn = await aiomysql.connect(
        host=settings.SEEKDB_HOST,
        port=settings.SEEKDB_PORT,
        user=settings.SEEKDB_USER,
        password=settings.SEEKDB_PASSWORD,
    )
    try:
        async with conn.cursor() as cur:
            for statement in SCHEMA_SQL.split(";"):
                statement = statement.strip()
                if statement:
                    await cur.execute(statement)
        await conn.commit()
    finally:
        conn.close()
