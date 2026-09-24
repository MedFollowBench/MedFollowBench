"""Load all release components and render one turn prompt locally (no API calls)."""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from render_prompts import physician_prompt, turn_evaluator_prompt, patient_prompt

def load(name):
    with (ROOT / "data" / name).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]

if __name__ == "__main__":
    single = load("single_turn.jsonl")
    sessions = load("multi_turn.jsonl")
    asr = load("single_turn_asr.jsonl")
    prompt = physician_prompt(single[0])
    judge = turn_evaluator_prompt(single[0], "待评测的医生回复", "ia")
    simulator = patient_prompt(sessions[0], "医生：您好，请问是您本人吗？")
    print(json.dumps({"single_turn":len(single), "sessions":len(sessions), "spoken_asr":len(asr), "asr_types":dict(Counter(x["asr_type"] for x in asr)), "rendered_prompt_characters":{"physician":len(prompt), "judge":len(judge), "simulator":len(simulator)}}, ensure_ascii=False, indent=2))
