The OpenAI-compatible chat completions service started through /opt/venv/bin/vllm is answering, but two prompts that share a long common prefix do not continue as a tokenizer-aligned replica of that prefix. Later turns that should have reused the overlapping token-id window drift away from the replica, and the replica's incremental decode of the same window does not stay lined up with the tokens the server reports.

Bring serving back to a state where both of the following hold together. Satisfying only one is failure.

Shared-prefix OpenAI chat/completions queries must rewrite the prefix fingerprint over the true token-id window so two requests that share a prefix yield continuations consistent with that prefix (the overlapping completion tokens match, and reuse agrees with the replica of the shared window).

The tokenizer replica offset on that same token-id window must agree with incremental detokenization: converting prompt ids to tokens must use a replica offset pairing whose tail and prefix/read offsets describe the hashed window, so replica text and server tokens stay aligned on that window.

Do not pull models or open unbounded network access. Drive checks through /opt/venv/bin/vllm and the OpenAI-compatible HTTP surface it exposes.

Write success evidence to /workspace/openai_compat_report.json as a single JSON object matching this schema. Both constraint flags must be true, and the numeric/trace fields must document both the shared-prefix query results and the replica offset alignment on the same token window.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "endpoint",
    "model",
    "prefix_cache_rewrite_ok",
    "tokenizer_replica_offset_ok",
    "shared_prefix_queries",
    "tokenizer_replica"
  ],
  "properties": {
    "endpoint": {
      "type": "string",
      "minLength": 1,
      "description": "OpenAI-compatible chat/completions URL used for the queries."
    },
    "model": {
      "type": "string",
      "minLength": 1
    },
    "prefix_cache_rewrite_ok": {
      "type": "boolean",
      "const": true
    },
    "tokenizer_replica_offset_ok": {
      "type": "boolean",
      "const": true
    },
    "shared_prefix_queries": {
      "type": "array",
      "minItems": 2,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "prompt",
          "shared_prefix",
          "completion_text",
          "prompt_token_ids",
          "completion_token_ids",
          "shared_window_token_ids",
          "matches_shared_prefix"
        ],
        "properties": {
          "prompt": { "type": "string", "minLength": 1 },
          "shared_prefix": { "type": "string", "minLength": 1 },
          "completion_text": { "type": "string" },
          "prompt_token_ids": {
            "type": "array",
            "minItems": 1,
            "items": { "type": "integer" }
          },
          "completion_token_ids": {
            "type": "array",
            "items": { "type": "integer" }
          },
          "shared_window_token_ids": {
            "type": "array",
            "minItems": 1,
            "items": { "type": "integer" }
          },
          "matches_shared_prefix": { "type": "boolean", "const": true }
        }
      }
    },
    "tokenizer_replica": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "token_window",
        "prefix_offset",
        "read_offset",
        "replica_tokens",
        "server_tokens",
        "windows_agree"
      ],
      "properties": {
        "token_window": {
          "type": "array",
          "minItems": 1,
          "items": { "type": "integer" }
        },
        "prefix_offset": { "type": "integer", "minimum": 0 },
        "read_offset": { "type": "integer", "minimum": 0 },
        "replica_tokens": {
          "type": "array",
          "minItems": 1,
          "items": { "type": "string" }
        },
        "server_tokens": {
          "type": "array",
          "minItems": 1,
          "items": { "type": "string" }
        },
        "windows_agree": { "type": "boolean", "const": true }
      }
    }
  }
}
```

The two shared_prefix_queries entries must use a common shared_prefix and distinct prompts. shared_window_token_ids must be the overlapping token-id window, and tokenizer_replica.token_window must be that same window. prefix_cache_rewrite_ok documents prefix-fingerprint rewrite; tokenizer_replica_offset_ok documents replica offset alignment. A report with only one of those true does not pass.

You have 1800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
