#!/bin/bash
set -uo pipefail

# FIXED: Harbor executes tests/test.sh directly, so keep this file executable.
# FIXED: the anchor task lives at /workspace; Reward Kit's workspace must match it.
rewardkit /tests --workspace /workspace
