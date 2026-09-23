#!/usr/bin/env python3
"""Minimal RESP client (stdlib only) for Harbor verifiers."""
from __future__ import annotations

import socket
import ssl


class RedisError:
    def __init__(self, message: str) -> None:
        self.message = message

    def __repr__(self) -> str:
        return f"RedisError({self.message!r})"


def _encode(*args: object) -> bytes:
    chunks = [f"*{len(args)}\r\n".encode()]
    for arg in args:
        if isinstance(arg, bytes):
            payload = arg
        else:
            payload = str(arg).encode()
        chunks.append(f"${len(payload)}\r\n".encode())
        chunks.append(payload)
        chunks.append(b"\r\n")
    return b"".join(chunks)


def _read_line(sock: socket.socket) -> bytes:
    buf = bytearray()
    while True:
        ch = sock.recv(1)
        if not ch:
            raise EOFError("redis connection closed")
        buf.extend(ch)
        if buf.endswith(b"\r\n"):
            return bytes(buf)


def _read_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise EOFError("redis connection closed")
        buf.extend(chunk)
    return bytes(buf)


def read_resp(sock: socket.socket):
    line = _read_line(sock)
    if not line:
        raise EOFError("empty RESP")
    typ = line[:1]
    rest = line[1:-2]
    if typ == b"+":
        return rest.decode("utf-8", "replace")
    if typ == b"-":
        return RedisError(rest.decode("utf-8", "replace"))
    if typ == b":":
        return int(rest)
    if typ == b"$":
        n = int(rest)
        if n == -1:
            return None
        data = _read_exact(sock, n)
        _read_exact(sock, 2)
        return data
    if typ == b"*":
        n = int(rest)
        if n == -1:
            return None
        return [read_resp(sock) for _ in range(n)]
    raise ValueError(f"unsupported RESP type {line!r}")


def to_str(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, RedisError):
        raise RuntimeError(value.message)
    return str(value)


class Redis:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 6379,
        timeout: float = 5.0,
        tls: bool = False,
        cafile: str | None = None,
        server_hostname: str = "redis",
    ) -> None:
        raw = socket.create_connection((host, port), timeout=timeout)
        raw.settimeout(timeout)
        if tls:
            ctx = ssl.create_default_context(cafile=cafile)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_REQUIRED
            self.sock = ctx.wrap_socket(raw, server_hostname=server_hostname)
        else:
            self.sock = raw

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def execute(self, *args: object):
        self.sock.sendall(_encode(*args))
        return read_resp(self.sock)

    def execute_ok(self, *args: object):
        reply = self.execute(*args)
        if isinstance(reply, RedisError):
            raise RuntimeError(f"{args[0]} failed: {reply.message}")
        return reply

    def ping(self) -> str:
        return to_str(self.execute_ok("PING")) or ""

    def config_get(self, param: str) -> str:
        reply = self.execute_ok("CONFIG", "GET", param)
        if not isinstance(reply, list) or len(reply) < 2:
            raise RuntimeError(f"CONFIG GET {param} returned {reply!r}")
        return to_str(reply[1]) or ""
