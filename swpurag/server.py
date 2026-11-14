"""Serve the evidence interface on the loopback address."""

import json
import re
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .answer import answer_question
from .capture import raw_path_for, read_archive, validate_url
from .html import decode_html
from .store import Store


WEB_DIR = Path(__file__).resolve().parent / "web"
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
}
ARCHIVE_PATH = re.compile(r"/archive/([a-f0-9]{64})\.(html|pdf)")
PUBLIC_HOSTS = {"www.swpu.edu.cn", "lib.swpu.edu.cn"}
MAX_BODY = 16 * 1024
MODEL_UNAVAILABLE = "回答暂不可用，请检查本地模型配置后重试。"
POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)


def archive_url(evidence):
    locator = evidence.get("locator", {})
    kind = locator.get("kind")
    position_key, fragment = {"html": ("line", "L"), "pdf": ("page", "page=")}.get(kind, (None, None))
    if position_key is None or evidence.get("host") not in PUBLIC_HOSTS:
        return None
    try:
        path = raw_path_for(evidence.get("raw_sha256"), kind)
    except ValueError:
        return None
    if evidence.get("raw_path") != path:
        return None
    position = locator.get(position_key)
    suffix = "#{}{}".format(fragment, position) if type(position) is int and position > 0 else ""
    return "/archive/" + path.split("/", 1)[1] + suffix


def public_archive(store, digest, kind):
    path = raw_path_for(digest, kind)
    rows = store.db.execute(
        """
        SELECT v.raw_sha256, v.raw_path, v.final_url, d.url, s.host, s.path_prefix
        FROM versions AS v
        JOIN documents AS d ON d.id = v.document_id
        JOIN sources AS s ON s.id = d.source_id
        WHERE v.raw_sha256 = ? AND v.raw_path = ?
          AND EXISTS (SELECT 1 FROM chunks AS c WHERE c.version_id = v.id)
        """,
        (digest, path),
    )
    for row in rows:
        if row["host"] in PUBLIC_HOSTS and row["final_url"] == row["url"]:
            try:
                validate_url(row)
            except ValueError:
                continue
            return row
    return None


def html_archive(body):
    try:
        source = decode_html(body, None)
    except (LookupError, UnicodeError):
        source = body.decode("utf-8", errors="replace")
    # 官网原件以转义后的文本展示，保留行号且不执行原网页的脚本。
    lines = "".join(
        '<span class="line" id="L{0}"><a href="#L{0}" aria-label="第 {0} 行">{0}</a>{1}</span>'.format(
            number, escape(line),
        )
        for number, line in enumerate(source.split("\n"), 1)
    )
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>官网 HTML 原件</title><style>'
        'body{margin:1rem;color:#192337;background:#fff}'
        'pre{white-space:pre-wrap;overflow-wrap:anywhere}'
        '.line{display:block;min-height:1.3em;scroll-margin-top:1rem}'
        '.line:target{background:#fef3c7}'
        'a{display:inline-block;min-width:4em;padding-right:1em;text-align:right;color:#365681}'
        '</style></head><body><h1>官网 HTML 原件</h1><pre>' + lines + '</pre></body></html>'
    ).encode("utf-8")


def clean_answer(result):
    # 模型服务的错误详情可能含本机配置或供应商响应，只对浏览器展示固定提示。
    if "error" in result:
        result["error"] = MODEL_UNAVAILABLE
    for part in result.get("topic_answers", {}).values():
        clean_answer(part)
    for part in result.get("parts", ()):
        clean_answer(part)


