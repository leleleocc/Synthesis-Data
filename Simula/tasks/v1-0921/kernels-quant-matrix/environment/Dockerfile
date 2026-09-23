FROM nvidia/cuda:13.0.3-devel-ubuntu24.04@sha256:b7ae301dea2c162444795462ce17a05f6a516e5a75944b57af5b88540a1a2266

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    CUDA_HOME=/usr/local/cuda \
    PATH=/opt/venv/bin:/usr/local/cuda/bin:/root/.cargo/bin:${PATH} \
    VIRTUAL_ENV=/opt/venv \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    GIT_TERMINAL_PROMPT=0 \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

# Shared language and build toolchain for the whole batch (Python, C++, CUDA, CMake).
# Do not install pytest here; later phases bake the verifier runner.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        python3 \
        python3-dev \
        python3-venv \
        build-essential \
        cmake \
        ninja-build \
        pkg-config \
        libnuma-dev \
        numactl \
        libibverbs-dev \
        ffmpeg \
        libsm6 \
        libxext6 \
        libgl1 \
        libglib2.0-0 \
        sudo \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv \
    && pip install --no-cache-dir \
        pip==25.2 \
        setuptools==77.0.3 \
        wheel==0.45.1 \
        packaging==24.2 \
        ninja==1.11.1.4 \
        cmake==3.31.6 \
        jinja2==3.1.6 \
        setuptools-scm==8.2.1 \
        setuptools-rust==1.11.1

WORKDIR /workspace

# Pin vLLM at the target commit. Later slots copy this tree and may edit sources.
RUN git clone --filter=blob:none --no-checkout https://github.com/vllm-project/vllm.git /workspace/repo \
    && git -C /workspace/repo fetch --depth 1 origin 98dff2a81d747d1dba01a47f939f48c3526d4206 \
    && git -C /workspace/repo checkout --detach 98dff2a81d747d1dba01a47f939f48c3526d4206 \
    && git -C /workspace/repo rev-parse HEAD \
    && test "$(git -C /workspace/repo rev-parse HEAD)" = "98dff2a81d747d1dba01a47f939f48c3526d4206"

# Batch-shared GPU runtime: CUDA 13.0 PyTorch matching vLLM 2.13.0, then the
# Python package without compiling CUDA/Rust extensions so the image stays a
# generic base. Later slots can rebuild kernels against this toolchain.
WORKDIR /workspace/repo
RUN pip install --no-cache-dir \
        torch==2.13.0 \
        torchvision==0.28.0 \
        torchaudio==2.11.0 \
        --index-url https://download.pytorch.org/whl/cu130 \
    && VLLM_TARGET_DEVICE=empty \
       VLLM_REQUIRE_RUST_FRONTEND=0 \
       pip install --no-cache-dir --no-build-isolation -e . \
    && install -m 0755 \
        /workspace/repo/docker/entrypoints/vllm-nonroot-entrypoint.sh \
        /usr/local/bin/vllm-nonroot-entrypoint.sh \
    && ln -sf /usr/local/bin/vllm-nonroot-entrypoint.sh /usr/local/bin/vllm-nonroot-entrypoint \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -y --default-toolchain 1.95.0 --profile minimal

WORKDIR /workspace

# Ampere-only gencode pin shared by the launcher, cmake, and nvcc. Hopper 9.0
# and 9.0a stay off this list so a one-axis restore cannot light both cells.
ENV TORCH_CUDA_ARCH_LIST="8.0;8.6" \
    CMAKE_CUDA_ARCHITECTURES="80;86"

COPY overlays/cuda_arch_pins.cmake /workspace/cuda_arch_pins.cmake
COPY overlays/cuda_arch_pins.cmake /workspace/repo/cmake/cuda_arch_pins.cmake
COPY overlays/vllm-nonroot-entrypoint.sh /usr/local/bin/vllm-nonroot-entrypoint.sh

RUN chmod 0755 /usr/local/bin/vllm-nonroot-entrypoint.sh \
    && ln -sf /usr/local/bin/vllm-nonroot-entrypoint.sh /usr/local/bin/vllm-nonroot-entrypoint \
    && python3 - <<'PY'
from pathlib import Path

p = Path("/workspace/repo/CMakeLists.txt")
src = p.read_text()

old_supported = '  set(CUDA_SUPPORTED_ARCHS "7.5;8.0;8.6;8.7;8.9;9.0;10.0;11.0;12.0")'
new_supported = '  set(CUDA_SUPPORTED_ARCHS "7.5;8.0;8.6;8.7;8.9;10.0;11.0;12.0")'
if old_supported not in src:
    raise SystemExit("cuda supported arch overlay target missing")
src = src.replace(old_supported, new_supported, 1)

old_filter = '''  message(STATUS "CUDA supported target architectures: ${CUDA_ARCHS}")
  if(NOT CUDA_ARCHS)
'''
new_filter = '''  message(STATUS "CUDA supported target architectures: ${CUDA_ARCHS}")
  include(${CMAKE_CURRENT_LIST_DIR}/cmake/cuda_arch_pins.cmake)
  if(NOT CUDA_ARCHS)
'''
if old_filter not in src:
    raise SystemExit("cuda arch pin include target missing")
src = src.replace(old_filter, new_filter, 1)

old_scaled = '  cuda_archs_loose_intersection(SCALED_MM_ARCHS "9.0a;" "${CUDA_ARCHS}")'
new_scaled = '  cuda_archs_loose_intersection(SCALED_MM_ARCHS "9.0a-disabled;" "${CUDA_ARCHS}")'
if old_scaled not in src:
    raise SystemExit("scaled_mm 9.0a overlay target missing")
src = src.replace(old_scaled, new_scaled, 1)

old_srcs = '''    set(SCALED_MM_SM90_SRCS
       "csrc/libtorch_stable/quantization/w8a8/cutlass/scaled_mm_c3x_sm90.cu"
       "csrc/libtorch_stable/quantization/w8a8/cutlass/c3x/scaled_mm_sm90_fp8.cu"
       "csrc/libtorch_stable/quantization/w8a8/cutlass/c3x/scaled_mm_sm90_int8.cu"
       "csrc/libtorch_stable/quantization/w8a8/cutlass/c3x/scaled_mm_azp_sm90_int8.cu"
       "csrc/libtorch_stable/quantization/w8a8/cutlass/c3x/scaled_mm_blockwise_sm90_fp8.cu")
'''
new_srcs = '''    set(SCALED_MM_SM90_SRCS
       "csrc/libtorch_stable/quantization/w8a8/cutlass/scaled_mm_c3x_sm90.cu"
       "csrc/libtorch_stable/quantization/w8a8/cutlass/c3x/scaled_mm_sm90_int8.cu"
       "csrc/libtorch_stable/quantization/w8a8/cutlass/c3x/scaled_mm_azp_sm90_int8.cu")
'''
if old_srcs not in src:
    raise SystemExit("fp8 scaled_mm source overlay target missing")
src = src.replace(old_srcs, new_srcs, 1)

p.write_text(src)
PY

# Inline verifier runner pins.
RUN pip install --no-cache-dir pytest==9.1.1 pytest-json-ctrf==0.5.2
