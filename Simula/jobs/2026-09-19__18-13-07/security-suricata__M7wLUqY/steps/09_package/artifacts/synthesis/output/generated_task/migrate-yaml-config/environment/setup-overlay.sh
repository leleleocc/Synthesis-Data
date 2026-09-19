#!/usr/bin/env bash
# Candidate c4: decoy partial yaml for migration; pkg-config stays available from base.
set -euo pipefail

WORKDIR_PATH="${WORKDIR_PATH:-/app}"
DATA_DIR="${DATA_DIR:-/data}"
RESULTS_DIR="${RESULTS_DIR:-/results}"
mkdir -p "${DATA_DIR}/etc" "${DATA_DIR}/rules" "${RESULTS_DIR}"

if [[ ! -f "${DATA_DIR}/etc/suricata.yaml.in" ]]; then
  if [[ -f "${WORKDIR_PATH}/suricata.yaml.in" ]]; then
    cp -a "${WORKDIR_PATH}/suricata.yaml.in" "${DATA_DIR}/etc/suricata.yaml.in"
  else
    echo "c4 setup-overlay: suricata.yaml.in missing" >&2
    exit 1
  fi
fi

DATA_DIR="${DATA_DIR}" python3 - <<'PY'
import os
from pathlib import Path
base = Path(os.environ["DATA_DIR"]) / "etc"
src = base / "suricata.yaml.in"
dst = base / "suricata.yaml.partial"
t = src.read_text(encoding="utf-8", errors="replace")
t = t.replace("@e_logdir@", "/var/log/suricata", 1)
t = t.replace("@PACKAGE_VERSION@", "PLACEHOLDER_VERSION", 1)
dst.write_text(t, encoding="utf-8")
assert "@" in dst.read_text(encoding="utf-8")
print("c4: decoy partial yaml written with remaining @ placeholders")
PY

command -v pkg-config >/dev/null
command -v python3 >/dev/null
pkg-config --exists libpcap
pkg-config --exists yaml-0.1

echo "c4 setup-overlay: migration decoy ready"
exit 0
