import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))

from src.parse import DisabledExport, InvalidExport, interpret_export, parse_since_stream


STREAM = """
{"type":"presence","schema":"idea-usage-presence/1","day":"2026-11-09","payload":{"schema":"idea-usage-presence/1","engine":"happy-zebra","ts":"2026-11-09T08:00:00+02:00","bootId":"b1","uptimeS":3600,"ntpSynced":true}}
{"type":"day","schema":"idea-usage-day/1","day":"2026-11-09","instance":"kolibri-a","payload":{"schema":"idea-usage-day/1","engine":"happy-zebra","day":"2026-11-09","app":"kolibri","instance":"kolibri-a","hookStatus":"ok"}}
{"type":"sample","schema":"idea-usage-sample/1","day":"2026-11-09","instance":"nextcloud-a","payload":{"schema":"idea-usage-sample/1","app":"nextcloud","office":{"documentIds":["abc"],"byGroup":{"teacher":1}}}}
{"type":"end","schema":"idea-usage-export/1","since":"2026-11-09","engine":"happy-zebra","usageMonitoring":"on","counts":{"day":1,"sample":1,"presence":1},"errors":0}
"""


class ParseTests(unittest.TestCase):
    def test_stream(self):
        parsed = parse_since_stream(STREAM)
        self.assertEqual(len(parsed["presence"]), 1)
        self.assertEqual(len(parsed["days"]), 1)
        self.assertEqual(len(parsed["samples"]), 1)
        self.assertEqual(parsed["end"]["counts"]["day"], 1)
        self.assertEqual(parsed["days"][0]["instance"], "kolibri-a")
        self.assertEqual(parsed["days"][0]["payload"]["instance"], "kolibri-a")

    def test_disabled_is_state(self):
        with self.assertRaises(DisabledExport):
            interpret_export(10, "", "disabled\n")

    def test_disabled_with_body_rejected(self):
        with self.assertRaises(InvalidExport):
            interpret_export(10, "{}\n", "disabled\n")

    def test_invalid_json(self):
        with self.assertRaises(InvalidExport):
            parse_since_stream('{"type":"day"}\nnot-json\n{"type":"end"}\n')

    def test_missing_end(self):
        with self.assertRaises(InvalidExport):
            parse_since_stream('{"type":"day","payload":{}}\n')

    def test_unknown_type_ignored(self):
        text = STREAM.replace(
            '{"type":"end"',
            '{"type":"future","payload":{}}\n{"type":"end"',
        )
        parsed = parse_since_stream(text)
        self.assertIsNotNone(parsed["end"])


if __name__ == "__main__":
    unittest.main()
