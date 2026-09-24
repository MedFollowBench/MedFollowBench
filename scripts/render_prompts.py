"""Render released prompts without leaking annotations to physician models."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISEASES = ("冠心病", "糖尿病", "脑梗", "颅脑损伤", "高血压")

def as_text(value):
    if value is None or value == "":
        return "未提供"
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

def disease_name(record):
    matches = [x for x in DISEASES if x in record["script_name"]]
    if len(matches) != 1:
        raise ValueError("Unknown or ambiguous script_name")
    return matches[0]

def template(relative):
    return (ROOT / "prompts" / relative).read_text(encoding="utf-8-sig")

def substitute(text, mapping):
    # One pass prevents input text that resembles a placeholder being interpreted.
    tokens = sorted(mapping, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(k) for k in tokens))
    missing = [k for k in tokens if k not in text]
    if missing:
        raise ValueError("Missing template placeholder(s): " + ", ".join(missing))
    return pattern.sub(lambda m: as_text(mapping[m[0]]), text)

def _two_dialog_fields(text, first, second):
    # Legacy templates use the same token for two different sections.
    if text.count("{{dialog}}") != 2:
        raise ValueError("Expected two dialog placeholders")
    before, between, after = text.split("{{dialog}}")
    return before + first + between + second + after

def physician_prompt(record, history=None, current_patient_reply=None):
    """Render the next-response prompt. No target_information or labels are read."""
    if history is None or current_patient_reply is None:
        components = record.get("prompt_components")
        if not components:
            raise ValueError("For a session, supply history and current_patient_reply")
        if history is None:
            history = components["history"]
        if current_patient_reply is None:
            current_patient_reply = components["current_patient_reply"]
    text = template(Path("doctor_agent") / (disease_name(record) + ".txt"))
    text = _two_dialog_fields(text, "{{history}}", "{{current_reply}}")
    # Use the record's own protocol, not a potentially different fixed example.
    pattern = r"(## 流程要求：\s*).*?(?=## 对话历史：)"
    text, n = re.subn(pattern, lambda m: m[1] + "{{protocol}}\n\n", text, flags=re.S)
    if n != 1:
        raise ValueError("Protocol section not found")
    return substitute(text, {"{{patient_profile}}":record.get("patient_profile"), "{{protocol}}":record["flow_requirements"], "{{history}}":history or "无", "{{current_reply}}":current_patient_reply})

def turn_evaluator_prompt(record, physician_response, metric):
    if metric not in ("hcc", "ia"):
        raise ValueError("metric must be hcc or ia")
    filename = "内容质量三维度.txt" if metric == "hcc" else "提问合理性.txt"
    text = template(Path("evaluation") / filename)
    if metric == "hcc":
        text = _two_dialog_fields(text, "{{history}}", "{{model_output}}")
    else:
        text = text.replace("{{dialog}}", "{{history}}")
    return substitute(text, {"{{flow_requirements}}":record["flow_requirements"], "{{patient_profile}}":record.get("patient_profile"), "{{history}}":record["conversation"]["raw_text"], "{{model_output}}":physician_response})

def patient_prompt(record, history):
    """Simulator-only prompt; never send this prompt to a physician model."""
    state = {"patient_profile":record.get("patient_profile"), "target_information":record["target_information"]}
    return substitute(template(Path("patient_agent") / "患者回复生成.txt"), {"{{dialog}}":history or "无", "{{aim}}":state})

def pcc_prompt(record, full_dialogue):
    return substitute(template(Path("evaluation") / "多轮流程完整性.txt"), {"{患者画像}":record.get("patient_profile"), "{信息节点}":record["information_nodes"], "{精细流程要求}":record["detailed_flow_requirements"], "{完整对话}":full_dialogue})
