# Contributing

通过 Pull Request 提交修改，说明变更范围和验证结果。数据数量或类别变动时同步更新 `docs/statistics.md`、README 和相关元数据。

提交数据修订时，请同时提供来源、修改原因和可复现脚本。不要直接手工改写 JSONL 后省略来源说明。

变更后运行：

```bash
python3 scripts/validate_dataset.py
python3 examples/quickstart.py
python3 examples/quickstart.py --task multi_turn
```