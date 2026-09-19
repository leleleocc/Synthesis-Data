#!/usr/bin/env bash
# Harbor verifier for c1: Suricata autotools + Rust cbindgen repair.
set -uo pipefail

REWARD=/logs/verifier/reward.txt
mkdir -p /logs/verifier
PASS=1
fail() { echo "FAIL: $*" >&2; PASS=0; }
ok() { echo "OK: $*" >&2; }

TESTS_DIR=/tests
if [[ ! -d "$TESTS_DIR" ]]; then
  TESTS_DIR="$(cd "$(dirname "$0")" && pwd)"
fi

# ---------------------------------------------------------------------------
# /data immutability (overlay left it empty aside from base assets)
# ---------------------------------------------------------------------------
if [[ -d /data ]]; then
  # Agent must not write task outputs under /data
  if [[ -e /data/repair-report.json ]] || [[ -e /data/configure.stdout ]]; then
    fail "/data must not receive results artifacts"
  fi
fi

# ---------------------------------------------------------------------------
# Toolchain still available
# ---------------------------------------------------------------------------
if ! command -v rustc >/dev/null 2>&1; then
  fail "rustc missing from PATH"
else
  RUSTC_LINE="$(rustc --version 2>/dev/null | head -1 || true)"
  ok "rustc: $RUSTC_LINE"
fi
if ! command -v cbindgen >/dev/null 2>&1; then
  fail "cbindgen missing from PATH"
else
  CBINDGEN_LINE="$(cbindgen --version 2>/dev/null | head -1 || true)"
  ok "cbindgen: $CBINDGEN_LINE"
fi

# ---------------------------------------------------------------------------
# Build system still Suricata autotools (not replaced)
# ---------------------------------------------------------------------------
if [[ ! -f /app/configure.ac ]]; then
  fail "missing /app/configure.ac (project replaced?)"
fi
if [[ ! -f /app/autogen.sh ]]; then
  fail "missing /app/autogen.sh"
fi
if ! grep -q "AC_INIT\|SURICATA\|suricata" /app/configure.ac 2>/dev/null; then
  fail "/app/configure.ac does not look like Suricata"
fi
# Incident damage must be repaired enough for cbindgen
if grep -q 'min_cbindgen_version="99.0.0"' /app/configure.ac 2>/dev/null; then
  fail "configure.ac still has impossible cbindgen floor 99.0.0"
fi
if [[ -f /app/rust/cbindgen.toml ]]; then
  if grep -q 'language = "Cython"' /app/rust/cbindgen.toml 2>/dev/null; then
    fail "rust/cbindgen.toml still has language = Cython"
  fi
  if ! grep -Eq 'language\s*=\s*"(C|C\+\+)"' /app/rust/cbindgen.toml 2>/dev/null; then
    fail "rust/cbindgen.toml language is not C or C++"
  fi
fi
# Damaged autogen stub must not remain
if grep -q 'cleanup stub: skipping autoreconf' /app/autogen.sh 2>/dev/null; then
  fail "autogen.sh still contains incident cleanup stub"
fi
if ! grep -Eq 'autoreconf|autoconf' /app/autogen.sh 2>/dev/null; then
  fail "autogen.sh does not invoke autoreconf/autoconf"
fi

# ---------------------------------------------------------------------------
# Working configure produced by autogen
# ---------------------------------------------------------------------------
if [[ ! -f /app/configure ]]; then
  fail "missing /app/configure (autogen did not produce it)"
elif [[ ! -x /app/configure ]]; then
  # configure may not have +x bit but should be a script
  if ! head -1 /app/configure | grep -q '#!'; then
    fail "/app/configure is not an executable script"
  fi
fi
# Sanity: regenerated configure is non-trivial
if [[ -f /app/configure ]]; then
  cfg_bytes=$(wc -c < /app/configure 2>/dev/null | tr -d " " || echo 0)
  if [[ "${cfg_bytes}" -lt 10000 ]]; then
    fail "/app/configure too small ($cfg_bytes bytes); not a real autotools configure"
  else
    ok "/app/configure size=$cfg_bytes"
  fi
fi

# ---------------------------------------------------------------------------
# Results artifacts
# ---------------------------------------------------------------------------
REPORT=/results/repair-report.json
STDOUT=/results/configure.stdout

if [[ ! -f "$STDOUT" ]]; then
  fail "missing $STDOUT"
elif [[ ! -s "$STDOUT" ]]; then
  fail "$STDOUT is empty"
else
  ok "configure.stdout present ($(wc -c < "$STDOUT") bytes)"
fi

if [[ ! -f "$REPORT" ]]; then
  fail "missing $REPORT"
else
  # Ensure trailing newline
  if [[ -s "$REPORT" ]] && [[ "$(tail -c 1 "$REPORT" | wc -l)" -eq 0 ]]; then
    fail "$REPORT missing trailing newline"
  fi
fi

# ---------------------------------------------------------------------------
# JSON schema + cross-checks (python stdlib)
# ---------------------------------------------------------------------------
export REPORT STDOUT RUSTC_LINE="${RUSTC_LINE:-}" CBINDGEN_LINE="${CBINDGEN_LINE:-}"
python3 - <<'PY'
import json, os, sys, re
from pathlib import Path

def fail(msg):
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)

report_path = Path(os.environ["REPORT"])
stdout_path = Path(os.environ["STDOUT"])

try:
    raw = report_path.read_text(encoding="utf-8")
except Exception as e:
    fail(f"cannot read report: {e}")

if not raw.endswith("\n"):
    fail("repair-report.json must end with trailing newline")

try:
    data = json.loads(raw)
