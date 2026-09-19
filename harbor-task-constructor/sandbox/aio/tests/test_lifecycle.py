"""The whole lifecycle on a laptop: no sandbox, no TOS, no NAS.

This is what the module was extracted for. The three behaviours that the shell
version could not demonstrate without burning a sandbox launch — standing down,
resuming, and archiving on every run — are each one test here.
"""

import json
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from support import (CaptureLog, declare_done, fake_agent, make_config,
                     make_workspace)

from runner import archive as archives
from runner import workspace as ws
from runner.__main__ import init_phase, iterate, lifecycle
from runner.lease import Lease
from runner.runlog import RunLog

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = CaptureLog()

    def seed_archive(self, cfg):
        """Put one verified archive on TOS and leave NAS empty.

        Also writes a minimal PROMPT.md, because an iterate phase with no prompt
        is a runner failure and would change the verdict of tests that are about
        something else entirely.
        """
        make_workspace(cfg)
        archives.create(cfg.workspace, cfg.archives_dir, "20260101T000000Z",
                        CaptureLog())
        import shutil
        shutil.rmtree(cfg.workspace)
        with open(cfg.prompt_file, "w") as fh:
            fh.write("Say hello.\n")

    def read_json(self, path):
        with open(path) as fh:
            return json.load(fh)

    def result(self, cfg):
        return self.read_json(os.path.join(cfg.run_dir, "result.json"))

    # -- transport round trip -------------------------------------------------
    def test_full_run_always_archives(self):
        """Every lifecycle run archives the workspace, regardless of .done."""
        cfg = make_config(self.tmp.name, max_iterations=1)
        self.seed_archive(cfg)
        lifecycle(cfg, self.log)

        body = self.result(cfg)
        # The stub agent produces nothing, so the loop ends without .done — and
        # that is still a clean run: the scaffold did its job.
        self.assertEqual(body["verdict"], "pass")
        self.assertFalse(body["done"])
        self.assertEqual(body["attach"], ws.RESTORED)
        self.assertIsNotNone(body["archived"])
        # Workspace is NOT cleaned — the runner no longer removes it.
        self.assertTrue(os.path.exists(cfg.workspace))
        self.assertTrue(os.path.exists(
            os.path.join(cfg.archives_dir, body["archived"] + ".sha256")))

    def test_done_flag_appears_in_result(self):
        """result.json must report done=True when .done was present at end."""
        cfg = make_config(self.tmp.name)
        self.seed_archive(cfg)
        # Pre-place .done so the iterate loop sees it immediately (no claude).
        lifecycle(cfg, self.log)
        declare_done(cfg)

        later = make_config(self.tmp.name, pid=os.getpid() + 1,
                            stamp="20260102T000000Z")
        lifecycle(later, CaptureLog())
        self.assertTrue(self.result(later)["done"])

    def test_lease_is_released_at_the_end(self):
        cfg = make_config(self.tmp.name)
        self.seed_archive(cfg)
        lifecycle(cfg, self.log)
        self.assertFalse(os.path.exists(cfg.lease_dir),
                         "a finished run must not look like a live constructor")

    # -- requirement 2: one constructor at a time ----------------------------
    def test_second_run_stands_down_and_says_so(self):
        first = make_config(self.tmp.name, pid=os.getpid())
        self.seed_archive(first)
        holder = Lease(first, CaptureLog())
        holder.acquire()
        self.addCleanup(holder.release)

        second = make_config(self.tmp.name, pid=os.getpid() + 1)
        lifecycle(second, self.log)

        body = self.result(second)
        self.assertEqual(body["verdict"], "stood-down")
        self.assertEqual(body["lease"], "denied")
        self.assertEqual(body["holder"]["run_id"], first.run_id)
        self.assertIsNone(body["attach"])
        self.assertFalse(os.path.exists(second.workspace),
                         "a run that stood down must not have touched the workspace")

    def test_stood_down_run_has_its_own_directory(self):
        """Two runs in the same second must not overwrite each other's log."""
        first = make_config(self.tmp.name, pid=os.getpid())
        self.seed_archive(first)
        holder = Lease(first, CaptureLog())
        holder.acquire()
        self.addCleanup(holder.release)

        second = make_config(self.tmp.name, pid=os.getpid() + 1)
        self.assertEqual(first.stamp, second.stamp)
        self.assertNotEqual(first.run_dir, second.run_dir)

    def test_a_second_real_process_stands_down(self):
        """End to end across two processes, with a construction slow enough to
        overlap. The lease tests cover the primitive; this covers the whole
        lifecycle behaving around it."""
        cfg = make_config(self.tmp.name)
        self.seed_archive(cfg)
        # Give the first process something slow to do so the second can see the
        # lease. init.sh sleeps; the loop sees no PROMPT.md quickly after.
        with open(cfg.init_script, "w") as fh:
            fh.write("#!/bin/sh\nsleep 10\n")
        os.chmod(cfg.init_script, 0o755)
        env = dict(os.environ, TASK_MOUNT_PATH=cfg.task, NAS_MOUNT_PATH=cfg.nas,
                   RUNTIME_MOUNT_PATH=cfg.runtime, TEMPLATE_MOUNT_PATH=cfg.template,
                   KEEP_ALIVE_SECONDS="0",
                   CONSTRUCT_MAX_ITERATIONS="1",
                   CONSTRUCT_AGENT_BIN="/usr/bin/true",
                   PYTHONDONTWRITEBYTECODE="1")

        first = subprocess.Popen([sys.executable, "-m", "runner"], env=env,
                                 cwd=ROOT, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        self.addCleanup(first.communicate)
        deadline = time.time() + 30
        while time.time() < deadline and not os.path.isdir(cfg.lease_dir):
            if first.poll() is not None:
                self.fail(f"first runner exited early: {first.communicate()[1]}")
            time.sleep(0.05)
        self.assertTrue(os.path.isdir(cfg.lease_dir),
                        "first runner never took the lease")

        second = subprocess.run([sys.executable, "-m", "runner"], env=env,
                                cwd=ROOT, capture_output=True, text=True,
                                timeout=60)
        self.assertEqual(second.returncode, 0, second.stderr)

        first.wait(timeout=60)
        self.assertEqual(first.returncode, 0)

        runs = os.path.join(cfg.task, "runs")
        stood = [self.read_json(os.path.join(runs, d, "result.json"))
                 for d in os.listdir(runs)]
        verdicts = sorted(b["verdict"] for b in stood)
        self.assertEqual(verdicts, ["pass", "stood-down"], verdicts)
        down = next(b for b in stood if b["verdict"] == "stood-down")
        self.assertEqual(down["lease"], "denied")
        self.assertIsNone(down["attach"])

    # -- requirement 3: pick up where the last run left off ------------------
    def test_next_run_resumes_instead_of_restoring(self):
        cfg = make_config(self.tmp.name)
        self.seed_archive(cfg)
        lifecycle(cfg, self.log)
        progress = os.path.join(cfg.workspace, "build/half-built.txt")
        with open(progress, "w") as fh:
            fh.write("partial\n")

        later = make_config(self.tmp.name, pid=os.getpid() + 2,
                            stamp="20260102T000000Z")
        lifecycle(later, CaptureLog())

        self.assertEqual(self.result(later)["attach"], ws.REUSED)
        self.assertTrue(os.path.exists(progress),
                        "the resumed run must not discard the previous run's work")

    def test_dead_holders_lease_does_not_wall_off_the_task(self):
        cfg = make_config(self.tmp.name)
        self.seed_archive(cfg)
        os.makedirs(cfg.lease_dir)
        with open(os.path.join(cfg.lease_dir, "owner.json"), "w") as fh:
            json.dump({"host": cfg.host, "pid": 999999, "run_id": "a-dead-run",
                       "heartbeat": 0}, fh)

        lifecycle(cfg, self.log)
        self.assertEqual(self.result(cfg)["lease"], "held")

    # -- archive always -------------------------------------------------------
    def test_rework_restores_the_archived_tree(self):
        """A second lifecycle restores from the first run's archive."""
        cfg = make_config(self.tmp.name)
        self.seed_archive(cfg)
        lifecycle(cfg, self.log)
        import shutil
        shutil.rmtree(cfg.workspace)

        rework = make_config(self.tmp.name, stamp="20260301T000000Z")
        lifecycle(rework, CaptureLog())
        self.assertEqual(self.result(rework)["attach"], ws.RESTORED)
        self.assertEqual(archives.count_files(rework.workspace), 4)
        self.assertTrue(os.access(
            os.path.join(rework.workspace, "build/bin/run.sh"), os.X_OK))

    # -- verify.sh -----------------------------------------------------------
    def test_verify_claimed_when_no_script(self):
        """Without verify.sh, a done run records verified='claimed'."""
        cfg = make_config(self.tmp.name)
        self.seed_archive(cfg)
        # First run restores the workspace (stalls — no .done yet). The
        # workspace stays on disk after the run so declare_done can write into it.
        lifecycle(cfg, CaptureLog())
        declare_done(cfg)
        later = make_config(self.tmp.name, pid=os.getpid() + 1,
                            stamp="20260102T000000Z")
        lifecycle(later, self.log)
        self.assertEqual(self.result(later).get("verified"), "claimed")

    def test_verify_verified_when_script_exits_zero(self):
        """A verify.sh that exits 0 records verified='verified'."""
        cfg = make_config(self.tmp.name)
        self.seed_archive(cfg)
        with open(cfg.verify_script, "w") as fh:
            fh.write("#!/bin/sh\nexit 0\n")
        os.chmod(cfg.verify_script, 0o755)
        lifecycle(cfg, CaptureLog())
        declare_done(cfg)
        later = make_config(self.tmp.name, pid=os.getpid() + 1,
                            stamp="20260102T000000Z")
        lifecycle(later, self.log)
        self.assertEqual(self.result(later).get("verified"), "verified")

    def test_verify_failed_when_script_exits_nonzero(self):
        """A verify.sh that exits non-zero records verified='failed'."""
        cfg = make_config(self.tmp.name)
        self.seed_archive(cfg)
        with open(cfg.verify_script, "w") as fh:
            fh.write("#!/bin/sh\nexit 1\n")
        os.chmod(cfg.verify_script, 0o755)
        lifecycle(cfg, CaptureLog())
        declare_done(cfg)
        later = make_config(self.tmp.name, pid=os.getpid() + 1,
                            stamp="20260102T000000Z")
        lifecycle(later, self.log)
        self.assertEqual(self.result(later).get("verified"), "failed")

    def test_verify_skipped_when_not_done(self):
        """verify.sh must not run unless .done was written."""
        cfg = make_config(self.tmp.name, max_iterations=1)
        self.seed_archive(cfg)
        # verify.sh exits non-zero; if it runs, verdict would still be pass but
        # 'verified' would be 'failed'. Confirm it is None instead.
        with open(cfg.verify_script, "w") as fh:
            fh.write("#!/bin/sh\nexit 1\n")
        os.chmod(cfg.verify_script, 0o755)
        lifecycle(cfg, self.log)
        self.assertIsNone(self.result(cfg).get("verified"))

    # -- observability -------------------------------------------------------
    def test_run_publishes_its_log_to_its_own_directory(self):
        cfg = make_config(self.tmp.name)
        self.seed_archive(cfg)
        log = RunLog(cfg)
        self.addCleanup(lambda: os.path.exists(log.local_path)
                        and os.remove(log.local_path))
        lifecycle(cfg, log)
        log.close()

        published = os.path.join(cfg.run_dir, "bootstrap.log")
        self.assertTrue(os.path.exists(published))
        with open(published) as fh:
            text = fh.read()
        self.assertIn("=== 3 attach ===", text)
        self.assertIn("=== 5 archive ===", text)
        # Phase 6 clean no longer exists.
        self.assertNotIn("=== 6 clean ===", text)

    def test_lifecycle_publishes_each_iteration_trace_under_task_prefix(self):
        """A multi-round agent leaves durable, complete trace objects per round."""
        cfg = make_config(
            self.tmp.name,
            max_iterations=2,
            trace_chunk_bytes=1,
            agent_bin=fake_agent(
                self.tmp.name,
                'if [ ! -f round-1 ]; then\n'
                '  touch round-1\n'
                '  printf \'%s\\n\' \'{"type":"assistant","text":"first"}\'\n'
                'else\n'
                '  touch round-2 .done\n'
                '  printf \'%s\\n\' \'{"type":"assistant","text":"second"}\'\n'
                'fi\n'
                'printf \'%s\\n\' \'{"type":"result","subtype":"success"}\'\n'),
        )
        self.seed_archive(cfg)

        lifecycle(cfg, self.log)

        self.assertTrue(self.result(cfg)["done"])
        iterations = os.path.join(cfg.run_dir, "iterations")
        self.assertEqual(sorted(os.listdir(iterations)), ["0001", "0002"])
        for number in ("0001", "0002"):
            directory = os.path.join(iterations, number)
            chunks = sorted(name for name in os.listdir(directory)
                            if name.startswith("output-") and name.endswith(".jsonl"))
            self.assertEqual(chunks, ["output-000001.jsonl", "output-000002.jsonl"])
            with open(os.path.join(directory, "status.json"), encoding="utf-8") as fh:
                status = json.load(fh)
            self.assertTrue(status["complete"])
            self.assertEqual(status["last_sequence"], 2)
            self.assertEqual(status["exit_code"], 0)
            with open(os.path.join(directory, "output-000001.jsonl"), "rb") as fh:
                self.assertIn(b'"type":"assistant"', fh.read())
            with open(os.path.join(directory, "output-000002.jsonl"), "rb") as fh:
                self.assertIn(b'"type":"result"', fh.read())
            self.assertFalse(any(name.startswith(".") for name in os.listdir(directory)))


class LoopTest(unittest.TestCase):
    """The three ways the iterate phase can stop, each provoked on demand.

    These are the tests the shell version could not have: the stop conditions
    are the whole contract between the scaffold and a tenant's template, and
    driving a stub agent is the only way to exercise them without an API key.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = CaptureLog()

    def ready(self, agent=None, **overrides):
        """A config with an attached workspace and a prompt, ready to iterate."""
        if agent is not None:
            overrides["agent_bin"] = fake_agent(self.tmp.name, agent)
        cfg = make_config(self.tmp.name, **overrides)
        make_workspace(cfg)
        with open(cfg.prompt_file, "w") as fh:
            fh.write("Build the thing.\n")
        return cfg

    def test_done_marker_stops_the_loop(self):
        cfg = self.ready('echo built > built.txt\ntouch .done\n')
        self.assertTrue(iterate(cfg, self.log))
        self.assertIn("iteration 1/", self.log.text)
        self.assertNotIn("iteration 2/", self.log.text)
        self.assertEqual(self.log.failures, 0)

    def test_loop_runs_until_the_agent_is_done(self):
        """Three rounds of real work, then .done — the ordinary case."""
        cfg = self.ready(
            'n=$(ls round-* 2>/dev/null | wc -l)\n'
            'touch "round-$n"\n'
            '[ "$n" -ge 2 ] && touch .done\n'
            'exit 0\n')
        self.assertTrue(iterate(cfg, self.log))
        self.assertIn("iteration 3/", self.log.text)
        self.assertNotIn("iteration 4/", self.log.text)

    def test_stall_stops_the_loop_without_failing_the_run(self):
        """An agent that changes nothing is stopped, but is not a runner fault."""
        cfg = self.ready("exit 0\n", max_iterations=20)
        self.assertFalse(iterate(cfg, self.log))
        self.assertIn("stall detected after 4 iterations", self.log.text)
        # Three *consecutive* unchanged fingerprints, and the first iteration
        # only establishes the baseline — so the fourth is the earliest a stall
        # can be called.
        self.assertNotIn("iteration 5/", self.log.text)
        self.assertEqual(self.log.failures, 0,
                         "a stalled model is a construction outcome, not a "
                         "broken scaffold")

    def test_max_iterations_stops_the_loop_without_failing_the_run(self):
        """Progress every round but never .done: the budget is the backstop."""
        cfg = self.ready('touch "round-$$-$(date +%s%N)"\n', max_iterations=3)
        self.assertFalse(iterate(cfg, self.log))
        self.assertIn("reached max_iterations=3", self.log.text)
        self.assertEqual(self.log.failures, 0)

    def test_a_failing_agent_does_not_fail_the_run(self):
        """Non-zero from the agent is noted and the loop carries on."""
        cfg = self.ready('echo "boom" >&2\nexit 1\n', max_iterations=2)
        self.assertFalse(iterate(cfg, self.log))
        self.assertIn("(continuing)", self.log.text)
        self.assertEqual(self.log.failures, 0)

    def test_stream_output_is_published_and_completed_on_agent_failure(self):
        """Claude JSONL is visible on stdout and durable after non-zero exit."""
        first = b'{"type":"assistant","text":"one"}\n'
        second = b'{"type":"result","subtype":"error"}\n'
        cfg = self.ready(
            "printf '%s\\n' '{\"type\":\"assistant\",\"text\":\"one\"}'\n"
            "printf '%s\\n' '{\"type\":\"result\",\"subtype\":\"error\"}'\n"
            "exit 7\n",
            max_iterations=1,
            trace_chunk_bytes=1024 * 1024,
        )

        platform = io.StringIO()
        with contextlib.redirect_stdout(platform):
            self.assertFalse(iterate(cfg, self.log))

        self.assertEqual(platform.getvalue(), (first + second).decode())
        iteration_dir = os.path.join(cfg.run_dir, "iterations", "0001")
        with open(os.path.join(iteration_dir, "output-000001.jsonl"), "rb") as fh:
            self.assertEqual(fh.read(), first + second)
        with open(os.path.join(iteration_dir, "status.json"), encoding="utf-8") as fh:
            status = json.load(fh)
        self.assertEqual(status["last_sequence"], 2)
        self.assertTrue(status["complete"])
        self.assertEqual(status["exit_code"], 7)

    def test_agent_launch_failure_leaves_incomplete_trace(self):
        cfg = self.ready("exit 0\n", max_iterations=1)
        with patch("runner.__main__.subprocess.Popen",
                   side_effect=OSError("agent unavailable")):
            with self.assertRaises(OSError):
                iterate(cfg, self.log)

        status_path = os.path.join(cfg.run_dir, "iterations", "0001", "status.json")
        with open(status_path, encoding="utf-8") as fh:
            status = json.load(fh)
        self.assertFalse(status["complete"])
        self.assertIsNone(status["exit_code"])

    def test_a_missing_prompt_is_a_runner_failure(self):
        """Unlike the above: a template with no PROMPT.md cannot be run at all."""
        cfg = make_config(self.tmp.name)
        make_workspace(cfg)
        self.assertFalse(iterate(cfg, self.log))
        self.assertEqual(self.log.failures, 1)

    # -- init ----------------------------------------------------------------
    def test_init_is_optional(self):
        cfg = make_config(self.tmp.name)
        make_workspace(cfg)
        self.assertTrue(init_phase(cfg, self.log))
        self.assertIn("no init.sh", self.log.text)

    def test_init_runs_in_the_workspace(self):
        cfg = make_config(self.tmp.name)
        make_workspace(cfg)
        with open(cfg.init_script, "w") as fh:
            fh.write("#!/bin/sh\npwd > where-init-ran.txt\n")
        self.assertTrue(init_phase(cfg, self.log))
        with open(os.path.join(cfg.workspace, "where-init-ran.txt")) as fh:
            self.assertEqual(os.path.realpath(fh.read().strip()),
                             os.path.realpath(cfg.workspace))

    def test_a_failing_init_is_a_hard_failure(self):
        cfg = make_config(self.tmp.name)
        make_workspace(cfg)
        with open(cfg.init_script, "w") as fh:
            fh.write("#!/bin/sh\nexit 3\n")
        self.assertFalse(init_phase(cfg, self.log))
        self.assertEqual(self.log.failures, 1)

    def test_a_failing_init_stops_the_lifecycle_before_iterating(self):
        cfg = make_config(self.tmp.name)
        make_workspace(cfg)
        archives.create(cfg.workspace, cfg.archives_dir, "20260101T000000Z",
                        CaptureLog())
        with open(cfg.init_script, "w") as fh:
            fh.write("#!/bin/sh\nexit 3\n")
        with open(cfg.prompt_file, "w") as fh:
            fh.write("Build the thing.\n")

        lifecycle(cfg, self.log)
        with open(os.path.join(cfg.run_dir, "result.json")) as fh:
            body = json.load(fh)
        self.assertEqual(body["verdict"], "fail")
        self.assertIsNone(body["archived"])
        self.assertNotIn("4b iterate", self.log.text)


if __name__ == "__main__":
    unittest.main()
