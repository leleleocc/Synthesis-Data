#!/usr/bin/env python3
"""Discriminate OpenAI SSE framing vs special-token replica offset."""

from __future__ import annotations

import json
from pathlib import Path

TRACE = Path("/workspace/sse_decode_trace.json")
FIXTURE_SSE = Path(__file__).resolve().parent.parent / "fixtures" / "openai_chat_stream.sse"
FIXTURE_META = Path(__file__).resolve().parent.parent / "fixtures" / "expected_events.json"

REQUIRED_TOP = ("framing_ok", "special_token_offset_ok", "events")
REQUIRED_EVENT = ("raw_frame", "parsed", "token_index", "is_special")


def _load_json(path: Path) -> tuple[object | None, str]:
    if not path.is_file():
        return None, f"missing {path}"
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return None, f"empty {path}"
    try:
        return json.loads(raw), ""
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON in {path}: {exc}"


def _split_sse(raw: str) -> list[str]:
    if not raw.endswith("\n\n"):
        raw += "\n\n"
    frames = []
    rest = raw
    while rest:
        idx = rest.find("\n\n")
        if idx < 0:
            if rest.strip():
                frames.append(rest)
            break
        frames.append(rest[: idx + 2])
        rest = rest[idx + 2 :]
    return [frame for frame in frames if frame.strip()]


def _content_of(parsed: object) -> str | None:
    if parsed == "[DONE]":
        return None
    if not isinstance(parsed, dict):
        return None
    choices = parsed.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    delta = choices[0].get("delta") if isinstance(choices[0], dict) else {}
    if not isinstance(delta, dict):
        return ""
    content = delta.get("content")
    return content if isinstance(content, str) else ""


def _is_special(content: str | None, specials: list[str]) -> bool:
    if not content:
        return False
    if content in specials:
        return True
    if content.startswith("<|") and content.endswith("|>"):
        return True
    if content.startswith("|") and content.endswith("|>"):
        return True
    return False


