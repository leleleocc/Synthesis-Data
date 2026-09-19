# Round 4 instance assembly

Source batch: `jobs/production-construction-round3-sop4-resumed-20260905`

Assembly refreshed on 2026-09-06 after all 21 source jobs became terminal.

## Selection and transport

Round 4 contains the 18 tasks that did not clear both construction gates. The three
excluded successes are `26117e32`, `87d51bdf`, and `a3e92222`.

Every instance uses the current outer `template/`. Its transport seed is the single
file `environment/seed/build.tar.gz`; image construction restores that archive to
the unchanged runtime path `/app/build/`. The seed packer retains the greatest
numbered round as the scoring head and the greatest round carrying `rollout.lock` as
the real-rollout source when those differ. It records both roles, every omitted
round, and explicit pruning in `evidence/seed-packaging.json` inside the archive.

| Instance | Admission | Source | Scoring head | Real source | Archive |
|---|---|---|---|---|---:|
| `22ca05d3` | upstream/API interruption; no numbered round | current batch | none | none | 1.6 MiB |
| `287f5217` | Daytona startup S3 failure | latest usable round-2 build | `round-0002` | none | 8.5 MiB |
| `387bef85` | completed with reverse gap | current batch | `round-0001` | `round-0001` | 8.0 MiB |
| `453cbac9` | completed with final-task digest mismatch | current batch | `round-0002` | `round-0002` | 77.6 MiB |
| `49bb6e22` | API interruption; readable result saturated | current batch | `round-0005` | `round-0005` | 14.4 MiB |
| `52efdaea` | API interruption; latest round has no qualifying job config | current batch | `round-0005` | none | 1.4 MiB |
| `667b8927` | API interruption; final-task digest mismatch | current batch | `round-0005` | `round-0005` | 14.1 MiB |
| `78e9cba6` | Daytona startup S3 failure | latest usable round-2 build | `round-0004` | none | 0.5 MiB |
| `7d289736` | completed with a mixed-digest latest round | current batch | `round-0004` | `round-0004` | 43.6 MiB |
| `84204b2d` | completed with an unreadable latest round | current batch | `round-0003` | `round-0003` | 0.2 MiB |
| `8818d381` | API interruption; readable result saturated | current batch | `round-0001` | `round-0001` | 3.4 MiB |
| `8a9ab226` | completed with an unreadable latest round | current batch | `round-0005` | `round-0005` | 11.3 MiB |
| `95713311` | completed with final-task digest mismatch | current batch | `round-0004` | `round-0004` | 233.4 MiB |
| `ade66e4d` | eight-hour agent timeout; latest round unreadable | current batch | `round-0008` | `round-0008` | 0.2 MiB |
| `b4f12661` | API interruption; latest round unreadable | current batch | `round-0003` | none | 0.7 MiB |
| `c0ae3ac3` | Daytona startup S3 failure | latest usable round-2 build | `round-0006` | none | 0.2 MiB |
| `c43673d3` | API interruption; readable result saturated | current batch | `round-0007` | `round-0007` | 117.3 MiB |
| `eeb26954` | Daytona startup S3 failure | latest usable round-2 build | `round-0005` | none | 5.0 MiB |

The four Daytona startup errors emitted no complete current build capsule, so their
seeds use the most recent earlier job artifact recorded by the preceding assembly.
They do not use an empty artifact or a previously packed seed as their source.

## Explicit pruning

Only `22ca05d3` prunes
`evidence/local/ws-base/backend/node_modules`. The directory is a reproducible
dependency cache outside every numbered round, occupied 543 MiB, and was already
approved for removal. The source build remains unchanged and the path is recorded in
that archive's `pruned_paths`. No other content was trimmed.

## Size and file-count effect

- Corrected unpacked seeds were approximately 1.83 GiB and 90,328 files after the
  approved `node_modules` pruning.
- The 18 compressed seed archives total 541.4 MiB.
- The complete assembled directory is 550 MiB and contains 576 ordinary files.
- The former 11-instance directory was 973 MiB and 44,888 files. It remains at
  `instances-round4.pre-archive-20260906` as a recoverable backup.
- On the largest seed (`95713311`), the observed raw tar was 839 MiB and gzip level 1
  was 237 MiB. The assembled deterministic archive is 233.4 MiB.

Daytona still performs one context upload in either representation. The archive
therefore removes local per-file context walking/hashing and reduces the uncompressed
context bytes; it does not claim to fix a per-file network-request problem.

## Verification performed

- Exactly 18 instance directories, each with exactly one `build.tar.gz` and no
  `environment/seed/build/` directory.
- Every archive opened and extracted successfully.
- For every task, the extracted archive was compared with a fresh expected pack made
  from its recorded canonical source. File contents, file sizes, modes, directories,
  symlink targets, packaging report, retained rounds, omitted rounds, and pruning all
  matched.
- Files outside `environment/seed/` matched the current template for all 18 instances.
- The old round-4 directory was moved aside only after those checks passed.
- The Harbor 0.21.0 Python environment passed all 118 repository tests in 53.031
  seconds; shell syntax checks passed for the materializer, runner, launcher, and
  verifier entrypoint.
- `harbor run --print-config` resolved one archive-backed instance as one task using
  the Daytona environment, without allocating a sandbox or calling a model.
- Harbor's publisher sees 19 publishable files for archive-backed `95713311`, versus
  36,393 for its preserved predecessor.
