"""The run log, written locally and republished to TOS at each phase boundary.

Appending to a live object through the TOS mount is exactly the operation object
storage does not reliably support, so the log is accumulated on local disk and
copied up whole. Each run owns a directory named for its run id, so two runs that
start in the same second — which near-identical instance pids make an ordinary
collision rather than a coincidence — cannot overwrite each other.
"""

import os
import shutil
import sys


class RunLog:
    def __init__(self, cfg):
        self.cfg = cfg
        self._closed = False
        # Local file is used only to buffer bootstrap.log for TOS publishing;
        # platform log collection reads stdout, not this file.  Prefer /tmp/user
        # then /tmp so the runner survives images with restricted paths.
        for candidate in ("/tmp/user", "/tmp"):
            try:
                os.makedirs(candidate, exist_ok=True)
                local_dir = candidate
                break
            except OSError:
                continue
        else:
            local_dir = "/tmp"
        self.local_path = os.path.join(local_dir, f"bootstrap-{cfg.run_id}.log")
        self._fh = open(self.local_path, "w", buffering=1)
        self.failures = 0

    def say(self, message=""):
        print(message, flush=True)
        if not self._closed:
            self._fh.write(message + "\n")

    def phase(self, title):
        self.say("")
        self.say(f"=== {title} ===")
        self.publish()

    def ok(self, message):
        self.say(f"  ok   {message}")

    def bad(self, message):
        self.say(f"  FAIL {message}")
        self.failures += 1

    def run_output(self, text):
        for line in str(text).rstrip("\n").splitlines():
            self.say(line)

    def publish(self):
        """Copy the log up as a whole object. Never fatal: losing the mount is
        something to report from the log, not a reason to lose the run."""
        try:
            os.makedirs(self.cfg.run_dir, exist_ok=True)
            self._fh.flush()
            shutil.copyfile(self.local_path,
                            os.path.join(self.cfg.run_dir, "bootstrap.log"))
        except OSError as exc:
            print(f"  (could not publish log: {exc})", file=sys.stderr, flush=True)

    def close(self):
        # Idempotent: stand-down paths close the log early, and main's finally
        # closes it again. A second close must be a no-op rather than an
        # I/O-on-closed-file error on the way out of an otherwise clean run.
        if self._closed:
            return
        self.publish()
        self._closed = True
        try:
            self._fh.close()
        except OSError:
            pass
