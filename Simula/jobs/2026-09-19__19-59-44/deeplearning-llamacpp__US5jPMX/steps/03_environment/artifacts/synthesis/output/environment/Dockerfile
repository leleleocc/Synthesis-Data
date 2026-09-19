# Harbor shared base for llama.cpp (ggml-org/llama.cpp).
# Platform image: toolchain + pinned source. No planted defects or task fixtures.
FROM docker.io/ubuntu:24.04@sha256:008173c23f95b170204355c12626cb5a965d779a7e1283b09e9cffbb1bf33ca3

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# Copy env provisioning scripts first (thin Dockerfile; logic in setup.sh).
COPY setup.sh setup-overlay.sh smoke_test.sh /opt/env/
COPY assets/ /data/

RUN chmod +x /opt/env/setup.sh /opt/env/setup-overlay.sh /opt/env/smoke_test.sh \
    && bash /opt/env/setup.sh \
    && bash /opt/env/setup-overlay.sh

WORKDIR /app

# Default command keeps the container useful for interactive/agent use.
CMD ["bash"]
