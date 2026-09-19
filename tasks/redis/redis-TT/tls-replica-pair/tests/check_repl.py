#!/usr/bin/env python3
"""Verify the TLS-only Redis 7 replica pair and /results/repl.json."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path

from redis_resp import Redis, RedisError, to_str
from src_guard import assert_src_unmodified

REPORT = Path("/results/repl.json")
CA = "/data/tls/ca.crt"
APP_USER = "app"
APP_PASS = "app-secret"
REPL_USER = "repl"
REPL_PASS = "repl-secret"
MASTER_PORT = 6379
REPLICA_PORT = 6380


def tls_client(port: int) -> Redis:
    return Redis(
        "127.0.0.1",
        port,
        timeout=5.0,
        tls=True,
        cafile=CA,
        server_hostname="redis",
    )


def is_error(reply) -> bool:
    return isinstance(reply, RedisError)


def plaintext_speaks_redis(port: int) -> bool:
    try:
        sock = socket.create_connection(("127.0.0.1", port), timeout=2.0)
        sock.settimeout(2.0)
    except OSError:
        return False
    try:
        sock.sendall(b"*1\r\n$4\r\nPING\r\n")
        data = b""
        while len(data) < 16:
            chunk = sock.recv(64)
            if not chunk:
                break
            data += chunk
            if b"PONG" in data or data.startswith(b"+") or data.startswith(b"-"):
                return True
        return False
    except OSError:
        return False
    finally:
        try:
            sock.close()
        except OSError:
            pass


def load_report(errors: list[str]):
    if not REPORT.is_file():
        errors.append(f"missing {REPORT}")
        return None
    raw = REPORT.read_bytes()
    if not raw.endswith(b"\n"):
        errors.append(f"{REPORT} must be UTF-8 JSON with a trailing newline")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"{REPORT} is not valid UTF-8 JSON: {exc}")
        return None
    if not isinstance(data, dict):
        errors.append("repl.json must be a JSON object")
        return None
    return data


def auth_as(r: Redis, user: str, password: str):
    return r.execute("AUTH", user, password)


def check_instance(
    port: int,
    expect_role: str,
    errors: list[str],
    label: str,
    require_tls_auth_clients_no: bool = False,
) -> Redis | None:
    try:
        r = tls_client(port)
    except OSError as exc:
        errors.append(f"{label}: TLS connect 127.0.0.1:{port} failed: {exc}")
        return None
    ping_unauth = r.execute("PING")
    if not is_error(ping_unauth):
        errors.append(f"{label}: unauthenticated PING must fail with default user off, got {ping_unauth!r}")
    default = r.execute("AUTH", "default")
    if not is_error(default):
        errors.append(f"{label}: AUTH as default must fail, got {default!r}")
    default2 = auth_as(r, "default", APP_PASS)
    if not is_error(default2):
        errors.append(f"{label}: AUTH as default/{APP_PASS} must fail, got {default2!r}")
    app = auth_as(r, APP_USER, APP_PASS)
    if is_error(app):
        errors.append(f"{label}: AUTH as app/app-secret failed: {app}")
        r.close()
        return None
    try:
        info = r.info("replication")
        role = info.get("role", "")
        if expect_role == "master" and role != "master":
            errors.append(f"{label}: INFO replication role is {role!r}, expected master")
        if expect_role == "replica" and role not in {"slave", "replica"}:
            errors.append(f"{label}: INFO replication role is {role!r}, expected slave/replica")
        port_plain = r.config_get("port")
        tls_port = r.config_get("tls-port")
        if port_plain not in {"0", ""}:
            errors.append(f"{label}: plaintext port must be 0, CONFIG GET port={port_plain!r}")
        if tls_port != str(port):
            errors.append(f"{label}: tls-port must be {port}, got {tls_port!r}")
        bind = r.config_get("bind")
        tokens = bind.split()
        if "127.0.0.1" not in tokens or "*" in tokens or "0.0.0.0" in tokens:
            errors.append(f"{label}: bind must be loopback-only 127.0.0.1, got {bind!r}")
        if require_tls_auth_clients_no:
            tls_auth = r.config_get("tls-auth-clients")
            if tls_auth.lower() not in {"no", "0"}:
                errors.append(f"{label}: tls-auth-clients must be no, got {tls_auth!r}")
    except (RuntimeError, EOFError, OSError) as exc:
        errors.append(f"{label}: post-AUTH probe failed: {exc}")
    return r


def main() -> int:
    errors: list[str] = []
    assert_src_unmodified(errors)
    if not Path(CA).is_file():
        errors.append(f"missing CA {CA}")

    report = load_report(errors)

    if plaintext_speaks_redis(MASTER_PORT):
        errors.append("non-TLS connection to 6379 spoke the Redis protocol")
    if plaintext_speaks_redis(REPLICA_PORT):
        errors.append("non-TLS connection to 6380 spoke the Redis protocol")

    master = check_instance(
        MASTER_PORT, "master", errors, "master", require_tls_auth_clients_no=True
    )
    replica = check_instance(REPLICA_PORT, "replica", errors, "replica")

    if master is not None:
        try:
            repl_auth = master.execute("AUTH", REPL_USER, REPL_PASS)
            if is_error(repl_auth):
                errors.append(f"AUTH as repl/repl-secret on master must succeed, got {repl_auth}")
            else:
                flush = master.execute("FLUSHALL")
                if not is_error(flush):
                    errors.append(f"repl user must not be able to run FLUSHALL, got {flush!r}")
                # Instruction forbids +@all; handshake-only replica ACLs must not write.
                write = master.execute("SET", "cache:probe", "from-repl")
                if not is_error(write):
                    errors.append(
                        f"repl user must not have +@all write access, SET succeeded: {write!r}"
                    )
            # Re-AUTH as app for the probe write.
            app = master.execute("AUTH", APP_USER, APP_PASS)
            if is_error(app):
                errors.append(f"re-AUTH as app on master failed: {app}")
            else:
                set_reply = master.execute("SET", "cache:probe", "ok")
                if is_error(set_reply) or to_str(set_reply) not in {"OK", "ok"}:
                    errors.append(f"SET cache:probe ok on master failed: {set_reply!r}")
        except (RuntimeError, EOFError, OSError) as exc:
            errors.append(f"master ACL/probe failed: {exc}")
        finally:
            master.close()

    replica_info = {}
    if replica is not None:
        try:
            try:
                tls_repl = replica.config_get("tls-replication")
                if tls_repl.lower() not in {"yes", "1"}:
                    errors.append(f"replica tls-replication must be yes, got {tls_repl!r}")
            except RuntimeError as exc:
                errors.append(str(exc))
            try:
                masteruser = replica.config_get("masteruser")
                if masteruser != REPL_USER:
                    errors.append(f"replica masteruser must be {REPL_USER!r}, got {masteruser!r}")
            except RuntimeError as exc:
                errors.append(str(exc))
            got = None
            for _ in range(50):
                got = replica.execute("GET", "cache:probe")
                if not is_error(got) and to_str(got) == "ok":
                    break
                time.sleep(0.1)
            if is_error(got) or to_str(got) != "ok":
                errors.append(f"GET cache:probe on replica must be ok, got {got!r}")
            replica_info = replica.info("replication")
            if replica_info.get("master_link_status") != "up":
                errors.append(
                    f"replica master_link_status is {replica_info.get('master_link_status')!r}, expected up"
                )
        except (RuntimeError, EOFError, OSError) as exc:
            errors.append(f"replica probe failed: {exc}")
        finally:
            replica.close()

    if report is not None:
        expected_ports = {
            "master_tls_port": MASTER_PORT,
            "replica_tls_port": REPLICA_PORT,
        }
        for key, val in expected_ports.items():
            if report.get(key) != val:
                errors.append(f"repl.json {key} must be {val}, got {report.get(key)!r}")
        if report.get("tls_build") != "yes":
            errors.append(f"repl.json tls_build must be the string 'yes', got {report.get('tls_build')!r}")
        # Reconnect briefly for live INFO comparison if needed.
        try:
            m = tls_client(MASTER_PORT)
            auth_as(m, APP_USER, APP_PASS)
            m_info = m.info("replication")
            m.close()
        except Exception as exc:  # noqa: BLE001
            m_info = {}
            errors.append(f"could not re-read master INFO: {exc}")
        if replica_info:
            live_replica_role = replica_info.get("role")
            live_link = replica_info.get("master_link_status")
            if report.get("role_replica") != live_replica_role:
                errors.append(
                    f"repl.json role_replica {report.get('role_replica')!r} != live INFO {live_replica_role!r}"
                )
            if report.get("master_link_status") != live_link:
                errors.append(
                    f"repl.json master_link_status {report.get('master_link_status')!r} != live {live_link!r}"
                )
        if m_info:
            live_master_role = m_info.get("role")
            if report.get("role_master") != live_master_role:
                errors.append(
                    f"repl.json role_master {report.get('role_master')!r} != live INFO {live_master_role!r}"
                )

    for item in errors:
        print(item, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"verifier crashed: {exc}", file=sys.stderr)
        sys.exit(1)
