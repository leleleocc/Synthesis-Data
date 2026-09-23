# Harbor shared base for Suricata (OISF/suricata).
# Platform image: toolchain + pinned source. No planted defects or task fixtures.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    CARGO_HOME=/opt/cargo \
    RUSTUP_HOME=/opt/rustup \
    PATH=/opt/cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    WORKDIR_PATH=/app \
    DATA_DIR=/data \
    RESULTS_DIR=/results

# Minimal bootstrap so setup.sh can run and git-clone the pinned commit.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        bash \
    && rm -rf /var/lib/apt/lists/*

COPY setup.sh setup-overlay.sh smoke_test.sh /opt/env/
COPY assets/ /data/

# Pin source at the exact synthesis commit (build-time network only).
ARG SURICATA_REPO=https://github.com/OISF/suricata
ARG SURICATA_COMMIT=d681600f3648030a67f7d618d30742bfd5fe7169
RUN git clone --filter=blob:none "${SURICATA_REPO}" /app \
    && git -C /app checkout --detach "${SURICATA_COMMIT}" \
    && git -C /app submodule update --init --recursive || true \
    && test "$(git -C /app rev-parse HEAD)" = "${SURICATA_COMMIT}"

RUN bash /opt/env/setup.sh
RUN bash /opt/env/setup-overlay.sh

WORKDIR /app
