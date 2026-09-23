#!/usr/bin/env bash
# Candidate overlay: python3 for JSON oracles, plus a broken RDB checksum path.
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
        "    if (server.rdb_checksum)\n"
        "        rdb->update_cksum = rioGenericUpdateChecksum;\n",
        "    if (server.rdb_checksum)\n"
        "        rdb->update_cksum = NULL;\n",
    ),
    (
        "    if (server.rdb_checksum)\n"
        "        rioGenericUpdateChecksum(r, buf, len);\n",
        "    if (server.rdb_checksum)\n"
        "        (void)buf;\n",
    ),
]
for path in (Path("/app/src/rdb.c"), Path("/src/src/rdb.c")):
    text = path.read_text(encoding="utf-8")
    for old, new in replacements:
        count = text.count(old)
        if count != 1:
            raise SystemExit(
                "%s overlay patch expected exactly one match, got %d for:\n%s"
                % (path, count, old)
            )
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")
PY

# Drop git metadata so neither tree still holds the unrepaired blob.
rm -rf /app/.git /src/.git
