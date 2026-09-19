"""Archive integrity: the sidecar protocol and the in-flight hash.

These two rules are what keep a partially-written archive from being mistaken for
a restorable one, which matters more here than usual: the only copy of a task's
work may be the archive, and the failure is silent by nature.
"""

import os
import tarfile
import tempfile
import unittest

from support import CaptureLog, make_config, make_workspace

from runner import archive as archives


class ArchiveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = make_config(self.tmp.name)
        self.log = CaptureLog()
        make_workspace(self.cfg)

    def create(self, stamp="20260101T000000Z"):
        return archives.create(self.cfg.workspace, self.cfg.archives_dir, stamp,
                               self.log)

    # -- writing -------------------------------------------------------------
    def test_create_writes_archive_sidecar_and_manifest(self):
        path, digest = self.create()
        self.assertIsNotNone(digest)
        self.assertTrue(os.path.exists(path))
        self.assertTrue(os.path.exists(path + ".sha256"))
        self.assertTrue(os.path.exists(path + ".manifest.json"))

    def test_sidecar_matches_the_bytes_on_disk(self):
        path, digest = self.create()
        self.assertEqual(digest, archives.sha256_of(path))
        with open(path + ".sha256") as fh:
            self.assertEqual(fh.read().split()[0], digest)

    def test_attached_marker_is_not_archived(self):
        path, _ = self.create()
        with tarfile.open(path) as tf:
            names = {os.path.basename(n) for n in tf.getnames()}
        self.assertNotIn(".attached", names)
        self.assertIn("instruction.md", names)

    def test_executable_bit_survives_the_round_trip(self):
        path, _ = self.create()
        out = os.path.join(self.tmp.name, "out")
        os.makedirs(out)
        archives.restore(path, out)
        self.assertTrue(os.access(os.path.join(out, "build/bin/run.sh"), os.X_OK))

    def test_manifest_counts_the_tree(self):
        import json
        path, _ = self.create()
        with open(path + ".manifest.json") as fh:
            manifest = json.load(fh)
        self.assertEqual(manifest["files"], 4)
        self.assertEqual(manifest["counts"]["build"], 2)
        self.assertEqual(sorted(manifest["top_level"]),
                         ["build", "instruction.md", "method"])

    # -- choosing ------------------------------------------------------------
    def test_newest_verified_prefers_the_newest(self):
        self.create("20260101T000000Z")
        newest, _ = self.create("20260601T000000Z")
        self.assertEqual(archives.newest_verified(self.cfg.archives_dir, self.log),
                         newest)

    def test_archive_without_a_sidecar_is_invisible(self):
        path, _ = self.create()
        os.remove(path + ".sha256")
        self.assertIsNone(archives.newest_verified(self.cfg.archives_dir, self.log))
        self.assertIn("no sidecar", self.log.text)

    def test_truncated_archive_is_skipped(self):
        """The case the sidecar exists for: bytes lost after the sidecar landed."""
        path, _ = self.create()
        with open(path, "r+b") as fh:
            fh.truncate(os.path.getsize(path) // 2)
        self.assertIsNone(archives.newest_verified(self.cfg.archives_dir, self.log))
        self.assertIn("sha256 mismatch", self.log.text)

    def test_falls_back_to_an_older_intact_archive(self):
        older, _ = self.create("20260101T000000Z")
        newer, _ = self.create("20260601T000000Z")
        with open(newer, "r+b") as fh:
            fh.truncate(10)
        self.assertEqual(archives.newest_verified(self.cfg.archives_dir, self.log),
                         older)

    def test_missing_archive_directory_is_not_an_error(self):
        cfg = make_config(os.path.join(self.tmp.name, "empty"))
        self.assertIsNone(archives.newest_verified(cfg.archives_dir, self.log))


if __name__ == "__main__":
    unittest.main()
