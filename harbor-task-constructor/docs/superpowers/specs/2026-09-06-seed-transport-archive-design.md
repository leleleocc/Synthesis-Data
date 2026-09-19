# Seed Transport Archive Design

> **Superseded:** Cross-life rollout retention in this document is superseded by the
> [life-local evidence design](2026-09-06-life-local-evidence-design.md) and its
> [implementation plan](../plans/2026-09-06-life-local-evidence.md). Harbor regrade
> remains supported inside one life; only cross-life workspace/rollout retention changed.

## Goal

Reduce the file-count and byte cost of distributing resumed construction seeds
without changing the runtime `/app/build/` contract or the retained evidence.

## Observed boundary

Harbor 0.21.0 and its Daytona SDK already turn directory transfers into one archive
upload. The expensive part that remains is walking and hashing every Docker `COPY`
source, and Daytona's image-context archive is an uncompressed tar. In the existing
round-4 seed for `95713311`, 36,382 files occupied 819 MiB; its tar was 839 MiB and
gzip level 1 reduced it to 237 MiB.

After excluding the three cleared tasks and the previously approved reproducible
`node_modules` directory, the corrected round-4 inputs are approximately 1.83 GiB
and 90,328 files before transport archiving.

## Design

The canonical host artifacts remain unpacked and untouched. `pack-seed.py` continues
to select the scoring head and latest real-rollout source into a temporary packed
build. An archive mode then writes those build contents as one deterministic
`build.tar.gz`, preserving file contents, directories, symlinks, and executable
modes. Explicitly pruned relative paths are rejected if unsafe or absent and are
recorded as `pruned_paths` in `evidence/seed-packaging.json`.

An assembled task contains exactly one of:

- `environment/seed/build/`, for the editable repository template; or
- `environment/seed/build.tar.gz`, for a transport-optimized batch instance.

The outer Dockerfile copies `environment/seed/` and runs a small materializer. It
rejects missing or ambiguous seed inputs, moves directory seeds unchanged, or
extracts archive seeds into `/app/build/`. Everything after image construction keeps
the existing `/app/build/task`, `/app/build/evidence`, regrade, and artifact contracts.

## Round-4 assembly

Rebuild 18 failed or uncleared tasks from the completed round-3 SOP4 batch. Exclude
`26117e32`, `87d51bdf`, and `a3e92222`, which cleared both construction gates. Use
the current batch artifact when it is a valid build capsule; for the four Daytona
startup failures, use the latest earlier complete source artifact already recorded
by the previous assembly. Apply the latest outer template and corrected round policy.

For `22ca05d3` only, prune
`evidence/local/ws-base/backend/node_modules`; it is reproducible, outside all retained
rounds, and was already approved for removal. Do not trim any other content.

Build into a new sibling directory, verify every archive by extraction and manifest
comparison, then move the old `instances-round4` aside before promoting the rebuild.

## Non-goals

- Do not change SOP reasoning or timeout policy.
- Do not change the runtime build-capsule shape.
- Do not compress or delete canonical job artifacts.
- Do not infer successful scores from notes or incomplete rounds.
