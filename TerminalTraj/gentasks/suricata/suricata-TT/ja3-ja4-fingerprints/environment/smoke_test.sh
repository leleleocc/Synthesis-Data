#!/usr/bin/env bash
# Runtime smoke for the shared Suricata base. Must not modify source files.
set -euo pipefail

WORKDIR="${WORKDIR:-/app}"
DATA_DIR="${DATA_DIR:-/data}"
RESULTS_DIR="${RESULTS_DIR:-/results}"

fail() {
    echo "smoke_test: $*" >&2
    exit 1
}

for dir in "${WORKDIR}" "${DATA_DIR}" "${RESULTS_DIR}"; do
    [ -d "${dir}" ] || fail "missing directory ${dir}"
    [ -w "${dir}" ] || fail "directory not writable: ${dir}"
done

# Prove data_dir / results_dir are writable without touching source.
data_probe="${DATA_DIR}/.smoke_probe"
results_probe="${RESULTS_DIR}/.smoke_probe"
echo smoke > "${data_probe}"
echo smoke > "${results_probe}"
[ -s "${data_probe}" ] || fail "failed to write ${data_probe}"
[ -s "${results_probe}" ] || fail "failed to write ${results_probe}"
rm -f "${data_probe}" "${results_probe}"

# workdir must be writable; write beside the tree, not into tracked sources.
workdir_probe="${WORKDIR}/.smoke_probe"
echo smoke > "${workdir_probe}"
[ -s "${workdir_probe}" ] || fail "failed to write ${workdir_probe}"
rm -f "${workdir_probe}"

# Pinned source is present and looks like Suricata (do not compile here).
[ -f "${WORKDIR}/src/main.c" ] || fail "missing ${WORKDIR}/src/main.c"
[ -f "${WORKDIR}/configure.ac" ] || fail "missing ${WORKDIR}/configure.ac"
[ -x "${WORKDIR}/autogen.sh" ] || fail "missing executable ${WORKDIR}/autogen.sh"
[ -d "${WORKDIR}/rust" ] || fail "missing ${WORKDIR}/rust"
[ -f "${WORKDIR}/suricata.yaml.in" ] || fail "missing ${WORKDIR}/suricata.yaml.in"

# Declared entrypoints: gcc / rustc / cargo / python3 / make / tcpdump.
# Invoke them; do not run autogen.sh (it would modify the source tree).
gcc --version >/dev/null || fail "gcc failed"
rustc --version >/dev/null || fail "rustc failed"
cargo --version >/dev/null || fail "cargo failed"
python3 --version >/dev/null || fail "python3 failed"
make --version >/dev/null || fail "make failed"
tcpdump --version >/dev/null 2>&1 || tcpdump -h >/dev/null 2>&1 || fail "tcpdump failed"

command -v cbindgen >/dev/null || fail "cbindgen missing"
command -v pkg-config >/dev/null || fail "pkg-config missing"
pkg-config --exists libpcap || fail "libpcap not found via pkg-config"
pkg-config --exists libpcre2-8 || fail "libpcre2 not found via pkg-config"
pkg-config --exists yaml-0.1 || fail "libyaml not found via pkg-config"
pkg-config --exists jansson || fail "jansson not found via pkg-config"

# Confirm we did not leave a compiled Suricata binary as a planted baseline.
if [ -x "${WORKDIR}/src/suricata" ]; then
    fail "src/suricata should not be pre-built in the shared base"
fi

echo "smoke_test: ok"
exit 0
