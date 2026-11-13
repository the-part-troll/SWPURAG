"""Build an offline embedding index and compare three rankers without generation."""

import argparse
import hashlib
import json
import time
from pathlib import Path

from .answer import prepare_retrieval
from .catalog_scope import directory_scope
from .embeddings import RRF_DEPTH, RRF_K, VectorIndex, build_index, fuse
from .evaluate import ArchiveCheck, matches_evidence, read_json
from .store import Store


LIMIT = 5
METHODS = ("lexical", "vector", "rrf")
FROZEN = {
    "samples/hybrid-admissions.json": "a0de366a1801c60b9cb04c1cee3d6f7169a316419b05f76cb2acf4efed617aa5",
    "samples/hybrid-library-mixed.json": "37f183a3d4847fd9f3f0ee030a6d527e6bbfefea2d0a9846df126626b3b926ba",
}
REGRESSION = ("admissions-eval", "admissions-acceptance", "admissions-pdf-eval",
              "admissions-catalog-scope-eval", "library-eval")


def read_sets():
    frozen = []
    for filename, digest in FROZEN.items():
        path = Path(filename)
        if hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() != digest:
            raise ValueError("Frozen question file checksum changed: " + filename)
        frozen.extend(read_json(path))
    old = [{**question, "suite": label} for label in REGRESSION
           for question in read_json(Path("samples", label + ".json"))["questions"]]
    return frozen, old


def locate(row, spec, samples):
    return row["url"] == samples[spec["sample"]] and all(
        row["locator"].get(key) == value for key, value in spec.items() if key != "sample"
    )


def validate_labels(questions, rows, samples, archive, *, size=(18, 24)):
    ids = [q["id"] for q in questions]
    if not size[0] <= len(ids) <= size[1] or len(set(ids)) != len(ids):
        raise ValueError(f"Expected {size[0]}–{size[1]} unique frozen questions")
    for q in questions:
        if q["expected_status"] not in {"evidence", "clarify", "insufficient"}:
            raise ValueError("Unknown target status for " + q["id"])
        if q["expected_status"] == "evidence" and not q["required"]:
            raise ValueError("Missing required evidence for " + q["id"])
        for spec in [item for group in q["required"] for item in group["alternatives"]] + q["wrong_scope"]:
            matches = [row for row in rows if locate(row, spec, samples)]
            # 整份错范围来源仅需已入库；精确段落和页行重新从原件核对。
            if not matches or (len(spec) > 1 and (len(matches) != 1 or not archive.verify(matches[0]))):
                raise ValueError("Cannot verify {} label {}".format(q["id"], spec))


def scope_states(topics, scopes, hits):
    # 只报告现有前置规则能判断的状态。有候选不能证明问题可答。
    states = {}
    for topic in topics:
        scope = scopes[topic]
        ranked = any(row["evidence_topic"] == topic for row in hits)
        if scope.get("clarification"):
            states[topic] = "clarify"
        elif scope.get("unsupported") or not ranked:
            states[topic] = "insufficient"
        else:
            states[topic] = "evidence_available"
    return states


def view_hit(row, by_url):
    locator = row["locator"]
    return {"sample": by_url[row["url"]], **{key: row[key] for key in
            ("chunk_id", "rank", "evidence_topic", "title", "url", "raw_sha256")},
            "locator": {key: locator[key] for key in ("kind", "paragraph", "line", "page", "row")
                        if key in locator},
            "snippet": row.get("snippet") or row["text"][:220],
            **{key: row[key] for key in ("vector_score", "rrf_score") if key in row}}


