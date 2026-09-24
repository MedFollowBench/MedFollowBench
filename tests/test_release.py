import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from render_prompts import physician_prompt, turn_evaluator_prompt, patient_prompt, pcc_prompt
from score_judgments import aggregate_case, rating, HCC_KEYS

def first(name):
    with (ROOT / "data" / name).open(encoding="utf-8") as f:
        return json.loads(next(f))

class PromptTests(unittest.TestCase):
    def setUp(self):
        self.turn = first("single_turn.jsonl")
        self.session = first("multi_turn.jsonl")

    def test_physician_no_reference_leakage(self):
        case = copy.deepcopy(self.turn)
        case["target_information"] = {"private":"HIDDEN_TARGET_SENTINEL"}
        case["patient_behavior_label"] = {"private":"HIDDEN_LABEL_SENTINEL"}
        text = physician_prompt(case)
        self.assertNotIn("HIDDEN_TARGET_SENTINEL", text)
        self.assertNotIn("HIDDEN_LABEL_SENTINEL", text)
        self.assertIn(case["flow_requirements"],text)

    def test_split_history_current_reply(self):
        text = physician_prompt(self.turn, "HISTORY_SENTINEL", "CURRENT_SENTINEL")
        self.assertEqual(text.count("HISTORY_SENTINEL"),1)
        self.assertEqual(text.count("CURRENT_SENTINEL"),1)

    def test_evaluators(self):
        for metric in ("hcc","ia"):
            text = turn_evaluator_prompt(self.turn,"RESPONSE_SENTINEL",metric)
            self.assertEqual(text.count("RESPONSE_SENTINEL"),1)
            self.assertNotIn("{{dialog}}",text)
        text = pcc_prompt(self.session,"SESSION_SENTINEL")
        self.assertEqual(text.count("SESSION_SENTINEL"),1)

    def test_patient_private_state(self):
        case = copy.deepcopy(self.session)
        case["target_information"] = {"private":"TARGET_SENTINEL"}
        self.assertIn("TARGET_SENTINEL",patient_prompt(case,"HISTORY"))

class ScoringTests(unittest.TestCase):
    def test_hcc_majority(self):
        good = {k:3 for k in HCC_KEYS}
        bad = {k:2 for k in HCC_KEYS}
        self.assertTrue(aggregate_case("hcc",[good,good,bad]))
        self.assertFalse(aggregate_case("hcc",[good,bad,bad]))

    def test_ia_majority(self):
        self.assertTrue(aggregate_case("ia",[{"提问合理性得分":x} for x in ("3分",3,2)]))

    def test_pcc_unanimous(self):
        good = {"是否有遗漏":"没有"}
        bad = {"是否有遗漏":"有"}
        self.assertTrue(aggregate_case("pcc",[good]*3))
        self.assertFalse(aggregate_case("pcc",[good,good,bad]))

    def test_invalid_ratings_fail(self):
        for value in (True,"1/2/3分",0,4,None):
            with self.assertRaises(ValueError):
                rating(value)

if __name__ == "__main__":
    unittest.main()
