import argparse
import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sbx import cmd_task
from sbx import __main__


class Object:
    def __init__(self, key, body=b"", last_modified=None):
        self.key = key
        self.body = body
        self.size = len(body)
        self.last_modified = last_modified


class Body:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data


class FakeClient:
    def __init__(self, objects):
        self.objects = {obj.key: obj for obj in objects}
        self.requested = []

    def get_object(self, bucket, key):
        self.requested.append((bucket, key))
        return Body(self.objects[key].body)


def args(task_id="task-1", run=None, iteration=None, follow=False, raw=False):
    return argparse.Namespace(task_id=task_id, run=run, iteration=iteration,
                              follow=follow, raw=raw)


class TraceCommandTests(unittest.TestCase):
    def setUp(self):
        self.env = {"TOS_BUCKET": "bucket", "TOS_BUCKET_PATH": "/sandbox"}
        self.prefix = "sandbox/task-1/"

    def run_ids(self, objects):
        runs = set()
        for obj in objects:
            parts = obj.key.split("/")
            if "runs" in parts:
                i = parts.index("runs")
                if i + 1 < len(parts) and parts[i + 1]:
                    runs.add(parts[i + 1])
        return sorted(runs)

    def run_cmd(self, objects, listing_prefixes=None, **kwargs):
        client = FakeClient(objects)
        listing_prefixes = [] if listing_prefixes is None else listing_prefixes

        def listing(_client, _bucket, prefix):
            listing_prefixes.append(prefix)
            return [obj for obj in objects if obj.key.startswith(prefix)]

        output = io.StringIO()
        with mock.patch.object(cmd_task.settings, "load_env", return_value=self.env), \
             mock.patch.object(cmd_task.tos, "connect", return_value=client), \
             mock.patch.object(cmd_task.tos, "prefixes",
                               return_value=self.run_ids(objects)), \
             mock.patch.object(cmd_task.tos, "listing", side_effect=listing), \
             contextlib.redirect_stdout(output):
            cmd_task.trace_cmd(args(**kwargs))
        return output.getvalue(), client, listing_prefixes

    def test_latest_run_is_selected_from_immutable_trace_objects(self):
        objects = [
            Object(self.prefix + "runs/20260101/iterations/0001/output-000001.jsonl",
                   b'{"type":"assistant","timestamp":"12:00:01Z","text":"old"}\n'),
            Object(self.prefix + "runs/20260102/iterations/0001/output-000001.jsonl",
                   b'{"type":"assistant","timestamp":"12:00:02Z","text":"new"}\n'),
            Object(self.prefix + "runs/20260102/iterations/0001/status.json",
                   b'{"complete":true}\n'),
        ]
        output, client, prefixes = self.run_cmd(objects)
        self.assertIn("# run 20260102", output)
        self.assertIn("new", output)
        self.assertNotIn("old", output)
        self.assertIn(("bucket", self.prefix + "runs/20260102/iterations/0001/output-000001.jsonl"),
                      client.requested)
        self.assertEqual(prefixes, [self.prefix + "runs/20260102/iterations/"])

    def test_explicit_run_and_iteration_filter(self):
        objects = [
            Object(self.prefix + "runs/r1/iterations/0001/output-000001.jsonl",
                   b'{"type":"assistant","text":"one"}\n'),
            Object(self.prefix + "runs/r1/iterations/0002/output-000001.jsonl",
                   b'{"type":"tool_use","name":"ls","text":"two"}\n'),
            Object(self.prefix + "runs/r2/iterations/0002/output-000001.jsonl",
                   b'{"type":"assistant","text":"other"}\n'),
            Object(self.prefix + "runs/r1/iterations/0002/status.json",
                   b'{"complete":false}\n'),
        ]
        output, _, prefixes = self.run_cmd(objects, run="r1", iteration=2)
        self.assertIn("two", output)
        self.assertNotIn("one", output)
        self.assertNotIn("other", output)
        self.assertEqual(prefixes, [self.prefix + "runs/r1/iterations/0002/"])

    def test_raw_output_emits_exact_stored_lines(self):
        line = b'{"type":"assistant","text":"exact \\u2603"}\n'
        objects = [
            Object(self.prefix + "runs/r1/iterations/0001/output-000001.jsonl", line),
            Object(self.prefix + "runs/r1/iterations/0001/status.json", b'{"complete":true}\n'),
        ]
        output, _, _ = self.run_cmd(objects, run="r1", raw=True)
        self.assertEqual(output, line.decode())

    def test_missing_trace_exits_with_message(self):
        with self.assertRaisesRegex(SystemExit, "no trace objects"):
            self.run_cmd([])

    def test_incomplete_status_is_reported(self):
        objects = [
            Object(self.prefix + "runs/r1/iterations/0001/output-000001.jsonl",
                   b'{"type":"result","text":"partial"}\n'),
            Object(self.prefix + "runs/r1/iterations/0001/status.json",
                   b'{"complete":false,"last_sequence":1}\n'),
        ]
        output, _, _ = self.run_cmd(objects, run="r1")
        self.assertIn("incomplete", output.lower())

    def test_follow_polls_until_status_is_complete(self):
        pending = [
            Object(self.prefix + "runs/r1/iterations/0001/output-000001.jsonl",
                   b'{"type":"assistant","text":"partial"}\n'),
            Object(self.prefix + "runs/r1/iterations/0001/status.json",
                   b'{"complete":false}\n'),
        ]
        complete = pending[:-1] + [
            Object(self.prefix + "runs/r1/iterations/0001/status.json",
                   b'{"complete":true}\n'),
        ]
        client = FakeClient(pending)
        listings = iter([pending, complete])
        seen_prefixes = []

        def next_listing(_client, _bucket, prefix):
            seen_prefixes.append(prefix)
            current = next(listings)
            client.objects = {obj.key: obj for obj in current}
            return [obj for obj in current if obj.key.startswith(prefix)]

        output = io.StringIO()
        with mock.patch.object(cmd_task.settings, "load_env", return_value=self.env), \
             mock.patch.object(cmd_task.tos, "connect", return_value=client), \
             mock.patch.object(cmd_task.tos, "prefixes", return_value=["r1"]), \
             mock.patch.object(cmd_task.tos, "listing", side_effect=next_listing), \
             mock.patch.object(cmd_task.time, "sleep") as sleep, \
             contextlib.redirect_stdout(output):
            cmd_task.trace_cmd(args(run="r1", follow=True))
        sleep.assert_called_once_with(5)
        self.assertIn("partial", output.getvalue())
        self.assertTrue(all(p == self.prefix + "runs/r1/iterations/" for p in seen_prefixes))

    def test_parser_registers_trace_options(self):
        parser = __main__.build_parser()
        parsed = parser.parse_args(["task", "trace", "task-1", "--run", "r1",
                                    "--iteration", "2", "--follow", "--raw"])
        self.assertEqual(parsed.run, "r1")
        self.assertEqual(parsed.iteration, 2)
        self.assertTrue(parsed.follow)
        self.assertTrue(parsed.raw)


