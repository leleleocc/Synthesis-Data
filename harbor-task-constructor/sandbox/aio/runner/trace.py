"""Durable JSONL output traces for one construction iteration."""

import json
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone


class TraceWriter:
    """Buffer Claude events locally and publish immutable iteration chunks."""

    def __init__(self, cfg, iteration: int):
        self.cfg = cfg
        self.iteration = iteration
        self.iteration_dir = os.path.join(
            cfg.run_dir, "iterations", f"{iteration:04d}"
        )
        os.makedirs(self.iteration_dir, exist_ok=True)
        self._local_dir = tempfile.mkdtemp(
            prefix=f"trace-{cfg.run_id}-{iteration:04d}-"
        )
        self._buffer = bytearray()
        self._sequence = 0
        self._next_chunk = 1
        self._last_flush = time.monotonic()
        self._complete = False
        self._exit_code = None
        self._closed = False
        self._write_status()

    def write_event(self, line: bytes):
        if self._closed:
            raise ValueError("trace writer is closed")
        if not isinstance(line, bytes):
            raise TypeError("trace events must be bytes")
        self._buffer.extend(line)
        self._sequence += 1
        self._write_status()
        if (
            len(self._buffer) >= self.cfg.trace_chunk_bytes
            or time.monotonic() - self._last_flush >= self.cfg.trace_flush_seconds
        ):
            self.flush_chunk()

    def flush_chunk(self):
        if self._closed:
            return
        if not self._buffer:
            return
        chunk_name = f"output-{self._next_chunk:06d}.jsonl"
        local_tmp = os.path.join(self._local_dir, f".{chunk_name}.tmp")
        local_final = os.path.join(self._local_dir, chunk_name)
        with open(local_tmp, "wb") as fh:
            fh.write(self._buffer)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(local_tmp, local_final)

        published_tmp = os.path.join(self.iteration_dir, f".{chunk_name}.tmp")
        shutil.copyfile(local_final, published_tmp)
        os.replace(published_tmp, os.path.join(self.iteration_dir, chunk_name))
        self._buffer.clear()
        self._next_chunk += 1
        self._last_flush = time.monotonic()
        self._write_status()

    def finish(self, exit_code: int, elapsed_seconds: float):
        if self._closed:
            return
        self.flush_chunk()
        self._complete = True
        self._exit_code = exit_code
        self._write_status()

    def close(self, incomplete: bool = True):
        if self._closed:
            return
        self.flush_chunk()
        if incomplete and not self._complete:
            self._complete = False
            self._exit_code = None
            self._write_status()
        self._closed = True
        shutil.rmtree(self._local_dir, ignore_errors=True)

    def status(self):
        return {
            "iteration": self.iteration,
            "last_sequence": self._sequence,
            "complete": self._complete,
            "exit_code": self._exit_code,
            "updated_at": self._updated_at,
        }

    def _write_status(self):
        self._updated_at = datetime.now(timezone.utc).isoformat()
        target = os.path.join(self.iteration_dir, "status.json")
        temporary = os.path.join(self.iteration_dir, ".status.json.tmp")
        with open(temporary, "w", encoding="utf-8") as fh:
            json.dump(self.status(), fh, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temporary, target)
