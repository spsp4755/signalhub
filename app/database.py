import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS keyword (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    result TEXT NOT NULL,
    run_type TEXT NOT NULL,
    sources TEXT,
    tags TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_analysis_keyword ON analysis(keyword);
CREATE INDEX IF NOT EXISTS idx_analysis_created ON analysis(created_at DESC);

CREATE TABLE IF NOT EXISTS setting (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recipient (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recipient_keyword (
    recipient_id INTEGER NOT NULL,
    keyword_id INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (recipient_id, keyword_id),
    FOREIGN KEY (recipient_id) REFERENCES recipient(id) ON DELETE CASCADE,
    FOREIGN KEY (keyword_id) REFERENCES keyword(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_recipient_keyword_keyword
    ON recipient_keyword(keyword_id);
"""


def init_db() -> None:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
        conn.commit()
    _migrate_add_columns()
    seed_default_keywords()


def _migrate_add_columns() -> None:
    with connect() as conn:
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(analysis)").fetchall()}
        if "sources" not in existing:
            conn.execute("ALTER TABLE analysis ADD COLUMN sources TEXT")
        if "tags" not in existing:
            conn.execute("ALTER TABLE analysis ADD COLUMN tags TEXT")
        conn.commit()


def seed_default_keywords() -> None:
    if not settings.default_keywords:
        return
    with connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM keyword").fetchone()[0]
        if count > 0:
            return
        conn.executemany(
            "INSERT INTO keyword (name, enabled) VALUES (?, 1)",
            [(k,) for k in settings.default_keywords],
        )
        conn.commit()


@contextmanager
def connect():
    conn = sqlite3.connect(settings.db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
