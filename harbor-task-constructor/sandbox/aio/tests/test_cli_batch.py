import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sbx import cmd_batch, tos


class Prefix:
    def __init__(self, prefix):
        self.prefix = prefix


class ListResult:
    def __init__(self, prefixes, truncated=False, token=None):
        self.common_prefixes = prefixes
        self.is_truncated = truncated
        self.next_continuation_token = token
        self.contents = []


class FakeTos:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def list_objects_type2(self, bucket, prefix, delimiter="", continuation_token="", max_keys=1000):
        self.calls.append({"bucket": bucket, "prefix": prefix,
                           "delimiter": delimiter, "token": continuation_token})
        return self.pages.pop(0)


class PrefixesTests(unittest.TestCase):
    def test_returns_first_segment_names(self):
        client = FakeTos([
            ListResult([
                Prefix("sandbox/my-batch/sglang-fp8/"),
                Prefix("sandbox/my-batch/sglang-int4/"),
            ]),
        ])
        names = tos.prefixes(client, "bucket", "sandbox/my-batch/")
        self.assertEqual(names, ["sglang-fp8", "sglang-int4"])
        self.assertEqual(client.calls[0]["delimiter"], "/")

    def test_pages(self):
        client = FakeTos([
            ListResult([Prefix("sandbox/my-batch/a/")], truncated=True, token="t"),
            ListResult([Prefix("sandbox/my-batch/b/")]),
        ])
        names = tos.prefixes(client, "bucket", "sandbox/my-batch/")
        self.assertEqual(names, ["a", "b"])
        self.assertEqual(len(client.calls), 2)


def batch_args(**kwargs):
    base = dict(directory="my-batch", name=None, template="harbor-constructor",
                dry_run=False)
    base.update(kwargs)
    return argparse.Namespace(**base)


class PushTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.join(self.tmp.name, "my-batch")
        os.makedirs(os.path.join(self.root, "sglang-fp8", "task"))
        os.makedirs(os.path.join(self.root, "sglang-int4", "task"))
        os.makedirs(os.path.join(self.root, ".skip-me"))
        os.makedirs(os.path.join(self.root, "seed"))  # reserved name
        with open(os.path.join(self.root, "batch.json"), "w") as fh:
            fh.write("{}")  # file, not a candidate

    def test_discovers_two_candidates_skips_dot_and_reserved(self):
        names = cmd_batch._candidates(self.root)
        self.assertEqual(names, ["sglang-fp8", "sglang-int4"])

    def test_push_calls_task_push_per_candidate_and_writes_batch_json(self):
        pushed = []
        recorded = []

        def fake_push(env, client, task_id, directory):
            pushed.append((task_id, directory))
            return "stamp.tar.gz"

        def fake_tos_put(client, bucket, key, path, label, ckpt_dir=None):
            with open(path) as fh:
                recorded.append((key, fh.read()))

        env = {"TOS_BUCKET": "b", "TOS_BUCKET_PATH": "/sandbox"}
        output = io.StringIO()
        with mock.patch.object(cmd_batch.settings, "load_env", return_value=env), \
             mock.patch.object(cmd_batch.settings, "need", side_effect=lambda e, k: e[k]), \
             mock.patch.object(cmd_batch.tos, "connect", return_value=object()), \
             mock.patch.object(cmd_batch.tos, "put", fake_tos_put), \
             mock.patch.object(cmd_batch.cmd_task, "_push", fake_push), \
             mock.patch.object(cmd_batch.cmd_task, "_check_task_id", lambda x: None), \
             contextlib.redirect_stdout(output):
            cmd_batch.push_cmd(batch_args(directory=self.root, template="tmpl"))
        self.assertEqual(
            [p[0] for p in pushed],
            ["my-batch/sglang-fp8", "my-batch/sglang-int4"],
        )
        self.assertEqual(
            [p[1] for p in pushed],
            [os.path.join(self.root, "sglang-fp8"),
             os.path.join(self.root, "sglang-int4")],
        )
        self.assertEqual([k for k, _ in recorded], ["sandbox/my-batch/batch.json"])
        body = json.loads(next(c for k, c in recorded if k.endswith("batch.json")))
        self.assertEqual(body["template"], "tmpl")
        self.assertIn("created_at", body)


