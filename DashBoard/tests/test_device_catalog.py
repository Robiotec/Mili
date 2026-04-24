import unittest

from surveillance.devices.catalog import build_device_catalog
from surveillance.web_runtime import CameraStreamDefinition, StreamRuntime, WebSettings


class DeviceCatalogTests(unittest.TestCase):
    def test_build_device_catalog_exposes_configured_locations(self):
        runtime = StreamRuntime(
            web_settings=WebSettings(),
            cameras={
                "cam1": CameraStreamDefinition(
                    camera_name="cam1",
                    source="rtsp://example.com/stream/1",
                    transport="tcp",
                    low_latency=False,
                    pass_through=False,
                )
            },
            states={},
        )

        catalog = build_device_catalog(
            {
                "IP_ADDRESS": {"cam1": "rtsp://example.com/stream/1"},
                "telemetry": {
                    "devices": {
                        "cam1": {
                            "lat": -2.170998,
                            "lon": -79.922359,
                        }
                    }
                },
            },
            runtime,
        )

        device = catalog.get("cam1")
        self.assertIsNotNone(device)
        self.assertAlmostEqual(device.lat, -2.170998)
        self.assertAlmostEqual(device.lon, -79.922359)
        self.assertEqual(device.source, "rtsp://example.com/stream/1")
        self.assertEqual(catalog.as_dicts()[0]["source"], "rtsp://example.com/stream/1")
        self.assertAlmostEqual(catalog.as_dicts()[0]["lat"], -2.170998)
        self.assertAlmostEqual(catalog.as_dicts()[0]["lon"], -79.922359)

    def test_build_device_catalog_infers_audio_for_hls_source(self):
        runtime = StreamRuntime(
            web_settings=WebSettings(),
            cameras={
                "cam_hls": CameraStreamDefinition(
                    camera_name="cam_hls",
                    source="http://example.com/live/index.m3u8",
                    transport="auto",
                    low_latency=True,
                    pass_through=False,
                )
            },
            states={},
        )

        catalog = build_device_catalog(
            {
                "IP_ADDRESS": {"cam_hls": "http://example.com/live/index.m3u8"},
                "audio": {
                    "devices": [],
                    "sources": {},
                },
            },
            runtime,
        )

        device = catalog.get("cam_hls")
        self.assertIsNotNone(device)
        self.assertTrue(device.capabilities.get("audio"))
        self.assertEqual(device.audio_source, "http://example.com/live/index.m3u8")


if __name__ == "__main__":
    unittest.main()