class StatusCommandTests(unittest.TestCase):
    def setUp(self):
        self.env = {"TOS_BUCKET": "bucket", "TOS_BUCKET_PATH": "/sandbox"}
        self.prefix = "sandbox/task-1/"

    def test_reads_result_json_per_run_without_walking_objects(self):
        objects = [
            Object(self.prefix + "status.json",
                   b'{"phase":"7","iteration":10,"max_iterations":10,'
                   b'"lives":10,"sandboxes":1,"done":false,"verified":null,'
                   b'"markers":{"measuring":false,"blocked":false}}\n'),
            Object(self.prefix + "runs/r1/result.json",
                   b'{"run_id":"r1","verdict":"pass","failures":0,"lease":"held",'
                   b'"attach":"reused","restored_files":3,"archived":"a.tar.gz",'
                   b'"done":false}\n'),
            Object(self.prefix + "runs/r1/iterations/0001/output-000001.jsonl",
                   b'{"type":"assistant","text":"noise"}\n'),
        ]
        client = FakeClient(objects)
        listed = []

        def no_listing(*_a, **_k):
            listed.append(True)
            raise AssertionError("status must not walk objects")

        output = io.StringIO()
        with mock.patch.object(cmd_task.settings, "load_env", return_value=self.env), \
             mock.patch.object(cmd_task.tos, "connect", return_value=client), \
             mock.patch.object(cmd_task.tos, "prefixes", return_value=["r1"]), \
             mock.patch.object(cmd_task.tos, "listing", side_effect=no_listing), \
             contextlib.redirect_stdout(output):
            cmd_task.status_cmd(argparse.Namespace(task_id="task-1", follow=False))
        text = output.getvalue()
        self.assertEqual(listed, [])
        self.assertIn("status.json", text)
        self.assertIn("r1", text)
        self.assertIn("verdict: pass", text)
        self.assertNotIn("noise", text)
        self.assertNotIn("output-000001.jsonl", text)


class LogsCommandTests(unittest.TestCase):
    def setUp(self):
        self.env = {"TOS_BUCKET": "bucket", "TOS_BUCKET_PATH": "/sandbox"}
        self.prefix = "sandbox/task-1/"

    def test_picks_newest_run_via_delimiter_not_full_listing(self):
        objects = [
            Object(self.prefix + "runs/20260101/bootstrap.log", b"old log\n"),
            Object(self.prefix + "runs/20260102/bootstrap.log", b"new log\n"),
        ]
        client = FakeClient(objects)
        listed = []

        def no_listing(*_a, **_k):
            listed.append(True)
            raise AssertionError("logs must not walk objects")

        output = io.StringIO()
        with mock.patch.object(cmd_task.settings, "load_env", return_value=self.env), \
             mock.patch.object(cmd_task.tos, "connect", return_value=client), \
             mock.patch.object(cmd_task.tos, "prefixes",
                               return_value=["20260101", "20260102"]), \
             mock.patch.object(cmd_task.tos, "listing", side_effect=no_listing), \
             contextlib.redirect_stdout(output):
            cmd_task.logs_cmd(argparse.Namespace(task_id="task-1", run=None))
        self.assertEqual(listed, [])
        self.assertEqual(output.getvalue(), "new log\n\n")
        self.assertIn(("bucket", self.prefix + "runs/20260102/bootstrap.log"),
                      client.requested)


if __name__ == "__main__":
    unittest.main()
