# Changelog

## GitHub release preparation - 2026-09-17

- Applied the MedFollowBench project name and repository citation metadata.
- Licensed data and prompt content under CC BY-NC 4.0 and Python code under MIT.
- Stored JSONL directly in Git instead of Git LFS, preserving source data bytes.
- Clarified the missing patient-simulator components and fixed the release-scope table.

- Corrected task descriptions to single-turn and multi-turn evaluation sets; removed training/test proportions.
- Documented evaluation inputs, reproduction limitations, and evaluation configuration checklist.
- Kept release data and original prompts unchanged.

## 1.0.0-rc6 - 2026-09-15

- Added a multi-turn process-completeness evaluation prompt distilled from stored judge labels and reasoning.
- Documented the prompt as derived rather than verbatim source content.

## 1.0.0-rc5 - 2026-09-15

- Enforced verbatim-only prompt extraction from existing source fields.
- Replaced normalized doctor prompts with one existing prompt per disease.
- Restored existing evaluation prompts without placeholder rewriting.
- Emptied the patient Agent and multi-turn completeness files because their original prompts are absent.

## 1.0.0-rc4 - 2026-09-15

- Corrected the multi-turn split to the 500 records in `话术_画像_抽取.jsonl`.
- Removed the 10,232-record raw annotation pool from the release data.
- Updated schemas, metadata, documentation, and validation counts.

## 1.0.0-rc3 - 2026-09-15

- Replaced prompt catalogs and occurrence logs with ten clean text templates.
- Added one doctor Agent prompt for each of the five disease groups.
- Added one patient Agent prompt and four evaluation prompts.
- Removed model names, case IDs, hashes, invocation metadata, and experiment traces from prompt files.

## 1.0.0-rc2 - 2026-09-15

- Limited single-turn data to `五个慢性病按照行为标签筛选后数据.xlsx`.
- Defined multi-turn data as `五种慢性病的原始10000数据.xlsx`.
- Split doctor Agent prompts and evaluation prompts into catalogs and occurrence maps.
- Recorded missing patient Agent and multi-turn evaluation prompt provenance.
- Added schemas, source checksums, validation, license draft, citation, and dataset card.
