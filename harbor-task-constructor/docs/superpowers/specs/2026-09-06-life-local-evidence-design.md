# Life-Local Evidence Retention Design

## Goal

Keep regrade useful inside one construction life without carrying full nested
Harbor workspaces into the next life or returning them in the outer artifact.
Every newly launched life starts with a fresh target/solver measurement, while
the host still receives the final task, resume notes, scores, and model
trajectories needed for review.

## Evidence behind the change

Round 4 exposed two distinct costs in the previous design:

- one task accumulated about 1.8 GiB in its fresh round and another 1.5 GiB in
  its regrade round, filling the requested 5 GiB Daytona disk;
- another task produced an approximately 1.7 GiB `/app/build` artifact and
  remained in artifact collection for more than two hours; and
- Harbor regrade copied the recorded `/workspace` into the derived trial, so a
  regrade round duplicated rather than referenced its source workspace.

Compressing the next seed reduces upload cost but does not remove workspace
duplication, disk peaks, or artifact-collection work. The retention seam must
therefore move before outer artifact collection.

## Decisions

### Cross-life capsule

`scripts/pack-seed.py` becomes an allowlist packer. A next-life seed contains:

```text
build/
├── task/
└── evidence/
    ├── resume.md
    ├── seed-packaging.json
    └── previous-life/
        ├── index.md
        └── rounds/
            └── round-NNNN/...
```

The complete `task/` tree is copied byte-for-byte, including its `tests/` and
`solution/`. `resume.md` is copied byte-for-byte. The selected most recent usable
reference generation is copied under `previous-life/rounds/`, including trial
locks, results, Reward Kit `reward-details.json`, manifests, logs, and the
target/solver trajectories kept by the compact publisher. Full workspaces,
agent session caches, dependency trees, and build caches are absent by
construction. The original outer job artifact remains on the host as the
complete historical source.

When the completed life contains at least one committed compact top-level
round, the packer replaces the inherited `previous-life/` with those current
rounds. When the life ended before committing any top-level round, the packer
instead carries forward the existing compact `previous-life/rounds/` once. It
never combines the two sources. This preserves the most recent usable evidence
through an early failure while keeping exactly one reference generation and
preventing accumulation. It applies no byte or file-count limit; structural
allowlisting and the single-generation window are the size controls.

`previous-life/index.md` is a generated, short map containing the retained
round names and kinds, the latest score round, the latest real trajectory
round, and the exact relative paths to their evidence. The packaging report
records whether the reference came from current-life rounds, a carried-forward
reference, or neither, plus retained round names and total reference bytes and
files. Neither file derives or rewrites scores.

Consequences:

- round numbering is scoped to one life;
- the first measurement in every new life is a real target/solver rollout;
- regrade never searches a preceding life's collected evidence;
- resetting runtime sources does not reset a previously reached rollout-input freeze; and
- previous conclusions travel through `resume.md`, while the index exposes raw
  previous-life evidence only for a concrete attribution question.

The archive transport remains available for tasks whose own file count is
large. Since packing is allowlist-based, the `--prune` escape hatch and the
latest-round/source-round selection policy are removed.

### Legacy bootstrap

Existing recovered tasks may still store a full real round and a thin regrade
as `round-*.tar.gz`. Those archives are not accepted as canonical input by the
new packer and are never unpacked inside a construction sandbox. Before the
first life using this design, a host-side one-time importer safely extracts a
trusted Harbor-produced archive to temporary storage, invokes the same compact
publisher for every arm/run, writes `round.json` last, and deletes the temporary
extraction. The resulting compact top-level rounds are then passed through the
normal seed packer and become `previous-life/rounds/`.

The importer preserves the archive's round name, copies run logs and exit
codes, includes Agent files only for a real round, and requires an explicit
source round from the imported legacy life for regrade provenance. It refuses multiple
top-level roots, unsafe archive members, an existing destination, or a full
workspace path in its output. This compatibility path is host-only and is not
part of the Agent-facing runtime surface.

### Life-local runtime state

Full nested Harbor jobs live below a new, uncollected root:

```text
/app/runtime/harbor-evidence/
└── round-NNNN/
    ├── rollout.lock
    ├── target/run-NNNN/jobs/...
    └── solver/run-NNNN/jobs/...
```

`run-two-models.sh` owns this root through
`SOP_RUNTIME_EVIDENCE_ROOT`, defaulting to
`/app/runtime/harbor-evidence`. Only the current outer life can use it. A real
round's complete jobs remain there while they are the latest reusable regrade
source.

Regrade source selection reads only this runtime root. If it is empty, regrade
fails before allocation or Harbor invocation and tells the Agent to run a real
two-arm measurement. This is expected on every new life.

