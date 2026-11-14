"""Command-line entry point for curated imports and evidence retrieval."""

import argparse
import json
import re
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import quote

from .answer import answer_question
from .capture import capture, validate_url
from .ingest import import_capture
from .retrieval import search_natural
from .store import Store


TOPIC_LABELS = {"admissions": "硕士招生", "library": "图书馆服务", "school_calendar": "校级放假与调休"}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def import_pages(store, args):
    manifest = read_json(args.manifest)
    for sample in manifest:
        validate_url(sample)
    samples = {sample["id"]: sample for sample in manifest}
    if len(samples) != len(manifest) or len({sample["url"] for sample in manifest}) != len(manifest):
        raise ValueError("Manifest has duplicate sample ids or URLs")
    if args.sample and args.sample not in samples:
        raise ValueError("Unknown sample id: {}".format(args.sample))
    selected = [samples[args.sample]] if args.sample else manifest
    if args.command == "import":
        # 离线导入先核对收据是否齐全，避免清单缺项时只导入一部分。
        receipts = read_json(args.captures)
        by_url = {receipt["url"]: receipt for receipt in receipts}
        if len(by_url) != len(receipts):
            raise ValueError("Capture file has duplicate URLs")
        missing = [sample["id"] for sample in selected if sample["url"] not in by_url]
        if missing:
            raise ValueError("Capture file is missing: " + ", ".join(missing))

    failed = False
    for index, sample in enumerate(selected):
        if args.command == "fetch":
            if index:
                # 批量抓取仍逐页请求，间隔一秒。
                time.sleep(1)
            receipt = capture(sample, args.data_dir)
        else:
            receipt = by_url[sample["url"]]
        result = import_capture(store, sample, receipt, args.data_dir)
        failed |= result["status"] == "failed"
        print(json.dumps(result, ensure_ascii=False))
    return int(failed)


def excerpt(text, query, width=220):
    if len(text) <= width:
        return text
    offsets = (text.lower().find(term) for term in re.findall(r"[^\W_]+", query.lower()))
    first = min((offset for offset in offsets if offset >= 0), default=0)
    start = max(0, first - 55)
    end = start + width
    return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")


def print_matches(results, query):
    if not results:
        print("未找到匹配的原文证据。")
    for index, result in enumerate(results, 1):
        locator = result["locator"]
        link = result["url"]
        is_pdf = locator["kind"] == "pdf"
        if is_pdf:
            link += "#page={}".format(locator["page"])
        elif locator.get("anchor"):
            link += "#" + quote(locator["anchor"], safe="")
        print("[{}] {}（{}）".format(result.get("id", index), result["title"], result["unit"]))
        label = "表格摘录" if is_pdf else "原文"
        print("{} {}".format(label, result.get("snippet") or excerpt(result["text"], query)))
        print("来源 {}".format(link))
        if is_pdf:
            print("PDF 第 {page} 页 · 表格第 {row} 行 · 区域 {bbox}".format(**locator))
        else:
            print("正文块 {paragraph} · HTML 第 {line} 行第 {column} 列".format(**locator))
            print("定位 {}".format(locator["selector"]))
            if result.get("topic") == "library":
                # 同一公告可分馆舍和日期，正文块的范围优先于页面默认值。
                scope = dict({key: result.get(key) for key in (
                    "campus", "building", "effective_from", "effective_to",
                )}, **locator.get("library_scope", {}))
                applies = [scope[key] for key in ("campus", "building") if scope.get(key)]
                if scope.get("effective_from") and scope.get("effective_to"):
                    applies.append("{} 至 {}".format(scope["effective_from"], scope["effective_to"]))
                print("适用 {}".format(" · ".join(applies)))
            if result.get("topic") == "school_calendar":
                scope = locator.get("calendar_scope", {})
                applies = [scope.get("holiday")]
                if scope.get("effective_from") and scope.get("effective_to"):
                    applies.append("{} 至 {}".format(scope["effective_from"], scope["effective_to"]))
                if scope.get("makeup_dates"):
                    applies.append("调休上课 " + "、".join(scope["makeup_dates"]))
                if any(applies):
                    print("适用 {}".format(" · ".join(value for value in applies if value)))
        print("原件 {} · 版本 {} · 抓取 {}".format(
            result["raw_path"], result["version_id"], result["fetched_at"]
        ))
        print()


