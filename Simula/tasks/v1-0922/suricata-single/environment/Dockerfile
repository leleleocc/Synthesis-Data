FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System packages only. Do NOT install Debian docker.io: on Trixie it is
# ~26.x and cannot talk to Harbor's DinD daemon (docker:28.3.3-dind, API
# 1.51). The matching CLI is copied from the official image below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       bash ca-certificates curl git jq make gcc g++ unzip zip file \
    && rm -rf /var/lib/apt/lists/*

# The project-scoped DinD service shares /synthesis with this client.
COPY --from=docker:28.3.3-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker:28.3.3-cli /usr/local/libexec/docker/cli-plugins/ /usr/local/libexec/docker/cli-plugins/
RUN docker compose version && docker buildx version \
    && pip install --no-cache-dir 'harbor[daytona]==0.23.0'

WORKDIR /synthesis
RUN mkdir -p /synthesis/input /synthesis/state /synthesis/output /synthesis/logs

# Agent resources live in these three trees only.
COPY docs/ /opt/terminaltraj/docs/
COPY scripts/ /opt/terminaltraj/scripts/
COPY skills/ /opt/terminaltraj/skills/
COPY assets/ /opt/terminaltraj/assets/
COPY setup-overlay.sh /opt/terminaltraj/setup-overlay.sh
# Only chmod files that exist; an empty *.sh glob must not fail the build.
RUN find /opt/terminaltraj/scripts /opt/terminaltraj/assets -type f \( -name '*.sh' -o -name '*.py' \) -exec chmod +x {} + \
    && chmod +x /opt/terminaltraj/setup-overlay.sh \
    && /opt/terminaltraj/setup-overlay.sh

CMD ["bash"]
