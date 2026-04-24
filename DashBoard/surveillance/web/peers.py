from __future__ import annotations

import threading

from aiortc import RTCPeerConnection


class PeerRegistry:
    def __init__(self):
        self.lock = threading.Lock()
        self.peer_connections: set[RTCPeerConnection] = set()
        self.camera_peers: dict[str, set[RTCPeerConnection]] = {}
        self.detached_peers: set[RTCPeerConnection] = set()

    @staticmethod
    def _normalized_state(pc: RTCPeerConnection, attr_name: str) -> str:
        raw = getattr(pc, attr_name, "")
        return str(raw or "").strip().lower()

    def _is_stale_peer(self, pc: RTCPeerConnection) -> bool:
        stale_states = {"closed", "failed", "disconnected"}
        return (
            self._normalized_state(pc, "connectionState") in stale_states
            or self._normalized_state(pc, "iceConnectionState") in stale_states
        )

    def _prune_stale_peers_locked(self, camera_name: str) -> int:
        peers = self.camera_peers.get(camera_name)
        if peers is None:
            return 0

        stale = [pc for pc in peers if self._is_stale_peer(pc)]
        for pc in stale:
            peers.discard(pc)
            self.peer_connections.discard(pc)
            self.detached_peers.discard(pc)

        if not peers:
            self.camera_peers.pop(camera_name, None)
            return 0

        return len(peers)

    def register(self, camera_name: str, pc: RTCPeerConnection, max_clients: int) -> tuple[bool, int]:
        with self.lock:
            current = self._prune_stale_peers_locked(camera_name)
            if current >= max_clients:
                return False, current

            peers = self.camera_peers.setdefault(camera_name, set())
            peers.add(pc)
            self.peer_connections.add(pc)
            self.detached_peers.discard(pc)
            return True, len(peers)

    def unregister(self, camera_name: str, pc: RTCPeerConnection) -> int:
        with self.lock:
            if pc in self.detached_peers:
                self.detached_peers.discard(pc)
                return self._prune_stale_peers_locked(camera_name)

            self.detached_peers.add(pc)
            self.peer_connections.discard(pc)

            peers = self.camera_peers.get(camera_name)
            if peers is not None:
                peers.discard(pc)
                return self._prune_stale_peers_locked(camera_name)

            return 0

    def snapshot_active_counts(self) -> dict[str, int]:
        with self.lock:
            active_by_camera: dict[str, int] = {}
            for camera_name in list(self.camera_peers.keys()):
                active_count = self._prune_stale_peers_locked(camera_name)
                if active_count > 0:
                    active_by_camera[camera_name] = active_count
            return active_by_camera

    def all_peers(self) -> list[RTCPeerConnection]:
        with self.lock:
            return list(self.peer_connections)

    def clear(self) -> None:
        with self.lock:
            self.peer_connections.clear()
            self.camera_peers.clear()
            self.detached_peers.clear()
