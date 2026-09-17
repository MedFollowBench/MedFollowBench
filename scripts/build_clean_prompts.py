#!/usr/bin/env python3
"""Create compact, clean prompt templates without experiment metadata."""

from __future__ import annotations

import json
from pathlib import Path

from extract_dataset import iter_json_objects, iter_table


DERIVED_MULTI_TURN_EVALUATION_PROMPT = """现在，这是一个医疗外呼随访的多轮对话流程完整性评测任务。请根据患者画像、信息节点和精细流程要求，检查完整对话中医生是否存在漏问。

## 患者画像
```
{患者画像}
```

## 信息节点
```
{信息节点}
```

## 精细流程要求
```
{精细流程要求}
```

## 完整对话
```
{完整对话}
```

## 判断依据
1. 按对话时间顺序逐项核对所有信息节点，检查医生是否已经进行相应提问。
2. 精细流程中的追问不是固定必问项。只有患者回复满足对应触发条件时，才检查医生是否完成该追问。
3. 患者已经在之前的回复中主动提供某个节点或追问所需的信息时，医生无需重复提问，不算遗漏。
4. 只要医生已经明确提问某个节点，即视为医生完成了该节点的提问；不要因为患者没有回答、答非所问、表示不知道、记不清或没有测量，就把它判为医生漏问。
5. 患者使用“正常、偏高、偏低、一直这样、最近才出现”等定性描述时，视为已经提供对应信息，不强制要求具体数值。
6. 判断指标是否异常、是否触发追问时，优先采用对话中医生对指标的明确判断。若医生没有定性，只有在流程要求给出明确判断标准时才据此判断，不自行引入额外医学阈值。
7. 如果精细流程规定特殊情况出现后应建议就医、停止当前节点的其他追问并进入下一节点，则医生按该特殊分支处理时，不得将被跳过的追问判为遗漏。
8. 如果患者回复没有触发某项追问条件，则医生未进行该追问不算遗漏。
9. 医生提出流程外问题、进行了多余追问、表达不够自然或医学解释存在问题，不属于本任务的“流程遗漏”；除非这些行为导致必问节点或已触发的追问最终没有被提问。
10. 最终结论只判断是否存在至少一个未提问的必问节点或已触发追问。存在任意一项则为“有”，否则为“没有”。

## 输出要求
严格输出一个 JSON 对象，不要输出 JSON 之外的内容：
```
{"模型分析": "按节点说明判断过程", "是否有遗漏": "有/没有", "遗留问题": ["遗漏的节点或追问；没有遗漏时为空数组"]}
```
"""


def first_doctor_prompts(root: Path) -> dict[str, str]:
    source = root / "实验1_单轮推理任务/外呼benchmark数据_推理_qwen35_all.xlsx"
    prompts = {}
    for _sheet, record in iter_table(source):
        script_name = record.get("话术名称")
        prompt = record.get("模型提示词输入")
        if script_name and isinstance(prompt, str) and prompt:
            prompts.setdefault(str(script_name), prompt)
    return prompts


def first_eval_prompt(directory: Path) -> str:
    path = sorted(directory.glob("*.json"))[0]
    for record in iter_json_objects(path):
        if isinstance(record, dict) and record.get("query"):
            return str(record["query"])
    raise RuntimeError(f"No evaluation prompt found in {directory}")


def first_behavior_prompt(root: Path) -> str:
    path = root / "患者打标签/四种行为分类_v2.xlsx"
    for _sheet, record in iter_table(path):
        if record.get("提示词_完整prompt"):
            return str(record["提示词_完整prompt"])
    raise RuntimeError("No patient behavior classification prompt found")


def write_prompt(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if not text else text.rstrip() + "\n", encoding="utf-8")


def build_clean_prompts(root: Path, output: Path) -> dict[str, int]:
    prompt_root = output / "prompts"
    prompt_root.mkdir(parents=True, exist_ok=True)
    for path in prompt_root.glob("*.jsonl"):
        path.unlink()
    for path in prompt_root.glob("*_MISSING.md"):
        path.unlink()

    doctor_prompts = first_doctor_prompts(root)
    disease_names = {
        "精细话术冠心病": "冠心病",
        "精细话术糖尿病": "糖尿病",
        "精细话术脑梗": "脑梗",
        "精细话术颅脑损伤": "颅脑损伤",
        "精细话术高血压": "高血压",
    }
    for source_name, file_name in disease_names.items():
        write_prompt(prompt_root / "doctor_agent" / f"{file_name}.txt", doctor_prompts.get(source_name, ""))

    write_prompt(prompt_root / "patient_agent" / "患者回复生成.txt", "")

    content_prompt = first_eval_prompt(root / "实验1_单轮推理评测/内容3维度")
    write_prompt(prompt_root / "evaluation" / "内容质量三维度.txt", content_prompt)

    question_prompt = first_eval_prompt(root / "实验1_单轮推理评测/提问合理性")
    write_prompt(prompt_root / "evaluation" / "提问合理性.txt", question_prompt)

    write_prompt(prompt_root / "evaluation" / "患者行为分类.txt", first_behavior_prompt(root))
    write_prompt(
        prompt_root / "evaluation" / "多轮流程完整性.txt",
        DERIVED_MULTI_TURN_EVALUATION_PROMPT,
    )
    return {
        "doctor_agent_prompts_available": sum(bool(value) for value in doctor_prompts.values()),
        "patient_agent_prompts_available": 0,
        "evaluation_prompts_available": 4,
        "empty_prompt_files": 1,
    }


if __name__ == "__main__":
    workspace = Path.cwd().resolve()
    release = workspace / "open_source_release"
    print(json.dumps(build_clean_prompts(workspace, release), ensure_ascii=False, indent=2))
