FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    CC=gcc-14 \
    CXX=g++-14

# git + CA certs only: clone the pinned tree before provisioning.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates=20240203 \
        git=1:2.43.0-1ubuntu7.3 \
    && rm -rf /var/lib/apt/lists/*

# Obtain source at the exact target_spec commit. Do not COPY the input tree.
RUN git clone --filter=blob:none https://github.com/ggml-org/llama.cpp /src \
    && git -C /src checkout --detach b29c606e28a01b1bc8c1351026a0fa6e616bf6c4 \
    && test "$(git -C /src rev-parse HEAD)" = "b29c606e28a01b1bc8c1351026a0fa6e616bf6c4"

COPY setup.sh setup-overlay.sh smoke_test.sh /opt/env/
COPY assets/ /data/

RUN chmod 0755 /opt/env/setup.sh /opt/env/setup-overlay.sh /opt/env/smoke_test.sh \
    && bash /opt/env/setup.sh \
    && bash /opt/env/setup-overlay.sh

WORKDIR /app
