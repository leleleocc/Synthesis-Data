Chat-completion JSON bodies are being decoded into sampling parameters incorrectly. Illegal combinations are accepted, and legal bodies drop scoring and stop ids.

Bodies on disk:

- `/workspace/requests/stream_prompt_logprobs.json` — `stream` true with `prompt_logprobs` 1
- `/workspace/requests/top_logprobs_without_logprobs.json` — `top_logprobs` 5 with `logprobs` false
- `/workspace/requests/logprob_token_ids_without_logprobs.json` — `logprob_token_ids` `[11, 13]` with `logprobs` false
- `/workspace/requests/echo_stops.json` — `echo` true, `logprobs` true, `top_logprobs` 5, `logprob_token_ids` `[11, 13]`, `stop_token_ids` `[1, 2]`

Reproduce with `/opt/venv/bin/python3 /workspace/repro_protocol.py`. Captured wire symptoms are in `/workspace/symptoms.log`: streaming `prompt_logprobs` returns 200 instead of the error `prompt_logprobs are not available when stream=True`; `top_logprobs` / `logprob_token_ids` without `logprobs=true` also parse; `echo` leaves `prompt_logprobs` unset; server-default stop ids replace or drop request stops; `logprob_token_ids` still copies `top_logprobs` into `SamplingParams.logprobs`.

Restore decode so both the guards and the mapping hold. Validating without the echo/stop merge silently drops scoring. Mapping without the stream/logprobs guards accepts illegal requests.

Write `/workspace/sampling_params.json` with exactly:

```json
{
  "illegal": [
    {"path": "/workspace/requests/stream_prompt_logprobs.json", "accepted": false, "error_contains": "prompt_logprobs"},
    {"path": "/workspace/requests/top_logprobs_without_logprobs.json", "accepted": false, "error_contains": "logprobs"},
    {"path": "/workspace/requests/logprob_token_ids_without_logprobs.json", "accepted": false, "error_contains": "logprobs"}
  ],
  "mapped": [
    {
      "path": "/workspace/requests/echo_stops.json",
      "prompt_logprobs": 5,
      "logprobs": null,
      "logprob_token_ids": [11, 13],
      "stop_token_ids": [1, 2, 99]
    }
  ]
}
```

Mapping for the legal body uses `ChatCompletionRequest.to_sampling_params(max_tokens=16, default_sampling_params={"stop_token_ids": [99, 2]})`. Observable outcomes: `echo` with unset `prompt_logprobs` fills `prompt_logprobs` from `top_logprobs` (here 5); `SamplingParams.logprobs` is null when `logprob_token_ids` is set even if `top_logprobs` is 5; `stop_token_ids` is the request list first then server defaults with duplicates removed (`[1, 2, 99]`).

Work in `/workspace/repo`. Do not modify `/opt/venv`. Do not use the network.

You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
