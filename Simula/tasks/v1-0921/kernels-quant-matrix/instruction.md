The CUDA/FP8 compile matrix no longer emits Hopper-class gencode and the FP8 quant kernel ABI together. Work driven through /usr/local/bin/vllm-nonroot-entrypoint.sh still produces Ampere-class objects, but a Hopper 9.0 cell and an FP8 scaled-mm ABI cell never come out of the same cmake/nvcc pass. Restoring only the Hopper 9.0 architecture still leaves the FP8 quant kernel ABI unbuilt. Restoring only the FP8 scaled-mm ABI still leaves Hopper 9.0 gencode absent.

Emit a cmake/build matrix as JSON at /workspace/cmake_build_matrix.json. Do not pull model weights or other artifacts from the network; only cmake, nvcc, and files already on the machine may be used. The matrix is not a kernel parity table and not an HTTP report. Joint success requires both axes.

The document must be a single JSON object with all of the following fields:

```json
{
  "entrypoint": "/usr/local/bin/vllm-nonroot-entrypoint.sh",
  "sm90_ok": true,
  "fp8_abi_ok": true,
  "cells": [
    {
      "arch": "9.0",
      "kernel_abi": "sm90",
      "built": true,
      "artifact_path": "/absolute/path/to/hopper-sm90-gencode-artifact"
    },
    {
      "arch": "9.0a",
      "kernel_abi": "fp8_scaled_mm",
      "built": true,
      "artifact_path": "/absolute/path/to/sm90a-fp8-scaled-mm-artifact"
    }
  ]
}
```

entrypoint is the string "/usr/local/bin/vllm-nonroot-entrypoint.sh". sm90_ok is true only when cells contains a Hopper 9.0 / sm90 cell whose built is true and whose artifact_path exists as a file. fp8_abi_ok is true only when cells contains an FP8 quant kernel ABI cell (sm90a / 9.0a scaled-mm fp8) whose built is true and whose artifact_path exists as a file. A matrix with sm90_ok true and fp8_abi_ok false is not complete. A matrix with fp8_abi_ok true and sm90_ok false is not complete. The two booleans are not sufficient on their own: a verifier will check the cells, the architecture strings, the kernel ABI strings, and that each artifact_path exists.

You have 1800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
