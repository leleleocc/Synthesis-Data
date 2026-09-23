#!/bin/bash
# Build a valid Redis 7 dump, then break RDB checksum verification and expire loading.
set -euo pipefail

test -x /app/src/redis-server
test -x /app/src/redis-cli
test -f /app/src/rdb.c

mkdir -p /data /results
chmod 0777 /data /results

# Generate the audit dump with the intact server, then shut it down.
/app/src/redis-server \
    --bind 127.0.0.1 \
    --port 16379 \
    --protected-mode yes \
    --dir /data \
    --dbfilename dump.rdb \
    --save "" \
    --appendonly no \
    --daemonize yes \
    --logfile /data/rdb-gen.log \
    --pidfile /data/rdb-gen.pid

for i in 1 2 3 4 5 6 7 8 9 10; do
    if /app/src/redis-cli -h 127.0.0.1 -p 16379 PING 2>/dev/null | grep -q PONG; then
        break
    fi
    sleep 0.2
done

/app/src/redis-cli -h 127.0.0.1 -p 16379 SET user:1 alice
/app/src/redis-cli -h 127.0.0.1 -p 16379 PEXPIRE user:1 2592000000
/app/src/redis-cli -h 127.0.0.1 -p 16379 SET cache:flag ok
/app/src/redis-cli -h 127.0.0.1 -p 16379 XADD stream:events 1700000000000-0 status ok
/app/src/redis-cli -h 127.0.0.1 -p 16379 SAVE
/app/src/redis-cli -h 127.0.0.1 -p 16379 SHUTDOWN NOSAVE || true
sleep 0.3
rm -f /data/rdb-gen.pid /data/rdb-gen.log
test -s /data/dump.rdb

# Invert CRC64 mismatch detection in both the loader and redis-check-rdb.
sed -i 's/} else if (cksum != expected) {/} else if (cksum == expected) {/' /app/src/rdb.c
sed -i 's/} else if (cksum != expected) {/} else if (cksum == expected) {/' /app/src/redis-check-rdb.c
grep -q 'cksum == expected' /app/src/rdb.c
grep -q 'cksum == expected' /app/src/redis-check-rdb.c

# Load millisecond expires as seconds so user:1 drops almost immediately.
sed -i 's/expiretime = rdbLoadMillisecondTime(rdb,rdbver);/expiretime = rdbLoadMillisecondTime(rdb,rdbver) \/ 1000;/' /app/src/rdb.c
grep -q 'rdbLoadMillisecondTime(rdb,rdbver) / 1000' /app/src/rdb.c

make -C /app -j"$(nproc)"
test -x /app/src/redis-check-rdb
chmod 0777 /app /data /results
chmod 0644 /data/dump.rdb
