#!/bin/bash
set -uo pipefail

mkdir -p /logs/verifier /tmp/ctrf
echo 0 > /logs/verifier/reward.txt
chmod 700 /logs/verifier
chmod 1777 /tmp/ctrf

export PYTHONPATH="/workspace/repo${PYTHONPATH:+:$PYTHONPATH}"
export PATH="/opt/venv/bin:${PATH}"
export HOME=/tmp
export XDG_CACHE_HOME=/tmp
export TMPDIR=/tmp

set +e
setpriv --reuid nobody --regid nogroup --clear-groups --no-new-privs \
  python3 -m pytest --ctrf /tmp/ctrf/ctrf.json /tests/test_reset.py -rA
status=$?
set -e

if [[ -f /tmp/ctrf/ctrf.json ]]; then
  cp /tmp/ctrf/ctrf.json /logs/verifier/ctrf.json
fi

if [[ $status -ne 0 ]]; then
  echo "cache reset invariant: fail"
  echo "reason: live reset_prefix_cache did not refuse in-flight holders or left hashed blocks after a true reset"
  echo 0 > /logs/verifier/reward.txt
  exit 0
fi

echo 1 > /logs/verifier/reward.txt
