# AIO Sandbox — a construction scaffold on Volcengine

A tenant submits a template — a `PROMPT.md` and an optional `init.sh` — and a
runner inside a Volcengine **AIO Sandbox** drives `claude -p` against a working
tree until the work declares itself done. The tree lives on NAS and outlives any
one sandbox; TOS carries the archives and is the host's only window onto a run.

Harbor is the first tenant, not the thing itself. New tenants start at
[`ONBOARDING.md`](ONBOARDING.md). `TODO.md` is what is still owed;
`examples/hello-world/` is a template you can copy.

Branch: `tenant/harbor-constructor`.
Design: [`docs/superpowers/specs/2026-09-10-aio-sandbox-transport-design.md`](../../docs/superpowers/specs/2026-09-10-aio-sandbox-transport-design.md)
(written before the pivot; see TODO section 9 for the vocabulary that changed).
Batch construction: [`docs/superpowers/specs/2026-09-14-batch-construction-design.md`](../../docs/superpowers/specs/2026-09-14-batch-construction-design.md).

## Storage selection — TOS vs NAS

The public `CreateSandbox` reference (`Action=CreateSandbox&Version=2024-06-06`)
documents only `InstanceTosMountConfig`, which made NAS look application-level and
unparameterizable. That is wrong: `volcengine-python-sdk==5.0.48` carries
`InstanceNasMountConfig` alongside it, and a TOS mount point carries its own
`BucketName` and `Endpoint` rather than inheriting the application's. Both mounts
are per-instance — which matters because a round runs ~18 tasks in parallel and
each needs its own workspace.

With one condition, learned from an API error rather than from documentation: an
instance mount point is an **override**, and the application's online revision
must already declare a mount point at the same `LocalMountPath`. Removing the
application's NAS config does not free the path, it forecloses it —
`local mount path /mnt/nas not exist in fn online revision nas mount points`
(the path was called `/mnt/nas` when that error was recorded; it is `/home/app`
now). So the application declares all four mount points once, and each instance
re-points the ones that are task-specific via `BucketPath` / `RemotePath`. The
table lives in `sbx/mounts.py` and both sides are generated from it.

| Dimension | TOS mount | NAS mount |
| --- | --- | --- |
| Per-instance parameterization | Yes — `TosMountPoints[].BucketPath` | Yes — `NasMountPoints[].RemotePath` |
| POSIX fidelity (modes, symlinks, rename, append) | Modes flattened to 777 | NFS, near-complete |
| Small-file performance (90,328 files) | Worst case | Strong |
| Large sequential objects (`build.tar.gz`) | Strong | Adequate |
| Cost / durable archive | Cheap, unbounded | Provisioned capacity, VPC-bound |

**Decision: split roles, do not choose one.** Never stage a 90k-file tree
unpacked on TOS — that is object storage's worst case, and its partial POSIX
semantics lose exactly the modes and symlinks that make a tree runnable.

- **NAS = the workspace.** The tree lives there and outlives any one execution.
  It is mounted at `/home/app`, so the working tree is `/home/app/workspace`.
- **The sandbox = the execution environment**, stateless and disposable.
- **TOS = durable storage**, guarding against an abort or an execution that
  yields no final result, and serving later debugging. It is also the host's only
  window, since the host cannot mount NAS. It carries whole-tree snapshots as
  single archives — large sequential IO only.

Transport carries bytes and nothing else: no seed selection, no allowlist, no
life counter.

## Round trip

`sbx task create <id> <dir>` packs, pushes, and creates in one call; the instance
does the rest. `sbx task status <id> --follow` is the window onto it.

The task's TOS prefix carries three things. `bootstrap.sh` and `runner/` are not
among them — they live in the shared `_runtime/<version>/` prefix, which every
sandbox mounts read-only at `/mnt/runtime`:

```
/sandbox/<task-id>/
  seed/<stamp>.tar.gz   input: the packed tree, pushed from the host
  archives/<run-id>.tar.gz   output: what the runner writes back
  runs/<run-id>/        bootstrap.log and result.json, one directory per run
  status.json           overwritten at phase/iteration bounds (host GETs this;
                        do not list runs/ just to learn if the line is alive)
```

A batch is the same layout one level down: `/sandbox/<batch>/<candidate>/`, plus
`/sandbox/<batch>/batch.json` (`{template, created_at}`). Nested task-id
`<batch>/<candidate>` is legal; `CreateSandbox` then also labels `batch=<batch>`.

