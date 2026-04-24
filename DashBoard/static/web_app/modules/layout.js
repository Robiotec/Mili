export function createLayoutModule(deps) {
  const {
    windowObj,
    documentObj,
    cameras,
    dashboardCameraPreviewStage,
    primaryView,
    appShell,
    appSidebar,
    sidebarToggle,
    sidebarLinks,
    sidebarNavLinks,
    logoutButtons,
    locationsMap,
    telemetryMap,
    cameraRegisterMap,
    cameraRegisterModal,
    cameraAdminMapModal,
    themeStorageKey,
    mobileSidebarQuery,
    sidebarStorageKey,
    getVideoByCamera,
    getActiveCamera,
    getActiveTheme,
    setActiveTheme,
    getThemeToggleButton,
    setThemeToggleButton,
    getSidebarViewportWasMobile,
    setSidebarViewportWasMobile,
    getViewportSyncFrame,
    setViewportSyncFrame,
    getViewportSyncTimeout,
    setViewportSyncTimeout,
    getLayoutResizeObserver,
    setLayoutResizeObserver,
    getMapInstance,
    getLastTelemetryCoordinates,
    getLocationsMapInstance,
    getLastLocationCoordinates,
    getRegisterMapInstance,
    getRegisterMapMarker,
    getRegisterMapSeedCoordinates,
    getCameraAdminMapInstance,
    getCameraAdminMapDraftLocation,
    getCameraAdminMapSeedCoordinates,
    fitMapToCoordinates,
    persistActiveCameraSelection,
    stopPolling,
    stopAll,
  } = deps;

  function scheduleViewportMetrics({ followTransition = false } = {}) {
    const currentFrame = getViewportSyncFrame();
    if (currentFrame) {
      windowObj.cancelAnimationFrame(currentFrame);
    }

    const nextFrame = windowObj.requestAnimationFrame(() => {
      setViewportSyncFrame(0);
      syncViewportMetrics();
    });
    setViewportSyncFrame(nextFrame);

    if (!followTransition) return;

    const currentTimeout = getViewportSyncTimeout();
    if (currentTimeout) {
      windowObj.clearTimeout(currentTimeout);
    }
    const nextTimeout = windowObj.setTimeout(() => {
      setViewportSyncTimeout(0);
      syncViewportMetrics();
    }, 280);
    setViewportSyncTimeout(nextTimeout);
  }

  function syncViewportMetrics() {
    const rawHeight = windowObj.visualViewport && Number.isFinite(windowObj.visualViewport.height)
      ? windowObj.visualViewport.height
      : windowObj.innerHeight;
    const nextHeight = Math.max(480, Math.round(rawHeight || windowObj.innerHeight || 0));
    documentObj.documentElement.style.setProperty("--app-height", `${nextHeight}px`);

    const mapInstance = getMapInstance();
    if (mapInstance) {
      windowObj.requestAnimationFrame(() => {
        try {
          mapInstance.invalidateSize();
          const lastTelemetryCoordinates = getLastTelemetryCoordinates();
          if (lastTelemetryCoordinates.length > 0) {
            fitMapToCoordinates(mapInstance, lastTelemetryCoordinates, {
              maxZoom: 15,
              singleZoom: 14,
            });
          }
        } catch (error) {}
      });
    }

    const locationsMapInstance = getLocationsMapInstance();
    if (locationsMapInstance) {
      windowObj.requestAnimationFrame(() => {
        try {
          locationsMapInstance.invalidateSize();
          const lastLocationCoordinates = getLastLocationCoordinates();
          if (lastLocationCoordinates.length > 0) {
            fitMapToCoordinates(locationsMapInstance, lastLocationCoordinates, {
              maxZoom: 17,
              singleZoom: 15,
            });
          }
        } catch (error) {}
      });
    }

    const registerMapInstance = getRegisterMapInstance();
    if (registerMapInstance && cameraRegisterModal && !cameraRegisterModal.hidden) {
      windowObj.requestAnimationFrame(() => {
        try {
          registerMapInstance.invalidateSize();
          const registerMapMarker = getRegisterMapMarker();
          if (registerMapMarker) {
            const markerLatLng = registerMapMarker.getLatLng();
            fitMapToCoordinates(registerMapInstance, [[markerLatLng.lat, markerLatLng.lng]], {
              maxZoom: 16,
              singleZoom: 16,
            });
          } else {
            const registerMapSeedCoordinates = getRegisterMapSeedCoordinates();
            if (registerMapSeedCoordinates.length > 0) {
              fitMapToCoordinates(registerMapInstance, registerMapSeedCoordinates, {
                maxZoom: 16,
                singleZoom: 15,
              });
            }
          }
        } catch (error) {}
      });
    }

    const cameraAdminMapInstance = getCameraAdminMapInstance();
    if (cameraAdminMapInstance && cameraAdminMapModal && !cameraAdminMapModal.hidden) {
      windowObj.requestAnimationFrame(() => {
        try {
          cameraAdminMapInstance.invalidateSize();
          const cameraAdminMapDraftLocation = getCameraAdminMapDraftLocation();
          if (cameraAdminMapDraftLocation) {
            fitMapToCoordinates(
              cameraAdminMapInstance,
              [[cameraAdminMapDraftLocation.lat, cameraAdminMapDraftLocation.lon]],
              {
                maxZoom: 17,
                singleZoom: 17,
              },
            );
          } else {
            const cameraAdminMapSeedCoordinates = getCameraAdminMapSeedCoordinates();
            if (cameraAdminMapSeedCoordinates.length > 0) {
              fitMapToCoordinates(cameraAdminMapInstance, cameraAdminMapSeedCoordinates, {
                maxZoom: 16,
                singleZoom: 15,
              });
            }
          }
        } catch (error) {}
      });
    }
  }

  function pageSupportsStreaming() {
    return cameras.some((camera) => Boolean(getVideoByCamera(camera.name)));
  }

  function pageUsesDashboardCameraPreview() {
    return Boolean(documentObj.body?.classList.contains("page-dashboard") && dashboardCameraPreviewStage);
  }

  function getStoredTheme() {
    try {
      const stored = String(windowObj.localStorage.getItem(themeStorageKey) || "").trim().toLowerCase();
      return stored === "light" ? "light" : stored === "dark" ? "dark" : "";
    } catch (error) {
      return "";
    }
  }

  function resolveInitialTheme() {
    return getStoredTheme() || "dark";
  }

  function syncThemeToggleButton() {
    const themeToggleButton = getThemeToggleButton();
    if (!themeToggleButton) return;
    const activeTheme = getActiveTheme();
    themeToggleButton.dataset.theme = activeTheme;
    themeToggleButton.setAttribute("aria-pressed", activeTheme === "light" ? "true" : "false");
    themeToggleButton.setAttribute(
      "aria-label",
      activeTheme === "light" ? "Cambiar a modo oscuro" : "Cambiar a modo claro",
    );
  }

  function syncThemeToggleVisibility() {
    const themeToggleButton = getThemeToggleButton();
    if (!themeToggleButton) return;
    const shouldHide = Boolean(primaryView && getActiveCamera());
    documentObj.body.classList.toggle("is-theme-toggle-hidden", shouldHide);
  }

  function applyTheme(theme, { persist = true } = {}) {
    const nextTheme = theme === "light" ? "light" : "dark";
    setActiveTheme(nextTheme);
    documentObj.body.dataset.theme = nextTheme;
    documentObj.documentElement.style.colorScheme = nextTheme;
    if (persist) {
      try {
        windowObj.localStorage.setItem(themeStorageKey, nextTheme);
      } catch (error) {}
    }
    syncThemeToggleButton();
  }

  function toggleTheme() {
    applyTheme(getActiveTheme() === "light" ? "dark" : "light");
  }

  function ensureThemeToggle() {
    const currentToggle = getThemeToggleButton();
    if (currentToggle) return currentToggle;

    const themeToggleButton = documentObj.createElement("button");
    themeToggleButton.type = "button";
    themeToggleButton.id = "theme-toggle";
    themeToggleButton.className = "theme-toggle";
    themeToggleButton.innerHTML = `
      <span class="theme-toggle-track" aria-hidden="true">
        <span class="theme-toggle-icon is-moon">☾</span>
        <span class="theme-toggle-icon is-sun">☀</span>
        <span class="theme-toggle-thumb"></span>
      </span>
    `;
    themeToggleButton.addEventListener("click", toggleTheme);
    documentObj.body.appendChild(themeToggleButton);
    setThemeToggleButton(themeToggleButton);
    syncThemeToggleButton();
    syncThemeToggleVisibility();
    return themeToggleButton;
  }

  function isMobileSidebarViewport() {
    return windowObj.matchMedia(mobileSidebarQuery).matches;
  }

  function syncSidebarToggleState() {
    if (!sidebarToggle || !appShell) return;
    const isMobile = isMobileSidebarViewport();
    const collapsed = appShell.classList.contains("is-sidebar-collapsed");
    const label = isMobile
      ? (collapsed ? "Abrir menu" : "Cerrar menu")
      : (collapsed ? "Expandir menu" : "Contraer menu");
    sidebarToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    sidebarToggle.setAttribute("aria-label", label);
    sidebarToggle.title = label;
    if (appSidebar) {
      appSidebar.setAttribute("aria-hidden", isMobile && collapsed ? "true" : "false");
    }
  }

  function syncMobileSidebarState() {
    if (!appShell) return;
    const isMobile = isMobileSidebarViewport();
    const isOpen = isMobile && !appShell.classList.contains("is-sidebar-collapsed");
    appShell.classList.toggle("is-sidebar-mobile-open", isOpen);
    documentObj.body.classList.toggle("is-sidebar-mobile-open", isOpen);
  }

  function applySidebarState(collapsed) {
    if (!appShell) return;
    appShell.classList.toggle("is-sidebar-collapsed", Boolean(collapsed));
    syncMobileSidebarState();
    syncSidebarToggleState();
    scheduleViewportMetrics({ followTransition: true });
  }

  function syncSidebarForViewport() {
    if (!appShell) return;
    if (isMobileSidebarViewport()) {
      if (!getSidebarViewportWasMobile()) {
        applySidebarState(true);
      } else {
        syncMobileSidebarState();
        syncSidebarToggleState();
      }
      setSidebarViewportWasMobile(true);
      return;
    }
    setSidebarViewportWasMobile(false);
    const storedValue = windowObj.localStorage.getItem(sidebarStorageKey);
    const shouldCollapse = storedValue === null ? true : storedValue === "1";
    applySidebarState(shouldCollapse);
  }

  function closeMobileSidebar() {
    if (!appShell || !isMobileSidebarViewport()) return;
    if (appShell.classList.contains("is-sidebar-collapsed")) {
      syncMobileSidebarState();
      syncSidebarToggleState();
      return;
    }
    applySidebarState(true);
  }

  function setActiveSidebarLink() {
    const currentPath = (windowObj.location.pathname || "/").replace(/\/+$/, "") || "/";
    sidebarNavLinks.forEach((link) => {
      const href = link.getAttribute("href") || "/";
      const target = new URL(href, windowObj.location.origin);
      const targetPath = target.pathname.replace(/\/+$/, "") || "/";
      link.classList.toggle("is-current", targetPath === currentPath);
    });
    logoutButtons.forEach((button) => button.classList.remove("is-current"));
  }

  function syncSidebarLinkLabels() {
    sidebarLinks.forEach((link) => {
      const tooltip = link.querySelector(".sidebar-link-tooltip");
      const primaryLabel = tooltip instanceof HTMLElement && tooltip.textContent
        ? tooltip.textContent.trim()
        : "";
      if (!primaryLabel) return;
      link.setAttribute("title", primaryLabel);
      if (!link.getAttribute("aria-label")) {
        link.setAttribute("aria-label", primaryLabel);
      }
    });
  }

  async function performLogout() {
    logoutButtons.forEach((button) => {
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
    });

    try {
      const response = await fetch("/api/logout", {
        method: "POST",
        headers: {
          Accept: "application/json",
        },
        credentials: "same-origin",
      });

      let payload = {};
      try {
        payload = await response.json();
      } catch (error) {
        payload = {};
      }

      if (!response.ok) {
        throw new Error(
          typeof payload.message === "string" && payload.message
            ? payload.message
            : "No se pudo cerrar la sesion.",
        );
      }

      stopPolling();
      stopAll();
      persistActiveCameraSelection(null);
      windowObj.location.assign(
        typeof payload.redirect === "string" && payload.redirect.trim()
          ? payload.redirect.trim()
          : "/login",
      );
    } catch (error) {
      logoutButtons.forEach((button) => {
        button.disabled = false;
        button.removeAttribute("aria-busy");
      });
      windowObj.alert(error instanceof Error ? error.message : "No se pudo cerrar la sesion.");
    }
  }

  function observeLayoutChanges() {
    if (typeof windowObj.ResizeObserver !== "function" || getLayoutResizeObserver()) return;
    const targets = [
      appShell,
      primaryView,
      locationsMap,
      telemetryMap,
      cameraRegisterMap,
    ].filter((node) => node instanceof Element);
    if (targets.length === 0) return;

    const observer = new windowObj.ResizeObserver(() => {
      scheduleViewportMetrics();
    });
    setLayoutResizeObserver(observer);
    targets.forEach((node) => observer.observe(node));
  }

  return {
    scheduleViewportMetrics,
    syncViewportMetrics,
    pageSupportsStreaming,
    pageUsesDashboardCameraPreview,
    getStoredTheme,
    resolveInitialTheme,
    syncThemeToggleButton,
    syncThemeToggleVisibility,
    applyTheme,
    toggleTheme,
    ensureThemeToggle,
    syncSidebarToggleState,
    isMobileSidebarViewport,
    syncMobileSidebarState,
    applySidebarState,
    syncSidebarForViewport,
    closeMobileSidebar,
    setActiveSidebarLink,
    syncSidebarLinkLabels,
    performLogout,
    observeLayoutChanges,
  };
}
