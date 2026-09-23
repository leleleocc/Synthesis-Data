#!/usr/bin/env python3
"""Behavior/state/result oracle for dual jemalloc/libc Redis builds."""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

EXPECTED_JSON_KEYS = [
    "jemalloc_allocator_prefix",
    "libc_allocator",
    "jemalloc_activedefrag",
    "libc_activedefrag_set_ok",
]
EXPECTED_JSON = {
    "jemalloc_allocator_prefix": "jemalloc",
    "libc_allocator": "libc",
    "jemalloc_activedefrag": "yes",
    "libc_activedefrag_set_ok": False,
}
JEMALLOC_CONF = {
    "bind": "127.0.0.1",
    "port": "6379",
    "protected-mode": "yes",
    "daemonize": "no",
    "dir": "/results/jemalloc-data",
    "pidfile": "/results/jemalloc.pid",
    "logfile": "/results/jemalloc.log",
    "appendonly": "no",
    "activedefrag": "yes",
    "active-defrag-ignore-bytes": "1048576",
    "active-defrag-threshold-lower": "10",
    "active-defrag-threshold-upper": "100",
}
LIBC_CONF = {
    "bind": "127.0.0.1",
    "port": "6380",
    "protected-mode": "yes",
    "daemonize": "no",
    "dir": "/results/libc-data",
    "pidfile": "/results/libc.pid",
    "logfile": "/results/libc.log",
    "appendonly": "no",
}
BINS = [
    Path("/results/bin/jemalloc/redis-server"),
    Path("/results/bin/jemalloc/redis-cli"),
    Path("/results/bin/libc/redis-server"),
    Path("/results/bin/libc/redis-cli"),
]


def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(1)


def is_elf_executable(path: Path) -> None:
    if not path.is_file():
        fail(f"missing binary {path}")
    with path.open("rb") as fh:
        magic = fh.read(4)
    if magic != b"\x7fELF":
        fail(f"{path} is not a real ELF executable (magic={magic!r})")
    if not os_access_exec(path):
        fail(f"{path} is not executable")


def os_access_exec(path: Path) -> bool:
    return os_mod_exec(path)


def os_mod_exec(path: Path) -> bool:
    import os

    return os.access(path, os.X_OK)


def encode_command(*parts: object) -> bytes:
    chunks = [f"*{len(parts)}\r\n".encode()]
    for part in parts:
        payload = part if isinstance(part, bytes) else str(part).encode()
        chunks.append(f"${len(payload)}\r\n".encode())
        chunks.append(payload)
        chunks.append(b"\r\n")
    return b"".join(chunks)


class RedisError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class Redis:
    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.buf = b""

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def _recv(self) -> None:
        chunk = self.sock.recv(4096)
        if not chunk:
            fail("redis connection closed")
        self.buf += chunk

    def _readline(self) -> bytes:
        while b"\r\n" not in self.buf:
            self._recv()
        line, self.buf = self.buf.split(b"\r\n", 1)
        return line

    def _readexact(self, n: int) -> bytes:
        while len(self.buf) < n:
            self._recv()
        data, self.buf = self.buf[:n], self.buf[n:]
        return data

    def _parse(self):
        line = self._readline()
        kind, rest = line[:1], line[1:]
        if kind == b"+":
            return rest.decode()
        if kind == b"-":
            raise RedisError(rest.decode())
        if kind == b":":
            return int(rest)
        if kind == b"$":
            n = int(rest)
            if n < 0:
                return None
            data = self._readexact(n)
            if self._readexact(2) != b"\r\n":
                fail("bad bulk terminator")
            return data.decode()
        if kind == b"*":
            n = int(rest)
            if n < 0:
                return None
            return [self._parse() for _ in range(n)]
        fail(f"unsupported redis reply {line!r}")

    def call(self, *parts: object):
        self.sock.sendall(encode_command(*parts))
        return self._parse()


def connect(port: int) -> Redis:
    try:
        sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    except OSError as exc:
        fail(f"cannot connect to 127.0.0.1:{port}: {exc}")
    sock.settimeout(5)
    return Redis(sock)


