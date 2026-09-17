---
language:
  - zh
license: cc-by-nc-4.0
task_categories:
  - text-generation
  - conversational
tags:
  - healthcare
  - outbound-call
  - benchmark
  - multi-turn-dialogue
pretty_name: MedFollowBench
size_categories:
  - 1K<n<10K
---

# MedFollowBench

A Chinese benchmark for proactive spoken medical outbound dialogue. This release contains **2,169 turn-level evaluation cases** and **500 session-level case specifications**, together with available physician and evaluator prompts, data-loading examples, and validation scripts.

**Current scope:** the patient-simulator prompt and model weights, complete model/evaluator configurations, and end-to-end experiment reproduction code are not included in this release. See [evaluation notes](docs/evaluation.md) for the available components and limitations.

这是一个面向中文医疗随访外呼研究的开放数据发布候选包。数据采用 UTF-8 JSONL，提示词采用逐字抽取的纯文本文件，适合直接加载到 Hugging Face Datasets、Python 或主流数据仓库。

## 发布范围

| 文件 | 记录数 | 来源 | 内容 |
| --- | ---: | --- | --- |
| `data/single_turn.jsonl` | 2,169 | `五个慢性病按照行为标签筛选后数据.xlsx` | 单轮下一回复任务、画像、流程、历史对话、患者行为标签与提示词组件 |
| `data/multi_turn.jsonl` | 500 | `实验2_多轮推理任务/话术_画像_抽取.jsonl` | 五个病种各100条多轮评测病例，包含画像与随访流程 |
| `prompts/doctor_agent/` | 5 | 既有单轮模型输入 | 冠心病、糖尿病、脑梗、颅脑损伤、高血压各一份原文 Prompt |
| `prompts/patient_agent/` | 0 份可用 | 原始指令尚未提供 | 保留一个空占位文件，不作为可运行提示词 |
| `prompts/evaluation/` | 4 | 既有评测输入与结果 | 内容质量、提问合理性、患者行为分类为原文；多轮流程完整性根据既有裁判结论与分析提炼 |

## 评测任务

本 benchmark 包含单轮评测集（2,169 条）和多轮评测集（500 条），分别用于下一轮医生回复生成与评测、完整随访对话生成与流程评测。不设置训练集或验证集。

## 数据格式

每行是一个独立 JSON 对象。单轮数据的对话同时保留：

- `conversation.raw_text`：原始文本，不改写内容。
- `conversation.messages`：规范化消息列表，角色为 `assistant`（医生）或 `user`（患者）。
- `source_file`：原始来源文件，可结合 `metadata/source_manifest.json` 校验。

多轮数据是 500 条评测病例输入，包含 `patient_profile`、`information_nodes` 和 `detailed_flow_requirements`，不混入任何模型生成结果。

## 快速读取

需要 Python 3.10 或更高版本。内置脚本仅使用标准库，无需安装第三方依赖。

在项目根目录运行：

```bash
python3 examples/quickstart.py
python3 examples/quickstart.py --task multi_turn
```

示例输出任务记录数、病种分布及首条样本。完整统计见 [docs/statistics.md](docs/statistics.md)。

```python
import json

with open("data/single_turn.jsonl", encoding="utf-8") as f:
    first_record = json.loads(next(f))

print(first_record["conversation"]["messages"])
```

## 复现与校验

在项目根目录运行：

```bash
python3 scripts/validate_dataset.py
```

检查 JSONL、唯一 ID、提示词文件数量、非空约束和基础敏感标识模式；报告写入 `metadata/independent_validation.json`。

重新抽取需要原始数据文件；公开包可直接读取，无需重新抽取。原始来源见 `metadata/source_manifest.json`。

```bash
python3 scripts/extract_dataset.py --root "/path/to/source" --output "/tmp/benchmark-rebuild"
```

## 项目配套文件

- [examples/quickstart.py](examples/quickstart.py)：读取单轮、多轮数据。
- [docs/statistics.md](docs/statistics.md)：样本数、病种、行为类别与空画像统计。
- [CONTRIBUTING.md](CONTRIBUTING.md)：反馈与贡献方式。
- [requirements.txt](requirements.txt)：运行环境与依赖说明。

评测输入与目前复现范围见 [docs/evaluation.md](docs/evaluation.md)，评测待确认事项见 [docs/release_checklist.md](docs/release_checklist.md)。

更完整的字段、来源和伦理说明见 `DATASET_CARD.md`。

## License / 使用许可

- **Data and prompt content:** [CC BY-NC 4.0](LICENSE-DATA.txt). Sharing and adaptation are permitted for non-commercial purposes with attribution; commercial use requires separate permission.
- **Python source code:** [MIT](LICENSE-CODE). This code license does not grant commercial rights over the data or prompt content.

数据及提示词内容可用于非商业研究与评测，须保留署名、许可说明并标明修改。商业使用需另行授权。数据未经临床有效性认证，不应将其视为临床建议或可直接部署的医疗系统。引用信息见 [CITATION.cff](CITATION.cff)。
