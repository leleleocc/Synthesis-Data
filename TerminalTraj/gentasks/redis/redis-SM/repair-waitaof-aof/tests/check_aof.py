#!/usr/bin/env python3
"""Verify the repaired AOF replica-offset handoff and WAITAOF behavior."""
from __future__ import annotations

import hashlib
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

SRC_AOF_SHA = "b84e0113adef2fe105c717d841a1147da6a0d61bd546fc10300bbedcfd194bd0"
SRC_REDIS_CONF_SHA = "319286fcdc3d98e9c248d9730f28c3e5bae106a58173f64302039e15507dca14"
SRC_ZMALLOC_C_SHA = "c01552d15fa7f2591ad6d770582b35cfe83b1a62b715ab8e99b8abceb021a11c"
SRC_ZMALLOC_H_SHA = "911a3c1ec25125fddb0f1978ae73e83b9008511e55034933ee9634f8d222f28b"

BINARY = "/app/src/redis-server"
AOF_APP = "/app/src/aof.c"
MASTER_PORT = 17379
REPLICA_PORT = 17380


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


def redis_pids() -> list[int]:
    found: list[int] = []
    proc = Path("/proc")
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        text = cmdline.replace(b"\x00", b" ")
        if b"redis-server" in text:
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
        if not line:
            fail("empty redis reply")
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
            pong = client.cmd("PING")
            if pong in (b"PONG", "PONG"):
                return client
            client.close()
        except (OSError, SystemExit, RuntimeError) as exc:
            last = exc
            time.sleep(0.1)
    fail(f"redis on port {port} did not become ready: {last}")


def start_server(port: int, datadir: str, extra: list[str]) -> subprocess.Popen:
    Path(datadir).mkdir(parents=True, exist_ok=True)
    cmd = [
        BINARY,
        "--port",
        str(port),
        "--bind",
        "127.0.0.1",
        "--protected-mode",
        "no",
        "--dir",
        datadir,
        "--dbfilename",
        "dump.rdb",
        "--appenddirname",
        "appendonlydir",
        "--save",
        "",
        "--daemonize",
        "no",
        "--logfile",
        str(Path(datadir) / "server.log"),
        "--appendonly",
        "yes",
        "--auto-aof-rewrite-percentage",
        "0",
    ] + extra
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd="/tmp",
    )
    return proc


def info_map(client: Redis, section: str) -> dict[str, str]:
    raw = client.cmd("INFO", section)
    if isinstance(raw, bytes):
        text = raw.decode("utf-8", "replace")
    else:
        text = str(raw)
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        out[key] = value.strip()
    return out