def print_answer_body(result):
    if result.get("scope_note"):
        print(result["scope_note"])
    if result["status"] == "unavailable":
        print("模型回答不可用。{}".format(result.get("error", "")))
    for claim in result["claims"]:
        ids = sorted({citation["id"] for citation in claim["citations"]})
        print("{} {}".format(claim["text"], " ".join("[{}]".format(index) for index in ids)))
    if result.get("follow_up"):
        label = "需要补充" if result["status"] == "clarify" else "证据缺口"
        print("{} {}".format(label, result["follow_up"]))


def print_answer(result):
    if result.get("topic_answers"):
        # 分主题显示回答，所有引文仍沿用本次问答统一编号。
        for index, (topic, answer) in enumerate(result["topic_answers"].items()):
            if index:
                print()
            print("【{}】".format(TOPIC_LABELS.get(topic, "回答")))
            print_answer_body(answer)
    else:
        if result.get("topics") == ["school_calendar"]:
            print("【{}】".format(TOPIC_LABELS["school_calendar"]))
        print_answer_body(result)
    if result["status"] == "unavailable" and not result["claims"]:
        print_matches(result["evidence"], result["question"])
        return
    # 保留本次问答的证据编号，仅展示回答实际引用的摘录。
    quotes = {}
    for claim in result["claims"]:
        for citation in claim["citations"]:
            quotes.setdefault(citation["id"], []).append(citation["quote"])
    cited = [
        dict(item, snippet=" … ".join(dict.fromkeys(quotes[item["id"]])))
        for item in result["evidence"] if item["id"] in quotes
    ]
    if cited:
        print()
        print_matches(cited, result["question"])


def main():
    parser = argparse.ArgumentParser(description="Import and retrieve curated SWPU page evidence")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--db", type=Path, help="defaults to <data-dir>/corpus.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("import", "replay local captures without network access"),
        ("fetch", "fetch only the exact manifest URLs, once each"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--manifest", type=Path, default=Path("samples/pages.json"))
        command.add_argument("--sample", help="import one id from the manifest")
        if name == "import":
            command.add_argument("--captures", type=Path, default=Path("samples/captures.json"))
    search = commands.add_parser("search", help="show matching paragraphs and citations")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)
    search.add_argument("--json", action="store_true", help="return full matching blocks and metadata")
    search_modes = search.add_mutually_exclusive_group()
    search_modes.add_argument("--natural", action="store_true", help="rank evidence for a natural question")
    search_modes.add_argument("--scoped", action="store_true", help="rank 2027 admissions evidence with study mode and college scope")
    search.add_argument("--admission-year", type=int, help="filter to the given admission cycle")
    ask = commands.add_parser("ask", help="answer a master's admissions, library or university calendar question with citations")
    ask.add_argument("query")
    ask.add_argument("--limit", type=int, choices=range(1, 11), default=5)
    ask.add_argument("--retriever", choices=("scoped", "natural", "keyword"), default="scoped")
    ask.add_argument("--json", action="store_true", help="return the answer and all supplied evidence")
    browser = commands.add_parser("serve", help="start the local browser demo on 127.0.0.1")
    browser.add_argument("--port", type=int, default=8765)
    commands.add_parser("stats", help="show corpus and import counts")
    args = parser.parse_args()
    if args.command == "serve" and not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    db_path = args.db or args.data_dir / "corpus.sqlite3"
    try:
        if args.command in ("import", "fetch"):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        elif not db_path.is_file():
            raise ValueError("Corpus not found. Run import first: {}".format(db_path))
        if args.command == "serve":
            from .server import serve

            return serve(db_path, args.data_dir, args.port)
        with Store(db_path) as store:
            if args.command in ("import", "fetch"):
                return import_pages(store, args)
            if args.command == "stats":
                print(json.dumps(store.stats(), ensure_ascii=False))
            elif args.command == "ask":
                result = answer_question(store, args.query, args.retriever, args.limit)
                if args.json:
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                else:
                    print_answer(result)
                return int(result["status"] == "unavailable")
            else:
                if args.scoped:
                    from .answer import ADMISSION_YEAR
                    from .catalog_scope import search_scoped

                    year = args.admission_year if args.admission_year is not None else ADMISSION_YEAR
                    results, _ = search_scoped(store, args.query, args.limit, year)
                elif args.natural:
                    results = search_natural(store, args.query, args.limit, admission_year=args.admission_year)
                else:
                    results = store.search(args.query, args.limit, admission_year=args.admission_year)
                if args.json:
                    print(json.dumps(results, ensure_ascii=False, indent=2))
                else:
                    print_matches(results, args.query)
    except (KeyError, OSError, ValueError, sqlite3.Error) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
