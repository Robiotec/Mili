from __future__ import annotations

import os
import re
import sys
import html
import json
import time
import argparse
import webbrowser
import requests
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile, gettempdir
from urllib.parse import urljoin, urlparse, urlunparse

from surveillance import settings


BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_API_HOST = settings.STREAM_API_HOST
DEFAULT_API_PORT = settings.STREAM_API_PORT
DEFAULT_API_BASE_URL = settings.STREAM_API_BASE_URL
DEFAULT_API_USERNAME = settings.STREAM_API_USERNAME
DEFAULT_API_PASSWORD = settings.STREAM_API_PASSWORD
DEFAULT_REQUEST_TIMEOUT = settings.STREAM_REQUEST_TIMEOUT
DEFAULT_AUTOPLAY_MUTED = settings.STREAM_VIEWER_MUTED

LOCAL_VIEWER_PREFIX = "authorized_stream_viewer_"
LOCAL_VIEWER_SUFFIX = ".html"
STALE_VIEWER_MAX_AGE_SECONDS = settings.VIEWER_CACHE_MAX_AGE_SECONDS
VIEWER_MARKERS = (
    "MediaMTXWebRTCReader",
    "reader.js",
    "new URL('whep'",
    'new URL("whep"',
)


class StreamViewerError(RuntimeError):
    """Raised when the authenticated stream viewer cannot be prepared."""


@dataclass(frozen=True)
class ViewerCredentials:
    username: str
    password: str


@dataclass(frozen=True)
class ViewerLaunchOptions:
    autoplay: bool = True
    muted: bool = DEFAULT_AUTOPLAY_MUTED
    controls: bool = False


@dataclass(frozen=True)
class ManagedViewerUrls:
    viewer_url: str
    reader_url: str
    whep_url: str


def sanitize_stream_name(stream_name: str) -> str:
    normalized = str(stream_name or "").strip()
    if not normalized:
        raise StreamViewerError("Debes indicar un nombre de stream, por ejemplo CAM1 o CAM2.")
    return normalized


def sanitize_file_component(value: str) -> str:
    return "".join(
        char if char.isalnum() or char in ("-", "_") else "_"
        for char in str(value or "").strip()
    ) or "stream"


def normalize_api_base_url(raw_url: str) -> str:
    normalized = str(raw_url or "").strip().rstrip("/")
    if not normalized:
        raise StreamViewerError("Debes configurar STREAM_API_BASE_URL o indicar --api-base-url.")

    # Soporta valores como LOCALHOST:8004 sin esquema.
    if "://" not in normalized:
        normalized = f"http://{normalized}"

    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise StreamViewerError(f"URL base de API invalida: {normalized}")
    return normalized


def resolve_viewer_url(viewer_url: str, api_base_url: str) -> str:
    candidate = str(viewer_url or "").strip()
    if not candidate:
        raise StreamViewerError("La API no devolvio stream_url para este stream.")
    return urljoin(f"{api_base_url}/", candidate)


