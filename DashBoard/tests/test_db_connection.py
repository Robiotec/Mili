import unittest
from unittest.mock import patch

from db.connection import DatabasePool


class _PoolConnectionContext:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        return False


class _CursorContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.params = params

    def fetchone(self):
        return {"ok": 1}


class _TrackedConnection:
    def __init__(self):
        self.commit_calls = 0
        self.rollback_calls = 0

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1

    def cursor(self):
        return _CursorContext()


class _TrackedPool:
    def __init__(self, conn):
        self._conn = conn

    def connection(self):
        return _PoolConnectionContext(self._conn)


class _FakeConnectionPool:
    check_connection = object()
    instances = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self._conn = _TrackedConnection()
        type(self).instances.append(self)

    def connection(self):
        return _PoolConnectionContext(self._conn)


class DatabasePoolTests(unittest.TestCase):
    def test_connection_delegates_transaction_handling_to_pool(self):
        tracked_conn = _TrackedConnection()
        pool = DatabasePool()
        pool._pool = _TrackedPool(tracked_conn)

        with self.assertRaisesRegex(RuntimeError, "boom"):
            with pool.connection():
                raise RuntimeError("boom")

        self.assertEqual(tracked_conn.commit_calls, 0)
        self.assertEqual(tracked_conn.rollback_calls, 0)

    def test_open_configures_pool_connection_check(self):
        _FakeConnectionPool.instances.clear()
        pool = DatabasePool()

        with patch("db.connection.ConnectionPool", _FakeConnectionPool):
            pool.open(retries=1, delay=0)

        self.assertIsNotNone(pool._pool)
        self.assertEqual(len(_FakeConnectionPool.instances), 1)
        created_pool = _FakeConnectionPool.instances[0]
        self.assertIs(
            created_pool.kwargs["check"],
            _FakeConnectionPool.check_connection,
        )


if __name__ == "__main__":
    unittest.main()
