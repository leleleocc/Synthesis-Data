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

# CLI only. The daemon is the Harbor/Daytona DinD host (or the local Docker
# socket) mounted via environment/docker-compose.yaml.
COPY --from=docker:28.3.3-cli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /synthesis
RUN mkdir -p /synthesis/input /synthesis/state /synthesis/output /synthesis/logs

COPY scripts/ /opt/terminaltraj/scripts/
COPY skills/ /opt/terminaltraj/skills/
# Only chmod files that exist; an empty *.sh glob must not fail the build.
RUN find /opt/terminaltraj/scripts -type f \( -name '*.sh' -o -name '*.py' \) -exec chmod +x {} +

CMD ["bash"]
