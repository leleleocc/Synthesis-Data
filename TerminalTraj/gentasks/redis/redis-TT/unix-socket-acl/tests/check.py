#!/usr/bin/env python3
"""Behavior/state/result oracle for unix-socket ACL hardening."""
from __future__ import annotations

import hashlib
import json
import os
import socket
import stat
import sys
from pathlib import Path

EXPECTED_JSON_KEYS = [
    "tcp_port",
    "unixsocket",
    "default_off",
    "app_ping",
    "app_wrong_key",
    "ops_whoami",
]
EXPECTED_JSON = {
    "tcp_port": 0,
    "unixsocket": "/results/redis.sock",
    "default_off": True,
    "app_ping": "PONG",
    "app_wrong_key": "denied",
    "ops_whoami": "ops",
}
DRAFT_SHA256 = "e18d82d7779b012b7e7291c110f41f12d71d4aa6dad899c3a742a91fe7b6a5f5"
CONF_EXPECT = {
    "bind": "127.0.0.1",
    "port": "0",
    "protected-mode": "yes",
    "unixsocket": "/results/redis.sock",
    "unixsocketperm": "700",
    "aclfile": "/results/users.acl",
    "daemonize": "no",
    "dir": "/results/redis-data",
    "dbfilename": "dump.rdb",
    "pidfile": "/results/redis.pid",
    "logfile": "/results/redis.log",
    "appendonly": "no",
}
SOCK = "/results/redis.sock"


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


def connect_unix() -> Redis:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect(SOCK)
    except OSError as exc:
        fail(f"cannot connect to {SOCK}: {exc}")
    return Redis(sock)


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


def tcp_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.5):
            return True
    except OSError:
        return False


def parse_acl_users(path: Path) -> dict[str, str]:
    raw = path.read_bytes()
    if b"\r" in raw:
        fail(f"{path} must use Unix newlines, found CR")
    if not raw.endswith(b"\n"):
        fail(f"{path} missing trailing newline")
    text = raw.decode("utf-8")
    users: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.lower().startswith("requirepass"):
            fail("users.acl must not contain requirepass")
        if not stripped.startswith("user "):
            fail(f"unexpected ACL line {stripped!r}")
        parts = stripped.split()
        if len(parts) < 2:
            fail(f"malformed user line {stripped!r}")
        name = parts[1]
        if name in users:
            fail(f"duplicate ACL user {name}")
        users[name] = stripped
    if set(users) != {"default", "app", "ops"}:
        fail(f"users.acl must define exactly default, app, ops; got {sorted(users)}")
    return users


def tokens(line: str) -> set[str]:
    return set(line.split())


