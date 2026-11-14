"""Scope behavior for competing catalog records."""

from pathlib import Path
import unittest
from unittest.mock import patch

from swpurag.answer import answer_question
from swpurag.catalog_scope import directory_scope, search_scoped
from swpurag.evaluate import read_json
from swpurag.ingest import import_capture
from swpurag.retrieval import explicit_subquestions
from swpurag.store import Store


def catalog_row(number, mode, college, subject):
    direction = "01({})不区分研究方向".format(mode)
    cells = {
        "college": {"text": college},
        "program": {"text": "085400电子信息"},
        "direction": {"text": direction},
        "subjects": {"text": subject},
    }
    return {
        "chunk_id": number, "version_id": number, "document_id": number, "ordinal": 1,
        "admission_year": 2027, "role": "admission_directory", "unit": "研究生院",
        "url": "https://example.test/catalog-{}.pdf".format(number),
        "title": mode + "招生目录", "text": college + "085400电子信息" + direction + subject,
        "locator": {"kind": "pdf", "row_type": "direction", "study_mode": mode,
                    "program_code": "085400", "cells": cells, "page": 1, "row": 4},
    }


class CatalogScopeTest(unittest.TestCase):
    def setUp(self):
        # 四条记录共用专业代码，各学院和学习方式组合用不同科目区分。
        self.rows = [
            catalog_row(1, "全日制", "001甲学院", "801计算基础"),
            catalog_row(2, "非全日制", "001甲学院", "802通信基础"),
            catalog_row(3, "全日制", "002乙学院", "803控制基础"),
            catalog_row(4, "非全日制", "002乙学院", "804电子基础"),
        ]

    def current_chunks(self):
        return iter(self.rows)

    def test_explicit_non_full_time_excludes_full_time_and_other_college(self):
        hits, scope = search_scoped(self, "甲学院非全日制085400初试考什么？", 5, 2027)
        self.assertEqual([directory_scope(row) for row in hits], [("非全日制", "甲学院")])
        self.assertNotIn("clarification", scope)

    def test_comparison_keeps_the_two_paired_scopes(self):
        hits, scope = search_scoped(self, "甲学院全日制085400和乙学院非全日制085400，科目一样吗？", 5, 2027)
        self.assertTrue(scope["compare_modes"])
        self.assertEqual([directory_scope(row) for row in hits], [
            ("全日制", "甲学院"), ("非全日制", "乙学院"),
        ])

    def test_unknown_scope_asks_before_synthesis(self):
        with patch("swpurag.answer.synthesize") as synthesize:
            result = answer_question(self, "085400第四门科目是什么？", "scoped")
        synthesize.assert_not_called()
        self.assertEqual(result["status"], "clarify")
        self.assertIn("学习方式", result["follow_up"])
        self.assertIn("报考学院", result["follow_up"])
        self.assertEqual(result["claims"], [])


class ExamSiteScopeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.store = Store(":memory:")
        cls.addClassCleanup(cls.store.db.close)
        samples = read_json(root / "samples/pages.json")
        cls.questions = {row["id"]: row["question"] for row in read_json(root / "samples/boundary-acceptance.json")}
        receipts = {row["url"]: row for row in read_json(root / "samples/captures.json")}
        for sample in samples:
            if sample["id"] in {"masters-admissions-charter-2027", "masters-admissions-unit-10615-2027",
                                "masters-exam-site-5110-2027"}:
                result = import_capture(cls.store, sample, receipts[sample["url"]], root / "data")
                if result["status"] != "new":
                    raise AssertionError(result)
        cls.rows = {row["chunk_id"]: row for row in cls.store.current_chunks()}

    def search(self, question):
        trace = []
        hits, _ = search_scoped(self.store, question, 5, 2027, trace=trace)
        candidates = [self.rows[key] for batch in trace for key in batch["candidate_ids"]]
        return hits, candidates

    def test_external_applicant_excludes_unit_rules_before_ranking(self):
        hits, candidates = self.search("我报外校，不报10615，只想在西油本部5110考，初试超过三小时可以吗？")
        self.assertTrue(candidates)
        self.assertTrue(all(row["role"] == "exam_site" for row in candidates))
        self.assertIn(27, [row["locator"]["paragraph"] for row in hits])

    def test_own_unit_and_exam_site_materials_keep_both_sources_in_top_five(self):
        hits, candidates = self.search(self.questions["B02"])
        locators = {(row["url"].rsplit("/", 1)[-1], row["locator"]["paragraph"]) for row in hits}
        self.assertIn(("8660.htm", 22), locators)
        self.assertTrue(locators & {("8650.htm", 13), ("8650.htm", 25)})
        self.assertIn("admission_unit", {row["role"] for row in candidates})

    def test_refund_scenarios_keep_their_own_clauses_and_evidence(self):
        cancel = "我在5110已交费，想撤掉报名，最晚几点前操作还能退报名费？"
        absent = "网上确认以后缺考，还能退考试费吗？"
        for question, expected, excluded in (
            (cancel, {43}, {44}),
            ("西油本部5110，" + absent, {44}, {43}),
            (cancel + absent, {43, 44}, set()),
        ):
            with self.subTest(question=question):
                hits, candidates = self.search(question)
                offsets = lambda rows: {row["locator"]["paragraph"] for row in rows if row["role"] == "exam_site"}
                self.assertTrue(expected <= offsets(hits))
                self.assertFalse(excluded & offsets(candidates))
        sections = explicit_subquestions(cancel + absent)
        self.assertEqual(len(sections), 2)
        self.assertIn("缺考", sections[1])
