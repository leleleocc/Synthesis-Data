#!/bin/bash
# Build-time provisioning for the shared Redis Harbor base.
# Idempotent and non-interactive. No network is required at container runtime.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

# Repository toolchain: C compiler, Make, TLS headers (optional BUILD_TLS),
# and Tcl for the in-tree runtest harness. Do not install Harbor verifier
# stacks (pytest, jq, ...). Phase 05 overlays add observation tools.
apt-get update
apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libssl-dev \
    tcl \
    procps
rm -rf /var/lib/apt/lists/*

mkdir -p /app /data /results /opt/env
chmod 0777 /app /data /results

# Writable working copy of the pinned clone. /src stays the pristine checkout.
if [ -d /src ] && [ ! -f /app/Makefile ]; then
    cp -a /src/. /app/
fi

# Working baseline binaries so cli / configuration / performance tasks have
# redis-server and redis-cli. Source remains writable; agents can distclean
# and rebuild for build-system tasks. Do not plant configs or defects here.
if [ -f /app/Makefile ] && [ ! -x /app/src/redis-server ]; then
    make -C /app -j"$(nproc)"
fi

chmod 0777 /app /data /results
