import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import web_app
from surveillance.telemetry.service import TelemetryService
from surveillance.vehicle_registry import VehicleRegistryEntry, VehicleRegistryStore


class DummyRequest(dict):
    def __init__(self, *, payload=None, json_error: Exception | None = None, match_info=None, auth_user=None):
        super().__init__()
        self._payload = payload
        self._json_error = json_error
        self.cookies = {}
        self.match_info = match_info or {}
        if auth_user is not None:
            self["auth_user"] = auth_user

    async def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class VehicleRegistryRenderTests(unittest.TestCase):
    def test_render_registro_vehiculos_exposes_db_vehicle_fields(self):
        rendered = web_app._render_template("registro_vehiculos.html").decode("utf-8")

        self.assertIn('id="vehicle-register-organization"', rendered)
        self.assertIn('id="vehicle-register-owner"', rendered)
        self.assertIn('id="vehicle-register-telemetry-mode"', rendered)
        self.assertIn('id="vehicle-register-api-device-id"', rendered)
        self.assertIn('id="vehicle-register-camera-list"', rendered)
        self.assertIn('id="vehicle-register-delete"', rendered)
        self.assertIn("Cámaras asociadas", rendered)


class VehicleRegistryHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_vehicle_registry_create_accepts_db_payload(self):
        request = DummyRequest(
            payload={
                "organizacion_id": 7,
                "propietario_usuario_id": 9,
                "vehicle_type_code": "auto",
                "label": "Patrulla 01",
                "identifier": "ABC-123",
                "notes": "Unidad urbana",
                "telemetry_mode": "api",
                "api_base_url": "http://127.0.0.1:8002",
                "api_device_id": "car-01",
                "camera_links": [{"camera_id": 21, "position": "frontal"}],
            },
            auth_user={"id": 3, "rol": "developer", "nivel_orden": 100},
        )

        user_repo = mock.Mock()
        user_repo.list_roles.return_value = []
        user_repo.get_user_by_id.return_value = {"id": 9, "usuario": "admin1", "nivel_orden": 80}
        organization_repo = mock.Mock()
        organization_repo.get_organization_by_id.return_value = {"id": 7, "nombre": "Bonanza"}
        camera_repo = mock.Mock()
        camera_repo.list_cameras.return_value = [{"id": 21, "nombre": "CAM-21"}]

        with (
            mock.patch.object(web_app.APP_CONTEXT, "ensure_initialized"),
            mock.patch.object(web_app, "_ensure_database_ready"),
            mock.patch("web_app.UserRepository", return_value=user_repo),
            mock.patch("web_app.OrganizationRepository", return_value=organization_repo),
            mock.patch("web_app.CameraRepository", return_value=camera_repo),
            mock.patch.object(
                web_app.APP_CONTEXT,
                "register_vehicle",
                return_value={
                    "registration_id": "15",
                    "vehicle_type": "automovil",
                    "vehicle_type_code": "auto",
                    "label": "Patrulla 01",
                    "identifier": "ABC-123",
                    "telemetry_mode": "api",
                    "api_base_url": "http://127.0.0.1:8002",
                    "api_device_id": "car-01",
                    "camera_links": [{"camera_id": 21, "position": "frontal"}],
                },
            ) as register_vehicle,
        ):
            response = await web_app.handle_vehicle_registry_create(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 201)
        self.assertEqual(payload["telemetry_mode"], "api")
        register_vehicle.assert_called_once_with(
            organization_id=7,
            owner_user_id=9,
            created_by_user_id=3,
            vehicle_type_code="auto",
            label="Patrulla 01",
            identifier="ABC-123",
            notes="Unidad urbana",
            telemetry_mode="api",
            api_base_url="",
            api_device_id="car-01",
            active=True,
            camera_links=[{"camera_id": 21, "position": "frontal"}],
        )

    async def test_handle_vehicle_registry_update_accepts_camera_links(self):
        request = DummyRequest(
            payload={
                "organizacion_id": 4,
                "propietario_usuario_id": 6,
                "vehicle_type_code": "drone_dji",
                "label": "Dron 02",
                "identifier": "DRN-002",
                "notes": "Ajustado",
                "telemetry_mode": "api",
                "api_base_url": "http://127.0.0.1:8002",
                "api_device_id": "drn-002",
                "camera_links": [{"camera_id": 31, "position": "gimbal"}],
            },
            match_info={"registration_id": "22"},
            auth_user={"id": 1, "rol": "developer", "nivel_orden": 100},
        )

        user_repo = mock.Mock()
        user_repo.list_roles.return_value = []
        user_repo.get_user_by_id.return_value = {"id": 6, "usuario": "ing01", "nivel_orden": 50}
        organization_repo = mock.Mock()
        organization_repo.get_organization_by_id.return_value = {"id": 4, "nombre": "Operaciones"}
        vehicle_repo = mock.Mock()
        vehicle_repo.get_vehicle_by_id.return_value = {
            "id": 22,
            "registration_id": "22",
            "propietario_nivel_orden": 50,
            "creado_por_usuario_id": 1,
        }
        camera_repo = mock.Mock()
        camera_repo.list_cameras.return_value = [{"id": 31, "nombre": "CAM-31"}]

        with (
            mock.patch.object(web_app.APP_CONTEXT, "ensure_initialized"),
            mock.patch.object(web_app, "_ensure_database_ready"),
            mock.patch("web_app.UserRepository", return_value=user_repo),
            mock.patch("web_app.OrganizationRepository", return_value=organization_repo),
            mock.patch("web_app.VehicleRepository", return_value=vehicle_repo),
            mock.patch("web_app.CameraRepository", return_value=camera_repo),
            mock.patch.object(
                web_app.APP_CONTEXT,
                "update_registered_vehicle",
                return_value={
                    "registration_id": "22",
                    "vehicle_type": "dron",
                    "vehicle_type_code": "drone_dji",
                    "label": "Dron 02",
                    "identifier": "DRN-002",
                    "telemetry_mode": "api",
                    "camera_links": [{"camera_id": 31, "position": "gimbal"}],
                },
            ) as update_vehicle,
        ):
            response = await web_app.handle_vehicle_registry_update(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["registration_id"], "22")
        update_vehicle.assert_called_once_with(
            "22",
            organization_id=4,
            owner_user_id=6,
            vehicle_type_code="drone_dji",
            label="Dron 02",
            identifier="DRN-002",
            notes="Ajustado",
            telemetry_mode="api",
            api_base_url="",
            api_device_id="drn-002",
            active=True,
            camera_links=[{"camera_id": 31, "position": "gimbal"}],
        )

    async def test_handle_vehicle_registry_delete_returns_deleted_vehicle(self):
        request = DummyRequest(
            match_info={"registration_id": "33"},
            auth_user={"id": 1, "rol": "developer", "nivel_orden": 100},
        )

        user_repo = mock.Mock()
        user_repo.list_roles.return_value = []
        vehicle_repo = mock.Mock()
        vehicle_repo.get_vehicle_by_id.return_value = {"id": 33, "registration_id": "33", "propietario_nivel_orden": 80}

        with (
            mock.patch.object(web_app.APP_CONTEXT, "ensure_initialized"),
            mock.patch.object(web_app, "_ensure_database_ready"),
            mock.patch("web_app.UserRepository", return_value=user_repo),
            mock.patch("web_app.VehicleRepository", return_value=vehicle_repo),
            mock.patch.object(
                web_app.APP_CONTEXT,
                "delete_registered_vehicle",
                return_value={"registration_id": "33", "identifier": "PAT-003"},
            ) as delete_vehicle,
        ):
            response = await web_app.handle_vehicle_registry_delete(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["vehicle"]["registration_id"], "33")
        delete_vehicle.assert_called_once_with("33")


