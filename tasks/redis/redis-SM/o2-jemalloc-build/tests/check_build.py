#!/usr/bin/env python3
"""Verify -O2/frame-pointer Makefile migration and jemalloc runtime invariant."""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

SRC_MAKEFILE_SHA = "64cba1862b07d90d439f111ac18bfb001e8949612e938bdefc23cd57382cc167"
ZMALLOC_C_SHA = "c01552d15fa7f2591ad6d770582b35cfe83b1a62b715ab8e99b8abceb021a11c"
ZMALLOC_H_SHA = "911a3c1ec25125fddb0f1978ae73e83b9008511e55034933ee9634f8d222f28b"

BINARY = "/app/src/redis-server"
APP_MAKEFILE = "/app/src/Makefile"
AUDIT = "/results/build-report.json"
PORT = 17382
KEY_ORDER = [
    "optimization",
    "frame_pointer_flag",
    "malloc",
    "use_jemalloc_macro",
    "binary",
]


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_elf(path: str) -> bool:
    with open(path, "rb") as handle:
        return handle.read(4) == b"\x7fELF"


def data_dir_is_pristine() -> bool:
    root = Path("/data")
    if not root.is_dir():
        return False
    return next(root.iterdir(), None) is None


def named_pids(*needles: bytes) -> list[int]:
    found: list[int] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        text = cmdline.replace(b"\x00", b" ")
        if any(needle in text for needle in needles):
            found.append(int(entry.name))
    return found


class Redis:
    def __init__(self, port: int, timeout: float = 5.0) -> None:
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        self.sock.settimeout(timeout)
        self.buf = b""

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def _recv(self) -> bytes:
        chunk = self.sock.recv(65536)
        if not chunk:
            raise ConnectionError("redis connection closed")
        return chunk

    def _readline(self) -> bytes:
        while b"\r\n" not in self.buf:
            self.buf += self._recv()
        line, self.buf = self.buf.split(b"\r\n", 1)
        return line

    def _read(self):
        line = self._readline()
        kind = line[:1]
        if kind == b"+":
            return line[1:].decode("utf-8", "replace")
        if kind == b"-":
            return RuntimeError(line[1:].decode("utf-8", "replace"))
        if kind == b":":
            return int(line[1:])
        if kind == b"$":
            n = int(line[1:])
            if n < 0:
                return None
            while len(self.buf) < n + 2:
                self.buf += self._recv()
            data = self.buf[:n]
            self.buf = self.buf[n + 2 :]
            return data
        if kind == b"*":
            n = int(line[1:])
            if n < 0:
                return None
            return [self._read() for _ in range(n)]
        fail(f"unsupported redis reply {line!r}")

    def cmd(self, *args):
        parts = []
        for arg in args:
            if isinstance(arg, int):
                raw = str(arg).encode()
            elif isinstance(arg, bytes):
                raw = arg
            else:
                raw = str(arg).encode()
            parts.append(raw)
        payload = f"*{len(parts)}\r\n".encode()
        for raw in parts:
            payload += f"${len(raw)}\r\n".encode() + raw + b"\r\n"
        self.sock.sendall(payload)
        try:
            reply = self._read()
        except (ConnectionError, OSError, TimeoutError):
            if args and str(args[0]).upper() == "SHUTDOWN":
                return "OK"
            raise
        if isinstance(reply, RuntimeError):
            if args and str(args[0]).upper() == "SHUTDOWN":
                return "OK"
            raise reply
        return reply


def wait_port(port: int, timeout: float = 15.0) -> Redis:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            client = Redis(port)
            if client.cmd("PING") in (b"PONG", "PONG"):
                return client
            client.close()
        except (OSError, SystemExit, RuntimeError) as exc:
            last = exc
            time.sleep(0.1)
    fail(f"redis on port {port} did not become ready: {last}")


