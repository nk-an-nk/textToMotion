import copy
import unittest
from tts_benchmark import summarize, percentile


class TtsBenchmarkTest(unittest.TestCase):
    def records(self):
        protocol = {"event": "protocol", "run_id": "test", "repeats": 1,
                    "cases": [{"id": "short", "text": "こんにちは。"}]}
        trial = {"event": "trial", "run_id": "test", "case_id": "short", "text": "こんにちは。",
                 "repeat": 1, "warmup": False, "status": "ok", "request_ns": 1_000_000,
                 "call_return_ns": 3_000_000, "start_callback_ns": 2_000_000,
                 "complete_callback_ns": 12_000_000}
        warmup = dict(trial, repeat=0, warmup=True, start_callback_ns=10_000_000)
        return [protocol, warmup, trial,
                {"event": "finished", "run_id": "test", "status": "complete"}]

    def test_sdk_start_and_call_return_can_overlap(self):
        result = summarize(self.records())
        self.assertTrue(result["complete"])
        self.assertEqual(result["groups"]["all"]["sdk_start_wait_ms"]["mean"], 1)
        self.assertEqual(result["groups"]["all"]["notification_to_complete_ms"]["mean"], 10)
        self.assertEqual(result["successful_measured_trials"], 1)
        self.assertEqual(result["warmup_trials"], 1)

    def test_missing_start_is_not_zero_latency(self):
        data = self.records()
        data[2]["start_callback_ns"] = 0
        with self.assertRaisesRegex(ValueError, "timestamp"):
            summarize(data)

    def test_failed_trials_excluded(self):
        data = self.records()
        data[2]["status"] = "timeout"
        data[-1]["status"] = "timeout"
        result = summarize(data)
        self.assertFalse(result["complete"])
        self.assertEqual(result["groups"]["all"]["n"], 0)
        self.assertIsNone(result["groups"]["all"]["sdk_start_wait_ms"])

    def test_duplicate_rejected(self):
        data = self.records()
        data.insert(3, copy.deepcopy(data[2]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            summarize(data)

    def test_mixed_runs_rejected(self):
        data = self.records()
        data[2]["run_id"] = "other"
        with self.assertRaisesRegex(ValueError, "mixed"):
            summarize(data)

    def test_percentile(self):
        self.assertAlmostEqual(percentile([10, 20, 30], .95), 29)


if __name__ == "__main__":
    unittest.main()
