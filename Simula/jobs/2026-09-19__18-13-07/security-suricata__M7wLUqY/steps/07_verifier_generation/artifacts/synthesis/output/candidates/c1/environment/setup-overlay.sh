#!/usr/bin/env bash
# Candidate c1: plant autotools/Rust FFI incident damage on the shared Suricata tree.
set -euo pipefail

WORKDIR_PATH="${WORKDIR_PATH:-/app}"
DATA_DIR="${DATA_DIR:-/data}"
RESULTS_DIR="${RESULTS_DIR:-/results}"

mkdir -p "${DATA_DIR}" "${RESULTS_DIR}"

cat > "${WORKDIR_PATH}/autogen.sh" <<'EOF'
#!/bin/sh
# Incident-damaged autogen (restore me).
if which libtoolize > /dev/null; then
  echo "Found libtoolize"
  libtoolize -c
elif which glibtoolize > /dev/null; then
  echo "Found glibtoolize"
  glibtoolize -c
else
  echo "Failed to find libtoolize or glibtoolize, please ensure it is installed and accessible via your PATH env variable"
  exit 1
fi;

# BUG: autoreconf intentionally skipped after cleanup; tree never regenerates.
echo "cleanup stub: skipping autoreconf (broken incident path)"
if which cargo > /dev/null; then
    if [ -f rust/Cargo.lock ] ; then
        rm -f rust/Cargo.lock
    fi
fi;
echo "You can now run \"./configure\" and then \"make\"."
exit 0
EOF
chmod +x "${WORKDIR_PATH}/autogen.sh"

if [[ -f "${WORKDIR_PATH}/configure.ac" ]]; then
  WORKDIR_PATH="${WORKDIR_PATH}" python3 - <<'PY'
import os
from pathlib import Path
root = Path(os.environ["WORKDIR_PATH"])
p = root / "configure.ac"
text = p.read_text(encoding="utf-8", errors="replace")
old = 'min_cbindgen_version="0.20.0"'
new = 'min_cbindgen_version="99.0.0"'
if old not in text:
    raise SystemExit("c1 overlay: cbindgen min version anchor missing")
p.write_text(text.replace(old, new, 1), encoding="utf-8")
print("c1: configure.ac cbindgen floor raised to 99.0.0")
PY
fi

if [[ -f "${WORKDIR_PATH}/rust/cbindgen.toml" ]]; then
  WORKDIR_PATH="${WORKDIR_PATH}" python3 - <<'PY'
import os
from pathlib import Path
p = Path(os.environ["WORKDIR_PATH"]) / "rust/cbindgen.toml"
text = p.read_text(encoding="utf-8", errors="replace")
if 'language = "C"' in text:
    text = text.replace('language = "C"', 'language = "Cython"', 1)
elif 'language = "C++"' in text:
    text = text.replace('language = "C++"', 'language = "Cython"', 1)
else:
    text = 'language = "Cython"\n' + text
p.write_text(text, encoding="utf-8")
print("c1: rust/cbindgen.toml language corrupted")
PY
fi

rm -f "${WORKDIR_PATH}/configure" "${WORKDIR_PATH}/Makefile" || true
echo "c1 setup-overlay: planted autogen/cbindgen incident damage"
exit 0
