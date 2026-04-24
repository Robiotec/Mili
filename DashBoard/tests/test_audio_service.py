import unittest

from surveillance.web.audio import _build_player_options


class CameraAudioPlayerOptionsTests(unittest.TestCase):
    def test_rtsp_audio_player_requests_audio_only(self):
        options = _build_player_options(
            "rtsp://example.com/stream/1",
            "tcp",
            low_latency=True,
        )

        self.assertIsNotNone(options)
        self.assertEqual(options["rtsp_transport"], "tcp")
        self.assertEqual(options["allowed_media_types"], "audio")
        self.assertEqual(options["fflags"], "nobuffer")
        self.assertEqual(options["flags"], "low_delay")


if __name__ == "__main__":
    unittest.main()
