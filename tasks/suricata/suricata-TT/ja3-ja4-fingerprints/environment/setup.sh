#!/usr/bin/env bash
# Build-time provisioning for the shared Suricata Harbor base.
# Installs the repository toolchain and task roots. Does not compile Suricata
# and does not plant task-specific configs, pcaps, or defects.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

WORKDIR="${WORKDIR:-/app}"
DATA_DIR="${DATA_DIR:-/data}"
RESULTS_DIR="${RESULTS_DIR:-/results}"

mkdir -p "${WORKDIR}" "${DATA_DIR}" "${RESULTS_DIR}" /opt/env

apt-get update
apt-get install -y --no-install-recommends \
    autoconf \
    automake \
    build-essential \
    ca-certificates \
    cargo \
    cbindgen \
    file \
    gettext \
    git \
    libcap-ng-dev \
    libevent-dev \
    libhiredis-dev \
    libhyperscan-dev \
    libjansson-dev \
    liblz4-dev \
    libmagic-dev \
    libmaxminddb-dev \
    libnet1-dev \
    libnetfilter-queue-dev \
    libnfnetlink-dev \
    libnuma-dev \
    libpcap-dev \
    libpcre2-dev \
    libtool \
    libyaml-dev \
    make \
    pkg-config \
    python-is-python3 \
    python3 \
    python3-dev \
    python3-yaml \
    rustc \
    tcpdump \
    zlib1g-dev
rm -rf /var/lib/apt/lists/*

# Writable task roots for repair/build/configuration overlays. Source stays
# unmodified beyond directory permissions.
chmod 0777 "${DATA_DIR}" "${RESULTS_DIR}"
if [ -d "${WORKDIR}" ]; then
    chmod u+w "${WORKDIR}" || true
fi

if command -v git >/dev/null 2>&1 && [ -d "${WORKDIR}/.git" ]; then
    git config --global --add safe.directory "${WORKDIR}" || true
fi

# Record pinned toolchain versions for later overlays (informational only).
mkdir -p "${DATA_DIR}/toolchain"
{
    echo "base=ubuntu:24.04"
    gcc --version | head -n 1
    rustc --version
    cargo --version
    python3 --version
    cbindgen --version 2>/dev/null || true
} > "${DATA_DIR}/toolchain/versions.txt" || true

exit 0
