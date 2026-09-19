#!/usr/bin/env bash
# Harbor verifier for c2: build Suricata engine + config test.
set -uo pipefail

REWARD=/logs/verifier/reward.txt
mkdir -p /logs/verifier
# Default to failure so aborted runs never leave a missing reward.txt
echo 0 > "$REWARD"
PASS=1
fail() { echo "FAIL: $*" >&2; PASS=0; }
ok() { echo "OK: $*" >&2; }

TESTS_DIR=/tests
if [[ ! -d "$TESTS_DIR" ]]; then
  TESTS_DIR="$(cd "$(dirname "$0")" && pwd)"
fi

# ---------------------------------------------------------------------------
# /data immutability
# ---------------------------------------------------------------------------
if [[ -e /data/build-info.json ]] || [[ -e /data/suricata.yaml ]]; then
  fail "/data must not receive results artifacts"
fi

# ---------------------------------------------------------------------------
# Engine binary
# ---------------------------------------------------------------------------
BIN=/app/src/suricata
if [[ ! -e "$BIN" ]]; then
  fail "missing engine binary $BIN"
elif [[ ! -f "$BIN" ]]; then
  fail "$BIN is not a regular file"
else
  BSIZE=$(wc -c < "$BIN" | tr -d ' ')
  if [[ "$BSIZE" -le 0 ]]; then
    fail "binary is empty"
  else
    ok "binary size=$BSIZE"
  fi
fi

# Must run -V and print Suricata
VERSION_OUT=""
VERSION_RC=1
if [[ -f "$BIN" ]]; then
  VERSION_OUT="$("$BIN" -V 2>&1 || true)"
  VERSION_RC=0
  # Some builds print to stdout; accept either
  if ! printf '%s' "$VERSION_OUT" | head -1 | grep -q 'Suricata'; then
    # try again capturing stderr only patterns
    if ! printf '%s' "$VERSION_OUT" | grep -q 'Suricata'; then
      fail "suricata -V output does not contain 'Suricata': ${VERSION_OUT:0:200}"
      VERSION_RC=1
    fi
  fi
  VERSION_LINE="$(printf '%s\n' "$VERSION_OUT" | head -1)"
  ok "version: $VERSION_LINE"
fi

# Prefer ELF / executable evidence without requiring a specific path layout
if [[ -f "$BIN" ]] && command -v file >/dev/null 2>&1; then
  ft="$(file -b "$BIN" 2>/dev/null || true)"
  if printf '%s' "$ft" | grep -Eqi 'ELF|executable|shared object'; then
    ok "file type: $ft"
  else
    # still allow if -V worked
    if [[ "$VERSION_RC" -ne 0 ]]; then
      fail "binary does not look executable: $ft"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# Runtime config + log dir
# ---------------------------------------------------------------------------
YAML=/results/suricata.yaml
LOGDIR=/results/suricata-log
INFO=/results/build-info.json

if [[ ! -f "$YAML" ]]; then
  fail "missing $YAML"
elif [[ ! -s "$YAML" ]]; then
  fail "$YAML is empty"
fi
if [[ ! -d "$LOGDIR" ]]; then
  fail "missing log dir $LOGDIR"
fi
if [[ ! -f "$INFO" ]]; then
  fail "missing $INFO"
else
  if [[ -s "$INFO" ]] && [[ "$(tail -c 1 "$INFO" | wc -l)" -eq 0 ]]; then
    fail "$INFO missing trailing newline"
  fi
fi

# ---------------------------------------------------------------------------
# Behavioral config test (-T must exit 0)
# ---------------------------------------------------------------------------
TEST_RC=999
if [[ -f "$BIN" && -f "$YAML" ]]; then
  mkdir -p "$LOGDIR"
  set +e
  "$BIN" -T -c "$YAML" -l "$LOGDIR" >/tmp/c2-config-test.out 2>&1
  TEST_RC=$?
  set -uo pipefail
  if [[ "$TEST_RC" -ne 0 ]]; then
    fail "suricata -T exited $TEST_RC (expected 0); tail: $(tail -5 /tmp/c2-config-test.out 2>/dev/null)"
  else
    ok "config test -T exited 0"
  fi
fi

# ---------------------------------------------------------------------------
# build-info.json schema + consistency
# ---------------------------------------------------------------------------
export BIN YAML INFO VERSION_LINE="${VERSION_LINE:-}" TEST_RC BSIZE="${BSIZE:-0}"
python3 - <<'PY'
import json, os, sys
from pathlib import Path

errors=[]
def fail(m):
    errors.append(m)
    print(f"FAIL: {m}", file=sys.stderr)

