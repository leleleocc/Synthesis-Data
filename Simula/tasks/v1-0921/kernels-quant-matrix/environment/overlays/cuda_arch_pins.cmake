# Shared arch list for the cmake/nvcc compile matrix.
# Ampere-only: Hopper 9.0 and 9.0a are omitted so both the sm90 gencode
# cell and the 9.0a FP8 scaled-mm ABI cell stay dark unless this list
# and the FP8 ABI gate are restored together.
set(CUDA_ARCHS "8.0;8.6")
set(TORCH_CUDA_ARCH_LIST "8.0;8.6")
