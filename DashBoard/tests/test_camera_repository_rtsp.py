import tempfile
import types
import sys
import unittest
from pathlib import Path

if "psycopg" not in sys.modules:
    fake_psycopg = types.ModuleType("psycopg")
    fake_psycopg_rows = types.ModuleType("psycopg.rows")
    fake_psycopg_rows.dict_row = object()
    fake_psycopg_pool = types.ModuleType("psycopg_pool")

    class _FakeConnectionPool:
        def __init__(self, *args, **kwargs):
            pass

        @staticmethod
        def check_connection(*args, **kwargs):
            return True

    fake_psycopg_pool.ConnectionPool = _FakeConnectionPool
    sys.modules["psycopg"] = fake_psycopg
    sys.modules["psycopg.rows"] = fake_psycopg_rows
    sys.modules["psycopg_pool"] = fake_psycopg_pool

if "dotenv" not in sys.modules:
    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *args, **kwargs: False
    sys.modules["dotenv"] = fake_dotenv

from repositories.querys_camera import CameraRepository
from surveillance.app_context import ApplicationContext


class CameraRepositoryRtspTests(unittest.TestCase):
    def test_normalize_bool_supports_inference_toggle_values(self):
        repo = CameraRepository()

        self.assertTrue(repo._normalize_bool("true", default=False))
        self.assertFalse(repo._normalize_bool("false", default=True))

    def test_normalize_stream_url_accepts_empty_value(self):
        repo = CameraRepository()

        self.assertEqual(repo._normalize_stream_url(""), "")

    def test_normalize_rtsp_url_accepts_rtsp_scheme(self):
        repo = CameraRepository()

        self.assertEqual(
            repo._normalize_rtsp_url("rtsp://operador:clave@192.168.1.64:554/Streaming/Channels/101"),
            "rtsp://operador:clave@192.168.1.64:554/Streaming/Channels/101",
        )

    def test_normalize_rtsp_url_rejects_non_rtsp_scheme(self):
        repo = CameraRepository()

        with self.assertRaisesRegex(ValueError, "invalid_camera_rtsp_url"):
            repo._normalize_rtsp_url("https://example.com/live/index.m3u8")

    def test_normalize_camera_ip_prefers_explicit_value(self):
        repo = CameraRepository()

        self.assertEqual(
            repo._normalize_camera_ip(
                "192.168.1.88",
                "rtsp://operador:clave@192.168.1.64:554/Streaming/Channels/101",
            ),
            "192.168.1.88",
        )

    def test_normalize_camera_ip_extracts_host_from_rtsp_url(self):
        repo = CameraRepository()

        self.assertEqual(
            repo._normalize_camera_ip(
                "",
                "rtsp://operador:clave@192.168.1.64:554/Streaming/Channels/101",
            ),
            "192.168.1.64",
        )


class ApplicationContextRtspProjectionTests(unittest.TestCase):
    def test_database_projection_uses_rtsp_when_stream_url_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.yaml"
            config_path.write_text("IP_ADDRESS: {}\n", encoding="utf-8")

            ctx = ApplicationContext(config_path)
            try:
                cfg_data = {"web": {}, "telemetry": {}}
                projected = ctx._apply_database_camera_projection(
                    cfg_data,
                    [
                        {
                            "id": 9,
                            "nombre": "camara_rtsp",
                            "url_stream": "",
                            "url_rtsp": "rtsp://192.168.1.50:554/Streaming/Channels/101",
                            "organizacion_id": 2,
                            "vehiculo_id": None,
                            "vehiculo_nombre": "",
                            "vehiculo_tipo_codigo": "vehicle",
                            "propietario_rol_codigo": "admin",
                            "propietario_nivel_orden": 2,
                            "tipo_camara_codigo": "static",
                            "protocolo_codigo": "rtsp",
                            "latitud_mapa": -2.18,
                            "longitud_mapa": -79.88,
                            "altitud_mapa": 5.0,
                        }
                    ],
                )
            finally:
                ctx.api_bridge_manager.stop()

        self.assertEqual(
            projected["IP_ADDRESS"]["camara_rtsp"],
            "rtsp://192.168.1.50:554/Streaming/Channels/101",
        )
        self.assertEqual(
            projected["camera_registry"]["cameras"]["camara_rtsp"]["rtsp_url"],
            "rtsp://192.168.1.50:554/Streaming/Channels/101",
        )

    def test_database_projection_appends_inference_suffix_for_managed_http_stream(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.yaml"
            config_path.write_text("IP_ADDRESS: {}\n", encoding="utf-8")

            ctx = ApplicationContext(config_path)
            try:
                cfg_data = {"web": {}, "telemetry": {}}
                projected = ctx._apply_database_camera_projection(
                    cfg_data,
                    [
                        {
                            "id": 10,
                            "nombre": "drone",
                            "url_stream": "http://127.0.0.1:8989/drone",
                            "url_rtsp": "",
                            "hacer_inferencia": True,
                            "organizacion_id": 2,
                            "vehiculo_id": None,
                            "vehiculo_nombre": "",
                            "vehiculo_tipo_codigo": "static",
                            "propietario_rol_codigo": "admin",
                            "propietario_nivel_orden": 2,
                            "tipo_camara_codigo": "static",
                            "protocolo_codigo": "http",
                            "latitud_mapa": -2.18,
                            "longitud_mapa": -79.88,
                            "altitud_mapa": 5.0,
                        }
                    ],
                )
            finally:
                ctx.api_bridge_manager.stop()

        self.assertEqual(
            projected["IP_ADDRESS"]["drone"],
            "http://127.0.0.1:8989/drone/INFERENCE",
        )
        self.assertEqual(
            projected["camera_registry"]["cameras"]["drone"]["display_name"],
            "drone - INF",
        )
        self.assertEqual(
            projected["camera_registry"]["cameras"]["drone"]["stream_url"],
            "http://127.0.0.1:8989/drone/INFERENCE",
        )
