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
from .hybrid_eval import LIMIT, locate, read_sets, score, validate_labels
from .store import Store


ACCEPTANCE = Path("samples/routing-acceptance.json")
ACCEPTANCE_SHA256 = "f043d2d3c808ed7d214491714739af737ecf7ede671abe8eb36e0e86b4c423e7"


def load_baseline(path):
    # 在内存执行三份修复前源码，与当前数据库和词法检索复用同一入口。
    modules = {name: ModuleType(name) for name in
               ("swpurag.topics", "swpurag.library_scope", "swpurag.answer")}
    with patch.dict(sys.modules, modules):
        for name, module in modules.items():
            source = path / (name.rsplit(".", 1)[1] + ".py")
            module.__package__ = "swpurag"
            exec(compile(source.read_bytes(), str(source), "exec"), module.__dict__)
    return modules["swpurag.answer"].prepare_retrieval


def run(store, output, acceptance, prepare=prepare_retrieval):
    rows = list(store.current_chunks())
    if (store.stats()["documents"], len(rows)) != (13, 747):
        raise ValueError("The routing comparison requires the original 13 documents and 747 blocks")
    archive = ArchiveCheck(Path("data"))
    samples = {row["id"]: row["url"] for row in archive.samples.values()}
    by_url = {url: sample for sample, url in samples.items()}
    rows_by_id = {row["chunk_id"]: row for row in rows}
    frozen, old = read_sets()
    if not 6 <= len(acceptance) <= 8:
        raise ValueError("Expected 6–8 new acceptance questions")
    # 两套新旧冻结标签使用同样的原件校验规则，但分别检查题数。
    validate_labels(frozen, rows, samples, archive)
    validate_labels(acceptance, rows, samples, archive, size=(6, 8))
    acceptance_ids = {q["id"] for q in acceptance}
    for q in frozen + old + acceptance:
        start = time.perf_counter()
        trace = {}
        evidence, topics, scopes = prepare(store, q["question"], limit=LIMIT, trace=trace)
        elapsed = (time.perf_counter() - start) * 1000
        hits = [row for row in evidence if row["rank"] is not None]
        result = score(q, "lexical", hits, topics, scopes, trace, elapsed, samples, by_url, rows_by_id)
        if q["id"] in acceptance_ids:
            result["suite"] = "routing-acceptance"
        specs = (q["evidence"] if "suite" in q else [group["alternatives"] for group in q["required"]])
        matches = matches_evidence if "suite" in q else lambda row, spec: locate(row, spec, samples)
        group_topics = [{row.get("topic") or "admissions" for row in rows
                         if any(matches(row, item) for item in group)} for group in specs]
        expected_topics = q.get("expected_topics") or q.get("topics") or sorted(set().union(*group_topics))
        result["routed_questions"] = topics
        result["expected_topics"] = expected_topics or None
        result["context_group_ids"] = [[row["id"] for row in evidence if row["rank"] is None
                                         and any(matches(row, item) for item in group)] for group in specs]
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
    parser.add_argument("--baseline-source", type=Path, help="trusted pre-fix copies of topics.py, library_scope.py and answer.py")
    args = parser.parse_args()
    raw = ACCEPTANCE.read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(raw).hexdigest() != ACCEPTANCE_SHA256:
        parser.error("acceptance file differs from the frozen questions")
    acceptance = read_json(ACCEPTANCE)
    prepare = load_baseline(args.baseline_source) if args.baseline_source else prepare_retrieval
    with Store(Path("data/corpus.sqlite3")) as store, args.output.open("x", encoding="utf-8") as output:
        run(store, output, acceptance, prepare)
    print("Saved", args.output)


if __name__ == "__main__":
    main()
