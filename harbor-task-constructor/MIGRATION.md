# Migration provenance

This repository began as a curated standalone import from:

- source repository: `/Users/likuanye/CodexProjects/failure-mode-synthesis`
- old product path: `experiments/20260902-sop-allinone/template/`
- imported product commit: `bb0434ced5f89a851b533f5cd4d2e76de096692d`
- migration date: `2026-09-03`

The import preserved all other committed template bytes and executable modes. The
three deliberate template deltas were:

- `template/task.toml` renames the outer task to
  `harbor-task-constructor/construct-model-separating-task`.
- `tests/test_template_shape.py` adds the matching outer-task identity
  assertion.
- `template/environment/method/reference/minimal-harbor-task/tests/judge.toml` was
  overlaid byte-for-byte from the primary source checkout so its then-uncommitted
  local edit was not lost.

The new repository intentionally starts with one curated initial commit rather than
carrying the source repository's unrelated history. The original implementation and
design evolution remain attributable through the imported commit in the source Git
history.
