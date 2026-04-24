import unittest
from unittest import mock

from surveillance.telemetry.api_bridge import _ApiTelemetryBridgeWorker
from surveillance.vehicle_registry import VehicleRegistryEntry


class ApiTelemetryBridgeWorkerTests(unittest.TestCase):
    def test_read_gps_queries_expected_api_device_id(self):
        entry = VehicleRegistryEntry(
            registration_id="reg-1",
            created_ts=1.0,
            updated_ts=1.0,
            vehicle_type="automovil",
            label="Rayo McQueen",
            identifier="ABC-002",
            telemetry_mode="api",
            api_base_url="http://127.0.0.1:8002",
            api_device_id="ROBIOCAR-001",
        )
        worker = _ApiTelemetryBridgeWorker(
            entry=entry,
            telemetry_service=mock.Mock(),
            event_store=mock.Mock(),
        )
        client = mock.Mock()

        worker._read_gps(client, entry)

        client.get_latest_gps.assert_called_once_with(
            device_id="ROBIOCAR-001",
            prefer_vehicle_path=True,
        )


if __name__ == "__main__":
    unittest.main()
