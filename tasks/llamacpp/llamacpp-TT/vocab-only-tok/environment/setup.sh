#!/bin/bash
# Build-time provisioning for the shared llama.cpp Harbor base.
# Idempotent, non-interactive, no runtime network.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"

apt-get update
apt-get install -y --no-install-recommends \
    binutils=2.42-4ubuntu2.10 \
    build-essential=12.10ubuntu1 \
    ca-certificates=20260601~24.04.1 \
    ccache=4.9.1-1 \
    cmake=3.28.3-1build7 \
    g++-14=14.2.0-4ubuntu2~24.04.1 \
    gcc-14=14.2.0-4ubuntu2~24.04.1 \
    git=1:2.43.0-1ubuntu7.3 \
    libgomp1=14.2.0-4ubuntu2~24.04.1 \
    libssl-dev=3.0.13-0ubuntu3.15 \
    make=4.3-4.1build2 \
    ninja-build=1.11.1-2 \
    pkg-config=1.8.1-2build1 \
    python3=3.12.3-0ubuntu2.1 \
    python3-dev=3.12.3-0ubuntu2.1 \
    python3-pip=24.0+dfsg-1ubuntu1.3 \
    python3-venv=3.12.3-0ubuntu2.1 \
    time=1.9-0.2build1

rm -rf /var/lib/apt/lists/*

if [ ! -e /usr/bin/gcc ] || [ "$(readlink -f /usr/bin/gcc 2>/dev/null || true)" = "/usr/bin/gcc-13" ]; then
    update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-14 140 \
        --slave /usr/bin/g++ g++ /usr/bin/g++-14 \
        --slave /usr/bin/gcov gcov /usr/bin/gcov-14 || true
fi

mkdir -p /app /data /results /opt/env

# Writable workdir is the cloned tree. Keep /src as a stable path to the same files.
if [ -d /src ] && [ ! -e /app/CMakeLists.txt ]; then
    if [ -d /app ] && [ -z "$(ls -A /app 2>/dev/null || true)" ]; then
        rmdir /app
    fi
    if [ ! -e /app ]; then
        mv /src /app
        ln -s /app /src
    else
        cp -a /src/. /app/
    fi
fi

chmod a+rwx /data /results
# Source tree must stay writable for repair / debugging / build tasks.
chmod -R a+rwX /app

git config --global --add safe.directory /app
git config --global --add safe.directory /src

# Shared fixture directory (overlays may add files here).
chmod a+rwx /data
