#!/usr/bin/env python3
"""Verify PREFIX=/opt/redis72 TLS+jemalloc install and /results/build-report.json."""
from __future__ import annotations

import json
import os
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path

from redis_resp import Redis, to_str
from src_guard import assert_src_unmodified

PREFIX = Path("/opt/redis72")
BIN = PREFIX / "bin"
SERVER = BIN / "redis-server"
CLI = BIN / "redis-cli"
SENTINEL = BIN / "redis-sentinel"
REPORT = Path("/results/build-report.json")
MAKE_SETTINGS = Path("/app/src/.make-settings")
REQUIRED_BINS = [
    "redis-server",
    "redis-cli",
    "redis-benchmark",
    "redis-check-rdb",
    "redis-check-aof",
    "redis-sentinel",
]
KEY_ORDER = [
    "prefix",
    "tls",
    "allocator",
    "server",
    "cli",
    "sentinel",
    "make_settings_tls",
    "make_settings_malloc",
]
PROBE_PORT = 6390


def elf_needed(path: Path) -> list[str]:
    data = path.read_bytes()
    if data[:4] != b"\x7fELF":
        raise ValueError(f"{path} is not ELF")
    ei_class = data[4]
    ei_data = data[5]
    if ei_class != 2 or ei_data != 1:
        raise ValueError(f"{path} is not ELF64 little-endian")
    e_phoff = struct.unpack_from("<Q", data, 32)[0]
    e_phentsize = struct.unpack_from("<H", data, 54)[0]
    e_phnum = struct.unpack_from("<H", data, 56)[0]
    loads: list[tuple[int, int, int]] = []
    dyn_off = dyn_sz = None
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type = struct.unpack_from("<I", data, off)[0]
        p_offset, p_vaddr, _p_paddr, p_filesz = struct.unpack_from("<QQQQ", data, off + 8)
        if p_type == 1:  # PT_LOAD
            loads.append((p_vaddr, p_offset, p_filesz))
        elif p_type == 2:  # PT_DYNAMIC
            dyn_off, dyn_sz = p_offset, p_filesz
    if dyn_off is None:
        return []

    def vaddr_to_off(addr: int) -> int | None:
        for vaddr, offset, filesz in loads:
            if vaddr <= addr < vaddr + filesz:
                return offset + (addr - vaddr)
        return None

    needed_vals: list[int] = []
    strtab_addr = None
    pos = dyn_off
    end = dyn_off + dyn_sz
    while pos + 16 <= end:
        tag, val = struct.unpack_from("<QQ", data, pos)
        pos += 16
        if tag == 0:
            break
        if tag == 1:  # DT_NEEDED
            needed_vals.append(val)
        elif tag == 5:  # DT_STRTAB
            strtab_addr = val
    if strtab_addr is None:
        return []
    strtab_off = vaddr_to_off(strtab_addr)
    if strtab_off is None:
        return []
    names = []
    for rel in needed_vals:
        start = strtab_off + rel
        end_idx = data.find(b"\0", start)
        names.append(data[start:end_idx].decode("ascii", "replace"))
    return names


def parse_make_settings(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        out[key.strip()] = val.strip()
    return out


def load_report(errors: list[str]):
    if not REPORT.is_file():
        errors.append(f"missing {REPORT}")
        return None, []
    raw = REPORT.read_bytes()
    if not raw.endswith(b"\n"):
        errors.append(f"{REPORT} must be UTF-8 JSON with a trailing newline")
    orders: list[list[str]] = []

    def hook(pairs):
        orders.append([k for k, _ in pairs])
        return dict(pairs)

    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=hook)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"{REPORT} is not valid UTF-8 JSON: {exc}")
        return None, []
    if not isinstance(data, dict):
        errors.append("build-report.json must be a JSON object")
        return None, []
    top_order = orders[-1] if orders else []
    return data, top_order


