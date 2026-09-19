#!/usr/bin/env bash
# Build-time provisioning for the shared Suricata Harbor base.
# Installs the repository toolchain and layout dirs. Does NOT compile Suricata
# (build/repair tasks need a clean tree + toolchain). Idempotent and non-interactive.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export CARGO_HOME="${CARGO_HOME:-/opt/cargo}"
export RUSTUP_HOME="${RUSTUP_HOME:-/opt/rustup}"
export PATH="${CARGO_HOME}/bin:${PATH}"

WORKDIR_PATH="${WORKDIR_PATH:-/app}"
DATA_DIR="${DATA_DIR:-/data}"
RESULTS_DIR="${RESULTS_DIR:-/results}"

# Pinned Rust toolchain (matches Suricata CI RUST_VERSION_KNOWN).
RUST_VERSION="1.98.0"
CBINDGEN_VERSION="0.27.0"

mkdir -p "${WORKDIR_PATH}" "${DATA_DIR}" "${RESULTS_DIR}" \
         /opt/env /var/log/suricata /var/run/suricata \
         "${CARGO_HOME}" "${RUSTUP_HOME}"

# ---------------------------------------------------------------------------
# System packages: autotools C build deps used by Suricata configure.ac / CI.
# Versions are whatever ubuntu:24.04 resolves; base image tag pins the set.
# ---------------------------------------------------------------------------
apt-get update
apt-get install -y --no-install-recommends \
    build-essential \
    autoconf \
    automake \
    autopoint \
    libtool \
    pkg-config \
    make \
    gcc \
    g++ \
    flex \
    bison \
    git \
    curl \
    ca-certificates \
    python3 \
    python3-yaml \
    python3-setuptools \
    zlib1g-dev \
    libpcre2-dev \
    libyaml-dev \
    libjansson-dev \
    libpcap-dev \
    libcap-ng-dev \
    libmagic-dev \
    libnet1-dev \
    liblz4-dev \
    libnspr4-dev \
    libnss3-dev \
    libevent-dev \
    libmaxminddb-dev \
    libhiredis-dev \
    libnetfilter-queue-dev \
    libnetfilter-log-dev \
    libnfnetlink-dev \
    libelf-dev \
    libbpf-dev \
    tcpdump \
    tshark \
    jq \
    file \
    xz-utils \
    unzip \
    procps \
    iproute2 \
    net-tools \
    vim-tiny \
    nano \
    strace \
    gdb \
    binutils \
    diffutils \
    patch \
    rsync \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Ensure cc/c++ are on PATH before building Rust crates (cbindgen).
command -v cc >/dev/null 2>&1 || ln -sfn "$(command -v gcc)" /usr/bin/cc
command -v gcc >/dev/null 2>&1 || { echo "ERROR: gcc missing after apt install" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Rust + cbindgen (required to configure/build Suricata's Rust components).
# ---------------------------------------------------------------------------
if ! command -v rustc >/dev/null 2>&1 || ! rustc --version 2>/dev/null | grep -q "${RUST_VERSION}"; then
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --default-toolchain "${RUST_VERSION}" --profile minimal
fi
# shellcheck disable=SC1091
source "${CARGO_HOME}/env" 2>/dev/null || true
export PATH="${CARGO_HOME}/bin:${PATH}"
rustup default "${RUST_VERSION}"
rustc --version
cargo --version

if ! command -v cbindgen >/dev/null 2>&1; then
  cargo install --locked cbindgen --version "${CBINDGEN_VERSION}"
fi
cbindgen --version

# Stable symlinks so entrypoints are predictable even if cargo path differs.
ln -sfn "$(command -v rustc)" /usr/local/bin/rustc
ln -sfn "$(command -v cargo)" /usr/local/bin/cargo
ln -sfn "$(command -v cbindgen)" /usr/local/bin/cbindgen
ln -sfn "$(command -v rustup)" /usr/local/bin/rustup || true

# ---------------------------------------------------------------------------
# Source tree sanity (cloned in Dockerfile). Keep writable for agent tasks.
# ---------------------------------------------------------------------------
if [[ ! -d "${WORKDIR_PATH}/.git" ]]; then
  echo "ERROR: ${WORKDIR_PATH} is missing the Suricata git checkout" >&2
  exit 1
fi
if [[ ! -f "${WORKDIR_PATH}/configure.ac" || ! -f "${WORKDIR_PATH}/autogen.sh" ]]; then
  echo "ERROR: Suricata source layout incomplete under ${WORKDIR_PATH}" >&2
  exit 1
fi
chmod -R a+rwX "${WORKDIR_PATH}" || true
# autogen.sh must be executable for agents and smoke.
chmod +x "${WORKDIR_PATH}/autogen.sh" || true

# Shared data layout: default rule/event snippets are already in the clone.
# Expose convenient read-only-ish copies under /data for configuration tasks
# without removing them from the writable workdir.
mkdir -p "${DATA_DIR}/rules" "${DATA_DIR}/etc" "${DATA_DIR}/pcaps"
if [[ -d "${WORKDIR_PATH}/rules" ]]; then
  # Copy a small shared subset of event rules as generic samples (not task goldens).
  for f in \
      dns-events.rules http-events.rules tls-events.rules \
      decoder-events.rules app-layer-events.rules files.rules
  do
    if [[ -f "${WORKDIR_PATH}/rules/${f}" ]]; then
      cp -a "${WORKDIR_PATH}/rules/${f}" "${DATA_DIR}/rules/${f}"
    fi
  done
fi
if [[ -f "${WORKDIR_PATH}/etc/classification.config" ]]; then
  cp -a "${WORKDIR_PATH}/etc/classification.config" "${DATA_DIR}/etc/"
fi
if [[ -f "${WORKDIR_PATH}/etc/reference.config" ]]; then
  cp -a "${WORKDIR_PATH}/etc/reference.config" "${DATA_DIR}/etc/"
fi
if [[ -f "${WORKDIR_PATH}/threshold.config" ]]; then
  cp -a "${WORKDIR_PATH}/threshold.config" "${DATA_DIR}/etc/"
fi
# suricata.yaml.in is the template; leave building suricata.yaml to configure/make.
if [[ -f "${WORKDIR_PATH}/suricata.yaml.in" ]]; then
  cp -a "${WORKDIR_PATH}/suricata.yaml.in" "${DATA_DIR}/etc/suricata.yaml.in"
fi

chmod -R a+rwX "${DATA_DIR}" "${RESULTS_DIR}"

# Record toolchain pins for agents/overlays.
cat > /opt/env/toolchain.txt <<EOF
rust=${RUST_VERSION}
cbindgen=${CBINDGEN_VERSION}
workdir=${WORKDIR_PATH}
data_dir=${DATA_DIR}
results_dir=${RESULTS_DIR}
source_commit=$(git -C "${WORKDIR_PATH}" rev-parse HEAD)
EOF

echo "setup.sh: Suricata shared base provisioned (source + toolchain, not prebuilt)."
