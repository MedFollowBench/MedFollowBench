"""Validate release counts, quotas, field types, boundaries and basic PII patterns."""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISEASES = ("冠心病", "糖尿病", "脑梗", "颅脑损伤", "高血压")
ASR_TYPES = ("Text Normalization Errors", "Spoken ellipsis", "Homophone Error")
PII = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)|(?<!\d)\d{17}[\dXx](?!\d)|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

def load(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]

def text_values(value, key=""):
    if key == "id":
        return
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k,v in value.items():
            yield from text_values(v, k)
    elif isinstance(value, list):
        for v in value:
            yield from text_values(v)

def disease(record):
    found = [x for x in DISEASES if x in record["script_name"]]
    if len(found) != 1:
        raise ValueError("Unknown script_name: " + record["id"])
    return found[0]

def require(condition, message):
    if not condition:
        raise ValueError(message)

def validate(root=ROOT):
    summary = {}
    all_data = {}
    for filename, expected, task in (("single_turn.jsonl",2169,"single_turn_next_response"),("single_turn_asr.jsonl",600,"single_turn_next_response"),("multi_turn.jsonl",500,"multi_turn_dialogue_simulation")):
        path = root / "data" / filename
        records = load(path)
        require(len(records) == expected, f"{filename}: expected {expected}, got {len(records)}")
        require(len({r["id"] for r in records}) == expected, filename + ": duplicate ids")
        diseases = Counter()
        for row in records:
            require(row.get("task") == task, "Unexpected task: " + row["id"])
            require(bool(row.get("flow_requirements")), "Empty protocol: " + row["id"])
            diseases[disease(row)] += 1
            require(not any(PII.search(s) for s in text_values(row)), "Possible direct identifier: " + row["id"])
            if task == "single_turn_next_response":
                conv = row["conversation"]
                msgs = conv["messages"]
                require(bool(msgs) and msgs[-1]["role"] == "user", "No terminal patient response: " + row["id"])
                require(conv["message_count"] == len(msgs), "Wrong message_count: " + row["id"])
                require(all(m["role"] in ("assistant","user") and isinstance(m["content"],str) and m["content"].strip() for m in msgs), "Invalid message: " + row["id"])
                require(msgs[-1]["content"] == row["prompt_components"]["current_patient_reply"], "Current response mismatch: " + row["id"])
                require("target_information" not in row, "Session target in turn-level record: " + row["id"])
            else:
                require(isinstance(row.get("target_information"),dict) and bool(row["target_information"]), "Missing target information: " + row["id"])
                require(bool(row.get("information_nodes")) and bool(row.get("detailed_flow_requirements")), "Missing session protocol: " + row["id"])
        summary[filename] = {"records":len(records),"disease_counts":dict(diseases),"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
        all_data[filename] = records
    asr = all_data["single_turn_asr.jsonl"]
    quota = Counter((r["asr_type"],disease(r)) for r in asr)
    require(set(r["asr_type"] for r in asr) == set(ASR_TYPES), "Unexpected ASR labels")
    require(len(quota) == 15 and all(x == 40 for x in quota.values()), "ASR disease quotas must be 40 per cell")
    main = all_data["single_turn.jsonl"]
    mapping = {"配合型回答":"Cooperative","偏离型回答":"Non-aligned","阻抗型回答":"Non-aligned","提问型回答":"Inquisitive"}
    behaviors = Counter(mapping[r["main_behavior_type"]] for r in main)
    require(behaviors == {"Cooperative":1000,"Non-aligned":726,"Inquisitive":443}, "Main behavior counts differ")
    sessions = all_data["multi_turn.jsonl"]
    require(Counter(disease(r) for r in sessions) == {d:100 for d in DISEASES}, "Session disease counts differ")
    require(sum(bool(r["patient_profile"]) for r in sessions) == 250, "Session profile availability differs")
    summary["asr_counts"] = dict(Counter(r["asr_type"] for r in asr))
    summary["behavior_counts"] = dict(behaviors)
    # This scanner is a regression check, not proof of complete anonymization.
    return summary

if __name__ == "__main__":
    print(json.dumps(validate(), ensure_ascii=False, indent=2))