def stop_proc(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def uncommented_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def check_unmodified() -> None:
    if sha256("/src/src/Makefile") != SRC_MAKEFILE_SHA:
        fail("modified /src/src/Makefile (do not modify /src)")
    for path, expected in (
        ("/src/src/zmalloc.c", ZMALLOC_C_SHA),
        ("/src/src/zmalloc.h", ZMALLOC_H_SHA),
        ("/app/src/zmalloc.c", ZMALLOC_C_SHA),
        ("/app/src/zmalloc.h", ZMALLOC_H_SHA),
    ):
        if not Path(path).is_file():
            fail(f"missing {path}")
        if sha256(path) != expected:
            fail(f"{path} allocator selection was modified")
    if not data_dir_is_pristine():
        fail("/data must remain unmodified")


def check_makefile() -> None:
    text = Path(APP_MAKEFILE).read_text(encoding="utf-8", errors="replace")
    lines = uncommented_lines(text)
    default_opt = [ln for ln in lines if re.match(r"^OPTIMIZATION\s*\?*=", ln)]
    if not default_opt:
        fail("Makefile is missing a default OPTIMIZATION assignment")
    if not re.search(r"^OPTIMIZATION\s*\?*=\s*-O2\s*$", default_opt[0]):
        fail(f"default OPTIMIZATION is not -O2: {default_opt[0]!r}")

    redis_fp = [
        ln
        for ln in lines
        if "fno-omit-frame-pointer" in ln and "REDIS_CFLAGS" in ln
    ]
    if not redis_fp:
        fail("-fno-omit-frame-pointer is not on the REDIS_CFLAGS channel")

    stock = Path("/src/src/Makefile").read_text(encoding="utf-8", errors="replace")
    stock_cflags_fp = {
        ln
        for ln in uncommented_lines(stock)
        if "fno-omit-frame-pointer" in ln and re.search(r"(^|\s)CFLAGS\s*\+", ln)
    }
    agent_cflags_fp = [
        ln
        for ln in lines
        if "fno-omit-frame-pointer" in ln
        and re.search(r"(^|\s)CFLAGS\s*\+", ln)
        and "REDIS_CFLAGS" not in ln
        and ln not in stock_cflags_fp
    ]
    if agent_cflags_fp:
        fail("frame-pointer flag was forced into CFLAGS (dependency builds)")

    joined = "\n".join(lines)
    if re.search(r"^USE_JEMALLOC\s*\??=\s*no\s*$", joined, re.M):
        fail("Makefile forces USE_JEMALLOC=no")
    if re.search(r"^SANITIZER\s*\??=", joined, re.M):
        fail("Makefile enables SANITIZER")
    if re.search(r"^MALLOC\s*\??=\s*libc\s*$", joined, re.M):
        # Stock file sets MALLOC=libc then overrides to jemalloc on Linux.
        # Fail only if the Linux override was removed.
        if not re.search(r"MALLOC\s*=\s*jemalloc", joined):
            fail("Makefile selects libc instead of jemalloc")

    settings = Path("/app/src/.make-settings")
    if settings.is_file():
        st = settings.read_text(encoding="utf-8", errors="replace")
        if re.search(r"^MALLOC=libc$", st, re.M) and "MALLOC=jemalloc" not in st:
            fail(".make-settings selected libc")
        if re.search(r"^SANITIZER=", st, re.M):
            fail(".make-settings enables SANITIZER")
        if "USE_JEMALLOC=no" in st:
            fail(".make-settings sets USE_JEMALLOC=no")
        if re.search(r"^OPT=-O3$", st, re.M):
            fail(".make-settings still records OPT=-O3")


def check_report() -> dict:
    path = Path(AUDIT)
    if not path.is_file():
        fail("missing /results/build-report.json")
    raw = path.read_bytes()
    if not raw.endswith(b"\n"):
        fail("build-report.json must end with a newline")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"build-report.json is not UTF-8: {exc}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        fail(f"build-report.json is not valid JSON: {exc}")
    if not isinstance(data, dict):
        fail("build-report.json must be an object")
    if list(data.keys()) != KEY_ORDER:
        fail(f"build-report.json keys {list(data.keys())} != {KEY_ORDER}")
    if not isinstance(data["optimization"], str) or data["optimization"] != "-O2":
        fail(f"optimization must be '-O2', got {data['optimization']!r}")
    if data["frame_pointer_flag"] != "-fno-omit-frame-pointer":
        fail(f"frame_pointer_flag must be '-fno-omit-frame-pointer', got {data['frame_pointer_flag']!r}")
    if data["malloc"] != "jemalloc":
        fail(f"malloc must be jemalloc on this Linux host, got {data['malloc']!r}")
    if data["use_jemalloc_macro"] is not True:
        fail("use_jemalloc_macro must be true")
    if data["binary"] != BINARY:
        fail(f"binary must be {BINARY}, got {data['binary']!r}")
    return data


def check_binary() -> None:
    if not Path(BINARY).is_file():
        fail("missing /app/src/redis-server")
    if not is_elf(BINARY):
        fail("/app/src/redis-server is not an ELF executable")
    if not os.access(BINARY, os.X_OK):
        fail("/app/src/redis-server is not executable")


def check_runtime() -> None:
    leftover = named_pids(b"redis-server")
    if leftover:
        fail(f"redis-server still running before probe: {leftover}")
    datadir = Path("/tmp/c3-build")
    datadir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [
            BINARY,
            "--port",
            str(PORT),
            "--bind",
            "127.0.0.1",
            "--protected-mode",
            "no",
            "--dir",
            str(datadir),
            "--save",
            "",
            "--appendonly",
            "no",
            "--daemonize",
            "no",
            "--logfile",
            str(datadir / "server.log"),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd="/tmp",
    )
    client = None
    try:
        client = wait_port(PORT)
        raw = client.cmd("INFO", "memory")
        text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
        allocator = None
        for line in text.splitlines():
            if line.startswith("mem_allocator:"):
                allocator = line.split(":", 1)[1].strip()
                break
        if allocator is None:
            fail("INFO memory did not report mem_allocator")
        if "jemalloc" not in allocator:
            fail(f"mem_allocator is {allocator!r}, expected jemalloc")
        client.cmd("SHUTDOWN", "NOSAVE")
        try:
            rc = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            fail("redis-server did not exit cleanly on SHUTDOWN")
        if rc not in (0, None):
            # Redis SHUTDOWN exits 0; treat other codes as unclean.
            if rc != 0:
                fail(f"redis-server SHUTDOWN exit status {rc}")
    finally:
        if client is not None:
            client.close()
        stop_proc(proc)
    leftover = named_pids(b"redis-server")
    if leftover:
        fail(f"redis-server still running: {leftover}")


def main() -> None:
    check_unmodified()
    check_makefile()
    check_report()
    check_binary()
    check_runtime()


if __name__ == "__main__":
    main()
    print("OK")
