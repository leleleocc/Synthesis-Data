"""Attach semantics and seed/archive precedence.

The cleanup-policy tests were removed when phase 6 (clean) was dropped from the
lifecycle. The workspace is never removed by the in-sandbox runner now.
"""

import os
import tempfile
import unittest

from support import CaptureLog, make_config, make_workspace, seed_tree

from runner import archive as archives
from runner import workspace as ws


class AttachTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = make_config(self.tmp.name)
        self.log = CaptureLog()

    def stock_archive(self):
        """An archive on TOS, with the NAS side wiped."""
        import shutil
        make_workspace(self.cfg)
        archives.create(self.cfg.workspace, self.cfg.archives_dir,
                        "20260101T000000Z", self.log)
        shutil.rmtree(self.cfg.workspace)

    def test_restores_when_nothing_is_on_nas(self):
        self.stock_archive()
        self.assertEqual(ws.attach(self.cfg, self.log), ws.RESTORED)
        self.assertTrue(os.path.exists(self.cfg.attached_marker))
        self.assertEqual(archives.count_files(self.cfg.workspace), 4)

    def test_reuses_an_attached_tree_without_restoring(self):
        """Requirement 3: the next run in continues the work, it does not redo it."""
        self.stock_archive()
        ws.attach(self.cfg, self.log)
        progress = os.path.join(self.cfg.workspace, "build/work-in-progress.txt")
        with open(progress, "w") as fh:
            fh.write("half done\n")

        second = CaptureLog()
        self.assertEqual(ws.attach(self.cfg, second), ws.REUSED)
        self.assertTrue(os.path.exists(progress),
                        "a reused workspace must not be overwritten by a restore")
        self.assertNotIn("extracting", second.text)

    def test_refuses_a_non_empty_tree_with_no_marker(self):
        self.stock_archive()
        os.makedirs(self.cfg.workspace)
        with open(os.path.join(self.cfg.workspace, "stray.txt"), "w") as fh:
            fh.write("half-extracted\n")
        with self.assertRaises(ws.AttachRefused):
            ws.attach(self.cfg, self.log)

    def test_refuses_when_there_is_no_archive(self):
        with self.assertRaises(ws.AttachRefused):
            ws.attach(self.cfg, self.log)

    def test_restore_leaves_no_staging_directory(self):
        self.stock_archive()
        ws.attach(self.cfg, self.log)
        leftovers = [n for n in os.listdir(self.cfg.nas) if n.startswith(".restore-")]
        self.assertEqual(leftovers, [])


class SeedPrecedenceTest(unittest.TestCase):
    """seed/ is an input, archives/ is output, and output always wins."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = make_config(self.tmp.name)
        self.log = CaptureLog()

    def restored_names(self):
        return set(os.listdir(self.cfg.workspace))

    def test_seed_is_used_when_no_archive_exists_yet(self):
        marker = seed_tree(self.cfg)
        self.assertEqual(ws.attach(self.cfg, self.log), ws.RESTORED)
        self.assertIn(marker, self.restored_names())
        self.assertIn("falling back to the seed", self.log.text)

    def test_an_archive_beats_the_seed(self):
        import shutil
        seed_tree(self.cfg)
        ws.attach(self.cfg, self.log)
        with open(os.path.join(self.cfg.workspace, "constructed.txt"), "w") as fh:
            fh.write("work done in the sandbox\n")
        archives.create(self.cfg.workspace, self.cfg.archives_dir,
                        "20260101T000000Z", self.log)
        shutil.rmtree(self.cfg.workspace)

        second = CaptureLog()
        ws.attach(self.cfg, second)
        self.assertIn("constructed.txt", self.restored_names())
        self.assertNotIn("falling back to the seed", second.text)

    def test_a_seed_pushed_after_an_archive_cannot_clobber_it(self):
        """The regression this split exists for: a *newer* seed still loses."""
        import shutil
        seed_tree(self.cfg, stamp="20250101T000000Z")
        ws.attach(self.cfg, self.log)
        with open(os.path.join(self.cfg.workspace, "constructed.txt"), "w") as fh:
            fh.write("work done in the sandbox\n")
        archives.create(self.cfg.workspace, self.cfg.archives_dir,
                        "20260101T000000Z", self.log)
        shutil.rmtree(self.cfg.workspace)

        seed_tree(self.cfg, stamp="20990101T000000Z", marker="corrected-seed")

        ws.attach(self.cfg, CaptureLog())
        names = self.restored_names()
        self.assertIn("constructed.txt", names)
        self.assertNotIn("corrected-seed", names)

    def test_refuses_when_neither_seed_nor_archive_exists(self):
        with self.assertRaises(ws.AttachRefused) as caught:
            ws.attach(self.cfg, self.log)
        message = str(caught.exception)
        self.assertIn("archive", message)
        self.assertIn("seed", message)


class FingerprintTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = make_config(self.tmp.name)

    def test_stable_without_changes(self):
        make_workspace(self.cfg)
        self.assertEqual(ws.fingerprint(self.cfg.workspace),
                         ws.fingerprint(self.cfg.workspace))

    def test_changes_when_file_added(self):
        make_workspace(self.cfg)
        fp1 = ws.fingerprint(self.cfg.workspace)
        with open(os.path.join(self.cfg.workspace, "extra.txt"), "w") as fh:
            fh.write("new\n")
        self.assertNotEqual(fp1, ws.fingerprint(self.cfg.workspace))

    def test_ignores_dotfiles_and_dot_dirs(self):
        make_workspace(self.cfg)
        fp1 = ws.fingerprint(self.cfg.workspace)
        hidden = os.path.join(self.cfg.workspace, ".claude")
        os.makedirs(hidden, exist_ok=True)
        with open(os.path.join(hidden, "journal.jsonl"), "w") as fh:
            fh.write("{}\n")
        self.assertEqual(fp1, ws.fingerprint(self.cfg.workspace))

    def test_empty_tree_returns_zero_count(self):
        make_workspace(self.cfg)
        import shutil
        shutil.rmtree(self.cfg.workspace)
        count, newest = ws.fingerprint(self.cfg.workspace)
        self.assertEqual(count, 0)
        self.assertEqual(newest, 0.0)


if __name__ == "__main__":
    unittest.main()
