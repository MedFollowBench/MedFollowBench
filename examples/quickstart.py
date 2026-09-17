#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_records(path: Path):
    """逐行读取，每行返回一个样本。"""
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: JSON 格式错误") from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=["single_turn", "multi_turn"], default="single_turn")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    counts = Counter()
    first = None
    for record in read_records(args.data_dir / f"{args.task}.jsonl"):
        counts[record["script_name"]] += 1
        if first is None:
            first = record
    print(json.dumps({"task": args.task, "records": sum(counts.values()),
                      "script_counts": dict(counts)}, ensure_ascii=False, indent=2))
    if first is None:
        return
    if args.task == "single_turn":
        example = {"id": first["id"], "messages": first["conversation"]["messages"],
                   "main_behavior_type": first["main_behavior_type"]}
    else:
        example = {key: first[key] for key in ["id", "patient_profile", "information_nodes",
                                              "detailed_flow_requirements"]}
    print(json.dumps(example, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
