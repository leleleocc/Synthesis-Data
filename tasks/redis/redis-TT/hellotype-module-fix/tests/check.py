#!/usr/bin/env python3
"""Behavior/state/result oracle for the hellotype module task."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

EXPECTED_JSON_KEYS = [
    "module_loaded",
    "range_skips_first",
    "sum_empty",
    "remove_persists",
]
EXPECTED_JSON = {
    "module_loaded": True,
    "range_skips_first": True,
    "sum_empty": True,
    "remove_persists": True,
}
WRONGTYPE = "WRONGTYPE Operation against a key holding the wrong kind of value"
CONF_EXPECT = {
    "bind": "127.0.0.1",
    "port": "6379",
    "protected-mode": "yes",
    "daemonize": "no",
    "dir": "/results/hellotype",
    "dbfilename": "dump.rdb",
    "appendonly": "yes",
    "appendfilename": "appendonly.aof",
    "appenddirname": "appendonlydir",
    "loadmodule": "/app/src/modules/hellotype.so",
    "enable-debug-command": "yes",
    "pidfile": "/results/hellotype.pid",
    "logfile": "/results/hellotype.log",
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


def is_elf_or_so(path: Path) -> bool:
    if not path.is_file():
        return False
    with path.open("rb") as fh:
        magic = fh.read(4)
    return magic == b"\x7fELF"


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


def try_connect(port: int, timeout: float = 0.5):
    try:
        sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    except OSError:
        return None
    sock.settimeout(10)
    return Redis(sock)


def connect(port: int = 6379) -> Redis:
    conn = try_connect(port, timeout=5)
    if conn is None:
        fail(f"cannot connect to 127.0.0.1:{port}")
    return conn


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


def expect_error(conn: Redis, needle: str, *cmd: object) -> None:
    try:
        reply = conn.call(*cmd)
    except RedisError as exc:
        if needle and needle.lower() not in exc.message.lower():
            fail(f"{cmd} error {exc.message!r} does not contain {needle!r}")
        return
    fail(f"{cmd} should error, got {reply!r}")


def module_names(conn: Redis) -> list[str]:
    listing = conn.call("MODULE", "LIST")
    names = []
    if not isinstance(listing, list):
        fail(f"MODULE LIST returned {listing!r}")
    for entry in listing:
        if isinstance(entry, list):
            # [name, hellotype, ver, 1] or nested pairs
            as_map = {}
            i = 0
            while i + 1 < len(entry):
                as_map[str(entry[i])] = entry[i + 1]
                i += 2
            if "name" in as_map:
                names.append(str(as_map["name"]))
            elif entry:
                names.append(str(entry[0]))
        elif isinstance(entry, str):
            names.append(entry)
    return names


def wait_rewrite(conn: Redis) -> None:
    deadline = time.time() + 20
    while time.time() < deadline:
        pers = conn.call("INFO", "persistence")
        if isinstance(pers, str) and "aof_rewrite_in_progress:0" in pers:
            return
        time.sleep(0.2)
    fail("AOF rewrite did not finish")


def verify_aof_reload_on_fresh_process() -> None:
    """Load the rewritten AOF in a throwaway server; do not stop the agent's process."""
    src_dir = Path("/results/hellotype/appendonlydir")
    if not src_dir.is_dir():
        fail("appendonlydir missing for AOF restart check")
    tmp = Path(tempfile.mkdtemp(prefix="hellotype-aof-"))
    proc = None
    try:
        dst = tmp / "appendonlydir"
        shutil.copytree(src_dir, dst)
        conf_path = tmp / "reload.conf"
        conf_path.write_text(
            "\n".join(
                [
                    "bind 127.0.0.1",
                    "port 16379",
                    "protected-mode yes",
                    "daemonize no",
                    f"dir {tmp}",
                    "appendonly yes",
                    "appendfilename appendonly.aof",
                    "appenddirname appendonlydir",
                    "loadmodule /app/src/modules/hellotype.so",
                    "save \"\"",
                    f"pidfile {tmp}/reload.pid",
                    f"logfile {tmp}/reload.log",
                    "",
                ]
            )
        )
        proc = subprocess.Popen(
            ["/app/src/redis-server", str(conf_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 15
        conn = None
        while time.time() < deadline:
            conn = try_connect(16379, timeout=0.5)
            if conn is not None:
                try:
                    if conn.call("PING") == "PONG":
                        break
                except RedisError:
                    pass
                conn.close()
                conn = None
            time.sleep(0.2)
        if conn is None:
            log = (tmp / "reload.log").read_text(encoding="utf-8", errors="replace") if (tmp / "reload.log").is_file() else ""
            fail(f"AOF restart server did not come up on 16379: {log}")
        try:
            restored = ints(conn.call("HELLOTYPE.RANGE", "ht:rm", "0", "10"))
        finally:
            conn.close()
        if restored != [5, 7, 9]:
            fail(f"REMOVE did not survive AOF rewrite + process restart: {restored}")
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)


def ints(reply) -> list[int]:
    if reply is None:
        return []
    if not isinstance(reply, list):
        fail(f"expected array, got {reply!r}")
    out = []
    for item in reply:
        out.append(int(item))
    return out


def main() -> None:
    if not is_elf(Path("/app/src/redis-server")):
        fail("/app/src/redis-server is not a real ELF redis-server")
    if not is_elf_or_so(Path("/app/src/modules/hellotype.so")):
        fail("/app/src/modules/hellotype.so is missing or not ELF")
    conf = parse_conf(Path("/results/hellotype.conf"))
    for key, val in CONF_EXPECT.items():
        if key == "bind":
            if "127.0.0.1" not in (conf.get(key) or "").split():
                fail(f"hellotype.conf: bind must include 127.0.0.1, got {conf.get(key)!r}")
            continue
        if conf.get(key) != val:
            fail(f"hellotype.conf: expected {key}={val!r}, got {conf.get(key)!r}")
    if not Path("/results/hellotype").is_dir():
        fail("missing /results/hellotype")
    pid_running(Path("/results/hellotype.pid"))
    conn = connect(6379)
    try:
        if conn.call("PING") != "PONG":
            fail("PING failed")
        names = module_names(conn)
        if "hellotype" not in names:
            fail(f"hellotype not in MODULE LIST: {names}")

        conn.call("DEL", "ht:ord")
        conn.call("HELLOTYPE.INSERT", "ht:ord", "30")
        conn.call("HELLOTYPE.INSERT", "ht:ord", "10")
        conn.call("HELLOTYPE.INSERT", "ht:ord", "20")
        if conn.call("HELLOTYPE.LEN", "ht:ord") != 3:
            fail("HELLOTYPE.LEN after three inserts is not 3")
        ordered = ints(conn.call("HELLOTYPE.RANGE", "ht:ord", "0", "10"))
        if ordered != [10, 20, 30]:
            fail(f"INSERT did not keep the list ordered: {ordered}")
        skipped = ints(conn.call("HELLOTYPE.RANGE", "ht:ord", "1", "2"))
        if skipped != [20, 30]:
            fail(f"RANGE first=1 count=2 should skip the head, got {skipped}")
        empty = ints(conn.call("HELLOTYPE.RANGE", "ht:missing", "0", "10"))
        if empty != []:
            fail(f"RANGE on missing key should be empty, got {empty}")
        expect_error(conn, "", "HELLOTYPE.RANGE", "ht:ord", "-1", "1")
        expect_error(conn, "", "HELLOTYPE.RANGE", "ht:ord", "0", "-1")

        brange = ints(conn.call("HELLOTYPE.BRANGE", "ht:ord", "0", "10", "1"))
        if brange != [10, 20, 30]:
            fail(f"BRANGE should still return the ordered list, got {brange}")

        if conn.call("HELLOTYPE.SUM", "ht:missing-sum") != 0:
            fail("SUM of a missing key must be 0")
        conn.call("DEL", "ht:empty")
        # empty key: never inserted
        if conn.call("HELLOTYPE.SUM", "ht:empty") != 0:
            fail("SUM of an empty/missing key must be 0")
        if conn.call("HELLOTYPE.SUM", "ht:ord") != 60:
            fail("SUM of 10,20,30 must be 60")

        conn.call("DEL", "ht:rm")
        for v in ("5", "7", "9", "7"):
            conn.call("HELLOTYPE.INSERT", "ht:rm", v)
        # ordered 5,7,7,9 ; REMOVE first 7 -> 5,7,9
        if conn.call("HELLOTYPE.REMOVE", "ht:rm", "7") != 1:
            fail("REMOVE of present value must return 1")
        if conn.call("HELLOTYPE.REMOVE", "ht:rm", "100") != 0:
            fail("REMOVE of missing value must return 0")
        after = ints(conn.call("HELLOTYPE.RANGE", "ht:rm", "0", "10"))
        if after != [5, 7, 9]:
            fail(f"REMOVE should drop the first matching node, got {after}")

        conn.call("SET", "ht:str", "nope")
        for cmd in (
            ("HELLOTYPE.RANGE", "ht:str", "0", "1"),
            ("HELLOTYPE.LEN", "ht:str"),
            ("HELLOTYPE.SUM", "ht:str"),
            ("HELLOTYPE.REMOVE", "ht:str", "1"),
        ):
            expect_error(conn, "WRONGTYPE", *cmd)

        conn.call("SAVE")
        conn.call("DEBUG", "RELOAD")
        reloaded = ints(conn.call("HELLOTYPE.RANGE", "ht:rm", "0", "10"))
        if reloaded != [5, 7, 9]:
            fail(f"REMOVE did not survive SAVE/DEBUG RELOAD: {reloaded}")

        conn.call("BGREWRITEAOF")
        wait_rewrite(conn)
        after_aof = ints(conn.call("HELLOTYPE.RANGE", "ht:rm", "0", "10"))
        if after_aof != [5, 7, 9]:
            fail(f"list changed after AOF rewrite: {after_aof}")
        aof_dir = Path("/results/hellotype/appendonlydir")
        if not aof_dir.is_dir():
            fail("appendonlydir missing after rewrite")
        verify_aof_reload_on_fresh_process()
    finally:
        conn.close()
    load_report(Path("/results/hellotype-report.json"))
    raise SystemExit(0)


if __name__ == "__main__":
    main()
