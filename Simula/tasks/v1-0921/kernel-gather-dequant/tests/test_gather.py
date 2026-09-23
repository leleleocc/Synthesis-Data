"""Kill wrong seq_starts indexing, OOB table walks, and missing fp8 dequant."""
from __future__ import annotations

from pathlib import Path

import pytest
import torch

from gather_ref import expected_bundle, page0_fp16, raw_fp8_bits_as_fp16

OUT = Path("/workspace/gathered_cache.pt")
REQUIRED = {
    "fp16_seq_offset",
    "bf16_entry320",
    "fp8_dequant_fp16",
    "fp8_dequant_bf16",
    "rejected_head_dim",
}


def _load_out() -> dict:
    assert OUT.is_file(), f"missing {OUT}"
    data = torch.load(OUT, map_location="cpu", weights_only=True)
    assert isinstance(data, dict), "gathered_cache.pt must be a dict"
    extra = set(data) - REQUIRED
    missing = REQUIRED - set(data)
    assert not extra, f"unexpected keys {sorted(extra)}"
    assert not missing, f"missing keys {sorted(missing)}"
    return data


@pytest.fixture(scope="module")
def out():
    return _load_out()


@pytest.fixture(scope="module")
def expected():
    return expected_bundle()


def test_fp16_uses_seq_starts_not_page_zero(out, expected):
    got = out["fp16_seq_offset"].cpu()
    exp = expected["fp16_seq_offset"]
    assert tuple(got.shape) == (16, 576), f"fp16_seq_offset shape {tuple(got.shape)}"
    assert got.dtype == torch.float16
    page0 = page0_fp16()
    # Padding the table without seq_starts copies page 0.
    assert not torch.equal(got.to(torch.float32), page0.to(torch.float32)), (
        "fp16 dest matches physical page 0; seq_starts was ignored"
    )
    torch.testing.assert_close(got.to(torch.float32), exp.to(torch.float32), atol=1e-3, rtol=1e-3)
    print("normal case: pass")


def test_bf16_entry_320(out, expected):
    got = out["bf16_entry320"].cpu()
    exp = expected["bf16_entry320"]
    assert tuple(got.shape) == (16, 320)
    assert got.dtype == torch.bfloat16
    torch.testing.assert_close(got.to(torch.float32), exp.to(torch.float32), atol=1e-2, rtol=1e-2)
    print("edge case: pass")


def test_fp8_dequant_not_raw_bits(out, expected):
    raw = raw_fp8_bits_as_fp16()
    got16 = out["fp8_dequant_fp16"].cpu()
    gotbf = out["fp8_dequant_bf16"].cpu()
    assert got16.dtype == torch.float16 and tuple(got16.shape) == (16, 576)
    assert gotbf.dtype == torch.bfloat16 and tuple(gotbf.shape) == (16, 576)
    assert not torch.equal(got16, raw), (
        "fp8 dest holds raw stored bits; dequant with scale was skipped"
    )
    torch.testing.assert_close(
        got16.to(torch.float32),
        expected["fp8_dequant_fp16"].to(torch.float32),
        atol=2e-2,
        rtol=2e-2,
        equal_nan=True,
    )
    torch.testing.assert_close(
        gotbf.to(torch.float32),
        expected["fp8_dequant_bf16"].to(torch.float32),
        atol=5e-2,
        rtol=5e-2,
        equal_nan=True,
    )
    print("error handling: pass")


def test_head_dim_reject(out):
    msg = str(out["rejected_head_dim"])
    assert "320" in msg or "576" in msg, (
        f"rejected_head_dim {msg!r} does not mention 320 or 576"
    )
    print("state check: pass")
