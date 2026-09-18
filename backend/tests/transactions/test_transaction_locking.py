import threading
import time
import unittest

from engine.transactions import Resource, TransactionError, TransactionManager


class TransactionLockingTest(unittest.TestCase):
    def setUp(self):
        self.manager = TransactionManager()
        self.resource = Resource("page", "users.dat", 1)

    def test_acquire_requires_an_active_transaction(self):
        with self.assertRaises(TransactionError):
            self.manager.acquire(self.resource)

    def test_transaction_keeps_lock_until_end(self):
        transaction = self.manager.begin()

        self.manager.acquire(self.resource)

        self.assertEqual(
            self.manager.lock_manager.owner(self.resource),
            transaction.transaction_id,
        )

    def test_end_releases_all_transaction_locks(self):
        second_resource = Resource("page", "users.dat", 2)
        self.manager.begin()
        self.manager.acquire(self.resource)
        self.manager.acquire(second_resource)

        self.manager.end()

        self.assertIsNone(self.manager.lock_manager.owner(self.resource))
        self.assertIsNone(self.manager.lock_manager.owner(second_resource))

    def test_second_transaction_continues_after_end(self):
        first_transaction = self.manager.begin()
        self.manager.acquire(self.resource)
        second_acquired = threading.Event()
        second_id = []

        def run_second_transaction():
            transaction = self.manager.begin()
            second_id.append(transaction.transaction_id)
            self.manager.acquire(self.resource, timeout=1)
            second_acquired.set()
            self.manager.end()

        second = threading.Thread(target=run_second_transaction)
        second.start()

        limit = time.monotonic() + 1
        while not second_id and time.monotonic() < limit:
            time.sleep(0.01)
        self.assertTrue(second_id)

        while (
            not self.manager.lock_manager.has_event("WAIT", second_id[0])
            and time.monotonic() < limit
        ):
            time.sleep(0.01)

        self.assertFalse(second_acquired.is_set())
        self.assertEqual(
            self.manager.lock_manager.owner(self.resource),
            first_transaction.transaction_id,
        )

        self.manager.end()
        second.join(timeout=1)

        self.assertFalse(second.is_alive())
        self.assertTrue(second_acquired.is_set())
        self.assertIsNone(self.manager.lock_manager.owner(self.resource))

    def test_ended_transaction_cannot_acquire_more_resources(self):
        self.manager.begin()
        self.manager.end()

        with self.assertRaises(TransactionError):
            self.manager.acquire(self.resource)


if __name__ == "__main__":
    unittest.main()
