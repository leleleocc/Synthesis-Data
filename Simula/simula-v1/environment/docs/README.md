# Synthesis guidance and review docs

Shared synthesis guidance plus local copies of Terminal-Bench Static Checks,
Implementation Rubric, and taxonomy. Phase 07 reviews each packaged Harbor
task under `generated_task/<slug>/` against the review files. They are not
TB submission docs.

Copied into the factory image at `/opt/terminaltraj/docs/`:

| File | Used for |
| --- | --- |
| `difficulty.md` | Shared difficulty bands for phase 03 planning and every phase 04 candidate subagent; advisory context for phase 07 |
| `failure-mode.md` | Failure modes a phase 04 candidate may and may not cause |
| `static-checks.md` | Named mechanical checks on the packaged task |
| `task-implementation.toml` | Implementation rubric (`[[criteria]]`) |
| `taxonomy.md` | `[metadata].category` / `subcategory` |

This `README.md` stays in the repo. It is listed in `environment/.dockerignore` so `COPY docs/` does not put it in the image.

Phase 07 also skips TB Agent Trials `/run`, Cheat `/cheat`, Fortify `/fortify`, AI-detection, Docker Build, and Oracle Validation. Packages have no `solution/`.

For each candidate, phase 07 must spawn a static reviewer and an
implementation reviewer. Their initial reviews run in parallel when capacity
allows, against the same unchanged package. Both are read-only: the static
reviewer applies
`static-checks.md`; the implementation reviewer applies
`task-implementation.toml`, with taxonomy and difficulty context. Give them
the actual package and relevant review docs, without earlier design
reasoning or self-assessments. They return per-item findings with `name`,
`outcome` (`pass`, `fail`, or `not_applicable`), `path`, and `reason`. The
main agent retains them in `review_reports.static` and
`review_reports.implementation`. The two difficulty criteria keep honest
outcomes with `advisory: true`; do not mark them `not_applicable` just to
bypass a disagreement.

The phase 07 main agent alone merges findings, edits packages, runs
calibration and post-edit nop, and records the publication decision. After
repairs, the affected reviewer re-reads the changed package; use both when
the change affects both scopes or its impact is uncertain. Keep each
package unchanged during its review round. Process a bounded number of
candidates at once rather than spawning two reviewers for the whole batch.

`difficult` and `essential_difficulty` do not gate publication. Perceived
ease, band mismatch, or a preference for another difficulty source must not
cause rejection, repair, difficulty relabeling, or `rubric_ok=false`.
Concrete correctness, fairness, instruction/test alignment, resource, and
task-validity defects remain blocking on their own merit; do not reclassify
a difficulty-only observation as one of those defects.

## vs TB official static-checks

Dropped (TB CI / submission hygiene, not a synthesized Harbor package):

- `check-test-sh-sanity`
- `check-test-file-references`
- `check-task-fields`
- `check-changelog`
- `check-package-name` (`terminal-bench/` prefix)
- `check-allow-internet` / the `allow_internet` pair (Harbor uses `network_mode`)

Adapted:

- Scan `generated_task/<slug>/`. For `step_mode=multiple`, scan `steps/<name>/instruction.md` and `steps/<name>/tests/`.
- `check-canary` is optional (absent is fine).
- Timeout suffix says "this task", not "Terminal-Bench tasks". `check-task-timeout` also caps `[[steps]]` timeouts.
- `check-resource-sizes` still uses Harbor buckets, and synthesized packages set exactly 4 CPU, 8192 MB, and 10240 MB, with 0 or 1 GPU.
- Pytest policy (was: install in `test.sh`): pin `pytest==9.1.1` and `pytest-json-ctrf==0.5.2`. Inline bakes them in `environment/Dockerfile`; separate bakes them in `tests/Dockerfile`. `tests/test.sh` never installs packages.
- `check-dockerfile-references`: inline pytest in the agent image is required, not a leak.
- `check-pytest-version`, `check-trial-network-fetch`, `check-verifier-tooling-baked`, `check-pip-pinning` enforce bake-in-image / no verify-time install.

## vs TB official task-implementation.toml

Dropped (need `solution/` or TB metadata fields this factory does not emit):

- `solvable`
- `solution_quality`
- `difficulty_explanation_quality`
- `solution_explanation_quality`
- `verification_explanation_quality`
- `expert_time_estimate`
- `task_toml_schema` (`author_github`, explanations, `[solution]`, `allow_internet`, …)

Adapted:

- `difficult` and `essential_difficulty` are advisory observations in phase 07; there is no professional-expertise or minimum-difficulty acceptance threshold.
- Same pytest bake policy as static-checks (`verifiable`, `environment_hygiene`, `separate_verifier_configured`, `ctrf_reporting`). CTRF example is `pytest --ctrf …`, not `uvx --with`.
- Strip `solution/` / `solve.sh` from `reviewable`, `instruction_concision`, `no_extraneous_files`, `anti_cheat_robustness`, `task_security`, `task_readme`, `typos`.
- `category_and_tags` points at `taxonomy.md`.
- `resource_configuration` notes fixed timeouts: single-step verifier 600, agent 7200, build 600; each multiple-step agent 1800 and verifier 300, with the same build 600.
- `separate_verifier_configured` and `artifact_efficiency` apply only when `verifier_mode=separate`.
