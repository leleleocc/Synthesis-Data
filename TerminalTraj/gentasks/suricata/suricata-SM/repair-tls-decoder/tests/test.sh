#!/usr/bin/env bash
# Harbor verifier for c6: TLS app-layer decoder repair + pcap classification.
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
if [[ -f "$TESTS_DIR/data.sha256" ]]; then
  while read -r hash path; do
    base=$(basename "$path")
    case "$base" in
      tls-session.pcap)
        if [[ -f /data/pcaps/tls-session.pcap ]]; then
          live=$(sha256sum /data/pcaps/tls-session.pcap | awk '{print $1}')
          [[ "$live" == "$hash" ]] || fail "/data/pcaps/tls-session.pcap modified"
        fi
        ;;
      tls-events.rules.golden)
        if [[ -f /data/rules/tls-events.rules ]]; then
          live=$(sha256sum /data/rules/tls-events.rules | awk '{print $1}')
          [[ "$live" == "$hash" ]] || fail "/data/rules/tls-events.rules modified"
        fi
        ;;
      decoder-events.rules.golden)
        if [[ -f /data/rules/decoder-events.rules ]]; then
          live=$(sha256sum /data/rules/decoder-events.rules | awk '{print $1}')
          [[ "$live" == "$hash" ]] || fail "/data/rules/decoder-events.rules modified"
        fi
        ;;
    esac
  done < "$TESTS_DIR/data.sha256"
fi

# ---------------------------------------------------------------------------
# Binary + results
# ---------------------------------------------------------------------------
BIN=/app/src/suricata
YAML=/results/suricata.yaml
EVE=/results/eve.json
LOGDIR=/results/suricata-log
JSONL=/results/decoder-event-log.jsonl
SUMMARY=/results/repair-summary.json

if [[ ! -f "$BIN" ]]; then
  fail "missing binary $BIN"
else
  BSIZE=$(wc -c < "$BIN" | tr -d ' ')
  [[ "$BSIZE" -gt 0 ]] || fail "binary empty"
  ok "binary size=$BSIZE"
fi

for f in "$YAML" "$EVE" "$JSONL" "$SUMMARY"; do
  if [[ ! -f "$f" ]]; then
    fail "missing $f"
  elif [[ ! -s "$f" ]]; then
    fail "$f empty"
  fi
done
if [[ ! -d "$LOGDIR" ]]; then
  fail "missing $LOGDIR"
fi
if [[ -f "$SUMMARY" ]] && [[ "$(tail -c 1 "$SUMMARY" | wc -l)" -eq 0 ]]; then
  fail "$SUMMARY missing trailing newline"
fi
if [[ -f "$JSONL" ]] && [[ "$(tail -c 1 "$JSONL" | wc -l)" -eq 0 ]]; then
  fail "$JSONL missing trailing newline"
fi

# ---------------------------------------------------------------------------
# Regression must be removed from SSL sources
# ---------------------------------------------------------------------------
SSL_C=/app/src/app-layer-ssl.c
if [[ ! -f "$SSL_C" ]]; then
  fail "missing $SSL_C"
else
  reg_ok=1
  if grep -q 'SURICATA_INCIDENT_TLS_REGRESSION' "$SSL_C"; then
    fail "app-layer-ssl.c still defines SURICATA_INCIDENT_TLS_REGRESSION"
    reg_ok=0
  fi
  if grep -q 'planted: drop SNI' "$SSL_C" || grep -q 'planted secondary regression' "$SSL_C"; then
    fail "app-layer-ssl.c still contains planted regression bodies"
    reg_ok=0
  fi
  if [[ "$reg_ok" -eq 1 ]]; then
    ok "TLS regression markers absent"
  fi
fi

# ssl_source_touched: agent should have changed app-layer-ssl*
# Compare to pristine golden — must differ from damaged OR match near-pristine without regression
if [[ -f "$TESTS_DIR/app-layer-ssl.c.damaged" ]]; then
  if cmp -s "$SSL_C" "$TESTS_DIR/app-layer-ssl.c.damaged"; then
    fail "app-layer-ssl.c identical to damaged golden (not repaired)"
  fi
