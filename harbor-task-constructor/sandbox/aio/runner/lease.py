"""A lease over the NAS workspace: one constructor at a time, with liveness.

Why a lease and not a lock. A lock left behind by a holder that died walls the
task off permanently, and the holders here do die without releasing: instances
are reclaimed without warning, and a failing one is retried on a ~120 s grid with
every retry re-running the startup command against the same NAS directory. A
lease pairs an owner record with a heartbeat, so a dead holder is *detected*
rather than waited on forever.

Why mkdir. flock over NFS is not dependable; mkdir is atomic there, and its
failure mode (EEXIST) is the signal we want.

The hard case is measured, not hypothetical. On 2026-09-10 one instance ran the
startup command three times, 120 s apart, with the pid namespace preserved
(restore pids 50 -> 466 -> 674, never reset) and /tmp/user surviving between
them. The previous run was still alive each time, sleeping out its keep-alive.
So the common contention is *same host, different pid, both alive* — which is why
liveness on the local host is an exact kill(pid, 0) rather than a timeout. The
cross-host case is real too and cannot use kill: in the live series two separate
instances contended over one workspace and the loser stood down on heartbeat age.
"""

import errno
import json
import os
import threading
import time


class LeaseBusy(Exception):
    """Another run holds the lease and is demonstrably alive."""

    def __init__(self, holder):
        self.holder = holder or {}
        who = f"{self.holder.get('host')}:{self.holder.get('pid')}"
        super().__init__(f"lease held by {who} (run {self.holder.get('run_id')})")


class Lease:
    def __init__(self, cfg, log):
        self.cfg = cfg
        self.log = log
        self.dir = cfg.lease_dir
        self.owner_file = os.path.join(self.dir, "owner.json")
        self._stop = threading.Event()
        self._thread = None
        self.held = False

    # -- owner record --------------------------------------------------------
    def _record(self):
        now = time.time()
        return {
            "host": self.cfg.host,
            "pid": self.cfg.pid,
            "run_id": self.cfg.run_id,
            "task_id": self.cfg.task_id,
            "acquired": now,
            "heartbeat": now,
        }

    def _read(self):
        try:
            with open(self.owner_file) as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def _write(self, record):
        # Write beside and rename: a reader never sees a half-written owner, and
        # the directory itself is left alone. Removing and recreating the
        # directory to take it over would reopen the very race mkdir closed.
        tmp = f"{self.owner_file}.{self.cfg.pid}.tmp"
        with open(tmp, "w") as fh:
            json.dump(record, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.owner_file)

    # -- liveness ------------------------------------------------------------
    def _alive(self, holder):
        if not holder:
            return False
        age = time.time() - float(holder.get("heartbeat") or 0)
        fresh = age <= self.cfg.lease_stale_seconds

        if holder.get("host") == self.cfg.host:
            # Same pid namespace, so this is exact rather than inferred. Still
            # require a fresh heartbeat: over hours a pid is recycled, and a
            # holder wedged with its heartbeat stopped is no more use than a
            # dead one.
            try:
                os.kill(int(holder.get("pid") or -1), 0)
            except (ProcessLookupError, ValueError, TypeError):
                return False
            except PermissionError:
                pass  # exists, just not ours to signal
            return fresh

        # Another instance: the heartbeat is the only evidence available.
        return fresh

    # -- acquisition ---------------------------------------------------------
    def acquire(self):
        """Take the lease, or raise LeaseBusy if a live holder has it."""
        try:
            os.mkdir(self.dir)
        except FileExistsError:
            holder = self._read()
            if holder is None:
                # Directory exists with no owner record: either an acquirer is
                # mid-write, or one died between mkdir and the first write. Give
                # the former a moment before treating the lease as abandoned.
                time.sleep(1)
                holder = self._read()
                if holder is None:
                    self.log.say("  lease directory has no owner record — taking it")
                    return self._take(None)
            if self._alive(holder):
                raise LeaseBusy(holder)
            age = int(time.time() - float(holder.get("heartbeat") or 0))
            self.log.say(f"  lease holder {holder.get('host')}:{holder.get('pid')} "
                         f"is gone (heartbeat {age}s old) — taking over")
            return self._take(holder)
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                os.makedirs(os.path.dirname(self.dir), exist_ok=True)
                return self.acquire()
            raise
        else:
            return self._take(None)

    def _take(self, previous):
        self._write(self._record())
        # Re-read: two runs can decide the same dead holder is dead and both
        # write. The last writer wins, and the loser must find that out here
        # rather than by constructing into a workspace someone else owns.
        confirmed = self._read()
        if not confirmed or confirmed.get("run_id") != self.cfg.run_id:
            raise LeaseBusy(confirmed)
        self.held = True
        if previous:
            self.log.say(f"  took over from run {previous.get('run_id')}")
        self._start_heartbeat()
        return self

    # -- heartbeat -----------------------------------------------------------
    def _start_heartbeat(self):
        def beat():
            while not self._stop.wait(self.cfg.lease_heartbeat_seconds):
                record = self._read()
                if not record or record.get("run_id") != self.cfg.run_id:
                    # Someone judged us dead and took over. Stop claiming to be
                    # alive; the phase loop checks `held` before it commits.
                    self.held = False
                    return
                record["heartbeat"] = time.time()
                try:
                    self._write(record)
                except OSError:
                    return

        self._thread = threading.Thread(target=beat, name="lease-heartbeat",
                                        daemon=True)
        self._thread.start()

    # -- release -------------------------------------------------------------
    def release(self):
        """Drop the lease. Safe to call twice, and safe when we no longer own it."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        if not self.held:
            return
        self.held = False
        current = self._read()
        if current and current.get("run_id") != self.cfg.run_id:
            return  # already taken over; removing it would evict the new holder
        try:
            os.remove(self.owner_file)
        except OSError:
            pass
        try:
            os.rmdir(self.dir)
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()
        return False
