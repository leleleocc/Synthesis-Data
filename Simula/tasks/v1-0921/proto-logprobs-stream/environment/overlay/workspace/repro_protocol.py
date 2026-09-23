#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, "/workspace/repo")
from vllm.entrypoints.openai.chat_completion.protocol import ChatCompletionRequest

DEFAULTS = {"stop_token_ids": [99, 2]}


def try_one(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    try:
        req = ChatCompletionRequest.model_validate(payload)
    except Exception as exc:
        print(path, "REJECTED", type(exc).__name__, str(exc).split("\\n")[0][:160])
        return
    print(path, "ACCEPTED")
    sp = req.to_sampling_params(max_tokens=16, default_sampling_params=DEFAULTS)
    print("  prompt_logprobs", sp.prompt_logprobs, "logprobs", sp.logprobs,
          "logprob_token_ids", sp.logprob_token_ids, "stop_token_ids", sp.stop_token_ids)


def main():
    for p in sorted(Path("/workspace/requests").glob("*.json")):
        try_one(p)


if __name__ == "__main__":
    main()
