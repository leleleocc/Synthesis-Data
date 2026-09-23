#!/usr/bin/env python3
"""Pytest discriminator for a live non-root serve worker under the GPU watermark."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

REPORT = Path("/workspace/runtime_metrics.json")
ENTRY = Path("/usr/local/bin/vllm-nonroot-entrypoint.sh")
CONF = Path("/workspace/serve_runtime.conf")
BOUND_FILE = Path(__file__).resolve().parent / "fixtures" / "watermark_bound.txt"
REQUIRED = (
    "entrypoint",
    "gpu_memory_utilization",
    "process_uid",
    "pid",
    "listen_port",
    "ready",
)


def _fail(message: str) -> None:
    print(message)
    raise AssertionError(message)


def _pass(name: str) -> None:
    print(f"{name}: pass")


def _load_bound() -> float:
    if not BOUND_FILE.is_file():
        _fail("fixture: fail reason: missing watermark bound fixture")
    raw = BOUND_FILE.read_text(encoding="utf-8").strip()
    if not raw:
        _fail("fixture: fail reason: empty watermark bound fixture")
    return float(raw)


def _tcp_tables(pid: int) -> list[Path]:
    tables = [
        Path("/proc/net/tcp"),
        Path("/proc/net/tcp6"),
        Path(f"/proc/{pid}/net/tcp"),
        Path(f"/proc/{pid}/net/tcp6"),
    ]
    return [table for table in tables if table.is_file()]


def _port_is_listening(pid: int, port: int) -> bool:
    hex_port = f"{port:04X}"
    for table in _tcp_tables(pid):
        try:
            lines = table.read_text(encoding="utf-8", errors="replace").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            parts = line.split()
            if len(parts) < 4 or parts[3] != "0A":
                continue
            addr = parts[1].rsplit(":", 1)
            if len(addr) == 2 and addr[1].upper() == hex_port:
                return True
    return False


def test_runtime_metrics() -> None:
    bound = _load_bound()
    if not REPORT.is_file():
        _fail(f"normal case: fail reason: missing {REPORT}")
    raw = REPORT.read_text(encoding="utf-8")
    if not raw.strip():
        _fail("empty output: fail reason: report file is empty")
    if "GPU_MEMORY_UTILIZATION" in raw:
        _fail("copied input: fail reason: report looks like serve_runtime.conf, not runtime_metrics.json")
    try:
        report = json.loads(raw)
    except json.JSONDecodeError as exc:
        _fail(f"normal case: fail reason: invalid JSON: {exc}")
    if not isinstance(report, dict):
        _fail("normal case: fail reason: report is not a JSON object")

    missing = [key for key in REQUIRED if key not in report]
    if missing:
        _fail(f"normal case: fail reason: missing {missing}")
    _pass("schema required")

    entrypoint = report.get("entrypoint")
    if entrypoint != str(ENTRY):
        _fail(f"normal case: fail reason: entrypoint must be {ENTRY}, got {entrypoint!r}")
    _pass("entrypoint")

    util = report.get("gpu_memory_utilization")
    if not isinstance(util, (int, float)) or isinstance(util, bool):
        _fail("normal case: fail reason: gpu_memory_utilization missing or not numeric")
    if not (0 < float(util) <= bound):
        _fail(f"edge case: fail reason: gpu_memory_utilization={util} is not in (0, {bound}]")
    _pass("gpu memory watermark")

    uid = report.get("process_uid")
    if not isinstance(uid, int) or isinstance(uid, bool) or uid == 0:
        _fail(f"edge case: fail reason: process_uid={uid} must be a non-zero integer")
    _pass("process uid")

    pid = report.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1:
        _fail(f"edge case: fail reason: pid={pid} must be greater than 1")
    _pass("pid")

    port = report.get("listen_port")
    if not isinstance(port, int) or isinstance(port, bool) or not (1 <= port <= 65535):
        _fail(f"edge case: fail reason: listen_port={port} is not a TCP port")
    _pass("listen port")

    if report.get("ready") is not True:
        _fail("ready: fail reason: ready must be JSON true")
    _pass("ready flag")

    if uid == 0 and 0 < float(util) <= bound:
        _fail("coupled constraints: fail reason: watermark and uid drop must hold together")
    if uid != 0 and float(util) > bound:
        _fail("coupled constraints: fail reason: watermark and uid drop must hold together")
    _pass("coupled dump flags")

    proc = Path(f"/proc/{pid}")
    if not proc.is_dir():
        _fail(f"state check: fail reason: pid {pid} is not a live process")
    status = (proc / "status").read_text(encoding="utf-8", errors="replace")
    live_uid = None
    for line in status.splitlines():
        if line.startswith("Uid:"):
            live_uid = int(line.split()[1])
            break
    if live_uid is None:
        _fail(f"state check: fail reason: cannot read Uid for pid {pid}")
    if live_uid != uid:
        _fail(f"state check: fail reason: live uid {live_uid} does not match process_uid {uid}")
    if live_uid == 0:
        _fail("negative space: fail reason: live worker still runs as UID 0")
    _pass("live uid")

    if not _port_is_listening(pid, port):
        _fail(f"state check: fail reason: pid {pid} is not listening on TCP port {port}")
    _pass("live socket")

    if not ENTRY.is_file() or not os.access(ENTRY, os.X_OK):
        _fail(f"entrypoint binary: fail reason: missing executable {ENTRY}")
    launcher = ENTRY.read_text(encoding="utf-8", errors="replace")
    if re.search(r"exec\s+sudo", launcher):
        _fail("negative space: fail reason: launcher still re-asserts uid 0 via sudo")
    _pass("launcher identity")

    launcher_util = None
    for line in launcher.splitlines():
        if line.startswith("GPU_MEMORY_UTILIZATION="):
            launcher_util = line.split("=", 1)[1].strip().strip('"')
            break
    conf_util = None
    if CONF.is_file():
        for line in CONF.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("GPU_MEMORY_UTILIZATION="):
                conf_util = line.split("=", 1)[1].strip().strip('"')
                break
    effective = conf_util if conf_util else launcher_util
    if not effective:
        _fail("watermark source: fail reason: GPU_MEMORY_UTILIZATION not set on launcher or conf")
    if not (0 < float(effective) <= bound):
        _fail(f"edge case: fail reason: launcher/conf watermark {effective} is not in (0, {bound}]")
    if float(effective) != float(util):
        _fail(f"state check: fail reason: dump watermark {util} does not match launcher/conf {effective}")
    _pass("launcher watermark")

    cmdline_path = Path(f"/proc/{pid}/cmdline")
    cmdline = cmdline_path.read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace") if cmdline_path.is_file() else ""
    if not re.search(r"vllm|vllm-nonroot-entrypoint", cmdline):
        _fail(f"state check: fail reason: pid {pid} cmdline is not the serve worker: {cmdline or '<empty>'}")
    if re.search(
        r"--gpu-memory-utilization[= ]0?\.9[1-9]|--gpu-memory-utilization[= ]0?\.99|--gpu-memory-utilization[= ]1",
        cmdline,
    ):
        _fail(f"negative space: fail reason: live cmdline still requests a watermark above {bound}")
    _pass("live cmdline")
    print("error handling: pass")


if __name__ == "__main__":
    try:
        test_runtime_metrics()
    except AssertionError as exc:
        print(f"error handling: fail reason: {exc}")
        raise SystemExit(1)
    raise SystemExit(0)
