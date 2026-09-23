#!/usr/bin/env python3
"""Independent Community ID v1 oracle matching Suricata output-json.c."""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import stat
import struct
import subprocess
import sys
from pathlib import Path

APP = Path("/app")
RESULTS = Path("/results")
TOOL = RESULTS / "community-id"
JSONL = RESULTS / "community_id.jsonl"
OUTPUT_JSON_C = APP / "src" / "output-json.c"
OUTPUT_JSON_SHA256 = "d0fc6412ccf47ed8bfb95d17c3a6ffe09ef5912f10eff1d56119676e55e7c1ed"

KEYS = ["seed", "src_ip", "dst_ip", "proto", "sp", "dp", "community_id"]
INPUT_KEYS = ["seed", "src_ip", "dst_ip", "proto", "sp", "dp"]

CORPUS = [
    {"seed": 0, "src_ip": "1.2.3.4", "dst_ip": "5.6.7.8", "proto": 6, "sp": 12345, "dp": 80},
    {"seed": 0, "src_ip": "5.6.7.8", "dst_ip": "1.2.3.4", "proto": 6, "sp": 80, "dp": 12345},
    {"seed": 0, "src_ip": "1.2.3.4", "dst_ip": "5.6.7.8", "proto": 17, "sp": 53, "dp": 1234},
    {"seed": 0, "src_ip": "10.0.0.1", "dst_ip": "10.0.0.1", "proto": 6, "sp": 40000, "dp": 443},
    {"seed": 0, "src_ip": "10.0.0.1", "dst_ip": "10.0.0.1", "proto": 6, "sp": 443, "dp": 40000},
    {"seed": 0, "src_ip": "192.0.2.10", "dst_ip": "192.0.2.20", "proto": 1, "sp": 8, "dp": 0},
    {"seed": 42, "src_ip": "1.2.3.4", "dst_ip": "5.6.7.8", "proto": 6, "sp": 12345, "dp": 80},
    {"seed": 0, "src_ip": "2001:db8::1", "dst_ip": "2001:db8::2", "proto": 6, "sp": 12345, "dp": 443},
    {"seed": 0, "src_ip": "2001:db8::2", "dst_ip": "2001:db8::1", "proto": 6, "sp": 443, "dp": 12345},
    {"seed": 0, "src_ip": "2001:db8::1", "dst_ip": "2001:db8::2", "proto": 58, "sp": 128, "dp": 129},
    {"seed": 65535, "src_ip": "8.8.8.8", "dst_ip": "1.1.1.1", "proto": 17, "sp": 53, "dp": 5353},
    {"seed": 0, "src_ip": "127.0.0.1", "dst_ip": "127.0.0.1", "proto": 6, "sp": 1, "dp": 1},
]

EXTRA = [
    {"seed": 1, "src_ip": "203.0.113.10", "dst_ip": "198.51.100.20", "proto": 6, "sp": 4444, "dp": 22},
    {"seed": 0, "src_ip": "198.51.100.20", "dst_ip": "203.0.113.10", "proto": 6, "sp": 22, "dp": 4444},
    {"seed": 7, "src_ip": "2001:db8::aa", "dst_ip": "2001:db8::bb", "proto": 17, "sp": 9, "dp": 53},
    {"seed": 0, "src_ip": "192.0.2.1", "dst_ip": "192.0.2.2", "proto": 1, "sp": 0, "dp": 8},
    {"seed": 1000, "src_ip": "fe80::1", "dst_ip": "fe80::2", "proto": 58, "sp": 128, "dp": 129},
    {"seed": 0, "src_ip": "0.0.0.0", "dst_ip": "255.255.255.255", "proto": 6, "sp": 1, "dp": 65535},
]


def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(1)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def community_id(seed: int, src_ip: str, dst_ip: str, proto: int, sp: int, dp: int) -> str:
    src = ipaddress.ip_address(src_ip)
    dst = ipaddress.ip_address(dst_ip)
    if src.version != dst.version:
        raise ValueError("mixed families")
    seed_n = int(seed) & 0xFFFF
    proto = int(proto)
    sp = int(sp)
    dp = int(dp)
    if src.version == 4:
        src_b, dst_b = src.packed, dst.packed
        src_i = int.from_bytes(src_b, "big")
        dst_i = int.from_bytes(dst_b, "big")
        if not (src_i < dst_i or (src_i == dst_i and sp < dp)):
            src_b, dst_b = dst_b, src_b
            sp, dp = dp, sp
        blob = struct.pack("!H4s4sBBHH", seed_n, src_b, dst_b, proto, 0, sp, dp)
    else:
        src_b, dst_b = src.packed, dst.packed
        if not (src_b < dst_b or (src_b == dst_b and sp < dp)):
            src_b, dst_b = dst_b, src_b
            sp, dp = dp, sp
        blob = struct.pack("!H16s16sBBHH", seed_n, src_b, dst_b, proto, 0, sp, dp)
    digest = hashlib.sha1(blob).digest()
    return "1:" + base64.b64encode(digest).decode("ascii")


