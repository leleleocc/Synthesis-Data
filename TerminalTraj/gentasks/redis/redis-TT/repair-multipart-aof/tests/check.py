#!/usr/bin/env python3
"""Behavior/state/result oracle for multi-part AOF recovery."""
from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

EXPECTED_JSON_KEYS = [
    "check_aof_ok",
    "role",
    "aof_enabled",
    "ticket",
    "owner",
    "meta_host",
]
EXPECTED_JSON = {
    "check_aof_ok": True,
    "role": "master",
    "aof_enabled": 1,
    "ticket": "AOF-7721",
    "owner": "ops-oncall",
    "meta_host": "cache-a",
}
DATA_SHA256 = {
    "appendonlydir/appendonly.aof.1.base.aof": "ce56842ff7992eb29218cd01bb6403db638df43bbfc0f090323b84c6b0a6ad0c",
    "appendonlydir/appendonly.aof.1.incr.aof": "c1af67cd0f75cbd9c7ba3325f9db8256024b1b94cf5d2448f9d12c02c6e51d2c",
    "appendonlydir/appendonly.aof.2.incr.aof": "bdf610ab361ff75d91a02b5d05bdd93db8b08d7c7ea14c14895158e97cebb559",
    "appendonlydir/appendonly.aof.9.incr.aof": "cc0faeaff5ab68ffe08fded609536e8083011a912710b0a93f588710a9719b0c",
    "appendonlydir/appendonly.aof.manifest": "58ecbde1696941c5b804909dc61c35a4f0c118948979972d10379d0a9a105af6",
    "appendonly.aof": "ce56842ff7992eb29218cd01bb6403db638df43bbfc0f090323b84c6b0a6ad0c",
}
CONF_EXPECT = {
    "bind": "127.0.0.1",
    "port": "6379",
    "protected-mode": "yes",
    "daemonize": "no",
    "dir": "/results/recovered",
    "appendonly": "yes",
    "appendfilename": "appendonly.aof",
    "appenddirname": "appendonlydir",
    "aof-load-truncated": "yes",
    "appendfsync": "no",
    "pidfile": "/results/recovered/redis.pid",
    "logfile": "/results/recovered/redis.log",
}
MANIFEST = Path("/results/recovered/appendonlydir/appendonly.aof.manifest")
CHECK_AOF = Path("/app/src/redis-check-aof")
SERVER = Path("/app/src/redis-server")


