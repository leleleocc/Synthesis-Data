#!/bin/bash
set -uo pipefail

mkdir -p /logs/verifier

python3 /tests/check.py
status=$?

if [ "$status" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
  exit 0
else
  echo 0 > /logs/verifier/reward.txt
  exit 1
fi