fi

# ---------------------------------------------------------------------------
# Live -V
# ---------------------------------------------------------------------------
VERSION_LINE=""
if [[ -f "$BIN" ]]; then
  VERSION_OUT="$("$BIN" -V 2>&1 || true)"
  VERSION_LINE="$(printf '%s\n' "$VERSION_OUT" | head -1)"
  if ! printf '%s' "$VERSION_OUT" | grep -q 'Suricata'; then
    fail "suricata -V missing Suricata: ${VERSION_OUT:0:200}"
  else
    ok "version $VERSION_LINE"
  fi
fi

# ---------------------------------------------------------------------------
# YAML sanity (eve tls extended, rules paths)
# ---------------------------------------------------------------------------
export BIN YAML EVE JSONL SUMMARY VERSION_LINE TESTS_DIR SSL_C
python3 - <<'PY'
import json, os, re, sys
from pathlib import Path

errors=[]
def fail(m):
    errors.append(m)
    print(f"FAIL: {m}", file=sys.stderr)
def ok(m):
    print(f"OK: {m}", file=sys.stderr)

tests=Path(os.environ["TESTS_DIR"])
yaml_path=Path(os.environ["YAML"])
eve_path=Path(os.environ["EVE"])
jsonl_path=Path(os.environ["JSONL"])
summary_path=Path(os.environ["SUMMARY"])
ssl_c=Path(os.environ["SSL_C"])

for _p in (yaml_path, eve_path, jsonl_path, summary_path):
    if not _p.is_file():
        fail(f"missing artifact for analysis: {_p}")
if errors:
    sys.exit(1)

try:
    import yaml as pyyaml
    ydoc=pyyaml.safe_load(yaml_path.read_text(encoding="utf-8", errors="replace"))
except Exception as e:
    fail(f"suricata.yaml parse error: {e}")
    ydoc=None

if isinstance(ydoc, dict):
    dld=ydoc.get("default-log-dir")
    if dld is None or str(dld).rstrip("/") != "/results/suricata-log":
        fail(f"default-log-dir must be /results/suricata-log, got {dld}")
    drp=str(ydoc.get("default-rule-path",""))
    if drp.rstrip("/") not in ("/data/rules", "/results/rules"):
        fail(f"default-rule-path must be /data/rules or /results/rules, got {drp}")
    rfiles=ydoc.get("rule-files") or []
    joined=" ".join(str(x) for x in rfiles) if isinstance(rfiles, list) else str(rfiles)
    if "tls-events.rules" not in joined:
        fail("rule-files must include tls-events.rules")
    if "decoder-events.rules" not in joined:
        fail("rule-files must include decoder-events.rules")
    outputs=ydoc.get("outputs") or []
    eve_cfg=None
    for item in outputs if isinstance(outputs, list) else []:
        if isinstance(item, dict) and "eve-log" in item:
            eve_cfg=item["eve-log"]
            break
    if not isinstance(eve_cfg, dict):
        fail("eve-log not configured")
    else:
        en=str(eve_cfg.get("enabled","")).lower()
        if en not in ("yes","true","1","on") and eve_cfg.get("enabled") is not True:
            fail("eve-log not enabled")
        fn=str(eve_cfg.get("filename",""))
        if fn and "eve.json" not in fn:
            fail(f"eve filename unexpected: {fn}")
        types=eve_cfg.get("types") or []
        names=[]
        tmap={}
        for t in types:
            if isinstance(t,str):
                names.append(t); tmap[t]={}
            elif isinstance(t,dict):
                for k,v in t.items():
                    names.append(k)
                    tmap[k]=v if isinstance(v,dict) else {}
        for need in ("alert","tls","anomaly"):
            if need not in names:
                fail(f"eve types missing {need}")
        tcfg=tmap.get("tls") or {}
        if not isinstance(tcfg, dict) or not tcfg:
            fail("tls eve type must set extended: yes")
        else:
            ext=str(tcfg.get("extended","")).lower()
            if ext not in ("yes","true","1","on"):
                fail(f"tls.extended must be yes, got {tcfg.get('extended')}")

