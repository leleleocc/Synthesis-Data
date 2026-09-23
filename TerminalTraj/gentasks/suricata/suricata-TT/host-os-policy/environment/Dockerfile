FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# git + CA certs are required to pin the source at image build time.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

# Obtain Suricata at the exact target_spec.source_repo.commit. Do not COPY the
# input tree; the Harbor package does not ship it.
RUN git clone https://github.com/OISF/suricata /app \
    && git -C /app checkout d681600f3648030a67f7d618d30742bfd5fe7169 \
    && git -C /app config --global --add safe.directory /app

COPY setup.sh setup-overlay.sh smoke_test.sh /opt/env/
RUN chmod 0755 /opt/env/setup.sh /opt/env/setup-overlay.sh /opt/env/smoke_test.sh \
    && bash /opt/env/setup.sh \
    && bash /opt/env/setup-overlay.sh

WORKDIR /app
