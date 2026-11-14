"""Run the frozen expansion questions through the actual ask CLI and verify citations."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from .evaluate import ArchiveCheck, read_json
from .hybrid_eval import read_sets
from .routing_eval import DISCOVERY, DISCOVERY_MANIFESTS, EXPANSION, EXPANSION_SHA256


QUESTION_IDS = ("A1", "A2", "N05", "N06", "N07", "E04", "Q6", "N04")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--only", choices=QUESTION_IDS, nargs="+")
    args = parser.parse_args()
    if not args.db.is_file() or args.db.resolve() == Path("data/corpus.sqlite3").resolve():
        parser.error("select the existing isolated validation database")
    if hashlib.sha256(EXPANSION.read_bytes().replace(b"\r\n", b"\n")).hexdigest() != EXPANSION_SHA256:
        parser.error("expansion file differs from the frozen questions")
    _, old = read_sets()
    questions = {row["id"]: row["question"] for row in old + read_json(DISCOVERY) + read_json(EXPANSION)}
    archive = ArchiveCheck(Path("data"), extra_manifests=DISCOVERY_MANIFESTS)
    with args.output.open("x", encoding="utf-8", newline="\n") as output:
        for qid in dict.fromkeys(args.only or QUESTION_IDS):
            process = subprocess.run(
                [sys.executable, "-B", "-m", "swpurag", "--db", str(args.db), "ask", questions[qid], "--json"],
                capture_output=True, encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8"),
            )
            if process.returncode not in (0, 1) or not process.stdout.strip():
                raise RuntimeError(f"{qid}: ask CLI failed with exit code {process.returncode}")
            result = json.loads(process.stdout)
            referenced = {citation["id"] for claim in result["claims"] for citation in claim["citations"]}
            evidence = {row["id"]: row for row in result["evidence"]}
            # CLI 已检查摘录归属，此处从存档重解析并复核被引用的段落位置。
            checks = {key: key in evidence and archive.verify(evidence[key]) for key in sorted(referenced)}
            output.write(json.dumps(dict(id=qid, citation_checks=checks, **result), ensure_ascii=False) + "\n")
            output.flush()
            print(qid, result["status"], checks, flush=True)


if __name__ == "__main__":
    main()
