"""CPU reference for MLA gather. Rebuilds fixtures; does not trust /workspace/fixtures."""
from __future__ import annotations

import torch

PAGE = 16
N_BLOCKS = 12
SEQ_START = 128
SEQ_LEN = 16
SCALE = 2.0
BLOCK_TABLE = [[8, 9, 10, 11]]


def make_src(entry: int, dtype: torch.dtype) -> torch.Tensor:
    t = torch.arange(N_BLOCKS * PAGE * entry, dtype=torch.int32).reshape(
        N_BLOCKS, PAGE, entry
    )
    return t.to(dtype)


def padded_block_table() -> list[int]:
    """Compact fixture [[8,9,10,11]] stores physical pages for logical 8..11."""
    first = SEQ_START // PAGE
    return [0] * first + list(BLOCK_TABLE[0])


def gather_rows(src: torch.Tensor, dequant: bool, dst_dtype: torch.dtype) -> torch.Tensor:
    table = padded_block_table()
    start = SEQ_START
    length = SEQ_LEN
    entry = src.shape[-1]
    out = torch.empty((length, entry), dtype=dst_dtype)
    stride = len(table)
    for i in range(length):
        logical = (start + i) // PAGE
        if logical >= stride:
            raise IndexError(f"logical_block {logical} >= block_table_stride {stride}")
        phys = int(table[logical])
        slot = (start + i) % PAGE
        row = src[phys, slot]
        if dequant:
            decoded = row.view(torch.float8_e4m3fn).to(torch.float32)
            out[i] = (decoded * SCALE).to(dst_dtype)
        else:
            out[i] = row.to(dst_dtype)
    return out


def expected_bundle() -> dict:
    return {
        "fp16_seq_offset": gather_rows(make_src(576, torch.float16), False, torch.float16),
        "bf16_entry320": gather_rows(make_src(320, torch.bfloat16), False, torch.bfloat16),
        "fp8_dequant_fp16": gather_rows(make_src(576, torch.uint8), True, torch.float16),
        "fp8_dequant_bf16": gather_rows(make_src(576, torch.uint8), True, torch.bfloat16),
    }


def page0_fp16() -> torch.Tensor:
    return make_src(576, torch.float16)[0, :SEQ_LEN]


def raw_fp8_bits_as_fp16() -> torch.Tensor:
    """Numeric copy of stored fp8 bytes. A skip-dequant dest matches this, not e4m3*scale."""
    src = make_src(576, torch.uint8)
    table = padded_block_table()
    out = torch.empty((SEQ_LEN, 576), dtype=torch.float16)
    for i in range(SEQ_LEN):
        logical = (SEQ_START + i) // PAGE
        phys = int(table[logical])
        slot = (SEQ_START + i) % PAGE
        out[i] = src[phys, slot].to(torch.float16)
    return out
