#!/usr/bin/env python3
"""Independent JA3/JA4 oracle matching this Suricata tree."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

APP = Path("/app")
RESULTS = Path("/results")
CSV_PATH = RESULTS / "fingerprints.csv"
PROBE = RESULTS / "ja3_probe.py"

FILES = {
    APP / "src" / "util-ja3.c": "1e6a411d4f61c8ab80a074cc21e9f2ea984b7a79530f990f9b5c7be806d2144d",
    APP / "src" / "app-layer-ssl.c": "f78b17cf902f48d9489dbd5079a32275a73d315ef867000bf78770e56065acf5",
    APP / "rust" / "src" / "ja4.rs": "48bdb9101b24062cc546f1ebf8847ae30b16f45f9ccd721950c84288ecb3499e",
    APP / "rust" / "src" / "handshake.rs": "484f0ef638bae1ed2369847a1bc57b99712281095fbf59ab1ffef4452df41193",
}

GREASE = {
    0x0A0A, 0x1A1A, 0x2A2A, 0x3A3A, 0x4A4A, 0x5A5A, 0x6A6A, 0x7A7A,
    0x8A8A, 0x9A9A, 0xAAAA, 0xBABA, 0xCACA, 0xDADA, 0xEAEA, 0xFAFA,
}
HEX = "0123456789abcdef"
HEX_ALPN_RE = re.compile(r"^[0-9a-f]+$")

HEADER = "id,ja3_string,ja3_hash,ja4"

HELLOs = [
    dict(id="h1", quic=False, hello_version=771, ciphers=[4865, 4866, 4867, 255],
         extensions=[0, 11, 10, 35, 13, 43, 45, 51], curves=[29, 23, 24],
         point_formats=[0], sigalgs=[1027, 2052, 1025], alpn=["h2", "http/1.1"], sni="example.com"),
    dict(id="h2", quic=False, hello_version=771, ciphers=[4865, 2570, 4866],
         extensions=[0, 11, 2570, 10], curves=[29, 2570, 23],
         point_formats=[0], sigalgs=[1027], alpn=["http/1.1"], sni=None),
    dict(id="h3", quic=True, hello_version=772, ciphers=[4865, 4866],
         extensions=[0, 16, 10, 13], curves=[29],
         point_formats=[], sigalgs=[1027, 1283], alpn=["h3"], sni="quic.example"),
    dict(id="h4", quic=False, hello_version=769, ciphers=[47, 53],
         extensions=[], curves=[],
         point_formats=[], sigalgs=[], alpn=[], sni=None),
    dict(id="h5", quic=False, hello_version=771, ciphers=[4865],
         extensions=[0, 16], curves=[],
         point_formats=[], sigalgs=[], alpn=["0154"], sni="a.example"),
    dict(id="h6", quic=False, hello_version=771, ciphers=[4865, 4866, 4867, 49195],
         extensions=[0, 23, 10, 11, 35, 16, 13], curves=[29, 23, 24, 25],
         point_formats=[0, 1, 2], sigalgs=[1027, 2052, 1025, 1283, 1537], alpn=["h2"], sni="cdn.test"),
    dict(id="h7", quic=False, hello_version=770, ciphers=[255, 4865],
         extensions=[10, 11], curves=[23],
         point_formats=[0], sigalgs=[], alpn=[], sni=None),
    dict(id="h8", quic=False, hello_version=771, ciphers=[4865],
         extensions=[0, 16], curves=[],
         point_formats=[], sigalgs=[], alpn=["*"], sni="star.example"),
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


def is_ascii_alnum(b: int) -> bool:
    return (0x30 <= b <= 0x39) or (0x41 <= b <= 0x5A) or (0x61 <= b <= 0x7A)


def hyphen(vals: list[int]) -> str:
    return "-".join(str(v) for v in vals if v not in GREASE)


def ja3_string(hello_version: int, ciphers, extensions, curves, point_formats) -> str:
    return ",".join(
        [
            str(hello_version),
            hyphen(ciphers),
            hyphen(extensions),
            hyphen(curves),
            hyphen(point_formats),
        ]
    )


def format_alpn(alpn: bytes) -> list[str]:
    ret = ["0", "0"]
    if not alpn:
        return ret
    if len(alpn) == 2:
        v = (alpn[0] << 8) | alpn[-1]
        if v in GREASE:
            return ret
    if (not is_ascii_alnum(alpn[0])) or (not is_ascii_alnum(alpn[-1])):
        return [HEX[alpn[0] >> 4], HEX[alpn[-1] & 0xF]]
    return [chr(alpn[0]), chr(alpn[-1])]


def version_to_ja4(hello_version: int) -> str:
    return {0x0304: "13", 0x0303: "12", 0x0302: "11", 0x0301: "10", 0x0300: "s3"}.get(hello_version, "00")


def decode_alpn_token(token: str) -> bytes:
    if len(token) >= 4 and len(token) % 2 == 0 and HEX_ALPN_RE.fullmatch(token):
        return bytes.fromhex(token)
    return token.encode("ascii")


def ja4_value(quic: bool, hello_version: int, ciphers, extensions, sigalgs, alpn_tokens) -> str:
    ciphers = [c for c in ciphers if c not in GREASE]
    exts_all = [e for e in extensions if e not in GREASE]
    sigalgs = [s for s in sigalgs if s not in GREASE]
    domain = 0 in exts_all
    alpns = [decode_alpn_token(t) for t in alpn_tokens]
    alpn = format_alpn(alpns[0]) if alpns else ["0", "0"]
    proto = "q" if quic else "t"
    version = version_to_ja4(hello_version)
    sni = "d" if domain else "i"
    ja4_a = f"{proto}{version}{sni}{min(99, len(ciphers)):02d}{min(99, len(exts_all)):02d}{alpn[0]}{alpn[1]}"
    ja4_b_raw = ",".join(f"{v:04x}" for v in sorted(ciphers))
    ja4_b = hashlib.sha256(ja4_b_raw.encode("ascii")).hexdigest()[:12]
    exts_c = sorted(e for e in exts_all if e not in (0, 16))
    ja4_c1 = ",".join(f"{v:04x}" for v in exts_c)
    ja4_c2 = ",".join(f"{v:04x}" for v in sigalgs)
    ja4_c = hashlib.sha256(f"{ja4_c1}_{ja4_c2}".encode("ascii")).hexdigest()[:12]
    return f"{ja4_a}_{ja4_b}_{ja4_c}"


def expected_for(h: dict) -> tuple[str, str, str]:
    j3 = ja3_string(h["hello_version"], h["ciphers"], h["extensions"], h["curves"], h["point_formats"])
    jh = hashlib.md5(j3.encode("ascii")).hexdigest()
    j4 = ja4_value(h["quic"], h["hello_version"], h["ciphers"], h["extensions"], h["sigalgs"], h["alpn"])
    return j3, jh, j4


def recover_fields(line: str) -> tuple[str, str, str, str]:
    parts = line.split(",")
    if len(parts) < 4:
        fail(f"CSV data line has fewer than 4 recovered fields: {line!r}")
    hid = parts[0]
    ja4 = parts[-1]
    ja3_hash = parts[-2]
    ja3_string_v = ",".join(parts[1:-2])
    return hid, ja3_string_v, ja3_hash, ja4


def run_probe(payload: dict, timeout: int = 20) -> tuple[str, str, str]:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    try:
        proc = subprocess.run(
            [str(PROBE)],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        fail("ja3_probe.py timed out")
    except OSError as exc:
        fail(f"failed to execute {PROBE}: {exc}")
    if proc.returncode != 0:
        fail(f"ja3_probe.py exit {proc.returncode} stderr={proc.stderr[:400]!r}")
    try:
        text = proc.stdout.decode("utf-8")
    except UnicodeDecodeError:
        fail("ja3_probe.py stdout is not UTF-8")
    if not text.endswith("\n"):
        fail("ja3_probe.py stdout missing trailing newline")
    lines = text.split("\n")
    if lines[-1] != "":
        fail("ja3_probe.py stdout missing trailing newline")
    lines = lines[:-1]
    if len(lines) != 3:
        fail(f"ja3_probe.py expected 3 lines, got {len(lines)}: {lines!r}")
    return lines[0], lines[1], lines[2]


def main() -> None:
    for path, digest in FILES.items():
        if not path.is_file():
            fail(f"missing {path}")
        if sha256_file(path) != digest:
            fail(f"do not modify files under /app: {path} hash mismatch")

    if not CSV_PATH.is_file():
        fail(f"missing {CSV_PATH}")
    raw = CSV_PATH.read_bytes()
    if raw == b"":
        fail("fingerprints.csv is empty")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        fail("fingerprints.csv is not UTF-8")
    if "\r" in text:
        fail("fingerprints.csv must use LF newlines")
    if not text.endswith("\n"):
        fail("fingerprints.csv missing trailing newline")
    lines = text.split("\n")[:-1]
    if len(lines) != 1 + len(HELLOs):
        fail(f"fingerprints.csv expected {1 + len(HELLOs)} lines, got {len(lines)}")
    if lines[0] != HEADER:
        fail(f"header {lines[0]!r} != {HEADER!r}")

    for i, h in enumerate(HELLOs, 1):
        line = lines[i]
        if '"' in line:
            fail(f"quoted fields forbidden on data line {i}: {line!r}")
        hid, j3, jh, j4 = recover_fields(line)
        ej3, ejh, ej4 = expected_for(h)
        if hid != h["id"]:
            fail(f"row {i} id {hid!r} != {h['id']!r}")
        if j3 != ej3:
            fail(f"{h['id']} ja3_string {j3!r} != {ej3!r}")
        if jh != ejh or len(jh) != 32 or any(c not in HEX for c in jh):
            fail(f"{h['id']} ja3_hash {jh!r} != {ejh!r}")
        if j4 != ej4 or len(j4) != 36 or j4.count("_") != 2:
            fail(f"{h['id']} ja4 {j4!r} != {ej4!r}")

    if not PROBE.is_file():
        fail(f"missing {PROBE}")
    if not (PROBE.stat().st_mode & stat.S_IXUSR):
        fail(f"{PROBE} is not executable")

    # Probe on corpus hellos (including hex ALPN for h5).
    for h in HELLOs:
        payload = {
            "quic": h["quic"],
            "hello_version": h["hello_version"],
            "ciphers": h["ciphers"],
            "extensions": h["extensions"],
            "curves": h["curves"],
            "point_formats": h["point_formats"],
            "sigalgs": h["sigalgs"],
            "alpn": h["alpn"],
            "sni": h["sni"],
        }
        got_j3, got_jh, got_j4 = run_probe(payload)
        ej3, ejh, ej4 = expected_for(h)
        if (got_j3, got_jh, got_j4) != (ej3, ejh, ej4):
            fail(f"probe {h['id']} {(got_j3, got_jh, got_j4)!r} != {(ej3, ejh, ej4)!r}")

    extra = {
        "quic": False,
        "hello_version": 771,
        "ciphers": [4865, 0x0A0A, 4866],
        "extensions": [0, 0x1A1A, 11, 10],
        "curves": [29, 0x2A2A],
        "point_formats": [0],
        "sigalgs": [1027, 0xBABA],
        "alpn": ["h2"],
        "sni": "probe.example",
    }
    ej3, ejh, ej4 = expected_for(
        dict(
            hello_version=extra["hello_version"],
            ciphers=extra["ciphers"],
            extensions=extra["extensions"],
            curves=extra["curves"],
            point_formats=extra["point_formats"],
            sigalgs=extra["sigalgs"],
            alpn=extra["alpn"],
            quic=extra["quic"],
        )
    )
    got_j3, got_jh, got_j4 = run_probe(extra)
    if (got_j3, got_jh, got_j4) != (ej3, ejh, ej4):
        fail(f"probe extra {(got_j3, got_jh, got_j4)!r} != {(ej3, ejh, ej4)!r}")

    extra2 = {
        "quic": True,
        "hello_version": 772,
        "ciphers": [4865],
        "extensions": [16, 10],  # no SNI extension 0 -> i
        "curves": [29],
        "point_formats": [],
        "sigalgs": [],
        "alpn": ["0154"],
        "sni": None,
    }
    ej3, ejh, ej4 = expected_for(
        dict(
            hello_version=extra2["hello_version"],
            ciphers=extra2["ciphers"],
            extensions=extra2["extensions"],
            curves=extra2["curves"],
            point_formats=extra2["point_formats"],
            sigalgs=extra2["sigalgs"],
            alpn=extra2["alpn"],
            quic=extra2["quic"],
        )
    )
    got_j3, got_jh, got_j4 = run_probe(extra2)
    if (got_j3, got_jh, got_j4) != (ej3, ejh, ej4):
        fail(f"probe extra2 {(got_j3, got_jh, got_j4)!r} != {(ej3, ejh, ej4)!r}")
    if "i" not in ej4[:4]:
        fail("internal: extra2 should be JA4 i marker")


if __name__ == "__main__":
    main()
