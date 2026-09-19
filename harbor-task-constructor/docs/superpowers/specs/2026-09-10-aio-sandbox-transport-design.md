# AIO Sandbox Transport Design

## Goal

Run the construction workspace on Volcengine AIO Sandbox with three roles and no
lifecycle vocabulary of its own:

- **NAS** is the workspace. The tree lives there and outlives any one execution.
- **The sandbox** is the execution environment. It is stateless and disposable.
- **TOS** is durable storage, guarding against an abort or an execution that
  produces no final result, and serving later debugging.

Transport carries bytes. It does not decide what evidence the Agent may read, how
rounds are selected, or when a measurement is stale — those stay in the SOP.

This design governs the AIO Sandbox path only. The existing Daytona-based
constructor is history and is not modified by this work; the two paths coexist
rather than converge. Subsequent sandbox work follows the three roles above.

## Observed boundary

**Harbor 0.21.0 supplies no workspace seam.** `AGENT_START` / `AGENT_END` are
notifications; `TrialHookEvent` carries event, task name, config, result, lock,
and timestamp, not the live `Trial` or `BaseEnvironment`. Collection returns one
task-declared final tree with no pre-Agent baseline. Recorded in
`docs/reviews/2026-09-06-agent-workspace-delta-feasibility.md`.

**Scale.** One seed (`95713311`) is 36,382 files and 819 MiB; its tar is 839 MiB
and gzip level 1 reduces it to 237 MiB. A full working tree is larger: a single
regrade round was observed filling a 5 GiB disk.

**Sandbox mounts.** `CreateSandbox` (`Version=2024-06-06`) exposes
`InstanceTosMountConfig` and `InstanceNasMountConfig`, both per-instance. Each TOS
mount point carries its own `BucketName`, `Endpoint`, `BucketPath` and
`LocalMountPath`; each NAS mount point carries `RemotePath` and `LocalMountPath`.
Confirmed against `volcengine-python-sdk==5.0.48`, which is also how this repo
issues the call.

But an instance mount point is an **override, not a free-standing mount**. The
sandbox application's online revision must already declare a mount point at the
same `LocalMountPath`; `CreateSandbox` may then only re-point it — `RemotePath`
for NAS, `BucketPath` for TOS. Three API errors establish this, in order:

| Sent | Error |
| --- | --- |
| TOS mount, application with `EnableTos=false` | `fn tos mount points is empty, not support to mount tos for instance` |
| NAS mount, application NAS config removed | `local mount path /mnt/nas not exist in fn online revision nas mount points` |
| `TimeoutUnit=Minute` | `request TimeoutUnit must be minute or second` |

So per-task isolation is real but *conditional*: the application is configured
once with `/mnt/tos` and `/mnt/nas` declared, and every instance thereafter
re-points those two paths at its own task. An application missing the declaration
cannot be rescued at instance level.

`InstanceNasMountConfig` carries no auth fields at all — only `Enable` and
`NasMountPoints` — so NAS authorization is network position within the VPC. TOS
has its own surface (`AuthMode`, `Credentials`, `RoleTrn`), left unset here; its
`AuthMode` enum is absent from the SDK and the documentation site renders
client-side, so the accepted values are unknown rather than chosen.

**Measured instance** (2026-09-10, `MemoryMB` 8192, both mounts present):

```
overlay    overlay   9.8G  236K  9.8G   1% /          inodes 655360
/dev/vdb   ext4      9.8G   28K  9.8G   1% /tmp/user
kataShared virtiofs  3.5T  420G  2.9T  13% /etc/hosts
:/enas-apse1b01ea3180a0e90/harbor/<task-id>  nfs  100G  745M  100G  1% /mnt/nas
fs-89c658a3e35e5a0                       virtiofs  8.0E     0  8.0E  0% /mnt/tos
Mem: 8129 MiB total
```

The writable layer is real disk, not tmpfs. `/dev/vdb` is a separate ext4 volume
at `/tmp/user`; `/tmp` itself is overlay. The runtime is Kata Containers over a
nydus lazy-loading image. Memory, not disk, is the constrained resource at the
default instance size; it is adjustable per instance.

**The TOS mount is virtiofs, not a FUSE client**, and every object on it reads
back as `rwxrwxrwx` — permission bits do not survive on the TOS side at all. That
is not a defect to work around; it is the reason only tar files cross it. NAS is
ordinary NFS and preserves modes, and `RemotePath` is created by the mount, so
the per-task directory need not exist beforehand.

**Host reach.** The host cannot mount the NAS. It reaches the workspace only
through TOS.

## Design

### Layout

| Where | Path | Role |
| --- | --- | --- |
| NAS | `/mnt/nas/workspace/` | The working tree, including `build/` and runtime evidence state |
| TOS | `/mnt/tos/snapshots/<utc-timestamp>.tar.gz` | Full workspace snapshot, plus a `.sha256` completeness sentinel |
| TOS | `/mnt/tos/status/` | Small liveness and outcome objects |

Both mounts are *already* the task's directory: `BucketPath` is
`/sandbox/<task-id>` and `RemotePath` is `<nas-prefix>/<task-id>`, set per
instance. So no path inside the sandbox repeats the task id, and isolation between
tasks is enforced by the mount on both sides rather than by path discipline in a
script. An instance that is handed the wrong id gets the wrong mount, not a
neighbour's files.

`/app` is a bind mount of the NAS workspace, so the existing runtime path contract
is unchanged while the tree physically lives on NAS. Runtime evidence state is
inside the workspace rather than on local disk, so a resumed execution continues
from exactly where the interrupted one stopped.

