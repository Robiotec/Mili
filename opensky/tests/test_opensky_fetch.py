import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import opensky_fetch


class OpenSkyFetchTests(unittest.TestCase):
    def test_parse_alt_m_handles_ground_and_numeric_values(self):
        self.assertEqual(opensky_fetch._parse_alt_m("ground"), 0.0)
        self.assertEqual(opensky_fetch._parse_alt_m(None), 0.0)
        self.assertAlmostEqual(opensky_fetch._parse_alt_m(1000), 304.8)
        self.assertIsNone(opensky_fetch._parse_alt_m("bad"))

    def test_fetch_states_deduplicates_by_icao_and_skips_missing_coords(self):
        responses = [
            {
                "ac": [
                    {"hex": "abc123", "lat": -2.1, "lon": -79.9, "flight": "TEST1", "alt_baro": 1000, "gs": 100, "track": 90},
                    {"hex": "missing", "lat": None, "lon": -79.0},
                ]
            },
            {
                "ac": [
                    {"hex": "abc123", "lat": -2.2, "lon": -79.8, "flight": "DUP", "alt_baro": 1200, "gs": 110, "track": 100},
                    {"hex": "def456", "lat": -2.3, "lon": -79.7, "flight": "TEST2", "alt_baro": "ground", "gs": None, "track": None},
                ]
            },
        ]

        class _Resp:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        with mock.patch.object(opensky_fetch, "QUERY_POINTS", [{"lat": 0, "lon": 0, "radius": 1}, {"lat": 1, "lon": 1, "radius": 1}]), \
             mock.patch.object(opensky_fetch.requests, "get", side_effect=[_Resp(item) for item in responses]), \
             mock.patch.object(opensky_fetch.time, "sleep", return_value=None):
            aircraft = opensky_fetch.fetch_states()

        self.assertEqual(len(aircraft), 2)
        ids = {item["icao24"] for item in aircraft}
        self.assertEqual(ids, {"abc123", "def456"})

    def test_save_writes_atomic_json_payload(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "opensky_data.json"
            with mock.patch.object(opensky_fetch, "OUT_FILE", out_file), \
                 mock.patch.object(opensky_fetch.time, "time", return_value=1234567890):
                opensky_fetch.save([{"icao24": "abc123"}])

            payload = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(payload["ts"], 1234567890)
            self.assertEqual(payload["aircraft"], [{"icao24": "abc123"}])


if __name__ == "__main__":
    unittest.main()
