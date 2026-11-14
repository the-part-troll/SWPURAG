"""Build and check an isolated discovery corpus from archived captures."""

import argparse
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from .capture import archive, validate_url
from .ingest import import_capture
from .store import Store


DATA = Path("data")
LOCAL = DATA / "local"
CURATED = Path("samples")
DISCOVERED = CURATED / "discovery"
COUNTS = ("sources", "documents", "versions", "chunks")
HISTORY_TABLES = ("sources", "documents", "versions", "chunks", "attempts")


def read_list(path):
    rows = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(rows, list):
        raise ValueError(f"Expected a JSON list in {path}")
    return rows


def read_inputs(directory):
    samples = read_list(directory / "pages.json")
    receipts = read_list(directory / "captures.json")
    by_url = {receipt["url"]: receipt for receipt in receipts}
    if (len({sample["id"] for sample in samples}) != len(samples)
            or len({sample["url"] for sample in samples}) != len(samples)
            or len(by_url) != len(receipts)):
        raise ValueError(f"Duplicate sample or receipt in {directory}")
    for sample in samples:
        validate_url(sample)
        if sample["url"] not in by_url:
            raise ValueError(f"Missing capture receipt for {sample['id']}")
    return [(sample, by_url[sample["url"]]) for sample in samples]


def record(output, phase, **values):
    output.write(json.dumps(dict(phase=phase, **values), ensure_ascii=False) + "\n")
    output.flush()


def checked_imports(store, pairs, output, phase, expected):
    for sample, receipt in pairs:
        result = import_capture(store, sample, receipt, DATA)
        fields = ("url", "fetched_at", "raw_sha256", "raw_path", "http_status")
        fields_for_sample = ("unit", "page_type", "admission_year", "role", "audience",
                             "campus", "building", "notice_kind", "effective_from", "effective_to", "service")
        metadata = {key: sample[key] for key in fields_for_sample if key in sample}
        if result["status"] != "failed":
            version = store.db.execute(
                "SELECT title, published_at, content_sha256 FROM versions WHERE id = ?", (result["version_id"],)
            ).fetchone()
            metadata.update(dict(version))
        record(output, phase, sample=sample["id"], receipt={key: receipt.get(key) for key in fields},
               metadata=metadata, result=result)
        if result["status"] != expected:
            raise ValueError(f"{sample['id']} returned {result['status']}; expected {expected}")


def compare_counts(before, after):
    if any(before[name] != after[name] for name in COUNTS):
        raise ValueError("The validation unexpectedly changed effective corpus counts")


def validate_failures(store, sample, receipt, output):
    # 在临时验证库副本里记录失败和合成原件，真实评测库只含公开原件。
    with TemporaryDirectory(prefix="discovery-failure-", dir=LOCAL) as work:
        work = Path(work)
        with Store(work / "failure.sqlite3") as isolated:
            store.db.backup(isolated.db)
            baseline = isolated.stats()
            rows = [row for row in isolated.current_chunks() if row["url"] == sample["url"]]
            if not rows:
                raise ValueError("Failure probe requires a current archived HTML version")
            instant = datetime.fromisoformat(receipt["fetched_at"])
            access = {"url": sample["url"], "final_url": sample["url"], "http_status": 403,
                      "fetched_at": (instant + timedelta(seconds=1)).isoformat(),
                      "error": "HTTP 403（合成的离线验证输入）"}
            invalid_html = b"<html><head><title>Synthetic fixture</title></head><body><p>Wrong container</p></body></html>"
            extraction = {**access, "http_status": 200, "charset": "utf-8",
                          "fetched_at": (instant + timedelta(seconds=2)).isoformat(), **archive(work, invalid_html)}
            del extraction["error"]
            for phase, probe in (("simulated_access_failure", access), ("simulated_extraction_failure", extraction)):
                result = import_capture(isolated, sample, probe, work)
                retained = rows == [row for row in isolated.current_chunks() if row["url"] == sample["url"]]
                record(output, phase, sample=sample["id"], receipt=probe, result=result,
                       current_version_id=rows[0]["version_id"], retained=retained, stats=isolated.stats())
                if result["status"] != "failed" or not retained:
                    raise ValueError(f"Archive retention failed for {phase}")
            after = isolated.stats()
            compare_counts(baseline, after)
            if (after["failed_attempts"] - baseline["failed_attempts"] != 2
                    or isolated.db.execute("PRAGMA foreign_key_check").fetchall()):
                raise ValueError("Unexpected result while checking failed import attempts")


def database_rows(store):
    return {table: [tuple(row) for row in store.db.execute(f"SELECT * FROM {table} ORDER BY id")]
            for table in HISTORY_TABLES}


def verify_history(store, baseline):
    for table, rows in database_rows(store).items():
        if rows[:len(baseline[table])] != baseline[table]:
            raise ValueError(f"The snapshot's existing {table} rows changed")


def verify_integrity(store):
    if ([row[0] for row in store.db.execute("PRAGMA integrity_check")] != ["ok"]
            or store.db.execute("PRAGMA foreign_key_check").fetchall()):
        raise ValueError("SQLite integrity check failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=LOCAL / "discovery.sqlite3")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--records", type=Path, default=DISCOVERED, help="directory with pages.json and captures.json")
    parser.add_argument("--snapshot", type=Path, help="read-only starting database for incremental validation")
    args = parser.parse_args()
    base = [] if args.snapshot else read_inputs(CURATED)
    additions = read_inputs(args.records)
    db = args.db.resolve()
    if db.parent != LOCAL.resolve() or db == (DATA / "corpus.sqlite3").resolve():
        parser.error("the validation database must be a new file under data/local/")
    if args.snapshot and not args.snapshot.is_file():
        parser.error("the starting database does not exist")
    if args.output.resolve() in {db, (DATA / "corpus.sqlite3").resolve()} or db.exists():
        parser.error("choose separate, unused validation database and output paths")
    LOCAL.mkdir(parents=True, exist_ok=True)
    # 独占创建数据库和日志，保留已做的验证结果及默认数据库。
    with args.output.open("x", encoding="utf-8", newline="\n") as output:
        db.open("xb").close()
        with Store(db) as store:
            if args.snapshot:
                with closing(sqlite3.connect(args.snapshot.resolve().as_uri() + "?mode=ro", uri=True)) as source:
                    source.backup(store.db)
            checked_imports(store, base, output, "base_import", "new")
            initial = store.stats()
            history = database_rows(store)
            original_urls = {row[0] for row in store.db.execute("SELECT url FROM documents")}
            if original_urls & {sample["url"] for sample, _ in additions}:
                raise ValueError("new manifest duplicates a URL in the starting database")
            checked_imports(store, additions, output, "discovery_import", "new")
            built = store.stats()
            checked_imports(store, base + additions, output, "offline_replay", "unchanged")
            replayed = store.stats()
            compare_counts(built, replayed)
            if (built["documents"] - initial["documents"] != len(additions)
                    or replayed["attempts"] - built["attempts"] != len(base) + len(additions)):
                raise ValueError("Unexpected rebuild or replay counts")
            for sample, receipt in additions:
                if sample.get("format", "html") == "html":
                    validate_failures(store, sample, receipt, output)
            verify_history(store, history)
            verify_integrity(store)
            record(output, "summary", base=initial, after_import=built, after_replay=replayed,
                   admitted=[sample["id"] for sample, _ in additions], database=str(args.db),
                   snapshot=str(args.snapshot) if args.snapshot else None, starting_rows_retained=True,
                   integrity_check="ok", foreign_key_check="ok")
    print("Saved", args.output)


if __name__ == "__main__":
    main()
