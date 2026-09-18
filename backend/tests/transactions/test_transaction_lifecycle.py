import threading
import unittest

from engine.transactions import TransactionError, TransactionManager, TransactionState


class TransactionLifecycleTest(unittest.TestCase):
    def test_begin_creates_an_active_transaction(self):
        manager = TransactionManager()

        transaction = manager.begin()

        self.assertEqual(transaction.state, TransactionState.ACTIVE)
        self.assertEqual(manager.current(), transaction)

    def test_end_finishes_the_current_transaction(self):
        manager = TransactionManager()
        transaction = manager.begin()

        ended_transaction = manager.end()

        self.assertEqual(ended_transaction, transaction)
        self.assertEqual(transaction.state, TransactionState.ENDED)
        self.assertIsNone(manager.current())

    def test_begin_rejects_a_second_active_transaction(self):
        manager = TransactionManager()
        manager.begin()

        with self.assertRaises(TransactionError):
            manager.begin()

    def test_end_rejects_when_there_is_no_active_transaction(self):
        manager = TransactionManager()

        with self.assertRaises(TransactionError):
            manager.end()

    def test_threads_have_different_transactions(self):
        manager = TransactionManager()
        barrier = threading.Barrier(2)
        transaction_ids = []

        def run_transaction():
            transaction = manager.begin()
            transaction_ids.append(transaction.transaction_id)
            barrier.wait()
            manager.end()

        first = threading.Thread(target=run_transaction)
        second = threading.Thread(target=run_transaction)
        first.start()
        second.start()
        first.join()
        second.join()

        self.assertEqual(len(transaction_ids), 2)
        self.assertNotEqual(transaction_ids[0], transaction_ids[1])


if __name__ == "__main__":
    unittest.main()
