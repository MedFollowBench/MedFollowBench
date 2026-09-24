# MedFollowBench

**A Chinese benchmark for behavior-adaptive protocol completion in spoken medical outbound dialogue.**

MedFollowBench evaluates both the quality of the next physician response and protocol coverage across a full conversation. It covers coronary heart disease, diabetes, cerebral infarction, traumatic brain injury, and hypertension.

## Data

| File | Task | Records |
| --- | --- | ---: |
| [`data/single_turn.jsonl`](data/single_turn.jsonl) | Next-response evaluation; disease and patient-behavior analyses | 2,169 |
| [`data/single_turn_asr.jsonl`](data/single_turn_asr.jsonl) | Spoken/ASR condition analysis of the next response | 600 |
| [`data/multi_turn.jsonl`](data/multi_turn.jsonl) | Session specifications for interactive evaluation | 500 |

- **Patient behavior:** 1,000 Cooperative, 726 Non-aligned, and 443 Inquisitive cases in the main turn-level set. The stored labels `偏离型回答` and `阻抗型回答` both map to Non-aligned.
- **Spoken/ASR conditions:** 200 Text Normalization Errors, 200 Spoken ellipsis, and 200 Homophone Error cases, with 40 cases per medical condition in each group. The `asr_type` label describes the **current (last) patient response**, interpreted with its preceding context. These are separate evaluation groups, not matched clean/noisy pairs; Text Normalization Errors is not a noise-free baseline.
- **Sessions:** 100 specifications per medical condition; 250 include a physician-visible profile and 250 do not.

The spoken/ASR file is a separate turn-level evaluation set and is not wholly contained in the 2,169-case behavior set. It may share cases or dialogue context with the main set; do not treat these files as disjoint training/test splits. Behavior labels and spoken/ASR labels describe different aspects of a response. Missing behavior labels in the spoken/ASR file are `null`, not inferred labels.

## Quick start

Python 3.10+; no third-party packages are required for loading, prompt rendering, or validation.

```bash
python scripts/validate_dataset.py
python examples/quickstart.py
python -m unittest discover -s tests
```

Load records directly:

```python
import json

with open("data/single_turn_asr.jsonl", encoding="utf-8") as stream:
    cases = [json.loads(line) for line in stream if line.strip()]
homophone_cases = [x for x in cases if x["asr_type"] == "Homophone Error"]
```

## Record format and input boundaries

All files are UTF-8 JSON Lines: one JSON object per line. Existing record identifiers are retained for matching results; identifiers are not model inputs.

| Field | Meaning |
| --- | --- |
| `id`, `task`, `script_name` | Record identifier, task, and medical-condition protocol |
| `patient_profile` | Available physician-visible profile; empty when not provided |
| `flow_requirements` | Follow-up protocol provided to the physician model |
| `conversation.messages` | Turn-level dialogue prefix; `assistant` = physician, `user` = patient |
| `prompt_components.history` / `current_patient_reply` | History before the last patient response / the current response |
| `main_behavior_type`, `patient_behavior_label` | Behavior annotations; not provided to the physician model |
| `asr_type` | Spoken/ASR label, only in the spoken/ASR file; not provided to the physician model |
| `information_nodes`, `detailed_flow_requirements` | Structured protocol fields for session setup and evaluation |
| `target_information` | Patient-side case information for the simulator; **never expose it to the evaluated physician model** |

Do not pass whole JSON records into a model prompt. For turn-level evaluation, provide only the available profile, protocol, and dialogue prefix, then generate one physician response. Internal behavior annotations and other reference fields remain hidden. The prompt helpers in [`scripts/render_prompts.py`](scripts/render_prompts.py) enforce this separation.

## Evaluation

| Metric | What it measures |
| --- | --- |
| **HCC — Human-Centered Communication** | Percentage of responses rated highest on content quality, profile grounding, and linguistic appropriateness |
| **IA — Inquiry Appropriateness** | Percentage of next-turn inquiries or dialogue decisions receiving the highest contextual-reasonableness rating; reasonable changes in inquiry order are allowed |
| **PCC — Protocol Coverage Completion** | Percentage of sessions covering every applicable protocol inquiry; an item is covered when explicitly asked or already volunteered. Conditional follow-ups are activated by observed patient responses. |

HCC/IA are evaluated on independent turn-level cases; PCC is evaluated on interactive sessions. PCC is not an average of turn-level IA and does not require every patient answer to be usable. The released rubric specifies the detailed boundary cases.

The paper uses three independent judges: HCC/IA pass by majority vote, and PCC passes only with unanimous completion. [`scripts/score_judgments.py`](scripts/score_judgments.py) implements this aggregation for saved judge outputs; it does not make network calls or supply model credentials.

## Prompts and patient simulator

- [`prompts/doctor_agent/`](prompts/doctor_agent/): five disease-specific physician prompts.
- [`prompts/evaluation/`](prompts/evaluation/): HCC, IA, and PCC rubrics.
- [`prompts/patient_agent/`](prompts/patient_agent/): patient-response prompt.
- **Patient-simulator API: forthcoming.** The public inference endpoint and client instructions will be added here when available. No simulator weights or live API endpoint are included in this release.

The same simulator configuration should be used across compared physician models. Session reproduction additionally needs the released simulator API and its configuration; loading the session specifications alone does not run the interactive evaluation.

## Privacy and intended use

The release contains de-identified text records and prompts, not source audio or private source spreadsheets. Identifying text is replaced by bracketed placeholders. Please do not attempt re-identification. This benchmark is for research and evaluation, not for clinical diagnosis, treatment, or deployment to patients. Report any suspected privacy issue without posting the identifying text publicly.

## License and citation

Data, annotations, prompts, schemas, and documentation retain the repository's **CC BY-NC 4.0** license; scripts and examples retain the **MIT** license. See [`LICENSE`](LICENSE), [`LICENSE-DATA.txt`](LICENSE-DATA.txt), and [`LICENSE-CODE`](LICENSE-CODE). Preserve attribution and check the applicable license before reuse.

Use [`CITATION.cff`](CITATION.cff) for citation metadata. The canonical repository is [MedFollowBench/MedFollowBench](https://github.com/MedFollowBench/MedFollowBench).