Snapshots are whole trees, keyed by UTC timestamp. There is no seed, no
allowlist, no generation window, and no life counter: the Agent reads the
workspace and decides which round to use, which is a judgment the SOP already
governs. Timestamps sort lexicographically, so resolving the newest snapshot needs
no counter state.

TOS never holds an unpacked tree. 36,382 small files over an object-storage mount
is its worst case, and the mount's partial POSIX semantics lose modes and symlinks.
Everything crossing the mount is a tar; the tree it expands into is on NAS.

### In-sandbox runner

`InstanceImageInfo.Command` is the only injection hook, and it does not replace
the application: the platform gates readiness on the application listening on its
port, so a command that only runs the startup script never becomes ready and the
instance fails with `function_cold_start_timeout`. The command therefore starts
the runner in the background and `exec`s the application's own entrypoint. The
runner itself waits for the TOS mount rather than assuming it, since the mount is
not necessarily up when the container starts.

The runner drives three phases.

**Attach.** Use the NAS workspace when it exists. When it is absent — a new task,
or a lost NAS — restore the newest snapshot that has a matching `.sha256` sidecar,
extracting into an empty directory. Restoring over an existing tree is forbidden:
it merges two states and silently resurrects files that were deleted. Extraction
is streamed; archives are never buffered in memory.

**Construct.** Run the existing SOP against `/app`. Inner target and solver
rollouts remain Harbor to Daytona and require egress, which this application does
not currently have — see Open verification.

**Snapshot.** Stream the whole workspace to the TOS snapshot prefix, then write
its `.sha256` sidecar. Snapshots are taken at round boundaries and on reaching the
construction deadline. Rounds are an existing unit of the construction loop, so
this adds no new concept.

Status objects are written throughout, since the host cannot observe NAS.

### Host side

Create one instance per task, with `InstanceTosMountConfig` pointing `BucketPath`
at `/sandbox/<task-id>` and `InstanceNasMountConfig` pointing `RemotePath` at
`<nas-prefix>/<task-id>`. Those two fields are what isolate tasks. The task id
still goes through `Envs` as a label, along with the construction deadline, but
nothing constructs a path from it inside the sandbox.

Bootstrap is a manual upload of the first snapshot. The host polls `status/` and
pulls snapshots to inspect or to recover a result.

## Failure handling

The sandbox `Timeout` is set far above the construction deadline — for example a
24-hour instance holding an 8-hour construction budget. The deadline is enforced
by the runner itself, with hours of margin behind it, so a snapshot cannot be
truncated by the platform kill. Nothing depends on trapping the platform timeout.

Instance death is covered by NAS: the tree survives, and a replacement instance
attaches to it. Snapshots exist for the cases NAS does not cover — the host's only
window onto the workspace, an abort that leaves no final result, loss of the NAS
tree, and post-hoc debugging.

**A failed instance is retried, and each retry re-runs the startup script against
the same NAS directory.** Observed 2026-09-10: an instance whose cold start timed
out was retried on a ~120 s grid, three runs in six minutes, all mounting one
task's NAS path — and one of those retries overlapped a second, healthy instance
created for the same task. So the runner cannot assume it is alone on the
workspace. Two consequences: it must take a lock on the NAS workspace before
touching it and stand down if another instance holds one, and it must never
delete the workspace as a routine step. The verification bootstrap does delete it,
which is safe only because that run owns a throwaway task id.

A large archive interrupted mid-write leaves a plausible-looking truncated object.
The `.sha256` sidecar is written only after the archive is closed, and a snapshot
without its sidecar is treated as absent. Because snapshots are periodic and
whole, a bad one is superseded rather than repaired, so the runner does not stage
snapshots locally to verify them; it streams them and lets the next snapshot
supersede a failure. Each version is written as a new object, never appended,
since object-storage mounts do not reliably support appending to an existing
object.

## Open verification

- ~~Confirm the TOS mount appears and behaves on an instance created with
  `InstanceTosMountConfig`.~~ **Closed 2026-09-10.** Two full round trips on a
  live instance, task `84204b2d`: restore 138 files from TOS to NAS, counts and
  executable bits matching the packed manifest, write back, re-read hash equal to
  the streamed hash. Both `pass`, 0 failures. The second trip restored from the
  first trip's write-back, so the archive the sandbox produced is itself
  attachable.
- Measure whether a large write through the TOS mount can truncate silently, and
  confirm the sidecar protocol detects it. The 190 KiB verification archive is far
  too small to show this; re-run at the 211 MiB package.
- Define the workspace lock, given that a retried instance re-runs the startup
  script against a NAS directory another instance may hold.
- Measure snapshot cost against the construction deadline, so that round-boundary
  snapshots stay a small fraction of a round.
- Watch inode headroom on NAS as full trees accumulate, and define reclamation for
  superseded snapshots.
- Settle egress. The sandbox application has `EnableSharedInternetAccess=false`,
  which is why the TOS endpoint must be the VPC-internal `ivolces` one. Inner
  target and solver rollouts go to Harbor and Daytona and need a route out.

## Non-goals

- Do not modify the existing Daytona-based constructor. It stays as it is, and
  nothing here is a migration of it.
- Do not change SOP reasoning or timeout policy.
- Do not change the runtime path contract.
- Do not move inner rollouts off Harbor and Daytona.
- Do not compute file-level deltas. Snapshots are whole trees.
- Do not select, prune, or allowlist workspace contents in transport. Whether a
  round is stale or reusable is the Agent's judgment under the SOP.
- Do not migrate production batches before the open verification items are closed.
