"""Verify the local HTTP interface with offline evidence and a model stub."""

import json
import tempfile
import unittest
from html import escape
from http.client import HTTPResponse
from importlib.util import find_spec
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

from swpurag.answer import AnswerError, normalize_quote
from swpurag.capture import archive
from swpurag.ingest import import_capture
from swpurag.server import Handler
from swpurag.store import Store


ROOT = Path(__file__).resolve().parents[1]
HTML_SAMPLE = "library-chengdu-hours"
PDF_SAMPLE = "masters-full-time-directory-2027"
HAS_PDF = find_spec("pdfplumber") is not None
LIBRARY_QUESTION = "成都总馆平时几点关门？"
MIXED_QUESTION = "计算机与软件学院全日制085404初试第四门是什么？另外，" + LIBRARY_QUESTION
QUOTES = {"admissions": "408计算机学科专业基础", "library": "8:00--22:00"}


class InMemorySocket:
    def __init__(self, incoming):
        self.incoming = BytesIO(incoming)
        self.outgoing = bytearray()

    def settimeout(self, timeout):
        pass

    def makefile(self, mode, *args):
        return self.incoming

    def sendall(self, data):
        self.outgoing.extend(data)


class LocalServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix=".test-server-", dir=ROOT)
        cls.addClassCleanup(temporary.cleanup)
        cls.data_dir = Path(temporary.name)
        db_path = cls.data_dir / "test.sqlite3"
        samples = json.loads((ROOT / "samples/pages.json").read_text(encoding="utf-8-sig"))
        captures = json.loads((ROOT / "samples/captures.json").read_text(encoding="utf-8-sig"))
        receipts = {receipt["url"]: receipt for receipt in captures}
        cls.originals = {}
        sample_ids = {HTML_SAMPLE, PDF_SAMPLE} if HAS_PDF else {HTML_SAMPLE}
        # 使用真实归档的副本和临时数据库，损坏测试不会接触项目数据。
        with Store(db_path) as store:
            for sample in (row for row in samples if row["id"] in sample_ids):
                receipt = receipts[sample["url"]]
                body = (ROOT / "data" / receipt["raw_path"]).read_bytes()
                archive(cls.data_dir, body, sample.get("format", "html"))
                result = import_capture(store, sample, receipt, cls.data_dir)
                if result["status"] != "new":
                    raise AssertionError(result)
                cls.originals[sample["id"]] = (receipt, body)
        cls.server = SimpleNamespace(db_path=db_path, data_dir=cls.data_dir, server_port=50000)

    def request(self, method, path, body=None, headers=None):
        headers = {"Host": f"127.0.0.1:{self.server.server_port}", **(headers or {})}
        if body is not None:
            headers.setdefault("Content-Length", str(len(body)))
        head = [f"{method} {path} HTTP/1.1", *(f"{key}: {value}" for key, value in headers.items())]
        request = ("\r\n".join(head) + "\r\n\r\n").encode("ascii") + (body or b"")
        # 直接交给真实 HTTP 请求处理器解析，避免测试环境的端口和网络限制。
        connection = InMemorySocket(request)
        Handler(connection, ("127.0.0.1", 0), self.server)
        with HTTPResponse(InMemorySocket(connection.outgoing), method=method) as response:
            response.begin()
            return response.status, dict(response.getheaders()), response.read()

    def ask(self, question):
        return self.request("POST", "/api/ask", json.dumps({"question": question}).encode("ascii"), {
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{self.server.server_port}",
        })

    def test_homepage_and_request_guards(self):
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b'src="/app.js"', body)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

        body = b'{"question":"test"}'
        json_headers = {"Content-Type": "application/json"}
        invalid = (
            (403, body, {**json_headers, "Host": "outside.example"}),
            (403, body, {**json_headers, "Origin": "https://outside.example"}),
            (415, body, {"Content-Type": "text/plain"}),
            (413, body, {**json_headers, "Content-Length": "99999"}),
            (400, b"{", json_headers),
            (400, b'{"question":"  "}', json_headers),
            (400, b'{"question":"\\ud800"}', json_headers),
        )
        with patch("swpurag.answer.request_model") as model:
            for expected, body, headers in invalid:
                with self.subTest(expected=expected, headers=headers, body=body):
                    status, _, response = self.request("POST", "/api/ask", body, headers)
                    self.assertEqual(status, expected)
                    self.assertTrue(json.loads(response)["error"])
            model.assert_not_called()

    @unittest.skipUnless(HAS_PDF, "Mixed PDF and HTML archive test requires pdfplumber")
    def test_mixed_answer_links_to_original_pdf_page_and_html_line(self):
        def model(question, evidence, *_):
            quote = QUOTES["admissions" if "085404" in question else "library"]
            match = next(row for row in evidence if quote in normalize_quote(row["text"]))
            return "offline-stub", {"status": "answered", "claims": [{
                "text": quote, "citations": [{"id": match["id"], "quote": quote}],
            }]}

        # 仅替代模型调用，主题拆分、检索、引用校验和 HTTP 输出均走实际路径。
        with patch("swpurag.answer.request_model", side_effect=model) as stub:
            status, headers, response = self.ask(MIXED_QUESTION)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(stub.call_count, 2)
        result = json.loads(response)
        self.assertEqual(result["status"], "answered")
        self.assertEqual(set(result["topic_answers"]), set(QUOTES))
        by_id = {row["id"]: row for row in result["evidence"]}
        for topic, sample_id in (("admissions", PDF_SAMPLE), ("library", HTML_SAMPLE)):
            with self.subTest(topic=topic):
                citation = result["topic_answers"][topic]["claims"][0]["citations"][0]
                evidence = by_id[citation["id"]]
                self.assertEqual(citation["quote"], QUOTES[topic])
                self.assertEqual(evidence["evidence_topic"], topic)
                receipt, original = self.originals[sample_id]
                self.assertEqual(evidence["url"], receipt["url"])
                archive_link = urlsplit(evidence["archive_url"])
                self.assertEqual(archive_link.path, "/archive/" + receipt["raw_path"].split("/", 1)[1])
                status, headers, body = self.request("GET", archive_link.path)
                self.assertEqual(status, 200)
                if topic == "admissions":
                    self.assertEqual(archive_link.fragment, "page=6")
                    self.assertEqual(headers["Content-Type"], "application/pdf")
                    self.assertEqual(body, original)
                else:
                    line = evidence["locator"]["line"]
                    self.assertEqual(archive_link.fragment, f"L{line}")
                    markup = body.decode("utf-8")
                    self.assertIn(f'id="L{line}"', markup)
                    source_line = escape(original.decode("utf-8").split("\n")[line - 1])
                    self.assertIn(f">{line}</a>{source_line}</span>", markup)
                    self.assertIn("&lt;script", markup)
                    self.assertNotIn("<script", markup)

    def test_model_failure_hides_details_and_keeps_evidence(self):
        detail = "供应商返回仅供测试的私密详情"
        with patch("swpurag.answer.request_model", side_effect=AnswerError(detail)):
            status, _, response = self.ask(MIXED_QUESTION if HAS_PDF else LIBRARY_QUESTION)
        self.assertEqual(status, 200)
        self.assertNotIn(detail, response.decode("utf-8"))
        result = json.loads(response)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["claims"], [])
        self.assertEqual(result["error"], "回答暂不可用，请检查本地模型配置后重试。")
        self.assertTrue(all(part["error"] == result["error"] for part in result.get("topic_answers", {}).values()))
        self.assertEqual({row["evidence_topic"] for row in result["evidence"] if row.get("archive_url")},
                         set(QUOTES) if HAS_PDF else {"library"})

    def test_archive_rejects_unregistered_tampered_and_out_of_route_files(self):
        unregistered = archive(self.data_dir, b"<html>Unregistered fixture</html>")
        self.assertEqual(self.request("GET", f'/archive/{unregistered["raw_sha256"]}.html')[0], 404)
        self.assertEqual(self.request("GET", "/archive/../samples/pages.json")[0], 404)
        receipt, original = self.originals[HTML_SAMPLE]
        path = self.data_dir / receipt["raw_path"]
        try:
            path.write_bytes(original + b"<!-- modified -->")
            self.assertEqual(self.request("GET", f'/archive/{receipt["raw_sha256"]}.html')[0], 404)
        finally:
            path.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
