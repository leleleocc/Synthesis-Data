#!/usr/bin/env bash
# Vendor a crashed multi-part AOF tree under /data and confirm python3.
set -euo pipefail
command -v python3 >/dev/null
python3 - <<'PY'
from pathlib import Path

def resp(*parts: str) -> bytes:
    chunks = [f"*{len(parts)}\r\n".encode()]
    for part in parts:
        payload = part.encode()
        chunks.append(f"${len(payload)}\r\n".encode())
        chunks.append(payload)
        chunks.append(b"\r\n")
    return b"".join(chunks)

root = Path("/data/aof-incident")
aof_dir = root / "appendonlydir"
aof_dir.mkdir(parents=True, exist_ok=True)

base = (
    resp("SELECT", "0")
    + resp("SET", "incident:ticket", "AOF-7721")
    + resp("SET", "incident:owner", "ops-oncall")
)
incr1 = resp("HSET", "incident:meta", "host", "cache-a", "zone", "eu-west")
# Last incremental file is a truncated MULTI/EXEC (no EXEC). redis-check-aof
# without --fix must reject this; --fix can drop the incomplete transaction.
incr2 = resp("MULTI") + resp("SET", "incident:scratch", "partial")

(aof_dir / "appendonly.aof.1.base.aof").write_bytes(base)
(aof_dir / "appendonly.aof.1.incr.aof").write_bytes(incr1)
(aof_dir / "appendonly.aof.2.incr.aof").write_bytes(incr2)
# Stale leftover that is not part of the live manifest.
(aof_dir / "appendonly.aof.9.incr.aof").write_bytes(resp("SET", "stale", "ignore"))

# Manifest lists a missing incr file and a non-monotonic later sequence.
manifest = (
    "file appendonly.aof.1.base.aof seq 1 type b\n"
    "file appendonly.aof.1.incr.aof seq 1 type i\n"
    "# rewrite aborted at 03:14\n"
    "file appendonly.aof.2.incr.aof seq 2 type i\n"
    "file appendonly.aof.3.incr.aof seq 3 type i\n"
)
(aof_dir / "appendonly.aof.manifest").write_text(manifest)

# Old-style leftover next to the directory; loading this would miss the hash.
(root / "appendonly.aof").write_bytes(base)
print("aof incident fixtures written")
PY
exit 0
