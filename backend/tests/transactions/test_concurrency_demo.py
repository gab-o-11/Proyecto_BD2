import unittest

from engine.transactions.demo import run_safe_demo, run_unsafe_demo


class ConcurrencyDemoTest(unittest.TestCase):
    def test_unsafe_demo_shows_a_lost_update(self):
        result = run_unsafe_demo()

        self.assertEqual(result["initial_value"], 100)
        self.assertEqual(result["expected_value"], 120)
        self.assertEqual(result["final_value"], 70)
        self.assertNotEqual(result["final_value"], result["expected_value"])
        self.assertTrue(result["threads_finished"])

    def test_safe_demo_produces_the_serial_result(self):
        result = run_safe_demo()

        self.assertEqual(result["initial_value"], 100)
        self.assertEqual(result["expected_value"], 120)
        self.assertEqual(result["final_value"], 120)
        self.assertEqual(len(result["transaction_ids"]), 2)
        self.assertTrue(result["wait_detected"])
        self.assertTrue(result["threads_finished"])
        self.assertEqual(result["active_locks"], 0)

    def test_safe_demo_is_repeatable(self):
        for _ in range(5):
            result = run_safe_demo()
            self.assertEqual(result["final_value"], 120)
            self.assertTrue(result["wait_detected"])


if __name__ == "__main__":
    unittest.main()
