#!/bin/bash
set -uo pipefail

mkdir -p /logs/verifier
REWARD_WRITTEN=0

write_reward() {
  echo "$1" > /logs/verifier/reward.txt
  REWARD_WRITTEN=1
}

trap 'if [ "${REWARD_WRITTEN:-0}" -eq 0 ]; then echo 0 > /logs/verifier/reward.txt; fi' EXIT

STATUS=1
python3 /tests/check_aof.py
STATUS=$?

if [ "$STATUS" -eq 0 ]; then
  write_reward 1
  exit 0
fi
write_reward 0
exit 1
