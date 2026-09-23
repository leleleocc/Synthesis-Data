#!/usr/bin/env python3
from pathlib import Path
import shutil

repo = Path("/workspace/repo")
cmake = repo / "CMakeLists.txt"
text = cmake.read_text(encoding="utf-8")
old = """    if(COOPERATIVE_TOPK_ARCHS)
      list(APPEND VLLM_GPU_FLAGS "-DVLLM_ENABLE_COOPERATIVE_TOPK=1")

    endif()"""
new = """    list(APPEND VLLM_GPU_FLAGS "-DVLLM_ENABLE_COOPERATIVE_TOPK=1")"""
if old not in text:
    raise SystemExit("COOPERATIVE_TOPK flags block not found")
text = text.replace(old, new, 1)
old = """    if(COOPERATIVE_TOPK_ARCHS)
      list(APPEND VLLM_STABLE_EXT_SRC
        "csrc/libtorch_stable/cooperative_topk.cu")
      set_gencode_flags_for_srcs(
        SRCS "csrc/libtorch_stable/cooperative_topk.cu"
        CUDA_ARCHS "${COOPERATIVE_TOPK_ARCHS}")
    endif()"""
new = """    list(APPEND VLLM_STABLE_EXT_SRC
      "csrc/libtorch_stable/cooperative_topk.cu")
    set_gencode_flags_for_srcs(
      SRCS "csrc/libtorch_stable/cooperative_topk.cu"
      CUDA_ARCHS "${CUDA_ARCHS}")"""
if old not in text:
    raise SystemExit("cooperative_topk.cu append block not found")
text = text.replace(old, new, 1)
old = """    if(COOPERATIVE_TOPK_ARCHS)
      target_compile_definitions(_C_stable_libtorch PRIVATE
        VLLM_ENABLE_COOPERATIVE_TOPK=1)
    endif()"""
new = """    target_compile_definitions(_C_stable_libtorch PRIVATE
      VLLM_ENABLE_COOPERATIVE_TOPK=1)"""
if old not in text:
    raise SystemExit("target_compile_definitions cooperative block not found")
cmake.write_text(text.replace(old, new, 1), encoding="utf-8")

cu = repo / "csrc/libtorch_stable/cache_kernels.cu"
text = cu.read_text(encoding="utf-8")
old = """  STD_TORCH_CHECK(
      head_dim == 320 || head_dim == 576,
      "gather_and_maybe_dequant_cache only support the head_dim to 320 or 576 "
      "for better performance")
"""
if old not in text:
    raise SystemExit("head_dim check not found")
cu.write_text(text.replace(old, "", 1), encoding="utf-8")

src = Path("/tmp/overlay/workspace")
for item in src.iterdir():
    dest = Path("/workspace") / item.name
    if item.is_dir():
        shutil.copytree(item, dest, dirs_exist_ok=True)
    else:
        shutil.copy2(item, dest)
print("overlay applied")
