"""Replay the frozen admissions questions with the same Top 5 evidence budget."""

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from .answer import answer_question, retrieve
from .capture import document_format, read_archive
from .catalog_scope import directory_scope
from .ingest import extract_document
from .store import Store, _search_text


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def compact(value):
    return re.sub(r"\s+", "", _search_text(value))


class ArchiveCheck:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.samples = {row["url"]: row for row in read_json(Path("samples/pages.json"))}
        self.charsets = {
            row["raw_sha256"]: row.get("charset")
            for row in read_json(Path("samples/captures.json")) if "raw_sha256" in row
        }
        self.cache = {}

    def verify(self, evidence):
        try:
            url, digest = evidence["url"], evidence["raw_sha256"]
            key = url, digest, evidence["raw_path"]
            if key not in self.cache:
                # 按原件哈希核验并重新解析，缓存结果供同一原件的多条引文复核。
                sample = self.samples[url]
                raw = read_archive(self.data_dir, evidence, document_format(sample))
                _, chunks, _ = extract_document(raw, self.charsets.get(digest), sample)
                self.cache[key] = chunks
            chunks = self.cache[key]
            ordinal = evidence["ordinal"]
            if not 1 <= ordinal <= len(chunks):
                return False
            chunk = chunks[ordinal - 1]
            return chunk["locator"] == evidence["locator"] and chunk["text"] == evidence["text"]
        except (LookupError, OSError, RecursionError, ValueError):
            return False


def matches_evidence(hit, item):
    if "url" in item:
        same_url = hit["url"] == item["url"]
    else:
        same_url = urlsplit(hit["url"]).path.endswith("/" + item["page"])
    locator = hit.get("locator", {})
    same_page = ("pdf_page" not in item
                 or (locator.get("kind") == "pdf" and locator.get("page") == item["pdf_page"]))
    matches_scope = all(locator.get("library_scope", {}).get(key, hit.get(key)) == value
                        for key, value in item.get("library_scope", {}).items())
    return (same_url and same_page and matches_scope
            and all(compact(term) in compact(hit["text"]) for term in item["terms"]))


def matching_ranks(hits, alternatives):
    # 一组证据允许多个等价来源，命中任意一个就满足该组要求。
    return [
        rank for rank, hit in enumerate(hits, 1)
        if any(matches_evidence(hit, item) for item in alternatives)
    ]


def evaluate(store, question, method, archive, generate):
    text = question["question"]
    if generate:
        answer = answer_question(store, text, method)
        all_evidence = answer.pop("evidence")
        # 表头和条款标题可用于引用，但不计入 Top 5 的证据覆盖。
        hits = [hit for hit in all_evidence if hit["rank"] is not None]
    else:
        hits = retrieve(store, text, method, 5)
        all_evidence = [dict(hit, id=rank, rank=rank) for rank, hit in enumerate(hits, 1)]
        answer = {"status": "not_run", "claims": []}
    groups = [matching_ranks(hits, group) for group in question["evidence"]]
    evidence = [
        {
            **{field: hit.get(field) for field in (
                "id", "rank", "context", "title", "url", "ordinal", "role", "admission_year",
                "audience", "published_at", "raw_sha256", "raw_path", "locator", "text",
                "snippet", "matched_terms", "evidence_topic", "topic", "campus", "building",
                "notice_kind", "service", "effective_from", "effective_to",
            )},
            "archive_verified": archive.verify(hit),
        }
        for hit in all_evidence
    ]
    checked = {hit["id"]: hit["archive_verified"] for hit in evidence}
    citations = {citation["id"] for claim in answer["claims"] for citation in claim["citations"]}
    result = {
        "id": question["id"],
        "question": text,
        "category": question["category"],
        "expected_status": question["answerability"],
        "expected_answer": question["expected"],
        "method": method,
        "required_group_ranks": groups,
        # 没有标注必需证据组的题不计入覆盖率分母。
        "all_required_in_top5": all(groups) if groups else None,
        "evidence": evidence,
        "answer": answer,
        "citations_locatable": all(checked.get(item, False) for item in citations) if citations else None,
    }
    if "allowed_catalog_scopes" in question:
        allowed = {tuple(scope) for scope in question["allowed_catalog_scopes"]}
        outside = [hit for hit in evidence if directory_scope(hit) is not None
                   and directory_scope(hit) not in allowed]
        result["out_of_scope_catalog_ranks"] = [hit["rank"] for hit in outside if hit["rank"] is not None]
        result["out_of_scope_catalog_citations"] = sorted(hit["id"] for hit in outside if hit["id"] in citations)
    if "topics" in question:
        result["expected_topics"] = question["topics"]
        allowed = set(question["topics"])
        result["out_of_topic_ranks"] = [hit["rank"] for hit in evidence
                                        if (hit["topic"] or "admissions") not in allowed
                                        or (hit["topic"] or "admissions") != hit["evidence_topic"]]
    if "excluded_urls" in question:
        result["excluded_url_ranks"] = [hit["rank"] for hit in evidence
                                        if hit["url"] in question["excluded_urls"]]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--db", type=Path)
    parser.add_argument("--questions", type=Path, default=Path("samples/admissions-eval.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generate", action="store_true", help="call the configured model")
    parser.add_argument("--method", choices=("keyword", "natural", "scoped"), action="append",
                        help="select a retriever; repeat to compare")
    parser.add_argument("--only", action="append", metavar="ID", help="select an evaluation ID; repeatable")
    args = parser.parse_args()
    questions = read_json(args.questions)["questions"]
    if args.only:
        requested = set(args.only)
        unknown = requested - {question["id"] for question in questions}
        if unknown:
            parser.error("unknown evaluation IDs: " + ", ".join(sorted(unknown)))
        questions = [question for question in questions if question["id"] in requested]
    archive = ArchiveCheck(args.data_dir)
    results = []
    methods = tuple(dict.fromkeys(args.method)) if args.method else ("keyword", "natural")
    db_path = args.db or args.data_dir / "corpus.sqlite3"
    if not db_path.is_file():
        parser.error("database not found; import the archived pages first")
    # 独占创建结果文件以保留已有评测，逐题写入便于中断后核对。
    with Store(db_path) as store, args.output.open("x", encoding="utf-8") as output:
        for question in questions:
            for method in methods:
                result = evaluate(store, question, method, archive, args.generate)
                results.append(result)
                output.write(json.dumps(result, ensure_ascii=False) + "\n")
                output.flush()
                print("{} {} top5={} answer={} citations={}".format(
                    question["id"], method, result["required_group_ranks"],
                    result["answer"]["status"], result["citations_locatable"]
                ), flush=True)
    for method in methods:
        applicable = [row for row in results if row["method"] == method
                      and row["all_required_in_top5"] is not None]
        print("{}: {}/{} all necessary evidence in Top 5".format(
            method, sum(row["all_required_in_top5"] for row in applicable), len(applicable)
        ))


if __name__ == "__main__":
    main()
