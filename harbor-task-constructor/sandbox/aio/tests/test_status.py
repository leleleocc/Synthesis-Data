"""Task-level status.json: cumulative counters, markers, and a corrupt previous file."""

import json
import os
import tempfile
import unittest

from support import CaptureLog, make_config, make_workspace

from runner import status as st


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = make_config(self.tmp.name)
        make_workspace(self.cfg)
        os.makedirs(self.cfg.task, exist_ok=True)

    def read(self):
        with open(self.cfg.status_path) as fh:
            return json.load(fh)

    def test_first_write_starts_counters_at_zero_then_adds(self):
        st.write(self.cfg, phase="2", bump_sandboxes=True)
        body = self.read()
        self.assertEqual(body["sandboxes"], 1)
        self.assertEqual(body["lives"], 0)
        self.assertEqual(body["task_id"], self.cfg.task_id)
        self.assertEqual(body["markers"], {"measuring": False, "blocked": False})

        st.write(self.cfg, phase="4b", iteration=1, bump_lives=True)
        body = self.read()
        self.assertEqual(body["sandboxes"], 1)
        self.assertEqual(body["lives"], 1)
        self.assertEqual(body["iteration"], 1)
        self.assertEqual(body["phase"], "4b")

    def test_markers_copied_from_workspace_files(self):
        open(self.cfg.measuring_marker, "w").close()
        st.write(self.cfg, phase="4b")
        self.assertTrue(self.read()["markers"]["measuring"])
        self.assertFalse(self.read()["markers"]["blocked"])

    def test_survives_corrupt_previous_file(self):
        os.makedirs(os.path.dirname(self.cfg.status_path), exist_ok=True)
        with open(self.cfg.status_path, "w") as fh:
            fh.write("not-json")
        st.write(self.cfg, phase="2", bump_sandboxes=True)
        self.assertEqual(self.read()["sandboxes"], 1)

    def test_create_false_does_not_invent_a_file(self):
        self.assertFalse(os.path.exists(self.cfg.status_path))
        body = st.write(self.cfg, phase="7", create=False)
        self.assertIsNone(body)
        self.assertFalse(os.path.exists(self.cfg.status_path))

    def test_create_false_updates_an_existing_file(self):
        st.write(self.cfg, phase="2", bump_sandboxes=True)
        st.write(self.cfg, phase="7", create=False, verified="verified")
        body = self.read()
        self.assertEqual(body["phase"], "7")
        self.assertEqual(body["sandboxes"], 1)
        self.assertEqual(body["verified"], "verified")
