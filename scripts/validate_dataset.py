#!/usr/bin/env python3
"""Validate JSONL syntax, IDs, clean prompt files, and basic privacy patterns."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]


def records(relative_path: str) -> Iterator[tuple[int, dict[str, Any]]]:
    with (ROOT / relative_path).open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            yield number, json.loads(line)


def text_values(value: Any, key: str | None = None) -> Iterator[str]:
    if key and (key == "sha256" or key.endswith("_id") or key == "id"):
        return
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child_key, child in value.items():
            yield from text_values(child, child_key)
    elif isinstance(value, list):
        for child in value:
            yield from text_values(child, key)


def main() -> int:
    errors: list[str] = []
    counts: Counter[str] = Counter()

    for path, id_key in [("data/single_turn.jsonl", "id"), ("data/multi_turn.jsonl", "id")]:
        seen = set()
        for line, record in records(path):
            counts[path] += 1
            record_id = record.get(id_key)
            if not record_id:
                errors.append(f"{path}:{line}: missing {id_key}")
            elif record_id in seen:
                errors.append(f"{path}:{line}: duplicate {id_key}={record_id}")
            seen.add(record_id)

    expected_prompts = {
        "doctor_agent": 5,
        "patient_agent": 1,
        "evaluation": 4,
    }
    allowed_empty = {
        "prompts/patient_agent/患者回复生成.txt",
    }
    prompt_paths = []
    for category, expected_count in expected_prompts.items():
        files = sorted((ROOT / "prompts" / category).glob("*.txt"))
        counts[f"prompts/{category}_files"] = len(files)
        counts[f"prompts/{category}_nonempty"] = sum(
            bool(path.read_text(encoding="utf-8").strip()) for path in files
        )
        if len(files) != expected_count:
            errors.append(f"prompts/{category}: expected {expected_count} files, found {len(files)}")
        for path in files:
            text = path.read_text(encoding="utf-8")
            prompt_paths.append(path)
            relative = path.relative_to(ROOT).as_posix()
            if not text.strip() and relative not in allowed_empty:
                errors.append(f"{path.relative_to(ROOT)}: empty prompt")
            if "prompt_" in text or "source_file" in text or "occurrence_id" in text:
                errors.append(f"{path.relative_to(ROOT)}: experiment metadata found in prompt text")

    privacy_patterns = {
        "mainland_china_mobile": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
        "mainland_china_id": re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)"),
        "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    }
    privacy_hits = Counter()
    for path in ["data/single_turn.jsonl", "data/multi_turn.jsonl"]:
        for _line, record in records(path):
            for text in text_values(record):
                for label, pattern in privacy_patterns.items():
                    privacy_hits[label] += len(pattern.findall(text))
    for path in prompt_paths:
        text = path.read_text(encoding="utf-8")
        for label, pattern in privacy_patterns.items():
            privacy_hits[label] += len(pattern.findall(text))

    report = {
        "valid": not errors,
        "record_counts": dict(counts),
        "privacy_pattern_hits": dict(privacy_hits),
        "errors": errors[:100],
        "notes": [
            "Zero regex hits do not replace manual disclosure review.",
            "Dates, medical details, organization names, and rare combinations require human review.",
        ],
    }
    report_path = ROOT / "metadata" / "independent_validation.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
