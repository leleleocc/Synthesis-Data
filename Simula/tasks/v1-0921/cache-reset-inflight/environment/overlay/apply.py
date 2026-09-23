#!/usr/bin/env python3
from pathlib import Path
import shutil

repo = Path("/workspace/repo")
pool = repo / "vllm/v1/core/block_pool.py"
text = pool.read_text(encoding="utf-8")
old = """        num_used_blocks = self.num_gpu_blocks - self.get_num_free_blocks()
        if num_used_blocks != 1:  # The null block is always marked as used
            logger.warning(
                "Failed to reset prefix cache because some "
                "blocks (%d) are not freed yet",
                num_used_blocks - 1,
            )
            return False

        # Remove all hashes so that no new blocks will hit.
        self.cached_block_hash_to_block = BlockHashToBlockMap()
        self.cached_block_hashes_by_block.clear()

        # Remove all hashes from all blocks.
        for block in self.blocks:
            block.reset_hash()
"""
new = """        self.cached_block_hash_to_block = BlockHashToBlockMap()
        self.cached_block_hashes_by_block.clear()
"""
if old not in text:
    raise SystemExit("reset_prefix_cache body not found")
pool.write_text(text.replace(old, new, 1), encoding="utf-8")

src = Path("/tmp/overlay/workspace")
for item in src.iterdir():
    dest = Path("/workspace") / item.name
    if item.is_dir():
        shutil.copytree(item, dest, dirs_exist_ok=True)
    else:
        shutil.copy2(item, dest)
print("overlay applied")
