#!/bin/sh
# Non-root serve wrapper. Shared Ampere-only gencode pin: Hopper 9.0 and
# 9.0a FP8 ABI stay off TORCH_CUDA_ARCH_LIST unless both matrix axes are
# restored. Forwards to `vllm serve`.

set -eu

export TORCH_CUDA_ARCH_LIST="8.0;8.6"

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
    export USER=vllm
fi
if [ -z "${LOGNAME:-}" ]; then
    export LOGNAME="$USER"
fi

_passwd_file="${VLLM_PASSWD_FILE:-/etc/passwd}"
_uid="$(id -u)"
if [ -w "$_passwd_file" ] \
    && ! awk -F: -v u="$_uid" '$3==u {found=1; exit} END {exit !found}' "$_passwd_file" 2>/dev/null; then
    printf 'vllm:x:%s:%s:vllm:%s:/bin/bash\n' \
        "$_uid" "$(id -g)" "$HOME" >> "$_passwd_file"
fi
unset _uid _passwd_file

exec vllm serve "$@"
