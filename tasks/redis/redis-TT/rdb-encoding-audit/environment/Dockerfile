FROM ubuntu:24.04@sha256:b3cc40b72b93588182b5410f723c7aaf142363311c2aa993d8a453ddcbb3ae15

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# git + CA certs are required before the pinned clone; remaining toolchain is in setup.sh.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git=1:2.43.0-1ubuntu7.3 \
        ca-certificates=20260601~24.04.1 \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/redis/redis /src \
    && git -C /src fetch origin 335554f18caf7bbf6b0ac2b3548133d750f00a1b \
    && git -C /src checkout 335554f18caf7bbf6b0ac2b3548133d750f00a1b

COPY setup.sh setup-overlay.sh smoke_test.sh /opt/env/

RUN bash /opt/env/setup.sh
RUN bash /opt/env/setup-overlay.sh

WORKDIR /app