def normalize_managed_viewer_base(viewer_url: str) -> str:
    parsed = urlparse(viewer_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise StreamViewerError(f"Viewer URL invalida: {viewer_url}")

    pathname = parsed.path or "/"
    trimmed_path = pathname.rstrip("/")
    last_segment = trimmed_path.split("/")[-1] if trimmed_path else ""
    has_extension = "." in last_segment if last_segment else False
    if pathname and not pathname.endswith("/") and not has_extension:
        pathname = f"{pathname}/"

    return urlunparse(parsed._replace(path=pathname, params="", query="", fragment=""))


def build_managed_viewer_urls(viewer_url: str) -> ManagedViewerUrls:
    target = urlparse(viewer_url)
    if target.scheme not in {"http", "https"} or not target.netloc:
        raise StreamViewerError(f"Viewer URL invalida: {viewer_url}")

    viewer_base = normalize_managed_viewer_base(viewer_url)
    reader_url = urljoin(viewer_base, "reader.js")
    whep_base = urlparse(urljoin(viewer_base, "whep"))
    whep_url = urlunparse(whep_base._replace(query=target.query, fragment=""))
    return ManagedViewerUrls(
        viewer_url=viewer_url,
        reader_url=reader_url,
        whep_url=whep_url,
    )


def is_access_denied_html(payload: str) -> bool:
    normalized = str(payload or "").lower()
    return "acceso denegado" in normalized or "access denied" in normalized


def looks_like_managed_viewer_html(payload: str) -> bool:
    normalized = str(payload or "")
    return any(marker in normalized for marker in VIEWER_MARKERS)


def cleanup_stale_local_viewers(
    *,
    prefix: str = LOCAL_VIEWER_PREFIX,
    suffix: str = LOCAL_VIEWER_SUFFIX,
    max_age_seconds: int = STALE_VIEWER_MAX_AGE_SECONDS,
) -> None:
    temp_dir = Path(gettempdir())
    cutoff = time.time() - max_age_seconds
    pattern = f"{prefix}*{suffix}"

    for candidate in temp_dir.glob(pattern):
        try:
            if candidate.stat().st_mtime < cutoff:
                candidate.unlink()
        except OSError:
            continue


def build_local_viewer_html(
    stream_name: str,
    managed_urls: ManagedViewerUrls,
    *,
    options: ViewerLaunchOptions,
) -> str:
    safe_title = html.escape(stream_name, quote=True)
    initial_muted = "true" if options.muted else "false"
    initial_controls = "true" if options.controls else "false"
    initial_autoplay = "true" if options.autoplay else "false"
    initial_volume = "0" if options.muted else "1"

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: #111;
      color: #fff;
      font-family: Arial, sans-serif;
    }}

    body {{
      position: relative;
    }}

    #video {{
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      background: #111;
      object-fit: contain;
    }}

    #overlay {{
      position: absolute;
      inset: auto 16px 16px 16px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
      flex-wrap: wrap;
      z-index: 1;
      pointer-events: none;
    }}

    #message {{
      min-height: 20px;
      max-width: 720px;
      padding: 10px 14px;
      border-radius: 12px;
      background: rgba(0, 0, 0, 0.76);
      border: 1px solid rgba(255, 255, 255, 0.12);
      text-align: center;
      pointer-events: auto;
    }}

    .action {{
      appearance: none;
      border: 0;
      border-radius: 999px;
      padding: 10px 16px;
      background: rgba(255, 255, 255, 0.92);
      color: #111;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      pointer-events: auto;
    }}

    .action[hidden],
    #message[data-empty="true"] {{
      display: none;
    }}
  </style>
  <script src={json.dumps(managed_urls.reader_url)}></script>
