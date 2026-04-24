import unittest

from gps_api_client import DummyDroneSource, GPSApiClient


class _FakeResponse:
    def __init__(self, payload, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, response):
        self._response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self._response

    def close(self):
        return None


class GPSApiClientTests(unittest.TestCase):
    def test_dummy_drone_source_can_publish_custom_device_id(self):
        source = DummyDroneSource(
            device_id="CAR1",
            start_lat=-2.0,
            start_lon=-79.0,
            step=0.5,
        )

        gps = source.read_gps()

        self.assertIsNotNone(gps)
        self.assertEqual(gps.id, "CAR1")
        self.assertAlmostEqual(gps.lat, -1.5)
        self.assertAlmostEqual(gps.lon, -78.5)
        self.assertAlmostEqual(gps.heading, 91.0)

    def test_get_latest_gps_selects_latest_matching_device_from_history(self):
        payload = [
            {
                "id": "OTRO-001",
                "lat": -2.100001,
                "lon": -79.900001,
                "timestamp": "2026-04-06T10:00:00Z",
            },
            {
                "id": "ROBIOCAR-001",
                "lat": -2.100100,
                "lon": -79.900100,
                "timestamp": "2026-04-06T10:01:00Z",
            },
            {
                "id": "ROBIOCAR-001",
                "lat": -2.100200,
                "lon": -79.900200,
                "timestamp": "2026-04-06T10:02:00Z",
            },
        ]
        client = GPSApiClient(base_url="http://127.0.0.1:8002")
        fake_session = _FakeSession(_FakeResponse(payload))
        client.session = fake_session

        gps = client.get_latest_gps(device_id="ROBIOCAR-001")

        self.assertIsNotNone(gps)
        self.assertEqual(gps.id, "ROBIOCAR-001")
        self.assertAlmostEqual(gps.lat, -2.100200)
        self.assertAlmostEqual(gps.lon, -79.900200)
        self.assertEqual(len(fake_session.calls), 1)
        request_url, kwargs = fake_session.calls[0]
        self.assertEqual(request_url, "http://127.0.0.1:8002/gps")
        self.assertEqual(kwargs["params"]["device_id"], "ROBIOCAR-001")
        self.assertEqual(kwargs["params"]["id"], "ROBIOCAR-001")
        self.assertEqual(kwargs["params"]["identifier"], "ROBIOCAR-001")
        self.assertIn("_ts", kwargs["params"])
        self.assertEqual(kwargs["headers"]["Cache-Control"], "no-cache, no-store, max-age=0")

    def test_get_latest_gps_supports_nested_location_payloads(self):
        payload = {
            "records": [
                {
                    "identifier": "ROBIOCAR-001",
                    "updated_at": "2026-04-06T12:34:56Z",
                    "location": {
                        "lat": "-2.189400",
                        "lng": "-79.889100",
                        "heading": "182.5",
                    },
                }
            ]
        }
        client = GPSApiClient(base_url="http://127.0.0.1:8002/gps")
        client.session = _FakeSession(_FakeResponse(payload))

        gps = client.get_latest_gps(device_id="ROBIOCAR-001")

        self.assertIsNotNone(gps)
        self.assertEqual(gps.id, "ROBIOCAR-001")
        self.assertAlmostEqual(gps.lat, -2.1894)
        self.assertAlmostEqual(gps.lon, -79.8891)
        self.assertAlmostEqual(gps.heading, 182.5)
        self.assertEqual(gps.timestamp, "2026-04-06T12:34:56Z")

if __name__ == "__main__":
    unittest.main()
