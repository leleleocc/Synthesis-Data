#!/usr/bin/env python3
"""Behavior/state/result oracle for the TLS master/replica task."""
from __future__ import annotations

import hashlib
import json
import os
import socket
import ssl
import subprocess
import sys
from pathlib import Path

EXPECTED_JSON_KEYS = [
    "redis_version",
    "master_tcp_port",
    "master_tls_port",
    "replica_role",
    "master_link_status",
    "tls_probe",
]
EXPECTED_JSON = {
    "redis_version": "7.2.16",
    "master_tcp_port": 0,
    "master_tls_port": 6379,
    "replica_role": "slave",
    "master_link_status": "up",
    "tls_probe": "ok",
}
PEM_SHA256 = {
    "ca.crt": "bf52eb28934161019faebbbdd54314740a7dd59a311adf2bc6fdd9f570ab4b44",
    "ca.key": "14fac123ca946ad8188568fe74b2008d7e03d5a56d2f251465908aeb293e16c9",
    "redis.crt": "539c4a3fb749178d343c4814c47be204728ff31d23fb15adda1f453e767ff260",
    "redis.key": "5d8756a86afd3a0548dbc4306c2117d2067c98d3b8b6b4cfb4c0f731d4e23d8e",
    "server.crt": "10ef340a279b8b9d399b077c719dd3d4b4410a7d6ee1d7976f0282375eb5b7cb",
    "server.key": "6a4b61850bba9dad1feba0031671e54a0cef22529bc6f3239260323e512e1c14",
    "client.crt": "01befeed1bfa28ae9d47226b535a462eeae597687634d60095efeff3a98afe62",
    "client.key": "8644c8dfa24829b5fb5b1144b947eff917c87cdd8d696e14f57c1fa8c857b545",
}
MASTER_CONF_EXPECT = {
    "bind": "127.0.0.1",
    "protected-mode": "yes",
    "port": "0",
    "tls-port": "6379",
    "tls-cert-file": "/data/tls/redis.crt",
    "tls-key-file": "/data/tls/redis.key",
    "tls-ca-cert-file": "/data/tls/ca.crt",
    "tls-auth-clients": "no",
    "tls-replication": "yes",
    "daemonize": "no",
    "dir": "/results/master",
    "dbfilename": "dump.rdb",
    "pidfile": "/results/master.pid",
    "logfile": "/results/master.log",
}
REPLICA_CONF_EXPECT = {
    "bind": "127.0.0.1",
    "protected-mode": "yes",
    "port": "0",
    "tls-port": "6380",
    "tls-cert-file": "/data/tls/redis.crt",
    "tls-key-file": "/data/tls/redis.key",
    "tls-ca-cert-file": "/data/tls/ca.crt",
    "tls-auth-clients": "no",
    "tls-replication": "yes",
    "daemonize": "no",
    "dir": "/results/replica",
    "dbfilename": "dump.rdb",
    "pidfile": "/results/replica.pid",
    "logfile": "/results/replica.log",
    "replica-read-only": "yes",
}


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
        if got is None and key == "replica-read-only":
            got = conf.get("slave-read-only")
        if key == "bind":
            if "127.0.0.1" not in (got or "").split():
                fail(f"{label}: bind must include 127.0.0.1, got {got!r}")
            continue
        if got != val:
            fail(f"{label}: expected {key}={val!r}, got {got!r}")
    replicaof = conf.get("replicaof") or conf.get("slaveof")
    if "replica-read-only" in expect:
        if not replicaof or replicaof.split()[:2] != ["127.0.0.1", "6379"]:
            fail(f"{label}: replicaof must be 127.0.0.1 6379, got {replicaof!r}")


def encode_command(*parts: object) -> bytes:
    chunks = [f"*{len(parts)}\r\n".encode()]
    for part in parts:
        if isinstance(part, bytes):
            payload = part
        else:
            payload = str(part).encode()
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
        if not line:
            fail("empty redis reply")
        kind = line[:1]
        rest = line[1:]
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
            crlf = self._readexact(2)
            if crlf != b"\r\n":
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


def tls_connect(port: int) -> Redis:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations("/data/tls/ca.crt")
    raw = socket.create_connection(("127.0.0.1", port), timeout=5)
    try:
        wrapped = ctx.wrap_socket(raw, server_hostname="127.0.0.1")
    except ssl.SSLError as exc:
        raw.close()
        fail(f"TLS handshake failed on 127.0.0.1:{port}: {exc}")
    wrapped.settimeout(5)
    return Redis(wrapped)


def plaintext_redis_pong(port: int) -> bool:
    """True if a non-TLS Redis PING receives +PONG (TCP connect alone is not success)."""
    try:
        sock = socket.create_connection(("127.0.0.1", port), timeout=2)
    except OSError:
        return False
    try:
        sock.settimeout(2)
        sock.sendall(encode_command("PING"))
        data = b""
        while b"\r\n" not in data:
            chunk = sock.recv(256)
            if not chunk:
                break
            data += chunk
        return data.startswith(b"+PONG")
    except OSError:
        return False
    finally:
        try:
            sock.close()
        except OSError:
            pass


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


