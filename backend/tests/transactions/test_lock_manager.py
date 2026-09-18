import threading
import time
import unittest

from engine.transactions import LockManager, LockTimeoutError, Resource


class LockManagerTest(unittest.TestCase):
    def setUp(self):
        self.manager = LockManager()
        self.resource = Resource("table", "users")

    def test_transaction_acquires_an_available_resource(self):
        acquired = self.manager.acquire(1, self.resource)

        self.assertTrue(acquired)
        self.assertEqual(self.manager.owner(self.resource), 1)

    def test_same_transaction_can_acquire_the_resource_again(self):
        self.manager.acquire(1, self.resource)

        acquired = self.manager.acquire(1, self.resource)

        self.assertTrue(acquired)
        self.assertEqual(self.manager.owner(self.resource), 1)

    def test_second_transaction_waits_until_release(self):
        self.manager.acquire(1, self.resource)
        second_acquired = threading.Event()

        def acquire_from_second_transaction():
            self.manager.acquire(2, self.resource, timeout=1)
            second_acquired.set()

        second = threading.Thread(target=acquire_from_second_transaction)
        second.start()

        limit = time.monotonic() + 1
        while not self.manager.has_event("WAIT", 2) and time.monotonic() < limit:
            time.sleep(0.01)

        self.assertTrue(self.manager.has_event("WAIT", 2))
        self.assertFalse(second_acquired.is_set())

        self.manager.release(1, self.resource)
        second.join(timeout=1)

        self.assertFalse(second.is_alive())
        self.assertTrue(second_acquired.is_set())
        self.assertEqual(self.manager.owner(self.resource), 2)

    def test_different_resources_can_be_acquired(self):
        other_resource = Resource("table", "orders")

        self.manager.acquire(1, self.resource)
        self.manager.acquire(2, other_resource)

        self.assertEqual(self.manager.owner(self.resource), 1)
        self.assertEqual(self.manager.owner(other_resource), 2)

    def test_timeout_is_reported(self):
        self.manager.acquire(1, self.resource)

        with self.assertRaises(LockTimeoutError):
            self.manager.acquire(2, self.resource, timeout=0.01)

    def test_release_all_removes_transaction_locks(self):
        other_resource = Resource("table", "orders")
        self.manager.acquire(1, self.resource)
        self.manager.acquire(1, other_resource)

        self.manager.release_all(1)

        self.assertIsNone(self.manager.owner(self.resource))
        self.assertIsNone(self.manager.owner(other_resource))


if __name__ == "__main__":
    unittest.main()
