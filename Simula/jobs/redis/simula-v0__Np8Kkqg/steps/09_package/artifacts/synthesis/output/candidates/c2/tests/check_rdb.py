#!/usr/bin/env python3
"""Verify RDB checksum repair, audit JSON, and redis-check-rdb help capture."""
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

SRC_RDB_C_SHA = "0a8253be63e36b17c54359fed31f1609623f903483df97270f91245f34a6c709"
SRC_RDB_H_SHA = "40acb977b34c48aedf3c7eb60e3712bf999300b308620dd5f3ade4f977065188"
SRC_REDIS_CONF_SHA = "319286fcdc3d98e9c248d9730f28c3e5bae106a58173f64302039e15507dca14"

SERVER = "/app/src/redis-server"
CHECK_RDB = "/app/src/redis-check-rdb"
AUDIT = "/results/rdb-audit.json"
HELP_FILE = "/results/rdb-check-help.txt"
EXPECTED_AUDIT = "/tests/expected_rdb_audit.json"
PORT = 17381
KEY_ORDER = [
    "rdb_version",
    "magic_prefix",
    "eof_opcode",
    "aux_opcode",
    "selectdb_opcode",
    "resizedb_opcode",
    "expiretime_ms_opcode",
    "checksum_min_rdbver",
    "zero_checksum_skips_validation",
    "checksum_uses_rio_update",
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


def check_unmodified_src() -> None:
    checks = {
        "/src/src/rdb.c": SRC_RDB_C_SHA,
        "/src/src/rdb.h": SRC_RDB_H_SHA,
        "/src/redis.conf": SRC_REDIS_CONF_SHA,
    }
    for path, expected in checks.items():
        if not Path(path).is_file():
            fail(f"missing sealed file {path}")
        if sha256(path) != expected:
            fail(f"modified {path} (do not modify /src)")
    if not data_dir_is_pristine():
        fail("/data must remain unmodified")


def check_binaries() -> None:
    for path in (SERVER, CHECK_RDB):
        if not Path(path).is_file():
            fail(f"missing {path}")
        if not is_elf(path):
            fail(f"{path} is not an ELF executable")
        if not os.access(path, os.X_OK):
            fail(f"{path} is not executable")


def check_rdb_source() -> None:
    text = Path("/app/src/rdb.c").read_text(encoding="utf-8", errors="replace")
    if "rdb->update_cksum = rioGenericUpdateChecksum;" not in text:
        fail("save path does not install rioGenericUpdateChecksum")
    if "rioGenericUpdateChecksum(r, buf, len);" not in text:
        fail("load path does not feed CRC64 through rioGenericUpdateChecksum")
    if "rdb->update_cksum = NULL;" in text:
        fail("save path still clears the rio checksum callback")
    if "if (server.rdb_checksum)\n        (void)buf;" in text:
        fail("load path still skips the rio checksum callback")


def check_audit_json() -> None:
    path = Path(AUDIT)
    if not path.is_file():
        fail("missing /results/rdb-audit.json")
    raw = path.read_bytes()
    if not raw.endswith(b"\n"):
        fail("rdb-audit.json must end with a newline")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"rdb-audit.json is not UTF-8: {exc}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        fail(f"rdb-audit.json is not valid JSON: {exc}")
    if not isinstance(data, dict):
        fail("rdb-audit.json must be an object")
    if list(data.keys()) != KEY_ORDER:
        fail(f"rdb-audit.json keys {list(data.keys())} != {KEY_ORDER}")

    expected = json.loads(Path(EXPECTED_AUDIT).read_text(encoding="utf-8"))
    type_map = {
        "rdb_version": int,
        "magic_prefix": str,
        "eof_opcode": int,
        "aux_opcode": int,
        "selectdb_opcode": int,
        "resizedb_opcode": int,
        "expiretime_ms_opcode": int,
        "checksum_min_rdbver": int,
        "zero_checksum_skips_validation": bool,
        "checksum_uses_rio_update": bool,
    }
    for key, typ in type_map.items():
        value = data[key]
        if typ is int and (not isinstance(value, int) or isinstance(value, bool)):
            fail(f"{key} has type {type(value).__name__}, expected int")
        elif typ is not int and not isinstance(value, typ):
            fail(f"{key} has type {type(value).__name__}, expected {typ.__name__}")
        if data[key] != expected[key]:
            fail(f"{key}: got {data[key]!r}, expected restored contract {expected[key]!r}")
    if data["checksum_uses_rio_update"] is not True:
        fail("checksum_uses_rio_update must report the restored rio callback path")


def _normalize_help(blob: bytes) -> str:
    text = blob.decode("utf-8", "replace")
    return re.sub(r"Usage: \S+ <rdb-file-name>", "Usage: BINARY <rdb-file-name>", text)


def check_help_capture() -> None:
    path = Path(HELP_FILE)
    if not path.is_file():
        fail("missing /results/rdb-check-help.txt")
    captured = path.read_bytes()
    if not captured:
        fail("rdb-check-help.txt is empty")
    if b"Usage:" not in captured or b"<rdb-file-name>" not in captured:
        fail("rdb-check-help.txt does not contain the redis-check-rdb usage line")
    proc = subprocess.run(
        [CHECK_RDB],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    split = subprocess.run(
        [CHECK_RDB],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    expected_blobs = (
        proc.stdout,
        split.stdout + split.stderr,
        split.stderr + split.stdout,
    )
    captured_n = _normalize_help(captured)
    if not any(_normalize_help(blob) == captured_n for blob in expected_blobs):
        fail("rdb-check-help.txt does not match redis-check-rdb with no arguments")


def check_saved_checksum() -> None:
    leftover = named_pids(b"redis-server", b"redis-check-rdb")
    if leftover:
        fail(f"redis-server or redis-check-rdb still running before probe: {leftover}")

    datadir = Path("/tmp/c2-rdb")
    datadir.mkdir(parents=True, exist_ok=True)
    dump = datadir / "dump.rdb"
    proc = subprocess.Popen(
        [
            SERVER,
            "--port",
            str(PORT),
            "--bind",
            "127.0.0.1",
            "--protected-mode",
            "no",
            "--dir",
            str(datadir),
            "--dbfilename",
            "dump.rdb",
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
        client.cmd("SET", "c2:checksum", "payload")
        client.cmd("SAVE")
        client.cmd("SHUTDOWN", "NOSAVE")
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            fail("redis-server did not exit after SHUTDOWN")
    finally:
        if client is not None:
            client.close()
        stop_proc(proc)

    if not dump.is_file() or dump.stat().st_size < 17:
        fail("SAVE did not produce an RDB file")
    blob = dump.read_bytes()
    if blob[:5] != b"REDIS":
        fail("RDB magic_prefix is not REDIS")
    cksum = blob[-8:]
    if cksum == b"\x00" * 8:
        fail("RDB trailing CRC64 is zero; checksum callback was not restored")


def main() -> None:
    check_unmodified_src()
    check_binaries()
    check_rdb_source()
    check_audit_json()
    check_help_capture()
    check_saved_checksum()
    leftover = named_pids(b"redis-server", b"redis-check-rdb")
    if leftover:
        fail(f"redis-server or redis-check-rdb still running: {leftover}")


if __name__ == "__main__":
    main()
    print("OK")
