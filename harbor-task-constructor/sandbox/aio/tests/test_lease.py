"""The lease: one constructor at a time, with a dead holder detectable.

The contention these tests reproduce is the one that was measured, not an
imagined one. On 2026-09-10 a single failing instance was retried and ran the
startup command three times, 120 s apart, with the pid namespace preserved and
the earlier run still alive sleeping out its keep-alive. So the case that matters
most is *same host, different pid, both alive* — test_live_holder_on_same_host_blocks.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

from support import CaptureLog, make_config

from runner.lease import Lease, LeaseBusy

HERE = os.path.dirname(os.path.abspath(__file__))

# A real separate process, because that is the real situation: the platform
# re-executes the startup command in the same container, so the contenders share
# a host and a pid namespace but not a pid. Threads would share the pid too and
# would make kill(pid, 0) answer for the wrong process.
WORKER = """
import os, sys, time
sys.path.insert(0, {here!r})
from support import CaptureLog, make_config
from runner.lease import Lease, LeaseBusy
cfg = make_config({root!r}, pid=os.getpid())
lease = Lease(cfg, CaptureLog())
try:
    lease.acquire()
except LeaseBusy:
    print("denied", flush=True)
    sys.exit(0)
print("held", flush=True)
time.sleep(1.5)
lease.release()
"""


class LeaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.addCleanup(self.tmp.cleanup)
        self.cfg = make_config(self.root)
        self.log = CaptureLog()

    def owner(self):
        with open(os.path.join(self.cfg.lease_dir, "owner.json")) as fh:
            return json.load(fh)

    def write_owner(self, **fields):
        os.makedirs(self.cfg.lease_dir, exist_ok=True)
        record = dict(host="host-a", pid=os.getpid(), run_id="someone-else",
                      task_id="t", acquired=time.time(), heartbeat=time.time())
        record.update(fields)
        with open(os.path.join(self.cfg.lease_dir, "owner.json"), "w") as fh:
            json.dump(record, fh)

    # -- taking it -----------------------------------------------------------
    def test_acquire_writes_an_owner_record(self):
        lease = Lease(self.cfg, self.log)
        lease.acquire()
        self.addCleanup(lease.release)
        self.assertTrue(lease.held)
        self.assertEqual(self.owner()["run_id"], self.cfg.run_id)
        self.assertEqual(self.owner()["pid"], self.cfg.pid)

    def test_release_removes_the_lease(self):
        lease = Lease(self.cfg, self.log)
        lease.acquire()
        lease.release()
        self.assertFalse(os.path.exists(self.cfg.lease_dir))

    def test_release_is_idempotent(self):
        lease = Lease(self.cfg, self.log)
        lease.acquire()
        lease.release()
        lease.release()  # must not raise

    # -- the measured case ---------------------------------------------------
    def test_live_holder_on_same_host_blocks(self):
        """A re-executed startup command must not join a run that is still alive."""
        self.write_owner(host="host-a", pid=os.getpid())  # this process: alive
        second = make_config(self.root, pid=os.getpid() + 1)
        with self.assertRaises(LeaseBusy) as caught:
            Lease(second, self.log).acquire()
        self.assertEqual(caught.exception.holder["run_id"], "someone-else")

    def test_dead_holder_on_same_host_is_taken_over(self):
        done = subprocess.Popen(["true"])
        done.wait()  # reaped, so kill(pid, 0) now raises ProcessLookupError
        self.write_owner(host="host-a", pid=done.pid)
        lease = Lease(self.cfg, self.log)
        lease.acquire()
        self.addCleanup(lease.release)
        self.assertEqual(self.owner()["run_id"], self.cfg.run_id)
        self.assertIn("taking over", self.log.text)

    def test_same_host_live_pid_with_stale_heartbeat_is_taken_over(self):
        """A wedged holder is no more use than a dead one."""
        self.write_owner(host="host-a", pid=os.getpid(),
                         heartbeat=time.time() - 600)
        second = make_config(self.root, pid=os.getpid() + 1)
        lease = Lease(second, self.log)
        lease.acquire()
        self.addCleanup(lease.release)
        self.assertEqual(self.owner()["run_id"], second.run_id)

    # -- across instances ----------------------------------------------------
    def test_fresh_heartbeat_on_another_host_blocks(self):
        self.write_owner(host="host-b", pid=1, heartbeat=time.time())
        with self.assertRaises(LeaseBusy):
            Lease(self.cfg, self.log).acquire()

    def test_stale_heartbeat_on_another_host_is_taken_over(self):
        self.write_owner(host="host-b", pid=1,
                         heartbeat=time.time() - self.cfg.lease_stale_seconds - 10)
        lease = Lease(self.cfg, self.log)
        lease.acquire()
        self.addCleanup(lease.release)
        self.assertEqual(self.owner()["run_id"], self.cfg.run_id)

    def test_heartbeat_keeps_the_record_fresh(self):
        lease = Lease(self.cfg, self.log)
        lease.acquire()
        self.addCleanup(lease.release)
        first = self.owner()["heartbeat"]
        time.sleep(self.cfg.lease_heartbeat_seconds + 1.5)
        self.assertGreater(self.owner()["heartbeat"], first)

    def test_lease_directory_without_an_owner_record_is_claimable(self):
        os.makedirs(self.cfg.lease_dir)  # died between mkdir and first write
        lease = Lease(self.cfg, self.log)
        lease.acquire()
        self.addCleanup(lease.release)
        self.assertEqual(self.owner()["run_id"], self.cfg.run_id)

    def test_release_does_not_evict_a_successor(self):
        lease = Lease(self.cfg, self.log)
        lease.acquire()
        self.write_owner(run_id="a-later-run", host="host-b", pid=1)
        lease.release()
        self.assertTrue(os.path.exists(self.cfg.lease_dir))
        self.assertEqual(self.owner()["run_id"], "a-later-run")

    # -- the whole point -----------------------------------------------------
    def test_only_one_of_many_processes_constructs(self):
        code = WORKER.format(here=HERE, root=self.root)
        procs = [subprocess.Popen([sys.executable, "-c", code],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True)
                 for _ in range(6)]
        outcomes = []
        for p in procs:
            out, err = p.communicate(timeout=60)
            self.assertEqual(p.returncode, 0, f"worker failed: {err}")
            outcomes.append(out.strip())
        self.assertEqual(outcomes.count("held"), 1,
                         f"exactly one process may hold the lease, got {outcomes}")
        self.assertEqual(outcomes.count("denied"), 5)


if __name__ == "__main__":
    unittest.main()
