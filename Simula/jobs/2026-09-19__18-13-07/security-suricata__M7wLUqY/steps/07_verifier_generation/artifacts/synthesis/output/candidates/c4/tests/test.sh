#!/usr/bin/env bash
# Harbor verifier for c4: suricata.yaml.in migration to offline layout.
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
# /data immutability
# ---------------------------------------------------------------------------
if [[ -f "$TESTS_DIR/data.sha256" ]]; then
  while read -r hash path; do
    # paths in golden are relative like etc/suricata.yaml.in
    rel="$path"
    live=""
    case "$rel" in
      etc/*) live="/data/$rel" ;;
      rules/*) live="/data/$rel" ;;
      *) live="" ;;
    esac
    if [[ -n "$live" && -f "$live" ]]; then
      h=$(sha256sum "$live" | awk '{print $1}')
      if [[ "$h" != "$hash" ]]; then
        fail "/data file modified: $live"
      fi
    fi
  done < "$TESTS_DIR/data.sha256"
fi

# ---------------------------------------------------------------------------
# Directories + files
# ---------------------------------------------------------------------------
for d in /results/etc /results/log /results/rules /results/run /results/data; do
  if [[ ! -d "$d" ]]; then
    fail "missing directory $d"
  fi
done

YAML=/results/suricata.yaml
YAML_ETC=/results/etc/suricata.yaml
REPORT=/results/migration-report.json

if [[ ! -f "$YAML" ]]; then fail "missing $YAML"; fi
if [[ ! -f "$YAML_ETC" ]]; then fail "missing $YAML_ETC"; fi
if [[ ! -f "$REPORT" ]]; then fail "missing $REPORT"; fi

if [[ -s "$REPORT" ]] && [[ "$(tail -c 1 "$REPORT" | wc -l)" -eq 0 ]]; then
  fail "$REPORT missing trailing newline"
fi

# Same bytes at both yaml locations
if ! cmp -s "$YAML" "$YAML_ETC"; then
  fail "/results/suricata.yaml and /results/etc/suricata.yaml differ"
else
  ok "yaml mirrored to etc"
fi

# Supporting configs copied
for f in classification.config reference.config threshold.config; do
  if [[ ! -f "/results/etc/$f" ]]; then
    fail "missing /results/etc/$f"
  elif [[ ! -s "/results/etc/$f" ]]; then
    fail "/results/etc/$f empty"
  else
    # match golden when available
    g="$TESTS_DIR/etc/$f"
    if [[ -f "$g" ]] && ! cmp -s "$g" "/results/etc/$f"; then
      # allow trivial whitespace? instruction says copy — require same content
      fail "/results/etc/$f does not match /data original"
    fi
  fi
done

# Rules installed
rules_count=$(find /results/rules -maxdepth 1 -type f -name '*.rules' 2>/dev/null | wc -l | tr -d ' ')
if [[ "$rules_count" -lt 1 ]]; then
  fail "no *.rules installed under /results/rules"
else
  ok "rules_dir_count=$rules_count"
fi
# All /data/rules should be present when data rules exist
if [[ -d /data/rules ]]; then
  while IFS= read -r -d '' rf; do
    bn=$(basename "$rf")
    if [[ ! -f "/results/rules/$bn" ]]; then
      fail "missing installed rule $bn"
    fi
  done < <(find /data/rules -maxdepth 1 -type f -name '*.rules' -print0 2>/dev/null)
fi

# pkg-config live values
PCAP_VER="missing"
YML_VER="missing"
if pkg-config --exists libpcap 2>/dev/null; then
  PCAP_VER="$(pkg-config --modversion libpcap 2>/dev/null || echo missing)"
fi
if pkg-config --exists yaml-0.1 2>/dev/null; then
  YML_VER="$(pkg-config --modversion yaml-0.1 2>/dev/null || echo missing)"
fi
# Prefer golden pinned versions if present
if [[ -f "$TESTS_DIR/pkg_libpcap.version" ]]; then
  exp=$(cat "$TESTS_DIR/pkg_libpcap.version")
  if [[ "$PCAP_VER" != "$exp" ]]; then
    echo "NOTE: live libpcap $PCAP_VER vs golden $exp" >&2
  fi
fi

export YAML REPORT PCAP_VER YML_VER rules_count TESTS_DIR
python3 - <<'PY'
import json, os, re, sys
from pathlib import Path

errors=[]
def fail(m):
    errors.append(m)
    print(f"FAIL: {m}", file=sys.stderr)
def ok(m):
    print(f"OK: {m}", file=sys.stderr)

yaml_path=Path(os.environ["YAML"])
report_path=Path(os.environ["REPORT"])
if not yaml_path.is_file():
    fail(f"missing {yaml_path}")
    print("OK: c4 early exit on missing yaml", file=sys.stderr)
    sys.exit(1)
text=yaml_path.read_text(encoding="utf-8", errors="replace")

# Autoconf-style @IDENTIFIER@ tokens only
auto_pat=re.compile(r"@([A-Za-z_][A-Za-z0-9_]*)@")
remaining=auto_pat.findall(text)
if remaining:
    fail(f"placeholder_remaining={len(remaining)} tokens still present: {sorted(set('@'+t+'@' for t in remaining))[:8]}")
else:
    ok("no @IDENTIFIER@ placeholders remain")

# Must not be the decoy partial with PLACEHOLDER_VERSION only half-resolved without layout
if "/results/etc" not in text and "default-rule-path" in text:
    # path layout should reference /results/...
    pass
# Check key path substitutions landed
need_substrings = ["/results/log", "/results/rules", "/results/etc", "/results/run"]
# data dir may appear less often
for s in ("/results/log", "/results/rules"):
    if s not in text:
        fail(f"migrated yaml lacks expected path {s}")

# HOME_NET / EXTERNAL_NET
if "10.0.0.0/8" not in text or "192.168.0.0/16" not in text:
    fail("HOME_NET must include 10.0.0.0/8 and 192.168.0.0/16")
# exact list form from instruction
if not re.search(r"HOME_NET:\s*\[?\"?\[?10\.0\.0\.0/8,\s*192\.168\.0\.0/16\]?\"?\]?|HOME_NET:\s*\"\[10\.0\.0\.0/8,192\.168\.0\.0/16\]\"", text):
    # softer: both CIDRs on HOME_NET line
    home_ok=False
    for line in text.splitlines():
        if "HOME_NET" in line and not line.strip().startswith("#"):
            if "10.0.0.0/8" in line and "192.168.0.0/16" in line:
                home_ok=True
                break
    if not home_ok:
        fail("HOME_NET line not set to [10.0.0.0/8,192.168.0.0/16]")

if not re.search(r"EXTERNAL_NET:\s*\"?!\$HOME_NET\"?", text):
    # EXTERNAL_NET: !$HOME_NET variants
    ext_ok=False
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        if "EXTERNAL_NET" in line and "!$HOME_NET" in line.replace(" ", ""):
            ext_ok=True
            break
        if "EXTERNAL_NET" in line and "!$HOME_NET" in line:
            ext_ok=True
            break
    if not ext_ok:
        fail("EXTERNAL_NET must be !$HOME_NET")

# Parse YAML
try:
    import yaml
    doc=yaml.safe_load(text)
except Exception as e:
    fail(f"yaml_parse_ok failed: {e}")
    doc=None

eve_enabled=False
fast_enabled=False
rule_files_listed=0

if isinstance(doc, dict):
    outputs=doc.get("outputs") or []
    if not isinstance(outputs, list):
        fail("outputs missing")
        outputs=[]
    for item in outputs:
        if not isinstance(item, dict):
            continue
        if "eve-log" in item:
            ec=item["eve-log"] or {}
            en=str(ec.get("enabled","")).lower()
            if en in ("yes","true","1","on") or ec.get("enabled") is True:
                eve_enabled=True
            types=ec.get("types") or []
            names=[]
            for t in types:
                if isinstance(t,str): names.append(t)
                elif isinstance(t,dict): names.extend(t.keys())
            for need in ("alert","http","tls","stats"):
                if need not in names:
                    fail(f"eve-log.types missing {need}")
            fn=str(ec.get("filename",""))
            if fn and Path(fn).name != "eve.json" and fn != "eve.json":
                fail(f"eve filename should be eve.json, got {fn}")
        if "fast" in item:
            fc=item["fast"] or {}
            en=str(fc.get("enabled","")).lower()
            if en in ("yes","true","1","on") or fc.get("enabled") is True:
                fast_enabled=True
            fn=str(fc.get("filename",""))
            if fn and Path(fn).name != "fast.log" and "fast.log" not in fn:
                fail(f"fast filename should be fast.log, got {fn}")
    if not eve_enabled:
        fail("eve-log not enabled")
    if not fast_enabled:
        fail("fast log not enabled")

    rfiles=doc.get("rule-files")
    if isinstance(rfiles, list):
        rule_files_listed=len(rfiles)
    else:
        fail("rule-files missing or not a list")

    # hardware plugins disabled/commented: pfring/dpdk/napatech not enabled
    # If sections exist with enabled yes, fail
    for key in ("pfring", "dpdk", "napatech"):
        # top-level or under capture
        if key in doc and isinstance(doc[key], (dict, list)):
            blob=doc[key]
            if isinstance(blob, dict) and str(blob.get("enabled","no")).lower() in ("yes","true","on","1"):
                fail(f"{key} should not be enabled")
        # also scan raw for enabled pfring blocks is hard; check outputs/capture
    raw_lower=text.lower()
    # if uncommented enabled: yes near pfring - soft check via yaml already

# migration-report.json
try:
    raw=report_path.read_text(encoding="utf-8")
except Exception as e:
    fail(f"read report: {e}")
    raw=""
if raw and not raw.endswith("\n"):
    fail("migration-report.json missing trailing newline")
try:
    rep=json.loads(raw) if raw else {}
except Exception as e:
    fail(f"report JSON invalid: {e}")
    rep={}

keys={
    "placeholder_remaining": int,
    "rule_files_listed": int,
    "rules_dir_count": int,
    "pkg_config_libpcap": str,
    "pkg_config_libyaml": str,
    "yaml_parse_ok": bool,
    "eve_enabled": bool,
    "fast_enabled": bool,
}
if not isinstance(rep, dict):
    fail("report must be object")
else:
    missing=set(keys)-set(rep)
    extra=set(rep)-set(keys)
    if missing: fail(f"report missing keys {sorted(missing)}")
    if extra: fail(f"report extra keys {sorted(extra)}")
    for k,t in keys.items():
        if k not in rep: continue
        v=rep[k]
        if t is bool and type(v) is not bool: fail(f"{k} must be bool")
        if t is int and (type(v) is not int or isinstance(v,bool)): fail(f"{k} must be int")
        if t is str and type(v) is not str: fail(f"{k} must be str")

    if rep.get("placeholder_remaining") != 0:
        fail(f"placeholder_remaining must be 0, got {rep.get('placeholder_remaining')}")
    if len(remaining) != rep.get("placeholder_remaining", -1) and not remaining:
        # both zero
        pass
    elif len(remaining) != 0:
        pass  # already failed
    if rep.get("yaml_parse_ok") is not True:
        fail("yaml_parse_ok must be true")
    if rep.get("eve_enabled") is not True:
        fail("eve_enabled must be true")
    if rep.get("fast_enabled") is not True:
        fail("fast_enabled must be true")

    live_rules=int(os.environ.get("rules_count","0"))
    if rep.get("rules_dir_count") != live_rules:
        fail(f"rules_dir_count {rep.get('rules_dir_count')} != actual {live_rules}")
    if rule_files_listed and rep.get("rule_files_listed") != rule_files_listed:
        fail(f"rule_files_listed {rep.get('rule_files_listed')} != yaml {rule_files_listed}")

    pcap=os.environ.get("PCAP_VER","missing")
    yml=os.environ.get("YML_VER","missing")
    if rep.get("pkg_config_libpcap") != pcap:
        fail(f"pkg_config_libpcap {rep.get('pkg_config_libpcap')!r} != live {pcap!r}")
    if rep.get("pkg_config_libyaml") != yml:
        fail(f"pkg_config_libyaml {rep.get('pkg_config_libyaml')!r} != live {yml!r}")

if errors:
    sys.exit(1)
print("OK: c4 checks passed", file=sys.stderr)
sys.exit(0)
PY
py_rc=$?
if [[ $py_rc -ne 0 ]]; then PASS=0; fi

if [[ "$PASS" -eq 1 ]]; then
  echo 1 > "$REWARD"
  echo "VERIFIER_PASS" >&2
  exit 0
else
  echo 0 > "$REWARD"
  echo "VERIFIER_FAIL" >&2
  exit 1
fi
