#!/usr/bin/env bash
# Harbor verifier for c3: HTTP rule repair + Eve TLS/HTTP offline pcap run.
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
# /data immutability vs goldens
# ---------------------------------------------------------------------------
if [[ -f "$TESTS_DIR/data.sha256" ]]; then
  # Verify key /data fixtures unchanged
  while read -r hash path; do
    base=$(basename "$path")
    case "$base" in
      data-http-events.rules.golden)
        if [[ -f /data/rules/http-events.rules ]]; then
          live=$(sha256sum /data/rules/http-events.rules | awk '{print $1}')
          if [[ "$live" != "$hash" ]]; then
            fail "/data/rules/http-events.rules was modified (hash mismatch)"
          fi
        fi
        ;;
      data-tls-events.rules.golden)
        if [[ -f /data/rules/tls-events.rules ]]; then
          live=$(sha256sum /data/rules/tls-events.rules | awk '{print $1}')
          if [[ "$live" != "$hash" ]]; then
            fail "/data/rules/tls-events.rules was modified"
          fi
        fi
        ;;
      session.pcap)
        if [[ -f /data/pcaps/session.pcap ]]; then
          live=$(sha256sum /data/pcaps/session.pcap | awk '{print $1}')
          if [[ "$live" != "$hash" ]]; then
            fail "/data/pcaps/session.pcap was modified"
          fi
        fi
        ;;
    esac
  done < "$TESTS_DIR/data.sha256"
else
  echo "NOTE: no data.sha256 golden" >&2
fi

# ---------------------------------------------------------------------------
# Deliverable files
# ---------------------------------------------------------------------------
HTTP_RULES=/results/http-events.rules
TLS_RULES=/results/tls-events.rules
YAML=/results/suricata.yaml
EVE=/results/eve.json
SUMMARY=/results/audit-summary.json
LOGDIR=/results/suricata-log

for f in "$HTTP_RULES" "$TLS_RULES" "$YAML" "$EVE" "$SUMMARY"; do
  if [[ ! -f "$f" ]]; then
    fail "missing $f"
  elif [[ ! -s "$f" ]]; then
    fail "$f is empty"
  fi
done

if [[ -f "$SUMMARY" ]] && [[ "$(tail -c 1 "$SUMMARY" | wc -l)" -eq 0 ]]; then
  fail "$SUMMARY missing trailing newline"
fi

# ---------------------------------------------------------------------------
# Rules + yaml + eve + summary checks in Python
# ---------------------------------------------------------------------------
export HTTP_RULES TLS_RULES YAML EVE SUMMARY TESTS_DIR
python3 - <<'PY'
import json, os, re, sys
from pathlib import Path

errors=[]
def fail(m):
    errors.append(m)
    print(f"FAIL: {m}", file=sys.stderr)

def ok(m):
    print(f"OK: {m}", file=sys.stderr)

tests = Path(os.environ["TESTS_DIR"])
http_path = Path(os.environ["HTTP_RULES"])
tls_path = Path(os.environ["TLS_RULES"])
yaml_path = Path(os.environ["YAML"])
eve_path = Path(os.environ["EVE"])
summary_path = Path(os.environ["SUMMARY"])

for _p in (http_path, tls_path, yaml_path, eve_path, summary_path):
    if not _p.is_file():
        fail(f"missing artifact for analysis: {_p}")
if errors:
    sys.exit(1)

stock_http = (tests / "stock-http-events.rules").read_text(encoding="utf-8", errors="replace")
stock_tls = (tests / "stock-tls-events.rules").read_text(encoding="utf-8", errors="replace")

def parse_alert_rules(text):
    """Return list of (sid, full_rule_text, first_line_proto) for alert rules."""
    rules=[]
    buf=[]
    for line in text.splitlines():
        stripped=line.strip()
        if not stripped or stripped.startswith("#"):
            # if we are mid-rule, still accumulate non-empty? comments mid-rule rare
            if buf and stripped.startswith("#"):
                continue
            continue
        if not buf:
            if stripped.startswith("alert "):
                buf=[line]
                if stripped.endswith(")"):
                    rules.append("\n".join(buf))
                    buf=[]
            continue
        else:
            buf.append(line)
            if stripped.endswith(")"):
                rules.append("\n".join(buf))
                buf=[]
    return rules

def sids_from_rules(rules):
    out=[]
    for r in rules:
        m=re.search(r"sid\s*:\s*(\d+)", r)
        if m:
            out.append(int(m.group(1)))
    return out

