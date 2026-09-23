#!/usr/bin/env bash
# Build-time provisioning for the shared Redis Harbor base.
# Idempotent, non-interactive. No network is required at container runtime.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

WORKDIR="${WORKDIR:-/app}"
DATA_DIR="${DATA_DIR:-/data}"
RESULTS_DIR="${RESULTS_DIR:-/results}"
SRC_DIR="${SRC_DIR:-/src}"

apt-get update
apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libssl-dev \
    tcl8.6 \
    tclx \
    time \
    procps
rm -rf /var/lib/apt/lists/*

mkdir -p "${WORKDIR}" "${DATA_DIR}" "${RESULTS_DIR}" /opt/env

# Writable working copy of the pinned source. Leave /src as the clone reference.
if [ -d "${SRC_DIR}" ]; then
    cp -a "${SRC_DIR}/." "${WORKDIR}/"
fi

# Agent-writable roots; do not pre-build Redis (build-system tasks own `make`).
chmod -R a+rwX "${WORKDIR}" "${DATA_DIR}" "${RESULTS_DIR}"

# Confirm the C toolchain is present without compiling the repository.
command -v gcc >/dev/null
command -v make >/dev/null
command -v pkg-config >/dev/null
test -f "${WORKDIR}/Makefile"
test -f "${WORKDIR}/src/Makefile"
test -f "${WORKDIR}/redis.conf"
test -f "${WORKDIR}/runtest"
