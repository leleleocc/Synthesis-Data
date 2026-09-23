#!/bin/bash
# Inject AOF-rewrite defects: drop live replica offset after BGREWRITEAOF.
# The RDB preamble already omits repl-id/offset (NULL rsi); leave that for the agent.
set -euo pipefail

AOF=/app/src/aof.c
test -f "${AOF}"

# Zero master_repl_offset and fsynced_reploff after a successful rewrite.
sed -i '/Background AOF rewrite finished successfully/a\
        server.master_repl_offset = 0;\
        server.fsynced_reploff = -1;\
        atomicSet(server.fsynced_reploff_pending, 0);' "${AOF}"

# When entering WAIT_REWRITE, also wipe the live offset so PSYNC cannot resume.
sed -i '/atomicSet(server.fsynced_reploff_pending, server.master_repl_offset);/{
n
s/server.fsynced_reploff = 0;/server.fsynced_reploff = 0;\
        server.master_repl_offset = 0;/
}' "${AOF}"

grep -q "server.master_repl_offset = 0;" "${AOF}"

make -C /app -j"$(nproc)"
chmod 0777 /app /data /results