def all_sids_in_text(text):
    # any sid on non-comment lines (for stock range membership)
    s=set()
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        for m in re.finditer(r"sid\s*:\s*(\d+)", line):
            s.add(int(m.group(1)))
    return s

stock_http_rules = parse_alert_rules(stock_http)
stock_http_sids = set(sids_from_rules(stock_http_rules))
stock_tls_rules = parse_alert_rules(stock_tls)
stock_tls_sids = set(sids_from_rules(stock_tls_rules))

http_text = http_path.read_text(encoding="utf-8", errors="replace")
tls_text = tls_path.read_text(encoding="utf-8", errors="replace")
http_rules = parse_alert_rules(http_text)
tls_rules = parse_alert_rules(tls_text)
http_sids = sids_from_rules(http_rules)
tls_sids = sids_from_rules(tls_rules)

ok(f"http alert rules={len(http_rules)} sids={sorted(set(http_sids))[:5]}...")
ok(f"tls alert rules={len(tls_rules)}")

# Keep every original sid from stock HTTP event range present in the broken file
# Stock sids that appear as alert rules must be present in repaired file
missing = stock_http_sids - set(http_sids)
if missing:
    fail(f"repaired http-events.rules missing stock sids: {sorted(missing)}")

# Must not keep the bogus TLS-suppress sid 2221099 from the broken file
if 2221099 in set(http_sids) or 2221099 in all_sids_in_text(http_text):
    fail("http-events.rules still contains bogus sid 2221099 (TLS-suppress collision)")

# sid 2221003 must exist again (was truncated in broken file)
if 2221003 not in set(http_sids):
    fail("sid 2221003 missing from repaired http rules")

# Valid Suricata rule syntax basics: each alert rule has sid:N; and ends with )
for r in http_rules:
    if not re.search(r"sid\s*:\s*\d+\s*;", r):
        fail(f"http rule missing well-formed sid:N; : {r[:120]}")
        break
    if "sid:" in r and re.search(r"sid:\d+\s+rev:", r):
        fail(f"http rule has broken sid/rev separator (missing semicolon): {r[:120]}")
        break

# Do not rewrite TLS app-layer event rules as HTTP TLS-collision
# sid 2221015 must be HTTP-oriented again (not alert tls with tls.invalid_sni_length)
for r in http_rules:
    if re.search(r"sid\s*:\s*2221015\s*;", r):
        if re.match(r"alert\s+tls\b", r.strip()):
            fail("sid 2221015 still alert tls (should be HTTP event rule)")
        if "tls.invalid_sni_length" in r:
            fail("sid 2221015 still references tls.invalid_sni_length")
        if not re.match(r"alert\s+http\b", r.strip()):
            fail(f"sid 2221015 should be alert http, got: {r[:80]}")
        break
else:
    fail("sid 2221015 not found in repaired http rules")

# sid 2221000 should not keep content:"BROKEN"
for r in http_rules:
    if re.search(r"sid\s*:\s*2221000\s*;", r):
        if 'content:"BROKEN"' in r or "content:\"BROKEN\"" in r:
            fail("sid 2221000 still contains content:BROKEN corruption")
        if re.match(r"alert\s+tcp\b", r.strip()) and "app-layer-event:http" in r:
            # tcp with http app-layer-event is the planted corruption; stock is alert http
            fail("sid 2221000 still alert tcp with http app-layer-event")
        break

# sid 2221014 flow direction: stock is to_server for missing Host header
for r in http_rules:
    if re.search(r"sid\s*:\s*2221014\s*;", r):
        if "to_client" in r and "to_server" not in r:
            fail("sid 2221014 still has incorrect flow to_client only")
        break

# TLS rules: no functional loss of TLS decoder/handshake coverage
missing_tls = stock_tls_sids - set(tls_sids)
if missing_tls:
    fail(f"tls-events.rules missing stock sids: {sorted(missing_tls)}")
if len(tls_rules) < len(stock_tls_rules):
    fail(f"tls rule count {len(tls_rules)} < stock {len(stock_tls_rules)}")

# Reject empty/header-only or copy of broken http from /data golden if identical to broken
broken_path = tests / "data-http-events.rules.golden"
if broken_path.is_file():
    broken = broken_path.read_text(encoding="utf-8", errors="replace")
    if http_text.strip() == broken.strip():
        fail("http-events.rules is still the broken /data copy")

# ---------------------------------------------------------------------------
# suricata.yaml requirements
# ---------------------------------------------------------------------------
try:
    import yaml
except ImportError:
    yaml = None

yraw = yaml_path.read_text(encoding="utf-8", errors="replace")

