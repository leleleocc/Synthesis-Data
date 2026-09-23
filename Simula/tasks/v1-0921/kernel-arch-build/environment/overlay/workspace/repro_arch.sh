#!/bin/bash
set -euo pipefail
echo "TORCH_CUDA_ARCH_LIST=${TORCH_CUDA_ARCH_LIST-unset}"
echo "host nvidia-smi (if present):"
nvidia-smi -q 2>/dev/null | head -n 5 || echo "nvidia-smi not available"
cat /workspace/symptoms.log
