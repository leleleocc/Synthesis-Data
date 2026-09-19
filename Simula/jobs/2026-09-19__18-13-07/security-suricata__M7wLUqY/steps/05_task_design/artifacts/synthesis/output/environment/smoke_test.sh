#!/usr/bin/env bash
# Runtime smoke for the shared Suricata base. Must not modify source.
set -euo pipefail

WORKDIR_PATH="${WORKDIR_PATH:-/app}"
DATA_DIR="${DATA_DIR:-/data}"
RESULTS_DIR="${RESULTS_DIR:-/results}"
EXPECTED_COMMIT="d681600f3648030a67f7d618d30742bfd5fe7169"

fail() { echo "SMOKE FAIL: $*" >&2; exit 1; }
pass() { echo "SMOKE OK: $*"; }

# --- directory layout ---
[[ -d "${WORKDIR_PATH}" ]] || fail "workdir missing: ${WORKDIR_PATH}"
[[ -d "${DATA_DIR}" ]] || fail "data_dir missing: ${DATA_DIR}"
[[ -d "${RESULTS_DIR}" ]] || fail "results_dir missing: ${RESULTS_DIR}"

touch "${WORKDIR_PATH}/.smoke_write" && rm -f "${WORKDIR_PATH}/.smoke_write" \
  || fail "workdir not writable: ${WORKDIR_PATH}"
touch "${DATA_DIR}/.smoke_write" && rm -f "${DATA_DIR}/.smoke_write" \
  || fail "data_dir not writable: ${DATA_DIR}"
touch "${RESULTS_DIR}/.smoke_write" && rm -f "${RESULTS_DIR}/.smoke_write" \
  || fail "results_dir not writable: ${RESULTS_DIR}"
pass "workdir/data_dir/results_dir exist and are writable"

# --- pinned source ---
[[ -d "${WORKDIR_PATH}/.git" ]] || fail "git metadata missing under ${WORKDIR_PATH}"
HEAD="$(git -C "${WORKDIR_PATH}" rev-parse HEAD)"
[[ "${HEAD}" == "${EXPECTED_COMMIT}" ]] || fail "commit ${HEAD} != ${EXPECTED_COMMIT}"
[[ -f "${WORKDIR_PATH}/configure.ac" ]] || fail "configure.ac missing"
[[ -f "${WORKDIR_PATH}/autogen.sh" ]] || fail "autogen.sh missing"
[[ -f "${WORKDIR_PATH}/src/suricata.c" ]] || fail "src/suricata.c missing"
[[ -f "${WORKDIR_PATH}/suricata.yaml.in" ]] || fail "suricata.yaml.in missing"
pass "Suricata source at ${EXPECTED_COMMIT}"

# --- declared entrypoints (toolchain + repo scripts; binary not prebuilt) ---
command -v gcc >/dev/null 2>&1 || fail "gcc missing"
command -v g++ >/dev/null 2>&1 || fail "g++ missing"
command -v make >/dev/null 2>&1 || fail "make missing"
command -v pkg-config >/dev/null 2>&1 || fail "pkg-config missing"
command -v autoconf >/dev/null 2>&1 || fail "autoconf missing"
command -v automake >/dev/null 2>&1 || fail "automake missing"
command -v rustc >/dev/null 2>&1 || fail "rustc missing"
command -v cargo >/dev/null 2>&1 || fail "cargo missing"
command -v cbindgen >/dev/null 2>&1 || fail "cbindgen missing"
command -v python3 >/dev/null 2>&1 || fail "python3 missing"
command -v tcpdump >/dev/null 2>&1 || fail "tcpdump missing"
command -v git >/dev/null 2>&1 || fail "git missing"

gcc --version >/dev/null || fail "gcc --version failed"
rustc --version || fail "rustc --version failed"
cargo --version || fail "cargo --version failed"
cbindgen --version || fail "cbindgen --version failed"
python3 -c "import yaml" || fail "python3 yaml module missing"

# Repo-native entrypoints must be invocable (help/version paths only).
[[ -x "${WORKDIR_PATH}/autogen.sh" ]] || fail "autogen.sh not executable"
# Prove autogen tooling resolves without rewriting the tree: dry check shebang + autoconf.
head -1 "${WORKDIR_PATH}/autogen.sh" | grep -Eq '#!/bin/(sh|bash)' || fail "autogen.sh shebang unexpected"
autoconf --version >/dev/null || fail "autoconf not runnable"
pkg-config --exists libpcap || fail "libpcap.pc missing"
pkg-config --exists yaml-0.1 || fail "libyaml.pc missing"
pkg-config --exists libpcre2-8 || fail "libpcre2.pc missing"
pkg-config --exists jansson || fail "jansson.pc missing"

# Lightweight compile probe (does not build Suricata): toolchain works end-to-end.
PROBE="$(mktemp /tmp/smoke_probe_XXXXXX.c)"
OUT="$(mktemp /tmp/smoke_probe_XXXXXX)"
cat > "${PROBE}" <<'EOF'
#include <stdio.h>
int main(void) { puts("ok"); return 0; }
EOF
gcc -O0 -o "${OUT}" "${PROBE}" || fail "gcc probe compile failed"
"${OUT}" | grep -qx ok || fail "gcc probe run failed"
rm -f "${PROBE}" "${OUT}"

# Rust probe
RPROBE="$(mktemp /tmp/smoke_rs_XXXXXX.rs)"
ROUT="$(mktemp /tmp/smoke_rs_XXXXXX)"
cat > "${RPROBE}" <<'EOF'
fn main() { println!("ok"); }
EOF
rustc -o "${ROUT}" "${RPROBE}" || fail "rustc probe compile failed"
"${ROUT}" | grep -qx ok || fail "rustc probe run failed"
rm -f "${RPROBE}" "${ROUT}"

# Shared fixtures under data_dir (copied at provision time; optional but expected).
[[ -d "${DATA_DIR}/rules" ]] || fail "data_dir/rules missing"
[[ -d "${DATA_DIR}/etc" ]] || fail "data_dir/etc missing"

# Write a tiny marker into results_dir proving agent output path works.
echo "smoke $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${RESULTS_DIR}/smoke_marker.txt"
[[ -s "${RESULTS_DIR}/smoke_marker.txt" ]] || fail "failed writing results marker"

pass "entrypoints and toolchain probes succeeded"
echo "SMOKE_TEST_PASSED"
exit 0
