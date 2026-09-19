#!/bin/bash
# Shared-base smoke: toolchain, pinned source, writable dirs. Does not compile
# Redis and does not modify source files.
set -euo pipefail

WORKDIR=/app
DATA_DIR=/data
RESULTS_DIR=/results
PINNED_COMMIT=335554f18caf7bbf6b0ac2b3548133d750f00a1b

for dir in "$WORKDIR" "$DATA_DIR" "$RESULTS_DIR"; do
    test -d "$dir"
    probe="${dir}/.smoke_write_probe"
    echo smoke > "$probe"
    test -s "$probe"
    rm -f "$probe"
done

test -f "$WORKDIR/Makefile"
test -f "$WORKDIR/src/server.c"
test -f "$WORKDIR/src/Makefile"
test -f "$WORKDIR/redis.conf"
test -f "$WORKDIR/runtest"
test -d /src/.git
test "$(git -C /src rev-parse HEAD)" = "$PINNED_COMMIT"

command -v gcc >/dev/null
command -v make >/dev/null
command -v python3 >/dev/null
command -v tclsh8.6 >/dev/null
command -v pkg-config >/dev/null

# Declared entrypoints: report versions without touching the Redis tree.
gcc --version
make --version

# Prove the C toolchain can produce a binary (scratch file, not source).
printf '%s\n' 'int main(void) { return 0; }' > /tmp/env_smoke.c
gcc -o /tmp/env_smoke /tmp/env_smoke.c
/tmp/env_smoke
rm -f /tmp/env_smoke /tmp/env_smoke.c

echo SMOKE_OK
