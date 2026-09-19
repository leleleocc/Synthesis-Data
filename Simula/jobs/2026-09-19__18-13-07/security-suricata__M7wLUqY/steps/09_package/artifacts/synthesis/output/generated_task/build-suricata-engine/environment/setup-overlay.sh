#!/usr/bin/env bash
# Candidate c2: mild onboarding friction in the top-level automake wiring.
set -euo pipefail

WORKDIR_PATH="${WORKDIR_PATH:-/app}"
DATA_DIR="${DATA_DIR:-/data}"
RESULTS_DIR="${RESULTS_DIR:-/results}"
mkdir -p "${DATA_DIR}" "${RESULTS_DIR}"

if [[ -f "${WORKDIR_PATH}/Makefile.am" ]]; then
  WORKDIR_PATH="${WORKDIR_PATH}" python3 - <<'PY'
import os, re
from pathlib import Path
p = Path(os.environ["WORKDIR_PATH"]) / "Makefile.am"
text = p.read_text(encoding="utf-8", errors="replace")
anchor = "SUBDIRS = rust src plugins qa rules doc etc python ebpf"
if anchor in text:
    text = text.replace(
        anchor,
        "SUBDIRS = rust missing-onboarding-dir plugins qa rules doc etc python ebpf",
        1,
    )
else:
    m = re.search(r"^SUBDIRS\s*=\s*.*$", text, re.M)
    if not m:
        raise SystemExit("c2 overlay: SUBDIRS line missing")
    old = m.group(0)
    new = old.replace(" src ", " missing-onboarding-dir ")
    if new == old:
        new = re.sub(r"\bsrc\b", "missing-onboarding-dir", old, count=1)
    text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")
print("c2: Makefile.am SUBDIRS damaged (src removed / fake dir)")
PY
fi

rm -f "${WORKDIR_PATH}/configure" "${WORKDIR_PATH}/Makefile" || true
rm -f "${WORKDIR_PATH}/src/suricata" || true

mkdir -p "${DATA_DIR}/etc"
cat > "${DATA_DIR}/etc/onboarding-hint.txt" <<'EOF'
Suricata onboarding: regenerate autotools, configure with a local prefix, build src/suricata.
EOF

echo "c2 setup-overlay: planted Makefile.am onboarding defect"
exit 0