class ClassifyTests(unittest.TestCase):
    cap = 10

    def test_queued_when_no_status(self):
        self.assertEqual(cmd_batch.classify(None, live=False, per_line_cap=self.cap), "queued")

    def test_verified_beats_live(self):
        st = {"done": True, "verified": "verified", "sandboxes": 2,
              "markers": {"measuring": False, "blocked": False}}
        self.assertEqual(cmd_batch.classify(st, live=True, per_line_cap=self.cap), "verified")

    def test_blocked(self):
        st = {"done": False, "verified": None, "sandboxes": 4,
              "markers": {"measuring": False, "blocked": True}}
        self.assertEqual(cmd_batch.classify(st, live=False, per_line_cap=self.cap), "blocked")

    def test_stopped_at_cap(self):
        st = {"done": False, "verified": None, "sandboxes": 10,
              "markers": {"measuring": False, "blocked": False}}
        self.assertEqual(cmd_batch.classify(st, live=False, per_line_cap=self.cap), "stopped")

    def test_not_stopped_if_done(self):
        st = {"done": True, "verified": "failed", "sandboxes": 10,
              "markers": {"measuring": False, "blocked": False}}
        # .done but verify failed is NOT terminal — keep running
        self.assertEqual(cmd_batch.classify(st, live=False, per_line_cap=self.cap), "idle")

    def test_measuring(self):
        st = {"done": False, "sandboxes": 1,
              "markers": {"measuring": True, "blocked": False}}
        self.assertEqual(cmd_batch.classify(st, live=True, per_line_cap=self.cap), "measuring")

    def test_working(self):
        st = {"done": False, "sandboxes": 1,
              "markers": {"measuring": False, "blocked": False}}
        self.assertEqual(cmd_batch.classify(st, live=True, per_line_cap=self.cap), "working")

    def test_idle(self):
        st = {"done": False, "sandboxes": 1,
              "markers": {"measuring": False, "blocked": False}}
        self.assertEqual(cmd_batch.classify(st, live=False, per_line_cap=self.cap), "idle")


class StatusTests(unittest.TestCase):
    def test_table_shows_measuring_and_queued(self):
        env = {
            "TOS_BUCKET": "b",
            "TOS_BUCKET_PATH": "/sandbox",
            "VEFAAS_FUNCTION_ID": "fn",
        }
        measuring = {
            "done": False,
            "sandboxes": 1,
            "lives": 3,
            "phase": "4b",
            "iteration": 2,
            "max_iterations": 10,
            "markers": {"measuring": True, "blocked": False},
            "updated_at": "2026-09-15T12:00:00+00:00",
        }

        def fake_get_json(_client, _bucket, key):
            if key.endswith("sglang-fp8/status.json"):
                return measuring
            return None

        sandbox = mock.Mock(status="Ready", metadata={"task": "my-batch/sglang-fp8"})
        listed = mock.Mock(sandboxes=[sandbox])
        output = io.StringIO()
        with mock.patch.object(cmd_batch.settings, "load_env", return_value=env), \
             mock.patch.object(cmd_batch.settings, "need", side_effect=lambda e, k: e[k]), \
             mock.patch.object(cmd_batch.tos, "connect", return_value=object()), \
             mock.patch.object(cmd_batch.tos, "prefixes",
                               return_value=["sglang-fp8", "qwen-gptq"]), \
             mock.patch.object(cmd_batch, "_get_json", side_effect=fake_get_json, create=True), \
             mock.patch.object(cmd_batch.faas, "configure", return_value=object()), \
             mock.patch.object(cmd_batch.faas, "list_sandboxes", return_value=listed), \
             contextlib.redirect_stdout(output):
            cmd_batch.status_cmd(argparse.Namespace(batch="my-batch"))
        text = output.getvalue()
        self.assertIn("measuring", text)
        self.assertIn("queued", text)
        self.assertIn("sglang-fp8", text)
        self.assertIn("qwen-gptq", text)


