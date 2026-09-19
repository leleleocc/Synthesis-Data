import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from support import make_config
from runner.config import from_env
from runner.trace import TraceWriter


class TraceWriterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = make_config(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    @property
    def iteration_dir(self):
        return os.path.join(self.cfg.run_dir, "iterations", "0001")

    def read_status(self):
        with open(os.path.join(self.iteration_dir, "status.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def test_events_are_preserved_in_jsonl_chunks(self):
        writer = TraceWriter(self.cfg, 1)
        first = b'{"type":"assistant","text":"one"}\n'
        second = b'{"type":"tool","text":"two"}\n'
        writer.write_event(first)
        writer.write_event(second)
        writer.flush_chunk()
        writer.close()

        with open(os.path.join(self.iteration_dir, "output-000001.jsonl"), "rb") as fh:
            self.assertEqual(fh.read(), first + second)

    def test_chunk_names_are_monotonic_and_immutable(self):
        writer = TraceWriter(self.cfg, 1)
        writer.write_event(b"one\n")
        writer.flush_chunk()
        writer.write_event(b"two\n")
        writer.flush_chunk()
        writer.close()

        names = sorted(os.listdir(self.iteration_dir))
        self.assertEqual(names, ["output-000001.jsonl", "output-000002.jsonl", "status.json"])
        with open(os.path.join(self.iteration_dir, "output-000001.jsonl"), "rb") as fh:
            self.assertEqual(fh.read(), b"one\n")

    def test_status_tracks_sequence_and_finish(self):
        writer = TraceWriter(self.cfg, 3)
        writer.write_event(b"one\n")
        writer.flush_chunk()
        self.assertEqual(writer.status()["last_sequence"], 1)
        writer.finish(exit_code=7, elapsed_seconds=1.25)
        status = writer.status()
        self.assertEqual(status["iteration"], 3)
        self.assertEqual(status["last_sequence"], 1)
        self.assertTrue(status["complete"])
        self.assertEqual(status["exit_code"], 7)
        self.assertIsInstance(status["updated_at"], str)
        writer.close()

    def test_close_marks_unfinished_iteration_incomplete(self):
        writer = TraceWriter(self.cfg, 1)
        writer.write_event(b"partial\n")
        writer.close()

        status = self.read_status()
        self.assertFalse(status["complete"])
        self.assertIsNone(status["exit_code"])
        self.assertEqual(status["last_sequence"], 1)

    def test_trace_thresholds_are_configurable_from_environment(self):
        cfg = from_env({"TRACE_FLUSH_SECONDS": "9", "TRACE_CHUNK_BYTES": "12"})
        self.assertEqual(cfg.trace_flush_seconds, 9)
        self.assertEqual(cfg.trace_chunk_bytes, 12)


if __name__ == "__main__":
    unittest.main()
