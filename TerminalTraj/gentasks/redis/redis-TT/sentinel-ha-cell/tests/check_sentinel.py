#!/usr/bin/env python3
"""Verify the six-process Sentinel cell and /results/sentinel.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from redis_resp import Redis, RedisError, to_str
from src_guard import assert_src_unmodified

REPORT = Path("/results/sentinel.json")
MASTER_PORT = 6379
REPLICA_PORTS = (6380, 6381)
SENTINEL_PORTS = (26379, 26380, 26381)
MASTER_NAME = "shop-master"
DATA_ROOT = Path("/results/sentinel-data")
INSTANCE_DIRS = {
    6379: DATA_ROOT / "master",
    6380: DATA_ROOT / "replica-6380",
    6381: DATA_ROOT / "replica-6381",
}
SENTINEL_CONFS = {
    26379: DATA_ROOT / "sentinel-26379.conf",
    26380: DATA_ROOT / "sentinel-26380.conf",
    26381: DATA_ROOT / "sentinel-26381.conf",
}


def dirs_match(got: str, expected: Path) -> bool:
    got_path = Path(got)
    try:
        return got_path.resolve() == expected.resolve()
    except OSError:
        return got_path.as_posix().rstrip("/") == expected.as_posix().rstrip("/")


def connect(port: int, errors: list[str], label: str) -> Redis | None:
    try:
        r = Redis("127.0.0.1", port, timeout=5.0)
    except OSError as exc:
        errors.append(f"{label}: no listener on 127.0.0.1:{port}: {exc}")
        return None
    try:
        pong = r.ping()
    except (RuntimeError, EOFError, OSError) as exc:
        errors.append(f"{label}: PING failed (no requirepass): {exc}")
        r.close()
        return None
    if pong != "PONG":
        errors.append(f"{label}: PING must return PONG, got {pong!r}")
    return r


def parse_sentinel_master(reply) -> dict[str, str]:
    if not isinstance(reply, list):
        raise RuntimeError(f"SENTINEL master returned {reply!r}")
    out: dict[str, str] = {}
    for i in range(0, len(reply) - 1, 2):
        key = to_str(reply[i]) or ""
        val = reply[i + 1]
        out[key] = to_str(val) if not isinstance(val, RedisError) else val.message
    return out


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
        errors.append("sentinel.json must be a JSON object")
        return None
    return data


def main() -> int:
    errors: list[str] = []
    assert_src_unmodified(errors)
    report = load_report(errors)
    dbfiles: list[str] = []

    master = connect(MASTER_PORT, errors, "master")
    if master is not None:
        try:
            info = master.info("replication")
            if info.get("role") != "master":
                errors.append(f"6379 INFO role is {info.get('role')!r}, expected master")
            bind = master.config_get("bind")
            tokens = bind.split()
            if "127.0.0.1" not in tokens or "*" in tokens or "0.0.0.0" in tokens:
                errors.append(f"master bind must be loopback 127.0.0.1, got {bind!r}")
            protected = master.config_get("protected-mode")
            if protected.lower() not in {"yes", "1"}:
                errors.append(f"master protected-mode must be on, got {protected!r}")
            data_dir = master.config_get("dir")
            if not dirs_match(data_dir, INSTANCE_DIRS[MASTER_PORT]):
                errors.append(f"master dir must be {INSTANCE_DIRS[MASTER_PORT]}, got {data_dir!r}")
            dbfiles.append(master.config_get("dbfilename"))
        except (RuntimeError, EOFError, OSError) as exc:
            errors.append(f"master probe failed: {exc}")
        finally:
            master.close()

    for port in REPLICA_PORTS:
        r = connect(port, errors, f"replica-{port}")
        if r is None:
            continue
        try:
            info = r.info("replication")
            role = info.get("role")
            if role not in {"slave", "replica"}:
                errors.append(f"{port}: INFO role is {role!r}, expected slave")
            if info.get("master_host") != "127.0.0.1":
                errors.append(
                    f"{port}: master_host is {info.get('master_host')!r}, expected 127.0.0.1"
                )
            if info.get("master_port") != str(MASTER_PORT):
                errors.append(
                    f"{port}: master_port is {info.get('master_port')!r}, expected {MASTER_PORT}"
                )
            bind = r.config_get("bind")
            tokens = bind.split()
            if "127.0.0.1" not in tokens or "*" in tokens or "0.0.0.0" in tokens:
                errors.append(f"{port}: bind must be loopback 127.0.0.1, got {bind!r}")
            protected = r.config_get("protected-mode")
            if protected.lower() not in {"yes", "1"}:
                errors.append(f"{port}: protected-mode must be on, got {protected!r}")
            data_dir = r.config_get("dir")
            if not dirs_match(data_dir, INSTANCE_DIRS[port]):
                errors.append(f"{port}: dir must be {INSTANCE_DIRS[port]}, got {data_dir!r}")
            dbfiles.append(r.config_get("dbfilename"))
        except (RuntimeError, EOFError, OSError) as exc:
            errors.append(f"replica {port} probe failed: {exc}")
        finally:
            r.close()

    if dbfiles and len(set(dbfiles)) != len(dbfiles):
        errors.append(f"master and replica dbfilename values must be distinct, got {dbfiles!r}")

    for path in INSTANCE_DIRS.values():
        if not path.is_dir():
            errors.append(f"missing data dir {path}")

    sentinel_views = []
    for port in SENTINEL_PORTS:
        s = connect(port, errors, f"sentinel-{port}")
        if s is None:
            continue
        try:
            addr = s.execute_ok("SENTINEL", "GET-MASTER-ADDR-BY-NAME", MASTER_NAME)
            if not isinstance(addr, list) or len(addr) != 2:
                errors.append(f"sentinel {port}: get-master-addr-by-name returned {addr!r}")
            else:
                ip, p = to_str(addr[0]), to_str(addr[1])
                if ip != "127.0.0.1" or p != str(MASTER_PORT):
                    errors.append(
                        f"sentinel {port}: get-master-addr-by-name is {[ip, p]}, "
                        f"expected ['127.0.0.1', '{MASTER_PORT}'] while original master is up"
                    )
            master_info = parse_sentinel_master(s.execute_ok("SENTINEL", "MASTER", MASTER_NAME))
            sentinel_views.append(master_info)
            try:
                num_other = int(master_info.get("num-other-sentinels", "0"))
            except ValueError:
                num_other = -1
            try:
                num_slaves = int(master_info.get("num-slaves", master_info.get("num-replicas", "0")))
            except ValueError:
                num_slaves = -1
            if num_other < 2:
                errors.append(
                    f"sentinel {port}: num-other-sentinels is {num_other}, need at least 2"
                )
            if num_slaves < 2:
                errors.append(f"sentinel {port}: num-slaves is {num_slaves}, need at least 2")
            quorum = master_info.get("quorum")
            if quorum is not None and str(quorum) != "2":
                errors.append(f"sentinel {port}: quorum is {quorum!r}, expected 2")
            down_after = master_info.get("down-after-milliseconds")
            if down_after is not None and str(down_after) != "5000":
                errors.append(
                    f"sentinel {port}: down-after-milliseconds is {down_after!r}, expected 5000"
                )
            failover_timeout = master_info.get("failover-timeout")
            if failover_timeout is not None and str(failover_timeout) != "15000":
                errors.append(
                    f"sentinel {port}: failover-timeout is {failover_timeout!r}, expected 15000"
                )
            parallel_syncs = master_info.get("parallel-syncs")
            if parallel_syncs is not None and str(parallel_syncs) != "1":
                errors.append(
                    f"sentinel {port}: parallel-syncs is {parallel_syncs!r}, expected 1"
                )
        except (RuntimeError, EOFError, OSError) as exc:
            errors.append(f"sentinel {port} probe failed: {exc}")
        finally:
            s.close()

        conf = SENTINEL_CONFS[port]
        if not conf.is_file():
            errors.append(f"missing persisted Sentinel config {conf}")
        else:
            text = conf.read_text(encoding="utf-8", errors="replace")
            if MASTER_NAME not in text or "monitor" not in text.lower():
                errors.append(f"{conf} must persist a sentinel monitor for {MASTER_NAME}")

    if report is not None:
        if report.get("master_name") != MASTER_NAME:
            errors.append(f"master_name must be {MASTER_NAME!r}, got {report.get('master_name')!r}")
        addr = report.get("master_addr")
        if not isinstance(addr, list) or [str(x) for x in addr] != ["127.0.0.1", "6379"]:
            errors.append(f"master_addr must be ['127.0.0.1', '6379'] as two strings, got {addr!r}")
        elif not all(isinstance(x, str) for x in addr):
            errors.append("master_addr elements must be strings")
        try:
            num_other = int(report.get("num_other_sentinels"))
            if num_other < 2:
                errors.append(f"num_other_sentinels must be at least 2, got {num_other}")
        except (TypeError, ValueError):
            errors.append(
                f"num_other_sentinels must be an integer >= 2, got {report.get('num_other_sentinels')!r}"
            )
        try:
            num_slaves = int(report.get("num_slaves"))
            if num_slaves < 2:
                errors.append(f"num_slaves must be at least 2, got {num_slaves}")
        except (TypeError, ValueError):
            errors.append(f"num_slaves must be an integer >= 2, got {report.get('num_slaves')!r}")
        sentinels = report.get("sentinels")
        if not isinstance(sentinels, list) or sentinels != [26379, 26380, 26381]:
            errors.append(
                f"sentinels must be the three TCP ports sorted ascending [26379, 26380, 26381], got {sentinels!r}"
            )
        elif not all(isinstance(x, int) and not isinstance(x, bool) for x in sentinels):
            errors.append("sentinels elements must be integers")
        if sentinel_views:
            live_other = int(sentinel_views[0].get("num-other-sentinels", "0"))
            live_slaves = int(
                sentinel_views[0].get("num-slaves", sentinel_views[0].get("num-replicas", "0"))
            )
            try:
                if int(report.get("num_other_sentinels")) != live_other:
                    errors.append(
                        f"num_other_sentinels {report.get('num_other_sentinels')!r} "
                        f"!= live SENTINEL master {live_other}"
                    )
                if int(report.get("num_slaves")) != live_slaves:
                    errors.append(
                        f"num_slaves {report.get('num_slaves')!r} != live SENTINEL master {live_slaves}"
                    )
            except (TypeError, ValueError):
                pass

    for item in errors:
        print(item, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"verifier crashed: {exc}", file=sys.stderr)
        sys.exit(1)
