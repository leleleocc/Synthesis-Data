#!/bin/bash
set -uo pipefail

mkdir -p /logs/verifier

PASS=1
python3 /tests/verify.py
if [ $? -ne 0 ]; then
  PASS=0
fi

if [ "$PASS" -eq 1 ]; then
  echo 1 > /logs/verifier/reward.txt
  exit 0
fi
echo 0 > /logs/verifier/reward.txt
exit 1
