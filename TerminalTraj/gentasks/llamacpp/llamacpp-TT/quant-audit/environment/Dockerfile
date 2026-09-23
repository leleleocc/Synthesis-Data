FROM ubuntu:24.04@sha256:b3cc40b72b93588182b5410f723c7aaf142363311c2aa993d8a453ddcbb3ae15

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    CC=gcc-14 \
    CXX=g++-14 \
    GIT_TERMINAL_PROMPT=0

# git + CA certs are required in the Dockerfile so the pinned clone can run
# before setup.sh. Remaining toolchain install lives in setup.sh.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates=20260601~24.04.1 \
        git=1:2.43.0-1ubuntu7.3 \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/ggml-org/llama.cpp /src \
    && git -C /src checkout b29c606e28a01b1bc8c1351026a0fa6e616bf6c4

COPY setup.sh setup-overlay.sh smoke_test.sh /opt/env/
RUN chmod 0755 /opt/env/setup.sh /opt/env/setup-overlay.sh /opt/env/smoke_test.sh \
    && bash /opt/env/setup.sh \
    && bash /opt/env/setup-overlay.sh

WORKDIR /app
