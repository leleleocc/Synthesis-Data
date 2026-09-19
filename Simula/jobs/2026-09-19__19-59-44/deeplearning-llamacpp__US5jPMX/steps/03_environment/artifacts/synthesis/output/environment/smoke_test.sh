#!/usr/bin/env bash
# Runtime smoke for the llama.cpp shared base. Must not modify source.
set -euo pipefail

WORKDIR="${WORKDIR:-/app}"
DATA_DIR="${DATA_DIR:-/data}"
RESULTS_DIR="${RESULTS_DIR:-/results}"
EXPECTED_COMMIT="b29c606e28a01b1bc8c1351026a0fa6e616bf6c4"

export PATH="/opt/venv/bin:/usr/local/bin:${PATH}"

fail() { echo "SMOKE FAIL: $*" >&2; exit 1; }
pass() { echo "SMOKE OK: $*"; }

echo "=== llama.cpp base smoke ==="

# Directories exist and are writable.
[[ -d "${WORKDIR}" ]] || fail "workdir missing: ${WORKDIR}"
[[ -d "${DATA_DIR}" ]] || fail "data_dir missing: ${DATA_DIR}"
[[ -d "${RESULTS_DIR}" ]] || fail "results_dir missing: ${RESULTS_DIR}"

touch "${WORKDIR}/.smoke_write_test" || fail "workdir not writable"
rm -f "${WORKDIR}/.smoke_write_test"
touch "${DATA_DIR}/.smoke_write_test" || fail "data_dir not writable"
rm -f "${DATA_DIR}/.smoke_write_test"
touch "${RESULTS_DIR}/.smoke_write_test" || fail "results_dir not writable"
rm -f "${RESULTS_DIR}/.smoke_write_test"
pass "dirs writable (${WORKDIR}, ${DATA_DIR}, ${RESULTS_DIR})"

# Pinned source present.
[[ -f "${WORKDIR}/CMakeLists.txt" ]] || fail "CMakeLists.txt missing in workdir"
[[ -d "${WORKDIR}/.git" ]] || fail "git metadata missing"
ACTUAL="$(git -C "${WORKDIR}" rev-parse HEAD 2>/dev/null || true)"
[[ "${ACTUAL}" == "${EXPECTED_COMMIT}" ]] || fail "commit mismatch: got ${ACTUAL}, want ${EXPECTED_COMMIT}"
pass "source at ${EXPECTED_COMMIT}"

# Toolchain entrypoints.
command -v gcc >/dev/null || fail "gcc missing"
command -v g++ >/dev/null || fail "g++ missing"
command -v cmake >/dev/null || fail "cmake missing"
command -v ninja >/dev/null || fail "ninja missing"
command -v python3 >/dev/null || fail "python3 missing"
gcc --version >/dev/null || fail "gcc failed"
cmake --version >/dev/null || fail "cmake failed"
pass "toolchain (gcc/g++/cmake/ninja/python3)"

# Python stack used by conversion / gguf tooling.
python3 -c "import numpy, gguf, yaml, tqdm; print('pyok')" || fail "python deps missing"
pass "python deps (numpy, gguf, yaml, tqdm)"

# Declared binary entrypoints from baseline build.
LLAMA_CLI=""
for candidate in llama-cli llama-server llama-quantize llama-bench llama-tokenize; do
  if command -v "${candidate}" >/dev/null 2>&1; then
    LLAMA_CLI="${candidate}"
    break
  fi
  if [[ -x "${WORKDIR}/build/bin/${candidate}" ]]; then
    LLAMA_CLI="${WORKDIR}/build/bin/${candidate}"
    break
  fi
done
[[ -n "${LLAMA_CLI}" ]] || fail "no llama binary entrypoint found"

# Run entrypoint in a way that does not need a model weights file.
# --help / -h should exit 0 or print usage (accept 0 or 1 depending on binary).
set +e
HELP_OUT="$("${LLAMA_CLI}" --help 2>&1 || "${LLAMA_CLI}" -h 2>&1 || true)"
set -e
echo "${HELP_OUT}" | grep -Eiq 'usage|help|llama|option|model' \
  || fail "entrypoint ${LLAMA_CLI} did not print usage/help"
pass "entrypoint runs: ${LLAMA_CLI}"

# cmake can reconfigure (build-system tag readiness) without network.
cmake -S "${WORKDIR}" -B "${WORKDIR}/build" -N >/dev/null \
  || fail "cmake -N on existing build failed"
pass "cmake configure graph readable"

# Write a tiny marker under results to prove results_dir end-to-end.
echo "smoke $(date -u +%Y-%m-%dT%H:%M:%SZ)" >"${RESULTS_DIR}/smoke_marker.txt"
[[ -s "${RESULTS_DIR}/smoke_marker.txt" ]] || fail "could not write results marker"
pass "results_dir write"

echo "=== SMOKE PASSED ==="
exit 0
