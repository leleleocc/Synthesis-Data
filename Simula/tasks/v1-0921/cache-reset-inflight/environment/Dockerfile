FROM nvidia/cuda:13.0.3-devel-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/usr/local/cuda/bin:${PATH} \
    PYTHONPATH=/workspace/repo \
    VLLM_TARGET_DEVICE=cuda \
    TORCH_CUDA_ARCH_LIST="7.5;8.0;8.9;9.0;10.0;12.0" \
    MAX_JOBS=4 \
    NVCC_THREADS=2

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        python3 \
        python3-dev \
        python3-pip \
        python3-venv \
        python3-setuptools \
        build-essential \
        cmake \
        ninja-build \
        pkg-config \
        libnuma-dev \
        wget \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv \
    && pip install --upgrade pip setuptools==77.0.3 wheel==0.48.0 \
    && pip install \
        numpy==2.2.6 \
        packaging==24.2 \
        setuptools-scm==8.2.0 \
        setuptools-rust==1.11.1 \
        torch==2.13.0 \
        pytest==9.1.1 \
        pytest-json-ctrf==0.5.2

# Pin the source at the target commit. Later slots copy this tree and add
# task-specific plants; do not compile CUDA kernels in the shared base.
RUN git clone --filter=blob:none --no-checkout https://github.com/vllm-project/vllm.git /workspace/repo \
    && git -C /workspace/repo fetch --depth 1 origin 98dff2a81d747d1dba01a47f939f48c3526d4206 \
    && git -C /workspace/repo checkout --detach 98dff2a81d747d1dba01a47f939f48c3526d4206

# Batch-shared Python runtime from the pin. Install the package after the
# plant so /opt/venv does not retain an unplanted vllm tree.
RUN pip install -r /workspace/repo/requirements/common.txt

COPY overlay/ /tmp/overlay/
RUN python3 /tmp/overlay/apply.py \
    && rm -rf /tmp/overlay \
    && VLLM_TARGET_DEVICE=empty VLLM_REQUIRE_RUST_FRONTEND=0 \
        pip install --no-build-isolation --no-deps /workspace/repo \
    && rm -rf /workspace/repo/.git

COPY smoke_test.sh /workspace/smoke_test.sh
RUN chmod +x /workspace/smoke_test.sh

WORKDIR /workspace
