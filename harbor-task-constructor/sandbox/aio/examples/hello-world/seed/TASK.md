# Task context (shipped in the seed)

This file is here to show where a task's own material goes: `sbx task create`
packs this directory into the task's `seed/` prefix, and the runner restores it
into the workspace before the first iteration. From then on the workspace is
whatever the previous run left behind — the seed is consulted only when the task
has no archive at all, and it loses to any archive the task has produced. Pushing
a corrected seed after a run will not overwrite the work.

For a real task this is where the input data, the spec, or the starting code
would live. The agent sees it in its working directory, so `PROMPT.md` can refer
to it by name.

For this example there is nothing to start from: everything in the acceptance
list is written from scratch.
