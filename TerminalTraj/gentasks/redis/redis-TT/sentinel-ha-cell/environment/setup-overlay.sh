#!/bin/bash
# Keep python3 on PATH for Sentinel inventory JSON checks.
set -euo pipefail
command -v python3 >/dev/null
mkdir -p /results
exit 0
