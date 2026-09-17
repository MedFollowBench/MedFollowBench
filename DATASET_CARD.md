# MedFollowBench Dataset Card

## Dataset summary

本数据集用于研究中文医疗随访外呼中的流程遵循、患者行为理解、下一轮医生回复生成与对话评测。当前发布候选版只包含用户指定的两类数据源及可从现有文件中直接抽取的提示词。

## Dataset structure

本 benchmark 包含单轮评测集（2,169 条）和多轮评测集（500 条），分别用于下一轮医生回复生成与评测、完整随访对话生成与流程评测。不设置训练集或验证集。

### Single-turn evaluation set

`data/single_turn.jsonl` 共 2,169 条，每条记录包含病例 ID、话术名称、患者画像、流程要求、历史对话、机构与姓名占位符、患者行为标签、提示词组件及行为分类。任务目标是结合上文和当前患者回复生成下一轮医生回复。

### Multi-turn evaluation set

`data/multi_turn.jsonl` 共 500 条，五个病种各100条，每条包含病例 ID、患者画像、完整随访流程、信息节点和精细流程要求，用于多轮对话生成与流程评测。

多轮评测集的 500 条病例中，250 条 `patient_profile` 为空，占 50%。空画像保留为空字符串（`""`）；使用这些病例时，仅依据该病例提供的流程与信息节点，不自动补造画像。

原始的10000条数据属于原始打标签数据，不作为多轮评测集发布。

### Prompt templates

- `prompts/doctor_agent/`：五个病种各一份从既有模型输入字段逐字抽取的医生 Agent Prompt。
- `prompts/patient_agent/`：源数据未保存原始 Prompt，文件内容为空。
- `prompts/evaluation/`：内容质量三维度、提问合理性和患者行为分类为既有 Prompt 原文；多轮流程完整性提示词由历史裁判结果提炼，不是恢复的原始提示词。

## Languages and domains

- Language: Simplified Chinese.
- Domain: medical discharge follow-up and chronic-disease outbound calls.
- Disease groups visible in the source include hypertension, diabetes, coronary heart disease, cerebral infarction, and brain injury-related follow-up scripts.

## Intended use

适合：学术研究、模型离线评测、对话流程分析、提示词复现实验和错误分析。

不适合：临床诊断、直接患者照护、自动处方、紧急医疗决策、未审核的生产外呼或个体风险预测。

## License and citation

数据、提示词内容、标注、元数据、模式定义及文档采用 **CC BY-NC 4.0**（署名—非商业性使用），详见 `LICENSE-DATA.txt`。`scripts/` 和 `examples/` 中的 Python 源代码采用 **MIT**，详见 `LICENSE-CODE`；代码许可不改变其中涉及的数据和提示词内容的非商业限制。商业使用数据需另行取得相关权利方许可。引用格式见 `CITATION.cff`。第三方材料仍受其原始许可及适用权利约束。

## Evaluation

单轮记录提供对话上下文与行为标签，不提供独立的下一轮医生标准答案；这是生成式评测输入，不是监督训练样本。


当前患者模拟协议与完整实验配置尚未发布。空画像的回答策略需要由实验设计者确认，不能从流程要求自动推断患者事实。现有提示词和读取示例不足以独立复现历史实验。详见 [评测说明](docs/evaluation.md)。

## Version

当前发布候选版本为 `1.0.0-rc6`。
