#!/bin/bash
# Build-time provisioning for the shared Redis Harbor base.
# Installs the repository toolchain, copies the pinned clone into the writable
# workdir, and creates data/results directories. Does not compile Redis.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends \
    build-essential=12.10ubuntu1 \
    gcc=4:13.2.0-7ubuntu1 \
    g++=4:13.2.0-7ubuntu1 \
    make=4.3-4.1build2 \
    pkg-config=1.8.1-2build1 \
    libssl-dev=3.0.13-0ubuntu3.15 \
    python3=3.12.3-0ubuntu2.1 \
    tcl8.6=8.6.14+dfsg-1build1 \
    tcl=8.6.14build1
rm -rf /var/lib/apt/lists/*

mkdir -p /app /data /results

# Writable workdir copy of the pinned source. /src stays the pristine clone.
if [ ! -f /app/Makefile ]; then
    cp -a /src/. /app/
fi
chmod -R u+w /app

chmod 0777 /data /results
