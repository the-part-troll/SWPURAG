"""Import captured pages without changing the current version on failure."""

import hashlib
import json

from .capture import document_format, read_archive, validate_url
from .html import extract as extract_html
from .store import library_metadata


ADMISSION_FIELDS = ("admission_year", "role", "audience")


def extract_document(body, charset, sample):
    if document_format(sample) == "pdf":
        if not body.startswith(b"%PDF-"):
            raise ValueError("Archived document has no PDF signature")
        # 仅解析 PDF 时加载其可选依赖，HTML 导入可独立运行。
        from .pdf import extract_pdf

        return extract_pdf(body, sample)
    return extract_html(body, charset, sample)


def content_hash(sample, title, chunks):
    version = {
        "title": title,
        "unit": sample["unit"],
        "page_type": sample["page_type"],
        "published_at": sample.get("published_at"),
        "updated_at": sample.get("updated_at"),
        "body": [chunk["text"] for chunk in chunks],
    }
    # 表格内容即使没变，移到另一页或另一行也会改变引用位置。
    if document_format(sample) == "pdf":
        version["format"] = "pdf"
        version["body"] = [
            {"text": chunk["text"], "page": chunk["locator"]["page"],
             "table": chunk["locator"].get("table"), "row": chunk["locator"].get("row")}
            for chunk in chunks
        ]
    # 缺省字段沿用原哈希规则，历史原件重复导入时可命中已有版本。
    version.update({field: sample[field] for field in ADMISSION_FIELDS if sample.get(field) is not None})
    version.update(library_metadata(sample))
    # 馆舍、有效期等段落适用范围的变更也应形成新版本。
    if version.get("topic") == "library":
        scopes = {
            index: chunk["locator"]["library_scope"]
            for index, chunk in enumerate(chunks, 1)
            if chunk["locator"].get("library_scope")
        }
        if scopes:
            version["library_scopes"] = scopes
    elif version.get("topic") == "school_calendar":
        # 校历日期与正文一起定版，标注修订可以单独形成版本。
        scopes = [chunk["locator"].get("calendar_scope") for chunk in chunks]
        if not all(scopes):
            raise ValueError("School calendar evidence requires a calendar scope for each block")
        version["calendar_scopes"] = scopes
    payload = json.dumps(version, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def import_capture(store, sample, receipt, data_dir):
    validate_url(sample)
    if receipt["url"] != sample["url"]:
        raise ValueError("Capture URL does not match the manifest")
    evidence = {}
    try:
        if receipt.get("error"):
            raise ValueError(receipt["error"])
        if receipt.get("http_status") != 200 or receipt.get("final_url") != sample["url"]:
            raise ValueError("Capture did not succeed at the declared URL")

        body = read_archive(data_dir, receipt, document_format(sample))
        # 校验字节后才关联原件，便于回查正文解析失败的快照。
        evidence = {key: receipt[key] for key in ("raw_sha256", "raw_path")}
        title, chunks, dates = extract_document(body, receipt.get("charset"), sample)
        version_sample = dict(sample, **dates)
        year = version_sample.get("admission_year")
        if year is not None and type(year) is not int:
            raise ValueError("admission_year must be an integer")
        for field in ("role", "audience"):
            value = version_sample.get(field)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(field + " must be a nonempty string")
        return store.record_success(
            version_sample, title=title, content_sha256=content_hash(version_sample, title, chunks),
            fetched_at=receipt["fetched_at"], final_url=receipt["final_url"], chunks=chunks, **evidence
        )
    except (LookupError, OSError, RecursionError, ValueError) as error:
        return store.record_failure(
            sample, fetched_at=receipt["fetched_at"], final_url=receipt.get("final_url"),
            error=error, **evidence
        )
