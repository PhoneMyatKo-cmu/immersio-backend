"""Aggregate LLM-judge results pasted from one or more chats.

Workflow:
  1. After judging each chunk in a separate chat, copy the judge's per-case
     output (the "Case N: ..." blocks) into a single text file, e.g.
     evals/output/judgments.txt. Order and chunk boundaries do not matter;
     just don't paste the same case twice.
  2. Run:  python -m evals.aggregate_judgments evals/output/judgments.txt

It parses each case by regex (tolerant of axis ordering and line breaks),
then prints per-axis means, the overall mean, mismatch-flag accuracy, and the
lowest-overall cases across the WHOLE set.
"""

import re
import sys
from collections import defaultdict

AXES = [
    "contextual_correctness",
    "faithfulness",
    "register_accuracy",
    "plain_language",
    "example_quality",
    "confidence_calibration",
    "overall",
]


def parse(text: str) -> list[dict]:
    # Split into per-case chunks starting at each "Case <id>".
    parts = re.split(r"(?im)^\s*case\s+(\d+)\s*:", text)
    # re.split with one capture group yields: [pre, id1, body1, id2, body2, ...]
    cases = {}
    for i in range(1, len(parts), 2):
        case_id = int(parts[i])
        body = parts[i + 1]
        record = {"case_id": case_id}
        for axis in AXES:
            m = re.search(rf"{axis}\s*:\s*([1-5])\b", body, re.IGNORECASE)
            if m:
                record[axis] = int(m.group(1))
        mf = re.search(r"mismatch_flag_correct\s*:\s*(true|false)", body, re.IGNORECASE)
        if mf:
            record["mismatch_flag_correct"] = mf.group(1).lower() == "true"
        cases[case_id] = record  # dedupe by id: last paste of a case wins
    return list(cases.values())


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python -m evals.aggregate_judgments <judgments.txt>")
        return
    with open(sys.argv[1], encoding="utf-8") as f:
        cases = parse(f.read())

    if not cases:
        print("No cases parsed. Check the file has 'Case N:' blocks.")
        return

    print(f"Parsed {len(cases)} unique cases.\n")

    sums = defaultdict(float)
    counts = defaultdict(int)
    for c in cases:
        for axis in AXES:
            if axis in c:
                sums[axis] += c[axis]
                counts[axis] += 1

    print("Per-axis means:")
    for axis in AXES:
        if counts[axis]:
            print(f"  {axis:24s} {sums[axis] / counts[axis]:.2f}  (n={counts[axis]})")
        else:
            print(f"  {axis:24s} (no scores parsed)")

    mf_vals = [c["mismatch_flag_correct"] for c in cases if "mismatch_flag_correct" in c]
    if mf_vals:
        correct = sum(mf_vals)
        print(f"\nmismatch_flag correct: {correct}/{len(mf_vals)} ({100*correct/len(mf_vals):.0f}%)")

    graded = [c for c in cases if "overall" in c]
    lowest = sorted(graded, key=lambda c: c["overall"])[:5]
    print("\nLowest-overall cases:")
    for c in lowest:
        print(f"  Case {c['case_id']}: overall {c['overall']}")

    # Flag any case missing scores so you can spot bad pastes.
    incomplete = [c["case_id"] for c in cases if any(a not in c for a in AXES)]
    if incomplete:
        print(f"\nWARNING: cases missing one or more axis scores: {sorted(incomplete)}")


if __name__ == "__main__":
    main()
