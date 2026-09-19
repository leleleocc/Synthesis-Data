#!/bin/bash
# Harbor verifier for c1: AOF rewrite must keep replication identity.
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
ENVF=/results/aof_repair.env
MASTER_P=6379
REPLICA_P=6380

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

# --- /opt/env must be untouched ---
if [ -f /opt/env/setup.sh ]; then
  h="$(sha256sum /opt/env/setup.sh | awk '{print $1}')"
  [ "$h" = "67f1d74525dacf1d75edced0959c305b9cdd354f93b7a349936249cd72dba7cd" ] || fail
else
  fail
fi
if [ -f /opt/env/setup-overlay.sh ]; then
  h="$(sha256sum /opt/env/setup-overlay.sh | awk '{print $1}')"
  [ "$h" = "d6f9eb7da019cca16dee48178e6f944a733fcc5fd99a0130c7ccc28ba86dcfc5" ] || fail
else
  fail
fi
if [ -f /opt/env/smoke_test.sh ]; then
  h="$(sha256sum /opt/env/smoke_test.sh | awk '{print $1}')"
  [ "$h" = "c4fd1b35e2a08aa1cd763088c477072ba9514629cad41842c96dbfac544639be" ] || fail
else
  fail
fi

# --- running rebuilt binaries on required ports ---
[ -x "$SRV" ] || fail
[ -x "$CLI" ] || fail
ping_ok "$MASTER_P" || fail
ping_ok "$REPLICA_P" || fail

m_exec="$(info_field "$MASTER_P" server executable)"
r_exec="$(info_field "$REPLICA_P" server executable)"
[ "$m_exec" = "$SRV" ] || fail
[ "$r_exec" = "$SRV" ] || fail
[ "$(info_field "$MASTER_P" server tcp_port)" = "$MASTER_P" ] || fail
[ "$(info_field "$REPLICA_P" server tcp_port)" = "$REPLICA_P" ] || fail

# --- master config ---
[ "$(cfg_get "$MASTER_P" appendonly)" = "yes" ] || fail
[ "$(cfg_get "$MASTER_P" appendfsync)" = "everysec" ] || fail
[ "$(cfg_get "$MASTER_P" dir)" = "/data" ] || fail
[ "$(cfg_get "$MASTER_P" dbfilename)" = "dump.rdb" ] || fail

pidfile="$(cfg_get "$MASTER_P" pidfile)"
case "$pidfile" in
  /var/run|/*/var/run/*|/var/run/*)
    fail
    ;;
esac
r_pidfile="$(cfg_get "$REPLICA_P" pidfile)"
case "$r_pidfile" in
  /var/run|/*/var/run/*|/var/run/*)
    fail
    ;;
esac

# --- live replication / persistence ---
m_role="$(info_field "$MASTER_P" replication role)"
m_replid="$(info_field "$MASTER_P" replication master_replid)"
m_offset="$(info_field "$MASTER_P" replication master_repl_offset)"
m_aof="$(info_field "$MASTER_P" persistence aof_enabled)"
r_role="$(info_field "$REPLICA_P" replication role)"
r_host="$(info_field "$REPLICA_P" replication master_host)"
r_port="$(info_field "$REPLICA_P" replication master_port)"
r_link="$(info_field "$REPLICA_P" replication master_link_status)"
r_sync="$(info_field "$REPLICA_P" replication master_sync_in_progress)"
r_offset="$(info_field "$REPLICA_P" replication slave_repl_offset)"
r_replid="$(info_field "$REPLICA_P" replication master_replid)"

[ "$m_role" = "master" ] || fail
[ "$r_role" = "slave" ] || fail
[ "$r_host" = "127.0.0.1" ] || fail
[ "$r_port" = "$MASTER_P" ] || fail
[ "$m_aof" = "1" ] || fail

# Wait briefly if the replica is still connecting.
i=0
while [ "$r_link" != "up" ] && [ "$i" -lt 20 ]; do
  sleep 0.25
  r_link="$(info_field "$REPLICA_P" replication master_link_status)"
  r_sync="$(info_field "$REPLICA_P" replication master_sync_in_progress)"
  r_offset="$(info_field "$REPLICA_P" replication slave_repl_offset)"
  r_replid="$(info_field "$REPLICA_P" replication master_replid)"
  m_replid="$(info_field "$MASTER_P" replication master_replid)"
  m_offset="$(info_field "$MASTER_P" replication master_repl_offset)"
  i=$((i + 1))
done

[ "$r_link" = "up" ] || fail
[ "$r_sync" = "0" ] || fail
[ -n "$m_replid" ] || fail
[ "$m_replid" != "0000000000000000000000000000000000000000" ] || fail
echo "$m_replid" | grep -Eq '^[0-9a-f]{40}$' || fail
[ "$r_replid" = "$m_replid" ] || fail
if is_int "$m_offset" && [ "$m_offset" -gt 0 ]; then
  :
else
  fail
fi
if is_int "$r_offset" && [ "$r_offset" -gt 0 ]; then
  :
else
  fail
fi

# Replica offset should track the master (PSYNC), not sit at 0 after a zeroed rewrite.
if is_int "$m_offset" && is_int "$r_offset"; then
  delta=$((m_offset - r_offset))
  if [ "$delta" -lt 0 ]; then
    delta=$((-delta))
  fi
  [ "$delta" -le 1024 ] || fail
else
  fail
fi

# --- dataset ---
ticket="$("$CLI" -h 127.0.0.1 -p "$MASTER_P" GET incident:ticket 2>/dev/null | tr -d '\r')" || true
rticket="$("$CLI" -h 127.0.0.1 -p "$REPLICA_P" GET incident:ticket 2>/dev/null | tr -d '\r')" || true
[ "$ticket" = "AOF-42" ] || fail
[ "$rticket" = "AOF-42" ] || fail

# --- WAITAOF uses a usable local fsynced replication offset ---
# appendfsync everysec: retry across one fsync window rather than treating
# a still-pending everysec flush as a rewrite bug.
wait_local=""
w=0
while [ "$w" -lt 4 ]; do
  wait_out="$("$CLI" -h 127.0.0.1 -p "$MASTER_P" WAITAOF 1 0 1500 2>/dev/null | tr -d '\r')" || true
  wait_local="$(printf '%s\n' "$wait_out" | awk 'NR==1 {print; exit}')"
  [ "$wait_local" = "1" ] && break
  sleep 0.5
  w=$((w + 1))
done
[ "$wait_local" = "1" ] || fail

# --- rewritten AOF base + manifest ---
[ -d /data/appendonlydir ] || fail
manif="$(ls /data/appendonlydir/*.manifest 2>/dev/null | head -n 1)" || true
basef="$(ls /data/appendonlydir/*.base.rdb 2>/dev/null | head -n 1)" || true
[ -n "${manif:-}" ] && [ -s "$manif" ] || fail
[ -n "${basef:-}" ] && [ -s "$basef" ] || fail
if [ -n "${basef:-}" ] && [ -f "$basef" ]; then
  grep -aq 'REDIS' "$basef" || fail
  grep -aq 'incident:ticket' "$basef" || fail
  grep -aq 'AOF-42' "$basef" || fail
  grep -aq 'repl-id' "$basef" || fail
  grep -aq 'repl-offset' "$basef" || fail
  [ -n "$m_replid" ] && grep -aq "$m_replid" "$basef" || fail
  ascii="$(tr -cd '[:print:]' < "$basef")"
  base_off="$(printf '%s\n' "$ascii" | sed -n 's/.*repl-offset\([0-9][0-9]*\).*/\1/p' | head -n 1)"
  if is_int "$base_off" && [ "$base_off" -gt 0 ]; then
    :
  else
    fail
  fi
