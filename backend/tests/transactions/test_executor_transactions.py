import threading
import time
import unittest

from engine.parser.executor import Executor, SemanticError, Table
from engine.parser.nodes import BeginTransaction, EndTransaction, Insert, Select
from engine.parser.scanner import Scanner
from engine.parser.sql_parser import Parser
from engine.transactions import Resource, TransactionManager


class ExecutorTransactionsTest(unittest.TestCase):
    def setUp(self):
        self.catalog = {
            "students": Table("students", ["id", "name"]),
        }
        self.manager = TransactionManager()
        self.executor = Executor(self.catalog, transaction_manager=self.manager)

    def test_begin_and_end_use_transaction_manager(self):
        self.executor.visit_BeginTransaction(BeginTransaction())

        transaction = self.manager.current()
        self.assertIsNotNone(transaction)

        self.executor.visit_EndTransaction(EndTransaction())

        self.assertIsNone(self.manager.current())

    def test_table_lock_is_kept_until_end(self):
        self.executor.visit_BeginTransaction(BeginTransaction())
        transaction = self.manager.current()

        self.executor.visit_Insert(Insert("students", [1, "Ana"]))

        resource = Resource("table", "students")
        self.assertEqual(
            self.manager.lock_manager.owner(resource),
            transaction.transaction_id,
        )

        self.executor.visit_EndTransaction(EndTransaction())

        self.assertIsNone(self.manager.lock_manager.owner(resource))

    def test_parser_executes_a_complete_transaction(self):
        statements = Parser(
            Scanner(
                "BEGIN TRANSACTION; "
                "INSERT INTO students VALUES (1, 'Ana'); "
                "END TRANSACTION;"
            )
        ).parse_program()

        for statement in statements:
            statement.accept(self.executor)

        self.assertEqual(self.catalog["students"].rows, [{"id": 1, "name": "Ana"}])
        self.assertIsNone(self.manager.current())

    def test_invalid_transaction_sequence_is_reported(self):
        with self.assertRaises(SemanticError):
            self.executor.visit_EndTransaction(EndTransaction())

        self.executor.visit_BeginTransaction(BeginTransaction())

        with self.assertRaises(SemanticError):
            self.executor.visit_BeginTransaction(BeginTransaction())

        self.executor.visit_EndTransaction(EndTransaction())

    def test_two_executors_wait_for_the_same_table(self):
        first_executor = Executor(self.catalog, transaction_manager=self.manager)
        second_executor = Executor(self.catalog, transaction_manager=self.manager)
        first_has_lock = threading.Event()
        release_first = threading.Event()
        second_finished = threading.Event()
        second_transaction_id = []

        def first_transaction():
            first_executor.visit_BeginTransaction(BeginTransaction())
            first_executor.visit_Insert(Insert("students", [1, "Ana"]))
            first_has_lock.set()
            release_first.wait()
            first_executor.visit_EndTransaction(EndTransaction())

        def second_transaction():
            first_has_lock.wait()
            second_executor.visit_BeginTransaction(BeginTransaction())
            second_transaction_id.append(self.manager.current().transaction_id)
            second_executor.visit_Select(Select("students", None))
            second_executor.visit_EndTransaction(EndTransaction())
            second_finished.set()

        first = threading.Thread(target=first_transaction)
        second = threading.Thread(target=second_transaction)
        first.start()
        second.start()

        limit = time.monotonic() + 2
        while not second_transaction_id and time.monotonic() < limit:
            time.sleep(0.01)

        self.assertTrue(second_transaction_id)

        while (
            not self.manager.lock_manager.has_event(
                "WAIT", second_transaction_id[0]
            )
            and time.monotonic() < limit
        ):
            time.sleep(0.01)

        self.assertTrue(
            self.manager.lock_manager.has_event("WAIT", second_transaction_id[0])
        )
        self.assertFalse(second_finished.is_set())

        release_first.set()
        first.join(timeout=2)
        second.join(timeout=2)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertTrue(second_finished.is_set())


if __name__ == "__main__":
    unittest.main()
