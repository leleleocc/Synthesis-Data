#!/usr/bin/env bash
set -u
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

here="$(cd "$(dirname "$0")" && pwd)"
cd "$here" || {
  echo "normal case: fail reason: cannot enter tests dir"
  echo 0 > /logs/verifier/reward.txt
  exit 0
}

if python3 -m pytest -s -q --tb=line --ctrf /logs/verifier/ctrf.json test_kernel_parity.py; then
  echo "state check: pass"
  echo 1 > /logs/verifier/reward.txt
else
  echo "state check: fail reason: parity table or restored kernel sources disagree"
  echo 0 > /logs/verifier/reward.txt
fi
exit 0
