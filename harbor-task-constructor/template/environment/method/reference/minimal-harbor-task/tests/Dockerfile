FROM python:3.12-slim

RUN export DEBIAN_FRONTEND=noninteractive \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# FIXED: this is the Reward Kit 0.2.x installation and PATH exposure proven by the structural anchor.
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh \
    && uv tool install --python 3.12 'harbor-rewardkit==0.2.*' \
    && ln -sf /root/.local/bin/rewardkit /usr/local/bin/rewardkit \
    && rewardkit --help > /dev/null

COPY . /tests/
RUN chmod +x /tests/test.sh
