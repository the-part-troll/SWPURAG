"""Run fixed-evidence admission experiments independently of live retrieval."""

import argparse
import json
from pathlib import Path

from .answer import synthesize
from .evaluate import ArchiveCheck
from .retrieval import explicit_subquestions
from .store import Store


def saved_question(path, question_id):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return next(row for row in rows if row["id"] == question_id and row["method"] == "natural")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--structured-partial", action="store_true",
                        help="replay the original incomplete Q2 evidence with per-question answers")
    args = parser.parse_args()
    reports = Path("reports")
    data = Path("data")
    baseline = (reports / "admissions-r3-baseline-prompt.txt").read_text(encoding="utf-8")
    # 直接重放旧评测的证据，排除当前检索结果变化的影响。
    q3 = saved_question(reports / "admissions-evaluation.jsonl", "Q3")
    q2 = saved_question(reports / "admissions-evaluation-r2.jsonl", "Q2")
    with Store(data / "corpus.sqlite3") as store:
        missing = next(row for row in store.current_chunks()
                       if row["url"].endswith("/8520.htm") and row["ordinal"] == 26)
    # 只替换一条证据，保留排名和引用编号，便于对照缺证据与补证据的回答。
    supplemented = [
        dict(missing, id=item["id"], rank=item["rank"], context=None)
        if item["rank"] == 5 else item for item in q2["evidence"]
    ]
    cases = [
        ("q3_original_evidence_previous_prompt", q3, q3["evidence"], {"system_prompt": baseline}),
        ("q3_original_evidence_scoped_prompt", q3, q3["evidence"], {}),
        ("q2_r2_evidence_scoped_prompt", q2, q2["evidence"], {}),
        ("q2_manual_replacement_scoped_prompt", q2, supplemented, {}),
    ]
    if args.structured_partial:
        cases = [("q2_r2_evidence_per_subquestion", q2, q2["evidence"], {
            "subquestions": explicit_subquestions(q2["question"]),
        })]
    archive = ArchiveCheck(data)
    with args.output.open("x", encoding="utf-8") as output:
        for name, source, evidence, prompt in cases:
            # 历史证据仍须能定位到原件，才能作为固定实验输入。
            if not all(archive.verify(item) for item in evidence):
                raise ValueError("Archive verification failed for " + name)
            answer = synthesize(source["question"], evidence, **prompt)
            output.write(json.dumps(dict(
                scenario=name, id=source["id"], question=source["question"], evidence=evidence,
                answer=answer, archive_verified=True,
            ), ensure_ascii=False) + "\n")
            output.flush()
            print("{} {}".format(name, answer["status"]), flush=True)


if __name__ == "__main__":
    main()