class ReconcileTests(unittest.TestCase):
    def test_order_queued_before_idle_then_name(self):
        rows = [
            {"name": "b", "state": "idle"},
            {"name": "a", "state": "queued"},
            {"name": "c", "state": "queued"},
            {"name": "d", "state": "working"},
        ]
        self.assertEqual(cmd_batch._next_to_open(rows), ["a", "c", "b"])

    def test_gates(self):
        self.assertTrue(cmd_batch._admitted(global_live=59, max_sandboxes=60,
                                            measuring=10, max_measuring=24))
        self.assertFalse(cmd_batch._admitted(global_live=60, max_sandboxes=60,
                                             measuring=10, max_measuring=24))
        self.assertFalse(cmd_batch._admitted(global_live=10, max_sandboxes=60,
                                             measuring=24, max_measuring=24))

    def test_dry_run_opens_queued_then_idle_without_create(self):
        env = {
            "TOS_BUCKET": "b",
            "TOS_BUCKET_PATH": "/sandbox",
            "VEFAAS_FUNCTION_ID": "fn",
        }
        created = []

        def fake_get_json(_client, _bucket, key):
            if key.endswith("batch.json"):
                return {"template": "tmpl"}
            if key.endswith("idle-one/status.json"):
                return {"done": False, "sandboxes": 1,
                        "markers": {"measuring": False, "blocked": False}}
            return None  # queued-a, queued-c have no status.json

        listed = mock.Mock(sandboxes=[])
        output = io.StringIO()
        with mock.patch.object(cmd_batch.settings, "load_env", return_value=env), \
             mock.patch.object(cmd_batch.settings, "need", side_effect=lambda e, k: e[k]), \
             mock.patch.object(cmd_batch.tos, "connect", return_value=object()), \
             mock.patch.object(cmd_batch.tos, "prefixes",
                               return_value=["idle-one", "queued-c", "queued-a"]), \
             mock.patch.object(cmd_batch, "_get_json", side_effect=fake_get_json), \
             mock.patch.object(cmd_batch.faas, "configure", return_value=object()), \
             mock.patch.object(cmd_batch.faas, "list_sandboxes", return_value=listed), \
             mock.patch.object(cmd_batch, "_open_one",
                               side_effect=lambda *a, **k: created.append(a)), \
             contextlib.redirect_stdout(output):
            cmd_batch.reconcile_cmd(argparse.Namespace(
                batch="my-batch", max_sandboxes=60, max_measuring=24,
                max_sandboxes_per_line=10, dry_run=True))
        text = output.getvalue()
        self.assertEqual(created, [])
        self.assertIn("open my-batch/queued-a", text)
        self.assertIn("open my-batch/queued-c", text)
        self.assertIn("open my-batch/idle-one", text)
        # queued before idle: first open line is queued-a
        opens = [ln for ln in text.splitlines() if "open my-batch/" in ln]
        self.assertEqual(opens[0].strip(), "open my-batch/queued-a")
        self.assertEqual(opens[1].strip(), "open my-batch/queued-c")
        self.assertEqual(opens[2].strip(), "open my-batch/idle-one")


class ListTests(unittest.TestCase):
    def test_rows_are_batch_meta_not_per_candidate_state(self):
        env = {
            "TOS_BUCKET": "b",
            "TOS_BUCKET_PATH": "/sandbox",
            "VEFAAS_FUNCTION_ID": "fn",
        }
        prefix_calls = []
        json_keys = []

        def fake_prefixes(_client, _bucket, prefix):
            prefix_calls.append(prefix)
            if prefix.rstrip("/").endswith("sandbox"):
                return ["_runtime", "_templates", "my-batch",
                        "harbor-constructor-sglang-fp8", "other-batch"]
            if prefix.endswith("my-batch/"):
                return ["sglang-fp8", "sglang-int4"]
            if prefix.endswith("other-batch/"):
                return ["one"]
            return ["seed", "archives", "runs"]

        def fake_get_json(_client, _bucket, key):
            json_keys.append(key)
            if key.endswith("my-batch/batch.json"):
                return {"template": "harbor-constructor",
                        "created_at": "2026-09-15T00:00:00+00:00"}
            if key.endswith("other-batch/batch.json"):
                return {"template": "hello-world"}
            return None

        sandboxes = [
            mock.Mock(status="Ready",
                      metadata={"task": "my-batch/sglang-fp8", "batch": "my-batch"}),
            mock.Mock(status="Failed",
                      metadata={"task": "my-batch/sglang-int4", "batch": "my-batch"}),
            mock.Mock(status="Ready",
                      metadata={"task": "harbor-constructor-sglang-fp8"}),
        ]
        listed = mock.Mock(sandboxes=sandboxes)
        output = io.StringIO()
        with mock.patch.object(cmd_batch.settings, "load_env", return_value=env), \
             mock.patch.object(cmd_batch.settings, "need", side_effect=lambda e, k: e[k]), \
             mock.patch.object(cmd_batch.tos, "connect", return_value=object()), \
             mock.patch.object(cmd_batch.tos, "prefixes", side_effect=fake_prefixes), \
             mock.patch.object(cmd_batch, "_get_json", side_effect=fake_get_json), \
             mock.patch.object(cmd_batch.faas, "configure", return_value=object()), \
             mock.patch.object(cmd_batch.faas, "list_sandboxes", return_value=listed), \
             contextlib.redirect_stdout(output):
            cmd_batch.list_cmd(argparse.Namespace())
        text = output.getvalue()
        self.assertIn("my-batch", text)
        self.assertIn("other-batch", text)
        self.assertIn("harbor-constructor", text)
        self.assertIn("hello-world", text)
        self.assertNotIn("sglang-fp8", text)
        self.assertNotIn("measuring", text)
        self.assertNotIn("queued", text)
        self.assertNotIn("harbor-constructor-sglang-fp8", text)
        self.assertTrue(any(k.endswith("batch.json") for k in json_keys))
        self.assertFalse(any("status.json" in k for k in json_keys))
        # live count: two sandboxes tagged batch=my-batch (Ready + Failed)
        self.assertRegex(text, r"my-batch\s+harbor-constructor\s+2\s+2")
        self.assertRegex(text, r"other-batch\s+hello-world\s+1\s+0")
