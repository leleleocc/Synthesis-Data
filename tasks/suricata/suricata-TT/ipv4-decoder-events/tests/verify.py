#!/usr/bin/env python3
"""Independent IPv4 decoder-event oracle matching decode-ipv4.c / decode-events.c."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

APP = Path("/app")
RESULTS = Path("/results")
TOOL = RESULTS / "ipv4-events"
JSONL = RESULTS / "ipv4-events.jsonl"
DECODE_C = APP / "src" / "decode-ipv4.c"
EVENTS_C = APP / "src" / "decode-events.c"
DECODE_SHA256 = "cc70d02dfca7304063fab271af5524bd6ed26e2d41de176bc5e1d909129fa5c6"
EVENTS_SHA256 = "d1e606cfa28c5974500d2e5de2ad50efd511f54bbb157e9f84136fd843f7304e"

IPV4_HEADER_LEN = 20
IPV4_OPT_EOL = 0x00
IPV4_OPT_NOP = 0x01
IPV4_OPT_RR = 0x07
IPV4_OPT_QS = 0x19
IPV4_OPT_TS = 0x44
IPV4_OPT_SEC = 0x82
IPV4_OPT_LSRR = 0x83
IPV4_OPT_ESEC = 0x85
IPV4_OPT_CIPSO = 0x86
IPV4_OPT_SID = 0x88
IPV4_OPT_SSRR = 0x89
IPV4_OPT_RTRALT = 0x94
IPV4_OPT_SID_LEN = 4
IPV4_OPT_RTRALT_LEN = 4
IPV4_OPT_SEC_MIN = 3
IPV4_OPT_ROUTE_MIN = 3
IPV4_OPT_QS_MIN = 8
IPV4_OPT_TS_MIN = 5
IPV4_OPT_CIPSO_MIN = 10

NAMES = {
    "PKT_TOO_SMALL": "decoder.ipv4.pkt_too_small",
    "HLEN_TOO_SMALL": "decoder.ipv4.hlen_too_small",
    "IPLEN_SMALLER_THAN_HLEN": "decoder.ipv4.iplen_smaller_than_hlen",
    "TRUNC_PKT": "decoder.ipv4.trunc_pkt",
    "OPT_INVALID": "decoder.ipv4.opt_invalid",
    "OPT_INVALID_LEN": "decoder.ipv4.opt_invalid_len",
    "OPT_MALFORMED": "decoder.ipv4.opt_malformed",
    "OPT_PAD_REQUIRED": "decoder.ipv4.opt_pad_required",
    "OPT_EOL_REQUIRED": "decoder.ipv4.opt_eol_required",
    "OPT_DUPLICATE": "decoder.ipv4.opt_duplicate",
    "OPT_UNKNOWN": "decoder.ipv4.opt_unknown",
    "WRONG_IP_VER": "decoder.ipv4.wrong_ip_version",
    "ICMPV6": "decoder.ipv4.icmpv6",
}

CORPUS = [
    ("p1", "45"),
    ("p2", "4500001400010000400600000102030405060708"),
    ("p3", "5500001400010000400600000102030405060708"),
    ("p4", "4400001400010000400600000102030405060708"),
    ("p5", "4500001300010000400600000102030405060708"),
    ("p6", "4500002800010000400600000102030405060708"),
    ("p7", "4500001400010000403a00000102030405060708"),
    ("p8", "460000180001000040060000010203040506070800000000"),
    ("p9", "460000180001000040060000010203040506070801070000"),
    ("p10", "4700001c000100004006000001020304050607088308040001020304"),
    ("p11", "4700001c000100004006000001020304050607088308030001020304"),
    ("p12", "4800002000010000400600000102030405060708440805000000000044040500"),
]

JSON_KEYS = ["id", "events"]

# Extra binary packets for the CLI behavior check (not in the jsonl corpus).
EXTRA = [
    bytes.fromhex("45"),  # too small
    bytes.fromhex("4500001400010000400600000102030405060708"),  # valid empty
    bytes.fromhex("4500001400010000403a00000102030405060708"),  # icmpv6
    bytes.fromhex("460000180001000040060000010203040506070801070000"),  # pad + invalid len
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


def ev(events, key: str) -> None:
    events.append(NAMES[key])


def validate_generic(t: int, optlen: int, events: list) -> bool:
    if t == IPV4_OPT_QS:
        if optlen < IPV4_OPT_QS_MIN:
            ev(events, "OPT_INVALID_LEN")
            return False
    elif t in (IPV4_OPT_SEC, IPV4_OPT_ESEC):
        if optlen < IPV4_OPT_SEC_MIN:
            ev(events, "OPT_INVALID_LEN")
            return False
    elif t == IPV4_OPT_SID:
        if optlen != IPV4_OPT_SID_LEN:
            ev(events, "OPT_INVALID_LEN")
            return False
    elif t == IPV4_OPT_RTRALT:
        if optlen != IPV4_OPT_RTRALT_LEN:
            ev(events, "OPT_INVALID_LEN")
            return False
    else:
        ev(events, "OPT_UNKNOWN")
        return False
    return True


def validate_route(optlen: int, data: bytes, events: list) -> bool:
    if optlen < IPV4_OPT_ROUTE_MIN:
        ev(events, "OPT_INVALID_LEN")
        return False
    if not data:
        ev(events, "OPT_MALFORMED")
        return False
    ptr = data[0]
    if (ptr < 4) or (ptr % 4) or (ptr > optlen + 1):
        ev(events, "OPT_MALFORMED")
        return False
    return True


def validate_ts(optlen: int, data: bytes, events: list) -> bool:
    if optlen < IPV4_OPT_TS_MIN:
        ev(events, "OPT_INVALID_LEN")
        return False
    if not data:
        ev(events, "OPT_MALFORMED")
        return False
    ptr = data[0]
    if ptr < 5:
        ev(events, "OPT_MALFORMED")
        return False
    flag = data[1] & 0x0F
    rec = 8 if flag in (1, 3) else 4
    if ((ptr - 5) % rec) or (ptr > optlen + 1):
        ev(events, "OPT_MALFORMED")
        return False
    return True


def validate_cipso(optlen: int, data: bytes, events: list) -> bool:
    if optlen < IPV4_OPT_CIPSO_MIN:
        ev(events, "OPT_INVALID_LEN")
        return False
    if not data:
        ev(events, "OPT_MALFORMED")
        return False
    tag = data[4:] if len(data) >= 4 else b""
    length = optlen - 1 - 1 - 4
    i = 0
    while length:
        if length < 2:
            ev(events, "OPT_MALFORMED")
            return False
        ttype = tag[i]
        tlen = tag[i + 1]
        i += 2
        if tlen > length:
            ev(events, "OPT_MALFORMED")
            return False
        if ttype in (1, 2, 5, 6, 7):
            if tlen < 4 or tlen > length:
                ev(events, "OPT_MALFORMED")
                return False
            if ttype != 7 and tag[i] != 0:
                ev(events, "OPT_MALFORMED")
                return False
            i += tlen - 2
            length -= tlen
            continue
        ev(events, "OPT_MALFORMED")
        return False
    return True


def decode_options(optbytes: bytes, events: list) -> bool:
    """Return True if decoding failed (invalid)."""
    plen = len(optbytes)
    off = 0
    if plen % 8:
        ev(events, "OPT_PAD_REQUIRED")
    seen = set()
    while plen:
        t = optbytes[off]
        if t == IPV4_OPT_EOL:
            break
        if t == IPV4_OPT_NOP:
            off += 1
            plen -= 1
            continue
        if plen < 2:
            ev(events, "OPT_EOL_REQUIRED")
            break
        if optbytes[off + 1] > plen:
            ev(events, "OPT_INVALID_LEN")
            return True
        optlen = optbytes[off + 1]
        if optlen > plen or optlen < 2:
            ev(events, "OPT_INVALID_LEN")
            return True
        data = optbytes[off + 2 : off + optlen] if optlen > 2 else b""

        def handle(kind: str, validator) -> None:
            if kind in seen:
                ev(events, "OPT_DUPLICATE")
            else:
                seen.add(kind)
                validator()

        if t == IPV4_OPT_TS:
            handle("TS", lambda: validate_ts(optlen, data, events))
        elif t == IPV4_OPT_RR:
            handle("RR", lambda: validate_route(optlen, data, events))
        elif t == IPV4_OPT_QS:
            handle("QS", lambda: validate_generic(t, optlen, events))
        elif t == IPV4_OPT_SEC:
            handle("SEC", lambda: validate_generic(t, optlen, events))
        elif t == IPV4_OPT_LSRR:
            handle("LSRR", lambda: validate_route(optlen, data, events))
        elif t == IPV4_OPT_ESEC:
            handle("ESEC", lambda: validate_generic(t, optlen, events))
        elif t == IPV4_OPT_CIPSO:
            handle("CIPSO", lambda: validate_cipso(optlen, data, events))
        elif t == IPV4_OPT_SID:
            handle("SID", lambda: validate_generic(t, optlen, events))
        elif t == IPV4_OPT_SSRR:
            handle("SSRR", lambda: validate_route(optlen, data, events))
        elif t == IPV4_OPT_RTRALT:
            handle("RTRALT", lambda: validate_generic(t, optlen, events))
        else:
            ev(events, "OPT_INVALID")
        off += optlen
        plen -= optlen
    return False


def classify(pkt: bytes) -> list[str]:
    events: list[str] = []
    if len(pkt) < IPV4_HEADER_LEN:
        ev(events, "PKT_TOO_SMALL")
        return events
    if (pkt[0] >> 4) != 4:
        ev(events, "WRONG_IP_VER")
        return events
    hlen = (pkt[0] & 0x0F) << 2
    if hlen < IPV4_HEADER_LEN:
        ev(events, "HLEN_TOO_SMALL")
        return events
    iplen = int.from_bytes(pkt[2:4], "big")
    if iplen < hlen:
        ev(events, "IPLEN_SMALLER_THAN_HLEN")
        return events
    if len(pkt) < iplen:
        ev(events, "TRUNC_PKT")
        return events
    ip_opt_len = hlen - IPV4_HEADER_LEN
    proto = pkt[9]
    failed = False
    if ip_opt_len > 0:
        failed = decode_options(pkt[IPV4_HEADER_LEN : IPV4_HEADER_LEN + ip_opt_len], events)
    if failed:
        return events
    if proto == 58:
        ev(events, "ICMPV6")
    return events


def compact_obj(obj: dict) -> str:
    parts = []
    for k in JSON_KEYS:
        parts.append(json.dumps(k) + ":" + json.dumps(obj[k], separators=(",", ":")))
    return "{" + ",".join(parts) + "}"


def run_tool(pkt: bytes, timeout: int = 15) -> str:
    try:
        proc = subprocess.run(
            [str(TOOL)],
            input=pkt,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        fail("ipv4-events timed out")
    except OSError as exc:
        fail(f"failed to execute {TOOL}: {exc}")
    if proc.returncode != 0:
        fail(f"ipv4-events exit {proc.returncode} stderr={proc.stderr[:400]!r}")
    try:
        return proc.stdout.decode("utf-8")
    except UnicodeDecodeError:
        fail("ipv4-events stdout is not UTF-8")


def parse_cli_stdout(text: str) -> list[str]:
    if text == "":
        return []
    if not text.endswith("\n"):
        fail("ipv4-events stdout missing trailing newline when non-empty")
    lines = text.split("\n")[:-1]
    if any(x == "" for x in lines):
        fail("ipv4-events stdout contains empty event names")
    return lines


def main() -> None:
    if not DECODE_C.is_file() or sha256_file(DECODE_C) != DECODE_SHA256:
        fail("do not modify files under /app: decode-ipv4.c hash mismatch")
    if not EVENTS_C.is_file() or sha256_file(EVENTS_C) != EVENTS_SHA256:
        fail("do not modify files under /app: decode-events.c hash mismatch")

    if not TOOL.is_file():
        fail(f"missing {TOOL}")
    if not (TOOL.stat().st_mode & stat.S_IXUSR):
        fail(f"{TOOL} is not executable")
    if not JSONL.is_file():
        fail(f"missing {JSONL}")

    raw = JSONL.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        fail("ipv4-events.jsonl is not UTF-8")
    if "\r" in text:
        fail("ipv4-events.jsonl must use LF newlines")
    if not text.endswith("\n"):
        fail("ipv4-events.jsonl missing trailing newline")
    lines = text.split("\n")[:-1]
    if len(lines) != len(CORPUS):
        fail(f"ipv4-events.jsonl expected {len(CORPUS)} lines, got {len(lines)}")

    expected_rows = []
    for pid, hx in CORPUS:
        events = classify(bytes.fromhex(hx))
        expected_rows.append({"id": pid, "events": events})

    for i, ((pid, hx), exp) in enumerate(zip(CORPUS, expected_rows)):
        line = lines[i]
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            fail(f"jsonl line {i+1} invalid JSON: {exc}")
        if not isinstance(obj, dict):
            fail(f"jsonl line {i+1} not an object")
        if list(obj.keys()) != JSON_KEYS:
            fail(f"jsonl line {i+1} keys {list(obj.keys())} != {JSON_KEYS}")
        rebuilt = compact_obj(exp)
        if line != rebuilt:
            fail(f"jsonl line {i+1} {line!r} != {rebuilt!r}")
        if obj["id"] != pid:
            fail(f"jsonl line {i+1} id {obj['id']!r} != {pid!r}")
        if obj["events"] != exp["events"]:
            fail(f"jsonl {pid} events {obj['events']!r} != {exp['events']!r}")

        cli = parse_cli_stdout(run_tool(bytes.fromhex(hx)))
        if cli != exp["events"]:
            fail(f"CLI {pid} {cli!r} != jsonl/oracle {exp['events']!r}")

    for pkt in EXTRA:
        cli = parse_cli_stdout(run_tool(pkt))
        exp = classify(pkt)
        if cli != exp:
            fail(f"CLI extra packet {pkt.hex()} {cli!r} != {exp!r}")


if __name__ == "__main__":
    main()
