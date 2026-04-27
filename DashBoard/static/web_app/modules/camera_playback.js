export function createCameraPlaybackModule(deps) {
  const {
    windowObj,
    documentObj,
    cameras,
    deviceByCamera,
    embeddedViewerSessions,
    hlsPlayers,
    reconnectDelayMs,
    connectionTokens,
    audioVolume,
    getAudioState,
    fetchJson,
    createCameraConnectionError,
    setState,
    scheduleReconnect,
    applyAudioState,
  } = deps;

  function getCameraByName(name) {
    return cameras.find((camera) => camera.name === name) || null;
  }

  function getDeviceByCamera(name) {
    return deviceByCamera.get(name) || null;
  }

  function getCardByCamera(camera) {
    return documentObj.getElementById(`card-${camera.dom_id}`);
  }

  function getCardCloseButton(cameraName) {
    const camera = getCameraByName(cameraName);
    return camera ? documentObj.getElementById(`card-close-${camera.dom_id}`) : null;
  }

  function getVideoByCamera(name) {
    const camera = getCameraByName(name);
    return camera ? documentObj.getElementById(`video-${camera.dom_id}`) : null;
  }

  function getCameraSource(cameraName) {
    const device = getDeviceByCamera(cameraName);
    return device && typeof device.source === "string" ? device.source.trim() : "";
  }

  function isHttpCameraSource(url) {
    const normalized = String(url || "").trim().toLowerCase();
    return normalized.startsWith("http://") || normalized.startsWith("https://");
  }

  function isLikelyHlsSource(url) {
    return /\.m3u8(?:[?#].*)?$/i.test(String(url || "").trim());
  }

  function isLikelyDirectVideoSource(url) {
    return /\.(?:mp4|webm|ogg|ogv|mov|m4v)(?:[?#].*)?$/i.test(String(url || "").trim());
  }

  function resolveCameraPlaybackTarget(cameraName) {
    const source = getCameraSource(cameraName);
    if (!source) {
      return { mode: "none", url: "" };
    }
    if (!isHttpCameraSource(source)) {
      return { mode: "unsupported", url: source };
    }
    if (isLikelyHlsSource(source)) {
      return { mode: "hls", url: source };
    }
    if (isLikelyDirectVideoSource(source)) {
      return { mode: "video", url: source };
    }
    return { mode: "iframe", url: source };
  }

  function supportsEmbeddedBrowserViewer(cameraName) {
    return resolveCameraPlaybackTarget(cameraName).mode === "iframe";
  }

  function supportsManagedAudioPlayback(cameraName) {
    const mode = resolveCameraPlaybackTarget(cameraName).mode;
    return mode === "video" || mode === "hls";
  }

  function getWebFrameByCamera(name) {
    const camera = getCameraByName(name);
    return camera ? documentObj.getElementById(`web-${camera.dom_id}`) : null;
  }

  function ensureWebFrame(cameraName) {
    const camera = getCameraByName(cameraName);
    if (!camera) return null;

    const card = getCardByCamera(camera);
    if (!card) return null;

    let frame = getWebFrameByCamera(cameraName);
    if (frame) return frame;

    frame = documentObj.createElement("iframe");
    frame.className = "camera-web-frame";
    frame.id = `web-${camera.dom_id}`;
    frame.hidden = true;
    frame.loading = "eager";
    frame.allow = "autoplay; fullscreen; picture-in-picture";
    frame.referrerPolicy = "strict-origin-when-cross-origin";
    frame.setAttribute("allowfullscreen", "");
    frame.setAttribute("title", `Visor web ${camera.name}`);
    card.insertBefore(frame, card.firstChild);
    return frame;
  }

  function buildEmbeddedViewerUrl(rawUrl, { muted } = {}) {
    try {
      const target = new URL(rawUrl, windowObj.location.href);
      if (!target.searchParams.has("controls")) {
        target.searchParams.set("controls", "1");
      }
      if (typeof muted === "boolean") {
        target.searchParams.set("muted", muted ? "1" : "0");
      } else if (!target.searchParams.has("muted")) {
        target.searchParams.set("muted", "1");
      }
      if (!target.searchParams.has("autoplay")) {
        target.searchParams.set("autoplay", "1");
      }
      if (!target.searchParams.has("playsinline")) {
        target.searchParams.set("playsinline", "1");
      }
      return target.toString();
    } catch (error) {
      return rawUrl;
    }
  }

  function normalizeManagedEmbeddedViewerBase(rawUrl) {
    const target = new URL(rawUrl, windowObj.location.href);
    const pathname = String(target.pathname || "");
    const lastSegment = pathname.split("/").filter(Boolean).pop() || "";
    if (pathname && !pathname.endsWith("/") && !/\.[a-z0-9]+$/i.test(lastSegment)) {
      target.pathname = `${pathname}/`;
    }
    return target;
  }

  function isLikelyManagedEmbeddedViewerSource(rawUrl) {
    try {
      const target = new URL(rawUrl, windowObj.location.href);
      const pathname = String(target.pathname || "").toLowerCase();
      const hasPathExtension = /\/[^/?#]+\.[a-z0-9]+$/i.test(pathname);
      return (
        (target.protocol === "http:" || target.protocol === "https:")
        && !hasPathExtension
        && target.port === "8989"
      );
    } catch (error) {
      return false;
    }
  }

  function supportsEmbeddedViewerVolumeSync(cameraName) {
    return isLikelyManagedEmbeddedViewerSource(getCameraSource(cameraName));
  }

  function shouldUseAuthorizedViewerUrl(cameraName, viewerUrl = "") {
    const device = getDeviceByCamera(cameraName);
    const candidate = viewerUrl
      || (device && typeof device.viewer_url === "string" ? device.viewer_url.trim() : "")
      || getCameraSource(cameraName);
    return isLikelyManagedEmbeddedViewerSource(candidate);
  }

  function buildAuthorizedManagedViewerSource(cameraName, authorizedViewerUrl) {
    try {
      const source = getCameraSource(cameraName);
      if (!isLikelyManagedEmbeddedViewerSource(source)) return "";

      const authorized = new URL(authorizedViewerUrl, windowObj.location.href);
      const token = authorized.searchParams.get("token");
      if (!token) return "";

      const target = new URL(source, windowObj.location.href);
      target.searchParams.set("token", token);
      return target.toString();
    } catch (error) {
      return "";
    }
  }

  async function fetchAuthorizedViewerAccess(camera, options = {}) {
    const cameraName = camera && typeof camera.name === "string" ? camera.name.trim() : "";
    const device = cameraName ? getDeviceByCamera(cameraName) : null;
    const cameraId = Number(
      (device && device.camera_id != null ? device.camera_id : null)
      ?? (camera && camera.camera_id != null ? camera.camera_id : null)
      ?? 0,
    );
    const audioState = getAudioState();
    const muted = Object.prototype.hasOwnProperty.call(options, "muted")
      ? Boolean(options.muted)
      : !audioState.enabled;
    const controls = Object.prototype.hasOwnProperty.call(options, "controls")
      ? Boolean(options.controls)
      : true;
    if (!cameraName && (!Number.isInteger(cameraId) || cameraId <= 0)) {
      throw createCameraConnectionError("authorized_viewer_unavailable", "camera_identifier_missing");
    }

    try {
      const query = Number.isInteger(cameraId) && cameraId > 0
        ? `camera_id=${encodeURIComponent(String(cameraId))}`
        : `camera_name=${encodeURIComponent(cameraName)}`;
      const payload = await fetchJson(
        `/api/camera-viewer-url?${query}&muted=${muted ? "1" : "0"}&controls=${controls ? "1" : "0"}`,
        {
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
          },
          timeoutMs: 10000,
        },
      );
      const viewerUrl = typeof payload.viewer_url === "string" ? payload.viewer_url.trim() : "";
      const viewerHtml = typeof payload.viewer_html === "string" ? payload.viewer_html : "";
      if (!viewerUrl) {
        throw new Error("authorized_viewer_missing");
      }
      return {
        viewerUrl: buildAuthorizedManagedViewerSource(cameraName, viewerUrl) || viewerUrl,
        viewerHtml,
        authorizedViewerUrl: viewerUrl,
      };
    } catch (error) {
      throw createCameraConnectionError(
        "authorized_viewer_unavailable",
        error instanceof Error ? error.message : "authorized_viewer_unavailable",
      );
    }
  }

  function buildManagedEmbeddedViewerDocument(rawUrl) {
    try {
      const target = new URL(rawUrl, windowObj.location.href);
      const viewerBase = normalizeManagedEmbeddedViewerBase(rawUrl);
      const readerUrl = new URL("reader.js", viewerBase);
      const whepUrl = new URL("whep", viewerBase);
      whepUrl.search = target.search;
      const audioState = getAudioState();
      const initialVolume = Math.max(0, Math.min(1, Number(audioVolume ? audioVolume.value : 75) / 100));
      const initialMuted = !audioState.enabled;

      return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
html, body {
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: rgb(30, 30, 30);
}
body {
  font-family: Arial, sans-serif;
}
#video {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  background: rgb(30, 30, 30);
}
#message {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  box-sizing: border-box;
  text-align: center;
  font-size: 16px;
  font-weight: bold;
  color: white;
  text-shadow: 0 0 5px black;
  pointer-events: none;
}
</style>
<script src=${JSON.stringify(readerUrl.toString())}></script>
</head>
<body>
<video id="video"></video>
<div id="message"></div>
<script>
const video = document.getElementById("video");
const message = document.getElementById("message");
const whepUrl = ${JSON.stringify(whepUrl.toString())};
let currentMuted = ${initialMuted ? "true" : "false"};
let currentVolume = ${String(initialVolume)};
let reader = null;

const clampVolume = (value) => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return currentVolume;
  return Math.max(0, Math.min(1, numeric));
};

const friendlyViewerMessage = (value) => {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const normalized = raw.toLowerCase();
  if (normalized.includes("stream not found") || normalized.includes("path not found")) {
    return "La señal de esta cámara no está disponible en este momento.";
  }
  if (normalized.includes("unauthorized") || normalized.includes("forbidden")) {
    return "No se pudo autorizar el acceso al video de esta cámara.";
  }
  if (normalized.includes("timeout") || normalized.includes("network")) {
    return "No se pudo conectar con la señal de video. Reintentando...";
  }
  return "La señal de video no está disponible. Reintentando...";
};

const setMessage = (value) => {
  const nextMessage = friendlyViewerMessage(value);
  message.textContent = nextMessage;
  video.controls = !nextMessage;
};

const applyAudioState = () => {
  video.muted = currentMuted;
  video.volume = currentVolume;
};

window.setViewerAudio = (payload = {}) => {
  if (Object.prototype.hasOwnProperty.call(payload, "muted")) {
    currentMuted = Boolean(payload.muted);
  }
  if (Object.prototype.hasOwnProperty.call(payload, "volume")) {
    currentVolume = clampVolume(payload.volume);
  }
  applyAudioState();
};

window.addEventListener("load", () => {
  video.autoplay = true;
  video.controls = true;
  video.playsInline = true;
  applyAudioState();

  if (typeof MediaMTXWebRTCReader !== "function") {
    setMessage("No se pudo cargar el visor WebRTC.");
    return;
  }

  reader = new MediaMTXWebRTCReader({
    url: whepUrl,
    onError: (err) => {
      setMessage(err);
    },
    onTrack: (evt) => {
      setMessage("");
      video.srcObject = evt.streams[0];
      applyAudioState();
    },
    onDataChannel: (evt) => {
      evt.channel.binaryType = "arraybuffer";
    },
  });
});

window.addEventListener("beforeunload", () => {
  if (reader !== null) {
    reader.close();
  }
});
</script>
</body>
</html>`;
    } catch (error) {
      return "";
    }
  }

  function setCameraSurfaceMode(cameraName, mode = "video") {
    const camera = getCameraByName(cameraName);
    if (!camera) return;

    const card = getCardByCamera(camera);
    const video = getVideoByCamera(cameraName);
    const frame = getWebFrameByCamera(cameraName);
    const usesWebViewer = mode === "web";

    if (card) {
      card.classList.toggle("is-web-viewer", usesWebViewer);
    }
    if (video) {
      video.hidden = usesWebViewer;
    }
    if (frame) {
      frame.hidden = !usesWebViewer;
    }
  }

  function closeEmbeddedViewer(name) {
    embeddedViewerSessions.delete(name);
    const frame = getWebFrameByCamera(name);
    if (frame) {
      frame.onload = null;
      frame.onerror = null;
      frame.dataset.viewerMode = "";
      frame.dataset.viewerUrl = "";
      frame.srcdoc = "";
      if (frame.src && frame.src !== "about:blank") {
        frame.src = "about:blank";
      }
      frame.hidden = true;
    }
    setCameraSurfaceMode(name, "video");
  }

  function syncEmbeddedViewerAudio(cameraName) {
    if (!cameraName || !supportsEmbeddedBrowserViewer(cameraName)) return;

    const frame = getWebFrameByCamera(cameraName);
    if (!frame || !embeddedViewerSessions.has(cameraName)) return;

    const source = getCameraSource(cameraName);
    if (!source) return;

    const targetVolume = Math.max(0, Math.min(1, Number(audioVolume ? audioVolume.value : 75) / 100));
    const audioState = getAudioState();
    if (frame.dataset.viewerMode === "remote") {
      return;
    }
    if (frame.dataset.viewerMode === "managed") {
      try {
        if (frame.contentWindow && typeof frame.contentWindow.setViewerAudio === "function") {
          frame.contentWindow.setViewerAudio({
            muted: !audioState.enabled,
            volume: targetVolume,
          });
          return;
        }
      } catch (error) {}
      return;
    }

    const nextSrc = buildEmbeddedViewerUrl(source, { muted: !audioState.enabled });
    if (frame.src !== nextSrc) {
      frame.src = nextSrc;
    }
  }

  function destroyHlsPlayer(name) {
    const player = hlsPlayers.get(name);
    if (!player) return;
    hlsPlayers.delete(name);
    try {
      player.destroy();
    } catch (error) {}
  }

  function getCardAudioToggle(cameraName) {
    const camera = getCameraByName(cameraName);
    return camera ? documentObj.getElementById(`card-audio-${camera.dom_id}`) : null;
  }

  function startEmbeddedViewer(camera, token, viewerUrlOverride = "", managedDocumentOverride = "") {
    const { name, dom_id: domId } = camera;
    const viewerUrl = viewerUrlOverride || getCameraSource(name);
    if (!viewerUrl) {
      throw createCameraConnectionError("camera_source_not_supported", "source_missing");
    }

    const frame = ensureWebFrame(name);
    if (!frame) {
      throw createCameraConnectionError("camera_connection_failed", "viewer_iframe_missing");
    }

    const audioState = getAudioState();
    const useManagedViewer = isLikelyManagedEmbeddedViewerSource(viewerUrl);
    const nextSrc = buildEmbeddedViewerUrl(viewerUrl, { muted: !audioState.enabled });
    const managedDocument = managedDocumentOverride || (useManagedViewer ? buildManagedEmbeddedViewerDocument(viewerUrl) : "");
    embeddedViewerSessions.add(name);
    frame.onload = () => {
      if (connectionTokens.get(name) !== token || !embeddedViewerSessions.has(name)) return;
      setState(domId, "En vivo web");
      reconnectDelayMs.set(name, 800);
      syncEmbeddedViewerAudio(name);
    };
    frame.onerror = () => {
      if (connectionTokens.get(name) !== token) return;
      embeddedViewerSessions.delete(name);
      setCameraSurfaceMode(name, "video");
      scheduleReconnect(camera, "Reconectando visor...");
    };
    setCameraSurfaceMode(name, "web");
    if (useManagedViewer && managedDocument) {
      frame.dataset.viewerMode = "managed";
      frame.dataset.viewerUrl = viewerUrl;
      if (frame.srcdoc !== managedDocument) {
        frame.srcdoc = managedDocument;
      } else {
        setState(domId, "En vivo web");
        syncEmbeddedViewerAudio(name);
      }
    } else if (frame.src !== nextSrc || frame.dataset.viewerMode === "managed") {
      frame.dataset.viewerMode = "remote";
      frame.dataset.viewerUrl = viewerUrl;
      frame.srcdoc = "";
      frame.src = nextSrc;
    } else {
      setState(domId, "En vivo web");
      syncEmbeddedViewerAudio(name);
    }
    setState(domId, "Abriendo visor...");
    reconnectDelayMs.set(name, 800);
    applyAudioState();
  }

  async function playVideoElement(video) {
    if (!video) return;
    const playPromise = video.play();
    if (playPromise && typeof playPromise.then === "function") {
      try {
        await playPromise;
      } catch (error) {}
    }
  }

  async function attachHlsPlayback(name, video, sourceUrl) {
    if (!video) {
      throw createCameraConnectionError("camera_connection_failed", "video_element_missing");
    }

    const canPlayNative = typeof video.canPlayType === "function"
      && (
        video.canPlayType("application/vnd.apple.mpegurl")
        || video.canPlayType("application/x-mpegURL")
      );
    if (canPlayNative) {
      video.src = sourceUrl;
      await playVideoElement(video);
      return;
    }

    if (!(windowObj.Hls && typeof windowObj.Hls.isSupported === "function" && windowObj.Hls.isSupported())) {
      throw createCameraConnectionError("camera_source_not_supported", "hls_not_supported");
    }

    const player = new windowObj.Hls({
      enableWorker: true,
      lowLatencyMode: true,
      backBufferLength: 30,
    });
    hlsPlayers.set(name, player);

    await new Promise((resolve, reject) => {
      let settled = false;
      const cleanup = () => {
        player.off(windowObj.Hls.Events.MANIFEST_PARSED, handleParsed);
        player.off(windowObj.Hls.Events.ERROR, handleError);
      };
      const finish = (callback) => {
        if (settled) return;
        settled = true;
        cleanup();
        callback();
      };
      const handleParsed = () => {
        finish(() => resolve(undefined));
      };
      const handleError = (_event, data) => {
        if (!data || !data.fatal) return;
        finish(() => {
          destroyHlsPlayer(name);
          reject(createCameraConnectionError("camera_connection_failed", data.details || data.type || "hls_error"));
        });
      };

      player.on(windowObj.Hls.Events.MANIFEST_PARSED, handleParsed);
      player.on(windowObj.Hls.Events.ERROR, handleError);
      player.loadSource(sourceUrl);
      player.attachMedia(video);
    });

    await playVideoElement(video);
  }

  return {
    getCameraByName,
    getDeviceByCamera,
    getCardByCamera,
    getCardCloseButton,
    getVideoByCamera,
    getCameraSource,
    isHttpCameraSource,
    isLikelyHlsSource,
    isLikelyDirectVideoSource,
    resolveCameraPlaybackTarget,
    supportsEmbeddedBrowserViewer,
    supportsManagedAudioPlayback,
    getWebFrameByCamera,
    ensureWebFrame,
    buildEmbeddedViewerUrl,
    normalizeManagedEmbeddedViewerBase,
    isLikelyManagedEmbeddedViewerSource,
    supportsEmbeddedViewerVolumeSync,
    shouldUseAuthorizedViewerUrl,
    fetchAuthorizedViewerAccess,
    buildManagedEmbeddedViewerDocument,
    setCameraSurfaceMode,
    closeEmbeddedViewer,
    syncEmbeddedViewerAudio,
    destroyHlsPlayer,
    getCardAudioToggle,
    startEmbeddedViewer,
    playVideoElement,
    attachHlsPlayback,
  };
}
