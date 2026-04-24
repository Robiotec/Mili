import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from surveillance.config import (
    is_network_path,
    normalize_camera_source,
    read_yaml,
    register_camera_source,
    resolve_camera_viewer_url,
)


class CameraRegistrationConfigTests(unittest.TestCase):
    def test_normalize_camera_source_rewrites_mediamtx_player_page_to_manifest(self):
        html = """
        <!DOCTYPE html>
        <html>
        <body>
        <script>
        hls.loadSource('index.m3u8' + window.location.search);
        </script>
        </body>
        </html>
        """

        class FakeResponse:
            def __init__(self, payload):
                self.headers = {"Content-Type": "text/html; charset=utf-8"}
                self._payload = payload.encode("utf-8")

            def read(self, size=-1):
                return self._payload if size < 0 else self._payload[:size]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        normalize_camera_source.cache_clear()
        with patch("surveillance.config.urlopen", return_value=FakeResponse(html)):
            resolved = normalize_camera_source("http://example.com/labcam_202/?controls=1")

        self.assertEqual(resolved, "http://example.com/labcam_202/index.m3u8?controls=1")

    def test_is_network_path_accepts_srt_sources(self):
        self.assertTrue(is_network_path("srt://example.com:9000?mode=caller"))

    def test_resolve_camera_viewer_url_detects_mediamtx_webrtc_page(self):
        html = """
        <!DOCTYPE html>
        <html>
        <body>
        <script>
        new MediaMTXWebRTCReader({
          url: new URL('whep', window.location.href) + window.location.search,
        });
        </script>
        </body>
        </html>
        """

        class FakeResponse:
            def __init__(self, payload):
                self.headers = {"Content-Type": "text/html; charset=utf-8"}
                self._payload = payload.encode("utf-8")

            def read(self, size=-1):
                return self._payload if size < 0 else self._payload[:size]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        resolve_camera_viewer_url.cache_clear()
        with patch("surveillance.config.urlopen", return_value=FakeResponse(html)):
            resolved = resolve_camera_viewer_url("http://example.com/labcam_202/?controls=1")

        self.assertEqual(resolved, "http://example.com/labcam_202/?controls=1")

    def test_normalize_camera_source_preserves_inference_subpath_for_mediamtx(self):
        html = """
        <!DOCTYPE html>
        <html>
        <body>
        <script>
        new MediaMTXWebRTCReader({
          url: new URL('whep', window.location.href) + window.location.search,
        });
        </script>
        </body>
        </html>
        """

        class FakeResponse:
            def __init__(self, payload):
                self.headers = {"Content-Type": "text/html; charset=utf-8"}
                self._payload = payload.encode("utf-8")

            def read(self, size=-1):
                return self._payload if size < 0 else self._payload[:size]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        normalize_camera_source.cache_clear()
        with patch("surveillance.config.urlopen", return_value=FakeResponse(html)):
            resolved = normalize_camera_source("http://example.com:8889/yandri/INFERENCE?controls=1")

        self.assertEqual(resolved, "rtsp://example.com:8554/yandri/INFERENCE")

    def test_register_camera_source_persists_camera_and_initial_location(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.yaml"
            config_path.write_text(
                textwrap.dedent(
                    """\
                    telemetry:
                      stale_after_sec: 10
                      lost_after_sec: 30
                      devices: {}

                    audio:
                      devices: []
                      sources: {}

                    IP_ADDRESS:
                      cam1: "rtsp://example.com/stream/1"
                    """
                ),
                encoding="utf-8",
            )

            register_camera_source(
                config_path,
                camera_name="cam2",
                source="rtsp://example.com/stream/2",
                lat=-2.170998,
                lon=-79.922359,
                audio_source="rtsp://example.com/stream/2",
            )

            saved = read_yaml(config_path)

            self.assertEqual(saved["IP_ADDRESS"]["cam2"], "rtsp://example.com/stream/2")
            self.assertAlmostEqual(saved["telemetry"]["devices"]["cam2"]["lat"], -2.170998)
            self.assertAlmostEqual(saved["telemetry"]["devices"]["cam2"]["lon"], -79.922359)
            self.assertEqual(saved["audio"]["sources"]["cam2"], "rtsp://example.com/stream/2")

    def test_register_camera_source_rejects_webrtc_style_sources(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.yaml"
            config_path.write_text("IP_ADDRESS: {}\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unsupported_camera_source_protocol"):
                register_camera_source(
                    config_path,
                    camera_name="cam_webrtc",
                    source="webrtc://example.com/live/cam1",
                )

    def tearDown(self) -> None:
        normalize_camera_source.cache_clear()
        resolve_camera_viewer_url.cache_clear()


if __name__ == "__main__":
    unittest.main()