class Handler(BaseHTTPRequestHandler):
    server_version = "SWPURAG"
    sys_version = ""

    def setup(self):
        self.request.settimeout(10)
        super().setup()

    def log_message(self, format, *args):
        pass

    def send_error(self, code, message=None, explain=None):
        self.send_json(code, {"error": "请求无法处理。"})

    def send_bytes(self, status, body, content_type, *, disposition=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", POLICY)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if disposition is not None:
            self.send_header("Content-Disposition", disposition)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, status, value):
        # 转义模型返回的孤立代理码，避免编码响应时中断连接。
        body = json.dumps(value).encode("ascii")
        self.send_bytes(status, body, "application/json; charset=utf-8")

    def local_request(self):
        # 限定 Host 和浏览器 Origin，防止外部网页借本地服务发起模型请求。
        hosts = self.headers.get_all("Host", [])
        origins = self.headers.get_all("Origin", [])
        port = self.server.server_port
        permitted = {"127.0.0.1:{}".format(port), "localhost:{}".format(port)}
        if port == 80:
            permitted.update({"127.0.0.1", "localhost"})
        if len(hosts) == 1 and hosts[0].lower() in permitted:
            if not origins or (len(origins) == 1 and origins[0].lower() == "http://" + hosts[0].lower()):
                return True
        self.send_json(403, {"error": "仅接受本机同源请求。"})
        return False

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self.local_request():
            return
        if self.path in STATIC:
            filename, content_type = STATIC[self.path]
            try:
                body = (WEB_DIR / filename).read_bytes()
            except OSError:
                self.send_error(404)
                return
            self.send_bytes(200, body, content_type)
            return
        match = ARCHIVE_PATH.fullmatch(self.path)
        if match is None:
            self.send_error(404)
            return
        self.get_archive(*match.groups())

    def get_archive(self, digest, kind):
        try:
            with Store(self.server.db_path) as store:
                receipt = public_archive(store, digest, kind)
            if receipt is None:
                self.send_error(404)
                return
            # 除库中已入库版本的登记外，原件仍须匹配其内容哈希。
            body = read_archive(self.server.data_dir, dict(receipt), kind)
        except (OSError, ValueError):
            self.send_error(404)
            return
        except Exception:
            self.send_error(500)
            return
        if kind == "pdf":
            if not body.startswith(b"%PDF-"):
                self.send_error(404)
                return
            self.send_bytes(200, body, "application/pdf", disposition='inline; filename="source.pdf"')
        else:
            self.send_bytes(200, html_archive(body), "text/html; charset=utf-8")

    def do_POST(self):
        if not self.local_request():
            return
        if self.path != "/api/ask":
            self.send_error(404)
            return
        if self.headers.get_content_type() != "application/json" or self.headers.get("Transfer-Encoding"):
            self.send_json(415, {"error": "请发送 JSON 请求。"})
            return
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,9}", lengths[0]):
            self.send_json(400, {"error": "请求长度无效。"})
            return
        length = int(lengths[0])
        if length > MAX_BODY:
            self.send_json(413, {"error": "问题请求过长。"})
            return
        try:
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError
            payload = json.loads(body.decode("utf-8"))
        except TimeoutError:
            self.send_json(408, {"error": "读取请求超时。"})
            return
        except (ValueError, RecursionError):
            self.send_json(400, {"error": "请求不是有效的 JSON。"})
            return
        question = payload.get("question") if isinstance(payload, dict) else None
        if not isinstance(question, str) or not 1 <= len(question.strip()) <= 1000:
            self.send_json(400, {"error": "请输入 1 至 1000 个字符的问题。"})
            return
        try:
            question.encode("utf-8")
        except UnicodeError:
            self.send_json(400, {"error": "问题包含无效字符。"})
            return
        try:
            # SQLite 连接只在当前请求线程中使用。
            with Store(self.server.db_path) as store:
                result = answer_question(store, question, "scoped", 5)
            clean_answer(result)
            for evidence in result.get("evidence", []):
                link = archive_url(evidence)
                if link:
                    evidence["archive_url"] = link
        except Exception:
            self.send_error(500)
            return
        self.send_json(200, result)


def make_server(db_path, data_dir, port=0):
    db_path = Path(db_path).resolve()
    if not db_path.is_file():
        raise FileNotFoundError("找不到资料库，请先运行导入。")
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.db_path = db_path
    httpd.data_dir = Path(data_dir).resolve()
    return httpd


def serve(db_path, data_dir, port):
    with make_server(db_path, data_dir, port) as httpd:
        print("本地问答页面 http://127.0.0.1:{}".format(httpd.server_port), flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
