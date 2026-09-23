"""Artifact checks for host-arch cache kernels and cooperative top-k gating."""
from __future__ import annotations

import json
import os
import re
import struct
import subprocess
from pathlib import Path

import pytest

SO = Path("/workspace/cache_kernels.so")
REJECT = Path("/workspace/gather_head_dim_reject.txt")
MATRIX = Path("/workspace/arch_matrix.json")
REQUIRED = {
    "torch_cuda_arch_list",
    "host_arch",
    "cache_kernels_archs",
    "cooperative_topk_enabled",
    "gather_rejects_head_dim_128",
}


@pytest.fixture(scope="module")
def matrix() -> dict:
    assert MATRIX.is_file(), "missing /workspace/arch_matrix.json"
    data = json.loads(MATRIX.read_text(encoding="utf-8"))
    extra = set(data) - REQUIRED
    missing = REQUIRED - set(data)
    assert not extra, f"unexpected arch_matrix keys {sorted(extra)}"
    assert not missing, f"missing arch_matrix keys {sorted(missing)}"
    return data


def test_shared_object_is_host_arch_elf(matrix):
    assert SO.is_file() and SO.stat().st_size > 0, "missing /workspace/cache_kernels.so"
    so_bytes = SO.read_bytes()
    assert so_bytes[:4] == b"\x7fELF", "cache_kernels.so is not an ELF shared object"
    host_arch = str(matrix["host_arch"]).strip()
    assert re.fullmatch(r"\d+\.\d+[a-zA-Z]?", host_arch), f"host_arch {host_arch!r} is not an sm version"
    archs = matrix["cache_kernels_archs"]
    assert isinstance(archs, list) and archs and all(isinstance(a, str) and a.strip() for a in archs)
    assert host_arch in archs, f"cache_kernels_archs {archs} does not include host_arch {host_arch}"
    declared_list = str(matrix["torch_cuda_arch_list"]).strip()
    assert declared_list, "torch_cuda_arch_list is empty"

    detected = None
    try:
        import torch

        if torch.cuda.is_available():
            major, minor = torch.cuda.get_device_capability(0)
            detected = f"{major}.{minor}"
    except Exception:
        detected = None
    if detected is None:
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip().splitlines()
            if out:
                detected = out[0].strip()
        except Exception:
            detected = None
    if detected:
        numeric = re.match(r"(\d+\.\d+)", host_arch)
        assert numeric and numeric.group(1) == detected, (
            f"host_arch {host_arch} does not match attached GPU {detected}"
        )

    parts = host_arch.split(".")
    sm_tag = f"sm_{parts[0]}{parts[1][0] if parts[1] else '0'}"
    if sm_tag.encode() not in so_bytes:
        major_minor = int(parts[0]) * 10 + int(parts[1][0])
        packed = struct.pack("<I", major_minor)
        assert packed in so_bytes or sm_tag.replace("sm_", "compute_").encode() in so_bytes, (
            f"cache_kernels.so does not contain host arch marker {sm_tag} / {major_minor}"
        )
    print("normal case: pass")


def test_gather_head_dim_reject_artifact(matrix):
    assert REJECT.is_file(), "missing /workspace/gather_head_dim_reject.txt"
    reject_txt = REJECT.read_text(encoding="utf-8")
    assert re.search(r"320|576", reject_txt), "gather reject text does not mention 320 or 576"
    assert matrix.get("gather_rejects_head_dim_128") is True
    print("edge case: pass")


def test_cooperative_topk_gated(matrix):
    enabled = matrix.get("cooperative_topk_enabled")
    assert enabled in (True, False)
    host_arch = str(matrix["host_arch"]).strip()
    host_numeric = float(re.match(r"(\d+\.\d+)", host_arch).group(1))
    intersects_coop = host_numeric >= 9.0
    assert not (enabled and not intersects_coop), (
        "cooperative_topk_enabled is true but host arch is not sm90+/sm100+/sm120"
    )
    print("error handling: pass")
    print("state check: pass")
