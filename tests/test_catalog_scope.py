"""Scope behavior for competing catalog records."""

import unittest
from unittest.mock import patch

from swpurag.answer import answer_question
from swpurag.catalog_scope import directory_scope, search_scoped


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
