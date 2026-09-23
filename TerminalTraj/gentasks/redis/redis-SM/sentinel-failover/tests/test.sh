#!/bin/bash
# Harbor verifier for c6: three-Sentinel quorum failover of cachemaster.
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
ENVF=/results/sentinel_failover.env
S1=26379
S2=26380
S3=26381

ping_ok() {
  local p="$1"
  local r
  r="$("$CLI" -h 127.0.0.1 -p "$p" PING 2>/dev/null | tr -d '\r')" || true
  [ "$r" = "PONG" ]
}

info_field() {
  local p="$1"
  local section="$2"
  local field="$3"
  "$CLI" -h 127.0.0.1 -p "$p" INFO "$section" 2>/dev/null | tr -d '\r' | awk -F: -v f="$field" '$1==f {print $2; exit}'
}

cfg_get() {
  local p="$1"
  local key="$2"
  "$CLI" -h 127.0.0.1 -p "$p" CONFIG GET "$key" 2>/dev/null | tr -d '\r' | awk 'NR==2 {print; exit}'
}

sentinel_pair() {
  local p="$1"
  local key="$2"
  "$CLI" -h 127.0.0.1 -p "$p" SENTINEL master cachemaster 2>/dev/null | tr -d '\r' | awk -v k="$key" 'found {print; exit} $0==k {found=1}'
}

[ -x "$SRV" ] || fail
[ -x "$CLI" ] || fail

# All three Sentinels must still be listening.
ping_ok "$S1" || fail
ping_ok "$S2" || fail
ping_ok "$S3" || fail

# get-master-addr-by-name from 26379.
addr="$("$CLI" -h 127.0.0.1 -p "$S1" SENTINEL get-master-addr-by-name cachemaster 2>/dev/null | tr -d '\r')" || true
new_host="$(printf '%s\n' "$addr" | awk 'NR==1 {print; exit}')"
new_port="$(printf '%s\n' "$addr" | awk 'NR==2 {print; exit}')"
[ "$new_host" = "127.0.0.1" ] || fail
echo "$new_port" | grep -Eq '^[0-9]+$' || fail
[ "$new_port" != "6379" ] || fail

# Promoted process is reachable and is master.
ping_ok "$new_port" || fail
new_role="$(info_field "$new_port" replication role)"
[ "$new_role" = "master" ] || fail
[ "$(info_field "$new_port" server tcp_port)" = "$new_port" ] || fail

# Original 6379 must not remain master if it is still alive.
if ping_ok 6379; then
  old_role="$(info_field 6379 replication role)"
  [ "$old_role" != "master" ] || fail
fi

# Bind every process to 127.0.0.1. Protected-mode on Redis data nodes.
bind_new="$(cfg_get "$new_port" bind)"
printf '%s' "$bind_new" | grep -q '127.0.0.1' || fail
[ "$(cfg_get "$new_port" protected-mode)" = "yes" ] || fail

if ping_ok 6379; then
  bind_old="$(cfg_get 6379 bind)"
  printf '%s' "$bind_old" | grep -q '127.0.0.1' || fail
  [ "$(cfg_get 6379 protected-mode)" = "yes" ] || fail
fi

for sp in "$S1" "$S2" "$S3"; do
  sb="$(cfg_get "$sp" bind)"
  printf '%s' "$sb" | grep -q '127.0.0.1' || fail
done

# Working directories under the specified trees (live process cwd).
proc_cwd() {
  local p="$1"
  local pid
  pid="$(info_field "$p" server process_id)"
  echo "$pid" | grep -Eq '^[0-9]+$' || { echo ""; return; }
  readlink "/proc/${pid}/cwd" 2>/dev/null || true
}

