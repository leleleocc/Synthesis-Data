You are building a small Python package inside a sandbox. Your working directory
is the workspace and it is the only place you may write.

**You will be run repeatedly with this exact prompt and no memory of previous
rounds.** Everything you know about your own progress has to come from the files
in the working directory. So begin every round by looking at what is already
there, decide what the next missing piece is, and do that one thing. Do not start
over, and do not redo work that is already finished.

## What to build

A package `greeter/` that formats greetings:

- `greeter/__init__.py` — exports `greet`
- `greeter/core.py` — `greet(name, *, formal=False)` returning `"Hello, <name>!"`,
  or `"Good day, <name>."` when `formal=True`. A blank or whitespace-only name
  raises `ValueError`.
- `tests/test_core.py` — covers both forms and the `ValueError`
- `README.md` — what it is, and how to run the tests

## Acceptance

The work is finished when all of these hold:

1. Every file above exists.
2. `python3 -m pytest -q` passes from the working directory.
3. `README.md` names the actual test command.

## How to stop

When — and only when — you have run the tests yourself and seen them pass,
create the marker file that ends the loop:

```
touch .done
```

Nothing else ends it. If you finish early without the marker you will simply be
run again; if you create the marker with failing tests, the broken tree is what
gets archived. Check first, then mark.

If you are part-way through and something is still failing, leave the marker
alone and fix what you can this round. The next round picks up from the files you
leave behind.