def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(1)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def is_elf(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(4) == b"\x7fELF"
    except OSError:
        return False


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


def connect(port: int = 6379) -> Redis:
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


def pid_running(pidfile: Path) -> None:
    if not pidfile.is_file():
        fail(f"missing pidfile {pidfile}")
    text = pidfile.read_text(encoding="utf-8", errors="replace").strip()
    if not text.isdigit():
        fail(f"bad pidfile {pidfile}: {text!r}")
    pid = int(text)
    if not Path(f"/proc/{pid}").is_dir():
        fail(f"pid {pid} from {pidfile} is not running")


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
            fail(f"{path}.{key}: expected {expect!r} ({type(expect).__name__}), got {got!r}")


def assert_data_frozen() -> None:
    root = Path("/data/aof-incident")
    if not root.is_dir():
        fail("/data/aof-incident missing")
    for rel, digest in DATA_SHA256.items():
        path = root / rel
        if not path.is_file():
            fail(f"/data fixture missing: {path}")
        got = sha256_file(path)
        if got != digest:
            fail(f"{path} was modified ({got})")


def run_check_aof() -> None:
    if not is_elf(CHECK_AOF):
        fail(f"{CHECK_AOF} is not a real ELF redis-check-aof")
    if not MANIFEST.is_file():
        fail(f"missing recovered manifest {MANIFEST}")
    proc = subprocess.run(
        [str(CHECK_AOF), str(MANIFEST)],
        capture_output=True,
        timeout=30,
        check=False,
    )
    text = ((proc.stdout or b"") + (proc.stderr or b"")).decode("utf-8", "replace")
    if proc.returncode != 0:
        fail(f"redis-check-aof rc={proc.returncode}: {text}")
    if "All AOF files and manifest are valid" not in text:
        fail(f"redis-check-aof did not report multi-part validity: {text}")


def assert_manifest_files() -> None:
    text = MANIFEST.read_text(encoding="utf-8", errors="replace")
    names = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("file "):
            names.append(line.split()[1])
    if not names:
        fail("recovered manifest has no file entries")
    aof_dir = MANIFEST.parent
    for name in names:
        if not (aof_dir / name).is_file():
            fail(f"manifest lists missing file {name}")
    # Broken incident listed a missing seq-3 incr; that must not still be required.
    if "appendonly.aof.3.incr.aof" in names and not (aof_dir / "appendonly.aof.3.incr.aof").is_file():
        fail("manifest still references the missing incident incr file")


def main() -> None:
    assert_data_frozen()
    if not is_elf(SERVER):
        fail(f"{SERVER} is not a real ELF redis-server")
    conf = parse_conf(Path("/results/recovered/redis.conf"))
    for key, val in CONF_EXPECT.items():
        if key == "bind":
            if "127.0.0.1" not in (conf.get(key) or "").split():
                fail(f"redis.conf: bind must include 127.0.0.1, got {conf.get(key)!r}")
            continue
        if conf.get(key) != val:
            fail(f"redis.conf: expected {key}={val!r}, got {conf.get(key)!r}")
    if conf.get("save") not in ("", '""'):
        fail(f"redis.conf save must be empty, got {conf.get('save')!r}")
    pid_running(Path("/results/recovered/redis.pid"))
    run_check_aof()
    assert_manifest_files()
    conn = connect(6379)
    try:
        if conn.call("PING") != "PONG":
            fail("server PING failed")
        if config_get(conn, "port") != "6379":
            fail("live port is not 6379")
        if config_get(conn, "appendonly") != "yes":
            fail("live appendonly is not yes")
        if config_get(conn, "appenddirname") != "appendonlydir":
            fail("live appenddirname mismatch")
        if config_get(conn, "aof-load-truncated") != "yes":
            fail("live aof-load-truncated is not yes")
        info = parse_info(conn.call("INFO", "replication"))
        if info.get("role") != "master":
            fail(f"role {info.get('role')!r}")
        pers = parse_info(conn.call("INFO", "persistence"))
        if pers.get("aof_enabled") != "1":
            fail(f"aof_enabled {pers.get('aof_enabled')!r}")
        if pers.get("aof_rewrite_in_progress") not in (None, "0"):
            deadline = time.time() + 20
            while time.time() < deadline:
                pers = parse_info(conn.call("INFO", "persistence"))
                if pers.get("aof_rewrite_in_progress") == "0":
                    break
                time.sleep(0.2)
            else:
                fail("BGREWRITEAOF still in progress")
        last_rewrite = pers.get("aof_last_rewrite_time_sec")
        if last_rewrite in (None, "-1"):
            fail("BGREWRITEAOF does not appear to have completed (aof_last_rewrite_time_sec=-1)")
        ticket = conn.call("GET", "incident:ticket")
        owner = conn.call("GET", "incident:owner")
        host = conn.call("HGET", "incident:meta", "host")
        zone = conn.call("HGET", "incident:meta", "zone")
        if ticket != "AOF-7721":
            fail(f"incident:ticket={ticket!r}")
        if owner != "ops-oncall":
            fail(f"incident:owner={owner!r}")
        if host != "cache-a":
            fail(f"incident:meta host={host!r}")
        if zone != "eu-west":
            fail(f"incident:meta zone={zone!r}")
        scratch = conn.call("GET", "incident:scratch")
        if scratch is not None:
            fail("truncated MULTI key incident:scratch must be absent")
        stale = conn.call("GET", "stale")
        if stale is not None:
            fail("leftover stale key must be absent")
    finally:
        conn.close()
    # Re-run check-aof after confirming rewrite finished.
    run_check_aof()
    load_report(Path("/results/aof-report.json"))
    raise SystemExit(0)


if __name__ == "__main__":
    main()
