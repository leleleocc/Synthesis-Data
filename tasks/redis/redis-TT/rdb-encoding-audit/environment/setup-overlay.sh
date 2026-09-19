#!/bin/bash
# Copy the four historical RDB snapshots into /data/rdb and keep python3
# on PATH for structured encoding-report checks.
set -euo pipefail
command -v python3 >/dev/null
mkdir -p /data/rdb /results
for name in hash-zipmap.rdb hash-ziplist.rdb zset-ziplist.rdb list-quicklist.rdb; do
    cp -a "/src/tests/assets/${name}" "/data/rdb/${name}"
done
chmod a+r /data/rdb/*.rdb
exit 0