info_path=Path(os.environ["INFO"])
try:
    raw=info_path.read_text(encoding="utf-8")
except Exception as e:
    fail(f"read build-info: {e}")
    raw=""
if raw and not raw.endswith("\n"):
    fail("build-info.json must end with trailing newline")
try:
    data=json.loads(raw) if raw else {}
except Exception as e:
    fail(f"build-info.json invalid JSON: {e}")
    data={}

if not isinstance(data, dict):
    fail("build-info.json must be object")
else:
    required={
        "binary_path": str,
        "version_line": str,
        "configure_args": str,
        "config_test_exit": int,
        "binary_bytes": int,
    }
    missing=set(required)-set(data)
    extra=set(data)-set(required)
    if missing:
        fail(f"missing keys: {sorted(missing)}")
    if extra:
        fail(f"unexpected keys: {sorted(extra)}")
    for k,t in required.items():
        if k not in data: continue
        v=data[k]
        if t is int and (type(v) is not int or isinstance(v, bool)):
            fail(f"{k} must be int, got {type(v).__name__}")
        if t is str and type(v) is not str:
            fail(f"{k} must be str, got {type(v).__name__}")

    if data.get("config_test_exit") != 0:
        fail(f"config_test_exit must be 0, got {data.get('config_test_exit')}")
    live_rc=int(os.environ.get("TEST_RC","999"))
    if live_rc != 0:
        fail(f"live -T rc was {live_rc}")
    # If both claim 0, good; if report says 0 but we got non-zero already failed above

    bpath=data.get("binary_path","")
    if bpath != "/app/src/suricata":
        # allow if it's the same file via absolute path
        if not Path(bpath).is_file():
            fail(f"binary_path does not exist: {bpath}")
        else:
            # must be the engine we tested or same inode
            try:
                if Path(bpath).resolve() != Path("/app/src/suricata").resolve():
                    # still ok if -V works on it and path is under /app
                    if not str(Path(bpath).resolve()).startswith("/app/"):
                        fail(f"binary_path outside /app: {bpath}")
            except Exception:
                fail(f"binary_path unresolvable: {bpath}")

    actual=Path("/app/src/suricata")
    if actual.is_file():
        asize=actual.stat().st_size
        if data.get("binary_bytes", 0) <= 0:
            fail("binary_bytes must be > 0")
        elif data.get("binary_bytes") != asize:
            fail(f"binary_bytes {data.get('binary_bytes')} != actual {asize}")

    vline=data.get("version_line","")
    if "Suricata" not in vline:
        fail(f"version_line must contain Suricata: {vline!r}")
    live=os.environ.get("VERSION_LINE","").strip()
    if live and vline.strip() and vline.strip() != live.strip():
        # first line comparison; allow minor whitespace
        if "Suricata" not in live or vline.strip() not in live and live not in vline.strip():
            # only soft-check: live must contain Suricata which we already checked
            if vline.strip() != live:
                print(f"NOTE: version_line differs from live -V first line: report={vline!r} live={live!r}", file=sys.stderr)

    carg=data.get("configure_args","")
    if not isinstance(carg, str) or not carg.strip():
        fail("configure_args must be non-empty string (args after configure script path)")
    # Instruction requires configure with prefix /usr/local
    if "prefix" not in carg and "/usr/local" not in carg:
        fail(f"configure_args must reflect --prefix=/usr/local, got {carg!r}")

if errors:
    sys.exit(1)
print("OK: build-info.json checks passed", file=sys.stderr)
sys.exit(0)
PY
py_rc=$?
if [[ $py_rc -ne 0 ]]; then
  PASS=0
fi

# Makefile.am should again include src if still present (onboarding defect fixed or worked around)
if [[ -f /app/Makefile.am ]]; then
  if grep -E '^SUBDIRS' /app/Makefile.am | grep -q 'missing-onboarding-dir'; then
    # Binary might still exist if agent built src manually — instruction allows adjusting build files
    # but leaving the defect while claiming success is suspicious if binary was faked
    if [[ ! -f /app/src/suricata ]]; then
      fail "SUBDIRS still damaged and no binary"
    else
      echo "NOTE: SUBDIRS still mentions missing-onboarding-dir but binary exists" >&2
    fi
  fi
fi

if [[ "$PASS" -eq 1 ]]; then
  echo 1 > "$REWARD"
  echo "VERIFIER_PASS" >&2
  exit 0
else
  echo 0 > "$REWARD"
  echo "VERIFIER_FAIL" >&2
  exit 1
fi