except Exception as e:
    fail(f"repair-report.json is not valid JSON: {e}")

if not isinstance(data, dict):
    fail("repair-report.json must be a JSON object")

required = {
    "autogen_ok": bool,
    "configure_ok": bool,
    "rustc_version": str,
    "cbindgen_version": str,
    "bindings_header": str,
    "bindings_bytes": int,
    "have_rust": bool,
}
extra = set(data) - set(required)
missing = set(required) - set(data)
if missing:
    fail(f"repair-report.json missing keys: {sorted(missing)}")
if extra:
    fail(f"repair-report.json has unexpected keys: {sorted(extra)}")

for k, t in required.items():
    v = data[k]
    if t is bool:
        if type(v) is not bool:
            fail(f"key {k}: expected bool, got {type(v).__name__}: {v!r}")
    elif t is int:
        if type(v) is not int or isinstance(v, bool):
            fail(f"key {k}: expected int, got {type(v).__name__}: {v!r}")
    elif t is str:
        if type(v) is not str:
            fail(f"key {k}: expected str, got {type(v).__name__}: {v!r}")

if data["autogen_ok"] is not True:
    fail("autogen_ok must be true")
if data["configure_ok"] is not True:
    fail("configure_ok must be true")
if data["have_rust"] is not True:
    fail("have_rust must be true")
if data["bindings_bytes"] <= 0:
    fail("bindings_bytes must be > 0")

header = Path(data["bindings_header"])
if not header.is_absolute():
    fail(f"bindings_header must be absolute path, got {header}")
allowed_prefixes = (
    Path("/app/rust/gen"),
    Path("/app/rust/dist"),
)
if not any(str(header).startswith(str(p) + "/") or header == p / header.name for p in allowed_prefixes):
    # must live under gen or dist
    ok_path = False
    for p in allowed_prefixes:
        try:
            header.resolve().relative_to(p.resolve() if p.exists() else p)
            ok_path = True
            break
        except Exception:
            if str(header).startswith(str(p)):
                ok_path = True
                break
    if not ok_path:
        fail(f"bindings_header must be under /app/rust/gen or /app/rust/dist, got {header}")

if header.name != "rust-bindings.h":
    # instruction names rust-bindings.h specifically
    if "rust-bindings.h" not in header.name:
        fail(f"bindings_header should be rust-bindings.h, got {header.name}")

if not header.is_file():
    fail(f"bindings_header does not exist: {header}")

actual_size = header.stat().st_size
if actual_size <= 0:
    fail(f"bindings header is empty: {header}")
if actual_size != data["bindings_bytes"]:
    fail(f"bindings_bytes {data['bindings_bytes']} != actual size {actual_size}")

text = header.read_text(encoding="utf-8", errors="replace")
# Generated C header should look like a header, not a stub
if len(text.strip()) < 20:
    fail("bindings header content too short")
# Reject Cython-looking garbage if language was wrong
if "cdef " in text and "#include" not in text:
    fail("bindings header looks like Cython, not C")

# Version strings should match live toolchain (first line)
rustc = os.environ.get("RUSTC_LINE", "").strip()
cbind = os.environ.get("CBINDGEN_LINE", "").strip()
if rustc and data["rustc_version"].strip() != rustc:
    # allow report to be exact first line
    if data["rustc_version"].strip() not in rustc and rustc not in data["rustc_version"].strip():
        fail(f"rustc_version {data['rustc_version']!r} != live {rustc!r}")
if cbind and data["cbindgen_version"].strip() != cbind:
    if data["cbindgen_version"].strip() not in cbind and cbind not in data["cbindgen_version"].strip():
        fail(f"cbindgen_version {data['cbindgen_version']!r} != live {cbind!r}")

# configure.stdout should reflect a real configure run with Rust enabled
if not stdout_path.is_file() or stdout_path.stat().st_size == 0:
    fail("configure.stdout missing or empty")
sout = stdout_path.read_text(encoding="utf-8", errors="replace")
# Heuristics: mention rust and not a hard error at the end about cbindgen 99
if re.search(r"cbindgen must be at least version 99", sout, re.I):
    fail("configure.stdout still shows cbindgen 99.x failure")
# have_rust true => configure should have accepted rust
rust_hints = ("rust", "Rust", "HAVE_RUST", "rustc")
if not any(h in sout for h in rust_hints):
    # config.log fallback
    clog = Path("/app/config.log")
    if clog.is_file():
        clog_t = clog.read_text(encoding="utf-8", errors="replace")
        if "HAVE_RUST" not in clog_t and "rustc" not in clog_t.lower():
            fail("configure output/log shows no Rust enablement evidence")
    else:
        fail("configure.stdout has no Rust-related output")

# config.status / config.log evidence of successful configure when present
cfg_status = Path("/app/config.status")
if cfg_status.is_file():
    print("OK: config.status present", file=sys.stderr)
else:
    # Not strictly required if agent cleaned up, but configure_ok claims success
    print("NOTE: no config.status (agent may have cleaned)", file=sys.stderr)

print("OK: repair-report.json cross-checks passed", file=sys.stderr)
sys.exit(0)
PY
# python failure sets exit code; capture into PASS
_py_rc=$?
if [[ $_py_rc -ne 0 ]]; then
  PASS=0
fi

# ---------------------------------------------------------------------------
# Reward
# ---------------------------------------------------------------------------
if [[ "$PASS" -eq 1 ]]; then
  echo 1 > "$REWARD"
  echo "VERIFIER_PASS" >&2
  exit 0
else
  echo 0 > "$REWARD"
  echo "VERIFIER_FAIL" >&2
  exit 1
fi
