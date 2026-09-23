#!/usr/bin/env python3
"""Independent verifier for schema-to-GBNF conversion."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

FIX_DIR = Path("/tests/fixtures/schemas")
DATA_DIR = Path("/data/schemas")
GRAM_DIR = Path("/results/grammars")
REPORT = Path("/results/grammar_report.json")
SCHEMA_CLI = Path("/results/bin/schema-gbnf")
CHECK_CLI = Path("/results/bin/gbnf-check")

STEMS = ["anyof_num_str", "enum_color", "integer_range", "object_closed", "ref_node"]
REPORT_KEYS = ["schemas", "n_ok"]
ENTRY_KEYS = ["file", "stem", "n_bytes", "has_root", "parse_ok"]

# Fragments from /app/tests/test-json-schema-to-grammar.cpp and the converter
# (json-schema-to-grammar.cpp). These are in-tree fingerprints, not a reimplementation.
FRAGMENTS = {
    "integer_range": [
        # min 3 (unbounded) from the in-tree test; with maximum 20 the converter
        # still emits a 3-based lower bound. Accept either the unbounded min-3
        # root or the closed 3..20 root produced by build_min_max_int.
        r'root\s*::=',
        r'\[3-9\]',
    ],
    "enum_color": [
        r'\\"red\\"',
        r'\\"amber\\"',
        r'\\"green\\"',
        r'root\s*::=',
    ],
    "object_closed": [
        r'id-kv\s*::=',
        r'name-kv\s*::=',
        r'char\+',  # minLength 1
        r'root\s*::=',
    ],
    "anyof_num_str": [
        r'alternative-0',
        r'alternative-1',
        r'root\s*::=',
        r'\\"n/a\\"',
        r'\\"unknown\\"',
    ],
    "ref_node": [
        r'ref-defs-node',
        r'leaf-kv\s*::=',
        r'root\s*::=',
    ],
}


def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def top_keys(text: str) -> list:
    return list(json.loads(text).keys())


def check_data_unmodified() -> None:
    if not DATA_DIR.is_dir():
        fail("missing /data/schemas")
    gold = sorted(p.name for p in FIX_DIR.glob("*.json"))
    got = sorted(p.name for p in DATA_DIR.glob("*.json"))
    if gold != got:
        fail(f"/data/schemas names {got} != fixture {gold}")
    for name in gold:
        if sha256(DATA_DIR / name) != sha256(FIX_DIR / name):
            fail(f"/data/schemas/{name} was modified")


def has_root_rule(text: str) -> bool:
    # llama_grammar_parser: identifiers are [A-Za-z0-9-]+ ; comments start with #
    stripped = []
    for line in text.splitlines():
        if "#" in line:
            line = line[: line.index("#")]
        stripped.append(line)
    body = "\n".join(stripped)
    return re.search(r'(?m)^\s*root\s*::=', body) is not None


def run_schema_gbnf(schema: Path) -> str:
    if not SCHEMA_CLI.is_file() or not os.access(SCHEMA_CLI, os.X_OK):
        fail("/results/bin/schema-gbnf must be an executable file")
    proc = subprocess.run(
        [str(SCHEMA_CLI), str(schema)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        fail(
            f"schema-gbnf {schema} exited {proc.returncode}\n"
            f"stdout: {proc.stdout[:400]!r}\nstderr: {proc.stderr[:800]!r}"
        )
    try:
        return proc.stdout.decode("utf-8")
    except UnicodeDecodeError as e:
        fail(f"schema-gbnf stdout is not UTF-8: {e}")
        return ""


def run_gbnf_check(path: Path) -> int:
    if not CHECK_CLI.is_file() or not os.access(CHECK_CLI, os.X_OK):
        fail("/results/bin/gbnf-check must be an executable file")
    proc = subprocess.run(
        [str(CHECK_CLI), str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    return proc.returncode


def check_report(text: str, files: dict[str, Path]) -> dict:
    if not text.endswith("\n"):
        fail("grammar_report.json must end with a newline")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        fail(f"grammar_report.json is not valid JSON: {e}")
    if not isinstance(obj, dict):
        fail("grammar_report.json must be a JSON object")
    if top_keys(text) != REPORT_KEYS:
        fail(f"grammar_report.json keys must be {REPORT_KEYS} in that order, got {top_keys(text)}")
    schemas = obj["schemas"]
    if not isinstance(schemas, list) or len(schemas) != 5:
        fail("schemas must be an array of 5 entries (one per /data/schemas/*.json)")
    files_listed = [e.get("file") for e in schemas]
    if files_listed != sorted(files_listed):
        fail(f"schemas must be sorted by file, got {files_listed}")
    for i, e in enumerate(schemas):
        if list(e.keys()) != ENTRY_KEYS:
            fail(f"schemas[{i}] keys must be {ENTRY_KEYS} in that order")
        if not isinstance(e["n_bytes"], int) or isinstance(e["n_bytes"], bool):
            fail("n_bytes must be an int")
        if e["has_root"] is not True and e["has_root"] is not False:
            fail("has_root must be a JSON bool")
        if e["parse_ok"] is not True and e["parse_ok"] is not False:
            fail("parse_ok must be a JSON bool")
        stem = e["stem"]
        if e["file"] != f"{stem}.json":
            fail(f"file/stem mismatch: {e}")
        gpath = files.get(stem)
        if gpath is None:
            fail(f"report references unknown stem {stem}")
        if e["n_bytes"] != gpath.stat().st_size:
            fail(f"{stem}: n_bytes {e['n_bytes']} != grammar size {gpath.stat().st_size}")
        if e["has_root"] is not True:
            fail(f"{stem}: has_root is not true")
        if e["parse_ok"] is not True:
            fail(f"{stem}: parse_ok is not true")
    if obj["n_ok"] != 5:
        fail(f"n_ok {obj['n_ok']} != 5")
    if not isinstance(obj["n_ok"], int) or isinstance(obj["n_ok"], bool):
        fail("n_ok must be an int")
    return obj


def main() -> None:
    check_data_unmodified()
    if not GRAM_DIR.is_dir():
        fail("missing /results/grammars")
    files = {}
    for stem in STEMS:
        p = GRAM_DIR / f"{stem}.gbnf"
        if not p.is_file() or p.stat().st_size == 0:
            fail(f"missing or empty {p}")
        text = p.read_text(encoding="utf-8")
        if not has_root_rule(text):
            fail(f"{p} does not define a root rule")
        for pat in FRAGMENTS[stem]:
            if re.search(pat, text) is None:
                fail(f"{stem}.gbnf is missing in-tree converter fingerprint /{pat}/")
        files[stem] = p

    # object_closed: required properties in original schema order (id then name)
    oc = files["object_closed"].read_text(encoding="utf-8")
    m = re.search(r'root\s*::=\s*(.+)', oc)
    if not m:
        fail("object_closed.gbnf has no root rule body")
    root_body = m.group(1)
    if "id-kv" not in root_body or "name-kv" not in root_body:
        fail("object_closed root does not sequence id-kv and name-kv")
    if root_body.find("id-kv") > root_body.find("name-kv"):
        fail("object_closed required props must follow original property order (id then name)")
    if "additional-kv" in oc:
        fail("object_closed has additionalProperties false; additional-kv should not appear")

    # integer_range: non-negative closed range 3..20 from the in-tree integer builder
    ir = files["integer_range"].read_text(encoding="utf-8")
    if re.search(r'"-"', ir) and "minimum" not in ir:
        # a leading minus in the integer rule would accept negatives; min is 3
        if re.search(r'root\s*::=.*"-"', ir, re.S):
            fail("integer_range root appears to allow negative integers")

    if not REPORT.is_file():
        fail("missing /results/grammar_report.json")
    check_report(REPORT.read_text(encoding="utf-8"), files)

    # behavior: schema-gbnf on the original fixtures matches the written grammars
    for stem in STEMS:
        out = run_schema_gbnf(DATA_DIR / f"{stem}.json")
        on_disk = files[stem].read_text(encoding="utf-8")
        if out.strip() != on_disk.strip():
            fail(f"schema-gbnf {stem}.json stdout does not match /results/grammars/{stem}.gbnf")

    # behavior: in-tree boolean schema fingerprint (test-json-schema-to-grammar.cpp)
    with tempfile.TemporaryDirectory(prefix="gbnf-cli-") as td:
        td_path = Path(td)
        sch = td_path / "boolean.json"
        sch.write_text('{"type": "boolean"}\n', encoding="utf-8")
        bout = run_schema_gbnf(sch)
        if 'root ::= ("true" | "false")' not in bout.replace(" ", " ").strip() and not re.search(
            r'root\s*::=\s*\("true"\s*\|\s*"false"\)', bout
        ):
            fail("schema-gbnf did not emit the in-tree boolean grammar fingerprint")
        # string minLength 1
        sch2 = td_path / "smin.json"
        sch2.write_text('{"type":"string","minLength":1}\n', encoding="utf-8")
        sout = run_schema_gbnf(sch2)
        if "char+" not in sout:
            fail("schema-gbnf string minLength 1 must use char+ (in-tree converter)")
        if re.search(r'root\s*::=\s*"\\\\"' , sout) is None and '\\"' not in sout and '"\\""' not in sout:
            # root ::= "\"" char+ "\""
            if "char+" not in sout:
                fail("schema-gbnf string grammar missing quotes/char+")

        # gbnf-check on produced grammars
        for stem in STEMS:
            rc = run_gbnf_check(files[stem])
            if rc != 0:
                fail(f"gbnf-check {stem}.gbnf exited {rc}, expected 0")

        good = td_path / "ok.gbnf"
        good.write_text('root ::= "ok"\n', encoding="utf-8")
        if run_gbnf_check(good) != 0:
            fail("gbnf-check rejected a trivial grammar that defines root")
        bad = td_path / "bad.gbnf"
        bad.write_text('foo ::= "ok"\n', encoding="utf-8")
        if run_gbnf_check(bad) == 0:
            fail("gbnf-check exited 0 on a grammar with no root rule")
        empty = td_path / "empty.gbnf"
        empty.write_text("", encoding="utf-8")
        if run_gbnf_check(empty) == 0:
            fail("gbnf-check exited 0 on an empty grammar")
        junk = td_path / "junk.gbnf"
        junk.write_text("this is not a grammar\n", encoding="utf-8")
        if run_gbnf_check(junk) == 0:
            fail("gbnf-check exited 0 on unparseable text")

    print("c4 checks passed", file=sys.stderr)


if __name__ == "__main__":
    main()
