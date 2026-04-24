import unittest

from controllers.api_protect_stream.protect_stream import (
    ViewerLaunchOptions,
    build_patched_protected_viewer_html,
    replace_viewer_location_references,
)


class AuthorizedViewerHtmlTests(unittest.TestCase):
    def test_replace_viewer_location_references_rewrites_href_and_search(self):
        source = """
        <script>
        const whep = new URL('whep', window.location.href) + window.location.search;
        const again = location.href + location.search;
        </script>
        """

        rewritten = replace_viewer_location_references(source)

        self.assertIn("window.__AUTHORIZED_VIEWER_URL__", rewritten)
        self.assertIn("window.__AUTHORIZED_VIEWER_SEARCH__", rewritten)
        self.assertNotIn("window.location.href", rewritten)
        self.assertNotIn("window.location.search", rewritten)

    def test_build_patched_protected_viewer_html_injects_base_bootstrap_and_autoplay_patch(self):
        source = """
        <!DOCTYPE html>
        <html>
        <head>
          <script src="reader.js"></script>
        </head>
        <body>
          <video></video>
          <script>
          new MediaMTXWebRTCReader({
            url: new URL('whep', window.location.href) + window.location.search,
          });
          </script>
        </body>
        </html>
        """

        result = build_patched_protected_viewer_html(
            source,
            "http://example.com:8889/labcam_202/?token=abc123",
            options=ViewerLaunchOptions(autoplay=True, muted=True, controls=True),
        )

        self.assertIn('<base href="http://example.com:8889/labcam_202/">', result)
        self.assertIn("window.__AUTHORIZED_VIEWER_URL__", result)
        self.assertIn("window.__AUTHORIZED_VIEWER_SEARCH__", result)
        self.assertIn("__authorized_stream_panel", result)
        self.assertIn("window.setViewerAudio = (payload = {}) => {", result)
        self.assertIn("video.volume = currentMuted ? 0 : currentVolume;", result)
        self.assertIn("video.autoplay = autoplayEnabled;", result)


if __name__ == "__main__":
    unittest.main()
