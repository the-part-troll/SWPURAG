"""Single-request acquisition and immutable document snapshots."""

import hashlib
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


MAX_BYTES = 4 * 1024 * 1024
MAX_PDF_BYTES = 25 * 1024 * 1024
FORMATS = {
    "html": (MAX_BYTES, {"text/html", "application/xhtml+xml"}),
    "pdf": (MAX_PDF_BYTES, {"application/pdf", "application/octet-stream"}),
}


def timestamp():
    china = timezone(timedelta(hours=8))
    return datetime.now(china).isoformat(timespec="seconds")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def document_format(sample):
    value = sample.get("format", "html")
    if not isinstance(value, str) or value not in FORMATS:
        raise ValueError("Unsupported document format: {}".format(value))
    return value


def raw_path_for(digest, file_format):
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Invalid SHA-256 for archived document")
    return "raw/{}.{}".format(digest, file_format)


def archive(data_dir, body, document_format="html"):
    if not isinstance(document_format, str) or document_format not in FORMATS:
        raise ValueError("Unsupported document format: {}".format(document_format))
    max_bytes = FORMATS[document_format][0]
    if len(body) > max_bytes:
        raise ValueError("Document exceeds {} bytes".format(max_bytes))
    digest = hashlib.sha256(body).hexdigest()
    relative_path = raw_path_for(digest, document_format)
    target = data_dir / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() == body:
        return {"raw_sha256": digest, "raw_path": relative_path}

    # Replace atomically so a reader sees a complete file even on concurrent imports.
    with tempfile.NamedTemporaryFile(dir=str(target.parent), delete=False) as temporary:
        temporary_path = temporary.name
        try:
            temporary.write(body)
            temporary.close()
            os.replace(temporary_path, str(target))
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)
    return {"raw_sha256": digest, "raw_path": relative_path}


def read_archive(data_dir, receipt, file_format):
    digest = receipt.get("raw_sha256")
    relative_path = raw_path_for(digest, file_format)
    if relative_path != receipt.get("raw_path"):
        raise ValueError("Invalid content-addressed {} path".format(file_format.upper()))
    max_bytes = FORMATS[file_format][0]
    with (data_dir / relative_path).open("rb") as original:
        body = original.read(max_bytes + 1)
    if len(body) > max_bytes or hashlib.sha256(body).hexdigest() != digest:
        raise ValueError("Archived {} size or SHA-256 verification failed".format(file_format.upper()))
    return body


def validate_url(sample):
    url = urlsplit(sample["url"])
    prefix = sample["path_prefix"]
    path = url.path or "/"
    in_scope = path == prefix or path.startswith(prefix.rstrip("/") + "/")
    if (url.scheme != "https" or url.netloc.lower() != sample["host"].lower()
            or not prefix.startswith("/") or not in_scope or url.fragment):
        raise ValueError("URL must use HTTPS and match the declared host and path")


def capture(sample, data_dir):
    validate_url(sample)
    file_format = document_format(sample)
    max_bytes, content_types = FORMATS[file_format]
    url = sample["url"]
    result = {"url": url, "fetched_at": timestamp(), "final_url": None}
    request = Request(url, headers={"User-Agent": "SWPURAG/0.1 (curated public-page sample)"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=15) as response:
            result.update(final_url=response.geturl(), http_status=response.status)
            if response.status != 200:
                raise ValueError("Unexpected HTTP status {}".format(response.status))
            content_type = response.headers.get_content_type()
            result["content_type"] = content_type
            if content_type not in content_types:
                raise ValueError("Unexpected {} content type: {}".format(file_format.upper(), content_type))
            if file_format == "html":
                result["charset"] = response.headers.get_content_charset()
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise ValueError("Response exceeds {} bytes".format(max_bytes))
            if not body.strip():
                raise ValueError("Empty response body")
            if file_format == "pdf" and not body.startswith(b"%PDF-"):
                raise ValueError("Response has no PDF signature")
            result.update(archive(data_dir, body, document_format=file_format))
    except HTTPError as error:
        with error:
            result.update(final_url=error.geturl(), http_status=error.code,
                          error="HTTP {} {}".format(error.code, error.reason))
    except (URLError, OSError, ValueError, HTTPException) as error:
        result["error"] = str(error)
    return result
