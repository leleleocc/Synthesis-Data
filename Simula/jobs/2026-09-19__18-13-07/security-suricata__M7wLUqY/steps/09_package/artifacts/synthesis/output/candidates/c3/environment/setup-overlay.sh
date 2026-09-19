#!/usr/bin/env bash
# Candidate c3: break HTTP event rules under /data and ensure session.pcap is present.
set -euo pipefail

WORKDIR_PATH="${WORKDIR_PATH:-/app}"
DATA_DIR="${DATA_DIR:-/data}"
RESULTS_DIR="${RESULTS_DIR:-/results}"

mkdir -p "${DATA_DIR}/rules" "${DATA_DIR}/pcaps" "${DATA_DIR}/etc" "${RESULTS_DIR}"

if [[ ! -f "${DATA_DIR}/pcaps/session.pcap" ]]; then
  echo "c3 setup-overlay: ${DATA_DIR}/pcaps/session.pcap missing (overlay assets required)" >&2
  exit 1
fi

if [[ ! -f "${WORKDIR_PATH}/rules/http-events.rules" ]]; then
  echo "c3 setup-overlay: stock http-events.rules missing under workdir" >&2
  exit 1
fi

WORKDIR_PATH="${WORKDIR_PATH}" DATA_DIR="${DATA_DIR}" python3 - <<'PY'
import os
from pathlib import Path
src = Path(os.environ["WORKDIR_PATH"]) / "rules/http-events.rules"
dst = Path(os.environ["DATA_DIR"]) / "rules/http-events.rules"
lines = src.read_text(encoding="utf-8", errors="replace").splitlines(True)
out = []
for line in lines:
    if "sid:2221000;" in line:
        line = line.replace("alert http", "alert tcp")
        line = line.replace(
            "app-layer-event:http.unknown_error",
            'content:"BROKEN"; app-layer-event:http.unknown_error',
        )
        line = line.replace("sid:2221000; rev:1;)", "sid:2221000 rev:1)")
    if "sid:2221014;" in line:
        line = line.replace("flow:established,to_server", "flow:established,to_client")
    if "sid:2221015;" in line:
        line = line.replace("alert http", "alert tls")
        line = line.replace("http.host_header_ambiguous", "tls.invalid_sni_length")
    if "sid:2221003;" in line:
        line = (
            'alert http any any -> any any '
            '(msg:"SURICATA HTTP invalid request chunk len BROKEN";\n'
        )
    out.append(line)
out.append(
    'alert http any any -> any any '
    '(msg:"SURICATA HTTP bogus tls suppress"; flow:established; content:"|16 03|"; '
    "classtype:protocol-command-decode; sid:2221099; rev:1;)\n"
)
dst.write_text("".join(out), encoding="utf-8")
print("c3: wrote broken", dst, "lines", len(out))
PY

if [[ -f "${WORKDIR_PATH}/rules/tls-events.rules" ]]; then
  cp -a "${WORKDIR_PATH}/rules/tls-events.rules" "${DATA_DIR}/rules/tls-events.rules"
fi

if cmp -s "${DATA_DIR}/rules/http-events.rules" "${WORKDIR_PATH}/rules/http-events.rules"; then
  echo "c3 setup-overlay: http-events.rules still matches stock" >&2
  exit 1
fi

command -v python3 >/dev/null
command -v tcpdump >/dev/null
tcpdump -nn -r "${DATA_DIR}/pcaps/session.pcap" -c 1 >/dev/null

echo "c3 setup-overlay: broken HTTP rules + session pcap ready"
exit 0
