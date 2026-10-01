import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("collector", ROOT / "collector.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class ReportTests(unittest.TestCase):
    def report(self, header, lines):
        return "PowerTOP\n\n# Overview of Software Power Consumers\n\n" + header + "\n" + lines

    def test_activity_is_not_presented_as_watts(self):
        raw = self.report("Usage,Wakeups/s,GPU ops/s,Disk IO/s,GFX Wakeups/s,Category,Description",
                          "1 ms/s,12,,,,Process,[PID 1] /usr/bin/browser --renderer\n"
                          "2 ms/s,8,,,,Process,[PID 2] /usr/bin/browser\n"
                          "3 ms/s,100,,,,Timer,tick_nohz_handler\n"
                          "1 ms/s,500,,,,Process,[PID 3] [kworker/1]\n"
                          "The battery reports a discharge rate of: , 14.3 W\n")
        sample = collector.parse_report(raw)
        self.assertEqual(sample["mode"], "activity")
        self.assertEqual(sample["dischargeWatts"], 14.3)
        self.assertEqual(sample["apps"], [{"name": "browser", "watts": None,
                                          "wakeups": 20, "processes": 2}])

    def test_power_units_and_process_aggregation(self):
        raw = self.report("Power est.,Usage,Wakeups/s,Category,Description",
                          '250 mW,1 ms/s,12,Process,"[PID 1] /usr/bin/browser --flags=a,b"\n'
                          "0.5 W,2 ms/s,8,Process,[PID 2] /usr/bin/browser\n"
                          "1.2 W,1 ms/s,1,Process,[PID 3] /usr/bin/editor\n")
        sample = collector.parse_report(raw)
        self.assertEqual(sample["mode"], "power")
        self.assertEqual([a["name"] for a in sample["apps"]], ["editor", "browser"])
        self.assertEqual(sample["apps"][1]["watts"], 0.75)

    def test_missing_power_is_unknown_not_zero(self):
        raw = self.report("Power est.,Usage,Wakeups/s,Category,Description",
                          "1 W,1 ms/s,12,Process,[PID 1] browser\n"
                          ",2 ms/s,8,Process,[PID 2] browser\n")
        sample = collector.parse_report(raw)
        self.assertEqual(sample["mode"], "activity")
        self.assertIsNone(sample["apps"][0]["watts"])

    def test_missing_table_is_rejected(self):
        with self.assertRaises(ValueError):
            collector.parse_report("PowerTOP\n# System Information\n")

    def test_unrecognised_unit_is_not_watts(self):
        self.assertIsNone(collector.number("15%", "W"))
        self.assertIsNone(collector.number("nan W", "W"))
        self.assertEqual(collector.number("0 W", "W"), 0)


if __name__ == "__main__":
    unittest.main()
