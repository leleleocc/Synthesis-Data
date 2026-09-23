#!/usr/bin/env python3
"""Write CPU gather fixtures under /workspace/fixtures."""
from pathlib import Path
import torch

out = Path("/workspace/fixtures")
out.mkdir(parents=True, exist_ok=True)
page = 16
n_blocks = 12
# src_cache: [NUM_BLOCKS, BLOCK_SIZE, ENTRY]
for name, entry, dtype in (
    ("src_cache_fp16", 576, torch.float16),
    ("src_cache_bf16_320", 320, torch.bfloat16),
    ("src_cache_fp8", 576, torch.uint8),
):
    t = torch.arange(n_blocks * page * entry, dtype=torch.int32).reshape(
        n_blocks, page, entry
    )
    torch.save(t.to(dtype), out / f"{name}.pt")
# one request, seq_starts = 128 -> first logical page 8 when page=16
torch.save(torch.tensor([[8, 9, 10, 11]], dtype=torch.int32), out / "block_table.pt")
torch.save(torch.tensor([0, 16], dtype=torch.int32), out / "cu_seq_lens.pt")
torch.save(torch.tensor([128], dtype=torch.int32), out / "seq_starts.pt")
torch.save(torch.tensor([2.0], dtype=torch.float32), out / "scale.pt")
torch.save(torch.zeros(16, dtype=torch.int32), out / "token_to_seq.pt")
print("fixtures written", out)