def yaml_load(text):
    if yaml is not None:
        return yaml.safe_load(text)
    # minimal fallback is insufficient for nested; require pyyaml from base image
    raise RuntimeError("python3-yaml required")

try:
    ydoc = yaml_load(yraw)
except Exception as e:
    fail(f"suricata.yaml failed to parse: {e}")
    ydoc = None

if isinstance(ydoc, dict):
    # default-rule-path at /results
    drp = ydoc.get("default-rule-path") or ydoc.get("default-rule-path".replace("-", "_"))
    # keys use hyphens in suricata
    drp = ydoc.get("default-rule-path")
    if drp is None:
        fail("suricata.yaml missing default-rule-path")
    else:
        drp_s = str(drp).rstrip("/")
        if drp_s != "/results":
            fail(f"default-rule-path must be /results, got {drp}")

    dld = ydoc.get("default-log-dir")
    if dld is None:
        fail("suricata.yaml missing default-log-dir")
    else:
        if str(dld).rstrip("/") != "/results/suricata-log":
            fail(f"default-log-dir must be /results/suricata-log, got {dld}")

    rfiles = ydoc.get("rule-files")
    if not isinstance(rfiles, list) or not rfiles:
        fail("rule-files must be a non-empty list")
    else:
        # entries may be strings
        norm=[]
        for item in rfiles:
            if isinstance(item, str):
                norm.append(item)
            elif isinstance(item, dict):
                norm.extend(str(x) for x in item.keys())
            else:
                norm.append(str(item))
        joined=" ".join(norm)
        if "http-events.rules" not in joined:
            fail("rule-files must list http-events.rules")
        if "tls-events.rules" not in joined:
            fail("rule-files must list tls-events.rules")

    outputs = ydoc.get("outputs")
    if not isinstance(outputs, list):
        fail("outputs must be a list enabling eve-log")
        outputs=[]
    eve_cfg=None
    for item in outputs:
        if isinstance(item, dict) and "eve-log" in item:
            eve_cfg = item["eve-log"]
            break
    if not isinstance(eve_cfg, dict):
        fail("eve-log not enabled under outputs")
    else:
        if eve_cfg.get("enabled") not in (True, "yes", "true", "on", 1, "Yes"):
            # sometimes enabled: yes as string
            en = str(eve_cfg.get("enabled", "")).lower()
            if en not in ("yes", "true", "on", "1"):
                fail(f"eve-log.enabled not yes: {eve_cfg.get('enabled')}")
        ft = str(eve_cfg.get("filetype", "regular")).lower()
        if ft not in ("regular", "file", ""):
            # instruction: filetype regular
            if ft not in ("regular",):
                fail(f"eve-log.filetype should be regular, got {ft}")
        fn = str(eve_cfg.get("filename", ""))
        # may be relative eve.json or absolute /results/eve.json
        if "eve.json" not in fn and fn != "/results/eve.json":
            # filename may be just eve.json with log dir elsewhere; instruction says to /results/eve.json
            if fn and Path(fn).name != "eve.json":
                fail(f"eve-log.filename should be eve.json, got {fn}")
        types = eve_cfg.get("types") or []
        if not isinstance(types, list):
            fail("eve-log.types must be a list")
            types=[]
        # normalize type names
        type_names=[]
        type_map={}
        for t in types:
            if isinstance(t, str):
                type_names.append(t)
                type_map[t]={}
            elif isinstance(t, dict):
                for k,v in t.items():
                    type_names.append(k)
                    type_map[k]=v if isinstance(v, dict) else {}
        for need in ("alert", "http", "tls"):
            if need not in type_names:
                fail(f"eve-log.types missing {need}")
        # http extended yes, tls extended yes
        for key in ("http", "tls"):
            cfg = type_map.get(key) or {}
            if isinstance(cfg, dict) and cfg:
                ext = cfg.get("extended")
                if ext is not None:
                    exs = str(ext).lower()
                    if exs not in ("yes", "true", "1", "on"):
                        fail(f"eve {key}.extended must be yes, got {ext}")
                else:
                    # extended key missing — instruction requires extended: yes
                    fail(f"eve {key} must set extended: yes")
            else:
                # bare '- http' without extended
                fail(f"eve {key} must be mapping with extended: yes")

    vars_ = ydoc.get("vars")
    if not isinstance(vars_, dict):
        fail("vars address/port groups missing")
    else:
        addr = vars_.get("address-groups") or vars_.get("address_groups")
        if not isinstance(addr, dict) or "HOME_NET" not in addr:
            fail("vars.address-groups.HOME_NET missing")

