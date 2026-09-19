#!/usr/bin/env python3
"""Verify RDB encoding audit report plus leftover 6379 hash-ziplist instance."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from redis_resp import Redis, to_str
from src_guard import assert_src_unmodified

REPORT = Path("/results/encodings.json")
EXPECTED_PATH = Path(__file__).resolve().parent / "expected_encodings.json"
RDB_DIR = Path("/data/rdb")
SCORE_TOL = 1e-9
RDB_HASHES = {
    "hash-zipmap.rdb": "8a33909df85fdba0899d502daa003baab413a70020ed6e242469e79080e06a99",
    "hash-ziplist.rdb": "28a3f83255191ec8d97cf66ec2d5510195a1d8a3213de45e04404a638435d780",
    "zset-ziplist.rdb": "638f7fbeb5f9819773c37e3020cacd2e03a67a41b83d5b78780e25682546bbb7",
    "list-quicklist.rdb": "3d073479e9c20b5fce8a487b38970383d2ef395f94dce2576f27ce4e842afbcf",
}
FILE_ORDER = [
    "hash-zipmap.rdb",
    "hash-ziplist.rdb",
    "zset-ziplist.rdb",
    "list-quicklist.rdb",
]


def scores_equal(got, expected) -> bool:
    try:
        return abs(float(got) - float(expected)) <= SCORE_TOL
    except (TypeError, ValueError):
        return False


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
        errors.append("encodings.json must be a JSON object")
        return None
    return data


def check_fields(file_name: str, typ: str, got, expected, errors: list[str]) -> None:
    if typ == "hash":
        if not isinstance(got, dict) or got != expected:
            errors.append(f"{file_name}: hash fields {got!r} != {expected!r}")
            return
    elif typ == "zset":
        if not isinstance(got, list) or len(got) != len(expected):
            errors.append(f"{file_name}: zset fields {got!r} != {expected!r}")
            return
        for row, exp in zip(got, expected):
            if not isinstance(row, dict) or row.get("member") != exp["member"]:
                errors.append(f"{file_name}: zset must be sorted by member; got {got!r}")
                return
            if not scores_equal(row.get("score"), exp["score"]):
                errors.append(
                    f"{file_name}: score for {exp['member']} {row.get('score')!r} != {exp['score']!r} "
                    f"(tolerance {SCORE_TOL})"
                )
    elif typ == "list":
        if not isinstance(got, list):
            errors.append(f"{file_name}: list fields {got!r} != {expected!r}")
            return
        got_norm = [str(x) for x in got]
        exp_norm = [str(x) for x in expected]
        if got_norm != exp_norm:
            errors.append(f"{file_name}: list fields {got!r} != {expected!r}")


def main() -> int:
    errors: list[str] = []
    assert_src_unmodified(errors)
    if not EXPECTED_PATH.is_file():
        errors.append(f"verifier missing golden {EXPECTED_PATH}")
        return 1
    expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    expected_by_file = {item["file"]: item for item in expected["files"]}

    for name, digest in RDB_HASHES.items():
        path = RDB_DIR / name
        if not path.is_file():
            errors.append(f"missing original RDB {path}")
            continue
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != digest:
            errors.append(f"{path} was modified (hash {got} != {digest})")

    data = load_report(errors)
    if data is not None:
        files = data.get("files")
        if not isinstance(files, list) or len(files) != 4:
            errors.append("files must be an array of four objects")
        else:
            names = [item.get("file") if isinstance(item, dict) else None for item in files]
            if names != FILE_ORDER:
                errors.append(f"files array order must be {FILE_ORDER}, got {names!r}")
            for item in files:
                if not isinstance(item, dict):
                    errors.append("each files element must be an object")
                    continue
                name = item.get("file")
                exp = expected_by_file.get(name)
                if exp is None:
                    errors.append(f"unexpected file {name!r}")
                    continue
                for field in ("key", "type", "default_encoding", "tight_encoding"):
                    if item.get(field) != exp[field]:
                        errors.append(
                            f"{name}: {field} {item.get(field)!r} != {exp[field]!r}"
                        )
                check_fields(name, exp["type"], item.get("fields"), exp["fields"], errors)

    try:
        r = Redis("127.0.0.1", 6379, timeout=5.0)
    except OSError as exc:
        errors.append(f"no Redis listener on 127.0.0.1:6379: {exc}")
        r = None
    if r is not None:
        try:
            try:
                pong = r.ping()
            except (RuntimeError, EOFError, OSError) as exc:
                errors.append(f"PING on 6379 failed (no password): {exc}")
            else:
                if pong != "PONG":
                    errors.append(f"PING must return PONG, got {pong!r}")
            try:
                dbfilename = r.config_get("dbfilename")
                if Path(dbfilename).name != "hash-ziplist.rdb":
                    errors.append(
                        f"live 6379 dbfilename must be a copy of hash-ziplist.rdb, got {dbfilename!r}"
                    )
                data_dir = r.config_get("dir")
                try:
                    dir_resolved = Path(data_dir).resolve()
                except OSError:
                    dir_resolved = Path(data_dir)
                if dir_resolved == Path("/data/rdb").resolve() or data_dir.rstrip("/") == "/data/rdb":
                    errors.append(
                        f"live 6379 dir must be a private copy of hash-ziplist.rdb, not {data_dir!r}"
                    )
                encoding = to_str(r.execute_ok("OBJECT", "ENCODING", "hash"))
                exp_enc = expected_by_file["hash-ziplist.rdb"]["default_encoding"]
                if encoding != exp_enc:
                    errors.append(
                        f"live OBJECT ENCODING hash is {encoding!r}, expected default {exp_enc!r}"
                    )
                hlen = r.execute_ok("HLEN", "hash")
                if hlen != 2:
                    errors.append(f"live hash HLEN {hlen!r} != 2")
                hmget = r.execute_ok("HMGET", "hash", "f1", "f2")
                values = [to_str(x) for x in (hmget or [])]
                if values != ["v1", "v2"]:
                    errors.append(f"live hash payload {values!r} != ['v1', 'v2']")
            except (RuntimeError, EOFError, OSError) as exc:
                errors.append(f"live hash-ziplist probe failed: {exc}")
        finally:
            r.close()

    for item in errors:
        print(item, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"verifier crashed: {exc}", file=sys.stderr)
        sys.exit(1)
