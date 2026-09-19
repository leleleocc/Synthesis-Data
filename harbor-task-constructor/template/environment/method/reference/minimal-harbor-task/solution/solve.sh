#!/bin/bash
set -euo pipefail

# FIXED: Harbor's Oracle executes solution/solve.sh directly, so keep this file executable.
printf '%s\n' ready > /workspace/answer.txt