def score(q, method, hits, topics, scopes, trace, elapsed_ms, samples, by_url, rows_by_id):
    candidate_ids = {item for batch in trace["batches"] for item in batch["candidate_ids"]}
    if "suite" not in q:
        expected = q["expected_status"]
        requirements = [group["alternatives"] for group in q["required"]]

        def matches(row, spec):
            return locate(row, spec, samples)

        wrong = [row["rank"] for row in hits if any(locate(row, spec, samples) for spec in q["wrong_scope"])]
    else:
        expected = {"answered": "evidence"}.get(q["answerability"], q["answerability"])
        requirements = q["evidence"]
        matches = matches_evidence
        allowed = {tuple(scope) for scope in q.get("allowed_catalog_scopes", [])}
        desired_topics = set(q.get("topics", ["admissions"]))
        wrong = [row["rank"] for row in hits if row["url"] in q.get("excluded_urls", [])
                 or (row.get("topic") or "admissions") not in desired_topics
                 or (allowed and directory_scope(row) is not None and directory_scope(row) not in allowed)]
    wrong = sorted(set(wrong) | {row["rank"] for row in hits
                               if (row.get("topic") or "admissions") != row["evidence_topic"]})
    states = scope_states(topics, scopes, hits)
    state = next((value for value in ("insufficient", "clarify") if value in states.values()), "evidence_available")
    groups = [[row["rank"] for row in hits if any(matches(row, spec) for spec in group)] for group in requirements]
    eligible_groups = [any(matches(rows_by_id[key], spec) for key in candidate_ids for spec in group)
                       for group in requirements]
    batch_counts = [{"topic": batch["topic"], "stage": batch["stage"], "query": batch["query"],
                     "candidate_count": len(batch["candidate_ids"]), "ranked_ids": batch["ranked_ids"]}
                    for batch in trace["batches"]]
    return {"suite": q.get("suite", "frozen"), "id": q["id"], "question": q["question"], "method": method,
            "expected_status": expected, "retrieval_status": state, "topic_statuses": states, "scopes": scopes,
            "required_group_ranks": groups, "required_groups_in_candidate_pool": eligible_groups,
            "any_required": any(groups) if expected == "evidence" else None,
            "all_required": bool(groups) and all(groups) if expected == "evidence" else None,
            "wrong_scope_ranks": wrong, "latency_ms": round(elapsed_ms, 3),
            "candidate_count": len(candidate_ids),
            "batches": batch_counts, "top5": [view_hit(row, by_url) for row in hits]}


def compare(store, questions, index, samples, rows, output):
    by_url = {url: sample for sample, url in samples.items()}
    rows_by_id = {row["chunk_id"]: row for row in rows}
    index.encoder.encode(["本地索引预热"])
    for i, q in enumerate(questions):
        results = {}
        reference = None
        # 轮换方法顺序，减少固定运行顺序带来的机器负载偏差。
        offset = i % len(METHODS)
        for method in METHODS[offset:] + METHODS[:offset]:
            trace = {}
            vector = index.scorer()

            def rank(query, candidates, limit, lexical):
                if method == "vector":
                    return vector(query, candidates, limit)
                return fuse(lexical(RRF_DEPTH), vector(query, candidates, RRF_DEPTH), limit)

            start = time.perf_counter()
            evidence, topics, scopes = prepare_retrieval(store, q["question"], limit=LIMIT,
                                                          ranker=None if method == "lexical" else rank, trace=trace)
            elapsed = (time.perf_counter() - start) * 1000
            hits = [row for row in evidence if row["rank"] is not None]
            signature = [(batch["topic"], batch["stage"], batch["query"], tuple(batch["candidate_ids"]))
                         for batch in trace["batches"]]
            if (reference is not None and signature != reference) or len(hits) > LIMIT:
                raise ValueError("Inconsistent candidate batches or budget for " + q["id"])
            reference = signature
            results[method] = score(q, method, hits, topics, scopes, trace, elapsed, samples, by_url, rows_by_id)
        for method in METHODS:
            output.write(json.dumps(results[method], ensure_ascii=False) + "\n")
        output.flush()
        print(q["id"], *(str(results[m]["all_required"]) for m in METHODS), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "evaluate"))
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--db", type=Path)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    db_path = args.db or args.data_dir / "corpus.sqlite3"
    if not db_path.is_file():
        parser.error("database not found; run the offline import first")
    if args.action == "evaluate" and args.output is None:
        parser.error("evaluate requires --output")
    with Store(db_path) as store:
        rows = sorted(store.current_chunks(), key=lambda row: row["chunk_id"])
        if (store.stats()["documents"], len(rows)) != (13, 747):
            parser.error("this comparison requires the original 13 documents and 747 current blocks")
        if args.action == "build":
            print(json.dumps(build_index(rows, args.model_dir, args.index), ensure_ascii=False))
        else:
            samples = {row["id"]: row["url"] for row in read_json(Path("samples/pages.json"))}
            frozen, old = read_sets()
            validate_labels(frozen, rows, samples, ArchiveCheck(args.data_dir))
            index = VectorIndex(rows, args.model_dir, args.index)
            with args.output.open("x", encoding="utf-8") as output:
                compare(store, frozen + old, index, samples, rows, output)
            print(f"Top {LIMIT}; equal-weight RRF k={RRF_K}, depth={RRF_DEPTH}")


if __name__ == "__main__":
    main()