else
  fail
fi

# --- env file schema and live binding ---
if [ -f "$ENVF" ]; then
  lastb="$(tail -c 1 "$ENVF" 2>/dev/null | od -An -tx1 | tr -d ' \n')"
  [ "$lastb" = "0a" ] || fail
  line1="$(awk 'NR==1 {print; exit}' "$ENVF" | tr -d '\r')"
  line2="$(awk 'NR==2 {print; exit}' "$ENVF" | tr -d '\r')"
  line3="$(awk 'NR==3 {print; exit}' "$ENVF" | tr -d '\r')"
  line4="$(awk 'NR==4 {print; exit}' "$ENVF" | tr -d '\r')"
  line5="$(awk 'NR==5 {print; exit}' "$ENVF" | tr -d '\r')"
  nlines="$(awk 'END{print NR}' "$ENVF")"
  [ "$nlines" = "5" ] || fail
  [ "$line1" = "MASTER_REPLID=${m_replid}" ] || fail
  [ "$line2" = "MASTER_REPL_OFFSET=${m_offset}" ] || fail
  [ "$line3" = "ROLE=${m_role}" ] || fail
  [ "$line4" = "AOF_ENABLED=${m_aof}" ] || fail
  [ "$line5" = "REPLICA_REPL_OFFSET=${r_offset}" ] || fail
  od -An -tx1 "$ENVF" | grep -Eq ' [89a-f][0-9a-f]' && fail
else
  fail
fi

# --- further INCR must not break the replica offset ---
seq_before="$("$CLI" -h 127.0.0.1 -p "$MASTER_P" GET incident:seq 2>/dev/null | tr -d '\r')" || true
incr_out="$("$CLI" -h 127.0.0.1 -p "$MASTER_P" INCR incident:seq 2>/dev/null | tr -d '\r')" || true
echo "$incr_out" | grep -Eq '^[0-9]+$' || fail
if echo "$seq_before" | grep -Eq '^[0-9]+$'; then
  expected_seq=$((seq_before + 1))
  [ "$incr_out" -eq "$expected_seq" ] || fail
fi

j=0
r_seq=""
while [ "$j" -lt 20 ]; do
  r_seq="$("$CLI" -h 127.0.0.1 -p "$REPLICA_P" GET incident:seq 2>/dev/null | tr -d '\r')" || true
  [ "$r_seq" = "$incr_out" ] && break
  sleep 0.25
  j=$((j + 1))
done
[ "$r_seq" = "$incr_out" ] || fail

m_offset2="$(info_field "$MASTER_P" replication master_repl_offset)"
r_offset2="$(info_field "$REPLICA_P" replication slave_repl_offset)"
r_link2="$(info_field "$REPLICA_P" replication master_link_status)"
r_replid2="$(info_field "$REPLICA_P" replication master_replid)"
m_replid2="$(info_field "$MASTER_P" replication master_replid)"
[ "$r_link2" = "up" ] || fail
[ "$m_replid2" = "$m_replid" ] || fail
[ "$r_replid2" = "$m_replid2" ] || fail
if is_int "$m_offset2" && is_int "$m_offset" && [ "$m_offset2" -ge "$m_offset" ]; then
  :
else
  fail
fi
if is_int "$r_offset2" && is_int "$r_offset" && [ "$r_offset2" -ge "$r_offset" ]; then
  :
else
  fail
fi

if [ "$FAILS" -eq 0 ]; then
  PASS=1
  exit 0
fi
exit 1
