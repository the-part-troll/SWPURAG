"""Check archived school calendar boundaries and separation from library evidence."""

from pathlib import Path
import unittest
from unittest.mock import patch

from swpurag.answer import answer_question, prepare_retrieval
from swpurag.evaluate import read_json
from swpurag.ingest import import_capture
from swpurag.store import Store
from swpurag.topics import topic_questions


ROOT = Path(__file__).resolve().parents[1]


class SchoolCalendarTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.db.close)
        for folder in ("school-calendar", "library-discovery"):
            directory = ROOT / "samples" / folder
            receipts = {row["url"]: row for row in read_json(directory / "captures.json")}
            sample = read_json(directory / "pages.json")[0]
            imported = import_capture(self.store, sample, receipts[sample["url"]], ROOT / "data")
            self.assertEqual(imported["status"], "new")

    def test_same_day_is_shared_and_explicit_dates_are_preserved(self):
        for library_text, library_day in (
            ("成都一期图书馆开门吗？", "2026-10-04"),
            ("2026 年 10 月 2 日成都一期图书馆开门吗？", "2026-10-02"),
        ):
            with self.subTest(library_text=library_text):
                question = "2026 年 10 月 4 日学校还放假吗？" + library_text
                evidence, _, scopes = prepare_retrieval(self.store, question)
                self.assertEqual(scopes["school_calendar"]["date"], "2026-10-04")
                self.assertEqual(scopes["library"]["date"], library_day)
                self.assertEqual([(row["evidence_topic"], row["locator"]["paragraph"]) for row in evidence],
                                 [("school_calendar", 4), ("library", 2)])
        questions = topic_questions("2026年国庆哪两天调休上课，另外10月4日成都一期图书馆开门吗？")
        self.assertNotIn("10月4日", questions["school_calendar"])

    def test_class_schedule_gap_retains_cited_school_arrangement(self):
        reply = {"status": "answered", "follow_up": "", "claims": [{
            "text": "10月10日学校正常上课。",
            "citations": [{"id": 1, "quote": "10月10日（星期六）正常上班上课。"}],
        }]}
        with patch("swpurag.answer.request_model", return_value=("mock", reply)):
            result = answer_question(self.store, "2026年10月10日学校要上课吗？是补星期几的课？", "scoped")
        self.assertEqual(result["status"], "insufficient")
        self.assertIn("补哪天", result["follow_up"])
        self.assertEqual(result["claims"], reply["claims"])

    def test_uncovered_holiday_never_receives_school_or_library_claims(self):
        with patch("swpurag.answer.request_model") as model:
            result = answer_question(self.store, "学校2026年元旦放哪几天假？", "scoped")
        model.assert_not_called()
        self.assertEqual(result["status"], "insufficient")
        self.assertEqual(result["evidence"], [])