</head>
<body>
  <video id="video"></video>
  <div id="overlay">
    <div id="message" role="status" aria-live="polite" data-empty="true"></div>
    <button id="retry" class="action" type="button" hidden>Iniciar video</button>
    <button id="toggle-audio" class="action" type="button" hidden>Activar audio</button>
  </div>
  <script>
    const video = document.getElementById("video");
    const message = document.getElementById("message");
    const retryButton = document.getElementById("retry");
    const toggleAudioButton = document.getElementById("toggle-audio");
    const whepUrl = {json.dumps(managed_urls.whep_url)};
    const autoplayEnabled = {initial_autoplay};
    let currentMuted = {initial_muted};
    let currentVolume = {initial_volume};
    let reader = null;

    function setMessage(value) {{
      const nextValue = value || "";
      message.textContent = nextValue;
      message.dataset.empty = nextValue ? "false" : "true";
    }}

    function applyPlaybackState() {{
      video.autoplay = autoplayEnabled;
      video.controls = {initial_controls};
      video.playsInline = true;
      video.defaultMuted = currentMuted;
      video.muted = currentMuted;
      video.volume = currentMuted ? 0 : currentVolume;
      toggleAudioButton.hidden = !currentMuted;
    }}

    async function requestPlayback() {{
      if (!autoplayEnabled) {{
        return;
      }}

      try {{
        const maybePromise = video.play();
        if (maybePromise && typeof maybePromise.then === "function") {{
          await maybePromise;
        }}
        retryButton.hidden = true;
        if (!video.srcObject) {{
          setMessage("Esperando video...");
        }} else {{
          setMessage("");
        }}
      }} catch (error) {{
        retryButton.hidden = false;
        setMessage(currentMuted ? "Haz clic en 'Iniciar video'." : "Autoplay bloqueado. Inicia el video o activa audio manualmente.");
      }}
    }}

    retryButton.addEventListener("click", () => {{
      applyPlaybackState();
      void requestPlayback();
    }});

    toggleAudioButton.addEventListener("click", () => {{
      currentMuted = false;
      currentVolume = 1;
      applyPlaybackState();
      void requestPlayback();
    }});

    video.addEventListener("loadedmetadata", () => {{
      void requestPlayback();
    }});

    document.addEventListener("visibilitychange", () => {{
      if (document.visibilityState === "visible") {{
        void requestPlayback();
      }}
    }});

    window.addEventListener("load", () => {{
      applyPlaybackState();
      setMessage("Conectando al stream...");

      if (typeof MediaMTXWebRTCReader !== "function") {{
        retryButton.hidden = false;
        setMessage("No se pudo cargar el visor WebRTC.");
        return;
      }}

      reader = new MediaMTXWebRTCReader({{
        url: whepUrl,
        onError: (error) => {{
          retryButton.hidden = false;
          setMessage(String(error || "No se pudo conectar al stream."));
        }},
        onTrack: (event) => {{
          video.srcObject = event.streams[0];
          applyPlaybackState();
          setMessage("");
          void requestPlayback();
        }},
        onDataChannel: (event) => {{
          event.channel.binaryType = "arraybuffer";
        }},
      }});
    }});

    window.addEventListener("beforeunload", () => {{
      if (reader !== null) {{
        reader.close();
      }}
    }});
  </script>
</body>
</html>
"""


def ensure_base_href(payload: str, base_href: str) -> str:
    escaped_base_href = html.escape(base_href, quote=True)
    base_tag = f'<base href="{escaped_base_href}">'

    if re.search(r"<base\b[^>]*href=", payload, flags=re.IGNORECASE):
        return re.sub(
            r"<base\b[^>]*href=(['\"]).*?\1[^>]*>",
            base_tag,
            payload,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
    return inject_into_head(payload, base_tag)


def inject_into_head(payload: str, snippet: str) -> str:
    match = re.search(r"<head\b[^>]*>", payload, flags=re.IGNORECASE)
    if match:
        return f"{payload[:match.end()]}\n{snippet}\n{payload[match.end():]}"
    return f"{snippet}\n{payload}"


def inject_before_body_end(payload: str, snippet: str) -> str:
    match = re.search(r"</body\s*>", payload, flags=re.IGNORECASE)
    if match:
        return f"{payload[:match.start()]}\n{snippet}\n{payload[match.start():]}"
    return f"{payload}\n{snippet}\n"


def replace_viewer_location_references(payload: str) -> str:
    patched = payload
    replacements = (
        (r"\bwindow\.location\.href\b", "window.__AUTHORIZED_VIEWER_URL__"),
        (r"\bdocument\.location\.href\b", "window.__AUTHORIZED_VIEWER_URL__"),
        (r"\blocation\.href\b", "window.__AUTHORIZED_VIEWER_URL__"),
        (r"\bwindow\.location\.search\b", "window.__AUTHORIZED_VIEWER_SEARCH__"),
        (r"\bdocument\.location\.search\b", "window.__AUTHORIZED_VIEWER_SEARCH__"),
        (r"\blocation\.search\b", "window.__AUTHORIZED_VIEWER_SEARCH__"),
    )
    for pattern, replacement in replacements:
        patched = re.sub(pattern, replacement, patched)
    return patched


def build_viewer_runtime_bootstrap(viewer_url: str) -> str:
    parsed = urlparse(viewer_url)
    viewer_search = f"?{parsed.query}" if parsed.query else ""
    viewer_base = normalize_managed_viewer_base(viewer_url)
    return f"""<script>