def check_trace() -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    def rec(name: str, ok: bool, reason: str = "") -> None:
        results.append((name, ok, reason))

    meta, err = _load_json(FIXTURE_META)
    if not isinstance(meta, dict):
        rec("fixture", False, err or "expected_events.json is not an object")
        return results
    specials = list(meta["special_contents"])
    min_events = int(meta["min_data_events"])
    done_frame = str(meta["done_frame"])
    keep_alive = str(meta["keep_alive_comment"])

    if not FIXTURE_SSE.is_file() or not FIXTURE_SSE.read_text(encoding="utf-8").strip():
        rec("fixture sse", False, "missing pristine openai_chat_stream.sse")
        return results
    pristine = FIXTURE_SSE.read_text(encoding="utf-8")
    pristine_frames = _split_sse(pristine.replace("\r\n", "\n"))
    pristine_data = [frame for frame in pristine_frames if frame.startswith("data:")]
    rec(
        "fixture framing",
        all(frame.endswith("\n\n") for frame in pristine_data) and pristine_data[-1] == done_frame,
        "pristine fixture itself is not a well-framed OpenAI stream",
    )

    trace, err = _load_json(TRACE)
    if not isinstance(trace, dict):
        rec("normal case", False, err or "sse_decode_trace.json is not an object")
        return results

    missing = [key for key in REQUIRED_TOP if key not in trace]
    rec("schema required", not missing, f"missing {missing}")

    framing_ok = trace.get("framing_ok") is True
    offset_ok = trace.get("special_token_offset_ok") is True
    rec("framing_ok", framing_ok, "framing_ok must be true")
    rec("special_token_offset_ok", offset_ok, "special_token_offset_ok must be true")
    rec(
        "coupled flags",
        framing_ok and offset_ok,
        "SSE framing and special-token offset must both be true",
    )

    events = trace.get("events")
    rec("events", isinstance(events, list) and events, "events is too short or not a list")
    if not isinstance(events, list) or not events:
        return results

    rec(
        "not copied fixture bytes",
        TRACE.read_text(encoding="utf-8").strip() != pristine.strip(),
        "trace is a copy of the raw SSE fixture, not a decode trace",
    )

    token_indices: list[int] = []
    special_seen: list[str] = []
    keep_alive_as_event = False
    collapsed = False
    for index, event in enumerate(events):
        label = f"event[{index}]"
        if not isinstance(event, dict):
            rec(label, False, "event must be an object")
            continue
        raw_frame = event.get("raw_frame")
        parsed = event.get("parsed")
        if parsed is None:
            rec(
                f"{label} ignored non-event",
                isinstance(raw_frame, str)
                and raw_frame.lstrip().startswith(":")
                and raw_frame.endswith("\n\n"),
                "ignored non-events must be comment frames with parsed null",
            )
            continue
        e_missing = [key for key in REQUIRED_EVENT if key not in event]
        rec(f"{label} schema", not e_missing, f"missing {e_missing}")
        rec(
            f"{label} raw_frame",
            isinstance(raw_frame, str) and raw_frame.startswith("data: ") and raw_frame.endswith("\n\n"),
            f"raw_frame is not data: ...\\n\\n, got {raw_frame!r}",
        )
        if isinstance(raw_frame, str):
            if raw_frame.endswith("\n") and not raw_frame.endswith("\n\n"):
                collapsed = True
            if raw_frame.lstrip().startswith(":"):
                keep_alive_as_event = True
        rec(
            f"{label} not comment",
            not (isinstance(raw_frame, str) and raw_frame.lstrip().startswith(":")),
            "keep-alive comment was promoted into events",
        )
        if parsed == "[DONE]":
            rec(
                f"{label} done frame",
                raw_frame == done_frame,
                f"terminal sentinel raw_frame must be {done_frame!r}",
            )
            continue
        rec(
            f"{label} parsed object",
            isinstance(parsed, dict),
            "parsed must be the JSON object or [DONE]",
        )
        token_index = event.get("token_index")
        rec(
            f"{label} token_index",
            isinstance(token_index, int) and not isinstance(token_index, bool) and token_index >= 0,
            f"token_index={token_index} is not a non-negative integer",
        )
        if isinstance(token_index, int) and not isinstance(token_index, bool):
            token_indices.append(token_index)
        content = _content_of(parsed)
        expect_special = _is_special(content, specials)
        rec(
            f"{label} is_special",
            event.get("is_special") is expect_special,
            f"is_special={event.get('is_special')} for content {content!r}, expected {expect_special}",
        )
        if expect_special and isinstance(content, str):
            special_seen.append(content)

    data_event_count = sum(
        1 for event in events if isinstance(event, dict) and event.get("parsed") is not None
    )
    rec(
        "min data events",
        data_event_count >= min_events,
        f"need at least {min_events} data events, got {data_event_count}",
    )
    rec("collapsed terminator", not collapsed, "a data frame used a single trailing newline")
    rec(
        "keep-alive not a data event",
        not keep_alive_as_event,
        "a keep-alive was treated as a token data event",
    )
    data_events = [event for event in events if isinstance(event, dict) and event.get("parsed") is not None]
    rec(
        "terminal done present",
        bool(data_events) and data_events[-1].get("parsed") == "[DONE]",
        "stream does not close with data: [DONE]\\n\\n",
    )
    rec(
        "token indices ordered",
        token_indices == sorted(token_indices) and len(token_indices) == len(set(token_indices)),
        f"token_index values are not unique/ordered: {token_indices}",
    )
    rec(
        "not hardcoded stub indices",
        not token_indices or len(set(token_indices)) == len(token_indices),
        "token_index looks like a hardcoded stub",
    )
    rec(
        "special tokens recovered",
        bool(special_seen),
        f"no special-token events recovered; saw contents {special_seen}",
    )
    rec(
        "non-special tokens present",
        any(
            isinstance(event, dict) and event.get("is_special") is False and event.get("parsed") != "[DONE]"
            for event in events
        ),
        "every non-DONE event is marked special; replica lookback is not discriminating",
    )
    rec(
        "keep-alive form known",
        keep_alive == ": keep-alive\n\n",
        "fixture keep-alive comment form drifted",
    )

    return results


def main() -> int:
    failures = []
    for name, ok, reason in check_trace():
        status = "pass" if ok else "fail"
        line = f"{name}: {status}"
        if not ok:
            line += f" reason: {reason}"
            failures.append(line)
        print(line)
    if failures:
        print("error handling: fail reason: " + "; ".join(failures))
        return 1
    print("error handling: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
