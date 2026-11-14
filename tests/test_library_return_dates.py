"""Check how a scheduled due date and a planned return date affect evidence."""

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from swpurag.answer import AnswerError, answer_question
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
            if sample["id"] in {"library-chengdu-2026-summer-schedule", "library-chengdu-reader-guide",
                                "library-chengdu-loan-rights"}:
                result = import_capture(cls.store, sample, by_url[sample["url"]], root / "data")
                if result["status"] != "new":
                    raise AssertionError(result)

    def search(self, question):
        return search_library(self.store, question, 5, today="2026-11-13")

    def test_overlap_subquestion_does_not_hide_supported_renewal(self):
        returned = ("我从成都二期图书馆借的书原本2026年7月11日到期，打算9月6日归还。"
                    "按那份暑期通知，这本书算不算超期？")
        question = returned + "另外，我是研究生，图书最多可以续借几次？"
        quote = "可续借2次，每次续借期30天"

        def model(text, evidence, _prompt, _subquestions, scope):
            self.assertEqual(text, "另外，我是研究生，图书最多可以续借几次？")
            self.assertNotIn("loan_dates", scope)
            self.assertEqual(scope["reader_group"], "graduate")
            self.assertEqual(len(evidence), 1)
            self.assertEqual(evidence[0]["library_scope"]["loan_aspect"], "renewal_rule")
            return "fixture", {"status": "answered", "follow_up": "", "claims": [{
                "text": "研究生可续借2次。", "citations": [{"id": evidence[0]["id"], "quote": quote}],
            }]}

        with patch("swpurag.answer.request_model", side_effect=model) as request:
            result = answer_question(self.store, question, "scoped")
        request.assert_called_once()
        self.assertEqual(result["status"], "insufficient")
        self.assertEqual([part["status"] for part in result["parts"]], ["insufficient", "answered"])
        self.assertEqual(result["parts"][0]["question"], returned)
        self.assertEqual(result["parts"][0]["claims"], result["claims"][:2])
        self.assertEqual(len(result["claims"]), 3)
        locations = {row["id"]: row["locator"]["library_scope"]["loan_aspect"] for row in result["evidence"]}
        self.assertEqual([locations[claim["citations"][0]["id"]] for claim in result["claims"]],
                         ["holiday_return", "holiday_return", "renewal_rule"])
        self.assertIn("向图书馆核对", result["follow_up"])

        with patch("swpurag.answer.request_model", side_effect=AnswerError("模型连接失败")):
            failed = answer_question(self.store, question, "scoped")
        self.assertEqual(failed["status"], "unavailable")
        self.assertEqual(failed["claims"], result["parts"][0]["claims"])
        self.assertEqual(failed["parts"][1]["status"], "unavailable")

        with patch("swpurag.answer.request_model") as request:
            unclear = answer_question(self.store, returned + "另外，图书最多可以续借几次？", "scoped")
        request.assert_not_called()
        self.assertEqual(unclear["claims"], result["parts"][0]["claims"])
        self.assertEqual(unclear["parts"][1]["status"], "clarify")
        self.assertIn("读者属于哪一类", unclear["parts"][1]["follow_up"])

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

    def test_overlapping_cutoff_retains_both_original_sentences(self):
        prefix = "成都分馆的书原本2026年7月11日到期，"
        for question in (
            prefix + "打算9月6日归还，按暑期通知算不算超期？",
            prefix + "按暑期通知会不会超期？",
        ):
            with self.subTest(question=question):
                hits, scope = self.search(question)
                self.assertEqual([hit["locator"]["paragraph"] for hit in hits], [12])
                self.assertFalse(scope["clarification"])
                self.assertIsNone(scope["loan_dates"]["within_extension"])
                policy = scope["return_policy"]
                self.assertEqual(policy["kind"], "overlap")
                self.assertEqual(policy["chunk_id"], hits[0]["chunk_id"])
                waived, carryover = policy["quotes"]
                self.assertIn("（均含当日）", waived)
                self.assertIn("7月11日（含当日）之前已经到期的未归还图书", carryover)
                self.assertEqual(waived + carryover, hits[0]["text"])

    def test_earlier_due_date_with_explicit_unreturned_status_uses_carryover(self):
        hits, scope = self.search(
            "成都总馆有本书原定2026年7月10日到期，7月11日仍没还，打算9月6日还。按暑期公告，之前的超期天数会不会扣掉？"
        )
        self.assertEqual([hit["locator"]["paragraph"] for hit in hits], [12])
        self.assertFalse(scope["clarification"])
        self.assertEqual(scope["loan_dates"]["unreturned_on"], "2026-07-11")
        self.assertIsNone(scope["loan_dates"]["within_extension"])
        self.assertEqual(scope["return_policy"]["kind"], "carryover")
        self.assertIn("不会给予扣除", scope["return_policy"]["quotes"][0])

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
