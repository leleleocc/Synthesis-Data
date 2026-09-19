#!/bin/bash
# Point Sentinel at the wrong master name, port, and quorum.
set -euo pipefail

CONF=/app/sentinel.conf
test -f "${CONF}"

sed -i 's/^sentinel monitor mymaster 127.0.0.1 6379 2/sentinel monitor cachemaster 127.0.0.1 9999 3/' "${CONF}"
sed -i 's/^sentinel down-after-milliseconds mymaster 30000/sentinel down-after-milliseconds cachemaster 30000/' "${CONF}"
sed -i 's/^sentinel parallel-syncs mymaster 1/sentinel parallel-syncs cachemaster 1/' "${CONF}"
sed -i 's/^sentinel failover-timeout mymaster 180000/sentinel failover-timeout cachemaster 180000/' "${CONF}"
sed -i 's/^SENTINEL master-reboot-down-after-period mymaster 0/SENTINEL master-reboot-down-after-period cachemaster 0/' "${CONF}"

grep -q 'sentinel monitor cachemaster 127.0.0.1 9999 3' "${CONF}"

chmod 0777 /app /data /results
