#!/bin/bash
# Plant a stale help target whose printed knobs do not match the real compile.
set -euo pipefail

MK=/app/src/Makefile
test -f "${MK}"

if ! grep -q '^help:' "${MK}"; then
    cat >> "${MK}" << 'EOF'

help:
	@echo "OPTIMIZATION=-O0"
	@echo "MALLOC=libc"
	@echo "BUILD_TLS="
	@echo "PREFIX=/usr"
	@echo "Try make BUILD_TLS=no"
.PHONY: help
EOF
fi

grep -q '^help:' "${MK}"
chmod 0777 /app /data /results
