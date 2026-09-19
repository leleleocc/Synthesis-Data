FROM ubuntu:24.04@sha256:b3cc40b72b93588182b5410f723c7aaf142363311c2aa993d8a453ddcbb3ae15

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    GIT_TERMINAL_PROMPT=0

# git + CA certs are required to pin the source at build time.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates=20260601~24.04.1 \
        git=1:2.43.0-1ubuntu7.3 \
    && rm -rf /var/lib/apt/lists/*

# Obtain the repository at the pinned commit. Do not COPY the input tree.
RUN git clone https://github.com/redis/redis.git /src \
    && git -C /src fetch origin 335554f18caf7bbf6b0ac2b3548133d750f00a1b \
    && git -C /src checkout --detach 335554f18caf7bbf6b0ac2b3548133d750f00a1b

COPY setup.sh setup-overlay.sh smoke_test.sh /opt/env/
RUN chmod +x /opt/env/setup.sh /opt/env/setup-overlay.sh /opt/env/smoke_test.sh \
    && bash /opt/env/setup.sh \
    && bash /opt/env/setup-overlay.sh

WORKDIR /app
