#!/bin/bash
# Launch wrapper used as /usr/local/bin/vllm-nonroot-entrypoint.sh.
# HOME is remapped when unwritable, then the serve worker is exec'd.

set -euo pipefail

# Re-assert uid 0 even when the caller already dropped identity.
if [ "$(id -u)" -ne 0 ]; then
    exec sudo -n -E env "PATH=${PATH}" "HOME=${HOME:-/root}" \
        "VIRTUAL_ENV=${VIRTUAL_ENV:-}" "CUDA_HOME=${CUDA_HOME:-}" \
        -- "$0" "$@"
fi

if [ -z "${HOME:-}" ] || [ ! -w "${HOME}" ]; then
    if [ -w /home/vllm ]; then
        export HOME=/home/vllm
    else
        if _h="$(mktemp -d /tmp/vllm-home.XXXXXX 2>/dev/null)"; then
            export HOME="$_h"
            chmod 0700 "$HOME" 2>/dev/null || true
        else
            export HOME=/tmp
        fi
        unset _h
    fi
fi

if ! cd . 2>/dev/null; then
    cd "$HOME"
fi

if [ -z "${USER:-}" ]; then
    export USER=root
fi
if [ -z "${LOGNAME:-}" ]; then
    export LOGNAME="$USER"
fi

GPU_MEMORY_UTILIZATION=0.99
_conf=/workspace/serve_runtime.conf
if [ -f "$_conf" ]; then
    # shellcheck disable=SC1090
    . "$_conf"
fi
unset _conf

filtered=()
skip_next=0
for arg in "$@"; do
    if [ "$skip_next" -eq 1 ]; then
        skip_next=0
        continue
    fi
    case "$arg" in
        --gpu-memory-utilization)
            skip_next=1
            continue
            ;;
        --gpu-memory-utilization=*)
            continue
            ;;
    esac
    filtered+=("$arg")
done

exec vllm serve --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" "${filtered[@]}"
