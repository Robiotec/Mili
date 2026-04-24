import unittest

from controllers.register_cameras.register_camera import (
    CameraRTSPConfig,
    RTSPGenerator,
    get_rtsp_brand_presets,
    normalize_rtsp_brand,
)


class CameraRTSPGeneratorTests(unittest.TestCase):
    def test_brand_catalog_exposes_supported_presets(self):
        presets = get_rtsp_brand_presets()

        codes = {item["code"] for item in presets}

        self.assertIn("hikvision", codes)
        self.assertIn("dahua", codes)
        self.assertIn("axis", codes)
        self.assertIn("uniview", codes)
        self.assertIn("generic", codes)
        self.assertIn("custom_path", codes)

    def test_normalize_rtsp_brand_maps_known_aliases(self):
        self.assertEqual(normalize_rtsp_brand("hik"), "hikvision")
        self.assertEqual(normalize_rtsp_brand("dawa"), "dahua")
        self.assertEqual(normalize_rtsp_brand("onvif"), "generic")
        self.assertEqual(normalize_rtsp_brand("custom"), "custom_path")

    def test_generator_omits_credentials_when_not_provided(self):
        config = CameraRTSPConfig(
            marca="hikvision",
            ip="192.168.10.20",
            usuario="",
            password="",
        )

        url = RTSPGenerator.generar(config)

        self.assertEqual(url, "rtsp://192.168.10.20:554/Streaming/Channels/101")

    def test_generator_supports_custom_path_brand(self):
        config = CameraRTSPConfig(
            marca="custom_path",
            ip="10.0.0.8",
            usuario="admin",
            password="1234",
            ruta_personalizada="live/ch00_1",
        )

        url = RTSPGenerator.generar(config)

        self.assertEqual(url, "rtsp://admin:1234@10.0.0.8:554/live/ch00_1")
