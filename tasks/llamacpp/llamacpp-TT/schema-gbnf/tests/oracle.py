#!/usr/bin/env python3
"""Check GBNF conversion artifacts against the instruction and in-tree converter fingerprints."""
from __future__ import annotations

import json
import os
import re
import sys
from collections import OrderedDict
from pathlib import Path


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def load_ordered(path: Path):
    raw_b = path.read_bytes()
    if not raw_b.endswith(b"\n"):
        fail(f"{path} must end with a newline")
    raw = raw_b.decode("utf-8")
    decoder = json.JSONDecoder(object_pairs_hook=OrderedDict)
    obj, idx = decoder.raw_decode(raw)
    if raw[idx:].strip() != "":
        fail(f"{path} has trailing junk")
    return obj, raw


def has_root_rule(text: str) -> bool:
    for line in text.splitlines():
        if re.match(r"^\s*root\s*::=", line):
            return True
    return False


def looks_like_gbnf(text: str) -> bool:
    return bool(re.search(r"::=", text))


def integer_range_fingerprint(text: str) -> None:
    # In-tree converter emits a root rule plus a space rule and digit classes.
    # A naive "root ::= [0-9]+" is not json_schema_to_grammar.
    if "root ::=" not in text:
        fail("integer_range.gbnf missing root ::=")
    if "space ::=" not in text:
        fail("integer_range.gbnf missing space ::= (in-tree converter always emits it)")
    if "[" not in text or not re.search(r"\[[0-9]", text):
        fail("integer_range.gbnf missing digit character classes from the in-tree converter")


def enum_color_fingerprint(text: str) -> None:
    # String enum ["red","amber","green"] -> quoted JSON string literals.
    for color in ('\\"red\\"', '\\"amber\\"', '\\"green\\"', '"red"', '"amber"', '"green"'):
        pass
    if "red" not in text or "amber" not in text or "green" not in text:
        fail("enum_color.gbnf missing enum literals")
    if "root ::=" not in text:
        fail("enum_color.gbnf missing root ::=")


def object_closed_fingerprint(text: str) -> None:
    if "root ::=" not in text:
        fail("object_closed.gbnf missing root ::=")
    if "id" not in text or "name" not in text:
        fail("object_closed.gbnf missing property names")


def anyof_fingerprint(text: str) -> None:
    if "root ::=" not in text:
        fail("anyof_num_str.gbnf missing root ::=")
    if "n/a" not in text and "unknown" not in text:
        # converter quotes JSON strings; accept either raw or escaped
        if "n\\/a" not in text and "unknown" not in text:
            fail("anyof_num_str.gbnf missing string-enum alternatives")


def ref_node_fingerprint(text: str) -> None:
    if "root ::=" not in text:
        fail("ref_node.gbnf missing root ::=")
    if "leaf" not in text:
        fail("ref_node.gbnf missing leaf property from $ref")


FINGERPRINTS = {
    "integer_range": integer_range_fingerprint,
    "enum_color": enum_color_fingerprint,
    "object_closed": object_closed_fingerprint,
    "anyof_num_str": anyof_fingerprint,
    "ref_node": ref_node_fingerprint,
}


def main() -> None:
    schemas_dir = Path("/data/schemas")
    grammars_dir = Path("/results/grammars")
    report_path = Path("/results/grammar_report.json")
    if not schemas_dir.is_dir():
        fail("missing /data/schemas")
    schemas = sorted(p for p in schemas_dir.glob("*.json") if p.is_file())
    if not schemas:
        fail("no schema files")
    stems = [p.stem for p in schemas]
    files = [p.name for p in schemas]

    for p in schemas:
        gpath = grammars_dir / f"{p.stem}.gbnf"
        if not gpath.is_file():
            fail(f"missing {gpath}")
        text = gpath.read_text(encoding="utf-8")
        if not looks_like_gbnf(text):
            fail(f"{gpath} does not look like GBNF")
        if not has_root_rule(text):
            fail(f"{gpath} has no root rule")
        fp = FINGERPRINTS.get(p.stem)
        if fp is not None:
            fp(text)

    report, raw = load_ordered(report_path)
    if list(report.keys()) != ["schemas", "n_ok"]:
        fail(f"grammar_report.json keys {list(report.keys())} != ['schemas','n_ok']")
    if not isinstance(report["schemas"], list):
        fail("schemas must be an array")
    if not isinstance(report["n_ok"], int) or isinstance(report["n_ok"], bool):
        fail("n_ok must be a JSON integer")
    got_files = [e.get("file") for e in report["schemas"]]
    if got_files != sorted(files):
        fail(f"schemas not sorted by file: {got_files} vs {sorted(files)}")
    if len(report["schemas"]) != len(files):
        fail("schema count mismatch")
    n_ok = 0
    for entry, schema in zip(report["schemas"], sorted(schemas, key=lambda p: p.name)):
        if list(entry.keys()) != ["file", "stem", "n_bytes", "has_root", "parse_ok"]:
            fail(f"schema object keys {list(entry.keys())}")
        if entry["file"] != schema.name:
            fail(f"file {entry['file']} != {schema.name}")
        if entry["stem"] != schema.stem:
            fail(f"stem {entry['stem']} != {schema.stem}")
        gpath = grammars_dir / f"{schema.stem}.gbnf"
        nbytes = gpath.stat().st_size
        if entry["n_bytes"] != nbytes:
            fail(f"n_bytes {entry['n_bytes']} != {nbytes} for {schema.stem}")
        if entry["has_root"] is not True:
            fail(f"has_root is not true for {schema.stem}")
        if entry["parse_ok"] is not True:
            fail(f"parse_ok is not true for {schema.stem}")
        n_ok += 1
    if report["n_ok"] != n_ok:
        fail(f"n_ok {report['n_ok']} != {n_ok}")
    if not re.search(r'"has_root"\s*:\s*true', raw) or not re.search(r'"parse_ok"\s*:\s*true', raw):
        fail("has_root/parse_ok must be JSON true/false")
    print("oracle: grammars and report match")


if __name__ == "__main__":
    main()
