#!/usr/bin/env python3
from pathlib import Path
import runpy
import shutil

repo = Path("/workspace/repo")
cu = repo / "csrc/libtorch_stable/cache_kernels.cu"
text = cu.read_text(encoding="utf-8")
replacements = [
    (
        "    const int32_t source_begin = seq_starts == nullptr ? 0 : seq_starts[req_id];",
        "    const int32_t source_begin = 0;",
    ),
    (
        "    copy_task = has_task && page.logical_block < block_table_stride;",
        "    copy_task = has_task;",
    ),
]
for old, new in replacements:
    if old not in text:
        raise SystemExit(f"pattern not found: {old[:60]}")
    text = text.replace(old, new, 1)
old = """      if constexpr (kv_dt == Fp8KVCacheDataType::kAuto) {
        reinterpret_cast<stype*>(output)[idx] =
            static_cast<stype>(reinterpret_cast<const ltype*>(src)[idx]);
      } else {
        const ltype loaded = reinterpret_cast<const ltype*>(src)[idx];
        stype converted;
#pragma unroll
        for (int32_t j = 0; j < vec_size; ++j) {
          converted.val[j] = fp8::scaled_convert<scalar_t, cache_t, kv_dt>(
              loaded.val[j], scale_value);
        }
        reinterpret_cast<stype*>(output)[idx] = converted;
      }"""
new = """      reinterpret_cast<stype*>(output)[idx] =
          static_cast<stype>(reinterpret_cast<const ltype*>(src)[idx]);"""
if old not in text:
    raise SystemExit("fp8 gather copy block not found")
text = text.replace(old, new, 1)
cu.write_text(text, encoding="utf-8")

src = Path("/tmp/overlay/workspace")
for item in src.iterdir():
    dest = Path("/workspace") / item.name
    if item.is_dir():
        shutil.copytree(item, dest, dirs_exist_ok=True)
    else:
        shutil.copy2(item, dest)
print("overlay applied")
runpy.run_path("/workspace/make_fixtures.py", run_name="__main__")