def wait_aof_ready(client: Redis, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        pers = info_map(client, "persistence")
        if (
            pers.get("aof_enabled") == "1"
            and pers.get("aof_rewrite_in_progress") == "0"
            and pers.get("aof_rewrite_scheduled", "0") == "0"
            and pers.get("aof_last_bgrewrite_status") == "ok"
        ):
            return
        time.sleep(0.1)
    fail("AOF did not become ready")


def wait_replica_online(master: Redis, replica: Redis, timeout: float = 25.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        repl = info_map(master, "replication")
        rinfo = info_map(replica, "replication")
        if repl.get("connected_slaves") == "1" and rinfo.get("master_link_status") == "up":
            return
        time.sleep(0.1)
    fail("replica did not connect")


def decode_int_list(reply) -> list[int]:
    if not isinstance(reply, list) or len(reply) != 2:
        fail(f"WAITAOF expected 2-element array, got {reply!r}")
    out = []
    for item in reply:
        if isinstance(item, int):
            out.append(item)
        elif isinstance(item, bytes):
            out.append(int(item))
        else:
            out.append(int(item))
    return out


def stop_proc(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def check_source_repair() -> None:
    if not Path(AOF_APP).is_file():
        fail("missing /app/src/aof.c")
    text = Path(AOF_APP).read_text(encoding="utf-8", errors="replace")
    if "bioCreateFsyncJob(fd, server.master_repl_offset, 1);" not in text:
        fail("BIO fsync job does not pass master_repl_offset")
    if "bioCreateCloseAofJob(fd, server.master_repl_offset, 1);" not in text:
        fail("BIO close-AOF job does not pass master_repl_offset")
    pending = text.count(
        "atomicSet(server.fsynced_reploff_pending, server.master_repl_offset);"
    )
    if pending < 2:
        fail(
            "always-fsync and AOF-rewrite paths must publish "
            f"master_repl_offset; found {pending} site(s)"
        )
    if "bioCreateFsyncJob(fd, 0, 1);" in text:
        fail("background fsync job still drops the replica offset")
    if "bioCreateCloseAofJob(fd, 0, 1);" in text:
        fail("background close-AOF job still drops the replica offset")


def check_unmodified_src() -> None:
    checks = {
        "/src/src/aof.c": SRC_AOF_SHA,
        "/src/redis.conf": SRC_REDIS_CONF_SHA,
        "/src/src/zmalloc.c": SRC_ZMALLOC_C_SHA,
        "/src/src/zmalloc.h": SRC_ZMALLOC_H_SHA,
    }
    for path, expected in checks.items():
        if not Path(path).is_file():
            fail(f"missing sealed file {path}")
        actual = sha256(path)
        if actual != expected:
            fail(f"modified {path} (do not modify /src)")
    if not data_dir_is_pristine():
        fail("/data must remain unmodified")


def check_binary() -> None:
    if not Path(BINARY).is_file():
        fail("missing /app/src/redis-server")
    if not is_elf(BINARY):
        fail("/app/src/redis-server is not an ELF executable")
    if not os.access(BINARY, os.X_OK):
        fail("/app/src/redis-server is not executable")


def main() -> None:
    check_unmodified_src()
    check_source_repair()
    check_binary()

    master_proc = None
    replica_proc = None
    master = None
    replica = None
    try:
        master_proc = start_server(
            MASTER_PORT,
            "/tmp/c1-master",
            ["--appendfsync", "always"],
        )
        master = wait_port(MASTER_PORT)
        wait_aof_ready(master)

        master.cmd("CONFIG", "SET", "appendfsync", "always")
        master.cmd("INCR", "c1:always")
        always_reply = decode_int_list(master.cmd("WAITAOF", 1, 0, 1000))
        if always_reply != [1, 0]:
            fail(f"WAITAOF local with appendfsync always returned {always_reply}")

        master.cmd("CONFIG", "SET", "appendfsync", "no")
        master.cmd("INCR", "c1:no")
        no_reply = decode_int_list(master.cmd("WAITAOF", 1, 0, 80))
        if no_reply[0] != 0:
            fail(f"WAITAOF local with appendfsync no acknowledged too early: {no_reply}")

        master.cmd("CONFIG", "SET", "appendfsync", "everysec")
        master.cmd("INCR", "c1:everysec")
        every_reply = decode_int_list(master.cmd("WAITAOF", 1, 0, 4000))
        if every_reply != [1, 0]:
            fail(f"WAITAOF local with appendfsync everysec returned {every_reply}")

        master.cmd("CONFIG", "SET", "appendfsync", "always")
        master.cmd("BGREWRITEAOF")
        wait_aof_ready(master)
        master.cmd("INCR", "c1:rewrite")
        rewrite_reply = decode_int_list(master.cmd("WAITAOF", 1, 0, 1000))
        if rewrite_reply != [1, 0]:
            fail(f"WAITAOF local after AOF rewrite returned {rewrite_reply}")

        replica_proc = start_server(
            REPLICA_PORT,
            "/tmp/c1-replica",
            ["--appendfsync", "always", "--replicaof", "127.0.0.1", str(MASTER_PORT)],
        )
        replica = wait_port(REPLICA_PORT)
        wait_aof_ready(replica)
        wait_replica_online(master, replica)
        replica.cmd("CONFIG", "SET", "appendfsync", "always")
        master.cmd("INCR", "c1:replica")
        both = decode_int_list(master.cmd("WAITAOF", 1, 1, 10000))
        if both != [1, 1]:
            fail(f"WAITAOF local+replica after fsync-policy changes returned {both}")
    finally:
        for client in (replica, master):
            if client is None:
                continue
            try:
                client.cmd("SHUTDOWN", "NOSAVE")
            except Exception:
                pass
            client.close()
        stop_proc(replica_proc)
        stop_proc(master_proc)

    leftover = redis_pids()
    if leftover:
        fail(f"redis-server still running: {leftover}")


if __name__ == "__main__":
    main()
    print("OK")
