import tempfile
import textwrap
import unittest
from pathlib import Path

from surveillance.app_context import ApplicationContext
from surveillance.config import read_yaml


class ApplicationContextCameraRegistrationTests(unittest.TestCase):
    def test_register_camera_preserves_direct_source_for_ui(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.yaml"
            config_path.write_text(
                textwrap.dedent(
                    """\
                    web:
                      default_camera: ""

                    telemetry:
                      devices: {}

                    audio:
                      devices: []
                      sources: {}

                    IP_ADDRESS: {}
                    """
                ),
                encoding="utf-8",
            )

            ctx = ApplicationContext(config_path)
            try:
                device = ctx.register_camera(
                    "camara.nueva",
                    "https://example.com/live/index.m3u8",
                )

                self.assertEqual(device["source"], "https://example.com/live/index.m3u8")
                self.assertEqual(
                    ctx.device_catalog.by_camera_name("camara.nueva").source,
                    "https://example.com/live/index.m3u8",
                )
                saved = read_yaml(config_path)
                self.assertEqual(
                    saved["IP_ADDRESS"]["camara.nueva"],
                    "https://example.com/live/index.m3u8",
                )
            finally:
                ctx.api_bridge_manager.stop()


if __name__ == "__main__":
    unittest.main()
