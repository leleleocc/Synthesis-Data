#!/usr/bin/env python3
"""Independent classification.config + rules usage oracle."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

APP = Path("/app")
RESULTS = Path("/results")
JSON_PATH = RESULTS / "classtypes.json"
CSV_PATH = RESULTS / "classtype-usage.csv"
UNUSED_PATH = RESULTS / "unused.txt"
INDEX_DIR = RESULTS / "class-index"
LOADER = APP / "src" / "util-classification-config.c"
APP_CLASS = APP / "etc" / "classification.config"
APP_RULES = APP / "rules"

LOADER_SHA256 = "4800475c7541a011b728eb1a9ec6eb953ee049679ca945c66a4b20e72f21c377"
CLASS_SHA256 = "54c5b94ba7cb7e1371c1c967dd8c3b95960938eaed6cecb8788195c19622cbd6"
RULES_SHA256 = "67a27ddf545f77bbf669775a4f1a47f8043a11e1c51f6b890a4fa9221a3108cf"

REGEX = re.compile(
    r"^\s*config\s*classification\s*:\s*([a-zA-Z][a-zA-Z0-9-_]*)\s*,\s*(.+)\s*,\s*(\d+)\s*$"
)
JSON_KEYS = ["id", "name", "description", "priority"]


def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(1)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def rules_digest(rules_dir: Path) -> str:
    files = sorted(
        (p for p in rules_dir.rglob("*.rules") if p.is_file()),
        key=lambda p: p.name.encode("utf-8"),
    )
    if not files:
        fail(f"no *.rules under {rules_dir}")
    h = hashlib.sha256()
    for path in files:
        h.update(path.name.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
    return h.hexdigest()


def is_blank_or_comment(line: str) -> bool:
    for ch in line:
        if ch == "#":
            return True
        if not ch.isspace():
            return False
    return True


def load_classtypes(text: str) -> list[dict]:
    stored = []
    seen = set()
    index = 1
    for line in text.splitlines():
        if is_blank_or_comment(line):
            continue
        m = REGEX.match(line)
        if not m:
            # invalid line: C increments errors, does not increment id
            continue
        name = m.group(1).lower()
        desc = m.group(2)
        priority = int(m.group(3), 10)
        ct_id = index
        index += 1  # id assigned on successful regex+priority parse, even if duplicate later
        if name in seen:
            continue
        seen.add(name)
        stored.append({"id": ct_id, "name": name, "description": desc, "priority": priority})
    return stored


def is_rule_line(line: str) -> bool:
    i = 0
    while i < len(line) and line[i] in " \t\r\v\f":
        i += 1
    if i >= len(line):
        return False
    return line[i] != "#"


def usage_for(stored: list[dict], rules_dir: Path) -> dict:
    names = [c["name"] for c in stored]
    # classtype:<name> as a rule option; match the exact normalized name
    pats = {n: re.compile(r"classtype:" + re.escape(n) + r"(?![A-Za-z0-9_-])") for n in names}
    usage = {n: {"rule_count": 0, "files": set()} for n in names}
    for path in sorted(rules_dir.rglob("*.rules")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if not is_rule_line(line):
                continue
            for n, pat in pats.items():
                if pat.search(line):
                    usage[n]["rule_count"] += 1
                    usage[n]["files"].add(path.name)
    return usage


def compact_array(items: list[dict]) -> str:
    objs = []
    for it in items:
        parts = [json.dumps(k) + ":" + json.dumps(it[k], separators=(",", ":")) for k in JSON_KEYS]
        objs.append("{" + ",".join(parts) + "}")
    return "[" + ",".join(objs) + "]"


def main() -> None:
    if not LOADER.is_file():
        fail(f"missing {LOADER}")
    if sha256_file(LOADER) != LOADER_SHA256:
        fail("do not modify files under /app: util-classification-config.c hash mismatch")
    if not APP_CLASS.is_file():
        fail(f"missing {APP_CLASS}")
    if sha256_file(APP_CLASS) != CLASS_SHA256:
        fail("do not modify files under /app: classification.config hash mismatch")
    if not APP_RULES.is_dir():
        fail(f"missing {APP_RULES}")
    if rules_digest(APP_RULES) != RULES_SHA256:
        fail("do not modify files under /app: rules/*.rules hash mismatch")

    stored = load_classtypes(APP_CLASS.read_text(encoding="utf-8"))
    if not stored:
        fail("internal: no stored classtypes")
    usage = usage_for(stored, APP_RULES)

    if not JSON_PATH.is_file():
        fail(f"missing {JSON_PATH}")
    jraw = JSON_PATH.read_bytes()
    try:
        jtext = jraw.decode("utf-8")
    except UnicodeDecodeError:
        fail("classtypes.json is not UTF-8")
    if not jtext.endswith("\n") or jtext.count("\n") != 1:
        fail("classtypes.json must be a single compact line plus trailing newline")
    line = jtext[:-1]
    try:
        arr = json.loads(line)
    except json.JSONDecodeError as exc:
        fail(f"classtypes.json invalid JSON: {exc}")
    if not isinstance(arr, list):
        fail("classtypes.json must be a JSON array")
    if len(arr) != len(stored):
        fail(f"classtypes.json length {len(arr)} != {len(stored)}")
    rebuilt = compact_array(stored)
    if line != rebuilt:
        # also verify content/order even if compact rebuild differs due to extras
        fail("classtypes.json does not match loader-stored classtypes (compact, id order)")
    ids = [x["id"] for x in stored]
    if ids != sorted(ids):
        fail("internal: stored ids not increasing")

    if not CSV_PATH.is_file():
        fail(f"missing {CSV_PATH}")
    craw = CSV_PATH.read_bytes()
    try:
        ctext = craw.decode("utf-8")
    except UnicodeDecodeError:
        fail("classtype-usage.csv is not UTF-8")
    if "\r" in ctext:
        fail("classtype-usage.csv must use LF newlines")
    if not ctext.endswith("\n"):
        fail("classtype-usage.csv missing trailing newline")
    clines = ctext.split("\n")[:-1]
    header = "name,priority,rule_count,files"
    if not clines or clines[0] != header:
        fail(f"classtype-usage.csv header {clines[:1]!r} != {header!r}")
    by_name = sorted(stored, key=lambda c: c["name"].encode("utf-8"))
    if len(clines) != 1 + len(by_name):
        fail(f"classtype-usage.csv expected {1 + len(by_name)} lines, got {len(clines)}")
    unused_names = []
    for i, ct in enumerate(by_name, 1):
        line = clines[i]
        if '"' in line:
            fail(f"quotes forbidden: {line!r}")
        parts = line.split(",")
        if len(parts) != 4:
            fail(f"usage row {i} must have 4 fields, got {len(parts)}: {line!r}")
        files = sorted(usage[ct["name"]]["files"])
        files_field = ";".join(files)
        want = [
            ct["name"],
            str(ct["priority"]),
            str(usage[ct["name"]]["rule_count"]),
            files_field,
        ]
        if parts != want:
            fail(f"usage row {i} {parts} != {want}")
        if usage[ct["name"]]["rule_count"] == 0:
            unused_names.append(ct["name"])

    if not UNUSED_PATH.is_file():
        fail(f"missing {UNUSED_PATH}")
    uraw = UNUSED_PATH.read_bytes()
    if not unused_names:
        if uraw != b"":
            fail("unused.txt must be empty (zero bytes) when none unused")
    else:
        try:
            utext = uraw.decode("utf-8")
        except UnicodeDecodeError:
            fail("unused.txt is not UTF-8")
        if "\r" in utext:
            fail("unused.txt must use LF newlines")
        if not utext.endswith("\n"):
            fail("unused.txt missing trailing newline")
        ulines = utext.split("\n")[:-1]
        if ulines != unused_names:
            fail(f"unused.txt {ulines} != {unused_names}")

    if not INDEX_DIR.is_dir():
        fail(f"missing {INDEX_DIR}")
    index_files = sorted(p.name for p in INDEX_DIR.iterdir() if p.is_file())
    want_files = [f"{ct['id']}.txt" for ct in stored]
    extra = set(index_files) - set(want_files)
    missing = set(want_files) - set(index_files)
    if extra or missing:
        fail(f"class-index extra={sorted(extra)} missing={sorted(missing)}")
    for ct in stored:
        p = INDEX_DIR / f"{ct['id']}.txt"
        raw = p.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            fail(f"{p} is not UTF-8")
        want = f"{ct['name']}\n{ct['priority']}\n"
        if text != want:
            fail(f"{p} {text!r} != {want!r}")


if __name__ == "__main__":
    main()
