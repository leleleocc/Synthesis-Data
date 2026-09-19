#!/bin/bash
# Smoke the shared base: toolchain, pinned source, dirs, and one entrypoint.
# Must not modify source files.
set -euo pipefail

fail() {
    echo "smoke_test: $*" >&2
    exit 1
}

WORKDIR="/app"
DATA_DIR="/data"
RESULTS_DIR="/results"

[ -d "$WORKDIR" ] || fail "workdir missing: $WORKDIR"
[ -d "$DATA_DIR" ] || fail "data_dir missing: $DATA_DIR"
[ -d "$RESULTS_DIR" ] || fail "results_dir missing: $RESULTS_DIR"

probe="$DATA_DIR/.smoke_probe_$$"
echo smoke > "$probe" || fail "data_dir not writable: $DATA_DIR"
rm -f "$probe"

probe="$RESULTS_DIR/.smoke_probe_$$"
echo smoke > "$probe" || fail "results_dir not writable: $RESULTS_DIR"
rm -f "$probe"

probe="$WORKDIR/.smoke_probe_$$"
echo smoke > "$probe" || fail "workdir not writable: $WORKDIR"
rm -f "$probe"

[ -f "$WORKDIR/CMakeLists.txt" ] || fail "source CMakeLists.txt missing under $WORKDIR"
[ -f "$WORKDIR/include/llama.h" ] || fail "include/llama.h missing under $WORKDIR"
[ -f "$WORKDIR/src/llama.cpp" ] || fail "src/llama.cpp missing under $WORKDIR"
[ -f "$WORKDIR/ggml/src/ggml.cpp" ] || fail "ggml/src/ggml.cpp missing under $WORKDIR"
[ -f "$WORKDIR/convert_hf_to_gguf.py" ] || fail "convert_hf_to_gguf.py missing under $WORKDIR"

command -v cmake >/dev/null || fail "cmake not on PATH"
command -v ninja >/dev/null || fail "ninja not on PATH"
command -v gcc-14 >/dev/null || fail "gcc-14 not on PATH"
command -v g++-14 >/dev/null || fail "g++-14 not on PATH"
command -v python3 >/dev/null || fail "python3 not on PATH"
command -v git >/dev/null || fail "git not on PATH"
command -v ccache >/dev/null || fail "ccache not on PATH"

# Declared entrypoints: cmake (build system) and python3 (conversion scripts).
cmake --version >/dev/null || fail "entrypoint cmake --version failed"
python3 --version >/dev/null || fail "entrypoint python3 --version failed"
gcc-14 --version >/dev/null || fail "gcc-14 --version failed"

expected_commit="b29c606e28a01b1bc8c1351026a0fa6e616bf6c4"
if [ -d "$WORKDIR/.git" ]; then
    got="$(git -C "$WORKDIR" rev-parse HEAD)"
    [ "$got" = "$expected_commit" ] || fail "pinned commit mismatch: $got"
fi

echo "smoke_test: ok"
