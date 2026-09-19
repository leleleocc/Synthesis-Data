#!/usr/bin/env bash
# Build-time provisioning for the llama.cpp Harbor shared base.
# Idempotent, non-interactive. Network used only during image build.
set -euo pipefail

WORKDIR="${WORKDIR:-/app}"
DATA_DIR="${DATA_DIR:-/data}"
RESULTS_DIR="${RESULTS_DIR:-/results}"
SRC_URL="https://github.com/ggml-org/llama.cpp"
SRC_COMMIT="b29c606e28a01b1bc8c1351026a0fa6e616bf6c4"

echo "[setup] creating directories"
mkdir -p "${WORKDIR}" "${DATA_DIR}" "${RESULTS_DIR}" /opt/env /usr/local/bin
chmod 777 "${DATA_DIR}" "${RESULTS_DIR}"

echo "[setup] installing system packages (pinned)"
apt-get update
apt-get install -y --no-install-recommends \
    ca-certificates=20240203 \
    curl=8.5.0-2ubuntu10.6 \
    wget=1.21.4-1ubuntu4.1 \
    git=1:2.43.0-1ubuntu7.3 \
    build-essential=12.10ubuntu1 \
    gcc=4:13.2.0-7ubuntu1 \
    g++=4:13.2.0-7ubuntu1 \
    gcc-14=14.2.0-4ubuntu2~24.04 \
    g++-14=14.2.0-4ubuntu2~24.04 \
    cmake=3.28.3-1build7 \
    ninja-build=1.11.1-2 \
    ccache=4.9.1-1 \
    pkg-config=1.8.1-2build1 \
    libssl-dev=3.0.13-0ubuntu3.6 \
    libcurl4-openssl-dev=8.5.0-2ubuntu10.6 \
    libgomp1=14.2.0-4ubuntu2~24.04 \
    python3=3.12.3-0ubuntu2.1 \
    python3-pip=24.0+dfsg-1ubuntu1.3 \
    python3-venv=3.12.3-0ubuntu2.1 \
    python3-dev=3.12.3-0ubuntu2.1 \
    python-is-python3=3.11.4-1 \
    make=4.3-4.1build2 \
    xxd=2:9.1.0016-1ubuntu7.9 \
    unzip=6.0-28ubuntu4.1 \
    tar=1.35+dfsg-3build1 \
    xz-utils=5.6.1+really5.4.5-1ubuntu0.2 \
    file=1:5.45-3build1 \
    parallel=20231122+ds-1 \
    time=1.9-0.2build1 \
    procps=2:4.0.4-4ubuntu3.2 \
    vim-tiny=2:9.1.0016-1ubuntu7.9 \
    nano=7.2-2ubuntu0.1 \
    jq=1.7.1-3ubuntu0.24.04.1 \
    || apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        wget \
        git \
        build-essential \
        gcc \
        g++ \
        gcc-14 \
        g++-14 \
        cmake \
        ninja-build \
        ccache \
        pkg-config \
        libssl-dev \
        libcurl4-openssl-dev \
        libgomp1 \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        python-is-python3 \
        make \
        xxd \
        unzip \
        tar \
        xz-utils \
        file \
        parallel \
        time \
        procps \
        vim-tiny \
        nano \
        jq

# Prefer gcc-14 when available (matches upstream .devops/cpu.Dockerfile).
if command -v gcc-14 >/dev/null 2>&1; then
  update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-14 140 \
    --slave /usr/bin/g++ g++ /usr/bin/g++-14 || true
  export CC=gcc-14
  export CXX=g++-14
fi

echo "[setup] cloning llama.cpp @ ${SRC_COMMIT}"
# Clone into a temp dir then move contents into WORKDIR so /app is the repo root.
rm -rf /tmp/llama.cpp-src
git clone --filter=blob:none --single-branch "${SRC_URL}" /tmp/llama.cpp-src
git -C /tmp/llama.cpp-src checkout --force "${SRC_COMMIT}"
git -C /tmp/llama.cpp-src rev-parse HEAD | grep -q "^${SRC_COMMIT}"
# Populate workdir with source (writable for repair/debug/build tasks).
rsync -a --delete /tmp/llama.cpp-src/ "${WORKDIR}/" 2>/dev/null \
  || (rm -rf "${WORKDIR:?}/"* "${WORKDIR}/".[!.]* "${WORKDIR}/"..?* 2>/dev/null || true; \
      cp -a /tmp/llama.cpp-src/. "${WORKDIR}/")
