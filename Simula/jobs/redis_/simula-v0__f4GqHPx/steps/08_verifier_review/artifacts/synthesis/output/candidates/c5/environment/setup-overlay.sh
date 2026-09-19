#!/bin/bash
# Break redis.conf so a naive start is not an LRU loopback cache.
set -euo pipefail

CONF=/app/redis.conf
test -f "${CONF}"

sed -i 's/^bind 127.0.0.1 -::1/bind 0.0.0.0/' "${CONF}"
sed -i 's/^protected-mode yes/protected-mode no/' "${CONF}"
sed -i 's/^daemonize no/daemonize yes/' "${CONF}"
sed -i 's|^dir ./|dir /tmp|' "${CONF}"
sed -i 's/^appendonly no/appendonly yes/' "${CONF}"
sed -i 's|^pidfile /var/run/redis_6379.pid|pidfile /var/run/redis.pid|' "${CONF}"

# Leave maxmemory commented (unlimited) and default save points enabled.
grep -q '^bind 0.0.0.0' "${CONF}"
grep -q '^protected-mode no' "${CONF}"
grep -q '^daemonize yes' "${CONF}"

chmod 0777 /app /data /results
