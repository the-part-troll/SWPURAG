"""Verify library scope and version metadata against the archived public pages."""

import copy
import sqlite3
import tempfile
import unittest
from json import dumps, loads
from pathlib import Path

from swpurag.ingest import content_hash, extract_document, import_capture
from swpurag.store import LIBRARY_FIELDS, SCHEMA, Store


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
AUTUMN = "library-chengdu-2026-autumn-extension"
SUMMER = "library-chengdu-2026-summer-schedule"
HOURS = "library-chengdu-hours"
LOANS = "library-chengdu-loan-rights"


class LibraryMetadataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest = loads((ROOT / "samples/pages.json").read_text(encoding="utf-8"))
        receipts = loads((ROOT / "samples/captures.json").read_text(encoding="utf-8"))
        cls.samples = {sample["id"]: sample for sample in manifest}
        cls.receipts = {receipt["url"]: receipt for receipt in receipts}

    def ingest(self, store, sample):
        return import_capture(store, sample, self.receipts[sample["url"]], DATA)

    def test_real_library_scope_and_topic_filter(self):
        with Store(":memory:") as store:
            samples = [sample for sample in self.samples.values() if sample.get("topic") == "library"]
            self.assertEqual(len(samples), 5)
            self.assertEqual(self.ingest(store, self.samples["overview"])["status"], "new")
            for sample in samples:
                with self.subTest(sample=sample["id"]):
                    imported = self.ingest(store, sample)
                    self.assertEqual(imported["status"], "new", imported)
                    self.assertEqual(self.ingest(store, sample)["status"], "unchanged")
            self.assertEqual(store.stats()["versions"], 6)

            library = list(store.current_chunks(topic="library"))
            self.assertEqual({row["url"] for row in library}, {sample["url"] for sample in samples})
            self.assertEqual({row["topic"] for row in library}, {"library"})
            self.assertFalse(store.search("石油本科院校", topic="library"))
            self.assertTrue(store.search("石油本科院校"))

            hours = [row["locator"]["library_scope"] for row in library
                     if row["url"] == self.samples[HOURS]["url"]
                     and row["locator"].get("library_scope", {}).get("service") == "hours"]
            self.assertEqual({scope["building"] for scope in hours}, {"成都总馆", "成都分馆"})

            autumn = next(row for row in library if row["url"] == self.samples[AUTUMN]["url"]
                          and row["locator"].get("library_scope", {}).get("hours_aspect") == "evening_only")
            self.assertIn("22:30", autumn["text"])
            self.assertEqual((autumn["notice_kind"], autumn["effective_from"], autumn["effective_to"]),
                             ("temporary", "2026-10-19", "2026-12-18"))

            summer = [row["locator"]["library_scope"] for row in library
                      if row["url"] == self.samples[SUMMER]["url"]
                      and row["locator"].get("library_scope")]
            self.assertIn(("成都总馆", "2026-07-20", "2026-08-26"), {
                (scope["building"], scope["effective_from"], scope["effective_to"])
                for scope in summer if scope["service"] == "hours"
            })
            self.assertIn(("2026-07-11", "2026-09-06"), {
                (scope["effective_from"], scope["effective_to"])
                for scope in summer if scope["service"] == "loans"
            })

            loans = [row["locator"]["library_scope"] for row in library
                     if row["url"] == self.samples[LOANS]["url"]
                     and row["locator"].get("library_scope", {}).get("reader_group")]
            self.assertEqual({scope["reader_group"] for scope in loans},
                             {"undergraduate", "graduate", "external"})

    def test_metadata_changes_version_and_invalid_dates_keep_current(self):
        sample = self.samples[AUTUMN]
        with Store(":memory:") as store:
            original = self.ingest(store, sample)
            self.assertEqual(original["status"], "new", original)
            # 重用同一份网页，分别变更通知有效期和正文块适用范围。
            updated = self.ingest(store, dict(sample, effective_to="2026-12-19"))
            self.assertEqual(updated["status"], "updated", updated)
            scoped = copy.deepcopy(dict(sample, effective_to="2026-12-19"))
            scoped["chunk_scopes"][0]["scope"]["hours_aspect"] = "synthetic-scope-change"
            scoped_result = self.ingest(store, scoped)
            self.assertEqual(scoped_result["status"], "updated", scoped_result)
            self.assertEqual(store.stats()["versions"], 3)
            hashes = store.db.execute(
                "SELECT raw_sha256, content_sha256, effective_to FROM versions ORDER BY id"
            ).fetchall()
            self.assertEqual(len({row["raw_sha256"] for row in hashes}), 1)
            self.assertEqual(len({row["content_sha256"] for row in hashes}), 3)
            self.assertEqual([row["effective_to"] for row in hashes],
                             ["2026-12-18", "2026-12-19", "2026-12-19"])
            for invalid in ("2026-02-30", "2026-10-18", "20261019"):
                with self.subTest(invalid=invalid):
                    failure = self.ingest(store, dict(sample, effective_to=invalid))
                    self.assertEqual(failure["status"], "failed")
                    self.assertIn("effective", failure["error"])
            self.assertEqual(store.stats()["versions"], 3)
            self.assertEqual({row["version_id"] for row in store.current_chunks(topic="library")},
                             {scoped_result["version_id"]})

    def test_legacy_migration_and_empty_fields_preserve_version(self):
        sample = self.samples["overview"]
        receipt = self.receipts[sample["url"]]
        raw = (DATA / receipt["raw_path"]).read_bytes()
        title, chunks, dates = extract_document(raw, receipt.get("charset"), sample)
        version_sample = dict(sample, **dates)
        # 此哈希来自新增图书馆字段之前的语料，用于验证旧版本标识保持稳定。
        digest = "76742f315a46cf6a0b1d4de663bf92e3c13718113ff69f16b1705f38f1fdd354"
        self.assertEqual(content_hash(version_sample, title, chunks), digest)
        self.assertEqual(content_hash(dict(version_sample, topic=None, building=" "), title, chunks), digest)

        with tempfile.TemporaryDirectory(prefix=".test-library-migration-", dir=str(ROOT)) as directory:
            path = Path(directory) / "old.sqlite3"
            # 去掉新增列，预置一份带原件和定位的历史记录，再由 Store 打开迁移。
            schema = SCHEMA
            for field in LIBRARY_FIELDS:
                schema = schema.replace("    " + field + " TEXT,\n", "")
            db = sqlite3.connect(str(path))
            try:
                db.executescript(schema)
                with db:
                    db.execute("INSERT INTO sources VALUES (1, ?, ?, ?)",
                               (sample["source_key"], sample["host"], sample["path_prefix"]))
                    db.execute("INSERT INTO documents VALUES (1, 1, ?, 1, ?)",
                               (sample["url"], receipt["fetched_at"]))
                    db.execute(
                        """
                        INSERT INTO versions (
                            id, document_id, title, unit, page_type, updated_at, content_sha256,
                            raw_sha256, raw_path, fetched_at, final_url
                        ) VALUES (1, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (title, sample["unit"], sample["page_type"], dates["updated_at"], digest,
                         receipt["raw_sha256"], receipt["raw_path"], receipt["fetched_at"], sample["url"]),
                    )
                    db.executemany(
                        "INSERT INTO chunks (version_id, ordinal, text, locator) VALUES (1, ?, ?, ?)",
                        ((ordinal, chunk["text"], dumps(chunk["locator"], ensure_ascii=False))
                         for ordinal, chunk in enumerate(chunks, 1)),
                    )
            finally:
                db.close()

            with Store(path) as store:
                replay = self.ingest(store, sample)
                self.assertEqual((replay["status"], replay["version_id"]), ("unchanged", 1))
                legacy = store.db.execute("SELECT * FROM versions WHERE id = 1").fetchone()
                self.assertEqual(legacy["content_sha256"], digest)
                self.assertTrue(all(legacy[field] is None for field in LIBRARY_FIELDS))
                hit = store.search("石油本科院校", limit=1)[0]
                self.assertEqual(hit["version_id"], 1)
                self.assertEqual(hit["raw_path"], receipt["raw_path"])
                self.assertEqual(hit["locator"], chunks[hit["ordinal"] - 1]["locator"])
                added = self.ingest(store, self.samples[AUTUMN])
                self.assertEqual(added["status"], "new", added)
                self.assertEqual(store.stats()["versions"], 2)
                self.assertEqual(store.db.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
