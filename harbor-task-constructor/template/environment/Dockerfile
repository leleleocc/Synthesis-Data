FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      ca-certificates \
      curl \
      git \
      gzip \
      jq \
      tar \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
      'harbor[daytona]==0.21.0' \
      'harbor-rewardkit==0.2.*'

COPY method/ /app/method/
COPY unpack-seed.sh /tmp/unpack-seed.sh
# seed contains exactly one complete capsule: editable build/ or transport build.tar.gz.
COPY seed/ /tmp/seed/
RUN /bin/sh /tmp/unpack-seed.sh && rm -rf /tmp/seed /tmp/unpack-seed.sh
WORKDIR /app/build
