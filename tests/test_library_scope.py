"""Verify date and building boundaries with the five archived library pages."""

import json
from pathlib import Path
import unittest

from swpurag.ingest import import_capture
from swpurag.library_scope import search_library
from swpurag.store import Store


ROOT = Path(__file__).resolve().parents[1]


class LibraryScopeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest = json.loads((ROOT / "samples/pages.json").read_text(encoding="utf-8-sig"))
        captures = json.loads((ROOT / "samples/captures.json").read_text(encoding="utf-8-sig"))
        by_url = {row["url"]: row for row in captures}
        cls.store = Store(":memory:")
        for sample in manifest:
            if sample.get("topic") == "library":
                result = import_capture(cls.store, sample, by_url[sample["url"]], ROOT / "data")
                if result["status"] != "new":
                    cls.store.db.close()
                    raise AssertionError(result)

    @classmethod
    def tearDownClass(cls):
        cls.store.db.close()

    def search(self, question):
        # 固定参考日，确保相对日期和省略年份的查询可以重复验证。
        return search_library(self.store, question, 5, today="2026-11-13")

    def test_temporary_end_date_is_inclusive(self):
        hits, scope = self.search("12月18日成都二期图书馆晚上几点关门？")
        self.assertEqual(scope["date_source"], "assumed_year")
        self.assertEqual(scope["date"], "2026-12-18")
        self.assertIn("22:30", hits[0]["text"])
        hits, scope = self.search("2026年12月19日成都分馆几点关门？")
        self.assertEqual(scope["notice_kind"], "regular")
        self.assertTrue(hits)
        self.assertTrue(all("22:30" not in hit["text"] for hit in hits))
        hits, scope = self.search("成都分馆2026年12月19日还按延长后的时间关门吗？")
        self.assertTrue(scope["no_applicable_extension"])
        self.assertTrue(all("22:30" not in hit["text"] for hit in hits))

    def test_summer_row_does_not_establish_branch_hours(self):
        # 暑假此段仅列总馆，分别验证查分馆、未指定馆舍和查总馆的结果。
        hits, scope = self.search("2026年8月1日成都分馆几点关门？")
        self.assertFalse(hits)
        self.assertTrue(scope["unsupported"])
        hits, scope = self.search("2026年8月1日成都校区图书馆几点关门？")
        self.assertFalse(hits)
        self.assertTrue(scope["clarification"])
        hits, scope = self.search("2026年8月1日成都一期图书馆几点关门？")
        self.assertEqual(scope["building"], "成都总馆")
        self.assertIn("9:00-21:00", hits[0]["text"])

    def test_loan_policy_and_method_use_two_distinct_evidence_rows(self):
        hits, scope = self.search("我是研究生，在成都图书馆借的书能续几次、每次多久，在哪里操作？")
        self.assertEqual(scope["reader_group"], "graduate")
        self.assertEqual(len(hits), 2)
        self.assertTrue(any("每次续借期30天" in hit["text"] for hit in hits))
        self.assertTrue(any("进行续借操作" in hit["text"] for hit in hits))
        self.assertFalse(any("可续借1次" in hit["text"] for hit in hits))

    def test_public_hours_never_substitute_for_realtime_or_other_campus(self):
        for question in ("成都总馆今晚还剩多少个自习座位？", "南充分馆平时几点开？"):
            with self.subTest(question=question):
                hits, scope = self.search(question)
                self.assertFalse(hits)
                self.assertTrue(scope["unsupported"])

    def test_relative_dates_and_regular_schedule(self):
        hits, scope = self.search("成都总馆明晚几点关门？")
        self.assertEqual(scope["date"], "2026-11-14")
        self.assertEqual(scope["date_source"], "relative")
        self.assertIn("22:30", hits[0]["text"])
        hits, scope = self.search("成都总馆平时几点开到几点，周日也能用自助借还机吗？")
        self.assertEqual(scope["date_source"], "regular")
        self.assertIn("所有开馆时间提供自动借还仪借还服务", hits[0]["text"])