def parse_info(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, val = line.split(":", 1)
        out[key] = val
    return out


def config_get(conn: Redis, name: str) -> str:
    reply = conn.call("CONFIG", "GET", name)
    if not isinstance(reply, list) or len(reply) < 2:
        fail(f"CONFIG GET {name} returned {reply!r}")
    return str(reply[1])


def parse_conf(path: Path) -> dict[str, str]:
    if not path.is_file():
        fail(f"missing conf {path}")
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        key = parts[0].lower()
        val = parts[1].strip() if len(parts) > 1 else ""
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        out[key] = val
    return out


def require_conf(conf: dict[str, str], expect: dict[str, str], label: str) -> None:
    for key, val in expect.items():
        if key == "bind":
            if "127.0.0.1" not in (conf.get(key) or "").split():
                fail(f"{label}: bind must include 127.0.0.1, got {conf.get(key)!r}")
            continue
        if conf.get(key) != val:
            fail(f"{label}: expected {key}={val!r}, got {conf.get(key)!r}")
    if conf.get("save") not in ("", '""'):
        fail(f"{label}: save must be empty, got {conf.get('save')!r}")


def pid_running(pidfile: Path) -> None:
    if not pidfile.is_file():
        fail(f"missing pidfile {pidfile}")
    text = pidfile.read_text(encoding="utf-8", errors="replace").strip()
    if not text.isdigit():
        fail(f"bad pidfile {pidfile}: {text!r}")
    if not Path(f"/proc/{int(text)}").is_dir():
        fail(f"pid {text} from {pidfile} is not running")


def load_report(path: Path) -> None:
    if not path.is_file():
        fail(f"missing {path}")
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        fail(f"{path} has a UTF-8 BOM")
    if b"\r" in raw:
        fail(f"{path} is not Unix-newline JSON")
    if not raw.endswith(b"\n"):
        fail(f"{path} missing trailing newline")
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"{path} is not UTF-8 JSON: {exc}")
    if not isinstance(obj, dict):
        fail(f"{path} must be a JSON object")
    if list(obj.keys()) != EXPECTED_JSON_KEYS:
        fail(f"{path} keys {list(obj.keys())} != {EXPECTED_JSON_KEYS}")
    for key, expect in EXPECTED_JSON.items():
        got = obj[key]
        if type(got) is not type(expect) or got != expect:
            fail(f"{path}.{key}: expected {expect!r}, got {got!r}")


def cmdline_of(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
    except OSError:
        return ""


def exe_of(pid: int) -> str:
    try:
        return os_readlink(f"/proc/{pid}/exe")
    except OSError:
        return ""


def os_readlink(path: str) -> str:
    import os

    return os.readlink(path)


def main() -> None:
    for path in BINS:
        is_elf_executable(path)
    je_conf = parse_conf(Path("/results/jemalloc.conf"))
    libc_conf = parse_conf(Path("/results/libc.conf"))
    require_conf(je_conf, JEMALLOC_CONF, "jemalloc.conf")
    require_conf(libc_conf, LIBC_CONF, "libc.conf")
    if libc_conf.get("activedefrag") in ("yes", "1"):
        fail("libc.conf must not enable activedefrag")
    for d in (Path("/results/jemalloc-data"), Path("/results/libc-data")):
        if not d.is_dir():
            fail(f"missing dir {d}")
    pid_running(Path("/results/jemalloc.pid"))
    pid_running(Path("/results/libc.pid"))
    je_pid = int(Path("/results/jemalloc.pid").read_text().strip())
    libc_pid = int(Path("/results/libc.pid").read_text().strip())
    je_exe = exe_of(je_pid)
    libc_exe = exe_of(libc_pid)
    if "/results/bin/jemalloc/redis-server" not in je_exe and "jemalloc/redis-server" not in cmdline_of(je_pid):
        fail(f"jemalloc pid {je_pid} is not running /results/bin/jemalloc/redis-server (exe={je_exe!r})")
    if "/results/bin/libc/redis-server" not in libc_exe and "libc/redis-server" not in cmdline_of(libc_pid):
        fail(f"libc pid {libc_pid} is not running /results/bin/libc/redis-server (exe={libc_exe!r})")

    je = connect(6379)
    libc = connect(6380)
    try:
        if je.call("PING") != "PONG":
            fail("jemalloc PING failed")
        if libc.call("PING") != "PONG":
            fail("libc PING failed")
        je_mem = parse_info(je.call("INFO", "memory"))
        libc_mem = parse_info(libc.call("INFO", "memory"))
        alloc_je = je_mem.get("mem_allocator", "")
        alloc_libc = libc_mem.get("mem_allocator", "")
        if not alloc_je.startswith("jemalloc"):
            fail(f"jemalloc mem_allocator={alloc_je!r} does not start with jemalloc")
        if alloc_libc != "libc":
            fail(f"libc mem_allocator={alloc_libc!r}, expected libc")
        running = je_mem.get("active_defrag_running")
        if running is None or not str(running).lstrip("-").isdigit():
            fail(f"jemalloc INFO memory missing integer active_defrag_running ({running!r})")
        if config_get(je, "activedefrag") != "yes":
            fail("CONFIG GET activedefrag on jemalloc is not yes")
        if config_get(je, "active-defrag-ignore-bytes") != "1048576":
            fail("jemalloc active-defrag-ignore-bytes is not 1048576")
        if config_get(je, "active-defrag-threshold-lower") != "10":
            fail("jemalloc active-defrag-threshold-lower is not 10")
        if config_get(je, "active-defrag-threshold-upper") != "100":
            fail("jemalloc active-defrag-threshold-upper is not 100")
        try:
            libc.call("CONFIG", "SET", "activedefrag", "yes")
        except RedisError as exc:
            msg = exc.message
            if "Active defragmentation cannot be enabled" not in msg:
                fail(f"libc CONFIG SET activedefrag yes error is not Redis's allocator error: {msg!r}")
            if "Jemalloc" not in msg and "jemalloc" not in msg:
                fail(f"libc activedefrag error should mention Jemalloc: {msg!r}")
        else:
            fail("CONFIG SET activedefrag yes on libc must fail")
    finally:
        je.close()
        libc.close()
    load_report(Path("/results/alloc-report.json"))
    raise SystemExit(0)


if __name__ == "__main__":
    main()