def check_tls_missing_certs(errors: list[str]) -> None:
    log = Path("/tmp/verifier-tls-missing.log")
    try:
        proc = subprocess.run(
            [
                str(SERVER),
                "--tls-port",
                "6379",
                "--port",
                "0",
                "--bind",
                "127.0.0.1",
                "--protected-mode",
                "no",
                "--logfile",
                str(log),
                "--daemonize",
                "no",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        errors.append("redis-server --tls-port 6379 --port 0 hung instead of failing without certs")
        return
    combined = (proc.stdout or "") + (proc.stderr or "")
    if log.is_file():
        combined += log.read_text(encoding="utf-8", errors="replace")
    low = combined.lower()
    if "unrecognized option" in low or "unknown option" in low or "bad number of args" in low:
        errors.append(
            "redis-server treated --tls-port as an unknown option; TLS must be built-in, not missing"
        )
        return
    tls_missing = (
        "no tls-cert-file configured" in low
        or "failed to configure tls" in low
        or "tls-cert-file" in low
    )
    if proc.returncode == 0 or not tls_missing:
        errors.append(
            "starting redis-server --tls-port 6379 --port 0 with no cert paths must fail as a "
            f"TLS-enabled binary missing certificates; rc={proc.returncode} output={combined[-500]!r}"
        )


def probe_jemalloc(errors: list[str]) -> str | None:
    work = Path("/tmp/verifier-jemalloc")
    work.mkdir(parents=True, exist_ok=True)
    log = work / "server.log"
    proc = subprocess.Popen(
        [
            str(SERVER),
            "--port",
            str(PROBE_PORT),
            "--bind",
            "127.0.0.1",
            "--protected-mode",
            "no",
            "--daemonize",
            "no",
            "--dir",
            str(work),
            "--dbfilename",
            "probe.rdb",
            "--save",
            "",
            "--logfile",
            str(log),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    allocator = None
    try:
        client = None
        for _ in range(50):
            try:
                client = Redis("127.0.0.1", PROBE_PORT, timeout=1.0)
                break
            except OSError:
                if proc.poll() is not None:
                    extra = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
                    errors.append(
                        f"plaintext redis-server on 127.0.0.1:{PROBE_PORT} exited before INFO "
                        f"(rc={proc.returncode}) {extra[-300:]}"
                    )
                    return None
                time.sleep(0.1)
        if client is None:
            errors.append(f"could not connect to short-lived plaintext instance on {PROBE_PORT}")
            return None
        try:
            info = client.info("memory")
            allocator = info.get("mem_allocator", "")
            if not allocator.lower().startswith("jemalloc"):
                errors.append(
                    f"INFO memory mem_allocator is {allocator!r}, expected jemalloc"
                )
        except (RuntimeError, EOFError, OSError) as exc:
            errors.append(f"INFO memory on {PROBE_PORT} failed: {exc}")
        finally:
            try:
                client.execute("SHUTDOWN", "NOSAVE")
            except Exception:
                pass
            client.close()
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except OSError:
                proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except OSError:
                    proc.kill()
    return allocator


def main() -> int:
    errors: list[str] = []
    assert_src_unmodified(errors)

    for name in REQUIRED_BINS:
        path = BIN / name
        if not path.is_file():
            errors.append(f"missing install binary {path}")
        elif not os.access(path, os.X_OK):
            errors.append(f"{path} is not executable")

    if SERVER.is_file():
        try:
            needed = elf_needed(SERVER)
            if not any("libssl" in lib for lib in needed):
                errors.append(f"redis-server DT_NEEDED has no libssl (got {needed})")
        except ValueError as exc:
            errors.append(str(exc))
        check_tls_missing_certs(errors)
        probe_jemalloc(errors)
    if CLI.is_file():
        try:
            needed = elf_needed(CLI)
            if not any("libssl" in lib for lib in needed):
                errors.append(f"redis-cli DT_NEEDED has no libssl (got {needed})")
        except ValueError as exc:
            errors.append(str(exc))

    settings = parse_make_settings(MAKE_SETTINGS)
    build_tls = settings.get("BUILD_TLS", "")
    malloc = settings.get("MALLOC", "")
    if build_tls != "yes":
        errors.append(
            f"/app/src/.make-settings BUILD_TLS must be yes (built-in, not module), got {build_tls!r}"
        )
    if malloc != "jemalloc":
        errors.append(f"/app/src/.make-settings MALLOC must be jemalloc, got {malloc!r}")

    data, top_order = load_report(errors)
    if data is not None:
        if top_order != KEY_ORDER:
            errors.append(f"build-report.json key order must be {KEY_ORDER}, got {top_order}")
        expected_values = {
            "prefix": "/opt/redis72",
            "tls": "yes",
            "allocator": "jemalloc",
            "server": str(SERVER),
            "cli": str(CLI),
            "sentinel": str(SENTINEL),
            "make_settings_tls": build_tls or "yes",
            "make_settings_malloc": malloc or "jemalloc",
        }
        for key, val in expected_values.items():
            if data.get(key) != val:
                errors.append(f"build-report.json {key} must be {val!r}, got {data.get(key)!r}")

    for item in errors:
        print(item, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"verifier crashed: {exc}", file=sys.stderr)
        sys.exit(1)
