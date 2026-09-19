#!/usr/bin/env bash
# Confirm python3 for structured JSON oracles. No extra packages.
set -euo pipefail
command -v python3 >/dev/null
exit 0
