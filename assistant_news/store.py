"""SQLite schema and persistent identity keys."""
import sqlite3
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SCHEMA = """
CREATE TABLE IF NOT EXISTS cursors (
 source TEXT PRIMARY KEY, initial_start TEXT NOT NULL, success_end TEXT
);
CREATE TABLE IF NOT EXISTS articles (
 id INTEGER PRIMARY KEY, day TEXT NOT NULL, title TEXT NOT NULL, source TEXT NOT NULL,
 source_id TEXT NOT NULL, published_at TEXT, date_status TEXT NOT NULL,
 url TEXT NOT NULL, category TEXT NOT NULL, collected_at TEXT NOT NULL, summary TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS articles_day ON articles(day);
CREATE TABLE IF NOT EXISTS aliases (
 kind TEXT NOT NULL, scope TEXT NOT NULL, value TEXT NOT NULL,
 article INTEGER NOT NULL REFERENCES articles(id), PRIMARY KEY(kind, scope, value)
);
CREATE TABLE IF NOT EXISTS runs (
 id INTEGER PRIMARY KEY, day TEXT NOT NULL, payload TEXT NOT NULL, exported INTEGER NOT NULL DEFAULT 0
);
"""


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(SCHEMA)
    return db


def canonical_url(url):
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname or parts.username is not None:
        raise ValueError("原文链接须为不含账号的 HTTP(S) 地址")
    host = parts.hostname.lower()
    if ":" in host:
        host = "[" + host + "]"
    if parts.port and (parts.scheme.lower(), parts.port) not in (("http", 80), ("https", 443)):
        host += ":" + str(parts.port)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid", "mc_cid", "mc_eid"}]
    return urlunsplit((parts.scheme.lower(), host, parts.path or "/", urlencode(query), ""))


def remember(db, entry, source, category, day, observed):
    keys = [("url", "", canonical_url(entry["url"]))]
    if entry.get("uid"):
        keys.insert(0, ("id", source["id"], entry["uid"]))
    existing = None
    for key in keys:
        hit = db.execute("SELECT article FROM aliases WHERE kind=? AND scope=? AND value=?", key).fetchone()
        if hit:
            existing = hit[0]
            break
    article_id = existing
    if existing is None:
        article_id = db.execute(
            "INSERT INTO articles(day,title,source,source_id,published_at,date_status,url,category,collected_at,summary) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (day, entry["title"], source["name"], source["id"], entry["published_at"],
             entry["date_status"], entry["url"], category, observed, entry.get("summary") or "")).lastrowid
    else:
        # Same-day refresh keeps the original first-observed time. Other days are archived.
        db.execute("UPDATE articles SET title=?,url=?,summary=?,category=?,published_at=?,date_status=? "
                   "WHERE id=? AND day=? AND source_id=?",
                   (entry["title"], entry["url"], entry.get("summary") or "", category,
                    entry["published_at"], entry["date_status"], existing, day, source["id"]))
    db.executemany("INSERT OR IGNORE INTO aliases VALUES(?,?,?,?)", [key + (article_id,) for key in keys])
    return existing is None