def compact_obj(obj: dict, keys: list[str]) -> str:
    parts = []
    for k in keys:
        parts.append(json.dumps(k, ensure_ascii=False) + ":" + json.dumps(obj[k], ensure_ascii=False, separators=(",", ":")))
    return "{" + ",".join(parts) + "}"


def expected_row(flow: dict) -> dict:
    out = {k: flow[k] for k in INPUT_KEYS}
    out["community_id"] = community_id(flow["seed"], flow["src_ip"], flow["dst_ip"], flow["proto"], flow["sp"], flow["dp"])
    return out


def parse_compact_line(raw: str, keys: list[str]) -> dict:
    if raw.endswith("\n"):
        fail("internal: line still has newline")
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON: {exc}: {raw!r}")
    if not isinstance(obj, dict):
        fail(f"expected object, got {type(obj)}")
    if list(obj.keys()) != keys:
        fail(f"key order/set {list(obj.keys())} != {keys}")
    rebuilt = compact_obj(obj, keys)
    if rebuilt != raw:
        fail(f"not compact Suricata-style JSON\n expected {rebuilt!r}\n got      {raw!r}")
    return obj


def run_tool(flows: list[dict], timeout: int = 30) -> str:
    stdin = "".join(compact_obj(f, INPUT_KEYS) + "\n" for f in flows)
    try:
        proc = subprocess.run(
            [str(TOOL)],
            input=stdin.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        fail("community-id timed out")
    except OSError as exc:
        fail(f"failed to execute {TOOL}: {exc}")
    if proc.returncode != 0:
        fail(f"community-id exit {proc.returncode} stderr={proc.stderr[:400]!r}")
    try:
        return proc.stdout.decode("utf-8")
    except UnicodeDecodeError:
        fail("community-id stdout is not UTF-8")


def check_rows(text: str, flows: list[dict], where: str) -> None:
    if not text.endswith("\n"):
        fail(f"{where}: missing trailing newline")
    lines = text.split("\n")
    if lines[-1] != "":
        fail(f"{where}: missing trailing newline")
    lines = lines[:-1]
    if len(lines) != len(flows):
        fail(f"{where}: expected {len(flows)} lines, got {len(lines)}")
    for i, (raw, flow) in enumerate(zip(lines, flows), 1):
        obj = parse_compact_line(raw, KEYS)
        exp = expected_row(flow)
        for k in INPUT_KEYS:
            if obj[k] != exp[k]:
                fail(f"{where} line {i}: {k} {obj[k]!r} != {exp[k]!r}")
        if not isinstance(obj["community_id"], str):
            fail(f"{where} line {i}: community_id not string")
        if obj["community_id"] != exp["community_id"]:
            fail(f"{where} line {i}: community_id {obj['community_id']!r} != {exp['community_id']!r}")


def main() -> None:
    if not OUTPUT_JSON_C.is_file():
        fail(f"missing {OUTPUT_JSON_C}")
    got = sha256_file(OUTPUT_JSON_C)
    if got != OUTPUT_JSON_SHA256:
        fail("do not modify files under /app: src/output-json.c hash mismatch")

    if not TOOL.is_file():
        fail(f"missing executable {TOOL}")
    mode = TOOL.stat().st_mode
    if not (mode & stat.S_IXUSR):
        fail(f"{TOOL} is not executable")

    if not JSONL.is_file():
        fail(f"missing {JSONL}")
    jsonl_text = JSONL.read_text(encoding="utf-8")
    if jsonl_text == "":
        fail("community_id.jsonl is empty")
    check_rows(jsonl_text, CORPUS, str(JSONL))

    reproduced = run_tool(CORPUS)
    if reproduced != jsonl_text:
        fail("community-id stdin of the 12 corpus lines did not reproduce community_id.jsonl")
    check_rows(reproduced, CORPUS, "community-id corpus stdout")

    extra_out = run_tool(EXTRA)
    check_rows(extra_out, EXTRA, "community-id extra stdout")

    # Bidirectional pair must hash equal.
    if expected_row(EXTRA[0])["community_id"] != expected_row(EXTRA[1])["community_id"]:
        fail("internal oracle: extra pair should share community_id")


if __name__ == "__main__":
    main()