window.__AUTHORIZED_VIEWER_URL__ = {json.dumps(viewer_url)};
window.__AUTHORIZED_VIEWER_SEARCH__ = {json.dumps(viewer_search)};
window.__AUTHORIZED_VIEWER_BASE__ = {json.dumps(viewer_base)};
</script>"""


def build_autoplay_patch_script(options: ViewerLaunchOptions) -> str:
    autoplay_enabled = "true" if options.autoplay else "false"
    controls_enabled = "true" if options.controls else "false"
    muted_enabled = "true" if options.muted else "false"

    return f"""<script>
(() => {{
  const autoplayEnabled = {autoplay_enabled};
  const controlsEnabled = {controls_enabled};
  let currentMuted = {muted_enabled};
  let currentVolume = currentMuted ? 0 : 1;
  let currentVideo = null;

  function clampVolume(value) {{
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {{
      return currentVolume;
    }}
    return Math.max(0, Math.min(1, numeric));
  }}

  function applyDocumentState() {{
    document.title = "";
    document.documentElement.style.margin = "0";
    document.documentElement.style.width = "100%";
    document.documentElement.style.height = "100%";
    document.documentElement.style.background = "#000";
    document.documentElement.style.overflow = "hidden";

    if (!document.body) {{
      return;
    }}

    document.body.style.margin = "0";
    document.body.style.width = "100vw";
    document.body.style.height = "100vh";
    document.body.style.background = "#000";
    document.body.style.overflow = "hidden";
    document.body.style.cursor = "none";
  }}

  function ensureUi() {{
    let panel = document.getElementById("__authorized_stream_panel");
    if (panel) {{
      return {{
        panel,
        message: document.getElementById("__authorized_stream_message"),
        retry: document.getElementById("__authorized_stream_retry"),
        audio: document.getElementById("__authorized_stream_audio"),
      }};
    }}

    panel = document.createElement("div");
    panel.id = "__authorized_stream_panel";
    panel.style.position = "fixed";
    panel.style.left = "16px";
    panel.style.right = "16px";
    panel.style.bottom = "16px";
    panel.style.zIndex = "2147483647";
    panel.style.display = "none";
    panel.style.alignItems = "center";
    panel.style.justifyContent = "center";
    panel.style.gap = "12px";
    panel.style.flexWrap = "wrap";
    panel.style.pointerEvents = "none";

    const message = document.createElement("div");
    message.id = "__authorized_stream_message";
    message.style.display = "none";
    message.style.padding = "10px 14px";
    message.style.borderRadius = "12px";
    message.style.background = "rgba(0, 0, 0, 0.76)";
    message.style.border = "1px solid rgba(255, 255, 255, 0.16)";
    message.style.color = "#fff";
    message.style.fontFamily = "Arial, sans-serif";
    message.style.fontSize = "14px";
    message.style.pointerEvents = "auto";

    const retry = document.createElement("button");
    retry.id = "__authorized_stream_retry";
    retry.type = "button";
    retry.textContent = "Iniciar video";
    retry.hidden = true;
    retry.style.pointerEvents = "auto";
    retry.style.padding = "10px 16px";
    retry.style.borderRadius = "999px";
    retry.style.border = "0";
    retry.style.cursor = "pointer";
    retry.style.fontWeight = "700";

    const audio = document.createElement("button");
    audio.id = "__authorized_stream_audio";
    audio.type = "button";
    audio.textContent = "Activar audio";
    audio.hidden = !currentMuted;
    audio.style.pointerEvents = "auto";
    audio.style.padding = "10px 16px";
    audio.style.borderRadius = "999px";
    audio.style.border = "0";
    audio.style.cursor = "pointer";
    audio.style.fontWeight = "700";

    retry.addEventListener("click", () => {{
      if (!currentVideo) {{
        return;
      }}
      applyVideoState(currentVideo);
      void requestPlayback(currentVideo);
    }});

    audio.addEventListener("click", () => {{
      currentMuted = false;
      if (currentVolume <= 0) {{
        currentVolume = 1;
      }}
      if (!currentVideo) {{
        audio.hidden = true;
        return;
      }}
      applyVideoState(currentVideo);
      void requestPlayback(currentVideo);
      audio.hidden = true;
    }});

    panel.append(message, retry, audio);
    document.addEventListener("DOMContentLoaded", () => {{
      document.body.appendChild(panel);
    }}, {{ once: true }});
    if (document.body) {{
      document.body.appendChild(panel);
    }}

    return {{ panel, message, retry, audio }};
  }}

  function setMessage(value) {{
    const ui = ensureUi();
    const nextValue = value || "";
    ui.panel.style.display = nextValue ? "flex" : "none";
    ui.message.textContent = nextValue;
    ui.message.style.display = nextValue ? "block" : "none";
    ui.retry.hidden = !nextValue;
    ui.audio.hidden = !currentMuted;
  }}

  function applyVideoState(video) {{
    if (!video) {{
      return;
    }}

    applyDocumentState();

    if (document.body && video.parentElement !== document.body) {{
      document.body.appendChild(video);
    }}

    video.autoplay = autoplayEnabled;
    video.controls = controlsEnabled;
    video.playsInline = true;
    video.defaultMuted = currentMuted;
    video.muted = currentMuted;
    video.volume = currentMuted ? 0 : currentVolume;
    video.setAttribute("autoplay", "");
    video.setAttribute("playsinline", "");
    video.removeAttribute("poster");
    video.style.position = "fixed";
    video.style.inset = "0";
    video.style.width = "100vw";
    video.style.height = "100vh";
    video.style.maxWidth = "100vw";
    video.style.maxHeight = "100vh";
    video.style.objectFit = "contain";
    video.style.background = "#000";
    video.style.zIndex = "2147483646";

    if (!currentMuted && Number(video.volume || 0) <= 0) {{
      video.volume = 1;
    }}

    if (document.body) {{
      for (const child of Array.from(document.body.children)) {{
        if (
          child === video
          || child.id === "__authorized_stream_panel"
          || child.tagName === "SCRIPT"
        ) {{
          continue;
        }}
        child.style.display = "none";
      }}
    }}
  }}

  window.setViewerAudio = (payload = {{}}) => {{
    if (Object.prototype.hasOwnProperty.call(payload, "muted")) {{
      currentMuted = Boolean(payload.muted);
    }}
    if (Object.prototype.hasOwnProperty.call(payload, "volume")) {{
      currentVolume = clampVolume(payload.volume);
    }}
    if (!currentMuted && currentVolume <= 0) {{
      currentVolume = 1;
    }}
    if (!currentVideo) {{
      return;
    }}
    applyVideoState(currentVideo);
    void requestPlayback(currentVideo);
  }};

  async function requestPlayback(video) {{
    if (!video || !autoplayEnabled) {{
      return;
    }}

    try {{
      const maybePromise = video.play();
      if (maybePromise && typeof maybePromise.then === "function") {{
        await maybePromise;
      }}
      setMessage("");
      if (document.body) {{
        document.body.style.cursor = "none";
      }}
    }} catch (error) {{
      setMessage(
        currentMuted
          ? "Haz clic en 'Iniciar video'."
          : "El navegador bloqueo el audio automatico. Haz clic una vez en el video."
      );
      if (document.body) {{
        document.body.style.cursor = "default";
      }}
    }}
  }}

  function bindVideo(video) {{
    if (!video) {{
      return;
    }}

    currentVideo = video;
    if (video.dataset.authorizedViewerBound === "1") {{
      applyVideoState(video);
      return;
    }}

    video.dataset.authorizedViewerBound = "1";
    applyVideoState(video);
    video.addEventListener("click", () => {{
      if (currentMuted) {{
        currentMuted = false;
        if (currentVolume <= 0) {{
          currentVolume = 1;
        }}
        applyVideoState(video);
      }}
      void requestPlayback(video);
    }});
    video.addEventListener("loadedmetadata", () => {{
      void requestPlayback(video);
    }});
    video.addEventListener("loadeddata", () => {{
      void requestPlayback(video);
    }});
    video.addEventListener("canplay", () => {{
      void requestPlayback(video);
    }});
    video.addEventListener("playing", () => {{
      setMessage("");
      if (document.body) {{
        document.body.style.cursor = "none";
      }}
    }});
    setTimeout(() => {{
      void requestPlayback(video);
    }}, 0);
    setTimeout(() => {{
      void requestPlayback(video);
    }}, 500);
  }}

  function scanForVideo() {{
    bindVideo(document.querySelector("video"));
  }}

  document.addEventListener("DOMContentLoaded", scanForVideo);
  window.addEventListener("load", scanForVideo);
  document.addEventListener("visibilitychange", () => {{
    if (document.visibilityState === "visible" && currentVideo) {{
      void requestPlayback(currentVideo);
    }}
  }});

  const observer = new MutationObserver(() => {{
    scanForVideo();
  }});

  const root = document.documentElement || document;
  observer.observe(root, {{
    childList: true,
    subtree: true,
  }});
}})();
</script>"""


def build_patched_protected_viewer_html(
    viewer_html: str,
    viewer_url: str,
    *,
    options: ViewerLaunchOptions,
) -> str:
    viewer_base = normalize_managed_viewer_base(viewer_url)
    patched = replace_viewer_location_references(viewer_html)
    patched = ensure_base_href(patched, viewer_base)
    patched = inject_into_head(patched, build_viewer_runtime_bootstrap(viewer_url))
    patched = inject_before_body_end(patched, build_autoplay_patch_script(options))
    return patched


def write_local_viewer_file(stream_name: str, html_document: str) -> Path:
    cleanup_stale_local_viewers()
    safe_stream_name = sanitize_file_component(stream_name)

    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            prefix=LOCAL_VIEWER_PREFIX,
            suffix=f"_{safe_stream_name}{LOCAL_VIEWER_SUFFIX}",
            delete=False,
        ) as handle:
            handle.write(html_document)
            local_path = Path(handle.name)
    except OSError as exc:
        raise StreamViewerError(
            f"No se pudo guardar el viewer temporal del stream {stream_name}: {exc}"
        ) from exc

    try:
        os.chmod(local_path, 0o600)
    except OSError:
        pass

    return local_path


class ProtectedStreamViewerClient:
    def __init__(
        self,
        *,
        api_base_url: str,
        credentials: ViewerCredentials,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        self.api_base_url = normalize_api_base_url(api_base_url)
        self.credentials = credentials
        self.request_timeout = request_timeout
        self.session = requests.Session()
        self.access_token: str | None = None

    def close(self) -> None:
        self.session.close()

    def _request_json(self, method: str, url: str, **kwargs: object) -> dict:
        try:
            response = self.session.request(
                method,
                url,
                timeout=self.request_timeout,
                **kwargs,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise StreamViewerError(f"Fallo la solicitud a {url}: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise StreamViewerError(f"La API respondio con JSON invalido en {url}.") from exc

        if not isinstance(data, dict):
            raise StreamViewerError(f"La API respondio con un payload inesperado en {url}.")
        return data

    def login(self) -> str:
        if self.access_token:
            return self.access_token

        username = self.credentials.username.strip()
        password = self.credentials.password.strip()
        if not username or not password:
            raise StreamViewerError(
                "Debes indicar credenciales con --username/--password o variables STREAM_API_USERNAME/STREAM_API_PASSWORD."
            )

        data = self._request_json(
            "POST",
            f"{self.api_base_url}/auth/login",
            json={
                "username": username,
                "password": password,
            },
        )

        access_token = str(data.get("access_token") or "").strip()
        if not access_token:
            raise StreamViewerError("La API respondio, pero no devolvio access_token.")

        self.access_token = access_token
        return access_token

    def request_stream_viewer_url(self, stream_name: str) -> str:
        access_token = self.login()
        data = self._request_json(
            "POST",
            f"{self.api_base_url}/stream-auth/stream/token/{stream_name}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        raw_viewer_url = str(data.get("stream_url") or "").strip()
        return resolve_viewer_url(raw_viewer_url, self.api_base_url)

    def fetch_protected_viewer_html(self, viewer_url: str) -> str:
        try:
            response = self.session.get(viewer_url, timeout=self.request_timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise StreamViewerError(f"No se pudo descargar el viewer protegido: {exc}") from exc

        payload = response.text
        if is_access_denied_html(payload):
            raise StreamViewerError("La sesion recibio acceso denegado en lugar del viewer.")
        return payload

    def prepare_local_viewer(
        self,
        *,
        stream_name: str,
        options: ViewerLaunchOptions,
    ) -> Path:
        normalized_stream_name = sanitize_stream_name(stream_name)
        viewer_url = self.request_stream_viewer_url(normalized_stream_name)
        viewer_html = self.fetch_protected_viewer_html(viewer_url)
        if not looks_like_managed_viewer_html(viewer_html):
            print(
                "Advertencia: el HTML protegido no coincide exactamente con el viewer esperado. "
                "Se intentara abrir una copia parcheada del visor protegido."
            )

        html_document = build_patched_protected_viewer_html(
            viewer_html,
            viewer_url,
            options=options,
        )
        return write_local_viewer_file(normalized_stream_name, html_document)


def open_local_viewer(viewer_path: Path) -> bool:
    opened = webbrowser.open(viewer_path.resolve().as_uri(), new=2)
    if not opened:
        print("No se pudo abrir el navegador automaticamente.")
        print(f"Abre este archivo manualmente: {viewer_path.resolve()}")
        return False
    return True


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Abre un stream protegido en un viewer local compatible con MediaMTX.",
    )
    parser.add_argument(
        "stream_name",
        nargs="?",
        default=DEFAULT_STREAM_NAME,
        help="Nombre del stream a abrir. Usa STREAM_NAME como valor por defecto.",
    )
    parser.add_argument(
        "--api-base-url",
        default=DEFAULT_API_BASE_URL,
        help="Base URL de la API de autenticacion del stream.",
    )
    parser.add_argument(
        "--username",
        default=DEFAULT_API_USERNAME,
        help="Usuario para /auth/login. Usa STREAM_API_USERNAME por defecto.",
    )
    parser.add_argument(
        "--password",
        default=DEFAULT_API_PASSWORD,
        help="Password para /auth/login. Usa STREAM_API_PASSWORD por defecto.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_REQUEST_TIMEOUT,
        help="Timeout en segundos para llamadas HTTP.",
    )
    parser.add_argument(
        "--unmuted",
        action="store_true",
        help="Compatibilidad: fuerza audio activo al iniciar.",
    )
    parser.add_argument(
        "--muted",
        action="store_true",
        help="Inicia el visor en silencio para maximizar compatibilidad con autoplay.",
    )
    parser.add_argument(
        "--no-controls",
        action="store_true",
        help="Compatibilidad: oculta los controles nativos del elemento video.",
    )
    parser.add_argument(
        "--controls",
        action="store_true",
        help="Muestra los controles nativos del video.",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Solo imprime la ruta del HTML local generado y no intenta abrir el navegador.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    muted = DEFAULT_AUTOPLAY_MUTED
    if args.unmuted:
        muted = False
    if args.muted:
        muted = True

    controls = False
    if args.controls:
        controls = True
    if args.no_controls:
        controls = False

    options = ViewerLaunchOptions(
        autoplay=True,
        muted=muted,
        controls=controls,
    )
    client = ProtectedStreamViewerClient(
        api_base_url=args.api_base_url,
        credentials=ViewerCredentials(
            username=str(args.username or "").strip(),
            password=str(args.password or "").strip(),
        ),
        request_timeout=args.timeout,
    )

    try:
        local_viewer = client.prepare_local_viewer(
            stream_name=str(args.stream_name or "").strip(),
            options=options,
        )
    except StreamViewerError as exc:
        print(exc)
        return 1
    finally:
        client.close()

    print(f"Viewer local generado para {sanitize_stream_name(args.stream_name)}")
    print(f"Archivo temporal: {local_viewer.resolve()}")
    if args.print_only:
        return 0
    return 0 if open_local_viewer(local_viewer) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
