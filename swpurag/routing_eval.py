"""Replay the scoped lexical retriever against the routing and scope labels."""

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from contextlib import closing, contextmanager, nullcontext
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from .answer import prepare_retrieval
from .evaluate import ArchiveCheck, matches_evidence, read_json
from .hybrid_eval import LIMIT, locate, read_sets, score, validate_labels, view_hit
from .store import Store


ACCEPTANCE = Path("samples/routing-acceptance.json")
ACCEPTANCE_SHA256 = "f043d2d3c808ed7d214491714739af737ecf7ede671abe8eb36e0e86b4c423e7"
BOUNDARY = Path("samples/boundary-acceptance.json")
BOUNDARY_SHA256 = "79ad3456470990c27bb4258e33f9dd5077544da0a814a97dd6f2fe4b0cd2801c"
DISCOVERY = Path("samples/discovery/acceptance.json")
DISCOVERY_SHA256 = "c6ad2abb5782fc613a3c4f223ee44a029000a23d6abc1094fe5bb04860759cce"
DISCOVERY_MANIFESTS = [(Path("samples/discovery/pages.json"), Path("samples/discovery/captures.json"))]
EXPANSION = Path("samples/discovery/expansion-acceptance.json")
EXPANSION_NEGATIVES = Path("samples/discovery/expansion-negatives.json")
EXPANSION_SHA256 = "4721faab4f77cbb804d29e6f3a9d9adf7b3febf7c5d106b38ba9aea314a1072d"
EXPANSION_NEGATIVES_SHA256 = "ef95fa39d175a48f882cdefedb2b7a533076aea827c26364d98f261cf05b6304"
LIBRARY_DISCOVERY_SHA256 = "78c3b5c65aece48912f306b7236f5679b4dbf0149f3ac293f94f01d5b4daaab4"
LIBRARY_HOLIDAY_SHA256 = "b75a2bb4a6e38776fb021e333631c8d5d632aa8dcffd24aa91f4279cbf81d88f"


def load_baseline(path):
    # 按依赖顺序在内存加载历史源码，也兼容只含路由、图书馆和回答模块的旧快照。
    names = [name for name in ("retrieval", "catalog_scope") if (path / f"{name}.py").is_file()]
    names.extend(("topics", "library_scope", "answer"))
    modules = {f"swpurag.{name}": ModuleType(f"swpurag.{name}") for name in names}
    with patch.dict(sys.modules, modules):
        for name, module in modules.items():
            source = path / (name.rsplit(".", 1)[1] + ".py")
            module.__package__ = "swpurag"
            exec(compile(source.read_bytes(), str(source), "exec"), module.__dict__)
    return modules["swpurag.answer"].prepare_retrieval


