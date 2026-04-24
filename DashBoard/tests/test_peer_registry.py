import unittest

from surveillance.web.peers import PeerRegistry


class DummyPeer:
    def __init__(self, state: str = "new", ice_state: str = "new"):
        self.connectionState = state
        self.iceConnectionState = ice_state


class PeerRegistryTests(unittest.TestCase):
    def test_register_enforces_max_clients_per_camera(self):
        registry = PeerRegistry()
        first_peer = DummyPeer(state="connected")
        second_peer = DummyPeer(state="connected")

        accepted, active_clients = registry.register("cam1", first_peer, 1)
        self.assertTrue(accepted)
        self.assertEqual(active_clients, 1)

        accepted, active_clients = registry.register("cam1", second_peer, 1)
        self.assertFalse(accepted)
        self.assertEqual(active_clients, 1)

    def test_unregister_removes_peer_from_camera_count(self):
        registry = PeerRegistry()
        peer = DummyPeer(state="connected")

        accepted, active_clients = registry.register("cam1", peer, 2)
        self.assertTrue(accepted)
        self.assertEqual(active_clients, 1)

        active_clients = registry.unregister("cam1", peer)
        self.assertEqual(active_clients, 0)
        self.assertEqual(registry.snapshot_active_counts(), {})

    def test_snapshot_prunes_disconnected_peers(self):
        registry = PeerRegistry()
        peer = DummyPeer(state="disconnected")

        accepted, active_clients = registry.register("cam1", peer, 2)
        self.assertTrue(accepted)
        self.assertEqual(active_clients, 1)

        self.assertEqual(registry.snapshot_active_counts(), {})

    def test_snapshot_prunes_disconnected_ice_peers(self):
        registry = PeerRegistry()
        peer = DummyPeer(state="connected", ice_state="disconnected")

        accepted, active_clients = registry.register("cam1", peer, 2)
        self.assertTrue(accepted)
        self.assertEqual(active_clients, 1)

        self.assertEqual(registry.snapshot_active_counts(), {})


if __name__ == "__main__":
    unittest.main()
