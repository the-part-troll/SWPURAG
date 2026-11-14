"""Rebuild and check the independent admissions discovery corpus from archives."""

import argparse
import json
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
        metadata = {key: sample.get(key) for key in ("unit", "page_type", "admission_year", "role", "audience")}
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=LOCAL / "discovery.sqlite3")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base, additions = read_inputs(CURATED), read_inputs(DISCOVERED)
    if {sample["url"] for sample, _ in base} & {sample["url"] for sample, _ in additions}:
        parser.error("new manifest duplicates a curated URL")
    db = args.db.resolve()
    if db.parent != LOCAL.resolve() or db == (DATA / "corpus.sqlite3").resolve():
        parser.error("the validation database must be a new file under data/local/")
    if args.output.resolve() in {db, (DATA / "corpus.sqlite3").resolve()} or db.exists():
        parser.error("choose separate, unused validation database and output paths")
    LOCAL.mkdir(parents=True, exist_ok=True)
    # 独占创建数据库和日志，保留已做的验证结果及默认数据库。
    with args.output.open("x", encoding="utf-8", newline="\n") as output:
        db.open("xb").close()
        with Store(db) as store:
            checked_imports(store, base, output, "base_import", "new")
            initial = store.stats()
            checked_imports(store, additions, output, "discovery_import", "new")
            built = store.stats()
            checked_imports(store, base + additions, output, "offline_replay", "unchanged")
            replayed = store.stats()
            compare_counts(built, replayed)
            if (built["documents"] - initial["documents"] != len(additions)
                    or replayed["attempts"] - built["attempts"] != len(base) + len(additions)):
                raise ValueError("Unexpected rebuild or replay counts")
            sample, receipt = next(pair for pair in additions + base if pair[0].get("format", "html") == "html")
            validate_failures(store, sample, receipt, output)
            record(output, "summary", base=initial, after_import=built, after_replay=replayed,
                   admitted=[sample["id"] for sample, _ in additions], database=str(args.db))
    print("Saved", args.output)


if __name__ == "__main__":
    main()
