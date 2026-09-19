#!/usr/bin/env python3
"""Independent host-OS policy / CIDR oracle matching util-cidr.c and util-host-os-info.c."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import stat
import subprocess
import sys
from pathlib import Path

APP = Path("/app")
RESULTS = Path("/results")
TOOL = RESULTS / "ospolicy"
JSON_PATH = RESULTS / "os-policy.json"
YAML_PATH = Path("/data/host-os-policy.yaml")

CIDR_C = APP / "src" / "util-cidr.c"
HINFO_C = APP / "src" / "util-host-os-info.c"
REASS_H = APP / "src" / "stream-tcp-reassemble.h"
YAML_IN = APP / "suricata.yaml.in"

CIDR_SHA256 = "48d775e8a891dcbe073c82e4040d048a713c6321996414a10838f974b41ed30a"
HINFO_SHA256 = "3d3b352ecdc08b2ebbe68faa35305f4858c01d1870a6ba0f812de12c70744802"
REASS_SHA256 = "9ce5977528637605597d2c402e211fb1f7adba69417bd552c67dca07576a2417"
YAML_IN_SHA256 = "21b03747eeb191357f93153a2382158b05fd946ac75fe188a6e8a6724f7dbe0f"

FLAVOURS = [
    "windows",
    "linux",
    "bsd",
    "bsd-right",
    "old-linux",
    "old-solaris",
    "solaris",
    "hpux10",
    "hpux11",
    "irix",
    "macos",
    "vista",
    "windows2k3",
]
VALID = set(FLAVOURS)

LOOKUP_IPS = [
    "0.0.0.0",
    "192.168.1.10",
    "10.1.2.3",
    "10.1.2.255",
    "172.16.0.1",
    "8.8.8.8",
    "2001:db8::1",
    "::1",
]

POLICY_DOC = {
    "windows": ["0.0.0.0/0"],
    "linux": ["10.0.0.0/8", "10.1.2.0/24", "2001:db8::/32"],
    "bsd": ["192.168.0.0/16"],
    "macos": ["::1"],
}

JSON_TOP_KEYS = ["lookups", "cidr"]
LOOKUP_KEYS = ["ip", "flavour"]
CIDR_KEYS = ["mask_24", "mask_bad", "mask_0", "mask_32", "get_24", "get_0", "get_33", "v6_7"]


def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(1)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def cidr_from_mask_dotted(dotted: str) -> int:
    packed = socket.inet_pton(socket.AF_INET, dotted)
    netmask_host = int.from_bytes(packed, "big")  # ntohl(s_addr)
    if netmask_host == 0:
        return 0
    p = 0
    seen_1 = False
    while netmask_host > 0:
        if netmask_host & 1:
            seen_1 = True
            p += 1
        else:
            if seen_1:
                return -1
        netmask_host >>= 1
    return p


def cidr_get(cidr: int) -> int:
    if cidr <= 0 or cidr > 32:
        return 0
    val = (0xFFFFFFFF << (32 - cidr)) & 0xFFFFFFFF
    net_bytes = val.to_bytes(4, "big")  # htonl result as memory on LE
    return int.from_bytes(net_bytes, "little")


def cidr_get_hex(cidr: int) -> str:
    return f"{cidr_get(cidr):08x}"


def cidr_get_ipv6(cidr: int) -> bytes:
    buf = bytearray(16)
    i = 0
    while cidr > 8:
        buf[i] = 0xFF
        cidr -= 8
        i += 1
    while cidr > 0:
        buf[i] |= 0x80
        cidr -= 1
        if cidr > 0:
            buf[i] = buf[i] >> 1
    return bytes(buf)


def expected_cidr_object() -> dict:
    return {
        "mask_24": cidr_from_mask_dotted("255.255.255.0"),
        "mask_bad": cidr_from_mask_dotted("255.255.0.42"),
        "mask_0": cidr_from_mask_dotted("0.0.0.0"),
        "mask_32": cidr_from_mask_dotted("255.255.255.255"),
        "get_24": cidr_get_hex(24),
        "get_0": cidr_get_hex(0),
        "get_33": cidr_get_hex(33),
        "v6_7": cidr_get_ipv6(7).hex(),
    }


class DuplicateError(Exception):
    pass


def parse_simple_yaml_map(text: str) -> dict:
    """Parse the flavour-root YAML mapping described in the instruction."""
    mapping: dict[str, list[str]] = {}
    current = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", raw)
        if m and not raw.startswith(" ") and not raw.startswith("\t") and not raw.startswith("-"):
            key = m.group(1)
            rest = m.group(2).strip()
            current = key
            mapping.setdefault(key, [])
            if rest.startswith("[") and rest.endswith("]"):
                inner = rest[1:-1].strip()
                if inner:
                    mapping[key].extend([x.strip().strip("'\"") for x in inner.split(",") if x.strip()])
            elif rest:
                mapping[key].append(rest.strip("'\""))
            continue
        m2 = re.match(r"^\s*-\s+(\S+)\s*$", raw)
        if m2 and current is not None:
            mapping[current].append(m2.group(1).strip("'\""))
            continue
    return mapping


def load_policy(mapping: dict) -> tuple[list[tuple[ipaddress._BaseNetwork, str]], list[tuple[ipaddress._BaseNetwork, str]]]:
    v4: list[tuple[ipaddress._BaseNetwork, str]] = []
    v6: list[tuple[ipaddress._BaseNetwork, str]] = []
    seen4 = set()
    seen6 = set()
    for flavour, addrs in mapping.items():
        if flavour not in VALID:
            continue
        for addr in addrs:
            a = addr.strip()
            if a.lower() == "default":
                # instruction: default means 0.0.0.0/0 or ::/0 according to family used
                # We expand both if the token is the string default, matching SCHInfoAddHostOSInfo
                # which picks family from is_ipv4 argument. For the YAML loader, family is
                # inferred from whether the address contains ':'.
                nets = []
            else:
                if a.count("/") == 0:
                    if ":" in a:
                        a = a + "/128"
                    else:
                        a = a + "/32"
                try:
                    net = ipaddress.ip_network(a, strict=False)
                except ValueError:
                    continue
                nets = [net]
            for net in nets:
                key = (int(net.network_address), net.prefixlen)
                if net.version == 4:
                    if key in seen4:
                        raise DuplicateError(a)
                    seen4.add(key)
                    v4.append((net, flavour))
                else:
                    if key in seen6:
                        raise DuplicateError(a)
                    seen6.add(key)
                    v6.append((net, flavour))
    return v4, v6


def lookup(ip_s: str, v4, v6) -> str:
    if "/" in ip_s:
        return "none"
    try:
        ip = ipaddress.ip_address(ip_s)
    except ValueError:
        return "none"
    tree = v4 if ip.version == 4 else v6
    best = None
    best_len = -1
    for net, flavour in tree:
        if ip in net and net.prefixlen >= best_len:
            # longest prefix; later equal-length would overwrite if we use >=
            # radix most-specific: longer prefix wins. equal length duplicate is an add error.
            if net.prefixlen > best_len:
                best = flavour
                best_len = net.prefixlen
    return best if best is not None else "none"


def compact_json(obj: dict) -> str:
    # lookups array of objects with ip, flavour then cidr object with fixed key order
    look_parts = []
    for item in obj["lookups"]:
        look_parts.append(
            "{"
            + json.dumps("ip")
            + ":"
            + json.dumps(item["ip"], separators=(",", ":"))
            + ","
            + json.dumps("flavour")
            + ":"
            + json.dumps(item["flavour"], separators=(",", ":"))
            + "}"
        )
    cidr_parts = []
    for k in CIDR_KEYS:
        cidr_parts.append(json.dumps(k) + ":" + json.dumps(obj["cidr"][k], separators=(",", ":")))
    return (
        "{"
        + json.dumps("lookups")
        + ":["
        + ",".join(look_parts)
        + "],"
        + json.dumps("cidr")
        + ":{"
        + ",".join(cidr_parts)
        + "}"
        + "}"
    )


def run_tool(args: list[str], stdin: bytes = b"", timeout: int = 20):
    try:
        proc = subprocess.run(
            [str(TOOL)] + args,
            input=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        fail(f"ospolicy timed out: {args}")
    except OSError as exc:
        fail(f"failed to execute {TOOL}: {exc}")
    return proc


def expect_line(proc, want: str, what: str) -> None:
    try:
        out = proc.stdout.decode("utf-8")
    except UnicodeDecodeError:
        fail(f"{what}: stdout not UTF-8")
    if proc.returncode != 0:
        fail(f"{what}: exit {proc.returncode} stderr={proc.stderr[:300]!r}")
    if out != want:
        fail(f"{what}: stdout {out!r} != {want!r}")


def main() -> None:
    for path, digest in (
        (CIDR_C, CIDR_SHA256),
        (HINFO_C, HINFO_SHA256),
        (REASS_H, REASS_SHA256),
        (YAML_IN, YAML_IN_SHA256),
    ):
        if not path.is_file() or sha256_file(path) != digest:
            fail(f"do not modify files under /app: {path} hash mismatch")

    if not TOOL.is_file():
        fail(f"missing {TOOL}")
    mode = TOOL.stat().st_mode
    if (mode & 0o777) != 0o755 and not (mode & stat.S_IXUSR):
        fail(f"{TOOL} must remain executable (mode 0755)")
    # Instruction: must be mode 0755
    if (mode & 0o777) != 0o755:
        fail(f"{TOOL} mode {oct(mode & 0o777)} != 0755")

    if not YAML_PATH.is_file():
        fail(f"missing {YAML_PATH}")
    ytext = YAML_PATH.read_text(encoding="utf-8")
    parsed = parse_simple_yaml_map(ytext)
    # Required flavour keys with listed CIDRs (extras of invalid flavours ignored).
    for flavour, addrs in POLICY_DOC.items():
        if flavour not in parsed:
            fail(f"{YAML_PATH} missing flavour {flavour}")
        got = parsed[flavour]
        # Compare as networks, order as listed
        if [str(ipaddress.ip_network(a, strict=False)) for a in got] != [
            str(ipaddress.ip_network(a, strict=False)) for a in addrs
        ]:
            # allow compact vs listed representation if the same set in order
            if got != addrs:
                fail(f"{YAML_PATH} {flavour} {got} != {addrs}")

    v4, v6 = load_policy(
        {k: v for k, v in parsed.items() if k in VALID}
    )
    # Ensure the required nets were loaded (invalid keys ignored).
    expected_lookups = [{"ip": ip, "flavour": lookup(ip, v4, v6)} for ip in LOOKUP_IPS]
    # Cross-check against POLICY_DOC directly as well.
    v4b, v6b = load_policy(POLICY_DOC)
    expected_from_doc = [{"ip": ip, "flavour": lookup(ip, v4b, v6b)} for ip in LOOKUP_IPS]
    if expected_lookups != expected_from_doc:
        fail(f"YAML at {YAML_PATH} does not implement the required policy mapping")

    exp_cidr = expected_cidr_object()
    exp_obj = {"lookups": expected_from_doc, "cidr": exp_cidr}

    if not JSON_PATH.is_file():
        fail(f"missing {JSON_PATH}")
    jraw = JSON_PATH.read_bytes()
    try:
        jtext = jraw.decode("utf-8")
    except UnicodeDecodeError:
        fail("os-policy.json is not UTF-8")
    if not jtext.endswith("\n") or jtext.count("\n") != 1:
        fail("os-policy.json must be one compact line plus trailing newline")
    line = jtext[:-1]
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as exc:
        fail(f"os-policy.json invalid JSON: {exc}")
    if not isinstance(obj, dict):
        fail("os-policy.json must be an object")
    if list(obj.keys()) != JSON_TOP_KEYS:
        fail(f"os-policy.json keys {list(obj.keys())} != {JSON_TOP_KEYS}")
    if not isinstance(obj["lookups"], list) or len(obj["lookups"]) != len(LOOKUP_IPS):
        fail("lookups array length mismatch")
    for i, item in enumerate(obj["lookups"]):
        if not isinstance(item, dict) or list(item.keys()) != LOOKUP_KEYS:
            fail(f"lookups[{i}] keys {item}")
        if item != expected_from_doc[i]:
            fail(f"lookups[{i}] {item} != {expected_from_doc[i]}")
    if not isinstance(obj["cidr"], dict) or list(obj["cidr"].keys()) != CIDR_KEYS:
        fail(f"cidr keys {list(obj.get('cidr', {}).keys()) if isinstance(obj.get('cidr'), dict) else obj.get('cidr')} != {CIDR_KEYS}")
    for k in CIDR_KEYS:
        if obj["cidr"][k] != exp_cidr[k]:
            fail(f"cidr.{k} {obj['cidr'][k]!r} != {exp_cidr[k]!r}")
    rebuilt = compact_json(exp_obj)
    if line != rebuilt:
        fail(f"os-policy.json not compact or extra spacing\n expected {rebuilt!r}\n got      {line!r}")

    # CLI cidr subcommands
    cases = [
        (["cidr", "ipv4-mask", "255.255.255.0"], f"{exp_cidr['mask_24']}\n"),
        (["cidr", "ipv4-mask", "255.255.0.42"], f"{exp_cidr['mask_bad']}\n"),
        (["cidr", "ipv4-mask", "0.0.0.0"], f"{exp_cidr['mask_0']}\n"),
        (["cidr", "ipv4-mask", "255.255.255.255"], f"{exp_cidr['mask_32']}\n"),
        (["cidr", "ipv4-prefix", "24"], f"{exp_cidr['get_24']}\n"),
        (["cidr", "ipv4-prefix", "0"], f"{exp_cidr['get_0']}\n"),
        (["cidr", "ipv4-prefix", "33"], f"{exp_cidr['get_33']}\n"),
        (["cidr", "ipv6-prefix", "7"], f"{exp_cidr['v6_7']}\n"),
        (["cidr", "ipv6-prefix", "8"], cidr_get_ipv6(8).hex() + "\n"),
        (["cidr", "ipv4-prefix", "1"], cidr_get_hex(1) + "\n"),
        (["cidr", "ipv4-mask", "255.0.0.0"], f"{cidr_from_mask_dotted('255.0.0.0')}\n"),
    ]
    for args, want in cases:
        proc = run_tool(args)
        expect_line(proc, want, " ".join(args))

    # load against the agent YAML
    stdin = "".join(ip + "\n" for ip in LOOKUP_IPS).encode("utf-8")
    proc = run_tool(["load", str(YAML_PATH)], stdin=stdin)
    want_lines = "".join(f"{ip} {lookup(ip, v4b, v6b)}\n" for ip in LOOKUP_IPS)
    expect_line(proc, want_lines, "ospolicy load corpus")

    extra_ips = ["10.0.0.1", "10.1.2.1", "192.168.255.1", "172.16.0.1", "2001:db8:1::1", "fe80::1", "127.0.0.1"]
    stdin2 = ("\n".join(extra_ips) + "\n\n").encode("utf-8")  # blank line skipped
    proc = run_tool(["load", str(YAML_PATH)], stdin=stdin2)
    want2 = "".join(f"{ip} {lookup(ip, v4b, v6b)}\n" for ip in extra_ips)
    expect_line(proc, want2, "ospolicy load extra")

    # Duplicate addresses: write a temp yaml under /tmp (verifier-only)
    dup_path = Path("/tmp/ospolicy-dup.yaml")
    dup_path.write_text("linux: [10.0.0.0/8, 10.0.0.0/8]\n", encoding="utf-8")
    proc = run_tool(["load", str(dup_path)], stdin=b"10.0.0.1\n")
    if proc.returncode != 1:
        fail(f"duplicate load exit {proc.returncode} != 1")
    err = proc.stderr.decode("utf-8", errors="replace")
    if err != "duplicate\n":
        fail(f"duplicate stderr {err!r} != 'duplicate\\n'")

    # Invalid flavour keys ignored
    ign_path = Path("/tmp/ospolicy-ignore.yaml")
    ign_path.write_text("no-such: [1.2.3.4]\nlinux: [10.0.0.0/8]\n", encoding="utf-8")
    proc = run_tool(["load", str(ign_path)], stdin=b"10.1.0.1\n8.8.8.8\n")
    expect_line(proc, "10.1.0.1 linux\n8.8.8.8 none\n", "invalid flavour ignored")


if __name__ == "__main__":
    main()