def run(store, output, acceptance, prepare=prepare_retrieval, *, boundary=(), discovery=(),
        expansion=(), negative_overlay=None, archive=None, library=(), library_label_store=None,
        holiday=()):
    rows = list(store.current_chunks())
    if archive is None and (store.stats()["documents"], len(rows)) != (13, 747):
        raise ValueError("The routing comparison requires the original 13 documents and 747 blocks")
    archive = archive or ArchiveCheck(Path("data"))
    samples = {row["id"]: row["url"] for row in archive.samples.values()}
    by_url = {url: sample for sample, url in samples.items()}
    rows_by_id = {row["chunk_id"]: row for row in rows}
    frozen, old = read_sets()
    if not 6 <= len(acceptance) <= 8:
        raise ValueError("Expected 6–8 new acceptance questions")
    # 各套冻结标签使用相同原件校验，分别检查题数。
    validate_labels(frozen, rows, samples, archive)
    validate_labels(acceptance, rows, samples, archive, size=(6, 8))
    if boundary:
        validate_labels(boundary, rows, samples, archive, size=(6, 8))
    if discovery:
        validate_labels(discovery, rows, samples, archive, size=(6, 8))
    if expansion:
        validate_labels(expansion, rows, samples, archive, size=(4, 6))
    if library or holiday:
        # 新公告在基线库中缺失，仍以候选库和归档原件核验同一套冻结标注。
        label_rows = list(library_label_store.current_chunks()) if library_label_store else rows
    if library:
        validate_labels(library, label_rows, samples, archive, size=(6, 8))
    if holiday:
        validate_labels(holiday, label_rows, samples, archive, size=(4, 4))
    suite_by_id = {q["id"]: suite for suite, dataset in
                   (("routing-acceptance", acceptance), ("boundary-acceptance", boundary),
                    ("discovery-acceptance", discovery), ("expansion-acceptance", expansion),
                    ("library-discovery", library), ("library-holiday", holiday)) for q in dataset}
    questions = frozen + old + acceptance + list(boundary) + list(discovery) + list(expansion) + list(library) + list(holiday)
    negative_overlay = negative_overlay or {}
    if set(negative_overlay) - {q["id"] for q in questions}:
        raise ValueError("Wrong-scope overlay refers to an unknown question")
    for entries in negative_overlay.values():
        for item in entries:
            matches = [row for row in rows if locate(row, item, samples)]
            if len(matches) != 1 or not archive.verify(matches[0]):
                raise ValueError("Cannot verify wrong-scope overlay: " + str(item))
    for q in questions:
        start = time.perf_counter()
        trace = {}
        evidence, topics, scopes = prepare(store, q["question"], limit=LIMIT, trace=trace)
        elapsed = (time.perf_counter() - start) * 1000
        hits = [row for row in evidence if row["rank"] is not None]
        result = score(q, "lexical", hits, topics, scopes, trace, elapsed, samples, by_url, rows_by_id)
        if q["id"] in suite_by_id:
            result["suite"] = suite_by_id[q["id"]]
        if "expected_answer_status" in q:
            result["expected_answer_status"] = q["expected_answer_status"]
        if "expected_hours_schedule" in q:
            result["expected_hours_schedule"] = q["expected_hours_schedule"]
        if "wrong_scope" in q:
            candidate_ids = {key for batch in trace["batches"] for key in batch["candidate_ids"]}
            result["wrong_scope_candidate_counts"] = [sum(locate(rows_by_id[key], spec, samples)
                                                           for key in candidate_ids)
                                                      for spec in q["wrong_scope"]]
        if q["id"] in negative_overlay:
            wrong = negative_overlay[q["id"]]
            overlay_ranks = [row["rank"] for row in hits if any(locate(row, spec, samples) for spec in wrong)]
            candidate_ids = {key for batch in trace["batches"] for key in batch["candidate_ids"]}
            result["wrong_scope_overlay_candidates"] = [spec for spec in wrong
                                                        if any(locate(rows_by_id[key], spec, samples)
                                                               for key in candidate_ids)]
            result["wrong_scope_overlay_ranks"] = overlay_ranks
            result["wrong_scope_ranks"] = sorted(set(result["wrong_scope_ranks"]) | set(overlay_ranks))
        specs = (q["evidence"] if "suite" in q else [group["alternatives"] for group in q["required"]])
        matches = matches_evidence if "suite" in q else lambda row, spec: locate(row, spec, samples)
        group_topics = [{row.get("topic") or "admissions" for row in rows
                         if any(matches(row, item) for item in group)} for group in specs]
        expected_topics = q.get("expected_topics") or q.get("topics") or sorted(set().union(*group_topics))
        result["routed_questions"] = topics
        result["expected_topics"] = expected_topics or None
        result["context_group_ids"] = [[row["id"] for row in evidence if row["rank"] is None
                                         and any(matches(row, item) for item in group)] for group in specs]
        result["context_evidence"] = [dict(view_hit(row, by_url), id=row["id"], context=row["context"])
                                      for row in evidence if row["rank"] is None]
        stages = []
        for target_topics, ranks, candidate in zip(group_topics, result["required_group_ranks"],
                                                   result["required_groups_in_candidate_pool"]):
            if ranks:
                stages.append(None)
            elif result["suite"] == "library-discovery" and not target_topics:
                stages.append("not_in_corpus")
            elif not target_topics & topics.keys():
                stages.append("topic_routing")
            else:
                stages.append("ranking" if candidate else "scope_filter")
        result["missing_group_stages"] = stages
        result["archived_top5_verified"] = all(archive.verify(row) for row in hits)
        output.write(json.dumps(result, ensure_ascii=False) + "\n")


