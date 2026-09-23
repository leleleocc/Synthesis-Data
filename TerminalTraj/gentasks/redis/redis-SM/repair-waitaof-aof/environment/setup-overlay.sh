#!/usr/bin/env bash
# Candidate overlay: python3 for JSON/RESP oracles, plus a broken AOF offset path.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

apt-get update
apt-get install -y --no-install-recommends python3
rm -rf /var/lib/apt/lists/*

command -v python3 >/dev/null

python3 - <<'PY'
from pathlib import Path

replacements = [
    (
        "    bioCreateFsyncJob(fd, server.master_repl_offset, 1);\n",
        "    bioCreateFsyncJob(fd, 0, 1);\n",
    ),
    (
        "    bioCreateCloseAofJob(fd, server.master_repl_offset, 1);\n",
        "    bioCreateCloseAofJob(fd, 0, 1);\n",
    ),
    (
        "        atomicSet(server.fsynced_reploff_pending, server.master_repl_offset);\n",
        "        atomicSet(server.fsynced_reploff_pending, 0);\n",
    ),
]
for path in (Path("/app/src/aof.c"), Path("/src/src/aof.c")):
    text = path.read_text(encoding="utf-8")
    for old, new in replacements:
        count = text.count(old)
        if count < 1:
            raise SystemExit("%s overlay patch missed expected snippet:\n%s" % (path, old))
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")
PY

# Drop git metadata so neither tree still holds the unrepaired blob.
rm -rf /app/.git /src/.git
