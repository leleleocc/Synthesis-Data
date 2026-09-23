FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH="/app/src:${PATH}"

# git + CA certs are required to pin the source at build time.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates=20240203 \
        git=1:2.43.0-1ubuntu7.3 \
    && rm -rf /var/lib/apt/lists/*

# Obtain Redis at the sealed commit. Do not COPY the input tree.
RUN git clone https://github.com/redis/redis /src \
    && git -C /src checkout 335554f18caf7bbf6b0ac2b3548133d750f00a1b \
    && git -C /src rev-parse --verify HEAD \
    && git -C /src remote remove origin \
    && git -C /src status --porcelain

COPY setup.sh setup-overlay.sh smoke_test.sh /opt/env/

RUN chmod +x /opt/env/setup.sh /opt/env/setup-overlay.sh /opt/env/smoke_test.sh \
    && bash /opt/env/setup.sh \
    && bash /opt/env/setup-overlay.sh

WORKDIR /app
