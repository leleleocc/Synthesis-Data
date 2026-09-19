#!/bin/bash
# Harbor verifier for c2: RDB checksum + millisecond expire repair.
set -uo pipefail

PASS=0
FAILS=0

fail() {
  FAILS=$((FAILS + 1))
}

is_int() {
  echo "$1" | grep -Eq '^[0-9]+$'
}

finish() {
  mkdir -p /logs/verifier
  if [ "$PASS" -eq 1 ]; then
    echo 1 > /logs/verifier/reward.txt
  else
    echo 0 > /logs/verifier/reward.txt
  fi
}
trap finish EXIT

CLI=/app/src/redis-cli
SRV=/app/src/redis-server
CHK=/app/src/redis-check-rdb
ENVF=/results/rdb_audit.env
DUMP=/data/dump.rdb
GOLD=/tests/dump.rdb
PORT=6379

ping_ok() {
  local r
  r="$("$CLI" -h 127.0.0.1 -p "$PORT" PING 2>/dev/null | tr -d '\r')" || true
  [ "$r" = "PONG" ]
}

info_field() {
  local section="$1"
  local field="$2"
  "$CLI" -h 127.0.0.1 -p "$PORT" INFO "$section" 2>/dev/null | tr -d '\r' | awk -F: -v f="$field" '$1==f {print $2; exit}'
}

cfg_get() {
  local key="$1"
  "$CLI" -h 127.0.0.1 -p "$PORT" CONFIG GET "$key" 2>/dev/null | tr -d '\r' | awk 'NR==2 {print; exit}'
}

[ -x "$SRV" ] || fail
[ -x "$CLI" ] || fail
[ -x "$CHK" ] || fail
[ -f "$DUMP" ] || fail
[ -f "$GOLD" ] || fail

# Do not modify /data/dump.rdb: it must stay the sealed overlay dump.
gold_hash="$(sha256sum "$GOLD" | awk '{print $1}')"
dump_hash="$(sha256sum "$DUMP" | awk '{print $1}')"
[ "$gold_hash" = "86d891ddbdee4179dbec8672514237dfff8f0f10666f33e95a1123bf89124f54" ] || fail
[ "$dump_hash" = "$gold_hash" ] || fail

# Intact dump must be accepted by the rebuilt checker.
set +o pipefail
"$CHK" "$DUMP" >/tmp/c2_check_ok.out 2>/tmp/c2_check_ok.err
chk_rc=$?
set -o pipefail
if [ "$chk_rc" -eq 0 ]; then
  chk_status=ok
else
  chk_status=err
  fail
fi
grep -q 'RDB CRC error' /tmp/c2_check_ok.out /tmp/c2_check_ok.err 2>/dev/null && fail

# Truncated copy (checksum bytes removed) must still be rejected.
sz="$(stat -c %s "$DUMP")"
[ "$sz" -gt 16 ] || fail
head -c "$((sz - 8))" "$DUMP" > /tmp/c2_trunc.rdb
set +o pipefail
"$CHK" /tmp/c2_trunc.rdb >/tmp/c2_check_trunc.out 2>/tmp/c2_check_trunc.err
trunc_rc=$?
set -o pipefail
[ "$trunc_rc" -ne 0 ] || fail

# Live server from repaired source, loading that dump.
ping_ok || fail
[ "$(info_field server executable)" = "$SRV" ] || fail
[ "$(info_field server tcp_port)" = "$PORT" ] || fail
[ "$(cfg_get dir)" = "/data" ] || fail
[ "$(cfg_get dbfilename)" = "dump.rdb" ] || fail
[ "$(cfg_get daemonize)" = "no" ] || fail

