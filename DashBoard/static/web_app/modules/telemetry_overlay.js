export function createTelemetryOverlayModule(deps) {
  const {
    documentObj,
    telemetryMapOverlayBox,
    telemetryMapOverlayOrganization,
    telemetryMapOverlayPreview,
    getTelemetryOverlayCameraName,
    setTelemetryOverlayCameraName,
    setTelemetryOverlaySourceKind,
    setTelemetryOverlaySelectionLabel,
    getTelemetryOverlayPlayerKey,
    setTelemetryOverlayPlayerKey,
    getTelemetryOverlayRenderToken,
    setTelemetryOverlayRenderToken,
    getLastTelemetrySnapshot,
    destroyHlsPlayer,
    getCameraByName,
    getDeviceByCamera,
    resolveCameraPlaybackTarget,
    getCameraSource,
    shouldUseAuthorizedViewerUrl,
    fetchAuthorizedViewerAccess,
    buildEmbeddedViewerUrl,
    buildManagedEmbeddedViewerDocument,
    playVideoElement,
    attachHlsPlayback,
    getSelectedTelemetryItem,
    telemetryLabel,
  } = deps;

  function incrementTelemetryOverlayRenderToken() {
    const nextToken = getTelemetryOverlayRenderToken() + 1;
    setTelemetryOverlayRenderToken(nextToken);
    return nextToken;
  }

  function resetTelemetryMapOverlaySurface() {
    const telemetryOverlayPlayerKey = getTelemetryOverlayPlayerKey();
    if (telemetryOverlayPlayerKey) {
      destroyHlsPlayer(telemetryOverlayPlayerKey);
      setTelemetryOverlayPlayerKey(null);
    }
    if (!telemetryMapOverlayPreview) return;

    const video = telemetryMapOverlayPreview.querySelector("video");
    if (video) {
      try { video.pause(); } catch (error) {}
      try {
        video.removeAttribute("src");
        video.load();
      } catch (error) {}
    }

    const frame = telemetryMapOverlayPreview.querySelector("iframe");
    if (frame) {
      try {
        frame.srcdoc = "";
        if (frame.src && frame.src !== "about:blank") {
          frame.src = "about:blank";
        }
      } catch (error) {}
    }

    telemetryMapOverlayPreview.innerHTML = "";
  }

  function getOverlayOrganizationName(cameraName) {
    const camera = getCameraByName(cameraName);
    if (camera && typeof camera.organization_name === "string" && camera.organization_name.trim()) {
      return camera.organization_name.trim();
    }

    const device = getDeviceByCamera(cameraName);
    if (device) {
      const rawName = String(
        device.organization_name
        || device.organizacion_nombre
        || "",
      ).trim();
      if (rawName) {
        return rawName;
      }
    }

    return "";
  }

  function updateTelemetryMapOverlayCopy() {
    if (!telemetryMapOverlayOrganization) return;
    const telemetryOverlayCameraName = getTelemetryOverlayCameraName();
    if (!telemetryOverlayCameraName) {
      telemetryMapOverlayOrganization.textContent = "";
      telemetryMapOverlayOrganization.hidden = true;
      return;
    }
    const organizationName = getOverlayOrganizationName(telemetryOverlayCameraName);
    telemetryMapOverlayOrganization.textContent = organizationName;
    telemetryMapOverlayOrganization.hidden = !organizationName;
  }

  function hideTelemetryMapOverlay() {
    incrementTelemetryOverlayRenderToken();
    setTelemetryOverlayCameraName(null);
    setTelemetryOverlaySourceKind("");
    setTelemetryOverlaySelectionLabel("");
    resetTelemetryMapOverlaySurface();
    updateTelemetryMapOverlayCopy();
    if (!telemetryMapOverlayBox) return;
    telemetryMapOverlayBox.hidden = true;
    telemetryMapOverlayBox.setAttribute("aria-hidden", "true");
  }

  async function renderTelemetryMapOverlayPreview() {
    const telemetryOverlayCameraName = getTelemetryOverlayCameraName();
    if (!telemetryMapOverlayBox || !telemetryMapOverlayPreview || !telemetryOverlayCameraName) {
      hideTelemetryMapOverlay();
      return;
    }

    const cameraName = telemetryOverlayCameraName;
    const playbackTarget = resolveCameraPlaybackTarget(cameraName);
    const sourceUrl = getCameraSource(cameraName);
    const renderToken = incrementTelemetryOverlayRenderToken();

    resetTelemetryMapOverlaySurface();
    updateTelemetryMapOverlayCopy();
    telemetryMapOverlayBox.hidden = false;
    telemetryMapOverlayBox.setAttribute("aria-hidden", "false");

    if (!sourceUrl || playbackTarget.mode === "none") {
      telemetryMapOverlayPreview.innerHTML = '<div class="empty-state">La camara seleccionada no tiene una fuente de video disponible.</div>';
      return;
    }

    if (playbackTarget.mode === "unsupported") {
      telemetryMapOverlayPreview.innerHTML = '<div class="empty-state">La fuente actual de esta camara no se puede abrir en la vista previa del mapa.</div>';
      return;
    }

    if (playbackTarget.mode === "iframe") {
      const frame = documentObj.createElement("iframe");
      frame.className = "telemetry-map-overlay-frame";
      frame.loading = "eager";
      frame.allow = "autoplay; fullscreen; picture-in-picture";
      frame.referrerPolicy = "strict-origin-when-cross-origin";
      frame.setAttribute("allowfullscreen", "");
      frame.setAttribute("title", `Vista previa ${cameraName}`);
      telemetryMapOverlayPreview.appendChild(frame);
      try {
        if (shouldUseAuthorizedViewerUrl(cameraName, sourceUrl)) {
          const camera = getCameraByName(cameraName);
          const viewerAccess = await fetchAuthorizedViewerAccess(camera, {
            muted: true,
            controls: true,
          });
          if (renderToken !== getTelemetryOverlayRenderToken() || getTelemetryOverlayCameraName() !== cameraName) {
            return;
          }
          const managedDocument = buildManagedEmbeddedViewerDocument(viewerAccess.viewerUrl);
          if (managedDocument) {
            frame.srcdoc = managedDocument;
          } else if (viewerAccess.viewerHtml) {
            frame.srcdoc = viewerAccess.viewerHtml;
          } else {
            frame.src = buildEmbeddedViewerUrl(viewerAccess.viewerUrl, { muted: true });
          }
        } else {
          frame.src = buildEmbeddedViewerUrl(sourceUrl, { muted: true });
        }
      } catch (error) {
        if (renderToken !== getTelemetryOverlayRenderToken()) {
          return;
        }
        resetTelemetryMapOverlaySurface();
        telemetryMapOverlayPreview.innerHTML = '<div class="empty-state">No se pudo abrir la camara seleccionada en la vista previa del mapa.</div>';
      }
      return;
    }

    const video = documentObj.createElement("video");
    video.className = "telemetry-map-overlay-video";
    video.autoplay = true;
    video.playsInline = true;
    video.muted = true;
    video.controls = true;
    video.disablePictureInPicture = true;
    telemetryMapOverlayPreview.appendChild(video);

    try {
      if (playbackTarget.mode === "video") {
        video.src = playbackTarget.url;
        await playVideoElement(video);
      } else if (playbackTarget.mode === "hls") {
        const playerKey = `telemetry-overlay:${cameraName}`;
        setTelemetryOverlayPlayerKey(playerKey);
        await attachHlsPlayback(playerKey, video, playbackTarget.url);
        video.muted = true;
        video.volume = 0;
      }

      if (renderToken !== getTelemetryOverlayRenderToken() || getTelemetryOverlayCameraName() !== cameraName) {
        resetTelemetryMapOverlaySurface();
      }
    } catch (error) {
      if (renderToken !== getTelemetryOverlayRenderToken()) {
        return;
      }
      resetTelemetryMapOverlaySurface();
      telemetryMapOverlayPreview.innerHTML = '<div class="empty-state">No se pudo abrir la camara seleccionada en la vista previa del mapa.</div>';
    }
  }

  function showTelemetryMapOverlay(cameraName, { sourceKind = "camera", selectionLabel = "" } = {}) {
    if (!telemetryMapOverlayBox || !cameraName || !getCameraByName(cameraName)) {
      hideTelemetryMapOverlay();
      return false;
    }
    const sameCamera = getTelemetryOverlayCameraName() === cameraName;
    const overlayVisible = !telemetryMapOverlayBox.hidden
      && telemetryMapOverlayBox.getAttribute("aria-hidden") !== "true";
    setTelemetryOverlayCameraName(cameraName);
    setTelemetryOverlaySourceKind(sourceKind);
    setTelemetryOverlaySelectionLabel(selectionLabel);
    updateTelemetryMapOverlayCopy();
    if (sameCamera && overlayVisible) {
      return true;
    }
    void renderTelemetryMapOverlayPreview();
    return true;
  }

  function syncTelemetryMapOverlayFromTelemetrySelection(items = getLastTelemetrySnapshot()) {
    if (!telemetryMapOverlayBox) return false;
    const selectedItem = getSelectedTelemetryItem(items);
    const cameraName = selectedItem ? String(selectedItem.camera_name || "").trim() : "";
    if (!cameraName) {
      hideTelemetryMapOverlay();
      return false;
    }
    return showTelemetryMapOverlay(cameraName, {
      sourceKind: "telemetry",
      selectionLabel: selectedItem ? telemetryLabel(selectedItem) : "",
    });
  }

  return {
    resetTelemetryMapOverlaySurface,
    getOverlayOrganizationName,
    updateTelemetryMapOverlayCopy,
    hideTelemetryMapOverlay,
    renderTelemetryMapOverlayPreview,
    showTelemetryMapOverlay,
    syncTelemetryMapOverlayFromTelemetrySelection,
  };
}
