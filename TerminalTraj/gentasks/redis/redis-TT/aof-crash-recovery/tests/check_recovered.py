#!/usr/bin/env python3
"""Verify AOF crash recovery: live 6379 keyspace plus /results/recovered.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from redis_resp import Redis, RedisError, to_str
from src_guard import assert_src_unmodified

EXPECTED_PATH = Path(__file__).resolve().parent / "expected_recovered.json"
REPORT_PATH = Path("/results/recovered.json")
FORBIDDEN = ("catalog:sku4", "should-not-load")
SCORE_TOL = 1e-9


def fail(errors: list[str]) -> int:
    for item in errors:
        print(item, file=sys.stderr)
    return 1 if errors else 0


def load_json_bytes(path: Path, errors: list[str]):
    if not path.is_file():
        errors.append(f"missing {path}")
        return None, None
    raw = path.read_bytes()
    if not raw.endswith(b"\n"):
        errors.append(f"{path} must be UTF-8 JSON with a trailing newline")
    try:
        text = raw.decode("utf-8")
        data = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"{path} is not valid UTF-8 JSON: {exc}")
        return raw, None
    return raw, data


def scores_equal(got, expected: float) -> bool:
    try:
        return abs(float(got) - expected) <= SCORE_TOL
    except (TypeError, ValueError):
        return False


def check_report(data, expected, errors: list[str]) -> None:
    if not isinstance(data, dict):
        errors.append("recovered.json must be a single JSON object")
        return
    if data.get("db") != expected["db"]:
        errors.append(f"db must be {expected['db']}, got {data.get('db')!r}")
    keys = data.get("keys")
    if not isinstance(keys, list):
        errors.append("keys must be an array")
        return
    names = [item.get("name") if isinstance(item, dict) else None for item in keys]
    expected_names = [item["name"] for item in expected["keys"]]
    if names != expected_names:
        errors.append(
            f"keys must be ordered by name ascending and match the recovered catalog; "
            f"got {names!r} expected {expected_names!r}"
        )
    by_name = {item["name"]: item for item in expected["keys"]}
    for item in keys:
        if not isinstance(item, dict):
            errors.append("each keys element must be an object")
            continue
        name = item.get("name")
        exp = by_name.get(name)
        if exp is None:
            errors.append(f"unexpected key in inventory: {name!r}")
            continue
        if item.get("type") != exp["type"]:
            errors.append(f"{name}: type {item.get('type')!r} != {exp['type']!r}")
        check_value(name, exp["type"], item.get("value"), exp["value"], errors, where="json")


def check_value(name: str, typ: str, got, expected, errors: list[str], where: str) -> None:
    prefix = f"{where} {name}"
    if typ == "string":
        if got != expected:
            errors.append(f"{prefix}: string value {got!r} != {expected!r}")
    elif typ == "list":
        if got != expected:
            errors.append(f"{prefix}: list value {got!r} != {expected!r}")
    elif typ == "set":
        if not isinstance(got, list) or got != expected:
            errors.append(f"{prefix}: set value must be {expected!r} sorted ascending, got {got!r}")
    elif typ == "hash":
        if not isinstance(got, dict):
            errors.append(f"{prefix}: hash value must be an object, got {got!r}")
            return
        if list(got.keys()) != sorted(expected.keys()) or got != expected:
            errors.append(
                f"{prefix}: hash fields must equal {expected!r} sorted by field name, got {got!r}"
            )
    elif typ == "zset":
        if not isinstance(got, list) or len(got) != len(expected):
            errors.append(f"{prefix}: zset must be {expected!r}, got {got!r}")
            return
        for row, exp in zip(got, expected):
            if not isinstance(row, dict) or row.get("member") != exp["member"]:
                errors.append(f"{prefix}: zset members must be sorted by name; got {got!r}")
                return
            if not scores_equal(row.get("score"), exp["score"]):
                errors.append(
                    f"{prefix}: score for {exp['member']} {row.get('score')!r} != {exp['score']!r} "
                    f"(float tolerance {SCORE_TOL})"
                )
    else:
        errors.append(f"{prefix}: unsupported type {typ!r}")


def live_value(r: Redis, name: str, typ: str):
    if typ == "string":
        return to_str(r.execute_ok("GET", name))
    if typ == "list":
        reply = r.execute_ok("LRANGE", name, 0, -1) or []
        return [to_str(x) for x in reply]
    if typ == "set":
        reply = r.execute_ok("SMEMBERS", name) or []
        return sorted(to_str(x) or "" for x in reply)
    if typ == "hash":
        reply = r.execute_ok("HGETALL", name) or []
        if len(reply) % 2 != 0:
            raise RuntimeError(f"HGETALL {name} odd length")
        pairs = [(to_str(reply[i]) or "", to_str(reply[i + 1]) or "") for i in range(0, len(reply), 2)]
        return dict(sorted(pairs, key=lambda kv: kv[0]))
    if typ == "zset":
        reply = r.execute_ok("ZRANGE", name, 0, -1, "WITHSCORES") or []
        if len(reply) % 2 != 0:
            raise RuntimeError(f"ZRANGE {name} odd length")
        rows = []
        for i in range(0, len(reply), 2):
            member = to_str(reply[i]) or ""
            score = float(to_str(reply[i + 1]) or "nan")
            rows.append({"member": member, "score": score})
        rows.sort(key=lambda row: row["member"])
        return rows
    raise RuntimeError(f"unhandled type {typ}")


def check_live(expected, errors: list[str]) -> None:
    try:
        r = Redis("127.0.0.1", 6379, timeout=5.0)
    except OSError as exc:
        errors.append(f"no Redis listener on 127.0.0.1:6379: {exc}")
        return
    try:
        try:
            pong = r.ping()
        except (RuntimeError, EOFError, TimeoutError, OSError) as exc:
            errors.append(f"PING failed (password-free PONG required): {exc}")
            return
        if pong != "PONG":
            errors.append(f"PING must return PONG, got {pong!r}")
        try:
            appendonly = r.config_get("appendonly")
            if appendonly.lower() not in {"yes", "1"}:
                errors.append(f"appendonly must still be yes, CONFIG GET appendonly={appendonly!r}")
            data_dir = r.config_get("dir")
            if Path(data_dir).resolve() != Path("/data/incident").resolve() and data_dir.rstrip("/") != "/data/incident":
                errors.append(f"server dir must be /data/incident, CONFIG GET dir={data_dir!r}")
        except RuntimeError as exc:
            errors.append(str(exc))
        try:
            live_names = sorted(r.keys())
        except RuntimeError as exc:
            errors.append(str(exc))
            return
        expected_names = [item["name"] for item in expected["keys"]]
        if live_names != sorted(expected_names):
            errors.append(
                f"live keyspace {live_names!r} must equal recovered catalog {sorted(expected_names)!r} "
                f"with no extra keys"
            )
        for bad in FORBIDDEN:
            if bad in live_names:
                errors.append(f"incomplete/unmanifested key {bad!r} must not be loaded")
        for item in expected["keys"]:
            name = item["name"]
            try:
                typ = to_str(r.execute_ok("TYPE", name))
            except RuntimeError as exc:
                errors.append(str(exc))
                continue
            if typ != item["type"]:
                errors.append(f"live TYPE {name} is {typ!r}, expected {item['type']!r}")
                continue
            try:
                value = live_value(r, name, item["type"])
            except RuntimeError as exc:
                errors.append(str(exc))
                continue
            check_value(name, item["type"], value, item["value"], errors, where="live")
    finally:
        r.close()


def main() -> int:
    errors: list[str] = []
    assert_src_unmodified(errors)
    if not EXPECTED_PATH.is_file():
        errors.append(f"verifier missing golden {EXPECTED_PATH}")
        return fail(errors)
    expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    raw, data = load_json_bytes(REPORT_PATH, errors)
    if data is not None:
        check_report(data, expected, errors)
        if raw is not None:
            def ordered(pairs):
                return dict(pairs)

            try:
                ordered_doc = json.loads(raw.decode("utf-8"), object_pairs_hook=ordered)
            except (UnicodeDecodeError, json.JSONDecodeError):
                ordered_doc = None
            keys = ordered_doc.get("keys") if isinstance(ordered_doc, dict) else None
            if isinstance(keys, list):
                for item in keys:
                    if not isinstance(item, dict) or item.get("type") != "hash":
                        continue
                    value = item.get("value")
                    if not isinstance(value, dict):
                        continue
                    for exp in expected["keys"]:
                        if exp["name"] == item.get("name"):
                            want = list(exp["value"].keys())
                            if list(value.keys()) != want:
                                errors.append(
                                    f"json {item.get('name')}: hash fields must be sorted by field name "
                                    f"{want}, got {list(value.keys())}"
                                )
                            break
    check_live(expected, errors)
    return fail(errors)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"verifier crashed: {exc}", file=sys.stderr)
        sys.exit(1)
