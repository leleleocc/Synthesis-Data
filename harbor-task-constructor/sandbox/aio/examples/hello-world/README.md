# hello-world — a template you can copy

The smallest example that exercises the whole loop: `init.sh` prepares the
container, then the agent is re-run against `PROMPT.md` until it writes `.done`.

Two directories, because they go to two different places:

```
template/   published to TOS, mounted read-only at /mnt/template
  PROMPT.md
  init.sh
seed/       packed and pushed to the task's seed/ prefix, restored into the workspace
  TASK.md
```

Keeping them apart is the point. The template is one tenant's instructions, reused
by every task that names it; the seed is one task's own material. Publishing the
seed into the template would put a second copy of it on a read-only mount, where
the agent would find it next to the writable one in its working directory.

## What a template is

A directory published to TOS and mounted read-only at `/mnt/template`. The runner
is fixed; everything task-specific arrives here.

| file | when it runs | failure means |
|---|---|---|
| `PROMPT.md` | piped to the agent's stdin, every iteration | missing → the run fails before iterating |
| `init.sh` | once, before the first iteration, **as root** | non-zero → hard fail, the loop never starts |
| `roles/*.md` | never directly — the agent reads them by path | — |

`init.sh` runs as root because it provisions — `npm install -g` needs a
root-owned prefix. The agent does not: `claude --dangerously-skip-permissions`
refuses to run as root, so it runs as `gem`, and the runner hands it ownership of
the workspace in between. Install tools globally and they will be on the agent's
`PATH`; write files into the workspace and the agent will own them.

The agent's working directory is the workspace on NAS, which persists across
iterations *and* across sandboxes. `/mnt/template` is reachable because the
runner passes `--add-dir`, so `roles/*.md` can be referenced from `PROMPT.md` by
path.

## The one thing that makes a prompt work here

**The agent is re-run with the same prompt and no memory of the previous round.**
A prompt that reads like a one-shot instruction ("write a package that…") makes
the agent start over every iteration, and the fingerprint never settles. A prompt
that works tells it to *look at the tree first*, do the next missing piece, and
name the condition under which it should write `.done`.

`template/PROMPT.md` here is written that way; copy its shape, not just its task.

## The loop stops for one of three reasons

- **`.done` appears in the workspace** — success. This is the only one the
  template controls, and the only one that means the work is finished.
- **Stall** — three consecutive iterations that change no file. The agent is
  going in circles.
- **`CONSTRUCT_MAX_ITERATIONS`** (default 10) — the budget ran out.

Only the first sets `done: true` in `result.json`. The other two are still clean
runs: the workspace is archived either way, and `verdict: fail` is reserved for
the scaffold itself breaking — a missing `PROMPT.md`, an `init.sh` that exited
non-zero, an archive that did not round-trip.

## Running it

```sh
sbx template publish sandbox/aio/examples/hello-world/template --name hello-world
sbx task create hello-1 sandbox/aio/examples/hello-world/seed --template hello-world
sbx task status hello-1 --follow
sbx task logs hello-1
sbx task trace hello-1 --follow
```

The tenant's model credential comes from `sandbox/aio/task.env` on the host and
is injected as environment values. `ANTHROPIC_MODEL` takes effect on its own —
the runner passes no model flag.

The trace lives in the task's TOS prefix at `runs/<run-id>/iterations/<nnnn>/`.
Use `task trace --follow` while a run is active; without `--follow`, an unfinished
iteration is printed with `status: incomplete` so a partial stream is not mistaken
for completion. Add `--raw` for the exact stored JSONL, or download a chunk with
`task get` when another tool needs a file:

```sh
sbx task trace hello-1 --run <run-id> --raw
sbx task get hello-1 runs/<run-id>/iterations/0001/output-000001.jsonl ./trace.jsonl
```

If a sandbox appears stuck at `4b iterate`, run `task trace --follow`, then inspect
`task logs` and `probe instances`/`probe logs <sandbox-id>`. Trace chunks flush
according to `TRACE_FLUSH_SECONDS` and `TRACE_CHUNK_BYTES`; the `.claude` directory
is deliberately not part of the host trace, and model output can still contain
secrets if a prompt or tool prints them.

## What it did when last run

Run `20260911T042421Z-…-sandbox-13`, task `hello-2`, in a real sandbox on
2026-09-11. `init.sh` installed `@anthropic-ai/claude-code` 2.1.268 and pytest
9.1.1 and exited 0 after 23 s; the runner chowned the workspace to `gem`; the
first iteration spent 56 s writing `greeter/`, `tests/` and `README.md` and wrote
`.done`. `result.json`: `verdict: pass`, `done: true`, 10 files, archive 2,549 B
with the round trip verified. Pulled back down afterwards, `python3 -m pytest -q`
gives 10 passed.
