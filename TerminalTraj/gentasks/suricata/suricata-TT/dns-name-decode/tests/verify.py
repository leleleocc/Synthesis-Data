#!/usr/bin/env python3
"""Independent DNS name decoder matching rust/src/dns/parser.rs dns_parse_name."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

APP = Path("/app")
OUTDIR = Path("/results/dns-decode")
PARSER = APP / "rust" / "src" / "dns" / "parser.rs"
PARSER_SHA256 = "5df8e973b5b2820a74a25fa60d5c1374131497629051f1510c5e40f9d2beafb4"

MAX_NAME_LEN = 1025
JSON_KEYS = ["id", "offset", "name", "truncated", "infinite_loop", "label_limit", "ok"]
IDS = [f"m{i}" for i in range(1, 11)]

CORPUS = {
    "m1": (12, "000101000001000000000000076578616d706c6503636f6d0000010001"),
    "m2": (12, "00010100000100000000000003677777076578616d706c6503636f6d0000010001"),
    "m3": (12, "00010100000100000000000003777777c012076578616d706c6503636f6d0000010001"),
    "m4": (12, "000101000001000000000000c00c00010001"),
    "m5": (0, "c000"),
    "m6": (0, None),
    "m7": (12, "0001010000010000000000000161c00c00010001"),
    "m8": (0, "00"),
    "m9": (0, "0161c000"),
    "m10": (0, "ff6161"),
}


class HardError(Exception):
    pass


def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(1)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def m6_bytes() -> bytes:
    parts = []
    for _ in range(16):
        parts.append(bytes([63]) + b"a" * 63)
    parts.append(bytes([16]) + b"a" * 16)
    parts.append(b"\x00")
    return b"".join(parts)


def dns_parse_name(message: bytes, offset: int) -> dict:
    start = offset
    pos = offset
    pivot = start
    name = bytearray()
    count = 0
    truncated = False
    infinite_loop = False
    label_limit = False
    msglen = len(message)

    while True:
        if pos >= msglen:
            break
        length = message[pos]
        if length == 0x00:
            pos += 1
            break
        if length & 0b11000000 == 0:
            lab_len = length
            if pos + 1 + lab_len > msglen:
                raise HardError()
            label = message[pos + 1 : pos + 1 + lab_len]
            if not truncated:
                if name:
                    name.append(ord("."))
                name.extend(label)
            pos = pos + 1 + lab_len
        elif length & 0b11000000 == 0b11000000:
            if pos + 2 > msglen:
                raise HardError()
            leader = (message[pos] << 8) | message[pos + 1]
            off = leader & 0x3FFF
            if off > msglen:
                raise HardError()
            rem = pos + 2
            if message[off:] == message[pos:]:
                infinite_loop = True
                if pivot != start:
                    break
                raise HardError()
            if pivot == start:
                pivot = rem
            pos = off
        else:
            raise HardError()

        count += 1
        if count > 255:
            label_limit = True
            if pivot != start:
                truncated = True
                break
            raise HardError()
        if len(name) > MAX_NAME_LEN:
            del name[MAX_NAME_LEN:]
            truncated = True
            if pivot != start:
                break

    return {
        "name": bytes(name).decode("latin-1"),
        "truncated": truncated,
        "infinite_loop": infinite_loop,
        "label_limit": label_limit,
        "ok": True,
    }


def expected_for(mid: str) -> dict:
    offset, hx = CORPUS[mid]
    if hx is None:
        msg = m6_bytes()
    else:
        msg = bytes.fromhex(hx)
    try:
        r = dns_parse_name(msg, offset)
    except HardError:
        r = {
            "name": "",
            "truncated": False,
            "infinite_loop": False,
            "label_limit": False,
            "ok": False,
        }
    r["id"] = mid
    r["offset"] = offset
    return r


def compact_obj(obj: dict) -> str:
    parts = []
    for k in JSON_KEYS:
        parts.append(json.dumps(k) + ":" + json.dumps(obj[k], separators=(",", ":")))
    return "{" + ",".join(parts) + "}"


def parse_json_file(path: Path, mid: str) -> dict:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        fail(f"{path} is not UTF-8")
    if not text.endswith("\n") or text.count("\n") != 1:
        fail(f"{path} must be one compact JSON object plus a single trailing newline")
    line = text[:-1]
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as exc:
        fail(f"{path} invalid JSON: {exc}")
    if not isinstance(obj, dict):
        fail(f"{path} not an object")
    if list(obj.keys()) != JSON_KEYS:
        fail(f"{path} keys {list(obj.keys())} != {JSON_KEYS}")
    rebuilt = compact_obj(obj)
    if rebuilt != line:
        fail(f"{path} not compact JSON\n expected {rebuilt!r}\n got      {line!r}")
    if obj["id"] != mid:
        fail(f"{path} id {obj['id']!r} != {mid!r}")
    return obj


def main() -> None:
    if not PARSER.is_file():
        fail(f"missing {PARSER}")
    if sha256_file(PARSER) != PARSER_SHA256:
        fail("do not modify files under /app: rust/src/dns/parser.rs hash mismatch")

    if not OUTDIR.is_dir():
        fail(f"missing directory {OUTDIR}")
    names = sorted(p.name for p in OUTDIR.iterdir() if p.is_file())
    expected_names = [f"{i}.json" for i in IDS] + ["manifest.csv"]
    extra = [n for n in names if n not in expected_names]
    missing = [n for n in expected_names if n not in names]
    # directory must contain exactly those 11 files and no others
    all_entries = list(OUTDIR.iterdir())
    if any(p.is_dir() for p in all_entries) or extra or missing or len(all_entries) != 11:
        fail(f"{OUTDIR} must contain exactly 11 files {expected_names}; got {sorted(p.name for p in all_entries)}")

    rows = []
    for mid in IDS:
        path = OUTDIR / f"{mid}.json"
        obj = parse_json_file(path, mid)
        exp = expected_for(mid)
        for k in JSON_KEYS:
            if obj[k] != exp[k]:
                fail(f"{mid}.json {k} {obj[k]!r} != {exp[k]!r}")
        if not isinstance(obj["name"], str):
            fail(f"{mid} name not string")
        if not isinstance(obj["offset"], int) or isinstance(obj["offset"], bool):
            fail(f"{mid} offset not integer")
        for bk in ("truncated", "infinite_loop", "label_limit", "ok"):
            if not isinstance(obj[bk], bool):
                fail(f"{mid} {bk} not boolean")
        rows.append(exp)

    man_path = OUTDIR / "manifest.csv"
    raw = man_path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        fail("manifest.csv is not UTF-8")
    if "\r" in text:
        fail("manifest.csv must use LF newlines")
    if not text.endswith("\n"):
        fail("manifest.csv missing trailing newline")
    lines = text.split("\n")[:-1]
    header = "id,offset,ok,truncated,infinite_loop,label_limit,name_len"
    if not lines or lines[0] != header:
        fail(f"manifest.csv header {lines[:1]!r} != {header!r}")
    if len(lines) != 1 + len(IDS):
        fail(f"manifest.csv expected {1 + len(IDS)} lines, got {len(lines)}")
    for i, (mid, exp) in enumerate(zip(IDS, rows), 1):
        line = lines[i]
        if '"' in line:
            fail(f"manifest.csv quotes forbidden: {line!r}")
        parts = line.split(",")
        if len(parts) != 7:
            fail(f"manifest.csv row {i} field count {len(parts)}")
        name_len = len(exp["name"].encode("utf-8"))
        want = [
            mid,
            str(exp["offset"]),
            "true" if exp["ok"] else "false",
            "true" if exp["truncated"] else "false",
            "true" if exp["infinite_loop"] else "false",
            "true" if exp["label_limit"] else "false",
            str(name_len),
        ]
        if parts != want:
            fail(f"manifest.csv row {i} {parts} != {want}")


if __name__ == "__main__":
    main()
