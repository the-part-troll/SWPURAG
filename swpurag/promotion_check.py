"""Check the curated corpus promotion without writing to any SQLite database."""

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from .evaluate import read_json
from .store import Store


DISCOVERY = Path("samples/discovery")
DEFAULT_REFERENCE = Path("reports/expansion-after.jsonl")
TABLES = ("sources", "documents", "versions", "chunks", "attempts")
OLD_COUNTS = {"sources": 8, "documents": 13, "versions": 13, "chunks": 747, "attempts": 27}
PROMOTED_COUNTS = {"sources": 8, "documents": 15, "versions": 15, "chunks": 813, "attempts": 29}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def open_readonly(path):
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def rows_by_id(db, table):
    return {row["id"]: dict(row) for row in db.execute(f"SELECT * FROM {table}")}


def current_corpus(db):
    # Use the normal read path without running the Store constructor's migrations.
    store = Store.__new__(Store)
    store.db = db
    local_fields = {"chunk_id", "version_id", "document_id", "latest_success_fetched_at"}
    return {(row["url"], row["ordinal"]): {key: value for key, value in row.items() if key not in local_fields}
            for row in store.current_chunks()}


def check_databases(backup, candidate, validation):
    for label, db in (("backup", backup), ("candidate", candidate), ("validation", validation)):
        require([row[0] for row in db.execute("PRAGMA integrity_check")] == ["ok"],
                f"SQLite integrity check failed for {label}")
        require(not db.execute("PRAGMA foreign_key_check").fetchone(),
                f"SQLite foreign-key check failed for {label}")

    old = {table: rows_by_id(backup, table) for table in TABLES}
    new = {table: rows_by_id(candidate, table) for table in TABLES}
    require({table: len(rows) for table, rows in old.items()} == OLD_COUNTS,
            "Backup is not the expected pre-promotion corpus")
    require({table: len(rows) for table, rows in new.items()} == PROMOTED_COUNTS,
            "Candidate counts differ from the expected promoted corpus")
    for table, rows in old.items():
        require(all(new[table].get(key) == row for key, row in rows.items()),
                f"Candidate changed an existing {table} row")

    expected_urls = {page["url"] for page in read_json(DISCOVERY / "pages.json")}
    receipts = {row["url"]: row for row in read_json(DISCOVERY / "captures.json")}
    additions = [row for key, row in new["attempts"].items() if key not in old["attempts"]]
    require({row["url"] for row in additions} == expected_urls,
            "The added attempts do not correspond to both archived notices")
    documents = {row["url"]: row for row in new["documents"].values()}
    for row in additions:
        url = row["url"]
        receipt = receipts[url]
        require(row["status"] == "new" and row["error"] is None
                and row["version_id"] == documents[url]["current_version_id"],
                f"Appended attempt is not a successful current version for {url}")
        require(all(row[key] == receipt[key] for key in ("final_url", "fetched_at", "raw_sha256", "raw_path")),
                f"Appended attempt does not match the archived receipt for {url}")

    current = current_corpus(candidate)
    reference = current_corpus(validation)
    require(len(current) == PROMOTED_COUNTS["chunks"] and len({key[0] for key in current}) == 15,
            "Candidate does not expose all current documents and blocks")
    require(current.keys() == reference.keys(), "Candidate and validation current block positions differ")
    for key, row in current.items():
        require(row == reference[key], f"Candidate and validation corpus differ at {key}")
    return {**PROMOTED_COUNTS, "preserved_attempts": len(old["attempts"]),
            "archive_additions": sorted(expected_urls), "matching_current_blocks": len(current)}


def read_results(path):
    with path.open(encoding="utf-8-sig") as stream:
        records = [json.loads(line) for line in stream]
    result = {(row["suite"], row["id"]): row for row in records}
    require(len(records) == len(result) == 82, f"Expected 82 unique records in {path}")
    return result


def evidence_position(hit):
    return hit["url"], hit["raw_sha256"], json.dumps(hit["locator"], sort_keys=True)


def ranks_as_positions(row, ranks):
    by_rank = {hit["rank"]: evidence_position(hit) for hit in row["top5"]}
    return {by_rank[rank] for rank in ranks}


def check_results(results, reference):
    actual = read_results(results)
    expected = read_results(reference)
    require(actual.keys() == expected.keys(), "Candidate questions differ from the accepted freeze")
    order_changes = 0
    scored = 0
    complete = 0
    for key, row in actual.items():
        prior = expected[key]
        require(row["question"] == prior["question"] and row["method"] == prior["method"] == "lexical"
                and row["expected_status"] == prior["expected_status"], f"Question or method differs for {key}")
        require(len(row["top5"]) <= 5 and row["archived_top5_verified"], f"Top 5 verification failed for {key}")
        for field in ("retrieval_status", "topic_statuses", "required_groups_in_candidate_pool",
                      "any_required", "all_required", "wrong_scope_overlay_candidates"):
            require(row.get(field) == prior.get(field), f"{field} differs for {key}")
        require([ranks_as_positions(row, ranks) for ranks in row["required_group_ranks"]]
                == [ranks_as_positions(prior, ranks) for ranks in prior["required_group_ranks"]],
                f"Necessary evidence positions differ for {key}")
        for field in ("wrong_scope_ranks", "wrong_scope_overlay_ranks"):
            require(ranks_as_positions(row, row.get(field, ())) == ranks_as_positions(prior, prior.get(field, ())),
                    f"{field} positions differ for {key}")
        order_changes += ([evidence_position(hit) for hit in row["top5"]]
                          != [evidence_position(hit) for hit in prior["top5"]])
        scored += row["all_required"] is not None
        complete += row["all_required"] is True

    h08 = next(row for row in actual.values() if row["id"] == "H08")
    require(h08["required_group_ranks"] == [[1], []] and h08["all_required"] is False,
            "H08 charging-table header was counted in the Top 5")
    header_ids = h08["context_group_ids"][1]
    require(any(hit["id"] in header_ids and hit["rank"] is None and hit["context"] == "table_header"
                and hit["locator"].get("paragraph") == 105
                for hit in h08["context_evidence"]), "H08 charging-table header is missing from answer context")
    return {"records_checked": len(actual), "complete": complete, "scored": scored,
            "top5_order_changes": order_changes, "h08_table_header_context": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    args = parser.parse_args()
    try:
        with (closing(open_readonly(args.backup)) as backup,
              closing(open_readonly(args.candidate)) as candidate,
              closing(open_readonly(args.validation)) as validation):
            contents = check_databases(backup, candidate, validation)
        retrieval = check_results(args.results, args.reference)
    except (OSError, sqlite3.Error, KeyError, ValueError) as error:
        parser.exit(1, f"Promotion check failed: {error}\n")
    print(json.dumps({"database": contents, "retrieval": retrieval}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
