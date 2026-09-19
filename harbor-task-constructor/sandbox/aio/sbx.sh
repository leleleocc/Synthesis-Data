#!/usr/bin/env bash
# The CLI's entry point.
#
#   sandbox/aio/sbx.sh app show
#   sandbox/aio/sbx.sh task create probe-1 ./tree --template probe
#
# The `.sh` is not decoration: the package directory is already called sbx/, and
# a file and a directory cannot share a name.
#
# A wrapper rather than a console script because sandbox/aio is a dependency-only
# uv project (`package = false`), so `sbx` is never installed into the venv and
# `python -m sbx` would only resolve with the working directory already inside
# sandbox/aio. This puts the package on the path explicitly, so the command works
# from anywhere in the repository — including from the repository root, which is
# where every other path in these instructions is written from.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec env PYTHONPATH="$here${PYTHONPATH:+:$PYTHONPATH}" \
  uv run --project "$here" python -m sbx "$@"
