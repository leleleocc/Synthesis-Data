#!/bin/bash
set -uo pipefail

mkdir -p /logs/verifier
PASS=1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

fail() {
  echo "FAIL: $*" >&2
  PASS=0
}

finish() {
  mkdir -p /logs/verifier
  if [ "${PASS:-0}" -eq 1 ]; then
    echo 1 > /logs/verifier/reward.txt
    exit 0
  fi
  echo 0 > /logs/verifier/reward.txt
  exit 1
}
trap finish EXIT

# Snapshot /data so later steps can prove the fixture was not rewritten.
DATA_HASH=""
if [ -f /data/attn_fixture.json ]; then
  DATA_HASH="$(python3 -c 'import hashlib,pathlib; print(hashlib.sha256(pathlib.Path("/data/attn_fixture.json").read_bytes()).hexdigest())')"
else
  fail "missing /data/attn_fixture.json"
fi

if [ ! -f /results/attn_out.bin ]; then
  fail "missing /results/attn_out.bin"
fi
if [ ! -f /results/attn_meta.json ]; then
  fail "missing /results/attn_meta.json"
fi
if [ ! -x /results/bin/attn_ref ]; then
  fail "missing executable /results/bin/attn_ref"
fi

if [ "$PASS" -eq 1 ]; then
  python3 "$SCRIPT_DIR/oracle.py" || fail "oracle rejected attn artifacts"
fi

# Behavior probe: the CLI must recompute from an arbitrary fixture path.
if [ "$PASS" -eq 1 ] && [ -x /results/bin/attn_ref ]; then
  TMPDIR="$(mktemp -d)"
  python3 - "$TMPDIR" <<'PY' || fail "could not clone fixture"
import json, pathlib, sys
src = json.loads(pathlib.Path("/data/attn_fixture.json").read_text(encoding="utf-8"))
path = pathlib.Path(sys.argv[1]) / "attn_fixture.json"
path.write_text(json.dumps(src) + "\n", encoding="utf-8")
# Perturb one Q value so a hardcoded dump cannot match both runs.
src2 = json.loads(json.dumps(src))
src2["q"][0][0][0] = float(src2["q"][0][0][0]) + 0.37
path2 = pathlib.Path(sys.argv[1]) / "attn_fixture_alt.json"
path2.write_text(json.dumps(src2) + "\n", encoding="utf-8")
PY
  if [ "$PASS" -eq 1 ]; then
    /results/bin/attn_ref --fixture "$TMPDIR/attn_fixture.json" --out "$TMPDIR/out.bin" --meta "$TMPDIR/meta.json"
    rc=$?
    if [ "$rc" -ne 0 ]; then
      fail "attn_ref exited $rc on cloned fixture"
    elif [ ! -f "$TMPDIR/out.bin" ] || [ ! -f "$TMPDIR/meta.json" ]; then
      fail "attn_ref did not write --out/--meta"
    else
      python3 - "$TMPDIR" <<'PY' || fail "attn_ref clone run mismatch"
import pathlib, sys
td = pathlib.Path(sys.argv[1])
a = pathlib.Path("/results/attn_out.bin").read_bytes()
b = (td / "out.bin").read_bytes()
if a != b:
    raise SystemExit("cloned-fixture attn_out.bin differs from /results/attn_out.bin")
print("clone run matches")
PY
    fi
  fi
  if [ "$PASS" -eq 1 ]; then
    /results/bin/attn_ref --fixture "$TMPDIR/attn_fixture_alt.json" --out "$TMPDIR/alt.bin" --meta "$TMPDIR/alt.json"
    rc=$?
    if [ "$rc" -ne 0 ]; then
      fail "attn_ref exited $rc on perturbed fixture"
    else
      python3 - "$TMPDIR" <<'PY' || fail "attn_ref ignored fixture contents"
import pathlib, sys
td = pathlib.Path(sys.argv[1])
a = pathlib.Path("/results/attn_out.bin").read_bytes()
b = (td / "alt.bin").read_bytes()
if a == b:
    raise SystemExit("perturbed fixture produced identical attn_out.bin (hardcoded?)")
print("perturbed fixture changed output")
PY
    fi
  fi
  rm -rf "$TMPDIR"
fi

if [ -n "$DATA_HASH" ]; then
  NOW="$(python3 -c 'import hashlib,pathlib; print(hashlib.sha256(pathlib.Path("/data/attn_fixture.json").read_bytes()).hexdigest())')"
  if [ "$NOW" != "$DATA_HASH" ]; then
    fail "/data/attn_fixture.json was modified"
  fi
fi
