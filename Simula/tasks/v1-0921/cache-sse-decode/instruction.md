Token SSE bytes no longer round-trip through OpenAI event framing with a stable special-token index. The streaming path still produces token-shaped payloads, but a client that splits on the OpenAI SSE grammar cannot recover an ordered event list whose special-token positions match the tokenizer replica.

Work from the serving process at /usr/local/bin/vllm-nonroot-entrypoint.sh. The evidence of success is not a live metrics dump, not a cmake matrix, and not a kernel table. Write a round-trip decode TRACE at /workspace/sse_decode_trace.json that records wire-in bytes as structured events-out.

Two independent wire phenomena have to hold together. Event framing on the OpenAI chat stream must be `data: {json}\n\n` per chunk (a `data:` line, the JSON object, then a blank line so the next frame can start), and the stream must close with a terminal `data: [DONE]\n\n`. Idle keep-alives, if they appear, are comment frames of the exact form `: keep-alive\n\n`; they are ignored non-events, never promoted to `data:` payloads, and they still terminate with a blank line. A collapsed terminator (a single trailing newline, a missing blank line, or a missing `[DONE]`) makes adjacent chunks unparseable even when the JSON objects themselves look fine. A keep-alive that is emitted as a fake data field is not a comment and must not be treated as a token event.

Separately, special-token indices on that same stream must match the tokenizer replica used by incremental detokenization. The replica keeps a lookback window with the prefix cursor behind the read cursor and an extra tail so a special piece does not slide when only the prompt tail is converted. If that window is empty, if the prefix cursor is pinned to the read cursor, or if the extra special-token tail is dropped, token_index / is_special on the decoded events drift even when every SSE frame is well formed.

Restoring only the SSE grammar still mis-indexes special tokens. Restoring only the offset window still fails to parse the wire. Both must be true on one shared stream.

Do not download models, tokenizers, or other network artifacts. Local bytes already in the image are enough to exercise framing and offset. Reconstruct or capture an OpenAI SSE byte stream, decode it, and emit the trace.

The trace file /workspace/sse_decode_trace.json is JSON with this shape:

```
{
  "framing_ok": true,
  "special_token_offset_ok": true,
  "events": [
    {
      "raw_frame": "data: {\"object\":\"chat.completion.chunk\",...}\n\n",
      "parsed": {},
      "token_index": 0,
      "is_special": false
    }
  ]
}
```

`events` is the ordered list of OpenAI SSE data events after comment frames have been ignored. Each event has raw_frame (the exact `data: ...\n\n` bytes as text, including the blank-line terminator), parsed (the JSON object for that frame, or the string `[DONE]` for the terminal sentinel), token_index (the replica index for that piece), and is_special (true when the piece is a special token under the replica lookback window). The stream recorded by the trace must include proper `data: {json}\n\n` framing and a terminal `data: [DONE]\n\n`. Keep-alive comments of the form `: keep-alive\n\n`, if present on the wire, are omitted from `events` (or recorded only as ignored non-events with parsed null and no token assignment). `framing_ok` and `special_token_offset_ok` are both required true; either false means the round-trip did not complete.

You have 1800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