Each archive and seed carries a `.sha256` sidecar and a `.manifest.json`
alongside it. The sidecar is written last, and one without a match is treated as
absent.

**How the startup script is injected.** Two things constrain this.

The script cannot replace the application. The platform gates readiness on the
application listening on its port, so a command that only runs the script never
opens one and the instance dies with `function_cold_start_timeout` after ~29 s.
And pointing `InstanceImageInfo.Command` straight at the script loses a race,
since the runtime mount is not necessarily up when the container starts.

So the two halves are split. `InstanceImageInfo.Command` starts the application
and nothing else:

```sh
exec /opt/gem/run.sh
```

and `bootstrap.sh` is triggered by the image's own `RUN_HOOK_POST_READY`, passed
per sandbox in `Envs`. The hook fires after the mounts are up, so the race is
gone rather than waited out, and the hook's output lands on the main process
stdout that `GetFunctionInstanceLogs` collects.

Generated by `sbx/faas.py`, not hand-written per task. Reading `bootstrap.sh` off
the mount is itself the first inbound test. The task-specific mounts are already
scoped to the task — `BucketPath` is `/sandbox/<task-id>` and `RemotePath` is
`<nas-prefix>/<task-id>` — so no path inside the sandbox carries the id, and
`Envs` passes it only as a label.

The host watches a run with `sbx.sh task status <task-id> --follow`. That command
GETs `status.json` and each run's `result.json`; it does not walk the jsonl
chunks under `runs/`. It reads TOS over the *public* endpoint, since the
`ivolces` endpoint in `.env` is what the instance mounts through and does not
resolve outside the VPC.

**What runs inside the instance.** `bootstrap.sh` is a ~50-line shim: it waits for
the `runner/` package to appear on the mount, finds an interpreter, and `exec`s
`python3 -m runner`. Everything else is the `runner/` package — standard library
only, so there is no install step standing between the instance and its first
line of log. The image ships `/usr/bin/python3` 3.10.12. Each run writes a log and
a `result.json` to `<tos>/runs/<stamp>-<host>-<pid>/`, since the host cannot see
NAS:

| Phase | |
| --- | --- |
| 1 preflight | mounts, capacity, and what is already running in this container; stops before touching anything if a mount is missing |
| 2 lease | take `<nas>/.lease`, or stand down because another run is alive |
| 3 attach | reuse the NAS tree if `.attached` is there, else restore — the newest verified archive, or the seed if this task has never produced one |
| 4a init | `init.sh` from the template, once, as root; non-zero is a hard fail and the loop never starts |
| 4b iterate | the agent, re-run against `PROMPT.md` until `.done`, a stall, or `CONSTRUCT_MAX_ITERATIONS`; as `gem`, which is handed the workspace first |
| 5 archive | NAS workspace → `<tos>/archives/`, hashed in flight and re-read to compare — every run, finished or not |
| 7 report | `result.json` |

