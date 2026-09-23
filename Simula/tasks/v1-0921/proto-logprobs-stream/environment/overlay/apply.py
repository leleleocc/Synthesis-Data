#!/usr/bin/env python3
from pathlib import Path
import shutil

repo = Path("/workspace/repo")
proto = repo / "vllm/entrypoints/openai/chat_completion/protocol.py"
text = proto.read_text(encoding="utf-8")
old = """        if data.get("logprob_token_ids") and not data.get("logprobs"):
            raise VLLMValidationError(
                "when using `logprob_token_ids`, `logprobs` must be set to true.",
                parameter="logprob_token_ids",
            )

"""
if old not in text:
    raise SystemExit("logprob_token_ids guard not found")
text = text.replace(old, "", 1)
old = """        if (prompt_logprobs := data.get("prompt_logprobs")) is not None:
            if data.get("stream") and (prompt_logprobs > 0 or prompt_logprobs == -1):
                raise VLLMValidationError(
                    "`prompt_logprobs` are not available when `stream=True`.",
                    parameter="prompt_logprobs",
                )

            if prompt_logprobs < 0 and prompt_logprobs != -1:
                raise VLLMValidationError(
                    "`prompt_logprobs` must be a positive value or -1.",
                    parameter="prompt_logprobs",
                    value=prompt_logprobs,
                )
"""
new = """        if (prompt_logprobs := data.get("prompt_logprobs")) is not None:
            if prompt_logprobs < 0 and prompt_logprobs != -1:
                raise VLLMValidationError(
                    "`prompt_logprobs` must be a positive value or -1.",
                    parameter="prompt_logprobs",
                    value=prompt_logprobs,
                )
"""
if old not in text:
    raise SystemExit("stream prompt_logprobs guard not found")
text = text.replace(old, new, 1)
old = """            if (top_logprobs == -1 or top_logprobs > 0) and not data.get("logprobs"):
                raise VLLMValidationError(
                    "when using `top_logprobs`, `logprobs` must be set to true.",
                    parameter="top_logprobs",
                )
"""
if old not in text:
    raise SystemExit("top_logprobs guard not found")
text = text.replace(old, "", 1)
old = """        stop_token_ids = self.stop_token_ids
        default_stop_ids = default_sampling_params.get("stop_token_ids")
        if default_stop_ids:
            if not stop_token_ids:
                stop_token_ids = list(default_stop_ids)
            else:
                stop_token_ids = list(
                    dict.fromkeys([*stop_token_ids, *default_stop_ids])
                )

        prompt_logprobs = self.prompt_logprobs
        if prompt_logprobs is None and self.echo:
            prompt_logprobs = self.top_logprobs
"""
new = """        stop_token_ids = self.stop_token_ids
        prompt_logprobs = self.prompt_logprobs
"""
if old not in text:
    raise SystemExit("echo/stop merge block not found")
text = text.replace(old, new, 1)
old = """            logprobs=(
                self.top_logprobs
                if self.logprobs and not self.logprob_token_ids
                else None
            ),
"""
new = """            logprobs=self.top_logprobs,
"""
if old not in text:
    raise SystemExit("logprobs mapping not found")
proto.write_text(text.replace(old, new, 1), encoding="utf-8")

src = Path("/tmp/overlay/workspace")
for item in src.iterdir():
    dest = Path("/workspace") / item.name
    if item.is_dir():
        shutil.copytree(item, dest, dirs_exist_ok=True)
    else:
        shutil.copy2(item, dest)
print("overlay applied")
