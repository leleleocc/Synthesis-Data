import os
import tempfile
import unittest
from unittest import mock

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sbx import cmd_task, settings, faas, mounts


class CheckTaskIdTests(unittest.TestCase):
    def test_flat_still_ok(self):
        cmd_task._check_task_id("sglang-fp8")

    def test_nested_ok(self):
        cmd_task._check_task_id("my-batch/sglang-fp8")

    def test_leading_underscore_rejected(self):
        with self.assertRaises(SystemExit):
            cmd_task._check_task_id("_runtime")
        with self.assertRaises(SystemExit):
            cmd_task._check_task_id("my-batch/_hidden")
        with self.assertRaises(SystemExit):
            cmd_task._check_task_id("_batch/one")

    def test_two_slashes_rejected(self):
        with self.assertRaises(SystemExit):
            cmd_task._check_task_id("a/b/c")

    def test_empty_segment_rejected(self):
        with self.assertRaises(SystemExit):
            cmd_task._check_task_id("/one")
        with self.assertRaises(SystemExit):
            cmd_task._check_task_id("batch/")
        with self.assertRaises(SystemExit):
            cmd_task._check_task_id("batch//one")


class LoadTaskEnvTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.here = self.tmp.name
        os.makedirs(os.path.join(self.here, "tasks"))
        with open(os.path.join(self.here, "tasks", "my-batch.env"), "w") as fh:
            fh.write("K=batch\n")
        with open(os.path.join(self.here, "tasks", "flat.env"), "w") as fh:
            fh.write("K=flat\n")
        with open(os.path.join(self.here, "task.env"), "w") as fh:
            fh.write("K=fallback\n")

    def test_nested_id_reads_batch_env(self):
        with mock.patch.object(settings, "HERE", self.here):
            path, env = settings.load_task_env("my-batch/sglang-fp8")
        self.assertTrue(path.endswith("tasks/my-batch.env"))
        self.assertEqual(env["K"], "batch")

    def test_flat_id_reads_task_env(self):
        with mock.patch.object(settings, "HERE", self.here):
            path, env = settings.load_task_env("flat")
        self.assertTrue(path.endswith("tasks/flat.env"))
        self.assertEqual(env["K"], "flat")


class MetadataTests(unittest.TestCase):
    def test_nested_id_sets_batch_label(self):
        env = {
            "VEFAAS_FUNCTION_ID": "fn",
            "TOS_BUCKET": "b",
            "TOS_BUCKET_PATH": "/sandbox",
            "NAS_REMOTE_PATH": "/harbor",
            "RUNTIME_VERSION": "v1",
        }
        # sandbox_request talks to volcengine types; we only assert the dict
        # it would put on the request. Patch instance_rows so we don't need
        # a real bucket layout.
        with mock.patch.object(mounts, "instance_rows", return_value=[]), \
             mock.patch.object(faas.settings, "need", side_effect=lambda e, k: e[k]):
            request = faas.sandbox_request(env, "my-batch/one", "tmpl")
        self.assertEqual(request.metadata["task"], "my-batch/one")
        self.assertEqual(request.metadata["batch"], "my-batch")

    def test_flat_id_has_no_batch_label(self):
        env = {
            "VEFAAS_FUNCTION_ID": "fn",
            "TOS_BUCKET": "b",
            "TOS_BUCKET_PATH": "/sandbox",
            "NAS_REMOTE_PATH": "/harbor",
            "RUNTIME_VERSION": "v1",
        }
        with mock.patch.object(mounts, "instance_rows", return_value=[]), \
             mock.patch.object(faas.settings, "need", side_effect=lambda e, k: e[k]):
            request = faas.sandbox_request(env, "flat", "tmpl")
        self.assertEqual(request.metadata["task"], "flat")
        self.assertNotIn("batch", request.metadata)
