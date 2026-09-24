"""Aggregate three saved judge results per case, without network calls.

Input JSONL: {"id": "...", "judges": [judge_output_1, judge_output_2, judge_output_3]}.
Usage: python scripts/score_judgments.py hcc judgments.jsonl
Judges must be independent outputs for the same metric, case, and model response.
"""
import argparse
import json
import re

HCC_KEYS = ("内容正确性得分", "结合画像能力得分", "表达合理性得分")

def rating(value):
    if isinstance(value, bool):
        raise ValueError("A boolean is not a rubric rating")
    if isinstance(value, int) and value in (1,2,3):
        return value
    if isinstance(value, str):
        match = re.fullmatch(r"\s*([123])\s*分?\s*", value)
        if match:
            return int(match[1])
    raise ValueError("Expected a single 1/2/3 rating")

def judge_pass(metric, output):
    if metric == "hcc":
        return all(rating(output[k]) == 3 for k in HCC_KEYS)
    if metric == "ia":
        return rating(output["提问合理性得分"]) == 3
    if metric == "pcc":
        value = output["是否有遗漏"]
        if value not in ("有", "没有"):
            raise ValueError("PCC requires 是否有遗漏 to be 有 or 没有")
        return value == "没有"
    raise ValueError("Unknown metric")

def aggregate_case(metric, judges):
    if len(judges) != 3:
        raise ValueError("Exactly three judge outputs are required")
    votes = sum(judge_pass(metric, j) for j in judges)
    return votes == 3 if metric == "pcc" else votes >= 2

def score(metric, cases):
    if not cases:
        raise ValueError("No cases provided")
    if len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Duplicate case ids; evaluate each physician model separately")
    passed = sum(aggregate_case(metric, c["judges"]) for c in cases)
    return {"metric":metric.upper(),"cases":len(cases),"passed":passed,"score_percent":100.0 * passed / len(cases)}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metric", choices=("hcc","ia","pcc"))
    parser.add_argument("judgments")
    args = parser.parse_args()
    with open(args.judgments, encoding="utf-8") as stream:
        cases = [json.loads(line) for line in stream if line.strip()]
    print(json.dumps(score(args.metric,cases), ensure_ascii=False, indent=2))
