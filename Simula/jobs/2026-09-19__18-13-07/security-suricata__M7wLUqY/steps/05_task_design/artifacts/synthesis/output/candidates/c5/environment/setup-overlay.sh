#!/usr/bin/env bash
# Candidate c5: require incident.pcap from overlay assets; keep threshold/decoder samples.
set -euo pipefail

WORKDIR_PATH="${WORKDIR_PATH:-/app}"
DATA_DIR="${DATA_DIR:-/data}"
RESULTS_DIR="${RESULTS_DIR:-/results}"

mkdir -p "${DATA_DIR}/pcaps" "${DATA_DIR}/etc" "${DATA_DIR}/rules" "${RESULTS_DIR}"

if [[ ! -f "${DATA_DIR}/pcaps/incident.pcap" ]]; then
  echo "c5 setup-overlay: ${DATA_DIR}/pcaps/incident.pcap missing (overlay assets required)" >&2
  exit 1
fi

if [[ ! -f "${DATA_DIR}/etc/threshold.config" && -f "${WORKDIR_PATH}/threshold.config" ]]; then
  cp -a "${WORKDIR_PATH}/threshold.config" "${DATA_DIR}/etc/threshold.config"
fi

if [[ ! -f "${DATA_DIR}/rules/decoder-events.rules" && -f "${WORKDIR_PATH}/rules/decoder-events.rules" ]]; then
  cp -a "${WORKDIR_PATH}/rules/decoder-events.rules" "${DATA_DIR}/rules/decoder-events.rules"
fi

command -v tcpdump >/dev/null
command -v python3 >/dev/null
tcpdump -nn -r "${DATA_DIR}/pcaps/incident.pcap" -c 1 >/dev/null

echo "c5 setup-overlay: incident pcap ready"
exit 0
