#!/usr/bin/env bash
# Candidate overlay: python3 stdlib for structured JSON checks.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

apt-get update
apt-get install -y --no-install-recommends python3
rm -rf /var/lib/apt/lists/*

command -v python3 >/dev/null
python3 -c 'import json, sys; sys.exit(0)'
