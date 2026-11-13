"""Checks for direction evidence and count scopes in the two archived catalogs."""

from collections import Counter
import importlib.util
import json
from pathlib import Path
import unittest

from swpurag.capture import read_archive
from swpurag.pdf import extract_pdf


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec("pdfplumber"), "PDF tests require pdfplumber")
class FullTimeCatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest = json.loads((ROOT / "samples/pages.json").read_text(encoding="utf-8"))
        receipts = json.loads((ROOT / "samples/captures.json").read_text(encoding="utf-8"))
        by_url = {receipt["url"]: receipt for receipt in receipts}
        cls.rows = {}
        for mode, sample_id in (
            ("全日制", "masters-full-time-directory-2027"),
            ("非全日制", "masters-part-time-directory-2027"),
        ):
            sample = next(item for item in manifest if item["id"] == sample_id)
            body = read_archive(ROOT / "data", by_url[sample["url"]], "pdf")
            _, chunks, _ = extract_pdf(body, sample)
            # 按原件页码和表格行号索引方向，便于核对两份目录的对应记录。
            cls.rows[mode] = {
                (chunk["locator"]["page"], chunk["locator"]["row"]): chunk
                for chunk in chunks if chunk["locator"]["row_type"] == "direction"
            }

    def test_same_program_and_direction_keep_catalog_counts_separate(self):
        full = self.rows["全日制"][1, 21]
        part = self.rows["非全日制"][1, 7]
        for expected_mode, row in (("全日制", full), ("非全日制", part)):
            locator = row["locator"]
            self.assertEqual(locator["study_mode"], expected_mode)
            self.assertEqual(locator["program_code"], "085706")
            self.assertEqual(locator["direction_code"], "03")
            self.assertIn("801工程流体力学", locator["cells"]["subjects"]["text"])
        self.assertIn("方向拟招全日制人数(含推免)：27", full["text"])
        self.assertIn("专业拟招全日制人数(含推免)：199", full["text"])
        self.assertIn("方向拟招推免人数：10", full["text"])
        self.assertIn("方向拟招生非全日制人数（不含单考）：4", part["text"])
        self.assertNotIn("direction_recommended_count", part["locator"]["cells"])

    def test_blank_and_merged_cells_retain_their_own_scopes(self):
        computing = self.rows["全日制"][6, 22]["locator"]
        self.assertEqual(computing["program_code"], "085404")
        cells = computing["cells"]
        # 科目单元格从专业行跨到方向行，专业人数仍保留在专业层级。
        self.assertEqual(cells["subjects"]["row"], 21)
        self.assertGreaterEqual(cells["subjects"]["bbox"][3], computing["bbox"][3])
        self.assertEqual(cells["program_count"]["text"], "45")
        self.assertEqual(cells["program_recommended_count"]["text"], "5")
        self.assertNotIn("direction_count", cells)
        law = self.rows["全日制"][10, 13]["locator"]["cells"]
        self.assertEqual(law["program_count"]["text"], "38")
        self.assertNotIn("program_recommended_count", law)

    def test_all_pages_and_lettered_program_codes_are_extracted(self):
        full_rows = self.rows["全日制"]
        counts = Counter(page for page, _ in full_rows)
        self.assertEqual([counts[page] for page in range(1, 12)],
                         [14, 12, 22, 24, 29, 17, 20, 30, 23, 17, 12])
        self.assertEqual(full_rows[1, 13]["locator"]["program_code"], "0820J2")
        self.assertEqual(full_rows[6, 9]["locator"]["program_code"], "0820J1")
