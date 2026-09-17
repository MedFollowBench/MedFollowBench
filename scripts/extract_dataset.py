#!/usr/bin/env python3
"""Build a normalized, publication-ready release from the benchmark source files.

The reader intentionally uses only Python's standard library so the release can be
rebuilt without Excel or third-party Python packages.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Iterator
from xml.etree import ElementTree as ET


NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
CELL_REF_RE = re.compile(r"([A-Z]+)(\d+)")


def column_index(cell_ref: str) -> int:
    match = CELL_REF_RE.match(cell_ref)
    if not match:
        return 0
    value = 0
    for char in match.group(1):
        value = value * 26 + ord(char) - 64
    return value - 1


def _rich_text(node: ET.Element) -> str:
    return "".join(part.text or "" for part in node.findall(".//m:t", NS))


def iter_xlsx_sheets(path: Path) -> Iterator[tuple[str, Iterator[list[Any]]]]:
    """Yield worksheet names and streaming row iterators from an XLSX file."""
    with zipfile.ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = [_rich_text(item) for item in root.findall("m:si", NS)]

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_targets = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in rels.findall("r:Relationship", REL_NS)
        }
        rel_key = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        sheet_specs = []
        for sheet in workbook.findall("m:sheets/m:sheet", NS):
            target = rel_targets[sheet.attrib[rel_key]].lstrip("/")
            if not target.startswith("xl/"):
                target = f"xl/{target}"
            sheet_specs.append((sheet.attrib["name"], target))

    def row_iterator(xml_path: str) -> Iterator[list[Any]]:
        with zipfile.ZipFile(path) as archive:
            with archive.open(xml_path) as stream:
                for _event, elem in ET.iterparse(stream, events=("end",)):
                    if elem.tag != f"{{{NS['m']}}}row":
                        continue
                    row: list[Any] = []
                    for cell in elem.findall("m:c", NS):
                        idx = column_index(cell.attrib.get("r", "A1"))
                        while len(row) <= idx:
                            row.append(None)
                        cell_type = cell.attrib.get("t")
                        value_node = cell.find("m:v", NS)
                        inline = cell.find("m:is", NS)
                        value: Any = None
                        if inline is not None:
                            value = _rich_text(inline)
                        elif value_node is not None:
                            raw = value_node.text or ""
                            if cell_type == "s":
                                value = shared[int(raw)] if raw else ""
                            elif cell_type in {"str", "e"}:
                                value = raw
                            elif cell_type == "b":
                                value = raw == "1"
                            else:
                                try:
                                    number = float(raw)
                                    value = int(number) if number.is_integer() else number
                                except ValueError:
                                    value = raw
                        row[idx] = value
                    while row and row[-1] is None:
                        row.pop()
                    yield row
                    elem.clear()

    for sheet_name, target in sheet_specs:
        yield sheet_name, row_iterator(target)


def source_files(root: Path, output: Path) -> list[Path]:
    allowed = {".xlsx", ".json", ".jsonl"}
    result = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in allowed:
            continue
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        if output == path or output in path.parents:
            continue
        result.append(path)
    return sorted(result)


def iter_table(path: Path) -> Iterator[tuple[str, dict[str, Any]]]:
    for sheet, rows in iter_xlsx_sheets(path):
        try:
            header = next(rows)
        except StopIteration:
            continue
        headers = [str(value).strip() if value is not None else "" for value in header]
        if not any(headers):
            continue
        for row in rows:
            if not any(value not in (None, "") for value in row):
                continue
            record = {
                key: row[index] if index < len(row) else None
                for index, key in enumerate(headers)
                if key
            }
            yield sheet, record


def iter_json_objects(path: Path) -> Iterator[Any]:
    text = path.read_text(encoding="utf-8-sig")
    decoder = json.JSONDecoder()
    index = 0
    while index < len(text) and text[index].isspace():
        index += 1
    if index >= len(text):
        return
    first, end = decoder.raw_decode(text, index)
    tail = text[end:].strip()
    if isinstance(first, list) and not tail:
        yield from first
        return
    yield first
    index = end
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        value, index = decoder.raw_decode(text, index)
        yield value


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def parse_embedded_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    starts = [position for position in (text.find("{"), text.find("[")) if position >= 0]
    if not starts:
        return None
    try:
        parsed, _ = json.JSONDecoder().raw_decode(text[min(starts):])
        return parsed
    except json.JSONDecodeError:
        return None


def split_flow(value: Any) -> tuple[Any, Any]:
    if not isinstance(value, str):
        return None, value
    match = re.search(r"##\s*精细流程要求\s*", value)
    if not match:
        return None, value
    first = re.sub(r"^\s*##\s*信息节点\s*", "", value[:match.start()]).strip()
    second = value[match.end():].strip()
    return first or None, second or None


ROLE_RE = re.compile(
    r"^\s*(?:【\s*)?(医生|患者|doctor|patient)\s*\d*\s*(?:】)?\s*[：:]\s*(.*)$",
    flags=re.IGNORECASE,
)


def parse_messages(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, str) or not value.strip():
        return []
    messages: list[dict[str, str]] = []
    for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        match = ROLE_RE.match(line)
        if match:
            label = match.group(1).lower()
            role = "assistant" if label in {"医生", "doctor"} else "user"
            messages.append({"role": role, "content": match.group(2).strip()})
        elif messages:
            messages[-1]["content"] += "\n" + line
    for message in messages:
        message["content"] = message["content"].strip()
    return [message for message in messages if message["content"]]


MODEL_PATTERNS = [
    (r"claude", "claude-opus-4.6"),
    (r"deepseek", "deepseek-v4-pro"),
    (r"doubao", "doubao-seed-2.0-pro"),
    (r"gemini", "gemini-3.1-pro-preview"),
    (r"gpt[-_]?5[._]?5|gpt55", "gpt-5.5"),
    (r"qwen", "qwen-3.5"),
    (r"kimi", "kimi-k2.5"),
    (r"glm", "glm-5"),
]


def infer_model(value: str) -> str:
    lowered = value.lower()
    for pattern, model in MODEL_PATTERNS:
        if re.search(pattern, lowered):
            return model
    return value


def clean_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: json_value(value) for key, value in record.items()}


class JsonlWriter:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = path.open("w", encoding="utf-8", newline="\n")
        self.count = 0

    def write(self, record: dict[str, Any]) -> None:
        self.handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        self.count += 1

    def close(self) -> None:
        self.handle.close()


class PromptRegistry:
    def __init__(self, catalog_path: Path, occurrence_path: Path):
        self.catalog_path = catalog_path
        self.occurrences = JsonlWriter(occurrence_path)
        self.catalog: dict[str, dict[str, Any]] = {}

    def add(
        self,
        text: Any,
        *,
        stage: str,
        prompt_type: str,
        source_file: str,
        case_id: Any = None,
        model: Any = None,
    ) -> str | None:
        if not isinstance(text, str) or not text.strip():
            return None
        prompt_id = "prompt_" + sha256_text(text)
        entry = self.catalog.setdefault(
            prompt_id,
            {
                "prompt_id": prompt_id,
                "text": text,
                "sha256": sha256_text(text),
                "stages": set(),
                "prompt_types": set(),
                "source_files": set(),
                "models": set(),
                "occurrence_count": 0,
            },
        )
        entry["stages"].add(stage)
        entry["prompt_types"].add(prompt_type)
        entry["source_files"].add(source_file)
        if model:
            entry["models"].add(str(model))
        entry["occurrence_count"] += 1
        occurrence = {
            "occurrence_id": f"prompt_occ_{self.occurrences.count + 1:07d}",
            "prompt_id": prompt_id,
            "case_id": case_id,
            "stage": stage,
            "prompt_type": prompt_type,
            "model": model,
            "source_file": source_file,
        }
        self.occurrences.write(occurrence)
        return prompt_id

    def close(self) -> tuple[int, int]:
        self.occurrences.close()
        writer = JsonlWriter(self.catalog_path)
        for prompt_id in sorted(self.catalog):
            record = self.catalog[prompt_id]
            for key in ("stages", "prompt_types", "source_files", "models"):
                record[key] = sorted(record[key])
            writer.write(record)
        writer.close()
        return writer.count, self.occurrences.count


CASE_FIELD_MAP = {
    "话术名称": "script_name",
    "用户画像": "patient_profile",
    "流程要求": "flow_requirements",
    "对话上文": "conversation_context",
    "医院": "organization",
    "姓名": "patient_name",
    "患者行为标签": "patient_behavior_label_raw",
    "信息节点": "information_nodes",
    "提示词_历史对话": "prompt_history",
    "提示词_当前轮患者回复": "prompt_current_patient_reply",
    "提示词_节点信息": "prompt_node_information",
    "提示词_完整prompt": "prompt_full",
    "患者行为类型": "behavior_type",
    "子类型": "behavior_subtype",
    "主行为类型": "main_behavior_type",
}


def build_single_turn_cases(
    root: Path,
    data_dir: Path,
    prompts: PromptRegistry,
    conversations: JsonlWriter,
) -> tuple[int, int, list[dict[str, Any]]]:
    inputs = [
        root / "五种慢性病的原始10000数据.xlsx",
        root / "患者打标签/四种行为分类_v2.xlsx",
        root / "患者打标签/带行为标签_MT3_20260424.xlsx",
        root / "五个慢性病按照行为标签筛选后数据.xlsx",
    ]
    cases: dict[str, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    for path in inputs:
        rel = path.relative_to(root).as_posix()
        is_selected = path.name.startswith("五个慢性病按照")
        for _sheet, raw in iter_table(path):
            case_id = str(raw.get("id") or "").strip()
            if not case_id:
                continue
            if is_selected:
                selected_ids.add(case_id)
            case = cases.setdefault(
                case_id,
                {"case_id": case_id, "source_files": [], "field_variants": {}},
            )
            case["source_files"].append(rel)
            for source_key, target_key in CASE_FIELD_MAP.items():
                value = raw.get(source_key)
                if value in (None, ""):
                    continue
                if target_key not in case:
                    case[target_key] = json_value(value)
                elif case[target_key] != value:
                    variants = case["field_variants"].setdefault(target_key, [])
                    if not variants:
                        variants.append({"source_file": case["source_files"][0], "value": case[target_key]})
                    if not any(item["value"] == value for item in variants):
                        variants.append({"source_file": rel, "value": json_value(value)})
                        conflicts.append({"case_id": case_id, "field": target_key, "source_file": rel})

    writer = JsonlWriter(data_dir / "single_turn_cases.jsonl")
    for case_id in sorted(cases):
        case = cases[case_id]
        case["benchmark_selected"] = case_id in selected_ids
        case["source_files"] = sorted(set(case["source_files"]))
        if not case["field_variants"]:
            case.pop("field_variants")
        behavior = parse_embedded_json(case.get("patient_behavior_label_raw"))
        if behavior is not None:
            case["patient_behavior_label"] = behavior
        nodes, detailed = split_flow(case.get("flow_requirements"))
        case.setdefault("information_nodes", nodes)
        case["detailed_flow_requirements"] = detailed
        conversation_text = case.pop("conversation_context", None)
        messages = parse_messages(conversation_text)
        if conversation_text:
            conversation_id = "conversation_st_" + sha256_text(case_id)[:20]
            conversations.write(
                {
                    "conversation_id": conversation_id,
                    "case_id": case_id,
                    "stage": "single_turn_context",
                    "model": None,
                    "messages": messages,
                    "message_count": len(messages),
                    "raw_text": conversation_text,
                }
            )
            case["conversation_id"] = conversation_id
        if case.get("prompt_full"):
            case["prompt_id"] = prompts.add(
                case["prompt_full"],
                stage="single_turn",
                prompt_type="generation",
                source_file=case["source_files"][-1],
                case_id=case_id,
            )
        writer.write(case)
    writer.close()
    return writer.count, len(selected_ids), conflicts


def build_single_turn_generations(
    root: Path, data_dir: Path, prompts: PromptRegistry
) -> int:
    writer = JsonlWriter(data_dir / "single_turn_generations.jsonl")
    xlsx_dir = root / "实验1_单轮推理任务"
    for path in sorted(xlsx_dir.glob("*.xlsx")):
        model = infer_model(path.name)
        rel = path.relative_to(root).as_posix()
        for _sheet, raw in iter_table(path):
            case_id = raw.get("id")
            prompt_id = prompts.add(
                raw.get("模型提示词输入"),
                stage="single_turn",
                prompt_type="generation",
                source_file=rel,
                case_id=case_id,
                model=model,
            )
            output = raw.get("原始模型输出")
            writer.write(
                {
                    "generation_id": f"stgen_{writer.count + 1:06d}",
                    "case_id": case_id,
                    "model": model,
                    "model_source_label": path.stem,
                    "prompt_id": prompt_id,
                    "response": parse_embedded_json(output),
                    "response_raw": output,
                    "reasoning_content": None,
                    "usage": None,
                    "input_snapshot": clean_record({
                        key: value for key, value in raw.items()
                        if key not in {"模型提示词输入", "原始模型输出"}
                    }),
                    "source_file": rel,
                }
            )
    for path in sorted(xlsx_dir.glob("*.json")):
        rel = path.relative_to(root).as_posix()
        for raw in iter_json_objects(path):
            if not isinstance(raw, dict):
                continue
            model_label = str(raw.get("source") or path.stem)
            model = infer_model(model_label)
            case_id = raw.get("id")
            prompt_id = prompts.add(
                raw.get("query"),
                stage="single_turn",
                prompt_type="generation",
                source_file=rel,
                case_id=case_id,
                model=model,
            )
            writer.write(
                {
                    "generation_id": f"stgen_{writer.count + 1:06d}",
                    "case_id": case_id,
                    "model": model,
                    "model_source_label": model_label,
                    "prompt_id": prompt_id,
                    "query_md5": raw.get("query_md5"),
                    "response": parse_embedded_json(raw.get("answer")),
                    "response_raw": raw.get("answer"),
                    "reasoning_content": raw.get("reasoning_content"),
                    "usage": {
                        "prompt_tokens": raw.get("prompt_tokens"),
                        "completion_tokens": raw.get("completion_tokens"),
                    },
                    "error": raw.get("err"),
                    "updated_at": raw.get("update_time") or raw.get("updatetime"),
                    "source_file": rel,
                }
            )
    writer.close()
    return writer.count


def build_single_turn_evaluations(
    root: Path, data_dir: Path, prompts: PromptRegistry
) -> int:
    writer = JsonlWriter(data_dir / "single_turn_evaluations.jsonl")
    base = root / "实验1_单轮推理评测"
    for path in sorted(base.rglob("*.json")):
        rel = path.relative_to(root).as_posix()
        dimension = "content_quality_3d" if "内容3维度" in rel else "question_reasonableness"
        judge_model = infer_model(path.name)
        for raw in iter_json_objects(path):
            if not isinstance(raw, dict):
                continue
            case_id = raw.get("id")
            prompt_id = prompts.add(
                raw.get("query"),
                stage="single_turn_evaluation",
                prompt_type=dimension,
                source_file=rel,
                case_id=case_id,
                model=judge_model,
            )
            response_raw = raw.get("回复")
            writer.write(
                {
                    "evaluation_id": f"steval_{writer.count + 1:06d}",
                    "case_id": case_id,
                    "dimension": dimension,
                    "judge_model": judge_model,
                    "prompt_id": prompt_id,
                    "result": parse_embedded_json(response_raw),
                    "result_raw": response_raw,
                    "latency": {
                        "time_to_first_response_seconds": raw.get("首响"),
                        "generated_characters": raw.get("生成字数"),
                        "characters_per_second": raw.get("平均字数/s"),
                        "total_seconds": raw.get("整体时间"),
                    },
                    "source_file": rel,
                }
            )
    writer.close()
    return writer.count


def build_multi_turn_cases(root: Path, data_dir: Path) -> int:
    path = root / "实验2_多轮推理任务/话术_画像_抽取.jsonl"
    writer = JsonlWriter(data_dir / "multi_turn_cases.jsonl")
    rel = path.relative_to(root).as_posix()
    for raw in iter_json_objects(path):
        if not isinstance(raw, dict):
            continue
        nodes, detailed = split_flow(raw.get("话术"))
        writer.write(
            {
                "case_id": raw.get("数据id"),
                "script_name": raw.get("话术名称"),
                "patient_profile": raw.get("用户画像"),
                "flow_requirements": raw.get("话术"),
                "information_nodes": nodes,
                "detailed_flow_requirements": detailed,
                "source_file": rel,
            }
        )
    writer.close()
    return writer.count


def build_multi_turn_generations(
    root: Path,
    data_dir: Path,
    prompts: PromptRegistry,
    conversations: JsonlWriter,
) -> tuple[int, list[dict[str, Any]]]:
    writer = JsonlWriter(data_dir / "multi_turn_generations.jsonl")
    base = root / "实验2_多轮推理任务/模型多轮推理结果"
    seen: dict[tuple[str, str], str] = {}
    duplicates: list[dict[str, Any]] = []
    for path in sorted(base.rglob("*.xlsx")):
        rel = path.relative_to(root).as_posix()
        model = infer_model(path.parent.name + " " + path.name)
        for _sheet, raw in iter_table(path):
            case_id = str(raw.get("数据id") or "")
            key = (model, case_id)
            if key in seen:
                duplicates.append({"model": model, "case_id": case_id, "files": [seen[key], rel]})
            else:
                seen[key] = rel
            prompt_id = prompts.add(
                raw.get("医生首轮提示词"),
                stage="multi_turn",
                prompt_type="generation",
                source_file=rel,
                case_id=case_id,
                model=model,
            )
            dialogue = raw.get("端到端生成对话")
            messages = parse_messages(dialogue)
            conversation_id = "conversation_mt_" + sha256_text(f"{model}\0{case_id}\0{rel}")[:20]
            conversations.write(
                {
                    "conversation_id": conversation_id,
                    "case_id": case_id,
                    "stage": "multi_turn_generation",
                    "model": model,
                    "messages": messages,
                    "message_count": len(messages),
                    "raw_text": dialogue,
                    "source_file": rel,
                }
            )
            writer.write(
                {
                    "generation_id": f"mtgen_{writer.count + 1:05d}",
                    "case_id": case_id,
                    "model": model,
                    "prompt_id": prompt_id,
                    "conversation_id": conversation_id,
                    "raw_model_output": raw.get("原始模型输出"),
                    "input_snapshot": {
                        "script_name": raw.get("话术名称"),
                        "organization": raw.get("机构名称"),
                        "patient_profile": raw.get("用户画像"),
                        "information_nodes": raw.get("医生agent-信息节点"),
                        "detailed_flow_requirements": raw.get("医生agent-精细流程要求"),
                    },
                    "source_file": rel,
                }
            )
    writer.close()
    return writer.count, duplicates


def build_multi_turn_evaluations(root: Path, data_dir: Path) -> int:
    writer = JsonlWriter(data_dir / "multi_turn_evaluations.jsonl")
    base = root / "实验2_多轮推理任务/多轮推理评测"
    for path in sorted(base.glob("外呼benchmark_多轮对话_*测评结果.xlsx")):
        rel = path.relative_to(root).as_posix()
        target_model = infer_model(path.name)
        for _sheet, raw in iter_table(path):
            writer.write(
                {
                    "evaluation_id": f"mteval_{writer.count + 1:05d}",
                    "case_id": raw.get("id"),
                    "target_model": target_model,
                    "judge_labels": {
                        "deepseek-v4-pro": raw.get("deepseekV4pro"),
                        "glm-5": raw.get("glm5"),
                        "qwen-3.5": raw.get("qwen3.5"),
                    },
                    "judge_reasoning_summary": raw.get("模型原因汇总"),
                    "aggregate_verdict_any_error": raw.get("多模型质检-错1个就算错"),
                    "aggregate_verdict_majority_error": raw.get("多模型质检-错2个才算错"),
                    "aggregate_label_summary": raw.get("多模型质检结果汇总"),
                    "human_annotation": raw.get("整通流程完整率-人工标注"),
                    "human_error_reason": raw.get("错误原因"),
                    "input_snapshot": {
                        "organization": raw.get("机构名称"),
                        "patient_profile": raw.get("用户画像"),
                        "information_nodes": raw.get("信息节点"),
                        "detailed_flow_requirements": raw.get("精细流程要求"),
                        "conversation_text": raw.get("对话内容"),
                    },
                    "source_file": rel,
                }
            )
    writer.close()
    return writer.count


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_schemas(output: Path) -> None:
    schemas = {
        "single_turn_cases": ["case_id", "benchmark_selected", "source_files"],
        "single_turn_generations": ["generation_id", "case_id", "model", "prompt_id", "response_raw"],
        "single_turn_evaluations": ["evaluation_id", "case_id", "dimension", "judge_model", "prompt_id"],
        "multi_turn_cases": ["case_id", "flow_requirements"],
        "multi_turn_generations": ["generation_id", "case_id", "model", "prompt_id", "conversation_id"],
        "multi_turn_evaluations": ["evaluation_id", "case_id", "target_model", "judge_labels"],
        "conversations": ["conversation_id", "case_id", "stage", "messages"],
        "prompt_catalog": ["prompt_id", "text", "sha256", "occurrence_count"],
        "prompt_occurrences": ["occurrence_id", "prompt_id", "stage", "source_file"],
    }
    for name, required in schemas.items():
        write_json(
            output / "schemas" / f"{name}.schema.json",
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": f"https://example.org/outbound-call-benchmark/{name}.schema.json",
                "title": name,
                "type": "object",
                "required": required,
                "additionalProperties": True,
                "properties": {key: {} for key in required},
            },
        )


def privacy_scan(data_dir: Path) -> dict[str, Any]:
    patterns = {
        "mainland_china_mobile": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
        "mainland_china_id": re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)"),
        "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    }
    counts = Counter()
    samples: dict[str, list[dict[str, Any]]] = {key: [] for key in patterns}
    files_scanned = 0
    identifier_keys = {
        "case_id", "conversation_id", "evaluation_id", "generation_id", "occurrence_id",
        "prompt_id", "query_md5", "sha256",
    }

    def text_values(value: Any, key: str | None = None) -> Iterator[str]:
        if key in identifier_keys or (key and key.endswith("_id")):
            return
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for child_key, child in value.items():
                yield from text_values(child, child_key)
        elif isinstance(value, list):
            for child in value:
                yield from text_values(child, key)

    for path in sorted(data_dir.glob("*.jsonl")):
        files_scanned += 1
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                record = json.loads(line)
                for text_value in text_values(record):
                    for key, pattern in patterns.items():
                        matches = pattern.findall(text_value)
                        if not matches:
                            continue
                        counts[key] += len(matches)
                        if len(samples[key]) < 5:
                            samples[key].append(
                                {
                                    "file": path.name,
                                    "line": line_number,
                                    "masked_match": matches[0][:3] + "***" + matches[0][-2:],
                                }
                            )
    return {
        "scan_scope": "All generated JSONL files",
        "files_scanned": files_scanned,
        "pattern_counts": dict(counts),
        "samples": samples,
        "limitations": [
            "Pattern matching cannot prove that free text contains no personal data.",
            "Dates, clinical facts, rare diseases, and organization names require human disclosure review.",
            "Generic placeholders such as xxx, 张三, [人名], [日期], and [医院名称] are retained.",
        ],
    }


def validate_jsonl(data_dir: Path) -> dict[str, Any]:
    files = []
    errors = []
    for path in sorted(data_dir.glob("*.jsonl")):
        count = 0
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                try:
                    json.loads(line)
                    count += 1
                except json.JSONDecodeError as exc:
                    errors.append({"file": path.name, "line": line_number, "error": str(exc)})
        files.append(
            {
                "path": f"data/{path.name}",
                "records": count,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {"valid": not errors, "errors": errors, "files": files}


def build_release(root: Path, output: Path) -> dict[str, Any]:
    data_dir = output / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    prompts = PromptRegistry(data_dir / "prompt_catalog.jsonl", data_dir / "prompt_occurrences.jsonl")
    conversations = JsonlWriter(data_dir / "conversations.jsonl")
    st_cases, selected, conflicts = build_single_turn_cases(root, data_dir, prompts, conversations)
    st_generations = build_single_turn_generations(root, data_dir, prompts)
    st_evaluations = build_single_turn_evaluations(root, data_dir, prompts)
    mt_cases = build_multi_turn_cases(root, data_dir)
    mt_generations, duplicates = build_multi_turn_generations(root, data_dir, prompts, conversations)
    mt_evaluations = build_multi_turn_evaluations(root, data_dir)
    conversations.close()
    prompt_catalog, prompt_occurrences = prompts.close()
    write_schemas(output)

    sources = []
    for path in source_files(root, output):
        rel = path.relative_to(root).as_posix()
        sources.append(
            {
                "path": rel,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "format": path.suffix.lower().lstrip("."),
            }
        )
    write_json(output / "metadata" / "source_manifest.json", {"sources": sources})
    privacy = privacy_scan(data_dir)
    write_json(output / "metadata" / "privacy_scan.json", privacy)
    validation = validate_jsonl(data_dir)
    counts = {
        "single_turn_cases": st_cases,
        "single_turn_benchmark_selected": selected,
        "single_turn_generations": st_generations,
        "single_turn_evaluations": st_evaluations,
        "multi_turn_cases": mt_cases,
        "multi_turn_generations": mt_generations,
        "multi_turn_evaluations": mt_evaluations,
        "conversations": conversations.count,
        "prompt_catalog": prompt_catalog,
        "prompt_occurrences": prompt_occurrences,
        "case_field_conflicts": len(conflicts),
        "duplicate_multi_turn_model_case_pairs": len(duplicates),
    }
    report = {
        "dataset_name": "MedFollowBench",
        "version": "1.0.0-rc1",
        "build_date": date.today().isoformat(),
        "counts": counts,
        "validation": validation,
        "privacy_scan": privacy,
        "conflict_examples": conflicts[:20],
        "duplicate_examples": duplicates[:20],
    }
    write_json(output / "dataset_info.json", report)
    write_json(output / "metadata" / "validation_report.json", validation)
    return report


class ScopedPromptRegistry:
    def __init__(self, catalog_path: Path, occurrence_path: Path):
        self.catalog_path = catalog_path
        self.occurrence_writer = JsonlWriter(occurrence_path)
        self.items: dict[str, dict[str, Any]] = {}

    def add(
        self,
        text: Any,
        *,
        prompt_type: str,
        source_file: str,
        case_id: Any = None,
        model: Any = None,
    ) -> str | None:
        if not isinstance(text, str) or not text.strip():
            return None
        digest = sha256_text(text)
        prompt_id = "prompt_" + digest
        item = self.items.setdefault(
            prompt_id,
            {
                "prompt_id": prompt_id,
                "prompt_type": prompt_type,
                "text": text,
                "sha256": digest,
                "occurrence_count": 0,
                "models": set(),
                "source_files": set(),
            },
        )
        item["occurrence_count"] += 1
        item["source_files"].add(source_file)
        if model:
            item["models"].add(str(model))
        self.occurrence_writer.write(
            {
                "occurrence_id": f"occ_{self.occurrence_writer.count + 1:07d}",
                "prompt_id": prompt_id,
                "prompt_type": prompt_type,
                "case_id": case_id,
                "model": model,
                "source_file": source_file,
            }
        )
        return prompt_id

    def close(self) -> tuple[int, int]:
        self.occurrence_writer.close()
        writer = JsonlWriter(self.catalog_path)
        for prompt_id in sorted(self.items):
            item = self.items[prompt_id]
            item["models"] = sorted(item["models"])
            item["source_files"] = sorted(item["source_files"])
            writer.write(item)
        writer.close()
        return writer.count, self.occurrence_writer.count


def clear_previous_generated_outputs(output: Path) -> None:
    """Remove only files generated by this script, never source workbooks."""
    for directory, pattern in [
        (output / "data", "*.jsonl"),
        (output / "prompts", "*.jsonl"),
        (output / "schemas", "*.schema.json"),
        (output / "metadata", "*.json"),
    ]:
        if directory.exists():
            for path in directory.glob(pattern):
                path.unlink()


def export_requested_data(root: Path, output: Path) -> dict[str, int]:
    data_dir = output / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    single_writer = JsonlWriter(data_dir / "single_turn.jsonl")
    single_source = root / "五个慢性病按照行为标签筛选后数据.xlsx"
    single_rel = single_source.relative_to(root).as_posix()
    for _sheet, raw in iter_table(single_source):
        raw_label = raw.get("患者行为标签")
        conversation_text = raw.get("对话上文")
        messages = parse_messages(conversation_text)
        single_writer.write(
            {
                "id": raw.get("id"),
                "task": "single_turn_next_response",
                "script_name": raw.get("话术名称"),
                "patient_profile": raw.get("用户画像"),
                "flow_requirements": raw.get("流程要求"),
                "conversation": {
                    "raw_text": conversation_text,
                    "messages": messages,
                    "message_count": len(messages),
                },
                "organization": raw.get("医院"),
                "patient_name": raw.get("姓名"),
                "patient_behavior_label": parse_embedded_json(raw_label),
                "patient_behavior_label_raw": raw_label,
                "information_nodes": raw.get("信息节点"),
                "prompt_components": {
                    "history": raw.get("提示词_历史对话"),
                    "current_patient_reply": raw.get("提示词_当前轮患者回复"),
                },
                "behavior_type": raw.get("患者行为类型"),
                "behavior_subtype": raw.get("子类型"),
                "main_behavior_type": raw.get("主行为类型"),
                "source_file": single_rel,
            }
        )
    single_writer.close()

    multi_writer = JsonlWriter(data_dir / "multi_turn.jsonl")
    multi_source = root / "实验2_多轮推理任务/话术_画像_抽取.jsonl"
    multi_rel = multi_source.relative_to(root).as_posix()
    for raw in iter_json_objects(multi_source):
        if not isinstance(raw, dict):
            continue
        information_nodes, detailed_flow = split_flow(raw.get("话术"))
        multi_writer.write(
            {
                "id": raw.get("数据id"),
                "task": "multi_turn_dialogue_simulation",
                "script_name": raw.get("话术名称"),
                "patient_profile": raw.get("用户画像"),
                "flow_requirements": raw.get("话术"),
                "information_nodes": information_nodes,
                "detailed_flow_requirements": detailed_flow,
                "source_file": multi_rel,
            }
        )
    multi_writer.close()
    return {"single_turn": single_writer.count, "multi_turn": multi_writer.count}


def export_doctor_prompts(root: Path, output: Path) -> dict[str, int]:
    prompt_dir = output / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    registry = ScopedPromptRegistry(
        prompt_dir / "doctor_agent_prompts.jsonl",
        prompt_dir / "doctor_agent_prompt_occurrences.jsonl",
    )
    single_base = root / "实验1_单轮推理任务"
    for path in sorted(single_base.glob("*.xlsx")):
        rel = path.relative_to(root).as_posix()
        model = infer_model(path.name)
        for _sheet, raw in iter_table(path):
            registry.add(
                raw.get("模型提示词输入"),
                prompt_type="doctor_agent_single_turn",
                source_file=rel,
                case_id=raw.get("id"),
                model=model,
            )
    for path in sorted(single_base.glob("*.json")):
        rel = path.relative_to(root).as_posix()
        for raw in iter_json_objects(path):
            if not isinstance(raw, dict):
                continue
            model_label = str(raw.get("source") or path.name)
            registry.add(
                raw.get("query"),
                prompt_type="doctor_agent_single_turn",
                source_file=rel,
                case_id=raw.get("id"),
                model=infer_model(model_label),
            )
    multi_base = root / "实验2_多轮推理任务/模型多轮推理结果"
    for path in sorted(multi_base.rglob("*.xlsx")):
        rel = path.relative_to(root).as_posix()
        model = infer_model(path.parent.name + " " + path.name)
        for _sheet, raw in iter_table(path):
            registry.add(
                raw.get("医生首轮提示词"),
                prompt_type="doctor_agent_multi_turn_initial",
                source_file=rel,
                case_id=raw.get("数据id"),
                model=model,
            )
    catalog, occurrences = registry.close()
    return {"doctor_agent_prompt_catalog": catalog, "doctor_agent_prompt_occurrences": occurrences}


def export_evaluation_prompts(root: Path, output: Path) -> dict[str, int]:
    prompt_dir = output / "prompts"
    registry = ScopedPromptRegistry(
        prompt_dir / "evaluation_prompts.jsonl",
        prompt_dir / "evaluation_prompt_occurrences.jsonl",
    )
    eval_base = root / "实验1_单轮推理评测"
    for path in sorted(eval_base.rglob("*.json")):
        rel = path.relative_to(root).as_posix()
        prompt_type = "content_quality_3d" if "内容3维度" in rel else "question_reasonableness"
        judge_model = infer_model(path.name)
        for raw in iter_json_objects(path):
            if isinstance(raw, dict):
                registry.add(
                    raw.get("query"),
                    prompt_type=prompt_type,
                    source_file=rel,
                    case_id=raw.get("id"),
                    model=judge_model,
                )
    behavior_source = root / "患者打标签/四种行为分类_v2.xlsx"
    behavior_rel = behavior_source.relative_to(root).as_posix()
    for _sheet, raw in iter_table(behavior_source):
        registry.add(
            raw.get("提示词_完整prompt"),
            prompt_type="patient_behavior_classification",
            source_file=behavior_rel,
            case_id=raw.get("id"),
            model=None,
        )
    catalog, occurrences = registry.close()
    return {"evaluation_prompt_catalog": catalog, "evaluation_prompt_occurrences": occurrences}


def write_requested_schemas(output: Path) -> None:
    specifications = {
        "single_turn": ["id", "task", "conversation", "source_file"],
        "multi_turn": ["id", "task", "script_name", "patient_profile", "flow_requirements", "source_file"],
    }
    for name, required in specifications.items():
        write_json(
            output / "schemas" / f"{name}.schema.json",
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "title": name,
                "type": "object",
                "required": required,
                "additionalProperties": True,
                "properties": {key: {} for key in required},
            },
        )


def validate_scoped_release(output: Path) -> dict[str, Any]:
    checked = []
    errors = []
    allowed_empty_prompts = {
        "prompts/patient_agent/患者回复生成.txt",
    }
    for directory in [output / "data", output / "prompts"]:
        for path in sorted(directory.glob("*.jsonl")):
            count = 0
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    try:
                        json.loads(line)
                        count += 1
                    except json.JSONDecodeError as exc:
                        errors.append({"file": str(path.relative_to(output)), "line": line_number, "error": str(exc)})
            checked.append(
                {
                    "path": path.relative_to(output).as_posix(),
                    "records": count,
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    for path in sorted((output / "prompts").rglob("*.txt")):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(output).as_posix()
        if not text.strip() and relative not in allowed_empty_prompts:
            errors.append({"file": str(path.relative_to(output)), "error": "empty prompt"})
        checked.append(
            {
                "path": path.relative_to(output).as_posix(),
                "records": 1,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {"valid": not errors, "errors": errors, "files": checked}


def build_scoped_release(root: Path, output: Path) -> dict[str, Any]:
    clear_previous_generated_outputs(output)
    counts = {}
    counts.update(export_requested_data(root, output))
    from build_clean_prompts import build_clean_prompts
    counts.update(build_clean_prompts(root, output))
    write_requested_schemas(output)
    availability = {
        "doctor_agent_prompts": {
            "status": "available",
            "count": 5,
            "organization": "one verbatim extracted prompt per disease",
        },
        "patient_agent_prompts": {
            "status": "not_found_empty_file",
            "count": 0,
            "note": "The source files do not contain the original patient-agent prompt. The corresponding file is intentionally empty.",
        },
        "evaluation_prompts": {
            "status": "available_with_one_derived_prompt",
            "count": 4,
            "verbatim_types": ["content-quality", "question-reasonableness", "patient-behavior classification"],
            "derived_types": ["multi-turn completeness, distilled from stored judge labels and reasoning"],
        },
    }
    write_json(output / "metadata" / "prompt_availability.json", availability)
    source_paths = [
        root / "五个慢性病按照行为标签筛选后数据.xlsx",
        root / "患者打标签/四种行为分类_v2.xlsx",
        root / "实验2_多轮推理任务/话术_画像_抽取.jsonl",
        root / "实验1_单轮推理任务/外呼benchmark数据_推理_qwen35_all.xlsx",
    ]
    source_paths += sorted((root / "实验1_单轮推理评测").rglob("*.json"))
    source_paths += sorted(
        (root / "实验2_多轮推理任务/多轮推理评测").glob(
            "外呼benchmark_多轮对话_*测评结果.xlsx"
        )
    )
    manifest = []
    for path in sorted(set(source_paths)):
        manifest.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    write_json(output / "metadata" / "source_manifest.json", {"sources": manifest})
    validation = validate_scoped_release(output)
    write_json(output / "metadata" / "validation_report.json", validation)
    info = {
        "dataset_name": "MedFollowBench",
        "license": "CC-BY-NC-4.0",
        "code_license": "MIT",
        "repository": "https://github.com/iflytekmedfollowbench/MedFollowBench",
        "version": "1.0.0-rc6",
        "build_date": date.today().isoformat(),
        "scope": {
            "single_turn_source": "五个慢性病按照行为标签筛选后数据.xlsx",
            "multi_turn_source": "实验2_多轮推理任务/话术_画像_抽取.jsonl",
            "prompt_categories": ["5 extracted doctor_agent prompts", "empty patient_agent prompt file", "3 extracted evaluation prompts", "1 derived multi-turn evaluation prompt"],
        },
        "counts": counts,
        "prompt_availability": availability,
        "validation": validation,
    }
    write_json(output / "dataset_info.json", info)
    return info


def inspect_sources(root: Path, output: Path) -> None:
    signatures: dict[tuple[Any, ...], dict[str, Any]] = {}
    for path in source_files(root, output):
        rel = path.relative_to(root).as_posix()
        if path.suffix.lower() == ".xlsx":
            for sheet, rows in iter_xlsx_sheets(path):
                try:
                    header = next(rows)
                except StopIteration:
                    header = []
                key = tuple(header)
                entry = signatures.setdefault(key, {"files": [], "rows": 0})
                count = sum(1 for _ in rows)
                entry["files"].append(f"{rel}#{sheet}")
                entry["rows"] += count
        else:
            try:
                with path.open("r", encoding="utf-8") as handle:
                    if path.suffix.lower() == ".jsonl":
                        first = next((json.loads(line) for line in handle if line.strip()), None)
                    else:
                        first = json.load(handle)
                if isinstance(first, list) and first:
                    first = first[0]
                key = ("<JSON>", *(first.keys() if isinstance(first, dict) else [type(first).__name__]))
                entry = signatures.setdefault(key, {"files": [], "rows": 0})
                entry["files"].append(rel)
            except Exception as exc:  # pragma: no cover - diagnostic mode
                print(json.dumps({"file": rel, "error": str(exc)}, ensure_ascii=False))
    for number, (header, entry) in enumerate(signatures.items(), start=1):
        print(json.dumps({"schema": number, "headers": header, **entry}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("open_source_release"))
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    output = (args.output if args.output.is_absolute() else root / args.output).resolve()
    if args.inspect:
        inspect_sources(root, output)
        return
    report = build_scoped_release(root, output)
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2))
    if not report["validation"]["valid"]:
        raise SystemExit("Generated JSONL validation failed.")


if __name__ == "__main__":
    main()
