#!/usr/bin/env bash
# Runs once, before the first iteration, as root in the workspace.
#
# Root because this is the provisioning phase: `npm install -g` writes to a
# root-owned global prefix. The agent that follows runs as gem, and the runner
# hands it the workspace in between — so anything this script leaves in the tree
# will be owned by the agent, and anything it installs globally will be on the
# agent's PATH.
#
# Non-zero here is a hard failure: the loop never starts and the run is reported
# as failed. That is deliberate — an agent turned loose on a half-prepared
# environment burns a model budget discovering that its tools are missing.
#
# Anything installed here has to be installed again next run. The workspace
# persists on NAS, but the container does not, so global npm and pip installs are
# gone by the next sandbox.

set -euo pipefail

echo "init: $(date -u +%H:%M:%S) as $(id -un) in $(pwd)"

# The agent the runner drives. The image ships node; claude itself does not.
if command -v claude >/dev/null 2>&1; then
  echo "init: claude already present at $(command -v claude)"
else
  echo "init: installing @anthropic-ai/claude-code ..."
  npm install -g @anthropic-ai/claude-code
fi
claude --version

# pytest is the acceptance check named in PROMPT.md, so it is init's job to make
# the check runnable rather than something for the agent to discover mid-round.
# System-wide, not --user: --user as root installs into root's site-packages,
# which is precisely where the agent will not look.
if ! python3 -m pytest --version >/dev/null 2>&1; then
  echo "init: installing pytest ..."
  pip install --quiet pytest \
    || pip install --quiet --break-system-packages pytest
fi
python3 -m pytest --version

echo "init: ready"
