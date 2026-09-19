#!/bin/bash
# Harbor verifier for c3: default -O2 without LTO, TLS paths intact.
set -uo pipefail

PASS=0
FAILS=0

fail() {
  FAILS=$((FAILS + 1))
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

ENVF=/results/build_flags.env
MKSRC=/app/src/Makefile
MK=/tmp/c3_Makefile.verify
SRV=/app/src/redis-server
CLI=/app/src/redis-cli

[ -f "$MKSRC" ] || fail
[ -x "$SRV" ] || fail
[ -x "$CLI" ] || fail

# Dry-run the agent's Makefile without applying persisted .make-settings
# (those would otherwise hide the real default OPTIMIZATION / REDIS_CFLAGS).
# -n never runs persist-settings/distclean.
sed '/^-include \.make-settings/d' "$MKSRC" > "$MK" || fail

compile_line() {
  local opt="$1"
  make -C /app/src -f "$MK" -n -B -o persist-settings -o .make-prerequisites \
    OPTIMIZATION="$opt" server.o 2>/dev/null | grep ' -c server.c' | tail -n 1
}

compile_default() {
  make -C /app/src -f "$MK" -n -B -o persist-settings -o .make-prerequisites \
    server.o 2>/dev/null | grep ' -c server.c' | tail -n 1
}

link_line_tls_yes() {
  make -C /app/src -f "$MK" -n -B -o persist-settings -o .make-prerequisites \
    BUILD_TLS=yes OPTIMIZATION=-O2 redis-server 2>/dev/null | grep ' -o redis-server ' | tail -n 1
}

compile_tls_yes() {
  make -C /app/src -f "$MK" -n -B -o persist-settings -o .make-prerequisites \
    BUILD_TLS=yes OPTIMIZATION=-O2 server.o 2>/dev/null | grep ' -c server.c' | tail -n 1
}

module_line() {
  make -C /app/src -f "$MK" -n -B -o persist-settings -o .make-prerequisites \
    BUILD_TLS=module OPTIMIZATION=-O2 redis-tls.so 2>/dev/null | grep 'redis-tls.so' | grep ' -shared ' | tail -n 1
}

default_cc="$(compile_default)"
o2_cc="$(compile_line -O2)"
o3_cc="$(compile_line -O3)"
tls_cc="$(compile_tls_yes)"
tls_ld="$(link_line_tls_yes)"
mod_cc="$(module_line)"

[ -n "$default_cc" ] || fail
[ -n "$o2_cc" ] || fail
[ -n "$o3_cc" ] || fail
[ -n "$tls_cc" ] || fail
[ -n "$tls_ld" ] || fail
[ -n "$mod_cc" ] || fail

# Default make (no extra knobs) and OPTIMIZATION=-O2: -O2, no LTO, jemalloc.
printf '%s\n' "$default_cc" | grep -q -- ' -O2 ' || fail
printf '%s\n' "$default_cc" | grep -q -- ' -O3 ' && fail
printf '%s\n' "$default_cc" | grep -q -- '-flto' && fail
printf '%s\n' "$default_cc" | grep -q -- 'USE_JEMALLOC' || fail
printf '%s\n' "$o2_cc" | grep -q -- ' -O2 ' || fail
printf '%s\n' "$o2_cc" | grep -q -- '-flto' && fail

# OPTIMIZATION=-O3 still enables LTO.
printf '%s\n' "$o3_cc" | grep -q -- ' -O3 ' || fail
printf '%s\n' "$o3_cc" | grep -q -- '-flto' || fail

# BUILD_TLS=yes defines USE_OPENSSL and links libhiredis_ssl even at default -O2.
printf '%s\n' "$tls_cc" | grep -q -- '-DUSE_OPENSSL=1' || fail
printf '%s\n' "$tls_ld" | grep -q 'libhiredis_ssl.a' || fail
printf '%s\n' "$tls_ld" | grep -q 'jemalloc' || fail

# BUILD_TLS=module still produces redis-tls.so.
printf '%s\n' "$mod_cc" | grep -q -- '-shared' || fail
printf '%s\n' "$mod_cc" | grep -q -- '-fPIC' || fail
printf '%s\n' "$mod_cc" | grep -q -- '-DUSE_OPENSSL=2' || fail
printf '%s\n' "$mod_cc" | grep -q 'libhiredis_ssl.a' || fail

# persist-settings keeps recording BUILD_TLS.
persist_n="$(make -C /app/src -f "$MK" -n persist-settings BUILD_TLS=yes 2>/dev/null || true)"
printf '%s\n' "$persist_n" | grep -q 'echo BUILD_TLS=yes' || fail

# Leftover default binaries from `make` with no extra knobs.
set +o pipefail
"$SRV" --version >/tmp/c3_srv_ver.out 2>/tmp/c3_srv_ver.err
srv_rc=$?
"$CLI" --version >/tmp/c3_cli_ver.out 2>/tmp/c3_cli_ver.err
cli_rc=$?
set -o pipefail
[ "$srv_rc" -eq 0 ] || fail
[ "$cli_rc" -eq 0 ] || fail
grep -q 'jemalloc' /tmp/c3_srv_ver.out || fail

# TLS builtin artifact.
tls_rc=1
if [ -x /results/redis-server-tls ]; then
  set +o pipefail
  /results/redis-server-tls --version >/tmp/c3_tls_ver.out 2>/tmp/c3_tls_ver.err
  tls_rc=$?
  set -o pipefail
  [ "$tls_rc" -eq 0 ] || fail
  grep -a -q 'libssl' /results/redis-server-tls || fail
else
  fail
fi

# TLS module artifact: non-empty ELF shared object.
mag=""
etype=""
if [ -s /results/redis-tls.so ]; then
  mag="$(od -An -tx1 -N 4 /results/redis-tls.so | tr -d ' \n')"
  etype="$(od -An -tu2 -j 16 -N 2 /results/redis-tls.so | tr -d ' ')"
  [ "$mag" = "7f454c46" ] || fail
  [ "$etype" = "3" ] || fail
else
  fail
fi

# Independent 0/1 outcomes.
default_has_flto=0
printf '%s\n' "$default_cc" | grep -q -- '-flto' && default_has_flto=1
o3_has_flto=0
printf '%s\n' "$o3_cc" | grep -q -- '-flto' && o3_has_flto=1
tls_builtin=0
if [ "$tls_rc" -eq 0 ] && [ -f /results/redis-server-tls ] && grep -a -q 'libssl' /results/redis-server-tls; then
  tls_builtin=1
fi
tls_module=0
if [ -s /results/redis-tls.so ] && [ "$mag" = "7f454c46" ] && [ "$etype" = "3" ]; then
  tls_module=1
fi

[ "$default_has_flto" = "0" ] || fail
[ "$o3_has_flto" = "1" ] || fail
[ "$tls_builtin" = "1" ] || fail
[ "$tls_module" = "1" ] || fail

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
  [ "$line1" = "DEFAULT_OPTIMIZATION=-O2" ] || fail
  [ "$line2" = "DEFAULT_HAS_FLTO=${default_has_flto}" ] || fail
  [ "$line3" = "DEFAULT_MALLOC=jemalloc" ] || fail
  [ "$line4" = "TLS_BUILTIN_HAS_OPENSSL=${tls_builtin}" ] || fail
  [ "$line5" = "TLS_MODULE_EXISTS=${tls_module}" ] || fail
  [ "$line6" = "O3_HAS_FLTO=${o3_has_flto}" ] || fail
  od -An -tx1 "$ENVF" | grep -Eq ' [89a-f][0-9a-f]' && fail
else
  fail
fi

if [ "$FAILS" -eq 0 ]; then
  PASS=1
  exit 0
fi
exit 1
