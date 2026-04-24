from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from aiortc import MediaStreamTrack
from aiortc.contrib.media import MediaPlayer, MediaRelay


@dataclass
class AudioEntry:
    source: str
    player: MediaPlayer
    relay: MediaRelay
    created_ts: float
    last_used_ts: float


class CameraAudioService:
    def __init__(self):
        self._lock = threading.Lock()
        self._entries: dict[str, AudioEntry] = {}

    def _build_player(self, source: str, transport: str, low_latency: bool) -> MediaPlayer:
        return MediaPlayer(
            source,
            options=_build_player_options(source, transport, low_latency),
        )

    def detect_audio(
        self,
        *,
        source: str,
        transport: str,
        low_latency: bool,
    ) -> bool:
        if not source.strip():
            return False
        try:
            player = self._build_player(source, transport, low_latency)
        except Exception:
            return False
        try:
            return player.audio is not None
        finally:
            _stop_player(player)

    def get_track(
        self,
        camera_name: str,
        *,
        source: str,
        transport: str,
        low_latency: bool,
    ) -> MediaStreamTrack | None:
        if not source.strip():
            return None

        with self._lock:
            entry = self._entries.get(camera_name)
            if entry is None or entry.source != source:
                if entry is not None:
                    self._close_entry(entry)
                player = self._build_player(source, transport, low_latency)
                if player.audio is None:
                    _stop_player(player)
                    return None
                entry = AudioEntry(
                    source=source,
                    player=player,
                    relay=MediaRelay(),
                    created_ts=time.monotonic(),
                    last_used_ts=time.monotonic(),
                )
                self._entries[camera_name] = entry
            else:
                entry.last_used_ts = time.monotonic()

            if entry.player.audio is None:
                return None
            return entry.relay.subscribe(entry.player.audio)

    def close_camera(self, camera_name: str) -> None:
        with self._lock:
            entry = self._entries.pop(camera_name, None)
        if entry is not None:
            self._close_entry(entry)

    def close_all(self) -> None:
        with self._lock:
            entries = list(self._entries.values())
            self._entries.clear()
        for entry in entries:
            self._close_entry(entry)

    @staticmethod
    def _close_entry(entry: AudioEntry) -> None:
        _stop_player(entry.player)


def _build_player_options(source: str, transport: str, low_latency: bool) -> dict[str, str] | None:
    options: dict[str, str] = {}
    is_rtsp_source = source.strip().lower().startswith("rtsp://")
    if is_rtsp_source:
        if transport in {"tcp", "udp"}:
            options["rtsp_transport"] = transport
        # Pedimos solo audio para no duplicar la decodificación de video del stream.
        options["allowed_media_types"] = "audio"
    if low_latency:
        options["fflags"] = "nobuffer"
        options["flags"] = "low_delay"
    return options or None


def _stop_player(player: MediaPlayer) -> None:
    try:
        if player.audio is not None:
            player._stop(player.audio)
        if player.video is not None:
            player._stop(player.video)
    except Exception:
        pass
