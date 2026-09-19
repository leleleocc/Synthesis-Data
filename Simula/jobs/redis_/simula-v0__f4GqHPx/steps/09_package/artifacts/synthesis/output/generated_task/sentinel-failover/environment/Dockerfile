FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# git + CA certs are required to clone the pinned source at build time.
# Remaining toolchain and Redis provisioning live in setup.sh.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/*

# Shared base obtains Redis at the exact target_spec commit. Later phases
# may overlay this tree; they must not COPY the synthesis input checkout.
RUN git clone https://github.com/redis/redis /src \
    && git -C /src checkout 335554f18caf7bbf6b0ac2b3548133d750f00a1b

COPY setup.sh setup-overlay.sh smoke_test.sh /opt/env/

RUN bash /opt/env/setup.sh
RUN bash /opt/env/setup-overlay.sh

WORKDIR /app