**Why 4a is root and 4b is not.** `claude --dangerously-skip-permissions` refuses
to run as root, so the agent has to be `gem` (uid=gid=1000, the image's own user).
But `init.sh` is provisioning, and provisioning needs root: the first real sandbox
run died with `init.sh exited 243` because `npm install -g` cannot write a
root-owned global prefix as uid 1000. Giving the tenant a per-user npm prefix
instead only moves the tools somewhere the agent's `PATH` does not look. So the
phases split, and between them the runner chowns the workspace to `gem` — which
also covers the tree root-owned by attach, and anything `init.sh` itself left
behind.

**Why seed and archives are separate prefixes.** Both hold workspace-shaped
tarballs named for a timestamp, so a seed sitting in `archives/` would be chosen
by the same newest-first rule as a run's own output. Pushing a corrected seed
after a run had archived would then outrank every archive and silently restore
the pristine tree over the construction. Attach therefore takes `archives/`
whenever it has one and consults `seed/` only otherwise: output beats input, and
ordering never has to arbitrate between the two. Measured on a live instance: a
run after a cleanup chose `archives/` and never hashed the seed at all.

**Why a run directory per run, and not a stamp.** Two runs can share a second.
Measured on 2026-09-10, task `84204b2d`: one container ran the startup command
three times with its pid namespace preserved (restore pids 50 → 466 → 674, never
reset) and `/tmp/user` surviving between them, while a second instance ran once.
Two of those runs computed the same second-resolution stamp, wrote the same key,
and one log was overwritten and lost.

Those repeats were *retries of a failing instance*, not routine — six healthy
instances on 2026-09-10 each ran the command exactly once. But the collision does
not need repeats: instance pids are near-identical (all six runs were pid 13),
so two instances started on the same task within a second of each other collide
on stamp and pid together. Two of the six did start 47 s apart and were told
apart only by hostname. Host and pid in the name make the overwrite structurally
impossible.

**Why a lease and not a lock.** Instances overlap. An earlier run can still be
alive — mid-construction, or sleeping out its keep-alive — when the next one
starts, and the later run would otherwise find `.attached`, "reuse" the live
tree, and construct concurrently with it. A plain lock would fix that and
introduce a worse failure: a holder that dies walls the task off permanently.
The lease pairs an owner record with a heartbeat, so a dead holder is detected —
exactly on the local host via `kill(pid, 0)`, and across instances by heartbeat
age. The lease is released before the keep-alive sleep, so a run that has
finished its work and is only holding the container open for inspection does not
look like a live constructor.

Measured across six live instances on 2026-09-10: two overlapping runs on one NAS
directory, on different hosts, were arbitrated by heartbeat age rather than
`kill(pid, 0)`, and the loser wrote a `stood-down` result without touching the
workspace. (TODO section 2 moves this mutual exclusion to the host, where
`ListSandboxes` can answer the same question without a heartbeat thread.)

**Why the archive is unconditional, and why there is no phase 6.** Phase 5 is the
one that matters — the bytes are hashed as they are written, then the object is
read back and hashed again. A write the mount accepts but truncates shows up as a
mismatch, and the `.sha256` sidecar is then withheld, which keeps the bad archive
invisible to the next attach. Every run archives, finished or not: an iteration
budget that ran out is exactly the case where the partial tree is worth keeping,
and the next run attaches to it and carries on.

There used to be a phase 6 that removed the NAS tree once the work was declared
complete. It is gone, and the number is left as a gap rather than closed up, so
that a log from before the rewrite lines up against one from after. Deleting the
workspace was only ever safe in the narrow window where a verified archive
already existed, and the general scaffold has no equivalent of "the work is
finished" to gate it on — `.done` says the *agent* thinks it is done, which is
not the same claim. Reclaiming NAS is a garbage-collection problem for the host,
which can see every task's archives; it was never the runner's, which can see
one.

The log is buffered locally and republished as a whole object each phase.
Appending to a live object over the TOS mount is precisely what object storage
does not reliably support.

**The archive round trip, at size.** Locally against simulated mounts, a
211,572,501 B snapshot of 43,825 entries restored to 36,389 files with counts
matching the manifest, was written back in 46 s, and re-read to the same hash it
was streamed with. On live instances a 505 MiB archive has been written, re-read, and matched
(sha256 round trip intact). Silent truncation at that size did not appear.

## Measured environment (2026-09-10, 8192 MiB instance)

```
overlay    overlay   9.8G  236K  9.8G   1% /
/dev/vdb   ext4      9.8G   28K  9.8G   1% /tmp/user
kataShared virtiofs  3.5T  420G  2.9T  13% /etc/hosts
:/enas-.../harbor/<task-id>  nfs       100G  745M  100G   1% /home/app
fs-89c658a3e35e5a0           virtiofs  8.0E     0  8.0E   0% /mnt/task
Mem: 8129 MiB total
```

Consequences:

- **The TOS mounts are virtiofs, not a FUSE client**, and everything on them reads
  back as `rwxrwxrwx` — permission bits do not survive there at all. This is why
  only tar files cross them. `/home/app` is ordinary NFS and preserved all 9
  executable bits in the same test.
- **NAS `RemotePath` is created by the mount.** The per-task directory does not
  have to exist beforehand. TOS is the opposite: a *read-only* TOS mount requires
  its prefix to already exist, which is why `sbx app sync` writes a `.keep` object
  first.
- The writable layer is **real disk, not tmpfs**, and `/dev/vdb` at `/tmp/user` is
  a separate ext4 volume — so extracting a large archive locally before publishing
  it to NAS is viable. Note `/tmp` itself is overlay; only `/tmp/user` is the data
  volume.
- Runtime is **Kata Containers with a nydus lazy-loading image** (`lowerdir=.../nydus/...`),
  so image layers fetch on demand.
- **Memory is the tight resource, not disk.** `MemoryMB=8192` is honoured (8129 MiB
  visible). Stream tar/gzip; do not buffer archives in memory.
- inode headroom is ~18x a single 90k-file seed, but a tree containing
  `node_modules` can close that gap fast.
- **A failed instance is retried on a ~120 s grid, and every retry re-runs the
  startup script against the same NAS directory.** Three runs landed in six
  minutes across two instances sharing one task id — which is why phase 1 reports
  pid 1's age and the count of prior logs in the container.

## Layout

Host-side, run from a laptop. One entry point, `sandbox/aio/sbx.sh`:

- `sbx app show` / `app sync` — read and write the application's four mount
  points. Both are generated from `sbx/mounts.py`, so what the application
  allows and what an instance asks for cannot drift apart.
- `sbx runtime publish` — `bootstrap.sh` + `runner/` → `_runtime/<version>/`.
- `sbx template publish <dir>` — one tenant's prompt and scripts →
  `_templates/<name>/`.
- `sbx task create|push|status|logs|trace|get|list|kill` — pack a tree, upload it with the
  sidecar last, create one instance narrowed to that task, and read back what it
  wrote. TOS is the only window, since the host cannot mount NAS.
- `sbx batch push|status|reconcile|list` — N candidate directories become nested
  task-ids under one batch prefix; a stateless reconciler opens the next sandbox.
  `list` is batch meta only (name, template, candidate count, live sandboxes);
  per-line state stays on `batch status <name>`. See
  [`ONBOARDING.md`](ONBOARDING.md) §6 and
  [`docs/superpowers/specs/2026-09-14-batch-construction-design.md`](../../docs/superpowers/specs/2026-09-14-batch-construction-design.md).
- `sbx probe describe|instances|logs|revision|timeout` — read-only platform
  questions. The only account of a sandbox that died before `bootstrap.sh` ran
  and so left nothing in TOS.

Volcengine credentials stay on the host. No instance is granted a `RoleTrn`, so
nothing running inside a sandbox can call the platform API at all.

Shipped into the instance, over the runtime mount:

- `bootstrap.sh` — the shim the platform invokes; waits for the mount, finds an
  interpreter, hands over to `runner/`.
- `runner/` — what actually runs inside the instance: lease, attach, `init.sh`,
  the `claude -p` loop, archive. Standard library only, so it needs no install
  step on the startup path.

And:

- `examples/hello-world/` — a template and seed a tenant can copy, proven
  end-to-end in a real sandbox.
- `tests/` — the runner's suite. The whole lifecycle, including lease contention
  between real processes and the iteration loop against a stub agent, runs
  against temporary directories on a laptop with no network:
  `python3 -m unittest discover -s sandbox/aio/tests -t sandbox/aio/tests`.

### Claude trace retrieval

`task trace` is the host observation path for Claude's streamed output. The
runner publishes under the task prefix, one immutable run and iteration at a
time:

```
runs/<run-id>/
  iterations/0001/
    output-000001.jsonl
    output-000002.jsonl
    status.json
  result.json
```

Each JSONL chunk is published once and `status.json` is replaced atomically.
Status starts as `complete: false`, advances `last_sequence` as events arrive,
and ends with `complete: true` and the agent `exit_code`. An interrupted or
still-running iteration therefore remains visible as an incomplete trace; it is
not evidence that the task finished. `task trace` reports that state and exits
after the current objects, while `task trace --follow <task-id>` polls every five
seconds until a complete iteration or `result.json` appears. Select a run or
iteration with `--run` and `--iteration`.

For an exact machine-readable copy, use the raw workflow and the existing object
download command:

```sh
sbx task trace <task-id> --run <run-id> --iteration 1 --raw
sbx task get <task-id> runs/<run-id>/iterations/0001/output-000001.jsonl ./output.jsonl
```

`TRACE_FLUSH_SECONDS` and `TRACE_CHUNK_BYTES` tune how quickly buffered output is
published; lower values improve live visibility at the cost of more objects.
Trace formatting redacts neither arbitrary prompt content nor secrets emitted by
the model, so do not print credentials in prompts, tool output, or workspace
files. The `.claude` directory is intentionally excluded from this interface:
inspect the trace and task artifacts instead of relying on Claude's private
session state.

When a sandbox stops at `4b iterate`, start with the live trace, then correlate it
with the bootstrap log and platform probes:

```sh
sbx task trace <task-id> --follow
sbx task logs <task-id>
sbx probe instances
sbx probe logs <sandbox-id>
```

## Non-goals

- Do not touch the Daytona-version constructor.
- Do not put Volcengine credentials inside a sandbox, by `RoleTrn` or otherwise.
- Do not treat this as a security boundary — tenants supply arbitrary images and
  commands and share one veFaaS application. See TODO section 6.
