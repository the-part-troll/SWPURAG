"""Checks for the archived 2027 part-time directory and row citations."""

import importlib.util
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from swpurag.__main__ import print_matches
from swpurag.evaluate import ArchiveCheck, compact
from swpurag.ingest import import_capture
from swpurag.store import Store


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_ID = "masters-part-time-directory-2027"


@unittest.skipUnless(importlib.util.find_spec("pdfplumber"), "PDF tests require pdfplumber")
class PdfDirectoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest = json.loads((ROOT / "samples/pages.json").read_text(encoding="utf-8"))
        receipts = json.loads((ROOT / "samples/captures.json").read_text(encoding="utf-8"))
        cls.sample = next(item for item in manifest if item["id"] == SAMPLE_ID)
        cls.receipt = next(item for item in receipts if item["url"] == cls.sample["url"])
        cls.data_dir = ROOT / "data"
        cls.store = Store(":memory:")
        cls.addClassCleanup(cls.store.db.close)
        result = import_capture(cls.store, cls.sample, cls.receipt, cls.data_dir)
        if result["status"] != "new":
            raise AssertionError(result)
        cls.rows = list(cls.store.current_chunks())

    def find(self, page, *terms):
        rows = [
            row for row in self.rows
            if row["locator"]["page"] == page
            and all(compact(term) in compact(row["text"]) for term in terms)
        ]
        self.assertEqual(len(rows), 1, terms)
        return rows[0]

    def test_repeated_code_and_direction_subjects_stay_with_the_right_row(self):
        storage = self.find(1, "085706", "油气储运工程", "801工程流体力学")
        well = self.find(1, "085706", "油气井工程", "802油层物理")
        management = self.find(4, "085706", "石油与天然气工程管理", "839管理学原理")
        self.assertNotEqual(storage["locator"]["row"], well["locator"]["row"])
        self.assertNotIn("802油层物理", compact(storage["text"]))
        self.assertNotIn("801工程流体力学", compact(management["text"]))
        self.assertIn("非全日制", management["audience"])

    def test_merged_subject_cells_and_citation_can_be_rechecked(self):
        row = self.find(3, "125601", "不区分研究方向", "199管理类综合能力", "204英语二")
        archive = ArchiveCheck(self.data_dir)
        self.assertTrue(archive.verify(row))
        self.assertFalse(archive.verify(dict(row, locator=dict(row["locator"], page=2))))
        output = io.StringIO()
        with redirect_stdout(output):
            print_matches([row], "125601")
        self.assertIn("#page=3", output.getvalue())
        self.assertIn("PDF 第 3 页 · 表格第", output.getvalue())

    def test_bad_capture_does_not_replace_pdf_version(self):
        before = self.store.stats()
        duplicate = import_capture(self.store, self.sample, self.receipt, self.data_dir)
        self.assertEqual(duplicate["status"], "unchanged")
        invalid = dict(self.receipt, raw_path="raw/invalid.pdf", fetched_at="2026-11-12T23:00:00+08:00")
        failed = import_capture(self.store, self.sample, invalid, self.data_dir)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(self.store.stats()["versions"], before["versions"])
        self.assertEqual(list(self.store.current_chunks()), self.rows)
