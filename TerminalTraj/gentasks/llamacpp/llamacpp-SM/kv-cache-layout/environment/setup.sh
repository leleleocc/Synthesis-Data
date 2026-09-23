#!/usr/bin/env bash
# Build-time provisioning for the shared llama.cpp Harbor base.
# Idempotent, non-interactive. No network is required at container runtime.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends \
    build-essential=12.10ubuntu1 \
    gcc-14=14.2.0-4ubuntu2~24.04.1 \
    g++-14=14.2.0-4ubuntu2~24.04.1 \
    cmake=3.28.3-1build7 \
    ninja-build=1.11.1-2 \
    pkg-config=1.8.1-2build1 \
    libssl-dev=3.0.13-0ubuntu3.15 \
    libcurl4-openssl-dev=8.5.0-2ubuntu10.13 \
    zlib1g-dev=1:1.3.dfsg-3.1ubuntu2.2 \
    python3=3.12.3-0ubuntu2.1 \
    python3-minimal=3.12.3-0ubuntu2.1 \
    ca-certificates=20240203 \
    git=1:2.43.0-1ubuntu7.3

# Prefer the repo's gcc-14/g++-14 toolchain (matches .devops/cpu.Dockerfile).
update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-14 140 \
    --slave /usr/bin/g++ g++ /usr/bin/g++-14 \
    --slave /usr/bin/gcov gcov /usr/bin/gcov-14
update-alternatives --set gcc /usr/bin/gcc-14 || true

mkdir -p /app /data /results

# Writable workdir with the pinned source. Do not configure or compile here:
# build/cmake/repair/debugging tasks need an unbuilt tree.
if [ ! -f /app/CMakeLists.txt ]; then
    if [ ! -d /src ]; then
        echo "setup.sh: expected cloned source at /src" >&2
        exit 1
    fi
    cp -a /src/. /app/
fi

chmod a+rwx /app /data /results
# Keep source files as copied; only the directory itself needs to be writable.

# Drop apt indexes so the image does not require network at runtime.
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Record the pin for later overlays without specializing the tree.
printf '%s\n' "b29c606e28a01b1bc8c1351026a0fa6e616bf6c4" > /opt/env/PINNED_COMMIT
