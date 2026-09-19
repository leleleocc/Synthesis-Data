#!/usr/bin/env bash
set -uo pipefail

mkdir -p /logs/verifier
printf '%s\n' '{"reward": 0.0}' > /logs/verifier/reward.json

python3 /tests/verify.py
