"""Replay the scoped lexical retriever against the routing and scope labels."""

import argparse
import hashlib
import json
import sys
import time
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


def run(store, output, acceptance, prepare=prepare_retrieval, *, boundary=(), discovery=(), archive=None):
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
    suite_by_id = {q["id"]: suite for suite, dataset in
                   (("routing-acceptance", acceptance), ("boundary-acceptance", boundary),
                    ("discovery-acceptance", discovery)) for q in dataset}
    for q in frozen + old + acceptance + list(boundary) + list(discovery):
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
        if "wrong_scope" in q:
            candidate_ids = {key for batch in trace["batches"] for key in batch["candidate_ids"]}
            result["wrong_scope_candidate_counts"] = [sum(locate(rows_by_id[key], spec, samples)
                                                           for key in candidate_ids)
                                                      for spec in q["wrong_scope"]]
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
            elif not target_topics & topics.keys():
                stages.append("topic_routing")
            else:
                stages.append("ranking" if candidate else "scope_filter")
        result["missing_group_stages"] = stages
        result["archived_top5_verified"] = all(archive.verify(row) for row in hits)
        output.write(json.dumps(result, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline-source", type=Path, help="trusted pre-fix source files")
    parser.add_argument("--boundary", action="store_true", help="include the frozen boundary acceptance set")
    parser.add_argument("--db", type=Path, default=Path("data/corpus.sqlite3"))
    parser.add_argument("--discovery", action="store_true", help="include the frozen discovery acceptance set")
    args = parser.parse_args()
    if args.discovery and args.db.resolve() == Path("data/corpus.sqlite3").resolve():
        parser.error("the discovery suite requires --db for an isolated validation database")
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
    archive = ArchiveCheck(Path("data"), extra_manifests=DISCOVERY_MANIFESTS) if args.discovery else None
    with Store(args.db) as store, args.output.open("x", encoding="utf-8") as output:
        run(store, output, acceptance, prepare, boundary=boundary, discovery=discovery, archive=archive)
    print("Saved", args.output)


if __name__ == "__main__":
    main()
