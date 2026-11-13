"""SQLite storage and paragraph retrieval for the curated corpus."""

import json
import re
import sqlite3
import unicodedata
from datetime import date, datetime, timezone
from urllib.parse import urlsplit


LIBRARY_FIELDS = ("topic", "campus", "building", "notice_kind", "effective_from", "effective_to", "service")


SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    source_key TEXT NOT NULL UNIQUE,
    host TEXT NOT NULL,
    path_prefix TEXT NOT NULL,
    UNIQUE(host, path_prefix)
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    url TEXT NOT NULL UNIQUE,
    current_version_id INTEGER REFERENCES versions(id),
    latest_success_fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS versions (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    title TEXT NOT NULL,
    unit TEXT NOT NULL,
    page_type TEXT NOT NULL,
    published_at TEXT,
    updated_at TEXT,
    admission_year INTEGER,
    role TEXT,
    audience TEXT,
    topic TEXT,
    campus TEXT,
    building TEXT,
    notice_kind TEXT,
    effective_from TEXT,
    effective_to TEXT,
    service TEXT,
    content_sha256 TEXT NOT NULL,
    raw_sha256 TEXT NOT NULL,
    raw_path TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    final_url TEXT NOT NULL,
    UNIQUE(document_id, content_sha256)
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    version_id INTEGER NOT NULL REFERENCES versions(id),
    ordinal INTEGER NOT NULL,
    text TEXT NOT NULL,
    locator TEXT NOT NULL,
    UNIQUE(version_id, ordinal)
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    url TEXT NOT NULL,
    final_url TEXT,
    fetched_at TEXT NOT NULL,
    status TEXT NOT NULL,
    version_id INTEGER REFERENCES versions(id),
    raw_sha256 TEXT,
    raw_path TEXT,
    error TEXT,
    CHECK ((raw_sha256 IS NULL) = (raw_path IS NULL)),
    CHECK (
        (status = 'failed' AND version_id IS NULL AND error IS NOT NULL)
        OR
        (status IN ('new', 'updated', 'unchanged', 'reverted')
         AND version_id IS NOT NULL AND raw_path IS NOT NULL AND error IS NULL)
    )
);
"""


def library_metadata(sample):
    metadata = {}
    for field in LIBRARY_FIELDS:
        value = sample.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(field + " must be a string")
        value = value.strip()
        if value:
            metadata[field] = value

    for field, choices in (
        ("notice_kind", {"regular", "temporary", "policy"}),
        ("service", {"hours", "loans"}),
    ):
        if field in metadata and metadata[field] not in choices:
            raise ValueError("{} must be one of {}".format(field, ", ".join(sorted(choices))))

    for field in ("effective_from", "effective_to"):
        if field not in metadata:
            continue
        try:
            day = date.fromisoformat(metadata[field])
        except ValueError:
            raise ValueError(field + " must be a valid YYYY-MM-DD date") from None
        if day.isoformat() != metadata[field]:
            raise ValueError(field + " must be a valid YYYY-MM-DD date")

    if "effective_from" in metadata and "effective_to" in metadata:
        if metadata["effective_from"] > metadata["effective_to"]:
            raise ValueError("effective_from cannot be after effective_to")
    return metadata


def _search_text(text):
    return unicodedata.normalize("NFKC", text).casefold()


def _capture_instant(value):
    if not isinstance(value, str):
        raise ValueError("Capture time must be an ISO timestamp with a UTC offset")
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    # Python 3.7 accepts three or six fractional digits in fromisoformat.
    value = re.sub(r"\.(\d{1,6})(?=[+-])", lambda match: "." + match[1].ljust(6, "0"), value)
    try:
        timestamp = datetime.fromisoformat(value)
        if timestamp.tzinfo is not None:
            return timestamp.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        raise ValueError("Capture time must be an ISO timestamp with a UTC offset") from None
    raise ValueError("Capture time must include a UTC offset")


class Store:
    def __init__(self, db_path):
        self.db = sqlite3.connect(str(db_path), timeout=10)
        self.db.row_factory = sqlite3.Row
        try:
            self.db.execute("PRAGMA foreign_keys = ON")
            self.db.executescript(SCHEMA)
            self._migrate()
        except Exception:
            self.db.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.db.close()

    def _migrate(self):
        # Keep the old version identifiers, hashes and paragraph citations.
        columns = {
            "documents": {"latest_success_fetched_at": "TEXT"},
            "versions": {
                "admission_year": "INTEGER", "role": "TEXT", "audience": "TEXT",
                **{field: "TEXT" for field in LIBRARY_FIELDS},
            },
        }
        if all(
            additions.keys() <= {row["name"] for row in self.db.execute("PRAGMA table_info(" + table + ")")}
            for table, additions in columns.items()
        ):
            return
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            needs_history = False
            for table, additions in columns.items():
                existing = {
                    row["name"] for row in self.db.execute("PRAGMA table_info(" + table + ")")
                }
                for name, kind in additions.items():
                    if name not in existing:
                        self.db.execute("ALTER TABLE {} ADD COLUMN {} {}".format(table, name, kind))
                        needs_history |= name == "latest_success_fetched_at"
            if needs_history:
                self._restore_current_versions()

    def _restore_current_versions(self):
        latest = {}
        rows = self.db.execute(
            """
            SELECT v.document_id, a.version_id, a.fetched_at
            FROM attempts AS a JOIN versions AS v ON v.id = a.version_id
            WHERE a.status != 'failed'
            ORDER BY a.id
            """
        )
        for row in rows:
            try:
                instant = _capture_instant(row["fetched_at"])
            except ValueError:
                # Legacy records without a usable absolute time cannot establish recency.
                continue
            document_id = row["document_id"]
            if document_id not in latest or instant >= latest[document_id][0]:
                latest[document_id] = (instant, row["version_id"], row["fetched_at"])
        self.db.executemany(
            "UPDATE documents SET current_version_id = ?, latest_success_fetched_at = ? WHERE id = ?",
            ((version, fetched_at, doc) for doc, (_, version, fetched_at) in latest.items()),
        )

    def _source_id(self, sample):
        host = sample["host"].lower()
        prefix = sample["path_prefix"]
        url = urlsplit(sample["url"])
        path = url.path or "/"
        in_scope = path == prefix or path.startswith(prefix.rstrip("/") + "/")
        if url.hostname != host or not prefix.startswith("/") or not in_scope:
            raise ValueError("URL is outside its declared source host/path scope")
        source = self.db.execute(
            "SELECT id, host, path_prefix FROM sources WHERE source_key = ?",
            (sample["source_key"],),
        ).fetchone()
        if source is None:
            return self.db.execute(
                "INSERT INTO sources (source_key, host, path_prefix) VALUES (?, ?, ?)",
                (sample["source_key"], host, prefix),
            ).lastrowid
        if (source["host"], source["path_prefix"]) != (host, prefix):
            raise ValueError("Source key is already registered to a different host/path")
        return source["id"]

    def _record_attempt(
        self, source_id, url, final_url, fetched_at, status, version_id=None,
        raw_sha256=None, raw_path=None, error=None,
    ):
        return self.db.execute(
            """
            INSERT INTO attempts (
                source_id, url, final_url, fetched_at, status, version_id,
                raw_sha256, raw_path, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (source_id, url, final_url, fetched_at, status, version_id,
             raw_sha256, raw_path, error),
        ).lastrowid

    def record_success(
        self, sample, *, title, content_sha256, raw_sha256, raw_path, fetched_at,
        final_url, chunks,
    ):
        if not chunks or any(not chunk["text"].strip() for chunk in chunks):
            raise ValueError("A successful version must have nonempty text chunks")
        instant = _capture_instant(fetched_at)
        metadata = library_metadata(sample)
        raw_path = str(raw_path)
        url = sample["url"]
        with self.db:
            # Lock before looking up the current version so simultaneous imports
            # cannot both decide to create the same document or version.
            self.db.execute("BEGIN IMMEDIATE")
            source_id = self._source_id(sample)
            document = self.db.execute(
                """
                SELECT id, source_id, current_version_id, latest_success_fetched_at
                FROM documents WHERE url = ?
                """,
                (url,),
            ).fetchone()
            if document is None:
                document_id = self.db.execute(
                    "INSERT INTO documents (source_id, url) VALUES (?, ?)",
                    (source_id, url),
                ).lastrowid
                current_version_id = None
                latest_fetched_at = None
            else:
                if document["source_id"] != source_id:
                    raise ValueError("Document URL is already registered to a different source")
                document_id = document["id"]
                current_version_id = document["current_version_id"]
                latest_fetched_at = document["latest_success_fetched_at"]
            is_latest = latest_fetched_at is None or instant >= _capture_instant(latest_fetched_at)

            version = self.db.execute(
                "SELECT id FROM versions WHERE document_id = ? AND content_sha256 = ?",
                (document_id, content_sha256),
            ).fetchone()
            if version is None:
                version_id = self.db.execute(
                    """
                    INSERT INTO versions (
                        document_id, title, unit, page_type, published_at, updated_at,
                        admission_year, role, audience, topic, campus, building, notice_kind,
                        effective_from, effective_to, service, content_sha256, raw_sha256,
                        raw_path, fetched_at, final_url
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (document_id, title, sample["unit"], sample["page_type"],
                     sample.get("published_at"), sample.get("updated_at"),
                     sample.get("admission_year"), sample.get("role"), sample.get("audience"),
                     *(metadata.get(field) for field in LIBRARY_FIELDS),
                     content_sha256, raw_sha256, raw_path, fetched_at, final_url),
                ).lastrowid
                self.db.executemany(
                    "INSERT INTO chunks (version_id, ordinal, text, locator) VALUES (?, ?, ?, ?)",
                    (
                        (version_id, ordinal, chunk["text"],
                         json.dumps(chunk["locator"], ensure_ascii=False))
                        for ordinal, chunk in enumerate(chunks, 1)
                    ),
                )
                status = "new" if current_version_id is None else "updated"
                chunk_count = len(chunks)
            else:
                version_id = version["id"]
                status = "unchanged" if current_version_id == version_id else "reverted"
                chunk_count = self.db.execute(
                    "SELECT COUNT(*) FROM chunks WHERE version_id = ?", (version_id,),
                ).fetchone()[0]

            if is_latest:
                self.db.execute(
                    """
                    UPDATE documents SET current_version_id = ?, latest_success_fetched_at = ?
                    WHERE id = ?
                    """,
                    (version_id, fetched_at, document_id),
                )
                current_version_id = version_id
                latest_fetched_at = fetched_at
            attempt_id = self._record_attempt(
                source_id, url, final_url, fetched_at, status,
                version_id, raw_sha256, raw_path,
            )
        return {
            "status": status,
            "url": url,
            "document_id": document_id,
            "version_id": version_id,
            "current_version_id": current_version_id,
            "is_current": version_id == current_version_id,
            "latest_success_fetched_at": latest_fetched_at,
            "attempt_id": attempt_id,
            "chunk_count": chunk_count,
        }

    def record_failure(
        self, sample, *, fetched_at, error, final_url=None, raw_sha256=None, raw_path=None,
    ):
        error = str(error)
        if raw_path is not None:
            raw_path = str(raw_path)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            source_id = self._source_id(sample)
            attempt_id = self._record_attempt(
                source_id, sample["url"], final_url, fetched_at, "failed",
                raw_sha256=raw_sha256, raw_path=raw_path, error=error,
            )
        return {
            "status": "failed",
            "url": sample["url"],
            "attempt_id": attempt_id,
            "error": error,
        }

    def current_chunks(self, *, topic=None):
        rows = self.db.execute(
            """
            SELECT d.url, v.*, c.id AS chunk_id, c.ordinal, c.text, c.locator,
                   s.source_key, s.host, s.path_prefix, d.latest_success_fetched_at
            FROM documents AS d
            JOIN sources AS s ON s.id = d.source_id
            JOIN versions AS v ON v.id = d.current_version_id
            JOIN chunks AS c ON c.version_id = v.id
            WHERE (? IS NULL OR v.topic = ?)
            """,
            (topic, topic),
        )
        for row in rows:
            result = dict(row)
            result["version_id"] = result.pop("id")
            result["locator"] = json.loads(result["locator"])
            yield result

    def search(self, query, limit=5, admission_year=None, *, topic=None):
        if limit < 1:
            raise ValueError("Search limit must be positive")
        terms = set(re.findall(r"[^\W_]+", _search_text(query)))
        if not terms:
            return []

        matches = []
        for row in self.current_chunks(topic=topic):
            if admission_year is not None and row["admission_year"] != admission_year:
                continue
            body = _search_text(row["text"])
            title = _search_text(row["title"])
            body_hits = {term for term in terms if term in body}
            title_hits = {term for term in terms if term in title}
            if body_hits and (body_hits | title_hits) == terms:
                rank = (-len(body_hits), -len(title_hits), row["url"], row["ordinal"])
                matches.append((rank, row))

        return [row for _, row in sorted(matches, key=lambda match: match[0])[:limit]]

    def stats(self):
        row = self.db.execute(
            """
            SELECT (SELECT COUNT(*) FROM sources) AS sources,
                   (SELECT COUNT(*) FROM documents) AS documents,
                   (SELECT COUNT(*) FROM versions) AS versions,
                   (SELECT COUNT(*) FROM chunks) AS chunks,
                   (SELECT COUNT(*) FROM attempts) AS attempts,
                   (SELECT COUNT(*) FROM attempts WHERE status = 'failed') AS failed_attempts
            """
        ).fetchone()
        return dict(row)
