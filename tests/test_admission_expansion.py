"""Regression checks for paragraph scope and personal review answers."""

from pathlib import Path
import unittest
from unittest.mock import patch

from swpurag.answer import answer_question, prepare_retrieval
from swpurag.evaluate import read_json
from swpurag.ingest import import_capture
from swpurag.store import Store


class AdmissionExpansionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.store = Store(":memory:")
        cls.addClassCleanup(cls.store.db.close)
        for directory in (root / "samples", root / "samples/discovery"):
            receipts = {row["url"]: row for row in read_json(directory / "captures.json")}
            for sample in read_json(directory / "pages.json"):
                if sample.get("admission_year") == 2027 and sample.get("format", "html") == "html":
                    result = import_capture(cls.store, sample, receipts[sample["url"]], root / "data")
                    if result["status"] != "new":
                        raise AssertionError(result)

    def test_fresh_and_older_site_rules_can_coexist(self):
        question = "我应届本科，同事已经毕业在上班，我们都参加统考，报考点能都按户籍选吗？"
        evidence, _, _ = prepare_retrieval(self.store, question)
        positions = {(row["url"].rsplit("/", 1)[-1], row["locator"]["paragraph"])
                     for row in evidence if row["rank"] is not None}
        self.assertTrue({("8650.htm", 24), ("8710.htm", 41)} <= positions)

    def test_personal_gap_does_not_remove_the_public_deadline(self):
        question = "我的四川研考网报显示待补充，我还缺哪份材料、多久能通过？另外考生补材料最晚几点？"
        calls = []

        def model(query, evidence, prompt, *_):
            calls.append(query)
            row, = evidence
            if "公开状态" in query:
                quote = "显示“待补充材料”表明考生报名阶段材料缺失，考生需按报考点要求提供新的补充材料。"
                answer = "待补充材料表示报名阶段材料缺失，应按报考点要求补交。"
            else:
                quote = "如需提交补充材料，请按照报考点的要求于10月31日12:00前完成材料提交。"
                answer = "考生须于10月31日12:00前完成材料提交。"
            return "test-model", {"status": "answered", "follow_up": "", "claims": [
                {"text": answer, "citations": [{"id": row["id"], "quote": quote}]}
            ]}

        with patch("swpurag.answer.request_model", side_effect=model):
            result = answer_question(self.store, question, "scoped")
        self.assertEqual(result["status"], "insufficient")
        self.assertEqual([part["status"] for part in result["parts"]], ["insufficient", "answered"])
        self.assertIn("研招网本人报名页面的审核意见", result["follow_up"])
        self.assertEqual(len(calls), 2)
        self.assertTrue(all("我还缺" not in query for query in calls))
