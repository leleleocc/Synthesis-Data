#!/usr/bin/env python3
from pathlib import Path
import shutil

repo = Path("/workspace/repo")

utils = repo / "vllm/v1/core/kv_cache_utils.py"
text = utils.read_text(encoding="utf-8")
old = """    extra_keys: list[Any] = (
        lora_extra_keys + mm_extra_keys + cache_salt_keys + prompt_embeds_keys
    )"""
new = """    extra_keys: list[Any] = (
        mm_extra_keys + prompt_embeds_keys
    )"""
if old not in text:
    raise SystemExit("kv_cache_utils extra_keys block not found")
utils.write_text(text.replace(old, new, 1), encoding="utf-8")

mgr = repo / "vllm/v1/core/kv_cache_manager.py"
text = mgr.read_text(encoding="utf-8")
old = """        available_blocks = self.block_pool.get_num_free_blocks() - reserved_blocks
        required_blocks = num_blocks_to_allocate + watermark_blocks
        if required_blocks > available_blocks:
            # Cannot allocate new blocks
            return None

        if (
            new_computed_block_list is not self.empty_kv_cache_blocks.blocks
            or num_external_computed_tokens > 0
        ):
            # Append the new computed blocks to the request blocks until now to
            # avoid the case where the new blocks cannot be allocated.
            self.coordinator.allocate_new_computed_blocks(
                request_id=request.request_id,
                new_computed_blocks=new_computed_block_list,
                num_local_computed_tokens=num_local_computed_tokens,
                num_external_computed_tokens=num_external_computed_tokens,
            )
"""
new = """        available_blocks = self.block_pool.get_num_free_blocks() - reserved_blocks
        required_blocks = num_blocks_to_allocate + watermark_blocks
        if (
            new_computed_block_list is not self.empty_kv_cache_blocks.blocks
            or num_external_computed_tokens > 0
        ):
            self.coordinator.allocate_new_computed_blocks(
                request_id=request.request_id,
                new_computed_blocks=new_computed_block_list,
                num_local_computed_tokens=num_local_computed_tokens,
                num_external_computed_tokens=num_external_computed_tokens,
            )
        if required_blocks > available_blocks:
            return None
"""
if old not in text:
    raise SystemExit("allocate_slots capacity block not found")
mgr.write_text(text.replace(old, new, 1), encoding="utf-8")

src = Path("/tmp/overlay/workspace")
for item in src.iterdir():
    dest = Path("/workspace") / item.name
    if item.is_dir():
        shutil.copytree(item, dest, dirs_exist_ok=True)
    else:
        shutil.copy2(item, dest)
print("overlay applied")
