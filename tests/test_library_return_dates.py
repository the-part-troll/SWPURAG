"""Check how a scheduled due date and a planned return date affect evidence."""

import json
from pathlib import Path
import unittest

from swpurag.ingest import import_capture
from swpurag.library_scope import search_library
from swpurag.store import Store


class LibraryReturnDatesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / "samples/pages.json").read_text(encoding="utf-8-sig"))
        captures = json.loads((root / "samples/captures.json").read_text(encoding="utf-8-sig"))
        by_url = {row["url"]: row for row in captures}
        cls.store = Store(":memory:")
        cls.addClassCleanup(cls.store.db.close)
        for sample in manifest:
            if sample["id"] in {"library-chengdu-2026-summer-schedule", "library-chengdu-reader-guide"}:
                result = import_capture(cls.store, sample, by_url[sample["url"]], root / "data")
                if result["status"] != "new":
                    raise AssertionError(result)

    def search(self, question):
        return search_library(self.store, question, 5, today="2026-11-13")

    def test_deadline_is_inclusive_and_return_date_does_not_filter_evidence(self):
        cases = [
            ("成都二期图书馆2026年暑假原定8月24日到期的书，9月6日还算不算超期？",
             "2026-08-24", "2026-09-06", True),
            ("我准备2026年9月7日去成都总馆还书，那本书原本8月26日到期，按暑期延期会超期吗？",
             "2026-08-26", "2026-09-07", False),
            ("成都一期图书馆的书到期日是8月26日，计划还书日期是2026年9月6日晚上几点前还不算超期？",
             "2026-08-26", "2026-09-06", True),
        ]
        for question, due, planned, within in cases:
            with self.subTest(question=question):
                hits, scope = self.search(question)
                self.assertEqual([hit["locator"]["paragraph"] for hit in hits], [12])
                self.assertFalse(scope["clarification"])
                self.assertEqual(scope["services"], ["loans"])
                dates = scope["loan_dates"]
                self.assertEqual((dates["due_date"], dates["return_date"]), (due, planned))
                self.assertEqual(dates["extension_until"], "2026-09-06")
                self.assertIs(dates["within_extension"], within)

    def test_planned_date_cannot_make_an_out_of_scope_due_date_eligible(self):
        hits, scope = self.search("成都总馆的书原本2026年7月10日到期，打算9月6日还，算暑期延期吗？")
        self.assertFalse(hits)
        self.assertIn("原到期日", scope["unsupported"][0])
        self.assertEqual(scope["loan_dates"]["return_date"], "2026-09-06")

    def test_conflicting_or_missing_roles_are_clarified(self):
        cases = [
            ("成都总馆的书可能是2026年7月10日到期，也可能是7月12日到期，打算9月6日还，算暑期延期吗？", "原到期日"),
            ("成都总馆这本书打算2026年9月6日还，暑期延长期内还算超期吗？", "原到期"),
            ("成都总馆这本书原本2026年8月26日到期，会不会超期？", "计划在"),
            ("成都总馆的书原本12月30日到期，打算1月3日还，按寒假延期会超期吗？", "年份"),
        ]
        for question, clarification in cases:
            with self.subTest(question=question):
                hits, scope = self.search(question)
                self.assertFalse(hits)
                self.assertIn(clarification, scope["clarification"])

    def test_general_holiday_policy_does_not_require_a_specific_loan(self):
        hits, scope = self.search("成都图书馆寒暑假期间到期的图书通常能延期归还吗？")
        self.assertEqual([hit["locator"]["paragraph"] for hit in hits], [21])
        self.assertFalse(scope["clarification"])