def pid_running(pidfile: Path) -> None:
    if not pidfile.is_file():
        fail(f"missing pidfile {pidfile}")
    text = pidfile.read_text(encoding="utf-8", errors="replace").strip()
    if not text.isdigit():
        fail(f"bad pidfile {pidfile}: {text!r}")
    pid = int(text)
    if not Path(f"/proc/{pid}").is_dir():
        fail(f"pid {pid} from {pidfile} is not running")


def load_report(path: Path) -> dict:
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
    return obj


def assert_data_frozen() -> None:
    root = Path("/data/tls")
    if not root.is_dir():
        fail("/data/tls missing")
    names = sorted(p.name for p in root.iterdir() if p.is_file())
    if names != sorted(PEM_SHA256):
        fail(f"/data/tls file set changed: {names}")
    for name, digest in PEM_SHA256.items():
        path = root / name
        got = sha256_file(path)
        if got != digest:
            fail(f"/data/tls/{name} was modified ({got})")


def assert_cli_tls() -> None:
    cli = Path("/app/src/redis-cli")
    if not is_elf(cli):
        fail(f"{cli} is not a real ELF redis-cli")
    proc = subprocess.run(
        [
            str(cli),
            "--tls",
            "--insecure",
            "--cacert",
            "/data/tls/ca.crt",
            "-h",
            "127.0.0.1",
            "-p",
            "6379",
            "PING",
        ],
        capture_output=True,
        timeout=15,
        check=False,
    )
    out = (proc.stdout or b"") + (proc.stderr or b"")
    text = out.decode("utf-8", "replace")
    if proc.returncode != 0 or "PONG" not in text:
        fail(f"TLS redis-cli PING failed rc={proc.returncode}: {text!r}")


def main() -> None:
    assert_data_frozen()
    server = Path("/app/src/redis-server")
    if not is_elf(server):
        fail(f"{server} is not a real ELF redis-server")
    require_conf(parse_conf(Path("/app/master.conf")), MASTER_CONF_EXPECT, "master.conf")
    require_conf(parse_conf(Path("/app/replica.conf")), REPLICA_CONF_EXPECT, "replica.conf")
    for d in (Path("/results/master"), Path("/results/replica")):
        if not d.is_dir():
            fail(f"missing dir {d}")
    pid_running(Path("/results/master.pid"))
    pid_running(Path("/results/replica.pid"))
    if plaintext_redis_pong(6379):
        fail("plaintext Redis PING succeeded on 6379")
    if plaintext_redis_pong(6380):
        fail("plaintext Redis PING succeeded on 6380")
    master = tls_connect(6379)
    replica = tls_connect(6380)
    try:
        ping = master.call("PING")
        if ping != "PONG":
            fail(f"master TLS PING={ping!r}")
        if config_get(master, "port") != "0":
            fail("live master port is not 0")
        if config_get(master, "tls-port") != "6379":
            fail("live master tls-port is not 6379")
        if config_get(master, "tls-replication") != "yes":
            fail("live master tls-replication is not yes")
        if config_get(master, "tls-auth-clients") != "no":
            fail("live master tls-auth-clients is not no")
        if config_get(master, "tls-cert-file") != "/data/tls/redis.crt":
            fail("live master tls-cert-file mismatch")
        if config_get(replica, "port") != "0":
            fail("live replica port is not 0")
        if config_get(replica, "tls-port") != "6380":
            fail("live replica tls-port is not 6380")
        if config_get(replica, "tls-replication") != "yes":
            fail("live replica tls-replication is not yes")
        info = parse_info(master.call("INFO", "server"))
        if info.get("redis_version") != "7.2.16":
            fail(f"redis_version {info.get('redis_version')!r}")
        repl = parse_info(replica.call("INFO", "replication"))
        if repl.get("role") != "slave":
            fail(f"replica role {repl.get('role')!r}")
        if repl.get("master_link_status") != "up":
            fail(f"master_link_status {repl.get('master_link_status')!r}")
        if repl.get("master_host") != "127.0.0.1" or repl.get("master_port") != "6379":
            fail(f"replica is not attached to 127.0.0.1:6379 ({repl})")
        master_probe = master.call("GET", "tls:probe")
        if master_probe != "ok":
            fail(f"master tls:probe={master_probe!r} (probe key was not set on the TLS master)")
        probe = replica.call("GET", "tls:probe")
        if probe != "ok":
            fail(f"replica tls:probe={probe!r} (TLS replica did not already serve the probe key)")
        load_report(Path("/results/tls-report.json"))
    finally:
        master.close()
        replica.close()
    assert_cli_tls()
    raise SystemExit(0)


if __name__ == "__main__":
    main()
