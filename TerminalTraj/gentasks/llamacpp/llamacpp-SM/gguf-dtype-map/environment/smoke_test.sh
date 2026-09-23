#!/usr/bin/env bash
# Runtime smoke for the shared llama.cpp base. Must not modify source files.
set -euo pipefail

fail() { echo "smoke_test: $*" >&2; exit 1; }

for d in /app /data /results; do
    [ -d "$d" ] || fail "missing directory $d"
    probe="$d/.harbor_smoke_writable"
    touch "$probe" || fail "$d is not writable"
    rm -f "$probe"
done

# Declared toolchain entrypoints must run.
command -v cmake >/dev/null || fail "cmake missing"
command -v ninja >/dev/null || fail "ninja missing"
command -v g++ >/dev/null || fail "g++ missing"
command -v gcc >/dev/null || fail "gcc missing"
command -v python3 >/dev/null || fail "python3 missing"
command -v git >/dev/null || fail "git missing"

cmake --version >/dev/null
ninja --version >/dev/null
g++ --version >/dev/null
gcc --version >/dev/null
python3 --version >/dev/null
git --version >/dev/null

# Pinned tree is present and writable-as-workdir, unbuilt.
[ -f /app/CMakeLists.txt ] || fail "missing /app/CMakeLists.txt"
[ -f /app/include/llama.h ] || fail "missing /app/include/llama.h"
[ -f /app/src/llama.cpp ] || fail "missing /app/src/llama.cpp"
[ -d /app/ggml ] || fail "missing /app/ggml"
[ ! -d /app/build ] || fail "base must not pre-build; found /app/build"

expected="b29c606e28a01b1bc8c1351026a0fa6e616bf6c4"
got="$(git -C /app rev-parse HEAD)"
[ "$got" = "$expected" ] || fail "pinned commit mismatch: got $got want $expected"

# Compiler actually works (do not touch repo sources).
cat >/tmp/harbor_smoke.cpp <<'EOF'
int main() { return 0; }
EOF
g++ -o /tmp/harbor_smoke /tmp/harbor_smoke.cpp
/tmp/harbor_smoke
rm -f /tmp/harbor_smoke /tmp/harbor_smoke.cpp

echo "smoke_test: ok"
exit 0