dir_new="$(proc_cwd "$new_port")"
case "$dir_new" in
  /data/master|/data/master/*|/data/replica|/data/replica/*) ;;
  *) fail ;;
esac
if ping_ok 6379; then
  dir_old="$(proc_cwd 6379)"
  case "$dir_old" in
    /data/master|/data/master/*|/data/replica|/data/replica/*) ;;
    *) fail ;;
  esac
fi

sdir1="$(proc_cwd "$S1")"
sdir2="$(proc_cwd "$S2")"
sdir3="$(proc_cwd "$S3")"
case "$sdir1" in
  /data/sentinel1|/data/sentinel1/*) ;;
  *) fail ;;
esac
case "$sdir2" in
  /data/sentinel2|/data/sentinel2/*) ;;
  *) fail ;;
esac
case "$sdir3" in
  /data/sentinel3|/data/sentinel3/*) ;;
  *) fail ;;
esac

# Quorum 2, timers, parallel-syncs, other sentinels.
quorum="$(sentinel_pair "$S1" quorum)"
num_other="$(sentinel_pair "$S1" num-other-sentinels)"
down_after="$(sentinel_pair "$S1" down-after-milliseconds)"
failover_to="$(sentinel_pair "$S1" failover-timeout)"
parallel="$(sentinel_pair "$S1" parallel-syncs)"
ip="$(sentinel_pair "$S1" ip)"
sport="$(sentinel_pair "$S1" port)"

[ "$quorum" = "2" ] || fail
if is_int "$num_other" && [ "$num_other" -ge 2 ]; then
  :
else
  fail
fi
# Automatic failover increments config-epoch. A Sentinel that only ever
# monitored 6380 (never failed over from 6379) stays at epoch 0.
epoch="$(sentinel_pair "$S1" config-epoch)"
if is_int "$epoch" && [ "$epoch" -ge 1 ]; then
  :
else
  fail
fi
# Failover of a real replica topology leaves the demoted master in the
# slave dict even if that process is down. A lone master on 6380 does not.
num_slaves="$(sentinel_pair "$S1" num-slaves)"
if is_int "$num_slaves" && [ "$num_slaves" -ge 1 ]; then
  :
else
  fail
fi
[ "$down_after" = "2000" ] || fail
[ "$failover_to" = "10000" ] || fail
[ "$parallel" = "1" ] || fail
[ "$ip" = "127.0.0.1" ] || fail
[ "$sport" = "$new_port" ] || fail

# Same view from the other two Sentinels.
for sp in "$S2" "$S3"; do
  a="$("$CLI" -h 127.0.0.1 -p "$sp" SENTINEL get-master-addr-by-name cachemaster 2>/dev/null | tr -d '\r')" || true
  h="$(printf '%s\n' "$a" | awk 'NR==1 {print; exit}')"
  p="$(printf '%s\n' "$a" | awk 'NR==2 {print; exit}')"
  [ "$h" = "127.0.0.1" ] || fail
  [ "$p" = "$new_port" ] || fail
  q="$(sentinel_pair "$sp" quorum)"
  [ "$q" = "2" ] || fail
done

# --- env file ---
if [ -f "$ENVF" ]; then
  lastb="$(tail -c 1 "$ENVF" 2>/dev/null | od -An -tx1 | tr -d ' \n')"
  [ "$lastb" = "0a" ] || fail
  nlines="$(awk 'END{print NR}' "$ENVF")"
  [ "$nlines" = "7" ] || fail
  line1="$(awk 'NR==1 {print; exit}' "$ENVF" | tr -d '\r')"
  line2="$(awk 'NR==2 {print; exit}' "$ENVF" | tr -d '\r')"
  line3="$(awk 'NR==3 {print; exit}' "$ENVF" | tr -d '\r')"
  line4="$(awk 'NR==4 {print; exit}' "$ENVF" | tr -d '\r')"
  line5="$(awk 'NR==5 {print; exit}' "$ENVF" | tr -d '\r')"
  line6="$(awk 'NR==6 {print; exit}' "$ENVF" | tr -d '\r')"
  line7="$(awk 'NR==7 {print; exit}' "$ENVF" | tr -d '\r')"
  [ "$line1" = "MASTER_NAME=cachemaster" ] || fail
  [ "$line2" = "OLD_MASTER_PORT=6379" ] || fail
  [ "$line3" = "NEW_MASTER_PORT=${new_port}" ] || fail
  [ "$line4" = "NEW_MASTER_ROLE=master" ] || fail
  [ "$line5" = "SENTINEL_QUORUM=2" ] || fail
  [ "$line6" = "NUM_OTHER_SENTINELS=${num_other}" ] || fail
  [ "$line7" = "FAILOVER_STATE=ok" ] || fail
  od -An -tx1 "$ENVF" | grep -Eq ' [89a-f][0-9a-f]' && fail
else
  fail
fi

if [ "$FAILS" -eq 0 ]; then
  PASS=1
  exit 0
fi
exit 1
