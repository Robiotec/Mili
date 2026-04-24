import unittest
from unittest.mock import patch

from surveillance.web_runtime import (
    build_stream_runtime,
    build_web_settings,
    camera_uses_pass_through,
)


class WebRuntimeSettingsTests(unittest.TestCase):
    def test_build_web_settings_parses_background_worker_controls(self):
        settings = build_web_settings(
            {
                "web": {
                    "run_without_viewers": True,
                    "always_on_cameras": ["cam1", "cam2", "cam1"],
                    "preload_shared_resources": False,
                    "supervisor_poll_sec": 0.2,
                    "worker_idle_shutdown_sec": 120.0,
                }
            }
        )

        self.assertTrue(settings.run_without_viewers)
        self.assertEqual(settings.always_on_cameras, ("cam1", "cam2"))
        self.assertFalse(settings.preload_shared_resources)
        self.assertEqual(settings.supervisor_poll_sec, 0.5)
        self.assertEqual(settings.worker_idle_shutdown_sec, 120.0)

    def test_build_stream_runtime_supports_global_pass_through(self):
        runtime = build_stream_runtime(
            {
                "paths": {"video": "rtsp://example.com/base"},
                "IP_ADDRESS": {
                    "cam1": "rtsp://example.com/stream/1",
                    "cam2": "rtsp://example.com/stream/2",
                },
                "stream": {
                    "pass_through_by_camera": ["*"],
                },
            }
        )

        self.assertTrue(runtime.cameras["cam1"].pass_through)
        self.assertTrue(runtime.cameras["cam2"].pass_through)

    def test_camera_uses_pass_through_supports_all_alias(self):
        self.assertTrue(
            camera_uses_pass_through(
                {"pass_through_by_camera": ["all"]},
                "camara.nueva",
            )
        )

    def test_build_stream_runtime_normalizes_network_camera_sources(self):
        with patch(
            "surveillance.web_runtime.normalize_camera_source",
            side_effect=lambda value: str(value).replace("/player/", "/player/index.m3u8"),
        ):
            runtime = build_stream_runtime(
                {
                    "IP_ADDRESS": {
                        "cam1": "http://example.com/player/",
                    },
                }
            )

        self.assertEqual(runtime.cameras["cam1"].source, "http://example.com/player/index.m3u8")


if __name__ == "__main__":
    unittest.main()
