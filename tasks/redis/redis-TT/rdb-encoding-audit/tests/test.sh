#!/bin/bash
set -uo pipefail

mkdir -p /logs/verifier
PASS=0
trap 'if [ "$PASS" -eq 1 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi' EXIT

python3 /tests/check_encodings.py
status=$?
if [ "$status" -eq 0 ]; then
  PASS=1
fi
exit "$status"