@contextmanager
def read_only_store(path):
    # 直接以只读模式打开，避免 Store 初始化时尝试建表或迁移。
    uri = path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        store = Store.__new__(Store)
        store.db = connection
        yield store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline-source", type=Path, help="trusted pre-fix source files")
    parser.add_argument("--boundary", action="store_true", help="include the frozen boundary acceptance set")
    parser.add_argument("--db", type=Path, default=Path("data/corpus.sqlite3"))
    parser.add_argument("--discovery", action="store_true", help="include the frozen discovery acceptance set")
    parser.add_argument("--expansion", action="store_true", help="include the expansion acceptance set and scope overlay")
    parser.add_argument("--library-discovery", type=Path, help="library notice manifests and frozen questions")
    parser.add_argument("--library-holiday", action="store_true", help="include the frozen holiday date boundary set")
    parser.add_argument("--library-label-db", type=Path, help="validate new labels against this database when replaying the baseline")
    args = parser.parse_args()
    if args.expansion and not (args.boundary and args.discovery):
        parser.error("expansion replay requires --boundary and --discovery")
    if args.library_holiday and not args.library_discovery:
        parser.error("holiday replay requires --library-discovery")
    if args.discovery and args.db.resolve() == Path("data/corpus.sqlite3").resolve():
        parser.error("the discovery suite requires --db for an isolated validation database")
    if args.library_label_db and not (args.library_discovery and args.library_label_db.is_file()):
        parser.error("--library-label-db requires --library-discovery and an existing database")
    if not args.db.is_file():
        parser.error("database does not exist")
    raw = ACCEPTANCE.read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(raw).hexdigest() != ACCEPTANCE_SHA256:
        parser.error("acceptance file differs from the frozen questions")
    acceptance = read_json(ACCEPTANCE)
    boundary = ()
    if args.boundary:
        raw = BOUNDARY.read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(raw).hexdigest() != BOUNDARY_SHA256:
            parser.error("boundary file differs from the frozen questions")
        boundary = read_json(BOUNDARY)
    prepare = load_baseline(args.baseline_source) if args.baseline_source else prepare_retrieval
    discovery = ()
    if args.discovery:
        raw = DISCOVERY.read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(raw).hexdigest() != DISCOVERY_SHA256:
            parser.error("discovery file differs from the frozen questions")
        discovery = read_json(DISCOVERY)
    manifests = list(DISCOVERY_MANIFESTS) if args.discovery else []
    library, holiday = (), ()
    if args.library_discovery:
        directory = args.library_discovery
        path = directory / "acceptance.json"
        if hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() != LIBRARY_DISCOVERY_SHA256:
            parser.error("library discovery file differs from the frozen questions")
        library = read_json(path)
        if args.library_holiday:
            path = directory / "holiday-acceptance.json"
            if hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() != LIBRARY_HOLIDAY_SHA256:
                parser.error("library holiday file differs from the frozen questions")
            holiday = read_json(path)
        manifests.append((directory / "pages.json", directory / "captures.json"))
    archive = ArchiveCheck(Path("data"), extra_manifests=manifests) if manifests else None
    expansion, overlay = (), None
    if args.expansion:
        for path, digest in ((EXPANSION, EXPANSION_SHA256), (EXPANSION_NEGATIVES, EXPANSION_NEGATIVES_SHA256)):
            if hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() != digest:
                parser.error(f"{path} differs from the frozen annotations")
        expansion, overlay = read_json(EXPANSION), read_json(EXPANSION_NEGATIVES)
    labels = read_only_store(args.library_label_db) if args.library_label_db else nullcontext()
    with read_only_store(args.db) as store, labels as library_label_store:
        if args.expansion and not library and (store.stats()["documents"], store.stats()["chunks"]) != (15, 813):
            parser.error("expansion replay requires the 15-document, 813-block validation database")
        with args.output.open("x", encoding="utf-8") as output:
            run(store, output, acceptance, prepare, boundary=boundary, discovery=discovery,
                expansion=expansion, negative_overlay=overlay, archive=archive, library=library,
                library_label_store=library_label_store, holiday=holiday)
    print("Saved", args.output)


if __name__ == "__main__":
    main()
