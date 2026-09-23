#!/usr/bin/env bash
# Smoke the sealed Redis base. Must not modify source files.
set -euo pipefail

WORKDIR="${WORKDIR:-/app}"
DATA_DIR="${DATA_DIR:-/data}"
RESULTS_DIR="${RESULTS_DIR:-/results}"

fail() {
    echo "SMOKE_FAIL: $*" >&2
    exit 1
}

# Declared roots exist and are writable.
for d in "${WORKDIR}" "${DATA_DIR}" "${RESULTS_DIR}"; do
    [ -d "$d" ] || fail "missing directory $d"
    probe="$d/.smoke_write_probe"
    echo smoke > "$probe" || fail "not writable: $d"
    rm -f "$probe"
done

# Pinned source is present in the writable workdir (do not compile here).
[ -f "${WORKDIR}/Makefile" ] || fail "missing ${WORKDIR}/Makefile"
[ -f "${WORKDIR}/src/Makefile" ] || fail "missing ${WORKDIR}/src/Makefile"
[ -f "${WORKDIR}/redis.conf" ] || fail "missing ${WORKDIR}/redis.conf"
[ -f "${WORKDIR}/runtest" ] || fail "missing ${WORKDIR}/runtest"
[ -x "${WORKDIR}/runtest" ] || fail "runtest is not executable"
[ -f "${WORKDIR}/src/server.c" ] || fail "missing ${WORKDIR}/src/server.c"

# Toolchain entrypoints exist (gcc/make/pkg-config). Redis binaries are not
# pre-built so later build-system tasks still have work to do.
command -v gcc >/dev/null || fail "gcc missing"
command -v make >/dev/null || fail "make missing"
command -v pkg-config >/dev/null || fail "pkg-config missing"
gcc --version >/dev/null || fail "gcc --version failed"
make --version >/dev/null || fail "make --version failed"

# A declared repo entrypoint actually runs: runtest without args prints usage
# and exits non-zero, so invoke tclsh on the helper with --help-style flags
# that do not start the suite. `make -C /app -n` is a live Makefile parse.
make -C "${WORKDIR}" -n all >/dev/null || fail "make -n all failed"

# Confirm the clone at /src is still at the pinned commit (read-only check).
if [ -d /src/.git ]; then
    pinned="335554f18caf7bbf6b0ac2b3548133d750f00a1b"
    actual="$(git -C /src rev-parse HEAD)"
    [ "$actual" = "$pinned" ] || fail "commit mismatch: $actual != $pinned"
fi

# Do not leave any source-tree dirt.
if git -C "${WORKDIR}" status --porcelain 2>/dev/null | grep -q .; then
    fail "workdir source was modified"
fi

echo "SMOKE_OK"
exit 0