def main() -> None:
    draft = Path("/data/acl/users.acl")
    if not draft.is_file():
        fail("/data/acl/users.acl missing")
    if sha256_file(draft) != DRAFT_SHA256:
        fail("/data/acl/users.acl was modified")
    if not is_elf(Path("/app/src/redis-server")):
        fail("/app/src/redis-server is not a real ELF redis-server")
    if not is_elf(Path("/app/src/redis-cli")):
        fail("/app/src/redis-cli is not a real ELF redis-cli")
    conf = parse_conf(Path("/results/redis.conf"))
    for key, val in CONF_EXPECT.items():
        if key == "unixsocketperm":
            raw_perm = conf.get(key) or ""
            try:
                perm = int(raw_perm, 8)
            except ValueError:
                fail(f"redis.conf: unixsocketperm must be octal 700, got {raw_perm!r}")
            if perm != 0o700:
                fail(f"redis.conf: unixsocketperm must be 700, got {raw_perm!r}")
            continue
        if key == "bind":
            if "127.0.0.1" not in (conf.get(key) or "").split():
                fail(f"redis.conf: bind must include 127.0.0.1, got {conf.get(key)!r}")
            continue
        if conf.get(key) != val:
            fail(f"redis.conf: expected {key}={val!r}, got {conf.get(key)!r}")
    if "requirepass" in conf:
        fail("redis.conf must not set requirepass")
    if conf.get("save") not in ("", '""'):
        fail(f"redis.conf save must be empty, got {conf.get('save')!r}")
    if not Path("/results/redis-data").is_dir():
        fail("missing /results/redis-data")
    pid_running(Path("/results/redis.pid"))
    sock_path = Path(SOCK)
    if not sock_path.exists():
        fail(f"missing unix socket {SOCK}")
    mode = stat.S_IMODE(sock_path.stat().st_mode)
    if mode != 0o700:
        fail(f"{SOCK} mode is {oct(mode)}, expected 0o700")
    if tcp_open(6379):
        fail("TCP port 6379 accepts connections; nothing may listen there")

    users = parse_acl_users(Path("/results/users.acl"))
    default_tok = tokens(users["default"])
    if "off" not in default_tok:
        fail("default user must be off")
    if "-@all" not in default_tok:
        fail("default user must include -@all")
    if any(tok.startswith("~") for tok in default_tok) or "allkeys" in default_tok:
        fail("default user must not have a key pattern that grants writes")
    app_tok = tokens(users["app"])
    if "on" not in app_tok:
        fail("app user must be on")
    for flag in (
        "+@connection",
        "+@read",
        "+@write",
        "+@string",
        "+@hash",
        "+@list",
        "-@admin",
        "-@dangerous",
        "resetchannels",
        "~app:*",
    ):
        if flag not in app_tok:
            fail(f"app user missing {flag}")
    if "~*" in app_tok:
        fail("app user must not use ~*")
    ops_tok = tokens(users["ops"])
    if "on" not in ops_tok:
        fail("ops user must be on")
    if "+@all" not in ops_tok:
        fail("ops user missing +@all")
    if "~*" not in ops_tok:
        fail("ops user missing ~*")
    if "allchannels" not in ops_tok and "&*" not in ops_tok:
        fail("ops user missing allchannels")

    unauth = connect_unix()
    try:
        try:
            unauth.call("PING")
        except RedisError:
            pass
        else:
            fail("unauthenticated PING must fail")
    finally:
        unauth.close()

    app = connect_unix()
    try:
        auth = app.call("AUTH", "app", "app-secret-7")
        if auth not in ("OK", True) and auth != "OK":
            # AUTH returns +OK
            if auth != "OK":
                fail(f"app AUTH returned {auth!r}")
        ping = app.call("PING")
        if ping != "PONG":
            fail(f"app PING returned {ping!r}")
        set_ok = app.call("SET", "app:health", "1")
        if set_ok != "OK":
            fail(f"app SET app:health returned {set_ok!r}")
        try:
            app.call("SET", "other:health", "1")
        except RedisError as exc:
            msg = exc.message.lower()
            if "acl" not in msg and "nack" not in msg and "permission" not in msg and "no permission" not in msg:
                # Redis 7 ACL key errors look like: NOPERM this user has no permissions to run the 'set' command or its key
                if "noperm" not in msg:
                    fail(f"app SET other:health error should be ACL/NOPERM, got {exc.message!r}")
        else:
            fail("app SET other:health 1 must be denied")
    finally:
        app.close()

    ops = connect_unix()
    try:
        ops.call("AUTH", "ops", "ops-secret-7")
        who = ops.call("ACL", "WHOAMI")
        if who != "ops":
            fail(f"ACL WHOAMI returned {who!r}")
        listing = ops.call("ACL", "LIST")
        if not isinstance(listing, list):
            fail(f"ACL LIST returned {listing!r}")
        names = []
        for entry in listing:
            if isinstance(entry, str) and entry.startswith("user "):
                names.append(entry.split()[1])
        if sorted(names) != ["app", "default", "ops"]:
            fail(f"live ACL LIST users {names} are not exactly default/app/ops")
        default_live = next(e for e in listing if isinstance(e, str) and e.startswith("user default "))
        if " off " not in f" {default_live} " and not default_live.split()[2] == "off":
            fail(f"live default user is not off: {default_live}")
    finally:
        ops.close()

    load_report(Path("/results/acl-report.json"))
    raise SystemExit(0)


if __name__ == "__main__":
    main()