After any regrade result has been compactly published, its derived full jobs are
removed from runtime state because Harbor has already duplicated the source
artifacts and a regrade can never be a later regrade source. A publication
failure keeps those jobs for diagnosis. After a newer complete real two-arm
round is published, older runtime rounds are removed. At steady state, runtime
retains at most one completed real source plus the active invocation.
Interrupted state remains available for current-life diagnosis until the Agent
admits another invocation. Before launch, every mode retains the latest complete
real source when one exists; an explicit `--round` repair additionally protects
its selected round with `.active`, and a new default real rollout adds only its
new active round. A readable replacement real round becomes the retained source
only after compact publication succeeds. If the replacement fails, the previous
source remains available and the partial active round remains for diagnosis
until the next invocation removes that superseded partial state. Compact logs
and partial metadata remain collected. Repeated failures therefore do not
accumulate unbounded workspace copies.

Ad-hoc nop/oracle Harbor jobs also use uncollected runtime storage at
`/app/runtime/harbor-checks`. Their small result summary and necessary diagnostics
may be recorded under collected evidence; their job trees and
`artifacts/workspace` directories may not. The score parser detects this structural
violation before delivery and directs cleanup without another model or verifier run.

The outer environment requests 10 GiB rather than 5 GiB of storage; Daytona's
support for that request size has been confirmed. Retention controls
steady-state use, while the additional headroom covers Harbor's unavoidable
source-plus-derived copy peak during regrade.

### Collected evidence

The existing `/app/build/evidence/round-NNNN/` shape remains the parser and outer
verifier input, but each run is a compact projection rather than the source job.
The runner writes `harbor.log` and `exit-code` directly into this collected run
so infrastructure failures remain inspectable even when Harbor does not finish.
After Harbor exits, an internal evidence-retention module publishes:

- job-level `config.json` and `result.json` when present;
- every trial's `lock.json`, `result.json`,
  `verifier/reward-details.json`, and `artifacts/manifest.json` when present;
- for real model runs, `agent/trajectory.json` and `agent/claude-code.txt` when
  present; and
- a round-level `round.json` describing `schema_version`, `kind`, and, for
  regrade, its current-life `source_round`.

The projection never copies `artifacts/workspace`, agent session caches,
dependency trees, or other files. Regrade projections omit agent trajectories
because those are identical copies of the source round's agent execution.

Publishing is allowlist-based. Each current invocation's compact `jobs/` tree is
built under its collected run directory and renamed into place; `round.json` is
written atomically after all current run projections succeed. Existing runs in
an incomplete round are not recopied when a missing arm is appended. A missing
file is not synthesized. The parser therefore continues to mark an incomplete
trial or round unreadable from its actual retained evidence.

`rollout.lock` remains private runtime state. Collected rounds use `round.json`
so historical evidence cannot be mistaken for a reusable regrade source.
Job-level `lock.json` is also omitted: trial locks carry the model, task digest,
and regrade source provenance used for attribution.

Compact publication happens after every `run-two-models.sh` invocation, not at
the end of the outer construction task. The runner allocates matching public
and runtime round/arm/run paths, writes `harbor.log` and `exit-code` directly to
the public run, waits for the Harbor children, atomically publishes each
allowlisted `jobs/` projection, and writes `round.json` only after the whole
invocation is publishable. It then runs the parser against the compact public
round. Consequently, a later Agent timeout does not erase compact rounds that
were already committed.

### Runner interface

The Agent-facing commands stay unchanged:

```text
run-two-models.sh both|target|solver|regrade
parse_scores.py ROUND --final-task TASK
parse_scores.py --last EVIDENCE --final-task TASK
```

The runner hides allocation across the runtime and collected roots, compact
publication, and retention. `--round` may repair an incomplete real round only
inside the current life. It cannot name a previous-life round because those
rounds are absent from runtime state.

One `run-two-models.sh` invocation owns the evidence roots at a time. The runner
holds a root-confined invocation lock through preflight, execution, publication,
and retention; another top-level invocation fails before allocation. This does
not reduce useful model parallelism: `both` still launches target and solver
concurrently, and `--concurrency` still controls trials inside each Harbor job.
The exclusivity matches the SOP rule that the main Agent alone owns formal
measurements and prevents one invocation from deleting another's source.

The runner's help and regrade errors explicitly say that regrade is current-life
only and that a new life must establish a fresh real source first.

### SOP behavior

The SOP keeps the verifier-first light loop, with one lifecycle clarification:

1. read `resume.md`; when `previous-life/index.md` exists, read that short index
   next without recursively loading its rounds;
2. keep the incoming task unchanged through the first current-life fresh run,
   except for a mechanical defect that blocks nop/oracle or Harbor wiring;
