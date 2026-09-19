# Harbor Task Constructor

A standalone Harbor outer task that asks an agent to construct and measure a real
Harbor task whose programmatic score separates a target model from a solver model.

> Taking over this project? Start with [`HANDOFF.md`](HANDOFF.md) for the design
> model, construction lifecycle, verified runtime state, unresolved correctness
> gate, and continuation runbook.

## How it works

The host injects one seed task and starts an outer Harbor job. The construction
Agent first proves the task's nop/oracle mechanics, then measures fresh target and
solver rollouts. It attributes one verifier hypothesis at a time, prefers a small
tests/solution change, and regrades compatible current-life rollouts before paying
for another model run. A passing life returns the task plus compact score evidence,
selected trajectories, and a resume note; the host can pack those conclusions into
the next life without carrying a complete workspace. See the handoff for the design
rationale and `template/environment/method/sop.md` for the exact Agent procedure.

## Repository layout

- `template/` — the runnable outer Harbor task.
- `template/instruction.md` — the agent's assignment and delivery contract.
- `template/environment/method/sop.md` — the six-step construction loop.
- `template/environment/method/reference/minimal-harbor-task/` — a minimal syntax anchor.
- `template/tests/` — runner, parser, verifier, reference, and shape regression tests.
- `HANDOFF.md` — design model, verified state, open correctness work, and takeover runbook.
- `docs/contract.md` — the host-side operating and evidence contract.
- Batch SOP review — when a construction batch finishes or its cutoff is frozen, follow
  `docs/batch-sop-review.md` to derive evidence-backed SOP candidates from its artifacts.

## Inject a task

For a first life, replace `template/environment/seed/build/task/` with the real
starting Harbor task and leave the empty handoff skeleton at
`template/environment/seed/build/evidence/resume.md`.

For a resumed life, keep the collected `build/` artifact on the host and create a
new seed with `pack-seed.py`; do not copy a complete prior artifact into the next
life. Never overlay seed representations or build trees: files removed in the
preceding life must not reappear from the repository seed.

```bash
python3 scripts/pack-seed.py SOURCE_BUILD NEW_BUILD
python3 scripts/pack-seed.py SOURCE_BUILD template/environment/seed/build.tar.gz --archive
```

The packer copies the task and resume notes plus one allowlisted generation of compact
evidence. If the source life has compact rounds, they replace an inherited reference;
if it has none, the existing compact reference is carried forward. It never merges
these sources or changes the source artifact. `evidence/previous-life/index.md` is the
short map to retained score details and real-run trajectories; it is for attribution,
not for regrade. Current-life compact evidence is read through its parser/current-round
path instead.

For a trusted legacy `round-*.tar.gz` archive, normalize it once on the host before
packing it. This compatibility command is not available inside the construction
environment:

```bash
python3 scripts/import-legacy-round.py ARCHIVE EVIDENCE_ROOT --kind real
python3 scripts/import-legacy-round.py ARCHIVE EVIDENCE_ROOT --kind regrade --source-round round-NNNN
```

The editable template contains `environment/seed/build/`. Batch instances may replace
that directory with the single `environment/seed/build.tar.gz`; the image build
materializes either representation into the same runtime `/app/build/`. A seed must
contain exactly one representation. Replace the seed only before dispatch, not while
a batch is running.

The outer and constructed tasks must keep public networking. Supply the target,
solver, judge, and environment values declared by `template/task.toml` through the
normal Harbor job configuration, then run `template/` as the task path.

The outer task intentionally has no `solution/` because it is not run with Harbor's
oracle agent; the task produced inside `build/task/` must still ship a valid solution.

## Run a production life

Copy `.env.example` to a location outside this repository, fill in its values, and
restrict access to the resulting file:

```bash
cp .env.example /secure/path/harbor-task-constructor.env
chmod 600 /secure/path/harbor-task-constructor.env
```

The file is trusted shell input and is sourced by the launcher. Do not use an env
file obtained from an untrusted source. The constructor, target, solver, and judge
endpoints must support the models assigned to them; target and solver model names
must resolve to the same identities Harbor records in their trial locks.

Use the launcher in three gates. `check` validates launcher inputs and the local task
path, then prints the Harbor JobConfig; its output does not expand nested task values,
and it makes no remote or model call:

```bash
scripts/run-production.sh check \
  --env-file /secure/path/harbor-task-constructor.env
```

`install` allocates the Daytona environment and validates the outer agent setup, but
does not execute the task:

```bash
scripts/run-production.sh install \
  --env-file /secure/path/harbor-task-constructor.env \
  --job-name ledger-install-smoke \
  --yes
```

After both gates succeed, start one real construction life:

```bash
scripts/run-production.sh run \
  --env-file /secure/path/harbor-task-constructor.env \
  --job-name ledger-life-0001 \
  --yes
```

Jobs default to the ignored `jobs/` directory. Pass `--jobs-dir /durable/path` when
the repository is not the desired storage location. The launcher intentionally fixes
the outer job to one attempt, one concurrent trial, and zero retries; the constructor
itself owns the nested target/solver measurement loop.

For a resumed life, run `pack-seed.py` against the preceding collected build and use
its output as `template/environment/seed/build/`, or archive that packed output as
`template/environment/seed/build.tar.gz`. Move the old representation aside first if
it must be retained; never merge or overlay the two. Reference scores and trajectories
remain available through `previous-life/index.md`, but the first nested measurement in
the new life is always fresh; only a current-life real run can later supply regrade.

## Validate without model calls

Run the tests from a Python 3.11+ environment that can import Harbor 0.21.0:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
bash -n template/environment/method/run-two-models.sh
bash -n scripts/run-production.sh
bash -n template/tests/test.sh
```

First, resolve launcher inputs and validate the local task path with Harbor's
`Task.is_valid_dir`. The printed JobConfig does not expand nested task values, start
an environment, or make a model call:

```bash
scripts/run-production.sh check \
  --env-file /secure/path/harbor-task-constructor.env
```

Then use the same Task API explicitly to validate layout/config validity and assert
the exact nested task values:

```bash
python3 - <<'PY'
from pathlib import Path
from harbor.models.task.task import Task

task_path = Path("template")
assert Task.is_valid_dir(task_path)
config = Task(task_path).config
assert config.environment.storage_mb == 10240
assert config.agent.timeout_sec == 28800
assert config.verifier.timeout_sec == 600
assert config.environment.build_timeout_sec == 900
assert config.environment.network_mode.value == "public"
assert config.environment.cpus == 2
assert config.environment.memory_mb == 4096
assert [(artifact.source, artifact.destination) for artifact in config.artifacts] == [
    ("/app/build", "build")
]
PY
```

## Provenance

This repository was split from `failure-mode-synthesis`. See `MIGRATION.md` for the
exact source boundary and imported commit.
