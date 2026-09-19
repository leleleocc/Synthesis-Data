#!/usr/bin/env bash
# Candidate c6: plant TLS app-layer decoder regression + require tls-session.pcap.
set -euo pipefail

WORKDIR_PATH="${WORKDIR_PATH:-/app}"
DATA_DIR="${DATA_DIR:-/data}"
RESULTS_DIR="${RESULTS_DIR:-/results}"

mkdir -p "${DATA_DIR}/pcaps" "${DATA_DIR}/rules" "${RESULTS_DIR}"

if [[ ! -f "${DATA_DIR}/pcaps/tls-session.pcap" ]]; then
  echo "c6 setup-overlay: ${DATA_DIR}/pcaps/tls-session.pcap missing (overlay assets required)" >&2
  exit 1
fi

for f in tls-events.rules decoder-events.rules; do
  if [[ ! -f "${DATA_DIR}/rules/${f}" && -f "${WORKDIR_PATH}/rules/${f}" ]]; then
    cp -a "${WORKDIR_PATH}/rules/${f}" "${DATA_DIR}/rules/${f}"
  fi
done

WORKDIR_PATH="${WORKDIR_PATH}" python3 - <<'PY'
import os, re
from pathlib import Path

p = Path(os.environ["WORKDIR_PATH"]) / "src/app-layer-ssl.c"
text = p.read_text(encoding="utf-8", errors="replace")
if "SURICATA_INCIDENT_TLS_REGRESSION" in text:
    print("c6: regression already present")
else:
    needle = '#include "app-layer-ssl.h"'
    if needle not in text:
        raise SystemExit("c6: include anchor missing")
    text = text.replace(
        needle,
        needle
        + "\n\n/* INCIDENT: forced TLS decoder regression - remove for repair */\n"
        + "#define SURICATA_INCIDENT_TLS_REGRESSION 1\n",
        1,
    )

    m = re.search(
        r"static\s+inline\s+int\s+TLSDecodeHSHelloExtensionSni\s*\([^;]*?\)\s*\{",
        text,
        re.S,
    )
    if not m:
        raise SystemExit("c6: TLSDecodeHSHelloExtensionSni not found")
    insert_at = m.end()
    text = (
        text[:insert_at]
        + "\n#ifdef SURICATA_INCIDENT_TLS_REGRESSION\n"
        + "    /* planted: drop SNI / fail extension parse */\n"
        + "    SSLSetEvent(ssl_state, TLS_DECODER_EVENT_INVALID_SNI_LENGTH);\n"
        + "    return -1;\n"
        + "#endif\n"
        + text[insert_at:]
    )

    m = re.search(
        r"static\s+int\s+TLSDecodeHandshakeHello\s*\([^;]*?\)\s*\{",
        text,
        re.S,
    )
    if not m:
        raise SystemExit("c6: TLSDecodeHandshakeHello not found")
    insert_at = m.end()
    text = (
        text[:insert_at]
        + "\n#ifdef SURICATA_INCIDENT_TLS_REGRESSION\n"
        + "    /* planted secondary regression in handshake hello */\n"
        + "    if (input_len > 0) {\n"
        + "        SSLSetEvent(ssl_state, TLS_DECODER_EVENT_INVALID_HANDSHAKE_MESSAGE);\n"
        + "        return -1;\n"
        + "    }\n"
        + "#endif\n"
        + text[insert_at:]
    )

    p.write_text(text, encoding="utf-8")
    print("c6: planted TLS decoder regression in app-layer-ssl.c")

t2 = p.read_text(encoding="utf-8", errors="replace")
assert "SURICATA_INCIDENT_TLS_REGRESSION" in t2
assert "TLSDecodeHSHelloExtensionSni" in t2
PY

command -v gcc >/dev/null
command -v python3 >/dev/null
command -v tcpdump >/dev/null
tcpdump -nn -r "${DATA_DIR}/pcaps/tls-session.pcap" -c 1 >/dev/null

echo "c6 setup-overlay: TLS decoder regression planted"
exit 0
