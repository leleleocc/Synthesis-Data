#!/usr/bin/env bash
# Vendor a rejected ACL draft under /data/acl and confirm python3.
set -euo pipefail
command -v python3 >/dev/null
mkdir -p /data/acl
# CRLF draft: default user is open, app keys are unrestricted, extra guest,
# and a requirepass line that is not valid ACL-file syntax.
python3 - <<'PY'
from pathlib import Path
body = (
    "# DRAFT - rejected in review, do not load as-is\r\n"
    "user default on nopass ~* &* +@all\r\n"
    "user app on >app-secret-7 ~* +@all -@admin\r\n"
    "user ops on >ops-secret-7 ~* +@all\r\n"
    "user guest on nopass ~* +@read\r\n"
    "requirepass not-valid-in-aclfile\r\n"
)
Path("/data/acl/users.acl").write_bytes(body.encode("ascii"))
print("acl draft written")
PY
chmod 644 /data/acl/users.acl
exit 0
