import json
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from app.routers import objetivo


class ObjetivoRouterTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.original_objetivos_dir = objetivo.OBJETIVOS_DIR
        self.original_latest_dir = objetivo.OBJETIVOS_LATEST_DIR
        objetivo.OBJETIVOS_DIR = Path(self.tmpdir.name)
        objetivo.OBJETIVOS_LATEST_DIR = objetivo.OBJETIVOS_DIR / "latest"
        objetivo.OBJETIVOS.clear()

    def tearDown(self):
        objetivo.OBJETIVOS.clear()
        objetivo.OBJETIVOS_DIR = self.original_objetivos_dir
        objetivo.OBJETIVOS_LATEST_DIR = self.original_latest_dir
        self.tmpdir.cleanup()

    def test_update_and_get_objetivo(self):
        payload = objetivo.ObjetivoPayload(latitud=-2.12, longitud=-79.89)
        response = objetivo.update_objetivo("DRONE", payload)

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"].id, "DRONE")
        self.assertEqual(response["data"].latitud, -2.12)
        self.assertEqual(response["data"].longitud, -79.89)

        get_response = objetivo.get_objetivo("DRONE")
        self.assertTrue(get_response["ok"])
        self.assertEqual(get_response["data"].id, "DRONE")

    def test_list_objetivos_returns_all_entries(self):
        objetivo.update_objetivo("DRONE", objetivo.ObjetivoPayload(latitud=-2.12, longitud=-79.89))
        objetivo.update_objetivo("CAR1", objetivo.ObjetivoPayload(latitud=-2.0, longitud=-79.8))

        response = objetivo.list_objetivos()
        self.assertTrue(response["ok"])
        self.assertEqual(response["count"], 2)
        ids = {item.id for item in response["data"]}
        self.assertEqual(ids, {"DRONE", "CAR1"})

    def test_update_persists_active_points_in_latest_folder(self):
        objetivo.update_objetivo("DRONE", objetivo.ObjetivoPayload(latitud=-2.12, longitud=-79.89))
        objetivo.update_objetivo("DRONE", objetivo.ObjetivoPayload(latitud=-2.13, longitud=-79.90))

        payload = json.loads((objetivo.OBJETIVOS_LATEST_DIR / "DRONE.json").read_text(encoding="utf-8"))

        self.assertEqual(payload["data"]["latitud"], -2.13)
        self.assertEqual(len(payload["points"]), 2)
        self.assertEqual([point["latitud"] for point in payload["points"]], [-2.12, -2.13])

    def test_get_recovers_objetivo_from_latest_folder_after_memory_loss(self):
        objetivo.update_objetivo("DRONE", objetivo.ObjetivoPayload(latitud=-2.12, longitud=-79.89))
        objetivo.OBJETIVOS.clear()

        response = objetivo.get_objetivo("DRONE")

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"].id, "DRONE")
        self.assertEqual(response["data"].latitud, -2.12)

    def test_clear_objetivo_removes_latest_state(self):
        objetivo.update_objetivo("DRONE", objetivo.ObjetivoPayload(latitud=-2.12, longitud=-79.89))
        self.assertTrue((objetivo.OBJETIVOS_LATEST_DIR / "DRONE.json").exists())

        delete_response = objetivo.clear_objetivo("DRONE")
        self.assertTrue(delete_response["ok"])
        self.assertTrue(delete_response["cleared"])
        self.assertTrue(delete_response["existed"])
        self.assertFalse((objetivo.OBJETIVOS_LATEST_DIR / "DRONE.json").exists())

        with self.assertRaises(HTTPException) as exc:
            objetivo.get_objetivo("DRONE")
        self.assertEqual(exc.exception.status_code, 404)

    def test_get_missing_objetivo_returns_404(self):
        with self.assertRaises(HTTPException) as exc:
            objetivo.get_objetivo("UNKNOWN")
        self.assertEqual(exc.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
