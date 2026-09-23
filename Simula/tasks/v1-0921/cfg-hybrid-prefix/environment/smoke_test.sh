#!/bin/bash
set -euo pipefail

# Shared-base smoke: paths, CUDA/Python runtime, and the vllm CLI entrypoint.
test -d /workspace
test -d /workspace/repo
test -f /workspace/repo/pyproject.toml
test -f /workspace/repo/vllm/entrypoints/cli/main.py
test -x /opt/venv/bin/python3
test -x /opt/venv/bin/vllm
command -v nvcc >/dev/null
command -v cmake >/dev/null
command -v ninja >/dev/null

python3 - <<'PY'
import pathlib
import sys

workdir = pathlib.Path("/workspace")
source_dir = pathlib.Path("/workspace/repo")
assert workdir.is_dir(), workdir
assert source_dir.is_dir(), source_dir
assert (source_dir / "vllm" / "entrypoints" / "cli" / "main.py").is_file()

sys.path.insert(0, str(source_dir))
from vllm.version import __version__

print("workdir", workdir)
print("source_dir", source_dir)
print("vllm_version", __version__)

import torch

print("torch", torch.__version__, "cuda_built", bool(torch.version.cuda))
PY

# --help builds the serve parser, which needs a detectable platform. The
# shared image has CUDA tooling but this host may have no GPU, so force CPU.
VLLM_TARGET_DEVICE=cpu vllm --help >/tmp/vllm_help.txt
grep -q "vLLM CLI" /tmp/vllm_help.txt
nvcc --version | tail -n 1
echo "smoke ok"
