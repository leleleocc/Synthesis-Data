#!/usr/bin/env bash
# Build-time provisioning for the shared Redis Harbor base.
# Idempotent, non-interactive. Network is used only during image build.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"

apt-get update
apt-get install -y --no-install-recommends \
    build-essential=12.10ubuntu1 \
    gcc=4:13.2.0-7ubuntu1 \
    g++=4:13.2.0-7ubuntu1 \
    make=4.3-4.1build2 \
    pkg-config=1.8.1-2build1 \
    libssl-dev=3.0.13-0ubuntu3.15 \
    tcl=8.6.14build1 \
    tcl8.6=8.6.14+dfsg-1build1 \
    tclx8.4=8.4.1-4 \
    procps=2:4.0.4-4ubuntu3.3 \
    python3=3.12.3-0ubuntu2.1 \
    time=1.9-0.2build1 \
    binutils=2.42-4ubuntu2.10 \
    libc6-dev=2.39-0ubuntu8.9
rm -rf /var/lib/apt/lists/*

mkdir -p /app /data /results

# Place the pinned clone in the writable workdir and drop the extra tree so
# later overlays cannot be compared against a second pristine copy.
if [[ -d /src ]]; then
    cp -a /src/. /app/
    rm -rf /src
fi

chmod a+rwx /app /data /results

# Keep the clone identity but allow the agent to edit the tree.
if [[ -d /app/.git ]]; then
    git -C /app config --local --add safe.directory /app || true
fi
