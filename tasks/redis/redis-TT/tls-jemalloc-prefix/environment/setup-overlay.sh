#!/bin/bash
# Keep python3 on PATH for PREFIX/TLS/jemalloc build-report checks.
set -euo pipefail
command -v python3 >/dev/null
mkdir -p /results /opt/redis72
exit 0