# ---------------------------------------------------------------------------
# eve.json JSONL
# ---------------------------------------------------------------------------
eve_lines=[]
if eve_path.is_file():
    for i, line in enumerate(eve_path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if not line.strip():
            continue
        try:
            eve_lines.append(json.loads(line))
        except Exception as e:
            fail(f"eve.json line {i+1} invalid JSON: {e}")
            break

if len(eve_lines) < 1:
    fail("eve.json must contain >= 1 JSON records")

def et(rec):
    return rec.get("event_type")

http_n = sum(1 for r in eve_lines if et(r)=="http")
tls_n = sum(1 for r in eve_lines if et(r)=="tls")
alert_n = sum(1 for r in eve_lines if et(r)=="alert")
ok(f"eve records={len(eve_lines)} http={http_n} tls={tls_n} alert={alert_n}")

tls_ext = False
for r in eve_lines:
    if et(r) != "tls":
        continue
    tobj = r.get("tls")
    if isinstance(tobj, dict):
        if any(k in tobj for k in ("sni", "version", "subject")):
            tls_ext = True
            break
if not tls_ext:
    fail("no tls eve record with tls.sni/version/subject (extended TLS metadata required)")

# ---------------------------------------------------------------------------
# audit-summary.json
# ---------------------------------------------------------------------------
try:
    sraw = summary_path.read_text(encoding="utf-8")
except Exception as e:
    fail(f"read summary: {e}")
    sraw=""
if sraw and not sraw.endswith("\n"):
    fail("audit-summary.json missing trailing newline")
try:
    summary = json.loads(sraw) if sraw else {}
except Exception as e:
    fail(f"audit-summary.json invalid JSON: {e}")
    summary={}

req_keys = {
    "http_rule_count": int,
    "tls_rule_count": int,
    "eve_records": int,
    "eve_http_events": int,
    "eve_tls_events": int,
    "eve_alert_events": int,
    "tls_extended_fields_present": bool,
    "rules_load_ok": bool,
}
if not isinstance(summary, dict):
    fail("audit-summary.json must be object")
else:
    missing=set(req_keys)-set(summary)
    extra=set(summary)-set(req_keys)
    if missing:
        fail(f"summary missing keys: {sorted(missing)}")
    if extra:
        fail(f"summary unexpected keys: {sorted(extra)}")
    for k,t in req_keys.items():
        if k not in summary: continue
        v=summary[k]
        if t is bool and type(v) is not bool:
            fail(f"{k} must be bool")
        if t is int and (type(v) is not int or isinstance(v, bool)):
            fail(f"{k} must be int")

    if summary.get("rules_load_ok") is not True:
        fail("rules_load_ok must be true")
    if summary.get("tls_extended_fields_present") is not True:
        fail("tls_extended_fields_present must be true")
    if summary.get("eve_records", 0) < 1:
        fail("eve_records must be >= 1")

    # Cross-check counts against artifacts
    if summary.get("http_rule_count") != len(http_rules):
        fail(f"http_rule_count {summary.get('http_rule_count')} != actual alert rules {len(http_rules)}")
    if summary.get("tls_rule_count") != len(tls_rules):
        fail(f"tls_rule_count {summary.get('tls_rule_count')} != actual {len(tls_rules)}")
    if summary.get("eve_records") != len(eve_lines):
        fail(f"eve_records {summary.get('eve_records')} != actual {len(eve_lines)}")
    if summary.get("eve_http_events") != http_n:
        fail(f"eve_http_events {summary.get('eve_http_events')} != actual {http_n}")
    if summary.get("eve_tls_events") != tls_n:
        fail(f"eve_tls_events {summary.get('eve_tls_events')} != actual {tls_n}")
    if summary.get("eve_alert_events") != alert_n:
        fail(f"eve_alert_events {summary.get('eve_alert_events')} != actual {alert_n}")
    if summary.get("tls_extended_fields_present") is True and not tls_ext:
        fail("summary claims tls_extended_fields_present but eve lacks fields")

if errors:
    sys.exit(1)
print("OK: c3 artifact checks passed", file=sys.stderr)
sys.exit(0)
PY
py_rc=$?
if [[ $py_rc -ne 0 ]]; then
  PASS=0
fi

# Optional: if binary exists, re-run is not required (agent already produced eve).
# Behavioral proof is the eve.json content + rules_load_ok cross-check.

if [[ "$PASS" -eq 1 ]]; then
  echo 1 > "$REWARD"
  echo "VERIFIER_PASS" >&2
  exit 0
else
  echo 0 > "$REWARD"
  echo "VERIFIER_FAIL" >&2
  exit 1
fi
