#!/usr/bin/env python3
"""Attempt MLA paged gather against the fixtures and print symptoms."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "/workspace/repo")
import torch

FIX = Path("/workspace/fixtures")


def main():
    print("fixtures", sorted(p.name for p in FIX.glob("*.pt")))
    seq_starts = torch.load(FIX / "seq_starts.pt")
    print("seq_starts", seq_starts.tolist(), "page_size", 16,
          "expected first logical page", int(seq_starts[0]) // 16)
    print("see /workspace/symptoms.log for dest-row mismatch and fp8 garbage")
    try:
        from vllm import _custom_ops as ops
        print("custom ops", hasattr(ops, "gather_and_maybe_dequant_cache"))
    except Exception as exc:
        print("custom ops unavailable:", type(exc).__name__, exc)


if __name__ == "__main__":
    main()
