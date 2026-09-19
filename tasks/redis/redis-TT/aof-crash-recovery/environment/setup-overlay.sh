#!/bin/bash
# Plant a crashed Redis 7 multi-part AOF under /data/incident and keep python3
# available for later observation of recovered JSON.
set -euo pipefail

command -v python3 >/dev/null

mkdir -p /data/incident/appendonlydir /results

python3 - <<'PY'
from pathlib import Path

root = Path("/data/incident")
aofdir = root / "appendonlydir"
aofdir.mkdir(parents=True, exist_ok=True)


def resp(*args: str) -> bytes:
    chunks = [f"*{len(args)}\r\n".encode()]
    for arg in args:
        payload = arg.encode()
        chunks.append(f"${len(payload)}\r\n".encode())
        chunks.append(payload)
        chunks.append(b"\r\n")
    return b"".join(chunks)


base = b"".join(
    [
        resp("SELECT", "0"),
        resp("SET", "catalog:sku1", "Widget-Blue"),
        resp("SET", "catalog:sku2", "Widget-Red"),
        resp("HSET", "catalog:meta", "brand", "Acme", "sku_count", "2"),
        resp("SADD", "catalog:tags", "winter", "sale"),
        resp("ZADD", "catalog:prices", "9.99", "sku1", "12.5", "sku2"),
        resp("RPUSH", "catalog:featured", "sku1", "sku2"),
    ]
)
(aofdir / "appendonly.aof.1.base.aof").write_bytes(base)

incr = b"".join(
    [
        resp("SET", "catalog:sku3", "Widget-Green"),
        resp("HSET", "catalog:meta", "sku_count", "3"),
        resp("SADD", "catalog:tags", "spring"),
        resp("ZADD", "catalog:prices", "7.5", "sku3"),
        resp("RPUSH", "catalog:featured", "sku3"),
        b"#TS:1710000000\r\n",
        resp("SET", "ops:last_rewrite", "ok"),
        # Truncated RESP tail from the crash: incomplete SET of catalog:sku4.
        b"*3\r\n$3\r\nSET\r\n$13\r\ncatalog:sku4\r\n$10\r\nTRUNC",
    ]
)
(aofdir / "appendonly.aof.1.incr.aof").write_bytes(incr)

# Blank line in the manifest is rejected by Redis 7 AOF loader.
manifest = (
    "file appendonly.aof.1.base.aof seq 1 type b\n"
    "\n"
    "file appendonly.aof.1.incr.aof seq 1 type i\n"
)
(aofdir / "appendonly.aof.manifest").write_text(manifest, encoding="ascii")

# Leftover history fragment that is not in the manifest and must not load.
(aofdir / "appendonly.aof.9.incr.aof").write_bytes(
    resp("SET", "should-not-load", "no")
)

conf = """\
bind 127.0.0.1
port 6379
protected-mode yes
daemonize no
dir /data/incident
dbfilename dump.rdb
appendonly yes
appendfilename appendonly.aof
appenddirname appendonlydir
appendfsync everysec
aof-load-truncated no
save
"""
(root / "redis.conf").write_text(conf, encoding="ascii")
(root / "CRASH.txt").write_text(
    "writer pid 4412 died during AOF append; last SKU write may be incomplete\n",
    encoding="ascii",
)
PY

# Drop the planting script so the intended catalog is not sitting in /opt/env.
rm -f /opt/env/setup-overlay.sh
