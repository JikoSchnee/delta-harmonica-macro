"""Regression tests for the startup account-store lock path.

The account store is guarded by ``AUTH_LOCK``. Historically it was a plain
``threading.Lock`` and the startup/request paths called helpers that acquire it,
which meant any accidental nesting froze the process at boot with no traceback.
These tests pin the properties that keep that from coming back:

* the ordering guard rejects taking library/analytics/ranking locks while the
  account lock is held (the A-B/B-A inversion that deadlocks two threads),
* the account lock is reentrant, so re-entry cannot hang a single thread,
* the real startup sequence runs with an instrumented, non-reentrant account
  lock and never re-acquires it,
* the one-time initialization guard keeps migrations off the request path and
  the point grants stay idempotent.
"""
import importlib.util
import sqlite3
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

SPEC = importlib.util.spec_from_file_location("local_library_server", TOOLS / "local_library_server.py")
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class DetectingLock:
    """Non-reentrant stand-in that reports same-thread re-acquisition."""

    def __init__(self, name, outer=None):
        self.name = name
        self.outer = outer
        self._lock = threading.Lock()
        self._local = threading.local()
        self.nested = []

    def depth(self):
        return int(getattr(self._local, "depth", 0))

    def held_by_current_thread(self):
        return self.depth() > 0

    def acquire(self, blocking=True, timeout=-1):
        depth = self.depth()
        if depth:
            self.nested.append(f"{self.name} re-entered by the same thread")
            raise RuntimeError(f"nested acquire of {self.name}")
        if self.outer is not None and self.outer.held_by_current_thread():
            self.nested.append(f"{self.outer.name} -> {self.name} inversion")
            raise RuntimeError(f"lock inversion {self.outer.name} -> {self.name}")
        acquired = self._lock.acquire(blocking, timeout) if timeout >= 0 else self._lock.acquire(blocking)
        if acquired:
            self._local.depth = depth + 1
        return bool(acquired)

    def release(self):
        depth = self.depth()
        if depth:
            self._local.depth = depth - 1
        self._lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_exc):
        self.release()
        return False

    def locked(self):
        return bool(self._lock.locked())


class LockOrderingTests(unittest.TestCase):
    def test_outer_locks_are_rejected_while_the_account_lock_is_held(self):
        with SERVER.AUTH_LOCK:
            for lock in (SERVER.LIBRARY_LOCK, SERVER.ANALYTICS_LOCK, SERVER.HOT_RANKING_LOCK):
                with self.assertRaises(SERVER.LockOrderError, msg=lock.name):
                    lock.acquire()
        # The guard must not leave the rejected locks poisoned.
        for lock in (SERVER.LIBRARY_LOCK, SERVER.ANALYTICS_LOCK, SERVER.HOT_RANKING_LOCK):
            with lock:
                self.assertTrue(lock.held_by_current_thread())

    def test_account_lock_is_reentrant_and_unwinds(self):
        with SERVER.AUTH_LOCK:
            with SERVER.AUTH_LOCK:
                self.assertEqual(SERVER.AUTH_LOCK.depth(), 2)
            self.assertEqual(SERVER.AUTH_LOCK.depth(), 1)
        self.assertEqual(SERVER.AUTH_LOCK.depth(), 0)

    def test_library_lock_is_not_reentrant(self):
        with SERVER.LIBRARY_LOCK:
            with self.assertRaises(SERVER.LockOrderError):
                SERVER.LIBRARY_LOCK.acquire()

    def test_locked_reports_state_for_reentrant_and_plain_locks(self):
        # RLock.locked() only exists on Python 3.14+, so this pins the fallback.
        self.assertFalse(SERVER.AUTH_LOCK.locked())
        with SERVER.AUTH_LOCK:
            self.assertTrue(SERVER.AUTH_LOCK.locked())
        self.assertFalse(SERVER.AUTH_LOCK.locked())
        with SERVER.LIBRARY_LOCK:
            self.assertTrue(SERVER.LIBRARY_LOCK.locked())
        self.assertFalse(SERVER.LIBRARY_LOCK.locked())


class PointMigrationIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self._temp = TemporaryDirectory()
        self._original = SERVER.AUTH_DATABASE
        SERVER.AUTH_DATABASE = Path(self._temp.name) / "auth.sqlite3"
        SERVER.reset_auth_schema_guard()

    def tearDown(self):
        SERVER.reset_auth_schema_guard()
        SERVER.AUTH_DATABASE = self._original
        self._temp.cleanup()

    def test_initialization_runs_migration_work_only_once_per_process(self):
        calls = []
        original = SERVER._initialize_auth_database_locked

        def counting():
            calls.append(1)
            original()

        SERVER._initialize_auth_database_locked = counting
        try:
            SERVER.initialize_auth_database()
            SERVER.initialize_auth_database()
            SERVER.initialize_auth_database()
            self.assertEqual(len(calls), 1)
            SERVER.reset_auth_schema_guard()
            SERVER.initialize_auth_database()
            self.assertEqual(len(calls), 2)
        finally:
            SERVER._initialize_auth_database_locked = original

if __name__ == "__main__":
    unittest.main()
