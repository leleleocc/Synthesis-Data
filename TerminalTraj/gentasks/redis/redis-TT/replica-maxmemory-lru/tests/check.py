#!/usr/bin/env python3
"""Behavior/state/result oracle for replica maxmemory / min-replicas."""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

EXPECTED_JSON_KEYS = [
    "master_maxmemory",
    "replica_maxmemory",
    "replica_ignore_maxmemory",
    "master_policy",
    "replica_policy",
    "min_replicas_to_write",
    "replica_role",
    "master_link_status",
]
EXPECTED_JSON = {
    "master_maxmemory": 2097152,
    "replica_maxmemory": 1048576,
    "replica_ignore_maxmemory": "no",
    "master_policy": "allkeys-lru",
    "replica_policy": "allkeys-lru",
    "min_replicas_to_write": 1,
    "replica_role": "slave",
    "master_link_status": "up",
}
MASTER_CONF = {
    "bind": "127.0.0.1",
    "port": "6379",
    "protected-mode": "yes",
    "daemonize": "no",
    "dir": "/results/master",
    "dbfilename": "dump.rdb",
    "pidfile": "/results/master.pid",
    "logfile": "/results/master.log",
    "appendonly": "no",
    "maxmemory": "2097152",
    "maxmemory-policy": "allkeys-lru",
    "maxmemory-samples": "5",
    "min-replicas-to-write": "1",
    "min-replicas-max-lag": "10",
}
REPLICA_CONF = {
    "bind": "127.0.0.1",
    "port": "6380",
    "daemonize": "no",
    "dir": "/results/replica",
    "dbfilename": "dump.rdb",
    "pidfile": "/results/replica.pid",
    "logfile": "/results/replica.log",
    "appendonly": "no",
    "replica-read-only": "yes",
    "replica-serve-stale-data": "no",
    "replica-ignore-maxmemory": "no",
    "maxmemory": "1048576",
    "maxmemory-policy": "allkeys-lru",
}


def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(1)


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
        got = conf.get(key)
        if got is None and key.startswith("replica-"):
            got = conf.get("slave-" + key[len("replica-") :])
        if key == "bind":
            if "127.0.0.1" not in (got or "").split():
                fail(f"{label}: bind must include 127.0.0.1, got {got!r}")
            continue
        if got != val:
            fail(f"{label}: expected {key}={val!r}, got {got!r}")
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


def main() -> None:
    if not is_elf(Path("/app/src/redis-server")):
        fail("/app/src/redis-server is not a real ELF redis-server")
    if not is_elf(Path("/app/src/redis-cli")):
        fail("/app/src/redis-cli is not a real ELF redis-cli")
    master_conf = parse_conf(Path("/results/master.conf"))
    replica_conf = parse_conf(Path("/results/replica.conf"))
    require_conf(master_conf, MASTER_CONF, "master.conf")
    require_conf(replica_conf, REPLICA_CONF, "replica.conf")
    replicaof = replica_conf.get("replicaof") or replica_conf.get("slaveof")
    if replicaof.split() != ["127.0.0.1", "6379"]:
        fail(f"replica.conf replicaof must be 127.0.0.1 6379, got {replicaof!r}")
    for d in (Path("/results/master"), Path("/results/replica")):
        if not d.is_dir():
            fail(f"missing dir {d}")
    pid_running(Path("/results/master.pid"))
    pid_running(Path("/results/replica.pid"))

    master = connect(6379)
    replica = connect(6380)
    try:
        if master.call("PING") != "PONG":
            fail("master PING failed")
        if replica.call("PING") != "PONG":
            fail("replica PING failed")
        if config_get(master, "maxmemory") != "2097152":
            fail("live master maxmemory is not 2097152")
        if config_get(master, "maxmemory-policy") != "allkeys-lru":
            fail("live master maxmemory-policy is not allkeys-lru")
        if config_get(master, "maxmemory-samples") != "5":
            fail("live master maxmemory-samples is not 5")
        if config_get(master, "min-replicas-to-write") != "1":
            fail("live min-replicas-to-write is not 1")
        if config_get(master, "min-replicas-max-lag") != "10":
            fail("live min-replicas-max-lag is not 10")
        if config_get(replica, "maxmemory") != "1048576":
            fail("live replica maxmemory is not 1048576")
        if config_get(replica, "maxmemory-policy") != "allkeys-lru":
            fail("live replica maxmemory-policy is not allkeys-lru")
        ignore = config_get(replica, "replica-ignore-maxmemory")
        if ignore != "no":
            fail(f"live replica-ignore-maxmemory is {ignore!r}, not no")
        if config_get(replica, "replica-read-only") != "yes":
            fail("live replica-read-only is not yes")
        if config_get(replica, "replica-serve-stale-data") != "no":
            fail("live replica-serve-stale-data is not no")
        repl = parse_info(replica.call("INFO", "replication"))
        if repl.get("role") != "slave":
            fail(f"replica role {repl.get('role')!r}")
        if repl.get("master_link_status") != "up":
            fail(f"master_link_status {repl.get('master_link_status')!r}")
        if repl.get("master_host") != "127.0.0.1" or repl.get("master_port") != "6379":
            fail(f"replica is not attached to 127.0.0.1:6379 ({repl})")
        try:
            master.call("SET", "cache:probe", "ok")
        except RedisError as exc:
            fail(f"master SET failed while replica is up: {exc.message}")
        got = replica.call("GET", "cache:probe")
        if got != "ok":
            fail(f"replica did not serve replicated cache:probe ({got!r})")
        try:
            replica.call("SET", "cache:ro", "nope")
        except RedisError as exc:
            if "read" not in exc.message.lower() and "readonly" not in exc.message.lower():
                fail(f"replica SET should be read-only, got {exc.message!r}")
        else:
            fail("replica SET succeeded; replica-read-only yes was not enforced")
    finally:
        master.close()
        replica.close()
    load_report(Path("/results/cache-report.json"))
    raise SystemExit(0)


if __name__ == "__main__":
    main()
