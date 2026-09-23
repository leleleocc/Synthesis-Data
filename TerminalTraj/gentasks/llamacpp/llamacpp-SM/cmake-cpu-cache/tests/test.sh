#!/bin/bash
set -uo pipefail

mkdir -p /logs/verifier

PASS=0
python3 /tests/check.py
if [ "${?}" -eq 0 ]; then
  PASS=1
fi

if [ "${PASS}" -eq 1 ]; then
  echo 1 > /logs/verifier/reward.txt
  exit 0
fi
echo 0 > /logs/verifier/reward.txt
exit 1
