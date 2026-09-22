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


class StartupLockSafetyTests(unittest.TestCase):
    def setUp(self):
        self._originals = {}
        self._temp = TemporaryDirectory()
        root = Path(self._temp.name)
        (root / "data" / "community-scores").mkdir(parents=True)
        (root / "data" / "analytics").mkdir(parents=True)
        overrides = {
            "REPOSITORY_ROOT": root,
            "SOURCE_DIRECTORY": root / "data" / "community-scores",
            "LIBRARY_OUTPUT": root / "data" / "community-songs.js",
            "AUTH_DATABASE": root / "data" / "auth.sqlite3",
            "ANALYTICS_DIRECTORY": root / "data" / "analytics",
            "EXPORT_EVENT_COUNT_CACHE": SERVER.SingleFlightCache(),
            "AUTH_LOCK": DetectingLock("AUTH_LOCK"),
            "LIBRARY_LOCK": DetectingLock("LIBRARY_LOCK"),
            "ANALYTICS_LOCK": DetectingLock("ANALYTICS_LOCK"),
            "HOT_RANKING_LOCK": DetectingLock("HOT_RANKING_LOCK"),
        }
        for name, value in overrides.items():
            self._originals[name] = getattr(SERVER, name)
            setattr(SERVER, name, value)
        SERVER.reset_auth_schema_guard()

    def tearDown(self):
        SERVER.reset_auth_schema_guard()
        for name, value in self._originals.items():
            setattr(SERVER, name, value)
        self._temp.cleanup()

    def _run_with_watchdog(self, label, fn, timeout=25.0):
        outcome = {}

        def target():
            try:
                fn()
                outcome["result"] = "ok"
            except BaseException as error:  # noqa: BLE001 - surface anything
                outcome["result"] = f"{type(error).__name__}: {error}"

        thread = threading.Thread(target=target, name=label, daemon=True)
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            self.fail(f"startup step {label} deadlocked (never returned within {timeout}s)")
        if outcome.get("result") != "ok":
            self.fail(f"startup step {label} failed: {outcome.get('result')}")

    def test_startup_sequence_never_reenters_the_account_lock(self):
        server = SimpleNamespace(
            auth_enabled=True,
            analytics_enabled=True,
            analytics_retention_days=SERVER.DEFAULT_ANALYTICS_RETENTION_DAYS,
        )
        self._run_with_watchdog("initialize_auth_database", SERVER.initialize_auth_database)
        self._run_with_watchdog("migrate_identity_tables", SERVER.migrate_identity_tables)
        self._run_with_watchdog(
            "backfill_legacy_score_owners_for_known_account",
            SERVER.backfill_legacy_score_owners_for_known_account,
        )
        self._run_with_watchdog(
            "apply_legacy_export_points_migration",
            lambda: SERVER.apply_legacy_export_points_migration(server),
        )
        nested = [entry for lock in (SERVER.AUTH_LOCK, SERVER.LIBRARY_LOCK) for entry in lock.nested]
        self.assertEqual(nested, [], f"startup path nested locks: {nested}")

    def test_export_migration_refuses_to_run_while_holding_the_account_lock(self):
        server = SimpleNamespace(
            auth_enabled=True,
            analytics_enabled=True,
            analytics_retention_days=SERVER.DEFAULT_ANALYTICS_RETENTION_DAYS,
        )
        SERVER.initialize_auth_database()
        with SERVER.AUTH_LOCK:
            with self.assertRaises(SERVER.LockOrderError):
                SERVER.apply_legacy_export_points_migration(server)


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

    def test_legacy_grant_is_idempotent_and_worth_one_hundred(self):
        SERVER.initialize_auth_database()
        with SERVER.AUTH_LOCK, SERVER.auth_database() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO accounts(id, email, user_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("acct-legacy", "legacy@example.invalid", "legacy", 1, 1),
            )
            # Initialization already ran the migration against an empty account
            # table, so clear the marker to model "this account existed when the
            # migration first runs" (the production startup situation).
            connection.execute(
                "DELETE FROM point_migrations WHERE migration_key = ?",
                (SERVER.LEGACY_POINTS_NOTICE_KEY,),
            )
            SERVER.apply_legacy_points_migration(connection)
            first = SERVER.point_balance(connection, "acct-legacy")
            SERVER.apply_legacy_points_migration(connection)
            second = SERVER.point_balance(connection, "acct-legacy")
            grants = connection.execute(
                "SELECT COUNT(*) FROM point_ledger WHERE account_id = ? AND reason = 'legacy_grant'",
                ("acct-legacy",),
            ).fetchone()[0]
            migrations = connection.execute(
                "SELECT COUNT(*) FROM point_migrations WHERE migration_key = ?",
                (SERVER.LEGACY_POINTS_NOTICE_KEY,),
            ).fetchone()[0]
        self.assertEqual(first, SERVER.POINT_RULES["legacy_grant"])
        self.assertEqual(second, first)
        self.assertEqual(grants, 1)
        self.assertEqual(migrations, 1)

    def test_star_reward_matches_the_configured_rule(self):
        self.assertEqual(SERVER.POINT_RULES["github_star"], 500)
        self.assertEqual(SERVER.POINT_RULES["legacy_grant"], 100)


if __name__ == "__main__":
    unittest.main()
