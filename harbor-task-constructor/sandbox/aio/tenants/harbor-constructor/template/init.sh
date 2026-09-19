#!/bin/sh
# init.sh — provisioning for the harbor-constructor sandbox instance.
# Runs once as root before the claude -p loop. Idempotent.
#
# uv and Python 3.12 are provided by the runtime image. Harbor and Reward Kit
# live in an isolated venv because the system Python is 3.10.
set -eu

HARBOR_VENV="${SOP_HARBOR_VENV:-/opt/harbor-venv}"
HARBOR_PYTHON="${SOP_HARBOR_PYTHON:-${HARBOR_VENV}/bin/python}"

if ! command -v uv > /dev/null 2>&1; then
  echo "uv is required by harbor-constructor but was not found" >&2
  exit 1
fi

if [ ! -x "${HARBOR_PYTHON}" ]; then
  echo "creating Harbor Python environment at ${HARBOR_VENV}"
  uv venv "${HARBOR_VENV}" --python /usr/local/bin/python3.12
  uv pip install \
    --python "${HARBOR_PYTHON}" \
    'harbor[daytona]==0.21.0' \
    'harbor-rewardkit==0.2.*'
else
  echo "Harbor Python environment already present: ${HARBOR_VENV}"
fi

if [ -x "${HARBOR_VENV}/bin/harbor" ]; then
  ln -sf "${HARBOR_VENV}/bin/harbor" /usr/local/bin/harbor
fi
if [ -x "${HARBOR_VENV}/bin/rewardkit" ]; then
  ln -sf "${HARBOR_VENV}/bin/rewardkit" /usr/local/bin/rewardkit
fi
# harbor-python must be a wrapper, NOT a symlink. CPython locates a venv by
# looking for pyvenv.cfg beside the *invoked* path, without resolving symlinks:
# invoked as /usr/local/bin/harbor-python it probes /usr/local/pyvenv.cfg, finds
# nothing, and falls back to the base prefix /opt/python3.12 — so `import harbor`
# raises ModuleNotFoundError even though the venv is intact. `exec` hands Python
# the real in-venv path, so the wrapper resolves correctly.
# rm -f first: `>` onto an existing symlink writes through it and would clobber
# the venv interpreter itself.
rm -f /usr/local/bin/harbor-python
printf '#!/bin/sh\nexec "%s" "$@"\n' "${HARBOR_PYTHON}" > /usr/local/bin/harbor-python
chmod 0755 /usr/local/bin/harbor-python

# Verify through the path the template actually uses (route.sh, run-two-models.sh
# and the role docs all call /usr/local/bin/harbor-python), not through
# ${HARBOR_PYTHON}. Checking the latter is what let the broken symlink ship.
/usr/local/bin/harbor-python -c 'import harbor, rewardkit; print("harbor dependencies ready")'

# Install Claude Code if not already present.
if ! command -v claude > /dev/null 2>&1; then
  echo "installing claude..."
  npm install -g @anthropic-ai/claude-code 2>&1
else
  echo "claude already installed"
fi

# Ensure the evidence root exists so roles can write to it immediately.
mkdir -p "${SOP_EVIDENCE_ROOT:-/home/app/workspace/evidence}"

echo "init done"