rm -rf /tmp/llama.cpp-src
# Ensure .git remains so agents can inspect commit / diff.
test -d "${WORKDIR}/.git"
test -f "${WORKDIR}/CMakeLists.txt"
ACTUAL_COMMIT="$(git -C "${WORKDIR}" rev-parse HEAD)"
test "${ACTUAL_COMMIT}" = "${SRC_COMMIT}"

echo "[setup] python venv + pinned language deps"
python3 -m venv /opt/venv
# shellcheck disable=SC1091
source /opt/venv/bin/activate
pip install --upgrade pip==25.0.1 setuptools==75.8.0 wheel==0.45.1
# Core scientific stack used by convert_*.py and gguf-py (pins from gguf-py + common).
pip install \
    "numpy==2.2.6" \
    "tqdm==4.67.1" \
    "pyyaml==6.0.2" \
    "requests==2.32.3" \
    "sentencepiece==0.2.0" \
    "protobuf==5.29.3" \
    "safetensors==0.5.2" \
    "gguf==0.19.0"
# Editable install of in-tree gguf-py so scripts resolve local package.
if [[ -f "${WORKDIR}/gguf-py/pyproject.toml" ]]; then
  pip install -e "${WORKDIR}/gguf-py"
fi
deactivate

# Put venv on default PATH for subsequent layers and runtime.
ln -sfn /opt/venv/bin/python3 /usr/local/bin/python3-venv
cat >/etc/profile.d/llama-env.sh <<'EOF'
export PATH="/opt/venv/bin:${PATH}"
export CC="${CC:-gcc-14}"
export CXX="${CXX:-g++-14}"
export CMAKE_BUILD_PARALLEL_LEVEL="${CMAKE_BUILD_PARALLEL_LEVEL:-$(nproc)}"
export WORKDIR=/app
export DATA_DIR=/data
export RESULTS_DIR=/results
EOF
chmod 644 /etc/profile.d/llama-env.sh

# Non-login shells (Harbor exec) also see the venv.
echo 'export PATH="/opt/venv/bin:$PATH"' >/etc/environment.d/99-llama-path.conf 2>/dev/null || true
export PATH="/opt/venv/bin:${PATH}"

echo "[setup] baseline CPU Release build (shared working binary set)"
# Provide a working baseline for cli/serving/benchmark tags. Build-system tasks
# may reconfigure or clean; source and toolchain remain available.
cd "${WORKDIR}"
# shellcheck disable=SC1091
source /etc/profile.d/llama-env.sh || true
export PATH="/opt/venv/bin:${PATH}"
export CC="${CC:-gcc-14}"
export CXX="${CXX:-g++-14}"

cmake -S . -B build \
  -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_NATIVE=OFF \
  -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_EXAMPLES=ON \
  -DLLAMA_BUILD_TOOLS=ON \
  -DLLAMA_BUILD_SERVER=ON \
  -DBUILD_SHARED_LIBS=OFF

cmake --build build --config Release --parallel "$(nproc)"

# Expose common binaries on PATH without requiring build/bin prefix.
if [[ -d "${WORKDIR}/build/bin" ]]; then
  for b in "${WORKDIR}/build/bin/"*; do
    [[ -x "${b}" && -f "${b}" ]] || continue
    base="$(basename "${b}")"
    ln -sfn "${b}" "/usr/local/bin/${base}"
  done
fi

echo "[setup] helper wrappers"
cat >/usr/local/bin/llama-workdir <<EOF
#!/usr/bin/env bash
cd "${WORKDIR}" && exec "\$@"
EOF
chmod +x /usr/local/bin/llama-workdir

# Record provenance for smoke / later overlays.
cat >"${DATA_DIR}/ENV_PROVENANCE.txt" <<EOF
source_repo=${SRC_URL}
source_commit=${SRC_COMMIT}
workdir=${WORKDIR}
data_dir=${DATA_DIR}
results_dir=${RESULTS_DIR}
build_type=Release
backend=cpu
EOF
chmod 644 "${DATA_DIR}/ENV_PROVENANCE.txt"

# Shared empty placeholder so /data is non-empty and mounts behave predictably.
mkdir -p "${DATA_DIR}/models" "${DATA_DIR}/fixtures" "${RESULTS_DIR}/runs"
chmod -R a+rwX "${DATA_DIR}" "${RESULTS_DIR}"

echo "[setup] cleanup apt lists to shrink image"
apt-get clean
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

echo "[setup] done"
