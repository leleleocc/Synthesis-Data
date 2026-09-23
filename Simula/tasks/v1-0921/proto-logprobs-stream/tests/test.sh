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
  python3 -m pytest --ctrf /tmp/ctrf/ctrf.json /tests/test_protocol.py -rA
status=$?
set -e

if [[ -f /tmp/ctrf/ctrf.json ]]; then
  cp /tmp/ctrf/ctrf.json /logs/verifier/ctrf.json
fi

if [[ $status -ne 0 ]]; then
  echo "protocol decode: fail"
  echo "reason: illegal chat-completion bodies were accepted or legal echo/stop mapping did not hold"
  echo 0 > /logs/verifier/reward.txt
  exit 0
fi

echo "normal case: pass"
echo "edge case: pass"
echo "error handling: pass"
echo "state check: pass"
echo 1 > /logs/verifier/reward.txt