3. use indexed `reward-details.json` only for a score/verifier hypothesis and
   indexed trajectories only for a model-behavior hypothesis, comparing the
   available target/solver samples rather than relying on one pair; task-local
   trajectory work must answer a named verifier decision rather than perform
   batch-level model profiling;
4. if this life has no reusable runtime source, run fresh even when the notes
   describe a previous regrade-ready rollout;
5. after a current-life fresh rollout, use regrade for `tests/**` and synchronized
   `solution/**` changes while rollout input remains unchanged; and
6. use compact current-life trajectories for score-delta attribution,
   superseding the previous-life reference after fresh, and escalate
   to the current-life runtime workspace only when the compact record cannot
   answer the current question.

The Agent must not reconstruct or import old workspaces. It continues toward a
complete latest round without waiting for user interaction and uses subagents
for independent analysis when available.

### Host retention

The complete outer artifact for each life remains the host-side historical
record. The outer task already collects `/app/build`, so normal completion,
score failure, Harbor failure, and Agent timeout all return the last written
`task/`, `resume.md`, inherited compact reference, committed current-life
rounds, and any partial run logs that reached the collected root. A platform
failure that deletes the sandbox before outer artifact collection is outside
this guarantee. `/app/runtime/harbor-evidence` is never part of the returned
artifact.

Because `/app/build` is compact, the returned artifact has no nested workspace
copies. The next-life packer reads it and allowlists `task/`, `resume.md`, and
exactly one compact reference generation. Committed current-life top-level
rounds replace the inherited reference; if there are no committed current-life
rounds, the inherited reference is preserved rather than silently lost.

No separate copy of `tests/` is needed: the authoritative tests are already in
the returned `task/` tree.

## Code-delta boundary

Target/solver development diffs are desirable analysis artifacts, but they are
not part of this change. A faithful diff needs a common pre-Agent workspace
baseline and a post-Agent workspace. The existing collected artifacts guarantee
only the latter.

After this retention change, a separate feasibility check may inspect Harbor's
runner for a common pre/post Agent seam. A later design may add generic tree
deltas only if that seam works across tasks without changing each task's startup
logic. Git-only inference, per-task launch adapters, and treating a final
workspace as an exact diff are rejected.

## Failure behavior

- A compact-publish failure returns nonzero and keeps the runtime source for
  diagnosis until another invocation is admitted; it never reports a readable
  new round.
- A regrade without a current-life source fails before creating a collected
  round.
- A concurrent top-level runner call fails before allocation and points to the
  active invocation; it never waits in the background.
- A failed regrade that publishes successfully keeps its compact diagnostics,
  removes its full derived copy, is not a source, and does not delete the last
  real source.
- Runtime cleanup never touches `/app/build/task`, `/app/build/evidence`, or an
  active invocation.
- Seed packing rejects a missing task, missing resume file, unsafe destination,
  ambiguous archive target, or a supposedly compact round containing a full
  workspace/session/dependency/cache path, without modifying the source.
- Seed packing prefers committed current-life rounds over inherited reference
  rounds and falls back to the inherited reference only when no committed
  current-life round exists; it never merges both generations.
- Legacy archive import is atomic and host-only. A rejected archive leaves no
  destination round and does not modify the source archive.

## Verification

Automated tests cover the allowlist seed, zero-round reference fallback,
deterministic archive, one-time legacy import, compact projection, parser
compatibility, current-life-only source selection, partial failure evidence,
and runtime retention. Existing scoring, credential isolation, concurrency,
signal cleanup, and task-readiness tests remain green.

The production gate uses one actual legacy-archive, regrade-ready task and
Harbor 0.21.0 on Daytona:

1. import its old real/regrade archives once and pack them as indexed
   `previous-life` evidence without a workspace;
2. run one fresh target/solver round;
3. run regrade against that current-life source;
4. prove both current rounds parse from compact collected evidence;
5. prove `/app/build/evidence` contains no `artifacts/workspace` directory;
6. prove runtime retains the real source but not the completed regrade copy;
7. pack a next-life seed and prove it contains the task, resume, packaging
   report, index, and exactly the immediately preceding life's compact rounds;
   and
8. prove regrade in that new life refuses to run until a fresh source exists.

Record paths, byte counts, file counts, commands, exit statuses, and score
reports. Mock-only evidence is not sufficient for release.

## Non-goals

- Replaying or regrading across lives.
- Carrying or merging more than one compact reference generation.
- Automatically loading previous-life trajectories into the Agent's context.
- Capturing or applying target/solver code diffs.
- Changing reward semantics, target thresholds, verifier-quality guidance,
  timeout policy, model identity, or Harbor's retry policy.
