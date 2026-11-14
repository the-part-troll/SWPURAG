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
from .routing_eval import (DISCOVERY, DISCOVERY_MANIFESTS, EXPANSION, EXPANSION_SHA256,
                           LIBRARY_DISCOVERY_SHA256)


QUESTION_IDS = ("A1", "A2", "N05", "N06", "N07", "E04", "Q6", "N04")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--only", nargs="+")
    parser.add_argument("--library-discovery", type=Path, help="use the frozen library questions and archive manifests")
    parser.add_argument("--baseline-package", type=Path, help="parent directory of the trusted historical swpurag package")
    args = parser.parse_args()
    if not args.db.is_file() or args.db.resolve() == Path("data/corpus.sqlite3").resolve():
        parser.error("select the existing isolated validation database")
    manifests = list(DISCOVERY_MANIFESTS)
    if args.library_discovery:
        directory = args.library_discovery
        path, digest = directory / "acceptance.json", LIBRARY_DISCOVERY_SHA256
        manifests.append((directory / "pages.json", directory / "captures.json"))
        questions = read_json(path)
        allowed = tuple(row["id"] for row in questions)
    else:
        path, digest = EXPANSION, EXPANSION_SHA256
        _, old = read_sets()
        questions = old + read_json(DISCOVERY) + read_json(EXPANSION)
        allowed = QUESTION_IDS
    if hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() != digest:
        parser.error(f"{path} differs from the frozen questions")
    if args.only and set(args.only) - set(allowed):
        parser.error("choose question IDs from " + ", ".join(allowed))
    questions = {row["id"]: row["question"] for row in questions}
    archive = ArchiveCheck(Path("data"), extra_manifests=manifests)
    cli = [sys.executable, "-B", "-m", "swpurag"]
    if args.baseline_package:
        directory = args.baseline_package.resolve()
        if not (directory / "swpurag" / "__main__.py").is_file():
            parser.error("the baseline package is missing swpurag/__main__.py")
        # 加载历史包，工作目录仍指向当前项目的存档与配置。
        launcher = ("import runpy, sys; sys.path.insert(0, sys.argv.pop(1)); "
                    "runpy.run_module('swpurag', run_name='__main__', alter_sys=True)")
        cli = [sys.executable, "-B", "-c", launcher, str(directory)]
    with args.output.open("x", encoding="utf-8", newline="\n") as output:
        for qid in dict.fromkeys(args.only or allowed):
            process = subprocess.run(
                [*cli, "--db", str(args.db), "ask", questions[qid], "--json"],
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
