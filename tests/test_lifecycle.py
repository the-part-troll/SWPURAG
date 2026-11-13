"""Offline import and citation checks using the three archived public pages."""

import re
import tempfile
import unittest
from html import unescape
from json import loads
from pathlib import Path

from swpurag.capture import archive
from swpurag.ingest import import_capture
from swpurag.store import Store


ROOT = Path(__file__).resolve().parents[1]
OVERVIEW = "overview"
ORIGINAL_TEXT = "新中国创建的第二所石油本科院校"
CHANGED_TEXT = "合成测试版本专用段落"
PUBLIC_SAMPLE_IDS = (OVERVIEW, "anniversary-notice", "faculty-profile")


class ImportLifecycleTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix=".test-lifecycle-", dir=str(ROOT))
        self.addCleanup(temporary.cleanup)
        self.data_dir = Path(temporary.name)
        self.store = Store(self.data_dir / "test.sqlite3")
        self.addCleanup(self.store.db.close)

        manifest = loads((ROOT / "samples/pages.json").read_text(encoding="utf-8"))
        receipts = loads((ROOT / "samples/captures.json").read_text(encoding="utf-8"))
        self.samples = {sample["id"]: sample for sample in manifest if sample["id"] in PUBLIC_SAMPLE_IDS}
        urls = {sample["url"] for sample in self.samples.values()}
        self.receipts = {receipt["url"]: receipt for receipt in receipts if receipt["url"] in urls}
        # 将真实原件复制到临时归档，后续测试可在副本上制造更新或损坏。
        for receipt in self.receipts.values():
            original = (ROOT / "data" / receipt["raw_path"]).read_bytes()
            stored = archive(self.data_dir, original)
            self.assertEqual(stored["raw_sha256"], receipt["raw_sha256"])
            self.assertEqual(stored["raw_path"], receipt["raw_path"])

    def receipt(self, sample_id):
        return self.receipts[self.samples[sample_id]["url"]]

    def ingest(self, sample_id, receipt=None):
        if receipt is None:
            receipt = self.receipt(sample_id)
        return import_capture(self.store, self.samples[sample_id], receipt, self.data_dir)

    def overview_bytes(self):
        return (self.data_dir / self.receipt(OVERVIEW)["raw_path"]).read_bytes()

    def snapshot(self, body, timestamp):
        receipt = dict(self.receipt(OVERVIEW), fetched_at=timestamp)
        receipt.update(archive(self.data_dir, body))
        return receipt

    def test_public_pages_have_checkable_citations(self):
        for sample_id in self.samples:
            self.assertEqual(self.ingest(sample_id)["status"], "new")
        self.assertEqual(self.store.stats()["documents"], 3)

        examples = (
            (OVERVIEW, ORIGINAL_TEXT, "学校概况", "updated_at", "2026-10-20"),
            ("anniversary-notice", "西南石油大学档案馆", "全面征集校史实物史料",
             "published_at", "2026-06-16"),
            ("faculty-profile", "海洋工程流动安全与控制", "高岳", "updated_at", None),
        )
        for sample_id, query, title, date_field, date in examples:
            with self.subTest(sample=sample_id):
                results = self.store.search(query)
                self.assertTrue(results)
                hit = results[0]
                sample = self.samples[sample_id]
                self.assertEqual(hit["url"], sample["url"])
                self.assertEqual(hit["unit"], sample["unit"])
                self.assertEqual(hit["fetched_at"], self.receipt(sample_id)["fetched_at"])
                self.assertIn(title, hit["title"])
                self.assertEqual(hit[date_field], date)
                self.assertIn(query, hit["text"])
                locator = hit["locator"]
                self.assertEqual(locator["kind"], "html")
                self.assertGreaterEqual(locator["paragraph"], 1)
                self.assertTrue(locator["selector"])
                # 按行列回到原始 HTML，直接验证定位落在含引文的段落。
                original = (self.data_dir / hit["raw_path"]).read_text(encoding="utf-8")
                lines = original.splitlines(keepends=True)
                line_index = locator["line"] - 1
                start = lines[line_index][locator["column"] - 1:] + "".join(lines[line_index + 1:])
                self.assertRegex(start, r"(?i)^<p(?:\s|>)")
                paragraph = re.split(r"</p\s*>", start, maxsplit=1, flags=re.I)[0]
                self.assertIn(query, unescape(re.sub(r"<[^>]*>", "", paragraph)))

        self.assertEqual(self.store.search("火星分校招生简章"), [])
        biography = self.store.search("高岳 纽卡斯尔大学")
        self.assertTrue(biography)
        self.assertEqual(biography[0]["url"], self.samples["faculty-profile"]["url"])

    def test_duplicate_content_and_update_keep_version_history(self):
        first = self.ingest(OVERVIEW)
        self.assertEqual(first["status"], "new")
        baseline = self.store.stats()
        exact_repeat = self.ingest(OVERVIEW)
        self.assertEqual(exact_repeat["status"], "unchanged")
        self.assertEqual(exact_repeat["version_id"], first["version_id"])

        raw = self.overview_bytes()
        # 仅追加 HTML 注释，原件哈希会变化，正文版本应复用。
        template_only = self.snapshot(
            raw + b"\n<!-- Synthetic fixture: template-only change -->\n",
            "2026-11-12T15:00:00+08:00",
        )
        equivalent = self.ingest(OVERVIEW, template_only)
        self.assertEqual(equivalent["status"], "unchanged")
        self.assertEqual(equivalent["version_id"], first["version_id"])
        after_repeat = self.store.stats()
        for key in ("sources", "documents", "versions", "chunks"):
            self.assertEqual(after_repeat[key], baseline[key])
        self.assertEqual(after_repeat["attempts"], baseline["attempts"] + 2)
        attempt = self.store.db.execute(
            "SELECT raw_sha256, raw_path FROM attempts WHERE id = ?",
            (equivalent["attempt_id"],),
        ).fetchone()
        self.assertEqual(attempt["raw_sha256"], template_only["raw_sha256"])
        self.assertEqual(attempt["raw_path"], template_only["raw_path"])

        self.assertIn(ORIGINAL_TEXT.encode("utf-8"), raw)
        updated_raw = raw.replace(ORIGINAL_TEXT.encode("utf-8"), CHANGED_TEXT.encode("utf-8"), 1)
        receipt = self.snapshot(updated_raw, "2026-11-12T15:01:00+08:00")
        updated = self.ingest(OVERVIEW, receipt)
        self.assertEqual(updated["status"], "updated")
        self.assertNotEqual(updated["version_id"], first["version_id"])
        self.assertEqual(self.store.stats()["documents"], 1)
        self.assertEqual(self.store.stats()["versions"], 2)
        self.assertEqual(self.store.search(ORIGINAL_TEXT), [])
        hit = self.store.search(CHANGED_TEXT)[0]
        self.assertEqual(hit["version_id"], updated["version_id"])
        self.assertEqual(hit["raw_path"], receipt["raw_path"])
        previous = self.store.db.execute(
            """
            SELECT c.text, v.raw_path FROM versions AS v
            JOIN chunks AS c ON c.version_id = v.id
            WHERE v.id = ? AND instr(c.text, ?) > 0
            """,
            (first["version_id"], ORIGINAL_TEXT),
        ).fetchone()
        self.assertIn(ORIGINAL_TEXT, previous["text"])
        self.assertEqual((self.data_dir / previous["raw_path"]).read_bytes(), raw)

        replayed = self.ingest(OVERVIEW)
        self.assertFalse(replayed["is_current"])
        self.assertEqual(replayed["current_version_id"], updated["version_id"])
        self.assertEqual(self.store.search(CHANGED_TEXT)[0]["version_id"], updated["version_id"])

        # UTC 时间晚于前一次成功抓取，重现的旧正文应重新成为当前版本。
        recent_original = dict(self.receipt(OVERVIEW), fetched_at="2026-11-12T07:02:00Z")
        restored = self.ingest(OVERVIEW, recent_original)
        self.assertEqual(restored["status"], "reverted")
        self.assertTrue(restored["is_current"])
        self.assertEqual(restored["version_id"], first["version_id"])
        self.assertEqual(self.store.stats()["versions"], 2)
        self.assertEqual(self.store.search(ORIGINAL_TEXT)[0]["version_id"], first["version_id"])
        self.assertEqual(self.store.search(CHANGED_TEXT), [])

    def test_newer_duplicate_keeps_intermediate_history_inactive(self):
        first = self.ingest(OVERVIEW)
        duplicate = dict(self.receipt(OVERVIEW), fetched_at="2026-11-12T15:30:00+08:00")
        refreshed = self.ingest(OVERVIEW, duplicate)
        self.assertEqual(refreshed["status"], "unchanged")
        self.assertEqual(refreshed["version_id"], first["version_id"])
        self.assertEqual(refreshed["latest_success_fetched_at"], duplicate["fetched_at"])

        changed = self.overview_bytes().replace(
            ORIGINAL_TEXT.encode("utf-8"), CHANGED_TEXT.encode("utf-8"), 1
        )
        # 07:25 UTC 即北京时间 15:25，内容不同但早于上方 15:30 的成功抓取。
        intermediate = self.snapshot(changed, "2026-11-12T07:25:00Z")
        history = self.ingest(OVERVIEW, intermediate)
        self.assertFalse(history["is_current"])
        self.assertEqual(history["current_version_id"], first["version_id"])
        self.assertEqual(self.store.stats()["versions"], 2)
        self.assertEqual(self.store.search(CHANGED_TEXT), [])
        hit = self.store.search(ORIGINAL_TEXT)[0]
        self.assertEqual(hit["fetched_at"], self.receipt(OVERVIEW)["fetched_at"])
        self.assertEqual(hit["latest_success_fetched_at"], duplicate["fetched_at"])

    def test_200_responses_with_body_region_are_checked_before_versioning(self):
        self.assertEqual(self.ingest(OVERVIEW)["status"], "new")
        previous = self.store.search(ORIGINAL_TEXT)
        start = '<html><head><title>学校概况</title></head><body><div id="vsb_content">'
        end = "</div></body></html>"
        # 模拟带正常标题和正文容器的 HTTP 200 页面，检查异常内容能否被识别。
        fixtures = (
            (start + "<p>网站正在维护，请稍后访问。</p>" + end, "maintenance"),
            (start + "<h1>学校概况</h1><p>请先登录后查看正文。</p>" + end, "login"),
            (start + '<form><p>账号认证</p><input type="password"></form>' + end, "login form"),
            (start + "<p>正文加载失败，请刷新页面。</p>" + end, "incomplete"),
            (start + "<p>学校概况第一段文本……", "closing tag missing"),
        )
        for html, error in fixtures:
            with self.subTest(error=error):
                receipt = self.snapshot(html.encode("utf-8"), "2026-11-13T00:00:00+08:00")
                failed = self.ingest(OVERVIEW, receipt)
                self.assertEqual(failed["status"], "failed")
                self.assertIn(error, failed["error"])
                attempt = self.store.db.execute(
                    "SELECT version_id, raw_sha256 FROM attempts WHERE id = ?",
                    (failed["attempt_id"],),
                ).fetchone()
                self.assertIsNone(attempt["version_id"])
                self.assertEqual(attempt["raw_sha256"], receipt["raw_sha256"])
                self.assertEqual(self.store.search(ORIGINAL_TEXT), previous)

        # 正常通知也可能提到登录，借此检查正文不会被误识别为登录页。
        body = '<p id="apply">请先登录招生系统，按通知要求提交报名材料并确认提交结果。</p>'
        valid = self.snapshot((start + body + end).encode("utf-8"), "2026-11-12T17:00:00+08:00")
        sample = dict(
            self.samples[OVERVIEW], admission_year=2026, role="admission_unit", audience="报名考生",
            minimum_body_chars=10, required_body_anchors=["apply"],
        )
        for config, error in (
            (dict(sample, minimum_body_chars=1000), "shorter than"),
            (dict(sample, required_body_anchors=["absent"]), "missing configured anchors"),
        ):
            failed = import_capture(self.store, config, valid, self.data_dir)
            self.assertEqual(failed["status"], "failed")
            self.assertIn(error, failed["error"])
            self.assertEqual(self.store.search(ORIGINAL_TEXT), previous)

        updated = import_capture(self.store, sample, valid, self.data_dir)
        self.assertTrue(updated["is_current"])
        hit = self.store.search("报名材料", admission_year=2026)[0]
        self.assertEqual((hit["admission_year"], hit["role"], hit["audience"]),
                         (2026, "admission_unit", "报名考生"))
        self.assertEqual(hit["latest_success_fetched_at"], valid["fetched_at"])
        self.assertEqual(self.store.search("报名材料", admission_year=2027), [])
        self.assertEqual(self.store.stats()["versions"], 2)

    def test_failures_preserve_current_evidence(self):
        self.assertEqual(self.ingest(OVERVIEW)["status"], "new")
        baseline = self.store.stats()
        before = self.store.search(ORIGINAL_TEXT)
        url = self.samples[OVERVIEW]["url"]
        access_failure = {
            "url": url, "final_url": url, "http_status": 403,
            "fetched_at": "2026-11-12T15:02:00+08:00",
            "error": "HTTP 403 (synthetic test failure)",
        }
        invalid_html = self.snapshot(
            b"<html><title>Synthetic validation page</title><p>Verify access</p></html>",
            "2026-11-12T15:03:00+08:00",
        )
        damaged = self.snapshot(
            self.overview_bytes() + b"\n<!-- Synthetic fixture: archive integrity -->",
            "2026-11-12T15:04:00+08:00",
        )
        # 保持抓取记录不变，替换本地原件字节，单独触发哈希校验失败。
        (self.data_dir / damaged["raw_path"]).write_bytes(self.overview_bytes())
        for receipt in (access_failure, invalid_html, damaged):
            self.assertEqual(self.ingest(OVERVIEW, receipt)["status"], "failed")
            self.assertEqual(self.store.search(ORIGINAL_TEXT), before)
        after = self.store.stats()
        for key in ("sources", "documents", "versions", "chunks"):
            self.assertEqual(after[key], baseline[key])
        self.assertEqual(after["failed_attempts"], baseline["failed_attempts"] + 3)
        self.assertEqual(self.store.db.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
