#!/usr/bin/env bash
# Runtime smoke for the shared Redis base. Must not modify source files.
set -euo pipefail

fail() {
    echo "smoke_test: $*" >&2
    exit 1
}

for dir in /app /data /results; do
    [[ -d "$dir" ]] || fail "missing directory $dir"
    [[ -w "$dir" ]] || fail "directory not writable: $dir"
done

data_probe="$(mktemp /data/smoke.XXXXXX)"
echo ok >"$data_probe"
[[ -s "$data_probe" ]] || fail "failed write to /data"
rm -f "$data_probe"

results_probe="$(mktemp /results/smoke.XXXXXX)"
echo ok >"$results_probe"
[[ -s "$results_probe" ]] || fail "failed write to /results"
rm -f "$results_probe"

# Prove /app is writable without touching tracked source.
app_probe="/app/.env-smoke-probe"
echo ok >"$app_probe"
[[ -s "$app_probe" ]] || fail "failed write to /app"
rm -f "$app_probe"

[[ -f /app/Makefile ]] || fail "missing /app/Makefile"
[[ -f /app/src/Makefile ]] || fail "missing /app/src/Makefile"
[[ -f /app/src/server.c ]] || fail "missing /app/src/server.c"
[[ -f /app/src/redis-cli.c ]] || fail "missing /app/src/redis-cli.c"
[[ -f /app/redis.conf ]] || fail "missing /app/redis.conf"
[[ -f /app/runtest ]] || fail "missing /app/runtest"
[[ ! -e /src ]] || fail "pristine /src tree must not remain in the image"

commit="$(git -C /app rev-parse HEAD)"
expected="335554f18caf7bbf6b0ac2b3548133d750f00a1b"
[[ "$commit" == "$expected" ]] || fail "pinned commit mismatch: $commit"

command -v make >/dev/null || fail "make not on PATH"
command -v gcc >/dev/null || fail "gcc not on PATH"
command -v python3 >/dev/null || fail "python3 not on PATH"
command -v tclsh8.6 >/dev/null || fail "tclsh8.6 not on PATH"

# Invoke declared entrypoints (toolchain only; do not compile Redis here).
make --version
gcc --version

echo "smoke_test ok"