# eve.json
recs=[]
if eve_path.is_file():
    for i,line in enumerate(eve_path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if not line.strip():
            continue
        try:
            recs.append(json.loads(line))
        except Exception as e:
            fail(f"eve.json line {i+1} bad JSON: {e}")
            break

tls_recs=[r for r in recs if r.get("event_type")=="tls"]
alert_recs=[r for r in recs if r.get("event_type")=="alert"]
anomaly_recs=[r for r in recs if r.get("event_type")=="anomaly"]
ok(f"eve total={len(recs)} tls={len(tls_recs)} alert={len(alert_recs)} anomaly={len(anomaly_recs)}")
if len(tls_recs) < 1:
    fail("eve.json must contain at least one event_type=tls record")

# decoder-event-log.jsonl
jraw=jsonl_path.read_text(encoding="utf-8")
if not jraw.endswith("\n"):
    fail("decoder-event-log.jsonl must end with trailing newline")
# no extra blank lines beyond trailing newline: splitlines drops final empty after trailing nl
lines=jraw.splitlines()
# allow zero blank lines in middle
if any(not ln.strip() for ln in lines):
    fail("decoder-event-log.jsonl contains blank lines")

jrecs=[]
allowed_keys={"event_type","src_ip","dest_ip","app_proto","tls_sni"}
for i,ln in enumerate(lines):
    try:
        o=json.loads(ln)
    except Exception as e:
        fail(f"jsonl line {i+1} invalid: {e}")
        continue
    if not isinstance(o, dict):
        fail(f"jsonl line {i+1} not object")
        continue
    if set(o.keys()) != allowed_keys:
        fail(f"jsonl line {i+1} keys {sorted(o.keys())} != {sorted(allowed_keys)}")
        continue
    if o.get("event_type") not in ("tls","anomaly","alert"):
        fail(f"jsonl line {i+1} bad event_type {o.get('event_type')}")
    for k in ("src_ip","dest_ip","app_proto","tls_sni"):
        v=o.get(k)
        if v is not None and type(v) is not str:
            fail(f"jsonl line {i+1} {k} must be str or null")
    jrecs.append(o)

# Must be derived from eve: count of filtered eve types should match jsonl lines
eve_filt=[r for r in recs if r.get("event_type") in ("tls","anomaly","alert")]
if len(jrecs) != len(eve_filt):
    fail(f"decoder-event-log.jsonl lines {len(jrecs)} != eve tls/anomaly/alert count {len(eve_filt)}")
else:
    # spot-check first few event_type sequences
    for a,b in zip(jrecs, eve_filt):
        if a.get("event_type") != b.get("event_type"):
            fail("jsonl event_type sequence does not match eve filtered records")
            break
        # src_ip/dest_ip consistency when present
        for src_key, dst_key in (("src_ip","src_ip"),):
            ev_src=b.get("src_ip")
            if a.get("src_ip") is not None and ev_src is not None and a.get("src_ip") != ev_src:
                fail("jsonl src_ip mismatch vs eve")
                break
        sni=None
        tobj=b.get("tls")
        if isinstance(tobj, dict):
            sni=tobj.get("sni")
        if a.get("event_type")=="tls" and sni is not None and a.get("tls_sni") not in (sni, None):
            if a.get("tls_sni") != sni:
                fail(f"tls_sni mismatch: jsonl={a.get('tls_sni')!r} eve={sni!r}")
                break

ok(f"jsonl lines={len(jrecs)}")

# repair-summary.json
try:
    sraw=summary_path.read_text(encoding="utf-8")
except Exception as e:
    fail(f"summary read: {e}"); sraw=""
if sraw and not sraw.endswith("\n"):
    fail("repair-summary.json missing trailing newline")
try:
    summary=json.loads(sraw) if sraw else {}
except Exception as e:
    fail(f"summary JSON: {e}"); summary={}

need={
    "binary_path": str,
    "run_exit": int,
    "eve_tls_count": int,
    "eve_alert_count": int,
    "decoder_log_lines": int,
    "ssl_source_touched": bool,
    "version_line": str,
}
if not isinstance(summary, dict):
    fail("summary must be object")
else:
    missing=set(need)-set(summary)
    extra=set(summary)-set(need)
    if missing: fail(f"summary missing {sorted(missing)}")
    if extra: fail(f"summary extra {sorted(extra)}")
    for k,t in need.items():
        if k not in summary: continue
        v=summary[k]
        if t is bool and type(v) is not bool: fail(f"{k} must be bool")
        if t is int and (type(v) is not int or isinstance(v,bool)): fail(f"{k} must be int")
        if t is str and type(v) is not str: fail(f"{k} must be str")

    if summary.get("run_exit") != 0:
        fail(f"run_exit must be 0, got {summary.get('run_exit')}")
    if summary.get("eve_tls_count", 0) < 1:
        fail("eve_tls_count must be >= 1")
    if summary.get("eve_tls_count") != len(tls_recs):
        fail(f"eve_tls_count {summary.get('eve_tls_count')} != actual {len(tls_recs)}")
    if summary.get("eve_alert_count") != len(alert_recs):
        fail(f"eve_alert_count {summary.get('eve_alert_count')} != actual {len(alert_recs)}")
    if summary.get("decoder_log_lines") != len(jrecs):
        fail(f"decoder_log_lines {summary.get('decoder_log_lines')} != actual {len(jrecs)}")

    bpath=summary.get("binary_path","")
    if not bpath or not Path(bpath).is_file():
        fail(f"binary_path missing or not a file: {bpath}")
    elif Path(bpath).resolve() != Path("/app/src/suricata").resolve():
        if not str(Path(bpath).resolve()).startswith("/app/"):
            fail(f"binary_path not under /app: {bpath}")

    vline=summary.get("version_line","")
    if "Suricata" not in str(vline):
        fail(f"version_line must contain Suricata: {vline!r}")
    live=os.environ.get("VERSION_LINE","").strip()
    if live and vline.strip() != live and "Suricata" in live:
        print(f"NOTE: version_line report={vline!r} live={live!r}", file=sys.stderr)

    # ssl_source_touched true if any app-layer-ssl* differs from pristine
    touched=False
    pristine_c=tests/"app-layer-ssl.c.pristine"
    pristine_h=tests/"app-layer-ssl.h.pristine"
    if pristine_c.is_file() and ssl_c.is_file():
        if ssl_c.read_bytes() != pristine_c.read_bytes():
            touched=True
    hpath=Path("/app/src/app-layer-ssl.h")
    if pristine_h.is_file() and hpath.is_file():
        if hpath.read_bytes() != pristine_h.read_bytes():
            touched=True
    # damaged file always differs from pristine once regression planted; after repair may equal pristine
    # Instruction: true if you changed any file matching app-layer-ssl*
    # If agent restored exactly to pristine, touched is False relative to pristine — but they did change from damaged.
    # Require: not identical to damaged, and summary.ssl_source_touched True when file differs from damaged.
    damaged=tests/"app-layer-ssl.c.damaged"
    changed_from_damaged = damaged.is_file() and ssl_c.is_file() and (ssl_c.read_bytes() != damaged.read_bytes())
    if not changed_from_damaged:
        fail("SSL sources not changed from damaged baseline")
    if summary.get("ssl_source_touched") is not True:
        # If they restored to pristine, they still touched; must report true
        fail("ssl_source_touched must be true after repairing app-layer-ssl*")
    # If summary says true but file still has regression — already failed earlier

if errors:
    sys.exit(1)
print("OK: c6 checks passed", file=sys.stderr)
sys.exit(0)
PY
py_rc=$?
if [[ $py_rc -ne 0 ]]; then PASS=0; fi

# ---------------------------------------------------------------------------
# Optional behavioral re-run if binary+yaml+pcap exist (bounded)
# ---------------------------------------------------------------------------
if [[ "$PASS" -eq 1 && -x "$BIN" && -f "$YAML" && -f /data/pcaps/tls-session.pcap ]]; then
  # Only re-validate if quick: skip full re-run to stay within verifier timeout budget
  # Rely on eve.json TLS evidence already checked.
  ok "skipping full pcap re-run; eve TLS evidence accepted"
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
