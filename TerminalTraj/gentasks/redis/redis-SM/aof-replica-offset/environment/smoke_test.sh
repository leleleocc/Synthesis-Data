#!/bin/bash
# Shared-base smoke: declared dirs are writable and at least one entrypoint runs.
# Must not modify repository source files.
set -euo pipefail

test -d /app
test -w /app
test -d /data
test -w /data
test -d /results
test -w /results

tmp_data="$(mktemp /data/smoke.XXXXXX)"
tmp_results="$(mktemp /results/smoke.XXXXXX)"
echo ok > "${tmp_data}"
echo ok > "${tmp_results}"
rm -f "${tmp_data}" "${tmp_results}"

test -f /app/Makefile
test -x /app/src/redis-server
test -x /app/src/redis-cli

/app/src/redis-server --version
/app/src/redis-cli --version
make -C /app -n all >/dev/null
