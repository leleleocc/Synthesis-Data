# harbor-constructor

AIO sandbox tenant for building Harbor tasks. The agent operates in four roles
that are mechanically routed each iteration by `template/route.sh`:

| Role | Responsibility |
|------|---------------|
| `builder` | Establish a mechanically valid task with nop=0, oracle=1 |
| `measure` | Run `run-two-models.sh both/regrade` and publish a compact round |
| `analyst` | Attribute scores, pick one verifier hypothesis, write `card.json` |
| `refine` | Execute the minimum change from `card.json`, trigger next round |

Delivery gate (enforced by `template/verify.sh`):
- `target_mean < 0.7` AND `R > 0.2`
- Round task digest matches final task
- `resume.md` present

## Layout

```
sandbox/aio/tenants/harbor-constructor/
  task.env.example          credential template (copy to task.env, fill in)
  template/
    PROMPT.md               runner entry point — reads route.sh, enters role
    route.sh                mechanical router (7 conditions, tree state only)
    init.sh                 provision: install harbor + claude (root, idempotent)
    verify.sh               delivery gate (programmatic, no model cost)
    roles/
      builder.md
      measure.md
      analyst.md
      refine.md
    method/
      run-two-models.sh     fork of template/environment/method — retain removed
      parse_scores.py       fork — collected_full_workspaces removed,
                            timeouts_dominate added
  tests/
    test_route.sh           route.sh branch tests
```

## Credentials

Copy `task.env.example` → `task.env` and fill in all values. The host injects
these as environment variables; `task.env` itself never enters the sandbox.

Required:
- `DAYTONA_API_KEY`
- `HARBOR_JUDGE_BASE_URL` / `HARBOR_JUDGE_AUTH_TOKEN`
- `HARBOR_TARGET_*` (model name, base URL, auth token, optional reasoning effort)
- `HARBOR_SOLVER_*` (same)
- `ANTHROPIC_API_KEY`

## Environment variables (optional tuning)

| Variable | Default | Purpose |
|----------|---------|---------|
| `SOP_TASK_ROOT` | `/home/app/workspace/task` | task directory |
| `SOP_EVIDENCE_ROOT` | `/home/app/workspace/evidence` | compact evidence root |
| `SOP_RUNTIME_EVIDENCE_ROOT` | `/home/app/workspace/runtime/harbor-evidence` | full runtime jobs |
| `SOP_FRESH_BUDGET` | `5` | rollout input changes allowed for the whole task, not per life; the tally lives in `resume.md` and nothing in code enforces it |

Workspace markers (empty files next to `.done`, copied into `status.json`):

| File | Who writes it | Effect |
|------|---------------|--------|
| `.measuring` | `run-two-models.sh` (not `regrade`) | tells the batch reconciler this line occupies Daytona |
| `.blocked` | refine, when a fresh round is needed but budget is 0 | reconciler stops opening sandboxes until someone `rm`s it |
