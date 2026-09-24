# Packaging and review validation

## Harbor validation

Harbor validates each assembled task with the installed library:

```python
from harbor.models.task.paths import TaskPaths
from harbor.models.task.config import TaskConfig
from harbor.models.task.task import Task

paths = TaskPaths(task_dir)
assert Task.is_valid_dir(task_dir)
TaskConfig.model_validate_toml(paths.config_path.read_text())
```

The Harbor import is required; a missing library fails the phase. Required
content is `task.toml`, `environment/` with Dockerfile or compose, and
instruction/verifier entries at the root for single-step tasks or under
declared `steps/<name>/` for multiple-step tasks. A native step may use a
local verifier or fall back to shared `tests/test.sh`.

## Assembly

Phase 06 is assembly only. Copy the candidate environment, instruction,
manifest, tests, and declared steps into one package; write a short README
with candidate id, slug, source URL/commit, and provenance; and write a
manifest with candidate id, package path, deployment mode, and pinned commit.
Do not copy synthesis state, source checkouts, scratch files, hidden answers,
or `.env`. Use a unique lowercase kebab-case slug of at most three words.
Initially preserve candidate bytes. Fix missing copies and `[task].name`
identity in the package. TOML repairs must preserve the parsed candidate
configuration apart from that name. Nop may require repairs to the assembled
environment; the final copy gate allows these while preserving instructions,
tests, steps, and task configuration. Preserve all slot deployment dimensions.
An environment repair must stay self-contained: keep the candidate `FROM` line
and the pinned source checkout. Do not retag a factory-local image or `FROM` a
tag that exists only on this host (`suricata-base:02`, `synth-env`, or any
other image a clean sandbox cannot pull). A nop pass against such a base is
not a successful package.

## Nop

Phase 06 runs nop for every package; phase 07 reruns it after any package edit:

```bash
harbor run -a nop -p <task-dir> --jobs-dir "$SIMULA_JOBS_DIR"
```

Packages whose actual `[environment].gpus > 0` add `-e daytona` and inherit
`DAYTONA_API_KEY` from the factory environment. Reward `0` is the pass: the
image built and a no-op agent did not complete the task. Any exception,
missing reward, or nonzero reward fails the package. Repair within the phase's
ownership and rerun; phase 06 cannot repair an already-solved task by changing
its instruction or tests. A build failure is not fixed by deleting the source
checkout or compile steps, or by basing the package on an image already built
in this factory. Restore the self-contained Dockerfile and rebuild from the
candidate base. A missing GPU key is a failure, not a skipped
trial. Keep the key in the factory environment; do not copy `.env` into an
image or package.

## Independent reviews

Phase 07 spawns two read-only reviewers per candidate. Run the initial pair
in parallel when capacity permits; bound concurrent candidates. Give each
the actual package and its assigned documents under `/opt/terminaltraj/docs/`:

- Static Review Agent: `static-checks.md` (Static Checks).
- Implementation Review Agent: `task-implementation.toml` (Implementation Rubric),
  `taxonomy.md` for category/subcategory, and `difficulty.md` for
  advisory context.

Start each with independent context limited to this assignment. Reviewers
may parse files and check syntax, but cannot execute package code, calibrate,
run nop, edit files, or decide publication. Keep the package unchanged until
both reports finish. Each enumerates all named checks in its assigned source
and returns `name`, `outcome` (`pass`, `fail`, `not_applicable`), `path`, and
`reason`. N/A must cite the applicability rule; missing reports, omitted
criteria, and failed agent runs are incomplete reviews.

Use the documented applicability rules: canary absence is acceptable;
separate-verifier checks and `artifact_efficiency` apply to separate mode;
trial-network and baked-tooling checks apply to every package. Apply the local
checks and rubric; skip Agent Trials, Cheat, Fortify, AI detection, Docker
Build, and Oracle Validation.

`difficult` and `essential_difficulty` retain honest outcomes with
`advisory: true`. Difficulty alone cannot cause rejection, repair, relabeling,
or `rubric_ok=false`, including through another criterion. Correctness,
fairness, alignment, security, resource, and validity defects remain blocking.

## Repair and re-review

The main agent alone merges findings, repairs packages, executes calibration
and nop, writes review state, and decides publication. Prefer the smallest
environment or test change. Edit root or step instructions only for shape
defects: headings, absolute paths, or timeout suffix. Preserve the goal and
oracle. Too-loose or too-strict findings need the smallest assertion edit in
the selected test tree followed by both calibration directions from `tests.md`.

After an edit, ask affected reviewers to inspect current files with a concise
change summary. Shape fixes need static re-review; assertion changes need
implementation re-review and affected static checks; environment, manifest,
or deployment changes need both. Use both when impact is uncertain. Retain
unaffected findings so final reports remain complete. Repeat this process for
edits arising from calibration or nop, and validate the final package before
publication. Store reports in `07_review.json`; `release_candidate_ids` joins
`generated_task/manifest.json` without a separate release manifest.

Harbor layout examples:
https://github.com/harbor-framework/harbor/tree/main/examples/tasks.
