"""Check citation boundaries and fail-closed behavior without a model credential."""

import unittest
from unittest.mock import patch

from swpurag.answer import AnswerError, answer_question, validate_answer, validate_parts


class AnswerTest(unittest.TestCase):
    def test_only_quotes_from_this_request_are_accepted(self):
        evidence = [{"id": 1, "text": "收费标准\n24000 元"}]
        answer = {
            "status": "answered",
            "claims": [{
                "text": "收费为 24000 元。",
                "citations": [{"id": 1, "quote": "收费标准 24000 元"}],
            }],
            "follow_up": "",
        }
        self.assertEqual(validate_answer(answer, evidence), answer)
        # 允许折叠原文换行，同时分别验证无效编号和原文中不存在的引文。
        for citation in ({"id": 2, "quote": "收费标准"}, {"id": 1, "quote": "收费 20000 元"}):
            with self.subTest(citation=citation):
                answer["claims"][0]["citations"] = [citation]
                with self.assertRaises(AnswerError):
                    validate_answer(answer, evidence)

    def test_model_failure_keeps_evidence_without_presenting_an_answer(self):
        hit = {"chunk_id": 12, "version_id": 3, "ordinal": 2, "locator": {},
               "text": "只显示本次检索到的原文。"}
        with patch("swpurag.answer._retrieve_admissions", return_value=[hit]), \
                patch("swpurag.answer.request_model", side_effect=AnswerError("模型连接失败")):
            store = type("SampleStore", (), {"current_chunks": lambda self: [hit]})()
            result = answer_question(store, "怎样查看正文？")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["claims"], [])
        self.assertEqual(result["evidence"][0]["id"], 1)

    def test_gap_and_clarification_can_be_reported_without_citations(self):
        for status, follow_up in (
            ("insufficient", "材料未给出具体分数线。"),
            ("clarify", "请说明想报考该校，还是在该校参加考试？"),
        ):
            with self.subTest(status=status):
                answer = {"status": status, "claims": [], "follow_up": follow_up}
                self.assertEqual(validate_answer(answer, []), answer)

    def test_partial_subquestions_keep_supported_claims_and_the_explicit_gap(self):
        evidence = [{"id": 1, "text": "缴费名额已满，系统将自动关闭。"}]
        claims = [{"text": "系统自动关闭。", "citations": [{"id": 1, "quote": "系统将自动关闭"}]}]
        questions = ["名额满了怎么办？", "考点有多少考位？"]
        parts = [
            {"id": 1, "status": "answered", "claims": claims, "follow_up": ""},
            {"id": 2, "status": "insufficient", "claims": [], "follow_up": "缺少考位总量。"},
        ]
        answer = validate_parts({"parts": parts}, evidence, questions)
        self.assertEqual(answer["status"], "insufficient")
        self.assertEqual(answer["claims"], claims)
        self.assertEqual(answer["follow_up"], "缺少考位总量。")
        with self.assertRaises(AnswerError):
            validate_parts({"parts": parts[:1]}, evidence, questions)

    def test_mixed_question_uses_shared_budget_and_separate_citations(self):
        # 图书馆仅命中一条，用招生的额外候选验证两个主题共享五条证据额度。
        library = {"chunk_id": 1, "version_id": 1, "ordinal": 1, "locator": {}, "topic": "library"}
        admissions = [{"chunk_id": index, "version_id": 2, "ordinal": index, "locator": {},
                       "text": "招生证据"}
                      for index in range(2, 7)]
        captured = []

        def synthesize(question, evidence, *args, **kwargs):
            captured.append((question, evidence))
            return {"status": "answered", "claims": [], "follow_up": ""}

        store = type("SampleStore", (), {"current_chunks": lambda self: [library] + admissions})()
        with patch("swpurag.answer.search_library", return_value=([library], {})), \
                patch("swpurag.answer._retrieve_admissions", return_value=admissions), \
                patch("swpurag.answer.synthesize", side_effect=synthesize):
            result = answer_question(store, "成都总馆什么时候关门？还有硕士初试考什么？")
        self.assertEqual(result["topics"], ["library", "admissions"])
        self.assertEqual(len(result["evidence"]), 5)
        self.assertEqual([[hit["evidence_topic"] for hit in evidence] for _, evidence in captured],
                         [["library"], ["admissions"] * 4])