class VehicleRegistryStoreTests(unittest.TestCase):
    def test_register_vehicle_api_defaults_device_id_to_identifier(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = VehicleRegistryStore(Path(temp_dir) / "vehicle_registry.json")
            entry = store.register(
                vehicle_type="automovil",
                label="Patrulla 02",
                identifier="PAT-002",
                telemetry_mode="api",
                api_base_url="http://127.0.0.1:8002",
            )

            self.assertEqual(entry.telemetry_mode, "api")
            self.assertEqual(entry.api_device_id, "PAT-002")
            self.assertTrue(entry.has_live_telemetry)

    def test_register_vehicle_rejects_invalid_telemetry_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = VehicleRegistryStore(Path(temp_dir) / "vehicle_registry.json")

            with self.assertRaisesRegex(ValueError, "invalid_vehicle_telemetry_mode"):
                store.register(
                    vehicle_type="automovil",
                    label="Patrulla 03",
                    identifier="PAT-003",
                    telemetry_mode="legacy",
                )

    def test_update_vehicle_changes_identifier_and_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = VehicleRegistryStore(Path(temp_dir) / "vehicle_registry.json")
            created = store.register(
                vehicle_type="dron",
                label="Dron inicial",
                identifier="DRN-010",
                telemetry_mode="manual",
            )

            updated = store.update(
                created.registration_id,
                vehicle_type="automovil",
                label="Unidad 010",
                identifier="CAR-010",
                telemetry_mode="api",
                api_base_url="http://127.0.0.1:8002",
                notes="Migrado a GPS API",
            )

            self.assertEqual(updated.registration_id, created.registration_id)
            self.assertEqual(updated.identifier, "CAR-010")
            self.assertEqual(updated.vehicle_type, "automovil")
            self.assertEqual(updated.telemetry_mode, "api")
            self.assertEqual(updated.api_device_id, "CAR-010")
            self.assertIsNone(store.get("DRN-010"))
            self.assertIsNotNone(store.get("CAR-010"))

    def test_delete_vehicle_removes_it_from_store(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = VehicleRegistryStore(Path(temp_dir) / "vehicle_registry.json")
            created = store.register(
                vehicle_type="automovil",
                label="Unidad 011",
                identifier="CAR-011",
            )

            deleted = store.delete(created.registration_id)

            self.assertEqual(deleted.registration_id, created.registration_id)
            self.assertIsNone(store.get("CAR-011"))


class TelemetryServiceRegisteredDeviceTests(unittest.TestCase):
    def test_seed_registered_devices_includes_api_vehicle_metadata(self):
        service = TelemetryService()
        entry = VehicleRegistryEntry(
            registration_id="reg-1",
            created_ts=1.0,
            updated_ts=1.0,
            vehicle_type="automovil",
            label="Patrulla 04",
            identifier="PAT-004",
            notes="GPS externo",
            telemetry_mode="api",
            api_base_url="http://127.0.0.1:8002",
            api_device_id="car-04",
            camera_name="CAM-77",
            owner_level=80,
        )

        service.seed_registered_devices([entry])
        metadata = service.get_device_metadata("PAT-004")

        self.assertIsNotNone(metadata)
        self.assertEqual(metadata["telemetry_mode"], "api")
        self.assertEqual(metadata["api_device_id"], "car-04")
        self.assertEqual(metadata["vehicle_type"], "automovil")
        self.assertEqual(metadata["camera_name"], "CAM-77")
        self.assertEqual(metadata["owner_level"], 80)