# Dataset from the dump (not a rewritten fake that left the dump untouched
# without a working loader: check-rdb already required on the golden file).
user1="$("$CLI" -h 127.0.0.1 -p "$PORT" GET user:1 2>/dev/null | tr -d '\r')" || true
cache="$("$CLI" -h 127.0.0.1 -p "$PORT" GET cache:flag 2>/dev/null | tr -d '\r')" || true
ttl="$("$CLI" -h 127.0.0.1 -p "$PORT" TTL user:1 2>/dev/null | tr -d '\r')" || true
cache_ttl="$("$CLI" -h 127.0.0.1 -p "$PORT" TTL cache:flag 2>/dev/null | tr -d '\r')" || true
stype="$("$CLI" -h 127.0.0.1 -p "$PORT" TYPE stream:events 2>/dev/null | tr -d '\r')" || true

[ "$user1" = "alice" ] || fail
[ "$cache" = "ok" ] || fail
if is_int "$ttl" && [ "$ttl" -gt 86400 ]; then
  :
else
  fail
fi
[ "$cache_ttl" = "-1" ] || fail
[ "$stype" = "stream" ] || fail

last_id="$("$CLI" -h 127.0.0.1 -p "$PORT" XINFO STREAM stream:events 2>/dev/null | tr -d '\r' | awk '$1=="last-generated-id" {getline; print; exit}')"
[ "$last_id" = "1700000000000-0" ] || fail

# Last entry field status=ok (and that ID is present).
entry="$("$CLI" -h 127.0.0.1 -p "$PORT" XRANGE stream:events 1700000000000-0 1700000000000-0 2>/dev/null | tr -d '\r')" || true
printf '%s\n' "$entry" | grep -q '1700000000000-0' || fail
printf '%s\n' "$entry" | grep -q 'status' || fail
printf '%s\n' "$entry" | grep -q 'ok' || fail

ks="$(info_field keyspace db0)"
keys_loaded="$(printf '%s\n' "$ks" | sed -n 's/.*keys=\([0-9][0-9]*\).*/\1/p')"
if is_int "$keys_loaded" && [ "$keys_loaded" -ge 3 ]; then
  :
else
  fail
fi

if is_int "$ttl" && [ "$ttl" -gt 86400 ]; then
  ttl_flag=1
else
  ttl_flag=0
fi

# --- env file ---
if [ -f "$ENVF" ]; then
  lastb="$(tail -c 1 "$ENVF" 2>/dev/null | od -An -tx1 | tr -d ' \n')"
  [ "$lastb" = "0a" ] || fail
  nlines="$(awk 'END{print NR}' "$ENVF")"
  [ "$nlines" = "6" ] || fail
  line1="$(awk 'NR==1 {print; exit}' "$ENVF" | tr -d '\r')"
  line2="$(awk 'NR==2 {print; exit}' "$ENVF" | tr -d '\r')"
  line3="$(awk 'NR==3 {print; exit}' "$ENVF" | tr -d '\r')"
  line4="$(awk 'NR==4 {print; exit}' "$ENVF" | tr -d '\r')"
  line5="$(awk 'NR==5 {print; exit}' "$ENVF" | tr -d '\r')"
  line6="$(awk 'NR==6 {print; exit}' "$ENVF" | tr -d '\r')"
  [ "$line1" = "CHECK_RDB_STATUS=${chk_status}" ] || fail
  [ "$line2" = "KEYS_LOADED=${keys_loaded}" ] || fail
  [ "$line3" = "USER1=${user1}" ] || fail
  [ "$line4" = "USER1_TTL_GT_60=${ttl_flag}" ] || fail
  [ "$line5" = "CACHE_FLAG=${cache}" ] || fail
  [ "$line6" = "STREAM_LAST_ID=${last_id}" ] || fail
  [ "$chk_status" = "ok" ] || fail
  [ "$ttl_flag" = "1" ] || fail
  [ "$line6" = "STREAM_LAST_ID=1700000000000-0" ] || fail
  od -An -tx1 "$ENVF" | grep -Eq ' [89a-f][0-9a-f]' && fail
else
  fail
fi

if [ "$FAILS" -eq 0 ]; then
  PASS=1
  exit 0
fi
exit 1
