#!/usr/bin/env python3
from pathlib import Path
import shutil

repo = Path("/workspace/repo")

utils = repo / "vllm/v1/core/kv_cache_utils.py"
text = utils.read_text(encoding="utf-8")
old = """    if any(bs % hash_block_size != 0 for bs in hashing_sizes):
        raise ValueError(
            f"Invalid prefix_match_unit={hash_block_size}; prefix-cacheable "
            "KV cache group block sizes must be divisible by prefix_match_unit. "
            f"Got group block sizes={group_block_sizes}, "
            f"prefix-cacheable={hashing_sizes}."
        )
"""
if old not in text:
    raise SystemExit("prefix_match_unit raise not found")
utils.write_text(text.replace(old, "", 1), encoding="utf-8")

layout = repo / "vllm/v1/attention/backends/utils.py"
text = layout.read_text(encoding="utf-8")
old = """    if len(hnc_shapes) > 1:
        candidates = [m for m in candidates if m.is_block_compact]
        if not candidates:
            raise ValueError(
                "Specs with mixed HNC shapes need a block-compact layout, but "
                f"none is in every supported set: {supported_layouts}."
            )

"""
if old not in text:
    raise SystemExit("mixed HNC filter not found")
layout.write_text(text.replace(old, "", 1), encoding="utf-8")

cache = repo / "vllm/config/cache.py"
text = cache.read_text(encoding="utf-8")
old = """_LAYOUT_COMPAT_ALIASES = {
    "NHD": "LBNHC",
    "HND": "LBHNC",
}
"""
new = """_LAYOUT_COMPAT_ALIASES = {
}
"""
if old not in text:
    raise SystemExit("layout aliases not found")
cache.write_text(text.replace(old, new, 1), encoding="utf-8")

src = Path("/tmp/overlay/workspace")
for item in src.iterdir():
    dest = Path("/workspace") / item.name
    if item.is_dir():
        shutil.copytree(item, dest, dirs_exist_ok=True)
    else:
        shutil.copy2(item, dest)
print("overlay applied")
