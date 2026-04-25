(async () => {
const config = window.__WEB_APP_CONFIG__ || {};
const CAMERAS = Array.isArray(config.cameras) ? config.cameras : [];
const DEVICES = Array.isArray(config.devices) ? config.devices : [];
const DEVICE_BY_CAMERA = new Map(DEVICES.map((device) => [device.camera_name, device]));
const DEFAULT_CAMERA = typeof config.defaultCamera === "string" ? config.defaultCamera : null;
const STATIC_ASSET_VERSION = typeof config.staticAssetVersion === "string" ? config.staticAssetVersion : "";
const START_WITHOUT_CAMERA = Boolean(config.startWithoutCamera);
const EMPTY_CAMERA_MESSAGE = typeof config.emptyCameraMessage === "string" && config.emptyCameraMessage.trim()
  ? config.emptyCameraMessage.trim()
  : "No ha seleccionado ninguna cámara.";
const embeddedViewerSessions = new Set();
const hlsPlayers = new Map();
const reconnectTimers = new Map();
const reconnectDelayMs = new Map();
const connectInFlight = new Set();
const connectionTokens = new Map();
const switchButtons = new Map();
const inferenceButtons = new Map();
const STATUS_REFRESH_MS = 4000;
const EVENT_REFRESH_MS = 4000;
const TELEMETRY_REFRESH_MS = Number.isFinite(Number(config.telemetryRefreshMs))
  ? Math.max(Number(config.telemetryRefreshMs), 250)
  : 1000;
const TELEMETRY_SPEED_SMOOTHING_FACTOR = 0.24;
const TELEMETRY_SPEED_MIN_MOVEMENT_METERS = 3;
const TELEMETRY_SPEED_STATIONARY_CONFIRMATIONS = 3;
const TELEMETRY_SPEED_ZERO_DECAY_FACTOR = 0.45;
const TELEMETRY_SPEED_MIN_VISIBLE_KMH = 0.5;
const TELEMETRY_SPEED_MAX_SAMPLE_GAP_SEC = 15;
const ARCOM_CONCESSION_MIN_ZOOM = Number.isFinite(Number(config.arcomMinZoom)) ? Math.max(1, Math.min(24, Number(config.arcomMinZoom))) : 11;
const ARCOM_CONCESSION_VIEW_LIMIT = 120;
const ECUADOR_MAP_CENTER = [-1.831239, -78.183406];
const ECUADOR_MAP_ZOOM = 7;
const VEHICLE_REGISTRY_REFRESH_MS = 4000;
const MAP_MARKER_DETAIL_HOVER_DELAY_MS = 3000;
const SINGLE_STREAM_BREAKPOINT_PX = 960;
const THEME_STORAGE_KEY = "robiotec.theme";
const TELEMETRY_MAP_STYLE_STORAGE_KEY = "robiotec.telemetry.map.style";
const TELEMETRY_MINING_LAYER_STORAGE_KEY = "robiotec.telemetry.mining.enabled";
const SATELLITE_TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
const SATELLITE_LABELS_TILE_URL = "https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}";
const SATELLITE_TILE_ATTRIBUTION = '&copy; <a href="https://www.esri.com/">Esri</a> &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community';
const STREET_TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const STREET_TILE_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const CAMERA_PICKER_MAX_ZOOM = 18;
const DARK_TILE_URL = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
const DARK_TILE_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>';
const RELIEF_TILE_URL = "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png";
const RELIEF_TILE_ATTRIBUTION = 'Map data: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, SRTM | Map style: &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)';
const TELEMETRY_MAP_STYLE_DEFINITIONS = {
  satellite: {
    baseUrl: SATELLITE_TILE_URL,
    baseOptions: {
      maxZoom: 20,
      attribution: SATELLITE_TILE_ATTRIBUTION,
    },
    overlayUrl: SATELLITE_LABELS_TILE_URL,
    overlayOptions: {
      maxZoom: 20,
      attribution: "",
      pane: "overlayPane",
      opacity: 0.92,
    },
  },
  dark: {
    baseUrl: DARK_TILE_URL,
    baseOptions: {
      subdomains: "abcd",
      maxZoom: 20,
      detectRetina: true,
      attribution: DARK_TILE_ATTRIBUTION,
    },
  },
  relief: {
    baseUrl: RELIEF_TILE_URL,
    baseOptions: {
      subdomains: "abc",
      maxZoom: 17,
      attribution: RELIEF_TILE_ATTRIBUTION,
    },
  },
};

const cameraStage = document.getElementById("camera-stage");
const primaryView = document.getElementById("primary-view");
const cameraPool = document.getElementById("camera-pool");
const switcher = document.getElementById("camera-switcher");
const focusClose = document.getElementById("focus-close");
const platePreviewOutput = document.getElementById("plate-preview-output");
const platePreviewCopy = document.getElementById("plate-preview-copy");
const platePreviewStatus = document.getElementById("plate-preview-status");
const platePreviewChoices = Array.from(document.querySelectorAll(".plate-preview-choice"));
const plateFileModal = document.getElementById("plate-file-modal");
const plateFileModalBackdrop = document.getElementById("plate-file-modal-backdrop");
const plateFileClose = document.getElementById("plate-file-close");
const plateFilePlate = document.getElementById("plate-file-plate");
const plateFileContent = document.getElementById("plate-file-content");
const dashboardCameraPreview = document.getElementById("dashboard-camera-preview");
const dashboardCameraPreviewName = document.getElementById("dashboard-camera-preview-name");
const dashboardCameraPreviewEmpty = document.getElementById("dashboard-camera-preview-empty");
const dashboardCameraPreviewStage = document.getElementById("dashboard-camera-preview-stage");
const dashboardCameraPreviewClose = document.getElementById("dashboard-camera-preview-close");
const dashboardMobilePanelSwitcher = document.getElementById("dashboard-mobile-panel-switcher");
const dashboardMobilePanelButtons = Array.from(document.querySelectorAll("[data-dashboard-mobile-view]"));
const activeCameraName = document.getElementById("active-camera-name");
const activeCameraCapabilities = document.getElementById("active-camera-capabilities");
const audioToggle = document.getElementById("audio-toggle");
const audioVolume = document.getElementById("audio-volume");
const audioSummary = document.getElementById("audio-summary");
const audioControls = document.querySelector(".audio-controls");
const cameraRegisterOpen = document.getElementById("camera-register-open");
const cameraRegisterModal = document.getElementById("camera-register-modal");
const cameraRegisterBackdrop = document.getElementById("camera-register-backdrop");
const cameraRegisterClose = document.getElementById("camera-register-close");
const cameraRegisterCancel = document.getElementById("camera-register-cancel");
const cameraRegisterForm = document.getElementById("camera-register-form");
const cameraRegisterName = document.getElementById("camera-register-name");
const cameraRegisterSource = document.getElementById("camera-register-source");
const cameraRegisterLat = document.getElementById("camera-register-lat");
const cameraRegisterLon = document.getElementById("camera-register-lon");
const cameraRegisterMap = document.getElementById("camera-register-map");
const cameraRegisterLocation = document.getElementById("camera-register-location");
const cameraRegisterSubmit = document.getElementById("camera-register-submit");
const cameraRegisterFeedback = document.getElementById("camera-register-feedback");
const vehicleRegisterOpen = document.getElementById("vehicle-register-open");
const vehicleRegisterModal = document.getElementById("vehicle-register-modal");
const vehicleRegisterBackdrop = document.getElementById("vehicle-register-backdrop");
const vehicleRegisterClose = document.getElementById("vehicle-register-close");
const vehicleRegisterCancel = document.getElementById("vehicle-register-cancel");
const vehicleRegisterDelete = document.getElementById("vehicle-register-delete");
const vehicleRegisterForm = document.getElementById("vehicle-register-form");
const vehicleRegisterTitle = document.getElementById("vehicle-register-title");
const vehicleRegisterCopy = document.getElementById("vehicle-register-copy");
const vehicleRegisterOrganization = document.getElementById("vehicle-register-organization");
const vehicleRegisterOwner = document.getElementById("vehicle-register-owner");
const vehicleRegisterType = document.getElementById("vehicle-register-type");
const vehicleRegisterTypeHelp = document.getElementById("vehicle-register-type-help");
const vehicleRegisterTypeNote = document.getElementById("vehicle-register-type-note");
const vehicleRegisterTelemetryMode = document.getElementById("vehicle-register-telemetry-mode");
const vehicleRegisterTelemetryHelp = document.getElementById("vehicle-register-telemetry-help");
const vehicleRegisterLabel = document.getElementById("vehicle-register-label");
const vehicleRegisterIdentifierLabel = document.getElementById("vehicle-register-identifier-label");
const vehicleRegisterIdentifier = document.getElementById("vehicle-register-identifier");
const vehicleRegisterIdentifierHelp = document.getElementById("vehicle-register-identifier-help");
const vehicleRegisterApiFields = document.getElementById("vehicle-register-api-fields");
const vehicleRegisterApiDeviceId = document.getElementById("vehicle-register-api-device-id");
const vehicleRegisterNotes = document.getElementById("vehicle-register-notes");
const vehicleRegisterCameraList = document.getElementById("vehicle-register-camera-list");
const vehicleRegisterSubmit = document.getElementById("vehicle-register-submit");
const vehicleRegisterFeedback = document.getElementById("vehicle-register-feedback");
const roleAdminForm = document.getElementById("role-admin-form");
const roleAdminCode = document.getElementById("role-admin-code");
const roleAdminName = document.getElementById("role-admin-name");
const roleAdminOrder = document.getElementById("role-admin-order");
const roleAdminSystem = document.getElementById("role-admin-system");
const roleAdminFeedback = document.getElementById("role-admin-feedback");
const roleAdminSubmit = document.getElementById("role-admin-submit");
const roleAdminReset = document.getElementById("role-admin-reset");
const roleAdminDelete = document.getElementById("role-admin-delete");
const roleAdminRailList = document.getElementById("role-admin-rail-list");
const roleAdminDetailTitle = document.getElementById("role-admin-detail-title");
const roleAdminDetailCopy = document.getElementById("role-admin-detail-copy");
const roleAdminTotal = document.getElementById("role-admin-total");
const userAdminRefresh = document.getElementById("user-admin-refresh");
const userAdminForm = document.getElementById("user-admin-form");
const userAdminUsername = document.getElementById("user-admin-username");
const userAdminEmail = document.getElementById("user-admin-email");
const userAdminName = document.getElementById("user-admin-name");
const userAdminLastName = document.getElementById("user-admin-last-name");
const userAdminPhone = document.getElementById("user-admin-phone");
const userAdminPassword = document.getElementById("user-admin-password");
const userAdminPasswordHelp = document.getElementById("user-admin-password-help");
const userAdminRole = document.getElementById("user-admin-role");
const userAdminActive = document.getElementById("user-admin-active");
const userAdminFeedback = document.getElementById("user-admin-feedback");
const userAdminSubmit = document.getElementById("user-admin-submit");
const userAdminReset = document.getElementById("user-admin-reset");
const userAdminDelete = document.getElementById("user-admin-delete");
const userAdminRailList = document.getElementById("user-admin-rail-list");
const userAdminDetailTitle = document.getElementById("user-admin-detail-title");
const userAdminDetailCopy = document.getElementById("user-admin-detail-copy");
const userAdminTotal = document.getElementById("user-admin-total");
const organizationAdminTotal = document.getElementById("organization-admin-total");
const userAdminDevelopers = document.getElementById("user-admin-developers");
const userAdminUpdated = document.getElementById("user-admin-updated");
const userAdminScopeRole = normalizeAccessRoleValue(document.body?.dataset.userAdminScopeRole || "desarrollador");
const organizationAdminForm = document.getElementById("organization-admin-form");
const organizationAdminName = document.getElementById("organization-admin-name");
const organizationAdminDescription = document.getElementById("organization-admin-description");
const organizationAdminOwner = document.getElementById("organization-admin-owner");
const organizationAdminActive = document.getElementById("organization-admin-active");
const organizationAdminFeedback = document.getElementById("organization-admin-feedback");
const organizationAdminSubmit = document.getElementById("organization-admin-submit");
const organizationAdminReset = document.getElementById("organization-admin-reset");
const organizationAdminDelete = document.getElementById("organization-admin-delete");
const organizationAdminRailList = document.getElementById("organization-admin-rail-list");
const organizationAdminDetailTitle = document.getElementById("organization-admin-detail-title");
const organizationAdminDetailCopy = document.getElementById("organization-admin-detail-copy");
const cameraAdminTotal = document.getElementById("camera-admin-total");
const cameraAdminForm = document.getElementById("camera-admin-form");
const cameraAdminName = document.getElementById("camera-admin-name");
const cameraAdminDescription = document.getElementById("camera-admin-description");
const cameraAdminOrganization = document.getElementById("camera-admin-organization");
const cameraAdminOwner = document.getElementById("camera-admin-owner");
const cameraAdminType = document.getElementById("camera-admin-type");
const cameraAdminTypeHelp = document.getElementById("camera-admin-type-help");
const cameraAdminProtocolWrap = document.getElementById("camera-admin-protocol-wrap");
const cameraAdminProtocol = document.getElementById("camera-admin-protocol");
const cameraAdminStreamUrl = document.getElementById("camera-admin-stream-url");
const cameraAdminStreamUrlHelp = document.getElementById("camera-admin-stream-url-help");
const cameraAdminRtspUrlWrap = document.getElementById("camera-admin-rtsp-url-wrap");
const cameraAdminRtspUrl = document.getElementById("camera-admin-rtsp-url");
const cameraAdminRtspUrlHelp = document.getElementById("camera-admin-rtsp-url-help");
const cameraAdminCode = document.getElementById("camera-admin-code");
const cameraAdminBrandWrap = document.getElementById("camera-admin-brand-wrap");
const cameraAdminBrand = document.getElementById("camera-admin-brand");
const cameraAdminBrandHelp = document.getElementById("camera-admin-brand-help");
const cameraAdminBrandCustomWrap = document.getElementById("camera-admin-brand-custom-wrap");
const cameraAdminBrandCustom = document.getElementById("camera-admin-brand-custom");
const cameraAdminModelWrap = document.getElementById("camera-admin-model-wrap");
const cameraAdminModel = document.getElementById("camera-admin-model");
const cameraAdminSerialWrap = document.getElementById("camera-admin-serial-wrap");
const cameraAdminSerial = document.getElementById("camera-admin-serial");
const cameraAdminStreamUserWrap = document.getElementById("camera-admin-stream-user-wrap");
const cameraAdminStreamUser = document.getElementById("camera-admin-stream-user");
const cameraAdminStreamPasswordWrap = document.getElementById("camera-admin-stream-password-wrap");
const cameraAdminStreamPassword = document.getElementById("camera-admin-stream-password");
const cameraAdminRtspBuilder = document.getElementById("camera-admin-rtsp-builder");
const cameraAdminRtspCopy = document.getElementById("camera-admin-rtsp-copy");
const cameraAdminRtspIp = document.getElementById("camera-admin-rtsp-ip");
const cameraAdminRtspPort = document.getElementById("camera-admin-rtsp-port");
const cameraAdminRtspChannelWrap = document.getElementById("camera-admin-rtsp-channel-wrap");
const cameraAdminRtspChannel = document.getElementById("camera-admin-rtsp-channel");
const cameraAdminRtspSubstreamWrap = document.getElementById("camera-admin-rtsp-substream-wrap");
const cameraAdminRtspSubstream = document.getElementById("camera-admin-rtsp-substream");
const cameraAdminRtspPathWrap = document.getElementById("camera-admin-rtsp-path-wrap");
const cameraAdminRtspPath = document.getElementById("camera-admin-rtsp-path");
const cameraAdminRtspGenerate = document.getElementById("camera-admin-rtsp-generate");
const cameraAdminRtspPreview = document.getElementById("camera-admin-rtsp-preview");
const cameraAdminInferenceEnabled = document.getElementById("camera-admin-inference-enabled");
const cameraAdminActive = document.getElementById("camera-admin-active");
const cameraAdminStaticFields = document.getElementById("camera-admin-static-fields");
const cameraAdminVehicleFields = document.getElementById("camera-admin-vehicle-fields");
const cameraAdminLat = document.getElementById("camera-admin-lat");
const cameraAdminLon = document.getElementById("camera-admin-lon");
const cameraAdminAltitude = document.getElementById("camera-admin-altitude");
const cameraAdminAddress = document.getElementById("camera-admin-address");
const cameraAdminReference = document.getElementById("camera-admin-reference");
const cameraAdminVehicle = document.getElementById("camera-admin-vehicle");
const cameraAdminVehiclePosition = document.getElementById("camera-admin-vehicle-position");
const cameraAdminFeedback = document.getElementById("camera-admin-feedback");
const cameraAdminRbox = document.getElementById("camera-admin-rbox");
const cameraAdminSubmit = document.getElementById("camera-admin-submit");
const cameraAdminReset = document.getElementById("camera-admin-reset");
const cameraAdminDelete = document.getElementById("camera-admin-delete");
const cameraAdminRailList = document.getElementById("camera-admin-rail-list");
const cameraAdminDetailTitle = document.getElementById("camera-admin-detail-title");
const cameraAdminDetailCopy = document.getElementById("camera-admin-detail-copy");
const cameraAdminMapOpen = document.getElementById("camera-admin-map-open");
const cameraAdminMapSummary = document.getElementById("camera-admin-map-summary");
const cameraAdminMapModal = document.getElementById("camera-admin-map-modal");
const cameraAdminMapBackdrop = document.getElementById("camera-admin-map-backdrop");
const cameraAdminMapClose = document.getElementById("camera-admin-map-close");
const cameraAdminMapCancel = document.getElementById("camera-admin-map-cancel");
const cameraAdminMapApply = document.getElementById("camera-admin-map-apply");
const cameraAdminMap = document.getElementById("camera-admin-map");
const cameraAdminMapLocation = document.getElementById("camera-admin-map-location");
const telemetryDeviceFilter = document.getElementById("telemetry-device-filter");
const telemetryFocusCard = document.getElementById("telemetry-focus-card");
const telemetryMapOverlayBox = document.getElementById("telemetry-map-overlay-box");
const telemetryMapOverlayOrganization = document.getElementById("telemetry-map-overlay-organization");
const telemetryMapOverlayPreview = document.getElementById("telemetry-map-overlay-preview");
const telemetryMapOverlayClose = document.getElementById("telemetry-map-overlay-close");
const telemetryMapMode = document.getElementById("telemetry-map-mode");
const telemetryMapStyleSelect = document.getElementById("telemetry-map-style");
const telemetryMapRecenter = document.getElementById("telemetry-map-recenter");
const telemetryMiningToggle = document.getElementById("telemetry-mining-toggle");
const eventsFeed = document.getElementById("events-feed");
const logsModeSwitch = document.getElementById("logs-mode-switch");
const eventsDeviceFilter = document.getElementById("events-device-filter");
const eventsSummary = document.getElementById("events-summary");
const eventsDetail = document.getElementById("events-detail");
const vehicleRegistryDetail = document.getElementById("vehicle-registry-detail");
const vehicleRegistryDetailTitle = document.getElementById("vehicle-registry-detail-title");
const vehicleRegistryDetailCopy = document.getElementById("vehicle-registry-detail-copy");
const vehicleRegistryRailList = document.getElementById("vehicle-registry-rail-list");
const vehicleRegistryTotal = document.getElementById("vehicle-registry-total");
const vehicleRegistryCameras = document.getElementById("vehicle-registry-cameras");
const vehicleRegistryUpdated = document.getElementById("vehicle-registry-updated");
const telemetryMap = document.getElementById("telemetry-map");
const locationsMap = document.getElementById("locations-map");
const locationsSummary = document.getElementById("locations-summary");
const appShell = document.querySelector(".app-shell");
const appSidebar = document.getElementById("app-sidebar");
const sidebarToggle = document.getElementById("sidebar-toggle");
const sidebarLinks = Array.from(document.querySelectorAll(".sidebar-link"));
const sidebarNavLinks = sidebarLinks.filter((link) => link instanceof HTMLAnchorElement);
const logoutButtons = Array.from(document.querySelectorAll(".sidebar-link-logout"));
const SIDEBAR_STORAGE_KEY = "robiotec.sidebar.collapsed";
const MOBILE_SIDEBAR_QUERY = "(max-width: 900px)";
const ACTIVE_CAMERA_STORAGE_KEY = "robiotec.active_camera";
const LOCATION_TAG_LABELS = {
  video: "Video",
  audio: "Audio",
  telemetry: "GPS",
};
const USER_CAN_MANAGE_CAMERA_INFERENCE = Boolean(cameraRegisterOpen || cameraRegisterModal);
const cameraStatuses = new Map();
const mapMarkerIconCache = new Map();

function buildCameraIconUrl(filename) {
  if (!filename) return "";
  if (!STATIC_ASSET_VERSION) {
    return `/icons/${filename}`;
  }
  return `/icons/${filename}?v=${encodeURIComponent(STATIC_ASSET_VERSION)}`;
}

const CAMERA_ICON_URLS = {
  on: buildCameraIconUrl("camara_on.png"),
  off: buildCameraIconUrl("camara_off.png"),
};
const DRONE_ICON_URL = buildCameraIconUrl("Dron_potition.png");
const SPY_CAR_ICON_URL = buildCameraIconUrl("carro_espia.png");

function getRequestedCameraNameFromUrl() {
  try {
    const params = new URLSearchParams(window.location.search || "");
    const requested = String(params.get("camera") || "").trim();
    if (requested && CAMERAS.some((camera) => camera.name === requested)) {
      return requested;
    }
  } catch (error) {}
  return null;
}

function normalizeCameraSelectionName(cameraName) {
  const normalized = String(cameraName || "").trim();
  if (!normalized) return null;
  return CAMERAS.some((camera) => camera.name === normalized) ? normalized : null;
}

function getStoredActiveCameraName() {
  try {
    const stored = normalizeCameraSelectionName(window.localStorage.getItem(ACTIVE_CAMERA_STORAGE_KEY));
    if (stored) {
      return stored;
    }
    window.localStorage.removeItem(ACTIVE_CAMERA_STORAGE_KEY);
  } catch (error) {}
  return null;
}

function persistActiveCameraSelection(cameraName) {
  try {
    const normalized = normalizeCameraSelectionName(cameraName);
    if (normalized) {
      window.localStorage.setItem(ACTIVE_CAMERA_STORAGE_KEY, normalized);
      return;
    }
    window.localStorage.removeItem(ACTIVE_CAMERA_STORAGE_KEY);
  } catch (error) {}
}

function resolveInitialMiningLayerEnabled() {
  try {
    const stored = window.localStorage.getItem(TELEMETRY_MINING_LAYER_STORAGE_KEY);
    if (stored === "0") return false;
    if (stored === "1") return true;
  } catch (error) {}
  return false;
}

function persistMiningLayerEnabled(enabled) {
  try {
    window.localStorage.setItem(TELEMETRY_MINING_LAYER_STORAGE_KEY, enabled ? "1" : "0");
  } catch (error) {}
}

function getInitialCameraName({ allowFallback = true } = {}) {
  const requestedCamera = getRequestedCameraNameFromUrl();
  if (requestedCamera) {
    return requestedCamera;
  }
  const storedCamera = getStoredActiveCameraName();
  if (storedCamera) {
    return storedCamera;
  }
  if (!allowFallback) {
    return null;
  }
  if (CAMERAS.find((camera) => camera.name === DEFAULT_CAMERA)) {
    return DEFAULT_CAMERA;
  }
  return CAMERAS.length > 0 ? CAMERAS[0].name : null;
}

let activeCamera = null;
let dashboardPinnedCameraNames = [];
let dashboardMobileView = "map";
let audioEnabled = false;
let audioUiSyncInProgress = false;
let activeTheme = "dark";
let themeToggleButton = null;
let sidebarViewportWasMobile = false;
let mapInstance = null;
let mapAutoFitDone = false;
let lastTelemetryBoundsSignature = "";
let lastTelemetryCoordinates = [];
let lastTelemetrySnapshot = [];
let activeTelemetryDeviceId = null;
let lastTelemetryFilterSignature = "";
let telemetryMapManualControl = false;
let telemetryMapProgrammaticInteractionUntil = 0;
let telemetryMapBaseLayer = null;
let telemetryMapOverlayLayer = null;
let miningConcessionLayer = null;
let miningConcessionViewportRefreshTimerId = null;
let miningConcessionViewportRequestId = 0;
let lastMiningConcessionViewportKey = "";
let selectedMiningConcessionInfo = null;
let selectedMiningConcessionDeviceId = "";
let selectedMiningConcessionLookupKey = "";
let miningConcessionLookupRequestId = 0;
let miningConcessionLayerEnabled = true;
let locationsMapInstance = null;
let locationsMapAutoFitDone = false;
let lastLocationMarkerCount = 0;
let lastLocationBoundsSignature = "";
let lastLocationCoordinates = [];
let telemetryOverlayCameraName = null;
let telemetryOverlaySourceKind = "";
let telemetryOverlaySelectionLabel = "";
let telemetryOverlayPlayerKey = null;
let telemetryOverlayRenderToken = 0;
let statusIntervalId = null;
let eventIntervalId = null;
let telemetryIntervalId = null;
let vehicleRegistryIntervalId = null;
let selectedVehicleRegistryKey = null;
let editingVehicleRegistrationId = null;
let lastVehicleRegistrySnapshot = [];
let vehicleApiDefaults = {
  default_drone_device_id: "drone",
};
let cameraAdminCreationMode = "camera";
const DEFAULT_CAMERA_BRAND_PRESETS = [
  {
    code: "hikvision",
    label: "Hikvision",
    description: "Usa canales numerados y permite elegir stream principal o substream.",
    default_port: 554,
    supports_channel: true,
    supports_substream: true,
    requires_custom_path: false,
  },
  {
    code: "dahua",
    label: "Dahua",
    description: "Genera la ruta realmonitor con canal y subtipo.",
    default_port: 554,
    supports_channel: true,
    supports_substream: true,
    requires_custom_path: false,
  },
  {
    code: "axis",
    label: "Axis",
    description: "Usa la ruta estándar axis-media/media.amp.",
    default_port: 554,
    supports_channel: false,
    supports_substream: false,
    requires_custom_path: false,
  },
  {
    code: "uniview",
    label: "Uniview",
    description: "Permite alternar entre video1 y video2.",
    default_port: 554,
    supports_channel: false,
    supports_substream: true,
    requires_custom_path: false,
  },
  {
    code: "generic",
    label: "Genérica / ONVIF",
    description: "Genera una ruta simple tipo stream1 o stream2.",
    default_port: 554,
    supports_channel: false,
    supports_substream: true,
    requires_custom_path: false,
  },
  {
    code: "custom_path",
    label: "Ruta personalizada",
    description: "Permite escribir manualmente la ruta RTSP completa después del host.",
    default_port: 554,
    supports_channel: false,
    supports_substream: false,
    requires_custom_path: true,
  },
];
let vehicleRegistryOptionCatalog = {
  organizations: [],
  owners: [],
  vehicle_types: [],
  cameras: [],
};
let activeLogsMode = "general";
let selectedLogEntryId = null;
let activeLogsDeviceId = "";
let lastEventsSnapshot = [];
let lastLogVehicleRegistry = [];
let lastLogsTelemetry = [];
let userAdminRoles = [];
let lastUserAdminSnapshot = [];
let lastRoleAdminSnapshot = [];
let lastOrganizationAdminSnapshot = [];
let lastCameraAdminSnapshot = [];
let selectedUserAdminId = null;
let selectedRoleAdminId = null;
let selectedOrganizationAdminId = null;
let selectedCameraAdminId = null;
let lastUserAdminUpdatedAt = 0;
let cameraInferenceFeedbackTimerId = null;
let platePreviewStatusTimerId = null;
let plateFileRequestToken = 0;
let cameraAdminOptionCatalog = {
  organizations: [],
  owners: [],
  camera_types: [],
  protocols: [],
  vehicles: [],
  brand_presets: [],
  stream_server: null,
};
let cameraAdminStreamUrlAutoManaged = false;
let cameraAdminLastGeneratedStreamUrl = "";
const mapMarkers = new Map();
const locationMarkers = new Map();
let registerMapInstance = null;
let registerMapMarker = null;
let registerMapViewportLoaded = false;
let registerMapSeedCoordinates = [];
let cameraAdminMapInstance = null;
let cameraAdminMapMarker = null;
let cameraAdminMapViewportLoaded = false;
let cameraAdminMapSeedCoordinates = [];
let cameraAdminMapDraftLocation = null;
let viewportSyncFrame = 0;
let viewportSyncTimeout = 0;
let layoutResizeObserver = null;
const CAMERA_BY_DOM_ID = new Map(CAMERAS.map((camera) => [camera.dom_id, camera]));

// Keep the public entrypoint stable while moving heavy feature areas into dedicated modules.
const MODULE_ASSET_SUFFIX = STATIC_ASSET_VERSION
  ? `?v=${encodeURIComponent(STATIC_ASSET_VERSION)}`
  : "";
let createLayoutModule;
let createCameraPlaybackModule;
let createTelemetryOverlayModule;
try {
  ([
    { createLayoutModule },
    { createCameraPlaybackModule },
    { createTelemetryOverlayModule },
  ] = await Promise.all([
    import(`/static/web_app/modules/layout.js${MODULE_ASSET_SUFFIX}`),
    import(`/static/web_app/modules/camera_playback.js${MODULE_ASSET_SUFFIX}`),
    import(`/static/web_app/modules/telemetry_overlay.js${MODULE_ASSET_SUFFIX}`),
  ]));
} catch (error) {
  document.body?.setAttribute("data-web-app-init-error", "module_load_failed");
  window.console.error("No se pudieron cargar los modulos de web_app.", error);
  return;
}

const {
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
} = createCameraPlaybackModule({
  windowObj: window,
  documentObj: document,
  cameras: CAMERAS,
  deviceByCamera: DEVICE_BY_CAMERA,
  embeddedViewerSessions,
  hlsPlayers,
  reconnectDelayMs,
  connectionTokens,
  audioVolume,
  getAudioState: () => ({
    enabled: audioEnabled,
    volume: Number(audioVolume ? audioVolume.value : 75),
  }),
  fetchJson: (...args) => fetchJson(...args),
  createCameraConnectionError: (...args) => createCameraConnectionError(...args),
  setState: (...args) => setState(...args),
  scheduleReconnect: (...args) => scheduleReconnect(...args),
  applyAudioState: () => applyAudioState(),
});

const {
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
} = createLayoutModule({
  windowObj: window,
  documentObj: document,
  cameras: CAMERAS,
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
  themeStorageKey: THEME_STORAGE_KEY,
  mobileSidebarQuery: MOBILE_SIDEBAR_QUERY,
  sidebarStorageKey: SIDEBAR_STORAGE_KEY,
  getVideoByCamera,
  getActiveCamera: () => activeCamera,
  getActiveTheme: () => activeTheme,
  setActiveTheme: (value) => {
    activeTheme = value;
  },
  getThemeToggleButton: () => themeToggleButton,
  setThemeToggleButton: (value) => {
    themeToggleButton = value;
  },
  getSidebarViewportWasMobile: () => sidebarViewportWasMobile,
  setSidebarViewportWasMobile: (value) => {
    sidebarViewportWasMobile = value;
  },
  getViewportSyncFrame: () => viewportSyncFrame,
  setViewportSyncFrame: (value) => {
    viewportSyncFrame = value;
  },
  getViewportSyncTimeout: () => viewportSyncTimeout,
  setViewportSyncTimeout: (value) => {
    viewportSyncTimeout = value;
  },
  getLayoutResizeObserver: () => layoutResizeObserver,
  setLayoutResizeObserver: (value) => {
    layoutResizeObserver = value;
  },
  getMapInstance: () => mapInstance,
  getLastTelemetryCoordinates: () => lastTelemetryCoordinates,
  getLocationsMapInstance: () => locationsMapInstance,
  getLastLocationCoordinates: () => lastLocationCoordinates,
  getRegisterMapInstance: () => registerMapInstance,
  getRegisterMapMarker: () => registerMapMarker,
  getRegisterMapSeedCoordinates: () => registerMapSeedCoordinates,
  getCameraAdminMapInstance: () => cameraAdminMapInstance,
  getCameraAdminMapDraftLocation: () => cameraAdminMapDraftLocation,
  getCameraAdminMapSeedCoordinates: () => cameraAdminMapSeedCoordinates,
  fitMapToCoordinates: (...args) => fitMapToCoordinates(...args),
  persistActiveCameraSelection: (...args) => persistActiveCameraSelection(...args),
  stopPolling: () => stopPolling(),
  stopAll: () => stopAll(),
});

const {
  resetTelemetryMapOverlaySurface,
  getOverlayOrganizationName,
  updateTelemetryMapOverlayCopy,
  hideTelemetryMapOverlay,
  renderTelemetryMapOverlayPreview,
  showTelemetryMapOverlay,
  syncTelemetryMapOverlayFromTelemetrySelection,
} = createTelemetryOverlayModule({
  documentObj: document,
  telemetryMapOverlayBox,
  telemetryMapOverlayOrganization,
  telemetryMapOverlayPreview,
  getTelemetryOverlayCameraName: () => telemetryOverlayCameraName,
  setTelemetryOverlayCameraName: (value) => {
    telemetryOverlayCameraName = value;
  },
  setTelemetryOverlaySourceKind: (value) => {
    telemetryOverlaySourceKind = value;
  },
  setTelemetryOverlaySelectionLabel: (value) => {
    telemetryOverlaySelectionLabel = value;
  },
  getTelemetryOverlayPlayerKey: () => telemetryOverlayPlayerKey,
  setTelemetryOverlayPlayerKey: (value) => {
    telemetryOverlayPlayerKey = value;
  },
  getTelemetryOverlayRenderToken: () => telemetryOverlayRenderToken,
  setTelemetryOverlayRenderToken: (value) => {
    telemetryOverlayRenderToken = value;
  },
  getLastTelemetrySnapshot: () => lastTelemetrySnapshot,
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
  getSelectedTelemetryItem: (...args) => getSelectedTelemetryItem(...args),
  telemetryLabel: (...args) => telemetryLabel(...args),
});

activeCamera = START_WITHOUT_CAMERA
  ? getInitialCameraName({ allowFallback: false })
  : getInitialCameraName();
if (pageUsesDashboardCameraPreview()) {
  activeCamera = null;
}

function addSatelliteTileLayers(map) {
  if (!map || typeof window.L === "undefined") return null;
  const imageryLayer = window.L.tileLayer(SATELLITE_TILE_URL, {
    maxZoom: 20,
    attribution: SATELLITE_TILE_ATTRIBUTION,
  }).addTo(map);

  window.L.tileLayer(SATELLITE_LABELS_TILE_URL, {
    maxZoom: 20,
    attribution: "",
    pane: "overlayPane",
    opacity: 0.92,
  }).addTo(map);

  return imageryLayer;
}

function addStreetTileLayer(map) {
  if (!map || typeof window.L === "undefined") return null;
  return window.L.tileLayer(STREET_TILE_URL, {
    maxZoom: CAMERA_PICKER_MAX_ZOOM,
    maxNativeZoom: CAMERA_PICKER_MAX_ZOOM,
    attribution: STREET_TILE_ATTRIBUTION,
  }).addTo(map);
}

function getInitialTelemetryMapStyle() {
  try {
    const savedValue = String(window.localStorage.getItem(TELEMETRY_MAP_STYLE_STORAGE_KEY) || "").trim().toLowerCase();
    if (Object.prototype.hasOwnProperty.call(TELEMETRY_MAP_STYLE_DEFINITIONS, savedValue)) {
      return savedValue;
    }
  } catch (error) {}
  return "satellite";
}

let activeTelemetryMapStyle = getInitialTelemetryMapStyle();

function applyTelemetryMapStyle(styleCode, { persist = true } = {}) {
  const normalizedStyle = Object.prototype.hasOwnProperty.call(TELEMETRY_MAP_STYLE_DEFINITIONS, styleCode)
    ? styleCode
    : "satellite";
  activeTelemetryMapStyle = normalizedStyle;

  if (telemetryMapStyleSelect && telemetryMapStyleSelect.value !== normalizedStyle) {
    telemetryMapStyleSelect.value = normalizedStyle;
  }

  if (persist) {
    try {
      window.localStorage.setItem(TELEMETRY_MAP_STYLE_STORAGE_KEY, normalizedStyle);
    } catch (error) {}
  }

  if (!mapInstance || typeof window.L === "undefined") {
    return normalizedStyle;
  }

  if (telemetryMapBaseLayer && mapInstance.hasLayer(telemetryMapBaseLayer)) {
    mapInstance.removeLayer(telemetryMapBaseLayer);
  }
  if (telemetryMapOverlayLayer && mapInstance.hasLayer(telemetryMapOverlayLayer)) {
    mapInstance.removeLayer(telemetryMapOverlayLayer);
  }
  telemetryMapBaseLayer = null;
  telemetryMapOverlayLayer = null;

  const styleDefinition = TELEMETRY_MAP_STYLE_DEFINITIONS[normalizedStyle];
  telemetryMapBaseLayer = window.L.tileLayer(styleDefinition.baseUrl, styleDefinition.baseOptions).addTo(mapInstance);
  if (styleDefinition.overlayUrl) {
    telemetryMapOverlayLayer = window.L.tileLayer(
      styleDefinition.overlayUrl,
      styleDefinition.overlayOptions || {},
    ).addTo(mapInstance);
  }

  return normalizedStyle;
}

function isCameraPowered(cameraName) {
  if (!cameraName) return true;
  const snapshot = cameraStatuses.get(cameraName);
  if (!snapshot) return true;
  return !snapshot.hasError && snapshot.rawStatus !== "error";
}

function cameraPowerLabel(cameraName) {
  return isCameraPowered(cameraName) ? "Encendida" : "Apagada";
}

function getMapMarkerIcon({ powered = true, active = false, markerKind = "camera" } = {}) {
  if (typeof window.L === "undefined") return null;
  if (markerKind === "drone") {
    const cacheKey = `drone:${active ? "active" : "idle"}`;
    const cachedIcon = mapMarkerIconCache.get(cacheKey);
    if (cachedIcon) {
      return cachedIcon;
    }

    const size = active ? 54 : 46;
    const icon = window.L.icon({
      iconUrl: DRONE_ICON_URL,
      iconRetinaUrl: DRONE_ICON_URL,
      iconSize: [size, size],
      iconAnchor: [Math.round(size / 2), size - 4],
      popupAnchor: [0, -size + 10],
      tooltipAnchor: [0, -size + 10],
      className: active ? "ops-map-marker is-active" : "ops-map-marker",
    });
    mapMarkerIconCache.set(cacheKey, icon);
    return icon;
  }
  if (markerKind === "car") {
    const cacheKey = `car:${active ? "active" : "idle"}`;
    const cachedIcon = mapMarkerIconCache.get(cacheKey);
    if (cachedIcon) {
      return cachedIcon;
    }

    const size = active ? 54 : 46;
    const icon = window.L.icon({
      iconUrl: SPY_CAR_ICON_URL,
      iconRetinaUrl: SPY_CAR_ICON_URL,
      iconSize: [size, size],
      iconAnchor: [Math.round(size / 2), size - 4],
      popupAnchor: [0, -size + 10],
      tooltipAnchor: [0, -size + 10],
      className: active ? "ops-map-marker is-active" : "ops-map-marker",
    });
    mapMarkerIconCache.set(cacheKey, icon);
    return icon;
  }

  const iconState = powered ? "on" : "off";
  const cacheKey = `camera:${iconState}:${active ? "active" : "idle"}`;
  const cachedIcon = mapMarkerIconCache.get(cacheKey);
  if (cachedIcon) {
    return cachedIcon;
  }

  const size = active ? 46 : 38;
  const icon = window.L.icon({
    iconUrl: CAMERA_ICON_URLS[iconState],
    iconRetinaUrl: CAMERA_ICON_URLS[iconState],
    iconSize: [size, size],
    iconAnchor: [Math.round(size / 2), size - 2],
    popupAnchor: [0, -size + 8],
    tooltipAnchor: [0, -size + 10],
    className: active ? "ops-map-marker is-active" : "ops-map-marker",
  });
  mapMarkerIconCache.set(cacheKey, icon);
  return icon;
}

function createMapMarker(map, lat, lon, { powered = true, active = false, markerKind = "camera" } = {}) {
  if (!map || typeof window.L === "undefined") return null;
  const marker = window.L.marker([lat, lon], {
    icon: getMapMarkerIcon({ powered, active, markerKind }),
    keyboard: false,
    riseOnHover: true,
    zIndexOffset: active ? 600 : 0,
  }).addTo(map);
  marker.__visualStateKey = `${markerKind}:${powered ? "1" : "0"}:${active ? "1" : "0"}`;
  marker.__hoverTooltipActive = false;
  marker.__hoverPopupActive = false;
  marker.__hoverPopupTimer = 0;
  marker.on("mouseover", () => {
    marker.__hoverTooltipActive = true;
    if (typeof marker.openTooltip === "function" && marker.getTooltip()) {
      marker.openTooltip();
    }
    if (marker.__hoverPopupTimer) {
      window.clearTimeout(marker.__hoverPopupTimer);
    }
    marker.__hoverPopupTimer = window.setTimeout(() => {
      marker.__hoverPopupTimer = 0;
      if (!marker.__hoverTooltipActive) {
        return;
      }
      marker.__hoverPopupActive = true;
      if (typeof marker.closeTooltip === "function" && marker.getTooltip()) {
        marker.closeTooltip();
      }
      if (typeof marker.openPopup === "function" && marker.getPopup()) {
        marker.openPopup();
      }
    }, MAP_MARKER_DETAIL_HOVER_DELAY_MS);
  });
  marker.on("mouseout", () => {
    marker.__hoverTooltipActive = false;
    if (marker.__hoverPopupTimer) {
      window.clearTimeout(marker.__hoverPopupTimer);
      marker.__hoverPopupTimer = 0;
    }
    if (typeof marker.closeTooltip === "function" && marker.getTooltip()) {
      marker.closeTooltip();
    }
    if (marker.__hoverPopupActive && typeof marker.closePopup === "function" && marker.getPopup()) {
      marker.closePopup();
    }
    marker.__hoverPopupActive = false;
  });
  marker.on("remove", () => {
    if (marker.__hoverPopupTimer) {
      window.clearTimeout(marker.__hoverPopupTimer);
      marker.__hoverPopupTimer = 0;
    }
  });
  return marker;
}

function updateMapMarkerStyle(marker, { powered = true, active = false, markerKind = "camera" } = {}) {
  if (!marker) return;
  const nextStateKey = `${markerKind}:${powered ? "1" : "0"}:${active ? "1" : "0"}`;
  if (typeof marker.setIcon === "function" && marker.__visualStateKey !== nextStateKey) {
    marker.setIcon(getMapMarkerIcon({ powered, active, markerKind }));
    marker.__visualStateKey = nextStateKey;
  }
  if (typeof marker.setZIndexOffset === "function") {
    marker.setZIndexOffset(active ? 600 : 0);
  }
  if (
    marker.__hoverPopupActive
    && typeof marker.openPopup === "function"
    && marker.getPopup()
    && !(typeof marker.isPopupOpen === "function" && marker.isPopupOpen())
  ) {
    marker.openPopup();
    return;
  }
  if (
    marker.__hoverTooltipActive
    && !marker.__hoverPopupActive
    && typeof marker.openTooltip === "function"
    && marker.getTooltip()
    && !(typeof marker.isTooltipOpen === "function" && marker.isTooltipOpen())
  ) {
    marker.openTooltip();
  }
}

function refreshRenderedMapMarkers() {
  for (const marker of mapMarkers.values()) {
    const cameraName = String(marker.__cameraName || "");
    const deviceId = String(marker.__deviceId || "");
    updateMapMarkerStyle(marker, {
      powered: isCameraPowered(cameraName),
      active: activeTelemetryDeviceId ? deviceId === activeTelemetryDeviceId : cameraName === activeCamera,
      markerKind: String(marker.__markerKind || "camera"),
    });
  }

  for (const marker of locationMarkers.values()) {
    const cameraName = String(marker.__cameraName || "");
    updateMapMarkerStyle(marker, {
      powered: isCameraPowered(cameraName),
      active: cameraName === activeCamera,
      markerKind: "camera",
    });
  }
}

function bindPrettyTooltip(marker, text) {
  if (!marker) return;
  const nextText = String(text || "").trim();
  if (!nextText) return;
  const tooltip = typeof marker.getTooltip === "function" ? marker.getTooltip() : null;
  if (!tooltip) {
    marker.bindTooltip(nextText, {
      className: "ops-map-tooltip",
      direction: "top",
      offset: [0, -18],
      opacity: 1,
    });
    marker.__tooltipText = nextText;
    return;
  }
  if (marker.__tooltipText === nextText) {
    if (
      marker.__hoverTooltipActive
      && !marker.__hoverPopupActive
      && typeof marker.openTooltip === "function"
      && !(typeof marker.isTooltipOpen === "function" && marker.isTooltipOpen())
    ) {
      marker.openTooltip();
    }
    return;
  }
  
  if (typeof tooltip.setContent === "function") {
    tooltip.setContent(nextText);
  } else {
    marker.bindTooltip(nextText, {
      className: "ops-map-tooltip",
      direction: "top",
      offset: [0, -18],
      opacity: 1,
    });
  }
  marker.__tooltipText = nextText;
  if (
    marker.__hoverTooltipActive
    && !marker.__hoverPopupActive
    && typeof marker.openTooltip === "function"
    && !(typeof marker.isTooltipOpen === "function" && marker.isTooltipOpen())
  ) {
    marker.openTooltip();
  }
}

function bindPrettyPopup(marker, html) {
  if (!marker) return;
  const nextHtml = String(html || "").trim();
  if (!nextHtml) return;
  const popup = typeof marker.getPopup === "function" ? marker.getPopup() : null;
  if (!popup) {
    marker.bindPopup(nextHtml, {
      className: "ops-map-popup",
      maxWidth: 280,
      closeButton: false,
      offset: [0, -18],
    });
    marker.__popupHtml = nextHtml;
    return;
  }
  if (marker.__popupHtml === nextHtml) {
    if (
      marker.__hoverPopupActive
      && typeof marker.openPopup === "function"
      && !(typeof marker.isPopupOpen === "function" && marker.isPopupOpen())
    ) {
      marker.openPopup();
    }
    return;
  }
  if (typeof popup.setContent === "function") {
    popup.setContent(nextHtml);
  } else {
    marker.bindPopup(nextHtml, {
      className: "ops-map-popup",
      maxWidth: 280,
      closeButton: false,
      offset: [0, -18],
    });
  }
  marker.__popupHtml = nextHtml;
  if (
    marker.__hoverPopupActive
    && typeof marker.openPopup === "function"
    && !(typeof marker.isPopupOpen === "function" && marker.isPopupOpen())
  ) {
    marker.openPopup();
  }
}

function normalizeMapCoordinates(coords) {
  if (!Array.isArray(coords)) return [];
  return coords
    .map((item) => {
      if (!Array.isArray(item) || item.length < 2) return null;
      const lat = Number(item[0]);
      const lon = Number(item[1]);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
      return [lat, lon];
    })
    .filter((item) => Array.isArray(item));
}

function mapCoordinateSignature(coords) {
  return normalizeMapCoordinates(coords)
    .map(([lat, lon]) => `${lat.toFixed(5)}:${lon.toFixed(5)}`)
    .join("|");
}

function markTelemetryMapProgrammaticInteraction(durationMs = 900) {
  telemetryMapProgrammaticInteractionUntil = Date.now() + durationMs;
}

function setTelemetryMapManualControl(isManual) {
  telemetryMapManualControl = Boolean(isManual);
  if (telemetryMapMode) {
    telemetryMapMode.dataset.mode = telemetryMapManualControl ? "manual" : "auto";
    telemetryMapMode.textContent = telemetryMapManualControl ? "Vista manual" : "Seguimiento automático";
  }
}

function requestTelemetryMapRecenter() {
  setTelemetryMapManualControl(false);
  mapAutoFitDone = false;
  lastTelemetryBoundsSignature = "";
  updateMap(lastTelemetrySnapshot);
}

function mapFitOptions(map, { maxZoom = 16 } = {}) {
  const size = map && typeof map.getSize === "function" ? map.getSize() : { x: 0, y: 0 };
  const padX = Math.max(28, Math.min(96, Math.round((size.x || 0) * 0.08)));
  const padY = Math.max(28, Math.min(112, Math.round((size.y || 0) * 0.12)));
  return {
    paddingTopLeft: [padX, padY],
    paddingBottomRight: [padX, padY],
    maxZoom,
  };
}

function fitMapToCoordinates(map, coords, { maxZoom = 16, singleZoom = 15 } = {}) {
  if (!map || typeof window.L === "undefined") return;
  const points = normalizeMapCoordinates(coords);
  if (points.length === 0) return;

  if (points.length === 1) {
    map.setView(points[0], Math.min(maxZoom, singleZoom));
    return;
  }

  map.fitBounds(window.L.latLngBounds(points), mapFitOptions(map, { maxZoom }));
}

function setMapToEcuadorDefault(map) {
  if (!map || typeof map.setView !== "function") return;
  map.setView(ECUADOR_MAP_CENTER, ECUADOR_MAP_ZOOM);
}

function navigateToCameraView(cameraName) {
  if (!cameraName || !getCameraByName(cameraName)) return;
  const target = new URL("/camaras", window.location.origin);
  target.searchParams.set("camera", cameraName);
  window.location.assign(`${target.pathname}${target.search}`);
}

function selectCameraFromMap(cameraName, { focusMarker = false } = {}) {
  if (!cameraName || !getCameraByName(cameraName)) return;

  showTelemetryMapOverlay(cameraName, { sourceKind: "camera" });

  if (pageUsesDashboardCameraPreview()) {
    openDashboardPinnedCamera(cameraName);
    if (focusMarker) {
      focusLocation(cameraName);
    }
    return;
  }

  if (pageSupportsStreaming()) {
    openCamera(cameraName);
    if (focusMarker) {
      focusLocation(cameraName);
    }
    return;
  }

  activeCamera = cameraName;
  persistActiveCameraSelection(cameraName);
  updateFocusUi();
  refreshTelemetry();
  refreshEvents();
  if (telemetryMapOverlayBox) {
    return;
  }

  navigateToCameraView(cameraName);
}

function ensurePrimaryViewPlaceholder() {
  if (!primaryView) return null;

  let placeholder = document.getElementById("camera-empty-state");
  if (!placeholder) {
    placeholder = document.createElement("div");
    placeholder.id = "camera-empty-state";
    placeholder.className = "camera-empty-state";
    primaryView.appendChild(placeholder);
  }
  placeholder.textContent = EMPTY_CAMERA_MESSAGE;
  return placeholder;
}

function updatePrimaryViewPlaceholder() {
  if (!primaryView) return;
  const placeholder = ensurePrimaryViewPlaceholder();
  const showPlaceholder = !activeCamera;
  if (placeholder) {
    placeholder.hidden = !showPlaceholder;
  }
  primaryView.classList.toggle("is-empty", showPlaceholder);
}

function getDashboardPinnedCameraNames() {
  return dashboardPinnedCameraNames.filter((cameraName, index, source) => (
    Boolean(cameraName)
    && Boolean(getCameraByName(cameraName))
    && source.indexOf(cameraName) === index
  ));
}

function pageUsesDashboardMobilePanels() {
  return Boolean(
    document.body?.classList.contains("page-dashboard")
    && dashboardMobilePanelSwitcher
    && dashboardMobilePanelButtons.length > 0
  );
}

function syncDashboardMobilePanelButtons() {
  if (!pageUsesDashboardMobilePanels()) return;

  dashboardMobilePanelButtons.forEach((button) => {
    const buttonView = String(button.dataset.dashboardMobileView || "").trim().toLowerCase();
    const isActive = buttonView === dashboardMobileView;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
}

function setDashboardMobilePanel(nextView, { force = false } = {}) {
  if (!pageUsesDashboardMobilePanels()) return;

  const resolvedView = String(nextView || "").trim().toLowerCase() === "cameras" ? "cameras" : "map";
  if (!force && dashboardMobileView === resolvedView) return;

  dashboardMobileView = resolvedView;
  document.body.dataset.dashboardMobileView = resolvedView;
  syncDashboardMobilePanelButtons();
  scheduleViewportMetrics({ followTransition: true });
}

function pinDashboardCamera(cameraName) {
  if (!pageUsesDashboardCameraPreview() || !cameraName || !getCameraByName(cameraName)) return;

  const nextNames = getDashboardPinnedCameraNames();
  if (!nextNames.includes(cameraName)) {
    nextNames.push(cameraName);
  }
  dashboardPinnedCameraNames = nextNames;
  activeCamera = cameraName;
}

function getActiveCameraHost() {
  if (primaryView) {
    return primaryView;
  }
  if (pageUsesDashboardCameraPreview()) {
    return dashboardCameraPreviewStage;
  }
  return null;
}

function updateDashboardCameraPreview() {
  if (!pageUsesDashboardCameraPreview()) return;

  const pinnedCameraNames = getDashboardPinnedCameraNames();
  const pinnedCount = pinnedCameraNames.length;
  const hasActiveCamera = pinnedCount > 0;
  if (dashboardCameraPreview) {
    dashboardCameraPreview.classList.toggle("is-active", hasActiveCamera);
  }
  if (dashboardCameraPreviewName) {
    dashboardCameraPreviewName.textContent = pinnedCount === 1
      ? getCameraDisplayName(String(pinnedCameraNames[0] || ""), { uppercase: true })
      : pinnedCount > 1
        ? `${pinnedCount} cámaras fijadas`
      : "Sin cámara fijada";
  }
  if (dashboardCameraPreviewEmpty) {
    dashboardCameraPreviewEmpty.hidden = hasActiveCamera;
  }
  if (dashboardCameraPreviewStage) {
    dashboardCameraPreviewStage.hidden = !hasActiveCamera;
    dashboardCameraPreviewStage.classList.toggle("has-multiple", pinnedCount > 1);
  }
  if (dashboardCameraPreviewClose) {
    dashboardCameraPreviewClose.textContent = pinnedCount > 1 ? "Vaciar" : "Cerrar";
    dashboardCameraPreviewClose.hidden = !hasActiveCamera;
  }
}

function setCameraRegisterFeedback(message, tone = "info") {
  if (!cameraRegisterFeedback) return;
  if (!message) {
    cameraRegisterFeedback.hidden = true;
    cameraRegisterFeedback.textContent = "";
    delete cameraRegisterFeedback.dataset.tone;
    return;
  }

  cameraRegisterFeedback.hidden = false;
  cameraRegisterFeedback.textContent = message;
  if (tone === "success" || tone === "error") {
    cameraRegisterFeedback.dataset.tone = tone;
  } else {
    delete cameraRegisterFeedback.dataset.tone;
  }
}

function setVehicleRegisterFeedback(message, tone = "info") {
  if (!vehicleRegisterFeedback) return;
  if (!message) {
    vehicleRegisterFeedback.hidden = true;
    vehicleRegisterFeedback.textContent = "";
    delete vehicleRegisterFeedback.dataset.tone;
    return;
  }

  vehicleRegisterFeedback.hidden = false;
  vehicleRegisterFeedback.textContent = message;
  if (tone === "success" || tone === "error") {
    vehicleRegisterFeedback.dataset.tone = tone;
  } else {
    delete vehicleRegisterFeedback.dataset.tone;
  }
}

function setUserAdminFeedback(message, tone = "info") {
  if (!userAdminFeedback) return;
  if (!message) {
    userAdminFeedback.hidden = true;
    userAdminFeedback.textContent = "";
    delete userAdminFeedback.dataset.tone;
    return;
  }

  userAdminFeedback.hidden = false;
  userAdminFeedback.textContent = message;
  if (tone === "success" || tone === "error") {
    userAdminFeedback.dataset.tone = tone;
  } else {
    delete userAdminFeedback.dataset.tone;
  }
}

function setRoleAdminFeedback(message, tone = "info") {
  if (!roleAdminFeedback) return;
  if (!message) {
    roleAdminFeedback.hidden = true;
    roleAdminFeedback.textContent = "";
    delete roleAdminFeedback.dataset.tone;
    return;
  }

  roleAdminFeedback.hidden = false;
  roleAdminFeedback.textContent = message;
  if (tone === "success" || tone === "error") {
    roleAdminFeedback.dataset.tone = tone;
  } else {
    delete roleAdminFeedback.dataset.tone;
  }
}

function setOrganizationAdminFeedback(message, tone = "info") {
  if (!organizationAdminFeedback) return;
  if (!message) {
    organizationAdminFeedback.hidden = true;
    organizationAdminFeedback.textContent = "";
    delete organizationAdminFeedback.dataset.tone;
    return;
  }

  organizationAdminFeedback.hidden = false;
  organizationAdminFeedback.textContent = message;
  if (tone === "success" || tone === "error") {
    organizationAdminFeedback.dataset.tone = tone;
  } else {
    delete organizationAdminFeedback.dataset.tone;
  }
}

function setCameraAdminFeedback(message, tone = "info") {
  if (!cameraAdminFeedback) return;
  if (!message) {
    cameraAdminFeedback.hidden = true;
    cameraAdminFeedback.textContent = "";
    delete cameraAdminFeedback.dataset.tone;
    return;
  }

  cameraAdminFeedback.hidden = false;
  cameraAdminFeedback.textContent = message;
  if (tone === "success" || tone === "error") {
    cameraAdminFeedback.dataset.tone = tone;
  } else {
    delete cameraAdminFeedback.dataset.tone;
  }
}

function setPlatePreviewStatus(message, tone = "info") {
  if (!platePreviewStatus) return;
  platePreviewStatus.textContent = String(message || "").trim();
  if (tone === "success" || tone === "error") {
    platePreviewStatus.dataset.tone = tone;
  } else {
    delete platePreviewStatus.dataset.tone;
  }
}

function syncPlatePreviewChoiceState(selectedPlate) {
  if (!platePreviewChoices.length) return;
  const activeValue = String(selectedPlate || "").trim();
  platePreviewChoices.forEach((choice) => {
    const isActive = String(choice.dataset.plateValue || "").trim() === activeValue;
    choice.classList.toggle("is-active", isActive);
    choice.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
}

function formatPlateDetailLabel(key) {
  const labels = {
    timestamp: "Timestamp",
    cam_id: "Camara",
    plate: "Placa",
    crop_path: "Crop",
    vehicle_info: "Vehiculo",
    placa: "Placa",
    marca: "Marca",
    modelo: "Modelo",
    clase: "Clase",
    anioModelo: "Anio modelo",
    servicio: "Servicio",
    paisFabricacion: "Pais fabricacion",
    dueño: "Dueno",
  };
  if (labels[key]) return labels[key];
  return String(key || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatPlateDetailValue(key, value) {
  if (value === null || value === undefined || value === "") return "";
  if (key === "timestamp" && Number.isFinite(Number(value))) {
    const date = new Date(Number(value) * 1000);
    if (!Number.isNaN(date.getTime())) {
      return `${date.toLocaleString()} (${value})`;
    }
  }
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch (error) {
      return String(value);
    }
  }
  return String(value);
}

function appendPlateDetailRow(container, key, value) {
  const formattedValue = formatPlateDetailValue(key, value);
  if (!formattedValue) return;

  const row = document.createElement("div");
  row.className = "plate-file-row";
  if (key === "crop_path") {
    row.classList.add("plate-file-row-image");
  }

  const label = document.createElement("span");
  label.textContent = formatPlateDetailLabel(key);

  const content = document.createElement("strong");
  content.textContent = formattedValue;

  row.append(label);
  if (key === "crop_path") {
    const image = document.createElement("img");
    image.className = "plate-crop-image";
    image.src = `/api/plate-crop-image?path=${encodeURIComponent(formattedValue)}`;
    image.alt = "Imagen del crop de placa";
    image.loading = "lazy";
    image.decoding = "async";
    image.addEventListener("error", () => {
      image.hidden = true;
    });
    row.append(image);
  }
  row.append(content);
  container.append(row);
}

function renderPlateFileContent(detail, detailError) {
  if (!plateFileContent) return;
  plateFileContent.replaceChildren();

  const errorMessage = String(detailError || "").trim();
  if (errorMessage) {
    const error = document.createElement("p");
    error.className = "plate-file-empty";
    error.textContent = errorMessage;
    plateFileContent.append(error);
    return;
  }

  if (!detail || typeof detail !== "object" || Array.isArray(detail)) {
    const empty = document.createElement("p");
    empty.className = "plate-file-empty";
    empty.textContent = "Sin informacion disponible para este crop.";
    plateFileContent.append(empty);
    return;
  }

  const primarySection = document.createElement("div");
  primarySection.className = "plate-file-section";

  Object.entries(detail).forEach(([key, value]) => {
    if (value && typeof value === "object" && !Array.isArray(value)) return;
    appendPlateDetailRow(primarySection, key, value);
  });

  if (primarySection.children.length) {
    plateFileContent.append(primarySection);
  }

  Object.entries(detail).forEach(([key, value]) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) return;

    const section = document.createElement("div");
    section.className = "plate-file-section";

    const title = document.createElement("span");
    title.className = "plate-file-section-title";
    title.textContent = formatPlateDetailLabel(key);
    section.append(title);

    Object.entries(value).forEach(([nestedKey, nestedValue]) => {
      appendPlateDetailRow(section, nestedKey, nestedValue);
    });

    plateFileContent.append(section);
  });
}

function renderPlateFileLoading() {
  if (!plateFileContent) return;
  plateFileContent.replaceChildren();
  const loading = document.createElement("p");
  loading.className = "plate-file-empty";
  loading.textContent = "Cargando informacion del crop...";
  plateFileContent.append(loading);
}

async function fetchPlateFileDetail(nextFile) {
  const response = await fetch("/api/plate-file-detail", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json",
    },
    body: JSON.stringify({ file: nextFile }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload.ok) {
    throw new Error(payload.message || payload.error || "No se pudo leer el crop.");
  }
  return payload;
}

function openPlateFileModal(plate) {
  if (!plateFileModal) return;
  const plateValue = String(plate || "").trim();
  if (plateFilePlate) {
    plateFilePlate.textContent = plateValue || "Sin placa";
  }
  renderPlateFileLoading();
  plateFileModal.hidden = false;
  document.body.classList.add("is-plate-file-modal-open");
  if (plateFileClose) {
    plateFileClose.focus();
  }
}

function closePlateFileModal() {
  if (!plateFileModal) return;
  plateFileModal.hidden = true;
  document.body.classList.remove("is-plate-file-modal-open");
}

async function setPlatePreviewSelection(nextPlate, nextFile = "") {
  if (!platePreviewOutput) return;
  const value = String(nextPlate || "").trim();
  if (!value) return;

  platePreviewOutput.value = value;
  syncPlatePreviewChoiceState(value);
  openPlateFileModal(value);

  const fileValue = String(nextFile || "").trim();
  if (!fileValue) {
    renderPlateFileContent(null, "Sin archivo asociado.");
    setPlatePreviewStatus("Sin archivo asociado.", "error");
    resetPlatePreviewStatus();
    return;
  }

  const requestToken = (plateFileRequestToken += 1);
  setPlatePreviewStatus("Cargando detalle del crop...");

  try {
    const payload = await fetchPlateFileDetail(fileValue);
    if (requestToken !== plateFileRequestToken) return;
    renderPlateFileContent(payload.detail, "");
    setPlatePreviewStatus("Detalle cargado.");
    resetPlatePreviewStatus();
  } catch (error) {
    if (requestToken !== plateFileRequestToken) return;
    renderPlateFileContent(null, error instanceof Error ? error.message : "No se pudo leer el crop.");
    setPlatePreviewStatus("No se pudo leer el crop.", "error");
    resetPlatePreviewStatus(2600);
  }
}

function resetPlatePreviewStatus(delayMs = 2200) {
  if (platePreviewStatusTimerId) {
    clearTimeout(platePreviewStatusTimerId);
  }
  platePreviewStatusTimerId = window.setTimeout(() => {
    platePreviewStatusTimerId = null;
    setPlatePreviewStatus("Selecciona y copia la placa.");
  }, delayMs);
}

function copyPlatePreviewTextFallback() {
  if (!platePreviewOutput) return false;
  try {
    platePreviewOutput.focus();
    platePreviewOutput.select();
    platePreviewOutput.setSelectionRange(0, platePreviewOutput.value.length);
    return Boolean(document.execCommand("copy"));
  } catch (error) {
    return false;
  }
}

async function copyPlatePreviewText() {
  if (!platePreviewOutput || !platePreviewCopy) return;

  const text = String(platePreviewOutput.value || "").trim();
  if (!text) {
    setPlatePreviewStatus("Sin placa", "error");
    resetPlatePreviewStatus();
    return;
  }

  const originalLabel = platePreviewCopy.textContent || "Copiar";
  platePreviewCopy.disabled = true;
  platePreviewCopy.textContent = "Copiando...";

  try {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function" && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else if (!copyPlatePreviewTextFallback()) {
      throw new Error("copy_failed");
    }

    setPlatePreviewStatus("Placa copiada", "success");
    platePreviewCopy.textContent = "Copiado";
    resetPlatePreviewStatus();
  } catch (error) {
    setPlatePreviewStatus("No se pudo copiar", "error");
    resetPlatePreviewStatus(2600);
  } finally {
    window.setTimeout(() => {
      platePreviewCopy.disabled = false;
      platePreviewCopy.textContent = originalLabel;
    }, 900);
  }
}

function syncCameraAdminQuickActions(isEditing) {
  const editing = Boolean(isEditing);
  if (cameraAdminReset) {
    const isActive = !editing && cameraAdminCreationMode === "camera";
    cameraAdminReset.classList.toggle("is-active", isActive);
    cameraAdminReset.setAttribute("aria-pressed", isActive ? "true" : "false");
  }
  if (cameraAdminRbox) {
    const isActive = !editing && cameraAdminCreationMode === "rbox";
    cameraAdminRbox.classList.toggle("is-active", isActive);
    cameraAdminRbox.setAttribute("aria-pressed", isActive ? "true" : "false");
  }
}

function normalizeAccessRoleValue(role) {
  const normalized = String(role || "").trim().toLowerCase().replace(/[\s-]+/g, "_");
  switch (normalized) {
    case "developer":
      return "desarrollador";
    case "engineer":
    case "enginer":
    case "engenir":
      return "ingeniero";
    case "client":
    case "cliente_normal":
      return "cliente";
    default:
      return normalized;
  }
}

function isCameraRegisterModalOpen() {
  return Boolean(cameraRegisterModal && !cameraRegisterModal.hidden);
}

function isVehicleRegisterModalOpen() {
  return Boolean(vehicleRegisterModal && !vehicleRegisterModal.hidden);
}

function isCameraAdminMapModalOpen() {
  return Boolean(cameraAdminMapModal && !cameraAdminMapModal.hidden);
}

function syncGlobalModalState() {
  const hasOpenModal = (
    isCameraRegisterModalOpen()
    || isCameraAdminMapModalOpen()
    || isVehicleRegisterModalOpen()
  );
  document.body.classList.toggle("is-modal-open", hasOpenModal);
}

function formatCoordinate(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "--";
  return numeric.toFixed(6);
}

function updateCameraRegisterLocationSummary() {
  if (!cameraRegisterLocation) return;
  const lat = cameraRegisterLat ? Number(cameraRegisterLat.value) : NaN;
  const lon = cameraRegisterLon ? Number(cameraRegisterLon.value) : NaN;
  if (Number.isFinite(lat) && Number.isFinite(lon)) {
    cameraRegisterLocation.textContent = `Ubicación seleccionada: ${formatCoordinate(lat)}, ${formatCoordinate(lon)}`;
    return;
  }
  cameraRegisterLocation.textContent = "Haz clic sobre el mapa o escribe las coordenadas manualmente.";
}

function placeCameraRegisterMarker(lat, lon, { center = true } = {}) {
  if (!registerMapInstance || typeof window.L === "undefined") return;
  const nextLat = Number(lat);
  const nextLon = Number(lon);
  if (!Number.isFinite(nextLat) || !Number.isFinite(nextLon)) return;

  if (!registerMapMarker) {
    registerMapMarker = window.L.circleMarker([nextLat, nextLon], {
      radius: 11,
      color: "#f97316",
      weight: 3,
      fillColor: "#f97316",
      fillOpacity: 0.96,
      opacity: 1,
    }).addTo(registerMapInstance);
  } else {
    registerMapMarker.setLatLng([nextLat, nextLon]);
  }

  if (center) {
    registerMapInstance.setView([nextLat, nextLon], Math.max(registerMapInstance.getZoom(), 16));
  }
}

function clearCameraRegisterMarker() {
  if (!registerMapInstance || !registerMapMarker) return;
  registerMapInstance.removeLayer(registerMapMarker);
  registerMapMarker = null;
}

function setCameraRegisterCoordinates(lat, lon, { center = true } = {}) {
  if (cameraRegisterLat) {
    cameraRegisterLat.value = Number(lat).toFixed(6);
  }
  if (cameraRegisterLon) {
    cameraRegisterLon.value = Number(lon).toFixed(6);
  }
  updateCameraRegisterLocationSummary();
  placeCameraRegisterMarker(lat, lon, { center });
}

function syncCameraRegisterMarkerFromInputs({ center = false } = {}) {
  const lat = cameraRegisterLat ? Number(cameraRegisterLat.value) : NaN;
  const lon = cameraRegisterLon ? Number(cameraRegisterLon.value) : NaN;
  updateCameraRegisterLocationSummary();
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
    clearCameraRegisterMarker();
    return;
  }
  placeCameraRegisterMarker(lat, lon, { center });
}

async function seedCameraRegisterMapViewport() {
  if (!registerMapInstance || registerMapViewportLoaded) return;
  registerMapViewportLoaded = true;
  try {
    const telemetry = await fetchJson("/api/telemetry", { timeoutMs: 4000 });
    const bounds = Array.isArray(telemetry)
      ? telemetry
        .filter((item) => Number.isFinite(Number(item.lat)) && Number.isFinite(Number(item.lon)))
        .map((item) => [Number(item.lat), Number(item.lon)])
      : [];
    registerMapSeedCoordinates = bounds;
    if (bounds.length > 0) {
      fitMapToCoordinates(registerMapInstance, bounds, {
        maxZoom: 16,
        singleZoom: 15,
      });
    } else {
      setMapToEcuadorDefault(registerMapInstance);
    }
  } catch (error) {
    setMapToEcuadorDefault(registerMapInstance);
  }
}

function ensureCameraRegisterMap() {
  if (!cameraRegisterMap) return false;
  if (registerMapInstance) {
    syncCameraRegisterMarkerFromInputs();
    return true;
  }
  if (typeof window.L === "undefined") {
    cameraRegisterMap.innerHTML = '<div class="empty-state">Mapa no disponible. Ingresa la latitud y longitud manualmente.</div>';
    return false;
  }

  registerMapInstance = window.L.map(cameraRegisterMap, {
    zoomControl: true,
    attributionControl: true,
    maxZoom: CAMERA_PICKER_MAX_ZOOM,
  });
  setMapToEcuadorDefault(registerMapInstance);

  addStreetTileLayer(registerMapInstance);

  registerMapInstance.on("click", (event) => {
    setCameraRegisterCoordinates(event.latlng.lat, event.latlng.lng);
    setCameraRegisterFeedback("");
  });

  seedCameraRegisterMapViewport();
  syncCameraRegisterMarkerFromInputs();
  return true;
}

function resetCameraRegisterState() {
  if (cameraRegisterForm) {
    cameraRegisterForm.reset();
  }
  clearCameraRegisterMarker();
  updateCameraRegisterLocationSummary();
  setCameraRegisterFeedback("");
}

function openCameraRegisterModal() {
  if (!cameraRegisterModal) return;
  if (cameraAdminForm) {
    resetCameraAdminForm({ creationMode: "camera" });
    void refreshUserAdmin({ preserveDraft: false });
    setCameraAdminFeedback("");
  } else {
    setCameraRegisterFeedback("");
  }
  cameraRegisterModal.hidden = false;
  syncGlobalModalState();
  updateCameraRegisterLocationSummary();
  ensureCameraRegisterMap();
  window.requestAnimationFrame(() => {
    if (registerMapInstance) {
      try {
        registerMapInstance.invalidateSize();
      } catch (error) {}
    }
    if (cameraAdminName) {
      cameraAdminName.focus();
      cameraAdminName.select();
      return;
    }
    if (cameraRegisterName) {
      cameraRegisterName.focus();
      cameraRegisterName.select();
    }
  });
}

function closeCameraRegisterModal() {
  if (!cameraRegisterModal) return;
  if (isCameraAdminMapModalOpen()) {
    closeCameraAdminMapModal();
  }
  cameraRegisterModal.hidden = true;
  syncGlobalModalState();
  setCameraRegisterFeedback("");
  setCameraAdminFeedback("");
}

function getCameraAdminInputCoordinates() {
  const lat = cameraAdminLat ? Number(cameraAdminLat.value) : NaN;
  const lon = cameraAdminLon ? Number(cameraAdminLon.value) : NaN;
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
    return null;
  }
  if (Math.abs(lat) < 0.000001 && Math.abs(lon) < 0.000001) {
    return null;
  }
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
    return null;
  }
  return { lat, lon };
}

function updateCameraAdminMapSummary() {
  if (!cameraAdminMapSummary) return;
  const coordinates = getCameraAdminInputCoordinates();
  if (coordinates) {
    cameraAdminMapSummary.textContent = `Ubicación actual: ${formatCoordinate(coordinates.lat)}, ${formatCoordinate(coordinates.lon)}`;
    return;
  }
  cameraAdminMapSummary.textContent = "Aún no se ha seleccionado una ubicación en el mapa.";
}

function updateCameraAdminMapLocationSummary() {
  if (!cameraAdminMapLocation) return;
  if (cameraAdminMapDraftLocation) {
    cameraAdminMapLocation.textContent = `Ubicación seleccionada: ${formatCoordinate(cameraAdminMapDraftLocation.lat)}, ${formatCoordinate(cameraAdminMapDraftLocation.lon)}`;
    return;
  }
  cameraAdminMapLocation.textContent = "Haz clic sobre el mapa para elegir la posición exacta.";
}

function placeCameraAdminMapMarker(lat, lon, { center = true } = {}) {
  if (!cameraAdminMapInstance || typeof window.L === "undefined") return;
  const nextLat = Number(lat);
  const nextLon = Number(lon);
  if (!Number.isFinite(nextLat) || !Number.isFinite(nextLon)) return;

  if (!cameraAdminMapMarker) {
    cameraAdminMapMarker = window.L.circleMarker([nextLat, nextLon], {
      radius: 11,
      color: "#f97316",
      weight: 3,
      fillColor: "#f97316",
      fillOpacity: 0.96,
      opacity: 1,
    }).addTo(cameraAdminMapInstance);
  } else {
    cameraAdminMapMarker.setLatLng([nextLat, nextLon]);
  }

  if (center) {
    cameraAdminMapInstance.setView([nextLat, nextLon], Math.max(cameraAdminMapInstance.getZoom(), 16));
  }
}

function clearCameraAdminMapMarker() {
  if (!cameraAdminMapInstance || !cameraAdminMapMarker) return;
  cameraAdminMapInstance.removeLayer(cameraAdminMapMarker);
  cameraAdminMapMarker = null;
}

function setCameraAdminMapDraftLocation(lat, lon, { center = true } = {}) {
  const nextLat = Number(lat);
  const nextLon = Number(lon);
  if (!Number.isFinite(nextLat) || !Number.isFinite(nextLon)) return;
  cameraAdminMapDraftLocation = { lat: nextLat, lon: nextLon };
  updateCameraAdminMapLocationSummary();
  placeCameraAdminMapMarker(nextLat, nextLon, { center });
  if (cameraAdminMapApply) {
    cameraAdminMapApply.disabled = false;
  }
}

function resetCameraAdminMapDraftFromInputs({ center = false } = {}) {
  const coordinates = getCameraAdminInputCoordinates();
  cameraAdminMapDraftLocation = coordinates;
  updateCameraAdminMapLocationSummary();
  if (!coordinates) {
    clearCameraAdminMapMarker();
    if (cameraAdminMapApply) {
      cameraAdminMapApply.disabled = true;
    }
    return;
  }
  placeCameraAdminMapMarker(coordinates.lat, coordinates.lon, { center });
  if (cameraAdminMapApply) {
    cameraAdminMapApply.disabled = false;
  }
}

function seedCameraAdminMapViewport() {
  if (!cameraAdminMapInstance || cameraAdminMapViewportLoaded) return;
  cameraAdminMapViewportLoaded = true;
  const bounds = lastLocationCoordinates.length > 0
    ? lastLocationCoordinates
    : lastTelemetryCoordinates.length > 0
      ? lastTelemetryCoordinates
      : [];
  cameraAdminMapSeedCoordinates = bounds;
  if (bounds.length > 0) {
    fitMapToCoordinates(cameraAdminMapInstance, bounds, {
      maxZoom: 16,
      singleZoom: 15,
    });
  } else {
    setMapToEcuadorDefault(cameraAdminMapInstance);
  }
}

function ensureCameraAdminMap() {
  if (!cameraAdminMap) return false;
  if (cameraAdminMapInstance) {
    resetCameraAdminMapDraftFromInputs();
    return true;
  }
  if (typeof window.L === "undefined") {
    cameraAdminMap.innerHTML = '<div class="empty-state">Mapa no disponible. Ingresa la latitud y longitud manualmente.</div>';
    return false;
  }

  cameraAdminMapInstance = window.L.map(cameraAdminMap, {
    zoomControl: true,
    attributionControl: true,
    maxZoom: CAMERA_PICKER_MAX_ZOOM,
  });
  setMapToEcuadorDefault(cameraAdminMapInstance);

  addStreetTileLayer(cameraAdminMapInstance);
  cameraAdminMapInstance.on("click", (event) => {
    setCameraAdminMapDraftLocation(event.latlng.lat, event.latlng.lng);
    setCameraAdminFeedback("");
  });

  seedCameraAdminMapViewport();
  resetCameraAdminMapDraftFromInputs();
  return true;
}

function openCameraAdminMapModal() {
  if (!cameraAdminMapModal) return;
  if (!cameraAdminUsesRtspAssistantType()) {
    setCameraAdminFeedback("El selector de mapa solo aplica para cámaras fijas o PTZ.", "info");
    return;
  }
  cameraAdminMapModal.hidden = false;
  syncGlobalModalState();
  updateCameraAdminMapSummary();
  ensureCameraAdminMap();
  resetCameraAdminMapDraftFromInputs();
  window.requestAnimationFrame(() => {
    if (cameraAdminMapInstance) {
      try {
        cameraAdminMapInstance.invalidateSize();
        if (cameraAdminMapDraftLocation) {
          fitMapToCoordinates(cameraAdminMapInstance, [[cameraAdminMapDraftLocation.lat, cameraAdminMapDraftLocation.lon]], {
            maxZoom: 17,
            singleZoom: 17,
          });
        } else if (cameraAdminMapSeedCoordinates.length > 0) {
          fitMapToCoordinates(cameraAdminMapInstance, cameraAdminMapSeedCoordinates, {
            maxZoom: 16,
            singleZoom: 15,
          });
        } else {
          setMapToEcuadorDefault(cameraAdminMapInstance);
        }
      } catch (error) {}
    }
    if (cameraAdminMapApply) {
      cameraAdminMapApply.focus();
    }
  });
}

function closeCameraAdminMapModal() {
  if (!cameraAdminMapModal) return;
  cameraAdminMapModal.hidden = true;
  syncGlobalModalState();
}

function applyCameraAdminMapSelection() {
  if (!cameraAdminMapDraftLocation) {
    setCameraAdminFeedback("Selecciona un punto en el mapa antes de continuar.", "error");
    return;
  }
  if (cameraAdminLat) {
    cameraAdminLat.value = cameraAdminMapDraftLocation.lat.toFixed(6);
  }
  if (cameraAdminLon) {
    cameraAdminLon.value = cameraAdminMapDraftLocation.lon.toFixed(6);
  }
  updateCameraAdminMapSummary();
  setCameraAdminFeedback("");
  closeCameraAdminMapModal();
}

function normalizeVehicleTypeCode(value) {
  return String(value || "").trim().toLowerCase();
}

function isDroneVehicleTypeCode(value) {
  const normalized = normalizeVehicleTypeCode(value);
  return normalized === "dron" || normalized.startsWith("drone");
}

function getVehicleTypeCatalog() {
  const catalog = Array.isArray(vehicleRegistryOptionCatalog.vehicle_types)
    ? vehicleRegistryOptionCatalog.vehicle_types
    : [];
  if (catalog.length > 0) {
    return catalog;
  }
  return [
    { id: 1, codigo: "drone_robiotec", nombre: "Dron Robiotec", categoria: "dron" },
    { id: 2, codigo: "drone_dji", nombre: "Dron DJI", categoria: "dron" },
    { id: 3, codigo: "auto", nombre: "Vehículo terrestre", categoria: "automovil" },
  ];
}

function getVehicleRegisterSelectedCameraLinks() {
  if (!vehicleRegisterCameraList) return [];
  return Array.from(vehicleRegisterCameraList.querySelectorAll("[data-vehicle-camera-checkbox]"))
    .filter((input) => input instanceof HTMLInputElement && input.checked)
    .map((input) => {
      const cameraId = Number(input.getAttribute("data-vehicle-camera-checkbox") || 0);
      const positionInput = vehicleRegisterCameraList.querySelector(
        `[data-vehicle-camera-position="${String(cameraId)}"]`,
      );
      return {
        camera_id: cameraId,
        position: positionInput instanceof HTMLInputElement ? positionInput.value.trim() : "",
      };
    })
    .filter((item) => Number.isInteger(item.camera_id) && item.camera_id > 0);
}

function buildVehicleRegisterCameraSelectionMap(source) {
  const selection = new Map();
  const links = Array.isArray(source)
    ? source
    : (source && Array.isArray(source.camera_links) ? source.camera_links : []);
  links.forEach((link) => {
    const cameraId = Number(link && (link.camera_id || link.camara_id) || 0);
    if (!Number.isInteger(cameraId) || cameraId <= 0) return;
    selection.set(cameraId, {
      position: String(link && (link.position || link.posicion) || "").trim(),
    });
  });
  return selection;
}

function syncVehicleRegisterCatalogOptions({ selectedLinks } = {}) {
  const organizations = Array.isArray(vehicleRegistryOptionCatalog.organizations)
    ? vehicleRegistryOptionCatalog.organizations
    : [];
  const owners = Array.isArray(vehicleRegistryOptionCatalog.owners)
    ? vehicleRegistryOptionCatalog.owners
    : [];
  const vehicleTypes = getVehicleTypeCatalog();
  const nextOrganizationValue = String(
    (vehicleRegisterOrganization && vehicleRegisterOrganization.value)
    || (organizations[0] && organizations[0].id)
    || "",
  );
  const nextOwnerValue = String(
    (vehicleRegisterOwner && vehicleRegisterOwner.value)
    || (owners[0] && owners[0].id)
    || "",
  );
  const nextVehicleType = normalizeVehicleTypeCode(
    (vehicleRegisterType && vehicleRegisterType.value)
    || (vehicleTypes[0] && vehicleTypes[0].codigo)
    || "drone_robiotec",
  );

  if (vehicleRegisterOrganization) {
    vehicleRegisterOrganization.innerHTML = organizations.length > 0
      ? organizations.map((organization) => `
          <option value="${escapeHtml(String(organization.id || ""))}">
            ${escapeHtml(String(organization.nombre || `Organización ${organization.id || ""}`))}
          </option>
        `).join("")
      : '<option value="">Sin organizaciones disponibles</option>';
    vehicleRegisterOrganization.value = nextOrganizationValue;
  }

  if (vehicleRegisterOwner) {
    vehicleRegisterOwner.innerHTML = owners.length > 0
      ? owners.map((owner) => `
          <option value="${escapeHtml(String(owner.id || ""))}">
            ${escapeHtml(String(owner.display_name || owner.usuario || `Usuario ${owner.id || ""}`))}
          </option>
        `).join("")
      : '<option value="">Sin propietarios disponibles</option>';
    vehicleRegisterOwner.value = nextOwnerValue;
  }

  if (vehicleRegisterType) {
    vehicleRegisterType.innerHTML = vehicleTypes.map((type) => `
      <option value="${escapeHtml(String(type.codigo || ""))}">
        ${escapeHtml(String(type.nombre || type.codigo || ""))}
      </option>
    `).join("");
    vehicleRegisterType.value = nextVehicleType;
  }

  renderVehicleRegisterCameraList(selectedLinks);
}

function renderVehicleRegisterCameraList(selectedLinks = null) {
  if (!vehicleRegisterCameraList) return;
  const cameras = Array.isArray(vehicleRegistryOptionCatalog.cameras)
    ? vehicleRegistryOptionCatalog.cameras
    : [];
  const selection = selectedLinks instanceof Map
    ? selectedLinks
    : buildVehicleRegisterCameraSelectionMap(selectedLinks || getVehicleRegisterSelectedCameraLinks());
  const isDrone = isDroneVehicleTypeCode(vehicleRegisterType && vehicleRegisterType.value);
  const expectedType = isDrone ? "drone" : "vehicle";
  const compatibleCameras = cameras.filter((camera) => {
    const typeCode = String(camera && camera.tipo_camara_codigo || "").trim().toLowerCase();
    return typeCode === expectedType;
  });

  if (compatibleCameras.length === 0) {
    vehicleRegisterCameraList.innerHTML = '<div class="empty-state">No hay cámaras compatibles disponibles para este tipo de vehículo.</div>';
    return;
  }

  vehicleRegisterCameraList.innerHTML = compatibleCameras.map((camera) => {
    const cameraId = Number(camera && camera.id || 0);
    const assignedVehicleId = String(camera && camera.vehiculo_id || "").trim();
    const isCurrentlyAssignedHere = Boolean(
      assignedVehicleId
      && editingVehicleRegistrationId
      && assignedVehicleId === String(editingVehicleRegistrationId),
    );
    const selectionState = selection.get(cameraId) || null;
    const checked = Boolean(selectionState);
    const assignmentNote = assignedVehicleId && !isCurrentlyAssignedHere
      ? `Actualmente asociada a ${String(camera.vehiculo_nombre || `vehículo ${assignedVehicleId}`).trim()}. Si la marcas, se reasignará.`
      : "Disponible para este vehículo.";
    return `
      <article class="vehicle-register-camera-item ${checked ? "is-selected" : ""}">
        <label class="vehicle-register-camera-head">
          <input
            type="checkbox"
            data-vehicle-camera-checkbox="${escapeHtml(String(cameraId))}"
            ${checked ? "checked" : ""}
          />
          <span>
            <strong>${escapeHtml(String(camera.nombre || `Cámara ${cameraId}`).trim())}</strong>
            <small>${escapeHtml(String(camera.tipo_camara_nombre || camera.tipo_camara_codigo || "").trim())}</small>
          </span>
        </label>
        <p>${escapeHtml(assignmentNote)}</p>
        <input
          class="vehicle-register-camera-position"
          type="text"
          placeholder="Frontal, cabina, lateral..."
          data-vehicle-camera-position="${escapeHtml(String(cameraId))}"
          value="${escapeHtml(selectionState ? selectionState.position : "")}"
          ${checked ? "" : "disabled"}
        />
      </article>
    `;
  }).join("");
}

async function refreshVehicleRegistryFormOptions() {
  if (!vehicleRegisterForm) return;
  try {
    const options = await fetchJson("/api/vehicle-form-options", { timeoutMs: 6000 });
    if (vehicleRegisterOpen) {
      vehicleRegisterOpen.hidden = false;
    }
    vehicleRegistryOptionCatalog = {
      organizations: Array.isArray(options && options.organizations) ? options.organizations : [],
      owners: Array.isArray(options && options.owners) ? options.owners : [],
      vehicle_types: Array.isArray(options && options.vehicle_types) ? options.vehicle_types : [],
      cameras: Array.isArray(options && options.cameras) ? options.cameras : [],
    };
    vehicleApiDefaults = {
      default_drone_device_id: String(
        options
        && options.api_defaults
        && options.api_defaults.default_drone_device_id
        || "drone",
      ).trim() || "drone",
    };
    syncVehicleRegisterCatalogOptions();
    updateVehicleRegisterTypeCopy();
  } catch (error) {
    if (vehicleRegisterOpen) {
      vehicleRegisterOpen.hidden = String(error && error.message || "").trim() === "forbidden";
    }
    vehicleRegistryOptionCatalog = {
      organizations: [],
      owners: [],
      vehicle_types: getVehicleTypeCatalog(),
      cameras: [],
    };
    syncVehicleRegisterCatalogOptions();
  }
}

function updateVehicleRegisterTypeCopy() {
  const vehicleType = normalizeVehicleTypeCode(vehicleRegisterType && vehicleRegisterType.value || "drone_robiotec");
  const isDrone = isDroneVehicleTypeCode(vehicleType);
  const availableTelemetryModes = ["manual", "api"];
  const currentTelemetryMode = String(vehicleRegisterTelemetryMode && vehicleRegisterTelemetryMode.value || "manual").trim().toLowerCase();
  const telemetryMode = availableTelemetryModes.includes(currentTelemetryMode)
    ? currentTelemetryMode
    : "manual";

  if (vehicleRegisterIdentifierLabel) {
    vehicleRegisterIdentifierLabel.textContent = isDrone ? "Serie o matrícula" : "Placa o código";
  }
  if (vehicleRegisterIdentifier) {
    vehicleRegisterIdentifier.placeholder = isDrone ? "DRN-001" : "ABC-1234";
  }
  if (vehicleRegisterIdentifierHelp) {
    vehicleRegisterIdentifierHelp.textContent = isDrone
      ? "Para drones puedes usar serie, matrícula o código interno."
      : "Para automóviles usa la placa, unidad o código de identificación.";
  }
  if (vehicleRegisterTypeHelp) {
    vehicleRegisterTypeHelp.textContent = isDrone
      ? "Modo dron activo: el identificador se guardará como serie o código operativo del dron."
      : "Modo vehículo terrestre activo: el identificador se guardará como placa o código de unidad.";
  }
  if (vehicleRegisterTelemetryMode) {
    const options = availableTelemetryModes.map((value) => {
      const label = value === "api"
          ? "API GPS"
          : "Sin telemetría";
      return `<option value="${value}">${label}</option>`;
    }).join("");
    if (vehicleRegisterTelemetryMode.innerHTML !== options) {
      vehicleRegisterTelemetryMode.innerHTML = options;
    }
    vehicleRegisterTelemetryMode.value = telemetryMode;
  }
  if (vehicleRegisterTelemetryHelp) {
    vehicleRegisterTelemetryHelp.textContent = telemetryMode === "api"
      ? "API CENTRAL consultará la ruta /telemetry/{id}/gps usando el ID configurado."
      : "Sin telemetría dejará el vehículo registrado como ficha operativa, sin fuente en tiempo real.";
  }
  if (vehicleRegisterTypeNote) {
    if (telemetryMode === "api") {
      vehicleRegisterTypeNote.textContent = isDrone
        ? "El dron se actualizará desde una API externa. El id recibido por la API debe coincidir con el que registres aquí."
        : "El automóvil se actualizará desde una API GPS externa. El id recibido por la API debe coincidir con el que registres aquí.";
    } else {
      vehicleRegisterTypeNote.textContent = isDrone
        ? "Al registrar un dron puedes dejarlo como ficha manual o enlazarlo por API."
        : "Al registrar un vehículo terrestre conviene guardar la placa, unidad o identificador operativo y, si quieres, enlazarlo luego a una API GPS.";
    }
  }
  if (vehicleRegisterApiFields) {
    vehicleRegisterApiFields.hidden = telemetryMode !== "api";
  }
  [vehicleRegisterApiDeviceId].forEach((field) => {
    if (!field) return;
    const enableField = telemetryMode === "api";
    field.disabled = !enableField;
    if (!enableField) {
      field.value = "";
    }
  });

  if (
    telemetryMode === "api"
    && isDrone
    && vehicleRegisterApiDeviceId
    && !String(vehicleRegisterApiDeviceId.value || "").trim()
  ) {
    vehicleRegisterApiDeviceId.value = String(vehicleApiDefaults.default_drone_device_id || "drone").trim() || "drone";
  }
  renderVehicleRegisterCameraList();
}

function resetVehicleRegisterState() {
  editingVehicleRegistrationId = null;
  if (vehicleRegisterForm) {
    vehicleRegisterForm.reset();
  }
  syncVehicleRegisterCatalogOptions({ selectedLinks: [] });
  if (vehicleRegisterTelemetryMode) vehicleRegisterTelemetryMode.value = "manual";
  syncVehicleRegisterModalChrome();
  updateVehicleRegisterTypeCopy();
  setVehicleRegisterFeedback("");
}

function normalizeVehicleRegistrationId(value) {
  const normalized = String(value || "").trim();
  return normalized || null;
}

function vehicleRegistrySelectionKey(item) {
  const registrationId = normalizeVehicleRegistrationId(item && item.registration_id);
  if (registrationId) {
    return `manual::${registrationId}`;
  }
  return [
    String(item && item.entry_kind || "manual").trim(),
    String(item && item.vehicle_type || "").trim().toLowerCase(),
    String(item && item.label || "").trim().toLowerCase(),
    String(item && item.identifier || "").trim().toLowerCase(),
    String(Number(item && item.ts) || 0),
  ].join("::");
}

function syncVehicleRegisterModalChrome() {
  const isEditing = Boolean(editingVehicleRegistrationId);
  if (vehicleRegisterTitle) {
    vehicleRegisterTitle.textContent = isEditing ? "Editar vehículo" : "Registrar nuevo vehículo";
  }
  if (vehicleRegisterCopy) {
    vehicleRegisterCopy.textContent = isEditing
      ? "Actualiza la ficha del vehículo seleccionado, su modo de telemetría y los datos de enlace si cambiaron."
      : "Selecciona si quieres registrar un dron o un automóvil y define si su telemetría llegará por API o si solo deseas guardarlo como ficha operativa.";
  }
  if (vehicleRegisterSubmit) {
    vehicleRegisterSubmit.textContent = isEditing ? "Guardar cambios" : "Guardar vehículo";
  }
  if (vehicleRegisterDelete) {
    vehicleRegisterDelete.hidden = !isEditing;
  }
}

function findVehicleRegistryItemByRegistrationId(registrationId) {
  const normalized = normalizeVehicleRegistrationId(registrationId);
  if (!normalized) return null;
  return (Array.isArray(lastVehicleRegistrySnapshot) ? lastVehicleRegistrySnapshot : [])
    .find((item) => normalizeVehicleRegistrationId(item && item.registration_id) === normalized) || null;
}

function populateVehicleRegisterState(item) {
  if (!item || typeof item !== "object") return;
  editingVehicleRegistrationId = normalizeVehicleRegistrationId(item.registration_id);
  if (vehicleRegisterOrganization) {
    vehicleRegisterOrganization.value = String(item.organizacion_id || "").trim();
  }
  if (vehicleRegisterOwner) {
    vehicleRegisterOwner.value = String(item.propietario_usuario_id || "").trim();
  }
  if (vehicleRegisterType) {
    vehicleRegisterType.value = normalizeVehicleTypeCode(item.vehicle_type_code || item.vehicle_type || "drone_robiotec");
  }
  if (vehicleRegisterLabel) {
    vehicleRegisterLabel.value = String(item.label || "").trim();
  }
  if (vehicleRegisterIdentifier) {
    vehicleRegisterIdentifier.value = String(item.identifier || "").trim();
  }
  if (vehicleRegisterTelemetryMode) {
    vehicleRegisterTelemetryMode.value = String(item.telemetry_mode || "manual").trim().toLowerCase() || "manual";
  }
  if (vehicleRegisterApiDeviceId) {
    vehicleRegisterApiDeviceId.value = String(item.api_device_id || "").trim();
  }
  if (vehicleRegisterNotes) {
    vehicleRegisterNotes.value = String(item.notes || "").trim();
  }
  syncVehicleRegisterModalChrome();
  updateVehicleRegisterTypeCopy();
  renderVehicleRegisterCameraList(item);
}

async function openVehicleRegisterModal(item = null) {
  if (!vehicleRegisterModal) return;
  await refreshVehicleRegistryFormOptions();
  resetVehicleRegisterState();
  if (
    item
    && typeof item === "object"
    && !(item instanceof Event)
    && (
      Object.prototype.hasOwnProperty.call(item, "registration_id")
      || Object.prototype.hasOwnProperty.call(item, "identifier")
      || Object.prototype.hasOwnProperty.call(item, "entry_kind")
    )
  ) {
    populateVehicleRegisterState(item);
  }
  vehicleRegisterModal.hidden = false;
  syncGlobalModalState();
  window.requestAnimationFrame(() => {
    if (vehicleRegisterLabel) {
      vehicleRegisterLabel.focus();
      vehicleRegisterLabel.select();
    }
  });
}

function closeVehicleRegisterModal() {
  if (!vehicleRegisterModal) return;
  vehicleRegisterModal.hidden = true;
  syncGlobalModalState();
  editingVehicleRegistrationId = null;
  syncVehicleRegisterModalChrome();
  setVehicleRegisterFeedback("");
}

function setState(domId, text) {
  const badge = document.getElementById(`state-${domId}`);
  if (badge) badge.textContent = text;

  const camera = CAMERA_BY_DOM_ID.get(domId);
  if (!camera) return;
  updateSelectorState(camera.name, text);
}

function supportsAudio(cameraName) {
  const device = getDeviceByCamera(cameraName);
  return Boolean(
    (device && device.capabilities && device.capabilities.audio)
    || supportsManagedAudioPlayback(cameraName)
    || supportsEmbeddedBrowserViewer(cameraName)
  );
}

function supportsTelemetry(cameraName) {
  const device = getDeviceByCamera(cameraName);
  return Boolean(device && device.capabilities && device.capabilities.telemetry);
}

function applyCapabilityBadges() {
  CAMERAS.forEach((camera) => {
    const badges = document.getElementById(`badges-${camera.dom_id}`);
    if (!badges) return;

    const device = getDeviceByCamera(camera.name);
    const items = [];
    if (supportsAudio(camera.name)) {
      items.push('<span class="camera-badge">AUDIO</span>');
    }
    if (device && device.capabilities) {
      if (device.capabilities.telemetry) {
        items.push('<span class="camera-badge">GPS</span>');
      }
    }
    if (resolveCameraPlaybackTarget(camera.name).mode === "iframe") {
      items.push('<span class="camera-badge">WEB</span>');
    }
    badges.innerHTML = items.join("");
  });
}

function setAudioButtonState(button, { label, disabled, pressed }) {
  if (!button) return;
  button.textContent = label;
  button.disabled = Boolean(disabled);
  button.dataset.state = pressed ? "on" : "off";
  button.setAttribute("aria-pressed", pressed ? "true" : "false");
}

function syncCardAudioButtons() {
  CAMERAS.forEach((camera) => {
    const button = getCardAudioToggle(camera.name);
    if (!button) return;

    const isActive = camera.name === activeCamera;
    const hasAudio = supportsAudio(camera.name);
    button.hidden = !isActive;

    if (!isActive) {
      setAudioButtonState(button, {
        label: "Activar audio",
        disabled: true,
        pressed: false,
      });
      return;
    }

    if (!hasAudio) {
      setAudioButtonState(button, {
        label: "Sin audio",
        disabled: true,
        pressed: false,
      });
      return;
    }

    setAudioButtonState(button, {
      label: audioEnabled ? "Silenciar" : "Activar audio",
      disabled: false,
      pressed: audioEnabled,
    });
  });
}

function getCameraCardErrorBox(camera) {
  const card = getCardByCamera(camera);
  if (!card) return null;

  let errorBox = card.querySelector(".camera-error");
  if (!errorBox) {
    errorBox = document.createElement("div");
    errorBox.className = "camera-error";
    errorBox.style.display = "none";
    card.insertBefore(errorBox, card.querySelector(".camera-meta") || null);
  }
  return errorBox;
}

function showCameraCardError(camera, message) {
  const errorBox = getCameraCardErrorBox(camera);
  if (!errorBox) return;
  errorBox.textContent = String(message || "No se pudo abrir la cámara.");
  errorBox.style.display = "";
}

function hideCameraCardError(camera) {
  const errorBox = getCameraCardErrorBox(camera);
  if (!errorBox) return;
  errorBox.textContent = "";
  errorBox.style.display = "none";
}

function syncAudioFromVideoElement(cameraName) {
  if (audioUiSyncInProgress) return;
  if (!cameraName || cameraName !== activeCamera) return;

  const video = getVideoByCamera(cameraName);
  if (!video) return;

  audioEnabled = !video.muted;
  if (audioVolume) {
    audioVolume.value = String(Math.max(0, Math.min(100, Math.round((video.volume || 0) * 100))));
  }
  applyAudioState();
}

function buildCameraCard(camera) {
  const card = document.createElement("section");
  card.className = "camera-card";
  card.id = `card-${camera.dom_id}`;
  card.setAttribute("role", "button");
  card.setAttribute("tabindex", "0");
  card.setAttribute("aria-pressed", "false");
  card.setAttribute("aria-label", `Abrir cámara ${getCameraDisplayName(camera)}`);
  card.innerHTML = `
    <video class="video" id="video-${camera.dom_id}" autoplay playsinline muted></video>
    <div class="camera-error" style="display:none;color:#e74c3c;font-size:0.95em;padding:4px 0;"></div>
    <button class="camera-card-close" id="card-close-${camera.dom_id}" type="button" hidden aria-label="Cerrar cámara ${getCameraDisplayName(camera)}">×</button>
    <div class="camera-meta">
      <div class="camera-topline">
        <div class="camera-name">${getCameraDisplayName(camera, { uppercase: true })}</div>
        <div class="camera-state" id="state-${camera.dom_id}">Conectando...</div>
      </div>
      <div class="camera-badges" id="badges-${camera.dom_id}"></div>
      <div class="camera-footer">
        <div class="camera-hint">Toca para enfocar</div>
        <button class="camera-audio-toggle" id="card-audio-${camera.dom_id}" type="button" hidden>Activar audio</button>
      </div>
    </div>
  `;
  return card;
}

function ensureCameraCard(camera) {
  const existing = getCardByCamera(camera);
  if (existing) return existing;

  const card = buildCameraCard(camera);
  if (cameraPool) {
    cameraPool.appendChild(card);
  } else if (primaryView) {
    primaryView.appendChild(card);
  }
  return card;
}

function upsertDevice(device) {
  if (!device || typeof device !== "object" || !device.camera_name) return;
  const currentIndex = DEVICES.findIndex((item) => item && item.camera_name === device.camera_name);
  if (currentIndex >= 0) {
    DEVICES.splice(currentIndex, 1, device);
  } else {
    DEVICES.push(device);
  }
  DEVICE_BY_CAMERA.set(device.camera_name, device);
}

function updateDeviceCapability(cameraName, capabilityName, enabled, extra = {}) {
  if (!cameraName || !capabilityName) return;
  const current = getDeviceByCamera(cameraName) || {
    device_id: cameraName,
    camera_name: cameraName,
    capabilities: {},
  };
  const next = {
    ...current,
    ...extra,
    capabilities: {
      ...(current.capabilities && typeof current.capabilities === "object" ? current.capabilities : {}),
      [capabilityName]: Boolean(enabled),
    },
  };
  upsertDevice(next);
}

function markCameraAudioAvailable(cameraName) {
  const device = getDeviceByCamera(cameraName);
  if (device && device.capabilities && device.capabilities.audio) return;
  updateDeviceCapability(cameraName, "audio", true, { has_audio_source: true });
  renderSwitcher();
  applyCapabilityBadges();
  updateFocusUi();
}

function getCameraRuntimeId(camera) {
  const numeric = Number(camera && (camera.camera_id || camera.id) || 0);
  return Number.isInteger(numeric) && numeric > 0 ? numeric : null;
}

function getCameraDisplayName(cameraOrName, { uppercase = false } = {}) {
  const camera = typeof cameraOrName === "string"
    ? getCameraByName(cameraOrName)
    : cameraOrName;
  const fallbackName = typeof cameraOrName === "string"
    ? String(cameraOrName || "").trim()
    : String(camera && camera.name || "").trim();
  const displayName = buildCameraAdminInferenceName(
    camera && camera.name ? camera.name : fallbackName,
    Boolean(camera && camera.hacer_inferencia === true),
  ) || fallbackName;
  return uppercase ? displayName.toUpperCase() : displayName;
}

function canToggleCameraInference(camera) {
  return USER_CAN_MANAGE_CAMERA_INFERENCE && getCameraRuntimeId(camera) !== null;
}

function isCameraInferenceEnabled(camera) {
  return Boolean(camera && camera.hacer_inferencia === true);
}

function buildCameraInferenceSourceUrl(rawUrl, enabled) {
  const candidate = String(rawUrl || "").trim();
  if (!candidate || !isLikelyManagedEmbeddedViewerSource(candidate)) {
    return candidate;
  }

  try {
    const target = new URL(candidate, window.location.href);
    let pathname = String(target.pathname || "").replace(/\/+INFERENCE\/?$/i, "").replace(/\/+$/, "");
    if (enabled) {
      pathname = pathname ? `${pathname}/INFERENCE` : "/INFERENCE";
    } else if (!pathname) {
      pathname = "/";
    }
    target.pathname = pathname || "/";
    return target.toString();
  } catch (error) {
    return candidate;
  }
}

function flashCameraInferenceFeedback(message, tone = "info", durationMs = 2600) {
  if (!cameraAdminFeedback || !message) return;
  setCameraAdminFeedback(message, tone);
  if (cameraInferenceFeedbackTimerId) {
    clearTimeout(cameraInferenceFeedbackTimerId);
  }
  cameraInferenceFeedbackTimerId = window.setTimeout(() => {
    cameraInferenceFeedbackTimerId = null;
    if (cameraAdminFeedback && cameraAdminFeedback.textContent === message) {
      setCameraAdminFeedback("");
    }
  }, durationMs);
}

function applyCameraInferenceButtonState(button, camera) {
  if (!button || !camera) return;

  const enabled = isCameraInferenceEnabled(camera);
  const updating = camera.inferenceUpdating === true;
  const actionLabel = enabled ? "Desactivar" : "Activar";
  const statusLabel = updating
    ? "Actualizando inferencia"
    : enabled
      ? "Inferencia activa"
      : "Inferencia inactiva";

  button.classList.toggle("is-enabled", enabled);
  button.classList.toggle("is-updating", updating);
  button.disabled = updating;
  button.dataset.state = enabled ? "on" : "off";
  button.setAttribute("aria-pressed", enabled ? "true" : "false");
  button.setAttribute("aria-label", `${actionLabel} inferencia en ${getCameraDisplayName(camera)}`);
  button.title = `${statusLabel} · ${getCameraDisplayName(camera, { uppercase: true })}`;
}

function syncCameraInferenceDeviceState(cameraName, enabled) {
  const currentDevice = getDeviceByCamera(cameraName);
  if (!currentDevice) return;

  upsertDevice({
    ...currentDevice,
    source: buildCameraInferenceSourceUrl(currentDevice.source, enabled),
    viewer_url: buildCameraInferenceSourceUrl(currentDevice.viewer_url, enabled),
    audio_source: buildCameraInferenceSourceUrl(currentDevice.audio_source, enabled),
    address: buildCameraInferenceSourceUrl(currentDevice.address, enabled),
  });
}

function syncCameraDisplayNameUi(cameraName) {
  const camera = getCameraByName(cameraName);
  if (!camera) return;

  const displayName = getCameraDisplayName(camera);
  const displayNameUpper = getCameraDisplayName(camera, { uppercase: true });
  const card = getCardByCamera(camera);
  if (card) {
    card.setAttribute("aria-label", `Abrir cámara ${displayName}`);
    const nameNode = card.querySelector(".camera-name");
    if (nameNode) {
      nameNode.textContent = displayNameUpper;
    }
  }

  const closeButton = getCardCloseButton(cameraName);
  if (closeButton) {
    closeButton.setAttribute("aria-label", `Cerrar cámara ${displayName}`);
  }

  renderActiveCameraSummary();
  updateDashboardCameraPreview();
}

function syncCameraInferenceAdminState(cameraName, enabled) {
  const normalizedName = String(cameraName || "").trim();
  if (!normalizedName) return;
  const runtimeCamera = getCameraByName(normalizedName);
  const runtimeCameraId = getCameraRuntimeId(runtimeCamera);

  lastCameraAdminSnapshot = lastCameraAdminSnapshot.map((item) => {
    const itemId = normalizeCameraAdminId(item && item.id);
    const sameCamera = runtimeCameraId !== null
      ? itemId === runtimeCameraId
      : String(item && item.nombre || "").trim() === normalizedName;
    if (!sameCamera) {
      return item;
    }
    return {
      ...item,
      hacer_inferencia: Boolean(enabled),
    };
  });

  const selectedCamera = findSelectedCameraAdminItem(lastCameraAdminSnapshot);
  if (
    selectedCamera
    && (
      (runtimeCameraId !== null && normalizeCameraAdminId(selectedCamera.id) === runtimeCameraId)
      || String(selectedCamera.nombre || "").trim() === normalizedName
    )
    && cameraAdminInferenceEnabled
  ) {
    cameraAdminInferenceEnabled.value = enabled ? "true" : "false";
    syncCameraAdminInferenceName();
  }
}

function setCameraInferenceEnabledState(cameraName, enabled) {
  const camera = getCameraByName(cameraName);
  if (!camera) return;
  camera.hacer_inferencia = Boolean(enabled);
  syncCameraInferenceDeviceState(cameraName, enabled);
  syncCameraInferenceAdminState(cameraName, enabled);
  syncCameraDisplayNameUi(cameraName);

  const button = inferenceButtons.get(cameraName);
  if (button) {
    applyCameraInferenceButtonState(button, camera);
  }

  renderSwitcher();
  applyCapabilityBadges();
  updateFocusUi();
}

function setCameraInferenceUpdating(cameraName, updating) {
  const camera = getCameraByName(cameraName);
  if (!camera) return;
  camera.inferenceUpdating = Boolean(updating);

  const button = inferenceButtons.get(cameraName);
  if (button) {
    applyCameraInferenceButtonState(button, camera);
  }
}

async function toggleCameraInference(cameraName) {
  const camera = getCameraByName(cameraName);
  if (!camera || camera.inferenceUpdating === true) return;

  const cameraId = getCameraRuntimeId(camera);
  if (cameraId === null) return;

  const nextValue = !isCameraInferenceEnabled(camera);
  setCameraInferenceUpdating(cameraName, true);

  try {
    const payload = await fetchJson(`/api/cameras/${cameraId}/inference`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        hacer_inferencia: nextValue,
      }),
      timeoutMs: 10000,
    });
    const updatedCamera = payload && typeof payload.camera === "object" ? payload.camera : null;
    setCameraInferenceEnabledState(
      cameraName,
      updatedCamera ? Boolean(updatedCamera.hacer_inferencia) : nextValue,
    );
    if (getDesiredCameraNames().includes(cameraName)) {
      deactivateCamera(cameraName, "Cambiando inferencia...");
      syncStreaming();
    }
  } catch (error) {
    flashCameraInferenceFeedback(friendlyCameraAdminError(error), "error", 3600);
  } finally {
    setCameraInferenceUpdating(cameraName, false);
  }
}

function addRegisteredCamera(payload) {
  const camera = payload && typeof payload.camera === "object" ? payload.camera : null;
  if (!camera || !camera.name || !camera.dom_id) {
    throw new Error("invalid_camera_payload");
  }

  const existingCamera = getCameraByName(camera.name);
  if (!existingCamera) {
    CAMERAS.push(camera);
    CAMERA_BY_DOM_ID.set(camera.dom_id, camera);
  }

  if (payload && typeof payload.device === "object") {
    upsertDevice(payload.device);
  }

  ensureCameraCard(existingCamera || camera);
  bindCardInteraction(existingCamera || camera);
  renderSwitcher();
  applyCapabilityBadges();
  activeCamera = camera.name;
  persistActiveCameraSelection(camera.name);
  updateFocusUi();
  syncStreaming();
  refreshStatus();
  refreshTelemetry();
  refreshEvents();
}

function friendlyCameraRegisterError(error) {
  const code = String((error && error.message) || "").trim();
  if (code.includes("Traceback")) {
    return "Ocurrió un error interno registrando la cámara.";
  }
  switch (code) {
    case "camera_already_exists":
      return "Ese nombre ya existe en el sistema.";
    case "invalid_camera_name":
      return "El nombre solo puede usar letras, números, puntos, guiones y guion bajo.";
    case "invalid_camera_location":
      return "Selecciona una ubicación válida en el mapa o ingresa latitud y longitud correctas.";
    case "invalid_camera_source":
      return "La fuente debe ser una URL web válida: HLS (.m3u8), video directo o una página del reproductor.";
    case "unsupported_camera_source_protocol":
      return "Esta app ya no abre RTSP/WebRTC directo. Registra la URL web final que entrega tu backend de video.";
    case "invalid_camera_payload":
      return "No pude interpretar la respuesta del registro.";
    default:
      return code || "No se pudo registrar la cámara.";
  }
}

function cameraSourceProtocolError(source) {
  const normalized = String(source || "").trim().toLowerCase();
  if (!normalized) return "";
  if (!isHttpCameraSource(normalized)) {
    return "Registra la URL web final del video. Usa http:// o https://, por ejemplo un .m3u8, .mp4 o una página del visor.";
  }
  if (
    normalized.startsWith("webrtc://")
    || normalized.startsWith("whip://")
    || normalized.startsWith("whep://")
  ) {
    return "Esta app ya no abre WebRTC directo. Registra la URL web final que entrega tu backend de video.";
  }
  return "";
}

function friendlyVehicleRegisterError(error) {
  const code = String((error && error.message) || "").trim();
  switch (code) {
    case "vehicle_not_found":
      return "Ese registro ya no existe o fue eliminado.";
    case "vehicle_already_exists":
      return "Ese identificador ya fue registrado. Usa otro código o corrige el existente.";
    case "invalid_vehicle_type":
      return "Selecciona si deseas registrar un dron o un automóvil.";
    case "invalid_vehicle_label":
      return "Ingresa un nombre o alias para el vehículo.";
    case "invalid_vehicle_identifier":
      return "Ingresa la placa, serie o identificador del vehículo.";
    case "invalid_organization_id":
      return "Selecciona la organización del vehículo.";
    case "invalid_owner_user_id":
      return "Selecciona el propietario del vehículo.";
    case "owner_user_not_found":
      return "El usuario propietario ya no existe.";
    case "organization_not_found":
      return "La organización seleccionada ya no existe.";
    case "invalid_vehicle_telemetry_mode":
      return "Selecciona un modo válido de telemetría para el vehículo.";
    case "invalid_api_base_url":
      return "La Base URL de la API GPS debe comenzar con http:// o https://.";
    case "invalid_vehicle_camera_links":
    case "invalid_vehicle_camera_id":
      return "La selección de cámaras del vehículo no es válida.";
    case "camera_not_found":
      return "Una de las cámaras seleccionadas ya no existe.";
    case "camera_organization_mismatch":
      return "Solo puedes asociar cámaras que pertenezcan a la misma organización del vehículo.";
    case "camera_vehicle_type_mismatch":
      return "El tipo de cámara no coincide con el tipo de vehículo seleccionado.";
    case "vehicle_scope_forbidden":
      return "Ese vehículo está fuera del alcance que tu rol puede administrar.";
    case "role_scope_forbidden":
      return "Ese usuario queda fuera de la jerarquía que tu rol puede administrar.";
    case "organization_scope_forbidden":
      return "La organización seleccionada está fuera de tu jerarquía operativa.";
    case "vehicle_in_use":
      return "No se puede eliminar el vehículo porque todavía tiene información relacionada dentro del sistema.";
    case "invalid_vehicle_payload":
      return "No pude interpretar la respuesta del registro.";
    case "forbidden":
      return "Solo administradores, ingenieros y desarrolladores pueden editar vehículos.";
    case "database_unavailable":
      return "La base de datos no está disponible en este momento.";
    default:
      return code || "No se pudo registrar el vehículo.";
  }
}

function friendlyUserAdminError(error) {
  const code = String((error && error.message) || "").trim();
  switch (code) {
    case "forbidden":
      return "Esta sección está disponible para administradores, ingenieros y desarrolladores.";
    case "database_unavailable":
      return "La base de datos no está disponible en este momento.";
    case "invalid_user_payload":
      return "No pude interpretar los datos enviados del usuario.";
    case "invalid_user_id":
      return "El identificador del usuario no es válido.";
    case "invalid_username":
      return "Ingresa un nombre de usuario válido.";
    case "username_too_long":
      return "El nombre de usuario no puede exceder 20 caracteres.";
    case "invalid_email":
      return "Ingresa un correo electrónico válido para la cuenta.";
    case "email_already_exists":
      return "Ese correo ya está registrado en otra cuenta.";
    case "invalid_name":
      return "Ingresa un nombre válido para el usuario.";
    case "invalid_last_name":
      return "El apellido del usuario no es válido.";
    case "invalid_phone":
      return "El teléfono ingresado no es válido.";
    case "invalid_password":
      return "Ingresa una contraseña válida.";
    case "invalid_role":
    case "role_not_found":
      return "Selecciona un rol válido para la cuenta.";
    case "role_scope_forbidden":
      return "Solo puedes gestionar usuarios con prioridad igual o inferior a la de tu rol.";
    case "user_already_exists":
      return "Ese usuario ya existe. Usa otro nombre.";
    case "user_not_found":
      return "El usuario seleccionado ya no existe.";
    case "cannot_delete_current_user":
      return "No puedes eliminar la cuenta con la que tienes la sesión actual.";
    case "cannot_change_current_user_role":
      return "No puedes cambiar el rol de tu propia sesión desde este panel.";
    default:
      return code || "No se pudo completar la operación sobre el usuario.";
  }
}

function friendlyRoleAdminError(error) {
  const code = String((error && error.message) || "").trim();
  switch (code) {
    case "forbidden":
      return "Esta sección está disponible solo para usuarios con rol desarrollador.";
    case "database_unavailable":
      return "La base de datos no está disponible en este momento.";
    case "invalid_role_payload":
      return "No pude interpretar los datos enviados del rol.";
    case "invalid_role_id":
      return "El identificador del rol no es válido.";
    case "invalid_role_code":
      return "Ingresa un código de rol válido.";
    case "invalid_role_name":
      return "Ingresa un nombre visible válido para el rol.";
    case "invalid_role_level":
      return "El nivel del rol debe ser un número entero válido.";
    case "role_already_exists":
      return "Ya existe un rol con ese código o nombre.";
    case "role_not_found":
      return "El rol seleccionado ya no existe.";
    case "role_in_use":
      return "No puedes eliminar un rol que todavía tiene usuarios asignados.";
    default:
      return code || "No se pudo completar la operación sobre el rol.";
  }
}

function friendlyOrganizationAdminError(error) {
  const code = String((error && error.message) || "").trim();
  switch (code) {
    case "forbidden":
      return "Esta sección está disponible para administradores, ingenieros y desarrolladores.";
    case "database_unavailable":
      return "La base de datos no está disponible en este momento.";
    case "invalid_organization_payload":
      return "No pude interpretar los datos enviados de la organización.";
    case "invalid_organization_id":
      return "El identificador de la organización no es válido.";
    case "invalid_organization_name":
      return "Ingresa un nombre válido para la organización.";
    case "organization_name_too_long":
      return "El nombre de la organización no puede exceder 150 caracteres.";
    case "invalid_owner_user_id":
      return "Selecciona un propietario válido para la organización.";
    case "owner_user_not_found":
      return "El propietario seleccionado ya no existe.";
    case "organization_already_exists":
      return "Ya existe una organización con ese nombre para el propietario seleccionado.";
    case "organization_not_found":
      return "La organización seleccionada ya no existe.";
    case "organization_scope_forbidden":
      return "Solo puedes gestionar organizaciones cuyo propietario este dentro de tu jerarquia.";
    default:
      return code || "No se pudo completar la operación sobre la organización.";
  }
}

function friendlyCameraAdminError(error) {
  const code = String((error && error.message) || "").trim();
  switch (code) {
    case "forbidden":
      return "Esta sección está disponible para administradores, ingenieros y desarrolladores.";
    case "database_unavailable":
      return "La base de datos no está disponible en este momento.";
    case "invalid_camera_payload":
      return "No pude interpretar los datos enviados de la cámara.";
    case "invalid_camera_id":
      return "El identificador de la cámara no es válido.";
    case "invalid_camera_name":
      return "Ingresa un nombre válido para la cámara.";
    case "invalid_camera_stream_url":
    case "invalid_camera_source":
      return "Ingresa una URL válida para el stream de la cámara.";
    case "invalid_camera_rtsp_payload":
      return "No pude interpretar los datos técnicos para generar la URL RTSP.";
    case "invalid_camera_rtsp_brand":
      return "La marca seleccionada no tiene una plantilla RTSP compatible o requiere datos adicionales.";
    case "invalid_camera_rtsp_ip":
      return "Ingresa una IP o un host válido para generar la URL RTSP.";
    case "invalid_puerto":
      return "El puerto RTSP debe ser un número válido mayor a cero.";
    case "invalid_canal":
      return "El canal RTSP debe ser un número válido mayor a cero.";
    case "invalid_camera_rtsp_path":
      return "La ruta personalizada es obligatoria para esa plantilla RTSP.";
    case "invalid_camera_rtsp_url":
      return "Ingresa una URL RTSP válida para la cámara.";
    case "unsupported_camera_source_protocol":
      return "La URL para visor debe ser http:// o https://. Si tienes una fuente rtsp://, colócala en “URL RTSP manual” o usa el asistente por fabricante.";
    case "invalid_camera_location":
    case "static_camera_requires_location":
      return "Las cámaras fijas necesitan una ubicación válida en el mapa.";
    case "moving_camera_requires_vehicle":
      return "Las cámaras móviles deben quedar enlazadas a un vehículo.";
    case "invalid_organization_id":
    case "organization_not_found":
      return "Selecciona una organización válida para la cámara.";
    case "invalid_owner_user_id":
    case "owner_user_not_found":
      return "Selecciona un responsable válido para la cámara.";
    case "camera_type_not_found":
    case "camera_type_not_supported":
      return "Selecciona un tipo de cámara válido.";
    case "camera_protocol_not_found":
      return "Selecciona un protocolo válido para la cámara.";
    case "camera_already_exists":
      return "Ya existe una cámara con ese nombre dentro de la organización seleccionada.";
    case "camera_unique_code_already_exists":
      return "Ese código único ya está asignado a otra cámara.";
    case "camera_scope_forbidden":
      return "Solo puedes gestionar cámaras cuyo propietario esté dentro de tu jerarquía.";
    case "organization_scope_forbidden":
      return "La organización elegida queda fuera de tu alcance operativo.";
    case "vehicle_not_found":
      return "El vehículo seleccionado ya no existe.";
    case "vehicle_organization_mismatch":
      return "El vehículo debe pertenecer a la misma organización de la cámara.";
    case "camera_vehicle_type_mismatch":
      return "El tipo de vehículo no coincide con el tipo de cámara que quieres registrar.";
    case "camera_not_found":
      return "La cámara seleccionada ya no existe.";
    case "camera_in_use":
      return "No puedes eliminar una cámara que todavía tiene eventos asociados.";
    default:
      return code || "No se pudo completar la operación sobre la cámara.";
  }
}

function isMobileOrNarrowScreen() {
  const mobileUa = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent || "");
  const narrowViewport = window.matchMedia(`(max-width: ${SINGLE_STREAM_BREAKPOINT_PX}px)`).matches;
  return mobileUa || narrowViewport;
}

function toneForStatus(text) {
  const value = String(text || "").toLowerCase();
  if (value.includes("vivo") || value.includes("online") || value.includes("running")) return "live";
  if (value.includes("conect") || value.includes("recon") || value.includes("cargando") || value.includes("warming")) return "busy";
  if (value.includes("error") || value.includes("fail") || value.includes("offline")) return "error";
  return "idle";
}

function updateSelectorState(cameraName, text) {
  const button = switchButtons.get(cameraName);
  if (!button) return;

  const statusNode = button.querySelector(".camera-pill-status");
  const ledNode = button.querySelector(".camera-pill-led");
  if (statusNode) {
    statusNode.textContent = text;
  }
  if (ledNode) {
    ledNode.className = `camera-pill-led tone-${toneForStatus(text)}`;
  }
  if (cameraName === activeCamera) {
    renderActiveCameraSummary();
  }
}

function renderActiveCameraSummary() {
  const camera = getCameraByName(activeCamera);
  if (!camera) {
    if (activeCameraName) {
      activeCameraName.textContent = "--";
    }
    if (activeCameraCapabilities) {
      activeCameraCapabilities.innerHTML = "";
    }
    return;
  }

  const device = getDeviceByCamera(camera.name);
  const button = switchButtons.get(camera.name);
  const currentStatus = button && button.querySelector(".camera-pill-status")
    ? button.querySelector(".camera-pill-status").textContent
    : "Lista";

  if (activeCameraName) {
    activeCameraName.textContent = getCameraDisplayName(camera, { uppercase: true });
  }

  const chips = [
    `<span class="viewer-chip viewer-chip-state tone-${toneForStatus(currentStatus)}">${currentStatus}</span>`,
  ];
  if (device && device.capabilities) {
    if (supportsAudio(camera.name)) {
      chips.push('<span class="viewer-chip">Audio</span>');
    }
    if (device.capabilities.telemetry) {
      chips.push('<span class="viewer-chip">GPS</span>');
    }
    if (resolveCameraPlaybackTarget(camera.name).mode === "iframe") {
      chips.push('<span class="viewer-chip">Web</span>');
    }
  }
  if (activeCameraCapabilities) {
    activeCameraCapabilities.innerHTML = chips.join("");
  }
}

function shouldUseSingleStreamMode() {
  if (CAMERAS.length <= 1) return false;
  return true;
}

function getDesiredCameraNames() {
  if (pageUsesDashboardCameraPreview()) {
    return getDashboardPinnedCameraNames();
  }
  if (!activeCamera) {
    return [];
  }
  if (shouldUseSingleStreamMode()) {
    return [activeCamera];
  }
  return [activeCamera];
}

function renderSwitcher() {
  if (!switcher) return;

  switcher.innerHTML = "";
  switchButtons.clear();
  inferenceButtons.clear();

  CAMERAS.forEach((camera) => {
    const device = getDeviceByCamera(camera.name);
    const tags = [];
    if (supportsAudio(camera.name)) tags.push("Audio");
    if (device && device.capabilities && device.capabilities.telemetry) tags.push("GPS");
    const shell = document.createElement("article");
    shell.className = "camera-pill-shell";

    const button = document.createElement("button");
    button.type = "button";
    button.className = "camera-pill";
    button.innerHTML = `
      <span class="camera-pill-main">
        <span class="camera-pill-topline">
          <span class="camera-pill-led tone-idle"></span>
          <span class="camera-pill-title">${getCameraDisplayName(camera, { uppercase: true })}</span>
        </span>
        <span class="camera-pill-status">Lista</span>
      </span>
      <span class="camera-pill-tags">${tags.map((tag) => `<span class="camera-pill-tag">${tag}</span>`).join("")}</span>
    `;
    button.addEventListener("click", () => openCamera(camera.name));
    shell.appendChild(button);

    if (canToggleCameraInference(camera)) {
      const inferenceButton = document.createElement("button");
      inferenceButton.type = "button";
      inferenceButton.className = "camera-pill-inference";
      inferenceButton.innerHTML = '<span class="camera-pill-inference-label" aria-hidden="true">IA</span>';
      applyCameraInferenceButtonState(inferenceButton, camera);
      inferenceButton.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        void toggleCameraInference(camera.name);
      });
      shell.appendChild(inferenceButton);
      inferenceButtons.set(camera.name, inferenceButton);
    }

    switcher.appendChild(shell);
    switchButtons.set(camera.name, button);
  });
}

function updateFocusUi() {
  const dashboardPinnedNames = pageUsesDashboardCameraPreview()
    ? new Set(getDashboardPinnedCameraNames())
    : null;
  const activeCameraHost = getActiveCameraHost();
  CAMERAS.forEach((camera) => {
    const isActive = camera.name === activeCamera;
    const card = getCardByCamera(camera);
    if (card) {
      card.classList.toggle("is-active", isActive);
      card.classList.remove("is-rail");
      card.setAttribute("aria-pressed", isActive ? "true" : "false");
      if (dashboardPinnedNames) {
        if (dashboardPinnedNames.has(camera.name)) {
          if (dashboardCameraPreviewStage) {
            dashboardCameraPreviewStage.appendChild(card);
          }
        } else if (cameraPool) {
          cameraPool.appendChild(card);
        }
      } else if (isActive) {
        if (activeCameraHost) {
          activeCameraHost.appendChild(card);
        } else if (cameraPool) {
          cameraPool.appendChild(card);
        }
      } else if (cameraPool) {
        cameraPool.appendChild(card);
      }
    }

    const button = switchButtons.get(camera.name);
    if (button) {
      button.classList.toggle("is-active", isActive);
    }

    const closeButton = getCardCloseButton(camera.name);
    if (closeButton) {
      closeButton.hidden = !(dashboardPinnedNames && dashboardPinnedNames.has(camera.name));
    }
  });

  if (cameraStage) {
    cameraStage.classList.toggle("has-multiple", CAMERAS.length > 1);
  }
  if (cameraPool) {
    cameraPool.hidden = true;
  }
  if (focusClose) {
    focusClose.hidden = !activeCamera;
  }
  updatePrimaryViewPlaceholder();
  updateDashboardCameraPreview();
  renderActiveCameraSummary();
  applyAudioState();
  syncThemeToggleVisibility();
  renderLocationsPanel();
  refreshRenderedMapMarkers();
}

function openCamera(cameraName) {
  if (!cameraName) return;
  activeCamera = cameraName;
  persistActiveCameraSelection(cameraName);
  deactivateInactiveCameras(cameraName);
  updateFocusUi();
  syncStreaming();
  refreshTelemetry();
  refreshEvents();
}

function openDashboardPinnedCamera(cameraName) {
  if (!cameraName) return;
  pinDashboardCamera(cameraName);
  if (isMobileSidebarViewport()) {
    setDashboardMobilePanel("cameras");
  }
  updateFocusUi();
  syncStreaming();
  refreshTelemetry();
  refreshEvents();
}

function clearFocus() {
  persistActiveCameraSelection(null);
  activeCamera = START_WITHOUT_CAMERA ? null : getInitialCameraName();
  deactivateInactiveCameras(activeCamera);
  updateFocusUi();
  syncStreaming();
}

function clearDashboardPinnedCamera() {
  dashboardPinnedCameraNames = [];
  activeCamera = null;
  updateFocusUi();
  syncStreaming();
  refreshTelemetry();
  refreshEvents();
}

function removeDashboardPinnedCamera(cameraName) {
  if (!pageUsesDashboardCameraPreview() || !cameraName) return;

  const nextPinnedNames = getDashboardPinnedCameraNames().filter((name) => name !== cameraName);
  dashboardPinnedCameraNames = nextPinnedNames;
  if (activeCamera === cameraName) {
    activeCamera = nextPinnedNames.length > 0 ? nextPinnedNames[nextPinnedNames.length - 1] : null;
  }
  updateFocusUi();
  syncStreaming();
  refreshTelemetry();
  refreshEvents();
}

function bindCardInteraction(camera) {
  const card = getCardByCamera(camera);
  if (!card) return;

  if (card.dataset.bound !== "1") {
    card.dataset.bound = "1";
    card.addEventListener("click", () => openCamera(camera.name));
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openCamera(camera.name);
      }
    });
  }

  const audioButton = getCardAudioToggle(camera.name);
  if (audioButton && audioButton.dataset.bound !== "1") {
    audioButton.dataset.bound = "1";
    audioButton.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (camera.name !== activeCamera) {
        openCamera(camera.name);
      }
      if (!supportsAudio(camera.name)) return;
      audioEnabled = !audioEnabled;
      applyAudioState();
    });
    audioButton.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.stopPropagation();
      }
    });
  }

  const closeButton = getCardCloseButton(camera.name);
  if (closeButton && closeButton.dataset.bound !== "1") {
    closeButton.dataset.bound = "1";
    closeButton.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      removeDashboardPinnedCamera(camera.name);
    });
  }

  const video = getVideoByCamera(camera.name);
  if (video && video.dataset.audioSyncBound !== "1") {
    video.dataset.audioSyncBound = "1";
    video.addEventListener("volumechange", () => syncAudioFromVideoElement(camera.name));
  }
}

function bindCardInteractions() {
  CAMERAS.forEach((camera) => {
    bindCardInteraction(camera);
  });
}

function clearReconnectTimer(name) {
  const timerId = reconnectTimers.get(name);
  if (timerId) {
    clearTimeout(timerId);
    reconnectTimers.delete(name);
  }
}

function closePeer(name) {
  destroyHlsPlayer(name);
  const video = getVideoByCamera(name);
  if (video) {
    try { video.pause(); } catch (e) {}
    const stream = video.srcObject;
    if (stream && typeof stream.getTracks === "function") {
      stream.getTracks().forEach((track) => {
        try {
          track.onended = null;
        } catch (error) {}
        try {
          track.stop();
        } catch (error) {}
      });
    }
    video.srcObject = null;
    try {
      video.removeAttribute("src");
      video.load();
    } catch (error) {}
  }
  applyAudioState();
}

function deactivateCamera(name, idleStatus = null) {
  if (!name) return;
  clearReconnectTimer(name);
  const token = (connectionTokens.get(name) || 0) + 1;
  connectionTokens.set(name, token);
  connectInFlight.delete(name);
  closePeer(name);
  closeEmbeddedViewer(name);

  const camera = getCameraByName(name);
  if (camera && typeof idleStatus === "string" && idleStatus.trim()) {
    setState(camera.dom_id, idleStatus.trim());
  }
}

function deactivateInactiveCameras(activeName) {
  CAMERAS.forEach((camera) => {
    if (camera.name === activeName) return;
    deactivateCamera(
      camera.name,
      activeName ? "En espera" : "Selecciona una cámara",
    );
  });
}

function scheduleReconnect(camera, reason = "Reconectando") {
  if (document.visibilityState === "hidden") return;

  const { name, dom_id: domId } = camera;
  if (!getDesiredCameraNames().includes(name)) {
    clearReconnectTimer(name);
    return;
  }
  setState(domId, reason);

  if (reconnectTimers.has(name)) return;

  const prev = reconnectDelayMs.get(name) || 800;
  const jitter = Math.floor(Math.random() * 180);
  const next = Math.min(6000, Math.floor(prev * 1.6));
  reconnectDelayMs.set(name, next);

  const timerId = setTimeout(() => {
    reconnectTimers.delete(name);
    startCamera(camera).catch(() => scheduleReconnect(camera, "Reintentando señal..."));
  }, prev + jitter);

  reconnectTimers.set(name, timerId);
}

function createCameraConnectionError(code, fallbackMessage = "") {
  const error = new Error(code || fallbackMessage || "camera_connection_failed");
  error.code = code || "camera_connection_failed";
  error.fallbackMessage = fallbackMessage || "";
  return error;
}

function isRetryableCameraError(error) {
  const code = String((error && error.code) || (error && error.message) || "").trim();
  return code !== "camera_source_not_supported";
}

function statusForCameraError(error) {
  const code = String((error && error.code) || (error && error.message) || "").trim();
  switch (code) {
    case "camera_source_not_supported":
      return "URL no compatible";
    case "authorized_viewer_unavailable":
      return "Viewer protegido no disponible";
    default:
      return "Error conexión";
  }
}

function applyAudioState() {
  if (!audioSummary || !audioToggle || !audioVolume) return;

  const activeUsesEmbeddedViewer = Boolean(activeCamera && supportsEmbeddedBrowserViewer(activeCamera));
  const activeSupportsManagedAudio = Boolean(activeCamera && supportsManagedAudioPlayback(activeCamera));
  const activeSupportsAudio = Boolean(activeCamera && supportsAudio(activeCamera));
  const enabledForPlayback = audioEnabled && activeSupportsManagedAudio;
  if (audioControls) {
    audioControls.hidden = false;
  }

  audioUiSyncInProgress = true;
  try {
    CAMERAS.forEach((camera) => {
      const video = getVideoByCamera(camera.name);
      if (!video) return;
      const isAudible = enabledForPlayback && camera.name === activeCamera;
      video.muted = !isAudible;
      video.volume = isAudible ? Number(audioVolume.value) / 100 : 0;
      if (isAudible) {
        const playPromise = video.play();
        if (playPromise && typeof playPromise.catch === "function") {
          playPromise.catch(() => {});
        }
      }
    });
  } finally {
    audioUiSyncInProgress = false;
  }

  if (!activeCamera) {
    audioSummary.textContent = EMPTY_CAMERA_MESSAGE;
    audioVolume.disabled = true;
    setAudioButtonState(audioToggle, {
      label: "Activar audio",
      disabled: true,
      pressed: false,
    });
    syncCardAudioButtons();
    return;
  }

  if (activeUsesEmbeddedViewer) {
    syncEmbeddedViewerAudio(activeCamera);
    audioSummary.textContent = audioEnabled
      ? supportsEmbeddedViewerVolumeSync(activeCamera)
        ? `Audio activo en ${getCameraDisplayName(activeCamera, { uppercase: true })} al ${audioVolume.value}%.`
        : `Audio activo en ${getCameraDisplayName(activeCamera, { uppercase: true })}. El volumen se controla desde el visor web.`
      : `Audio disponible en ${getCameraDisplayName(activeCamera, { uppercase: true })}. Pulsa activar audio para quitar el mute del visor web.`;
    audioVolume.disabled = !supportsEmbeddedViewerVolumeSync(activeCamera);
    setAudioButtonState(audioToggle, {
      label: audioEnabled ? "Silenciar audio" : "Activar audio",
      disabled: false,
      pressed: audioEnabled,
    });
    syncCardAudioButtons();
    return;
  }

  if (!activeSupportsAudio) {
    audioSummary.textContent = `La cámara ${getCameraDisplayName(activeCamera, { uppercase: true })} no tiene audio disponible.`;
    audioVolume.disabled = true;
    setAudioButtonState(audioToggle, {
      label: "Sin audio",
      disabled: true,
      pressed: false,
    });
    syncCardAudioButtons();
    return;
  }

  audioVolume.disabled = false;
  setAudioButtonState(audioToggle, {
    label: enabledForPlayback ? "Silenciar audio" : "Activar audio",
    disabled: false,
    pressed: enabledForPlayback,
  });
  audioSummary.textContent = enabledForPlayback
    ? `Audio activo en ${getCameraDisplayName(activeCamera, { uppercase: true })} al ${audioVolume.value}%.`
    : `Audio disponible en ${getCameraDisplayName(activeCamera, { uppercase: true })}, pendiente de activación.`;
  syncCardAudioButtons();
}

function syncStreaming() {
  if (document.visibilityState === "hidden") return;
  if (!pageSupportsStreaming()) return;

  const desiredNames = new Set(getDesiredCameraNames());

  CAMERAS.forEach((camera) => {
    if (desiredNames.has(camera.name)) return;
    deactivateCamera(
      camera.name,
      activeCamera ? "En espera" : "Selecciona una cámara",
    );
  });

  CAMERAS.forEach((camera) => {
    const { name, dom_id: domId } = camera;
    if (!desiredNames.has(name)) return;
    if (embeddedViewerSessions.has(name) || connectInFlight.has(name) || reconnectTimers.has(name)) {
      return;
    }

    startCamera(camera).catch((error) => {
      if (!getDesiredCameraNames().includes(name)) {
        return;
      }
      const nextStatus = statusForCameraError(error);
      if (isRetryableCameraError(error)) {
        scheduleReconnect(camera, nextStatus);
        return;
      }
      clearReconnectTimer(name);
      setState(domId, nextStatus);
    });
  });
}

async function startCamera(camera) {
  const { name, dom_id: domId } = camera;
  if (connectInFlight.has(name)) return;
  connectInFlight.add(name);

  const token = (connectionTokens.get(name) || 0) + 1;
  connectionTokens.set(name, token);
  clearReconnectTimer(name);
  closePeer(name);
  closeEmbeddedViewer(name);
  hideCameraCardError(camera);
  try {
    const target = resolveCameraPlaybackTarget(name);
    if (target.mode === "iframe") {
      setState(domId, "Abriendo visor...");
      if (shouldUseAuthorizedViewerUrl(name, target.url)) {
        let viewerAccess;
        try {
          viewerAccess = await fetchAuthorizedViewerAccess(camera);
        } catch (err) {
          showCameraCardError(camera, "Error autenticando o cargando el visor protegido.");
          setState(domId, "Error autenticación visor");
          return;
        }
        if (viewerAccess && viewerAccess.error) {
          showCameraCardError(camera, viewerAccess.viewer_html || "Error autenticando o cargando el visor protegido.");
          setState(domId, "Error autenticación visor");
          return;
        }
        startEmbeddedViewer(camera, token, viewerAccess.viewerUrl, viewerAccess.viewerHtml);
      } else {
        startEmbeddedViewer(camera, token, target.url);
      }
      return;
    }

    if (target.mode === "unsupported" || target.mode === "none") {
      showCameraCardError(camera, "Fuente de cámara no soportada.");
      throw createCameraConnectionError("camera_source_not_supported", target.url || "missing_source");
    }

    const video = document.getElementById(`video-${domId}`);
    if (!video) {
      showCameraCardError(camera, `No existe elemento de video para ${name}`);
      throw new Error(`No existe elemento de video para ${name}`);
    }

    setCameraSurfaceMode(name, "video");
    setState(domId, "Cargando video...");
    if (target.mode === "hls") {
      await attachHlsPlayback(name, video, target.url);
    } else {
      video.src = target.url;
      await playVideoElement(video);
    }

    if (connectionTokens.get(name) !== token) {
      closePeer(name);
      return;
    }
    if (supportsManagedAudioPlayback(name)) {
      markCameraAudioAvailable(name);
    }
    reconnectDelayMs.set(name, 800);
    setState(domId, "En vivo");
    applyAudioState();
  } catch (error) {
    closePeer(name);
    showCameraCardError(camera, error.message || "Error cargando el stream");
    throw error;
  } finally {
    connectInFlight.delete(name);
  }
}

async function fetchJson(url, options = {}) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), options.timeoutMs || 5000);
  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
    if (!response.ok) {
      const contentType = response.headers.get("content-type") || "";
      let message = `HTTP ${response.status}`;
      try {
        if (contentType.includes("application/json")) {
          const payload = await response.json();
          if (payload && typeof payload === "object" && payload.error) {
            message = String(payload.error);
          } else {
            message = JSON.stringify(payload);
          }
        } else {
          const text = await response.text();
          if (text.trim()) {
            message = text.trim();
          }
        }
      } catch (error) {}
      throw new Error(message);
    }
    return await response.json();
  } finally {
    clearTimeout(timeoutId);
  }
}

async function registerCamera(event) {
  event.preventDefault();
  if (!cameraRegisterName || !cameraRegisterSource || !cameraRegisterLat || !cameraRegisterLon || !cameraRegisterSubmit) return;

  const cameraName = cameraRegisterName.value.trim();
  const source = cameraRegisterSource.value.trim();
  const lat = Number(cameraRegisterLat.value);
  const lon = Number(cameraRegisterLon.value);
  if (!cameraName || !source || !cameraRegisterLat.value.trim() || !cameraRegisterLon.value.trim()) {
    setCameraRegisterFeedback("Completa el nombre, la URL y la ubicación de la cámara.", "error");
    return;
  }
  const sourceProtocolError = cameraSourceProtocolError(source);
  if (sourceProtocolError) {
    setCameraRegisterFeedback(sourceProtocolError, "error");
    return;
  }
  if (getCameraByName(cameraName)) {
    setCameraRegisterFeedback("Ese nombre ya existe en el sistema.", "error");
    return;
  }
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
    setCameraRegisterFeedback("Selecciona una ubicación válida en el mapa o ingresa coordenadas correctas.", "error");
    return;
  }

  const originalLabel = cameraRegisterSubmit.textContent || "Registrar cámara";
  cameraRegisterSubmit.disabled = true;
  cameraRegisterSubmit.textContent = "Registrando...";
  setCameraRegisterFeedback("Guardando la cámara en la configuración...", "info");

  try {
    const payload = await fetchJson("/api/cameras", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        camera_name: cameraName,
        source,
        lat,
        lon,
      }),
      timeoutMs: 10000,
    });
    addRegisteredCamera(payload);
    resetCameraRegisterState();
    closeCameraRegisterModal();
  } catch (error) {
    setCameraRegisterFeedback(friendlyCameraRegisterError(error), "error");
  } finally {
    cameraRegisterSubmit.disabled = false;
    cameraRegisterSubmit.textContent = originalLabel;
  }
}

async function registerVehicle(event) {
  event.preventDefault();
  if (
    !vehicleRegisterType
    || !vehicleRegisterLabel
    || !vehicleRegisterIdentifier
    || !vehicleRegisterSubmit
    || !vehicleRegisterOrganization
    || !vehicleRegisterOwner
  ) return;

  const vehicleTypeCode = normalizeVehicleTypeCode(vehicleRegisterType.value || "");
  const isDrone = isDroneVehicleTypeCode(vehicleTypeCode);
  const telemetryMode = String(vehicleRegisterTelemetryMode && vehicleRegisterTelemetryMode.value || "manual").trim().toLowerCase() || "manual";
  const organizationId = String(vehicleRegisterOrganization.value || "").trim();
  const ownerUserId = String(vehicleRegisterOwner.value || "").trim();
  const label = vehicleRegisterLabel.value.trim();
  const identifier = vehicleRegisterIdentifier.value.trim();
  const notes = vehicleRegisterNotes ? vehicleRegisterNotes.value.trim() : "";
  const apiDeviceId = vehicleRegisterApiDeviceId ? vehicleRegisterApiDeviceId.value.trim() : "";
  const cameraLinks = getVehicleRegisterSelectedCameraLinks();

  if (!label || !identifier) {
    setVehicleRegisterFeedback("Completa el nombre o alias y el identificador del vehículo.", "error");
    return;
  }
  if (!organizationId) {
    setVehicleRegisterFeedback("Selecciona la organización que será dueña del vehículo.", "error");
    return;
  }
  if (!ownerUserId) {
    setVehicleRegisterFeedback("Selecciona el propietario del vehículo.", "error");
    return;
  }
  if (!vehicleTypeCode) {
    setVehicleRegisterFeedback("Selecciona el tipo real del vehículo.", "error");
    return;
  }
  if (!["manual", "api"].includes(telemetryMode)) {
    setVehicleRegisterFeedback("Selecciona un modo válido de telemetría para el vehículo.", "error");
    return;
  }

  const originalLabel = vehicleRegisterSubmit.textContent || "Guardar vehículo";
  vehicleRegisterSubmit.disabled = true;
  vehicleRegisterSubmit.textContent = "Guardando...";
  setVehicleRegisterFeedback("Registrando vehículo en el sistema...", "info");

  try {
    const isEditing = Boolean(editingVehicleRegistrationId);
    const payload = await fetchJson(
      isEditing
        ? `/api/vehicle-registry/${encodeURIComponent(editingVehicleRegistrationId)}`
        : "/api/vehicle-registry",
      {
        method: isEditing ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          organizacion_id: organizationId,
          propietario_usuario_id: ownerUserId,
          vehicle_type_code: vehicleTypeCode,
          label,
          identifier,
          notes,
          telemetry_mode: telemetryMode,
          api_device_id: telemetryMode === "api" ? apiDeviceId : "",
          camera_links: cameraLinks,
        }),
        timeoutMs: 10000,
      },
    );
    selectedVehicleRegistryKey = vehicleRegistrySelectionKey({
      entry_kind: "manual",
      registration_id: payload && payload.registration_id,
      vehicle_type: payload && payload.vehicle_type,
      label: payload && payload.label,
      identifier: payload && payload.identifier,
      ts: payload && payload.ts,
    });
    await refreshVehicleRegistry();
    await refreshVehicleRegistryFormOptions();
    resetVehicleRegisterState();
    closeVehicleRegisterModal();
  } catch (error) {
    setVehicleRegisterFeedback(friendlyVehicleRegisterError(error), "error");
  } finally {
    vehicleRegisterSubmit.disabled = false;
    syncVehicleRegisterModalChrome();
  }
}

async function deleteVehicleRegistryEntry(registrationId, { closeModal = false } = {}) {
  const normalizedRegistrationId = normalizeVehicleRegistrationId(registrationId);
  if (!normalizedRegistrationId) return;

  const entry = findVehicleRegistryItemByRegistrationId(normalizedRegistrationId);
  const label = String(entry && (entry.label || entry.identifier) || "este vehículo").trim() || "este vehículo";
  const confirmed = window.confirm(`¿Deseas eliminar ${label}? Esta acción quitará su registro manual del sistema.`);
  if (!confirmed) return;

  if (vehicleRegisterDelete) {
    vehicleRegisterDelete.disabled = true;
  }
  setVehicleRegisterFeedback("Eliminando registro del vehículo...", "info");

  try {
    await fetchJson(`/api/vehicle-registry/${encodeURIComponent(normalizedRegistrationId)}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      timeoutMs: 10000,
    });
    if (selectedVehicleRegistryKey && entry && selectedVehicleRegistryKey === vehicleRegistrySelectionKey(entry)) {
      selectedVehicleRegistryKey = null;
    }
    await refreshVehicleRegistry();
    await refreshVehicleRegistryFormOptions();
    if (closeModal) {
      resetVehicleRegisterState();
      closeVehicleRegisterModal();
    }
  } catch (error) {
    setVehicleRegisterFeedback(friendlyVehicleRegisterError(error), "error");
  } finally {
    if (vehicleRegisterDelete) {
      vehicleRegisterDelete.disabled = false;
    }
  }
}

function normalizeUserAdminId(value) {
  const numeric = Number(value);
  return Number.isInteger(numeric) && numeric > 0 ? numeric : null;
}

function normalizeRoleAdminId(value) {
  const numeric = Number(value);
  return Number.isInteger(numeric) && numeric > 0 ? numeric : null;
}

function normalizeOrganizationAdminId(value) {
  const numeric = Number(value);
  return Number.isInteger(numeric) && numeric > 0 ? numeric : null;
}

function normalizeCameraAdminId(value) {
  const numeric = Number(value);
  return Number.isInteger(numeric) && numeric > 0 ? numeric : null;
}

function renderUserAdminRoleOptions(roles) {
  if (!userAdminRole) return;
  const source = Array.isArray(roles) ? roles : [];
  const currentValue = String(userAdminRole.value || "").trim().toLowerCase();
  const options = [
    '<option value="">Selecciona un rol</option>',
    ...source.map((item) => {
      const roleCode = String(item && (item.codigo || item.rol) || "").trim();
      const roleLabel = String(item && (item.nombre || item.label || roleCode) || "").trim();
      if (!roleCode) return "";
      const normalized = roleCode.toLowerCase();
      const optionLabel = roleLabel && roleLabel.toLowerCase() !== roleCode.toLowerCase()
        ? `${roleLabel} (${roleCode})`
        : roleLabel || roleCode;
      return `<option value="${escapeHtml(roleCode)}" ${normalized === currentValue ? "selected" : ""}>${escapeHtml(optionLabel)}</option>`;
    }),
  ].filter(Boolean);
  userAdminRole.innerHTML = options.join("");
}

function findSelectedRoleAdminItem(roles) {
  const source = Array.isArray(roles) ? roles : [];
  if (selectedRoleAdminId === null) return null;
  return source.find((item) => normalizeRoleAdminId(item && item.id) === selectedRoleAdminId) || null;
}

function findSelectedUserAdminItem(users) {
  const source = Array.isArray(users) ? users : [];
  if (selectedUserAdminId === null) return null;
  return source.find((item) => normalizeUserAdminId(item && item.id) === selectedUserAdminId) || null;
}

function findSelectedOrganizationAdminItem(organizations) {
  const source = Array.isArray(organizations) ? organizations : [];
  if (selectedOrganizationAdminId === null) return null;
  return source.find((item) => normalizeOrganizationAdminId(item && item.id) === selectedOrganizationAdminId) || null;
}

function findSelectedCameraAdminItem(cameras) {
  const source = Array.isArray(cameras) ? cameras : [];
  if (selectedCameraAdminId === null) return null;
  return source.find((item) => normalizeCameraAdminId(item && item.id) === selectedCameraAdminId) || null;
}

function isRoleAdminSectionVisible() {
  return Boolean(roleAdminForm && roleAdminForm.closest("[hidden]") === null);
}

function renderOrganizationAdminOwnerOptions(users) {
  if (!organizationAdminOwner) return;
  const source = Array.isArray(users) ? users : [];
  const currentValue = String(organizationAdminOwner.value || "").trim();
  const options = [
    '<option value="">Usuario a cargo</option>',
    ...source.map((item) => {
      const userId = normalizeUserAdminId(item && item.id);
      const username = String(item && item.usuario || "").trim();
      const displayName = String(item && (item.display_name || item.nombre || username) || "").trim();
      const roleLabel = String(item && (item.rol_label || item.rol_nombre || item.rol) || "").trim();
      if (!userId || !username) return "";
      const optionLabel = [displayName, username !== displayName ? `@${username}` : "", roleLabel]
        .filter(Boolean)
        .join(" · ");
      return `<option value="${escapeHtml(String(userId))}" ${String(userId) === currentValue ? "selected" : ""}>${escapeHtml(optionLabel)}</option>`;
    }),
  ].filter(Boolean);
  organizationAdminOwner.innerHTML = options.join("");
}

function renderCameraAdminOrganizationOptions(organizations) {
  if (!cameraAdminOrganization) return;
  const source = Array.isArray(organizations) ? organizations : [];
  const currentValue = String(cameraAdminOrganization.value || "").trim();
  const options = [
    '<option value="">Selecciona una organización</option>',
    ...source.map((item) => {
      const organizationId = normalizeOrganizationAdminId(item && item.id);
      const name = String(item && item.nombre || "").trim();
      const owner = String(item && (item.propietario_display_name || item.propietario_usuario) || "").trim();
      if (!organizationId || !name) return "";
      const optionLabel = [name, owner].filter(Boolean).join(" · ");
      return `<option value="${escapeHtml(String(organizationId))}" ${String(organizationId) === currentValue ? "selected" : ""}>${escapeHtml(optionLabel)}</option>`;
    }),
  ].filter(Boolean);
  cameraAdminOrganization.innerHTML = options.join("");
}

function renderCameraAdminOwnerOptions(users) {
  if (!cameraAdminOwner) return;
  const source = Array.isArray(users) ? users : [];
  const currentValue = String(cameraAdminOwner.value || "").trim();
  const options = [
    '<option value="">Selecciona un responsable</option>',
    ...source.map((item) => {
      const userId = normalizeUserAdminId(item && item.id);
      const username = String(item && item.usuario || "").trim();
      const displayName = String(item && (item.display_name || item.nombre || username) || "").trim();
      const roleLabel = String(item && (item.rol_label || item.rol_nombre || item.rol) || "").trim();
      if (!userId || !username) return "";
      const optionLabel = [displayName, username !== displayName ? `@${username}` : "", roleLabel]
        .filter(Boolean)
        .join(" · ");
      return `<option value="${escapeHtml(String(userId))}" ${String(userId) === currentValue ? "selected" : ""}>${escapeHtml(optionLabel)}</option>`;
    }),
  ].filter(Boolean);
  cameraAdminOwner.innerHTML = options.join("");
}

function normalizeCameraAdminBrandCode(value) {
  return String(value || "").trim().toLowerCase();
}

function normalizeCameraAdminProtocolCode(value) {
  return String(value || "").trim().toLowerCase();
}

function cameraAdminSelectedTypeCode() {
  return String(cameraAdminType && cameraAdminType.value || "").trim().toLowerCase();
}

function cameraAdminIsMovingType(typeCode = cameraAdminSelectedTypeCode()) {
  return typeCode === "vehicle" || typeCode === "drone";
}

function cameraAdminUsesRtspAssistantType(typeCode = cameraAdminSelectedTypeCode()) {
  return Boolean(typeCode) && !cameraAdminIsMovingType(typeCode);
}

function getCameraAdminBrandPresets() {
  const source = Array.isArray(cameraAdminOptionCatalog.brand_presets) && cameraAdminOptionCatalog.brand_presets.length > 0
    ? cameraAdminOptionCatalog.brand_presets
    : DEFAULT_CAMERA_BRAND_PRESETS;
  const allowedPresets = new Set(["hikvision", "dahua", "custom_path"]);
  return source
    .map((item) => ({
      code: String(item && item.code || "").trim(),
      label: String(item && (item.label || item.code) || "").trim(),
      description: String(item && item.description || "").trim(),
      default_port: Number(item && item.default_port) || 554,
      supports_channel: Boolean(item && item.supports_channel),
      supports_substream: Boolean(item && item.supports_substream),
      requires_custom_path: Boolean(item && item.requires_custom_path),
    }))
    .filter((item) => item.code && allowedPresets.has(normalizeCameraAdminBrandCode(item.code)))
    .map((item) => (
      normalizeCameraAdminBrandCode(item.code) === "custom_path"
        ? { ...item, label: "Personalizado", description: "Permite pegar manualmente la URL RTSP completa." }
        : item
    ));
}

function findCameraAdminBrandPreset(value) {
  const normalizedValue = normalizeCameraAdminBrandCode(value);
  if (!normalizedValue) return null;
  return getCameraAdminBrandPresets().find((item) => normalizeCameraAdminBrandCode(item.code) === normalizedValue) || null;
}

function findCameraAdminProtocolOption(value) {
  const normalizedValue = normalizeCameraAdminProtocolCode(value);
  if (!normalizedValue) return null;
  return (Array.isArray(cameraAdminOptionCatalog.protocols) ? cameraAdminOptionCatalog.protocols : []).find((item) => (
    normalizeCameraAdminProtocolCode(item && item.codigo) === normalizedValue
  )) || null;
}

function ensureCameraAdminDefaultProtocol({ force = false } = {}) {
  if (!cameraAdminProtocol) return "";
  const rtspOption = Array.from(cameraAdminProtocol.options || []).find((option) => (
    normalizeCameraAdminProtocolCode(option.value) === "rtsp"
  ));
  if (!rtspOption) {
    return String(cameraAdminProtocol.value || "").trim();
  }
  if (force || !String(cameraAdminProtocol.value || "").trim()) {
    cameraAdminProtocol.value = rtspOption.value;
  }
  return String(cameraAdminProtocol.value || rtspOption.value || "").trim();
}

function getCameraAdminStreamServer() {
  const server = cameraAdminOptionCatalog && typeof cameraAdminOptionCatalog === "object"
    ? cameraAdminOptionCatalog.stream_server
    : null;
  if (!server || typeof server !== "object") return null;
  const ip = String(server.ip_publica || "").trim();
  if (!ip) return null;
  return {
    id: Number(server.id) || 0,
    name: String(server.nombre || "").trim(),
    ip,
  };
}

function sanitizeCameraAdminStreamKey(value) {
  return String(value || "")
    .trim()
    .replace(/^\/+|\/+$/g, "")
    .replace(/\s+/g, "_")
    .replace(/[^A-Za-z0-9._-]+/g, "_");
}

function stripCameraAdminInferenceSuffix(value) {
  return String(value || "").trim().replace(/\s*-\s*INF\s*$/i, "").trim();
}

function buildCameraAdminInferenceName(name, inferenceEnabled) {
  const baseName = stripCameraAdminInferenceSuffix(name);
  if (!baseName) return "";
  return inferenceEnabled ? `${baseName} - INF` : baseName;
}

function syncCameraAdminInferenceName() {
  if (!cameraAdminName) return;
  const inferenceEnabled = String(cameraAdminInferenceEnabled && cameraAdminInferenceEnabled.value || "false").trim() === "true";
  const normalizedName = buildCameraAdminInferenceName(cameraAdminName.value, inferenceEnabled);
  if (normalizedName && cameraAdminName.value !== normalizedName) {
    cameraAdminName.value = normalizedName;
  } else if (!normalizedName && cameraAdminName.value.trim()) {
    cameraAdminName.value = stripCameraAdminInferenceSuffix(cameraAdminName.value);
  }
}

function isCameraAdminInferenceEnabledSelected(inferenceEnabled) {
  if (typeof inferenceEnabled === "boolean") {
    return inferenceEnabled;
  }
  return String(cameraAdminInferenceEnabled && cameraAdminInferenceEnabled.value || "false").trim() === "true";
}

function buildCameraAdminGeneratedStreamPath({ uniqueCode, inferenceEnabled } = {}) {
  const normalizedKey = sanitizeCameraAdminStreamKey(uniqueCode);
  if (!normalizedKey) {
    return "";
  }

  return isCameraAdminInferenceEnabledSelected(inferenceEnabled)
    ? `${normalizedKey}/INFERENCE`
    : normalizedKey;
}

function getCameraAdminGeneratedStreamScheme(protocolCode) {
  switch (normalizeCameraAdminProtocolCode(protocolCode)) {
    case "https":
      return "https";
    case "rtmp":
      return "rtmp";
    case "hls":
    case "http":
    case "rtsp":
    case "webrtc":
      return "http";
    default:
      return "";
  }
}

function getCameraAdminViewerProtocolOption(protocolCode) {
  const normalizedProtocol = normalizeCameraAdminProtocolCode(protocolCode);
  if (["webrtc", "http", "https"].includes(normalizedProtocol)) {
    return findCameraAdminProtocolOption(normalizedProtocol);
  }
  return findCameraAdminProtocolOption("webrtc")
    || findCameraAdminProtocolOption("http")
    || findCameraAdminProtocolOption("hls")
    || findCameraAdminProtocolOption(normalizedProtocol);
}

function buildCameraAdminGeneratedStreamUrl({ protocolCode, uniqueCode, inferenceEnabled } = {}) {
  const server = getCameraAdminStreamServer();
  const streamPath = buildCameraAdminGeneratedStreamPath({
    uniqueCode,
    inferenceEnabled,
  });
  const selectedProtocolCode = String(protocolCode || ensureCameraAdminDefaultProtocol() || "").trim();
  const protocol = getCameraAdminViewerProtocolOption(selectedProtocolCode);
  const viewerProtocolCode = protocol && protocol.codigo ? protocol.codigo : selectedProtocolCode;
  const scheme = getCameraAdminGeneratedStreamScheme(viewerProtocolCode);
  const port = Number(protocol && protocol.puerto_default);

  if (!server || !streamPath || !scheme || !Number.isFinite(port) || port <= 0) {
    return "";
  }

  const normalizedViewerProtocol = normalizeCameraAdminProtocolCode(viewerProtocolCode);
  if (normalizedViewerProtocol === "hls") {
    return `${scheme}://${server.ip}:${port}/${streamPath}/index.m3u8`;
  }
  return `${scheme}://${server.ip}:${port}/${streamPath}`;
}

function canCameraAdminAutoGenerateStreamUrl() {
  return Boolean(buildCameraAdminGeneratedStreamUrl({
    protocolCode: ensureCameraAdminDefaultProtocol(),
    uniqueCode: cameraAdminCode && cameraAdminCode.value,
    inferenceEnabled: isCameraAdminInferenceEnabledSelected(),
  }));
}

function syncCameraAdminGeneratedStreamUrl({ force = false } = {}) {
  if (!cameraAdminStreamUrl) return;
  const generatedUrl = buildCameraAdminGeneratedStreamUrl({
    protocolCode: ensureCameraAdminDefaultProtocol(),
    uniqueCode: cameraAdminCode && cameraAdminCode.value,
    inferenceEnabled: isCameraAdminInferenceEnabledSelected(),
  });
  const currentValue = cameraAdminStreamUrl.value.trim();
  const canOverwrite = force || cameraAdminStreamUrlAutoManaged || !currentValue;

  if (generatedUrl) {
    if (canOverwrite) {
      cameraAdminStreamUrl.value = generatedUrl;
      cameraAdminStreamUrlAutoManaged = true;
    } else {
      cameraAdminStreamUrlAutoManaged = currentValue === generatedUrl;
    }
    cameraAdminLastGeneratedStreamUrl = generatedUrl;
  } else {
    if (force || cameraAdminStreamUrlAutoManaged) {
      cameraAdminStreamUrl.value = "";
    }
    cameraAdminStreamUrlAutoManaged = false;
    cameraAdminLastGeneratedStreamUrl = "";
  }
}

function syncCameraAdminStreamUrlState() {
  const hasPreset = Boolean(getSelectedCameraAdminBrandPreset());
  const canGenerateStreamUrl = canCameraAdminAutoGenerateStreamUrl();
  const hasRtspUrl = Boolean(cameraAdminRtspUrl && cameraAdminRtspUrl.value.trim());
  const streamServer = getCameraAdminStreamServer();
  const protocol = getCameraAdminViewerProtocolOption(ensureCameraAdminDefaultProtocol());
  const normalizedPath = buildCameraAdminGeneratedStreamPath({
    uniqueCode: cameraAdminCode && cameraAdminCode.value,
    inferenceEnabled: isCameraAdminInferenceEnabledSelected(),
  });
  const generatedPreview = buildCameraAdminGeneratedStreamUrl({
    protocolCode: ensureCameraAdminDefaultProtocol(),
    uniqueCode: cameraAdminCode && cameraAdminCode.value,
    inferenceEnabled: isCameraAdminInferenceEnabledSelected(),
  });

  if (cameraAdminStreamUrl) {
    cameraAdminStreamUrl.required = !hasPreset && !hasRtspUrl && !canGenerateStreamUrl;
    cameraAdminStreamUrl.placeholder = canGenerateStreamUrl
      ? "Se completará automáticamente con el visor WebRTC de MediaMTX"
      : "https://.../index.m3u8 o https://.../visor/";
  }
  if (cameraAdminStreamUrlHelp) {
    cameraAdminStreamUrlHelp.textContent = canGenerateStreamUrl
      ? `Se genera automáticamente con ${streamServer && streamServer.name ? streamServer.name : "MediaMTX"} como visor WebRTC: ${generatedPreview}`
      : normalizedPath && protocol && streamServer
        ? "No pude generar la URL del stream con el protocolo seleccionado."
        : "Si completas el código único, la aplicación genera automáticamente la URL web del stream para el visor.";
  }
}

function getCameraAdminBrandValue() {
  if (!cameraAdminBrand) return "";
  return String(cameraAdminBrand.value || "").trim();
}

function getSelectedCameraAdminBrandPreset() {
  if (!cameraAdminBrand) return null;
  const selectedValue = String(cameraAdminBrand.value || "").trim();
  if (!selectedValue || normalizeCameraAdminBrandCode(selectedValue) === "custom_path") {
    return null;
  }
  return findCameraAdminBrandPreset(selectedValue);
}

function setCameraAdminRtspPreview(message) {
  if (!cameraAdminRtspPreview) return;
  cameraAdminRtspPreview.textContent = String(message || "La URL generada aparecerá en el campo “URL RTSP”.");
}

function resetCameraAdminRtspBuilderFields() {
  if (cameraAdminRtspIp) cameraAdminRtspIp.value = "";
  if (cameraAdminRtspPort) cameraAdminRtspPort.value = "";
  if (cameraAdminRtspChannel) cameraAdminRtspChannel.value = "";
  if (cameraAdminRtspSubstream) cameraAdminRtspSubstream.value = "false";
  if (cameraAdminRtspPath) cameraAdminRtspPath.value = "";
  setCameraAdminRtspPreview("");
}

function deriveCameraAdminRtspDraft(camera) {
  const emptyDraft = {
    ip: "",
    port: "",
    channel: "",
    substream: "false",
    path: "",
  };
  const storedIp = String(camera && camera.ip_camaras_fijas || "").trim();
  const rtspUrl = String(camera && camera.url_rtsp || "").trim();
  const fallbackStreamUrl = String(camera && camera.url_stream || "").trim();
  const rawUrl = rtspUrl || (
    fallbackStreamUrl.toLowerCase().startsWith("rtsp://")
      ? fallbackStreamUrl
      : ""
  );
  const brandPreset = findCameraAdminBrandPreset(camera && camera.marca);
  if (!brandPreset) {
    return {
      ...emptyDraft,
      ip: storedIp,
    };
  }
  if (!rawUrl) {
    return {
      ...emptyDraft,
      ip: storedIp,
    };
  }

  let parsed;
  try {
    parsed = new URL(rawUrl);
  } catch (error) {
    return emptyDraft;
  }

  const draft = {
    ip: storedIp || String(parsed.hostname || "").trim(),
    port: String(parsed.port || "").trim(),
    channel: "",
    substream: "false",
    path: "",
  };
  const pathName = String(parsed.pathname || "");

  switch (brandPreset.code) {
    case "hikvision": {
      const match = pathName.match(/\/Streaming\/Channels\/(\d+)(01|02)\/?$/i);
      if (match) {
        draft.channel = String(Number(match[1]) || 1);
        draft.substream = match[2] === "02" ? "true" : "false";
      }
      break;
    }
    case "dahua": {
      draft.channel = String(parsed.searchParams.get("channel") || "").trim();
      draft.substream = String(parsed.searchParams.get("subtype") || "0") === "1" ? "true" : "false";
      break;
    }
    case "uniview": {
      const match = pathName.match(/\/media\/video([12])\/?$/i);
      if (match) {
        draft.substream = match[1] === "2" ? "true" : "false";
      }
      break;
    }
    case "generic": {
      const match = pathName.match(/\/stream([12])\/?$/i);
      if (match) {
        draft.substream = match[1] === "2" ? "true" : "false";
      }
      break;
    }
    case "custom_path":
      draft.path = `${pathName.replace(/^\/+/, "")}${parsed.search || ""}`;
      break;
    default:
      break;
  }

  return draft;
}

function applyCameraAdminRtspDraft(draft) {
  const nextDraft = draft && typeof draft === "object" ? draft : {};
  if (cameraAdminRtspIp) cameraAdminRtspIp.value = String(nextDraft.ip || "").trim();
  if (cameraAdminRtspPort) cameraAdminRtspPort.value = String(nextDraft.port || "").trim();
  if (cameraAdminRtspChannel) cameraAdminRtspChannel.value = String(nextDraft.channel || "").trim();
  if (cameraAdminRtspSubstream) cameraAdminRtspSubstream.value = String(nextDraft.substream || "false") === "true" ? "true" : "false";
  if (cameraAdminRtspPath) cameraAdminRtspPath.value = String(nextDraft.path || "").trim();
  setCameraAdminRtspPreview("");
}

function getCameraAdminCurrentRtspDraft() {
  return {
    ip: cameraAdminRtspIp ? cameraAdminRtspIp.value.trim() : "",
    port: cameraAdminRtspPort ? cameraAdminRtspPort.value.trim() : "",
    channel: cameraAdminRtspChannel ? cameraAdminRtspChannel.value.trim() : "",
    substream: cameraAdminRtspSubstream && cameraAdminRtspSubstream.value === "true" ? "true" : "false",
    path: cameraAdminRtspPath ? cameraAdminRtspPath.value.trim() : "",
  };
}

function cameraAdminRtspDraftsMatch(leftDraft, rightDraft) {
  const left = leftDraft && typeof leftDraft === "object" ? leftDraft : {};
  const right = rightDraft && typeof rightDraft === "object" ? rightDraft : {};
  return (
    String(left.ip || "").trim() === String(right.ip || "").trim()
    && String(left.port || "").trim() === String(right.port || "").trim()
    && String(left.channel || "").trim() === String(right.channel || "").trim()
    && (String(left.substream || "false").trim() === "true" ? "true" : "false")
      === (String(right.substream || "false").trim() === "true" ? "true" : "false")
    && String(left.path || "").trim() === String(right.path || "").trim()
  );
}

function shouldRegenerateCameraAdminRtspUrl(selectedCamera, currentRtspUrl) {
  if (!getSelectedCameraAdminBrandPreset()) {
    return false;
  }

  const currentDraft = getCameraAdminCurrentRtspDraft();
  if (!currentDraft.ip) {
    return false;
  }

  const originalDraft = deriveCameraAdminRtspDraft(selectedCamera);
  if (cameraAdminRtspDraftsMatch(currentDraft, originalDraft)) {
    return false;
  }

  const originalRtspUrl = String(selectedCamera && selectedCamera.url_rtsp || "").trim();
  const normalizedCurrentRtspUrl = String(currentRtspUrl || "").trim();
  return !normalizedCurrentRtspUrl || normalizedCurrentRtspUrl === originalRtspUrl;
}

function setCameraAdminBrandSelection(rawBrand) {
  if (!cameraAdminBrand) return;
  const nextBrand = String(rawBrand || "").trim();
  const preset = findCameraAdminBrandPreset(nextBrand);
  if (preset) {
    cameraAdminBrand.value = preset.code;
  } else if (nextBrand) {
    cameraAdminBrand.value = normalizeCameraAdminBrandCode(nextBrand) === "personalizado" ? "custom_path" : "";
  } else {
    cameraAdminBrand.value = "";
  }
  syncCameraAdminBrandState();
}

function renderCameraAdminBrandOptions(brandPresets) {
  if (!cameraAdminBrand) return;
  const currentBrand = getCameraAdminBrandValue();
  const source = Array.isArray(brandPresets) && brandPresets.length > 0
    ? brandPresets
    : getCameraAdminBrandPresets();
  const options = [
    '<option value="">Selecciona una opción</option>',
    ...source.map((item) => {
      const code = String(item && item.code || "").trim();
      const label = String(item && (item.label || item.code) || "").trim();
      if (!code) return "";
      return `<option value="${escapeHtml(code)}">${escapeHtml(label)}</option>`;
    }),
  ].filter(Boolean);
  cameraAdminBrand.innerHTML = options.join("");
  setCameraAdminBrandSelection(currentBrand);
}

function syncCameraAdminBrandState() {
  const rtspAssistantEnabled = cameraAdminUsesRtspAssistantType();
  const selectedValue = String(cameraAdminBrand && cameraAdminBrand.value || "").trim();
  const selectedPreset = getSelectedCameraAdminBrandPreset();
  const isManualRtsp = normalizeCameraAdminBrandCode(selectedValue) === "custom_path";
  const hasPreset = Boolean(selectedPreset) && rtspAssistantEnabled;
  const showManualRtsp = rtspAssistantEnabled && isManualRtsp;
  if (cameraAdminRtspBuilder) {
    cameraAdminRtspBuilder.hidden = !hasPreset;
  }
  if (cameraAdminRtspUrlWrap) {
    cameraAdminRtspUrlWrap.hidden = !showManualRtsp;
  }
  if (cameraAdminRtspUrl) {
    cameraAdminRtspUrl.disabled = !showManualRtsp;
  }
  if (cameraAdminRtspIp) {
    cameraAdminRtspIp.disabled = !hasPreset;
  }
  if (cameraAdminRtspPort) {
    cameraAdminRtspPort.disabled = !hasPreset;
  }
  if (cameraAdminRtspGenerate) {
    cameraAdminRtspGenerate.disabled = !hasPreset;
  }
  if (cameraAdminRtspChannelWrap) {
    cameraAdminRtspChannelWrap.hidden = !Boolean(hasPreset && selectedPreset.supports_channel);
  }
  if (cameraAdminRtspChannel) {
    cameraAdminRtspChannel.disabled = !Boolean(hasPreset && selectedPreset.supports_channel);
  }
  if (cameraAdminRtspSubstreamWrap) {
    cameraAdminRtspSubstreamWrap.hidden = !Boolean(hasPreset && selectedPreset.supports_substream);
  }
  if (cameraAdminRtspSubstream) {
    cameraAdminRtspSubstream.disabled = !Boolean(hasPreset && selectedPreset.supports_substream);
  }
  if (cameraAdminRtspPathWrap) {
    cameraAdminRtspPathWrap.hidden = !Boolean(hasPreset && selectedPreset.requires_custom_path);
  }
  if (cameraAdminRtspPath) {
    cameraAdminRtspPath.disabled = !Boolean(hasPreset && selectedPreset.requires_custom_path);
  }

  if (cameraAdminBrandHelp) {
    cameraAdminBrandHelp.textContent = !rtspAssistantEnabled
      ? "Para cámaras montadas en dron o vehículo no hace falta configurar RTSP manual."
      : hasPreset
        ? `${selectedPreset.description} Usa “Usuario RTSP” y “Clave RTSP” para completar la URL automáticamente.`
        : showManualRtsp
          ? "Usa la opción Personalizado solo si ya tienes la URL RTSP completa."
          : "Selecciona Hikvision, Dahua o Personalizado para configurar el acceso RTSP.";
  }
  if (cameraAdminRtspCopy && hasPreset) {
    cameraAdminRtspCopy.textContent = `${selectedPreset.description} La URL RTSP se generará automáticamente con tus credenciales y parámetros.`;
  }
  if (cameraAdminRtspUrlHelp) {
    cameraAdminRtspUrlHelp.textContent = showManualRtsp
      ? "Pega la URL RTSP completa tal como la entrega la cámara o el DVR."
      : "La URL RTSP se generará automáticamente desde el asistente.";
  }
  if (hasPreset && cameraAdminRtspPort && !String(cameraAdminRtspPort.value || "").trim()) {
    cameraAdminRtspPort.value = String(selectedPreset.default_port || 554);
  }
  if (hasPreset && selectedPreset.supports_channel && cameraAdminRtspChannel && !String(cameraAdminRtspChannel.value || "").trim()) {
    cameraAdminRtspChannel.value = "1";
  }
  ensureCameraAdminDefaultProtocol({ force: rtspAssistantEnabled });
  if (!hasPreset) {
    setCameraAdminRtspPreview("");
  }
  syncCameraAdminGeneratedStreamUrl();
  syncCameraAdminStreamUrlState();
}

function renderCameraAdminTypeOptions(cameraTypes) {
  if (!cameraAdminType) return;
  const source = Array.isArray(cameraTypes) ? cameraTypes : [];
  const currentValue = String(cameraAdminType.value || "").trim().toLowerCase();
  const options = [
    '<option value="">Selecciona el tipo</option>',
    ...source.map((item) => {
      const code = String(item && item.codigo || "").trim();
      const label = String(item && (item.nombre || item.codigo) || "").trim();
      if (!code) return "";
      return `<option value="${escapeHtml(code)}" ${code.toLowerCase() === currentValue ? "selected" : ""}>${escapeHtml(label)}</option>`;
    }),
  ].filter(Boolean);
  cameraAdminType.innerHTML = options.join("");
}

function renderCameraAdminProtocolOptions(protocols) {
  if (!cameraAdminProtocol) return;
  const source = Array.isArray(protocols) ? protocols : [];
  const currentValue = String(cameraAdminProtocol.value || "").trim().toLowerCase();
  const options = [
    '<option value="">Selecciona el protocolo</option>',
    ...source.map((item) => {
      const code = String(item && item.codigo || "").trim();
      const label = String(item && (item.nombre || item.codigo) || "").trim();
      if (!code) return "";
      const port = Number(item && item.puerto_default);
      const optionLabel = Number.isFinite(port) && port > 0 ? `${label} · ${port}` : label;
      return `<option value="${escapeHtml(code)}" ${code.toLowerCase() === currentValue ? "selected" : ""}>${escapeHtml(optionLabel)}</option>`;
    }),
  ].filter(Boolean);
  cameraAdminProtocol.innerHTML = options.join("");
  ensureCameraAdminDefaultProtocol({ force: true });
}

function vehicleMatchesSelectedCameraType(vehicle, cameraTypeCode) {
  const vehicleTypeCode = String(vehicle && vehicle.tipo_vehiculo_codigo || "").trim().toLowerCase();
  const isDroneVehicle = vehicleTypeCode.startsWith("drone");
  if (cameraTypeCode === "drone") return isDroneVehicle;
  if (cameraTypeCode === "vehicle") return !isDroneVehicle;
  return false;
}

function renderCameraAdminVehicleOptions(vehicles) {
  if (!cameraAdminVehicle) return;
  const source = Array.isArray(vehicles) ? vehicles : [];
  const currentValue = String(cameraAdminVehicle.value || "").trim();
  const selectedType = cameraAdminSelectedTypeCode();
  const filteredVehicles = selectedType === "vehicle" || selectedType === "drone"
    ? source.filter((vehicle) => vehicleMatchesSelectedCameraType(vehicle, selectedType))
    : [];
  const options = [
    '<option value="">Selecciona un vehículo</option>',
    ...filteredVehicles.map((item) => {
      const vehicleId = normalizeCameraAdminId(item && item.id);
      const name = String(item && item.nombre || "").trim();
      const plate = String(item && item.placa || "").trim();
      const typeLabel = String(item && (item.tipo_vehiculo_nombre || item.tipo_vehiculo_codigo) || "").trim();
      if (!vehicleId || !name) return "";
      const optionLabel = [name, plate, typeLabel].filter(Boolean).join(" · ");
      return `<option value="${escapeHtml(String(vehicleId))}" ${String(vehicleId) === currentValue ? "selected" : ""}>${escapeHtml(optionLabel)}</option>`;
    }),
  ].filter(Boolean);
  cameraAdminVehicle.innerHTML = options.join("");
}

function syncCameraAdminTypeState() {
  const selectedType = cameraAdminSelectedTypeCode();
  const isMoving = cameraAdminIsMovingType(selectedType);
  const isStaticLike = Boolean(selectedType) && !isMoving;

  if (cameraAdminStaticFields) {
    cameraAdminStaticFields.hidden = !isStaticLike;
  }
  if (cameraAdminVehicleFields) {
    cameraAdminVehicleFields.hidden = !isMoving;
  }
  if (cameraAdminProtocolWrap) {
    cameraAdminProtocolWrap.hidden = true;
  }
  if (cameraAdminBrandWrap) {
    cameraAdminBrandWrap.hidden = isMoving;
  }
  if (cameraAdminModelWrap) {
    cameraAdminModelWrap.hidden = isMoving;
  }
  if (cameraAdminSerialWrap) {
    cameraAdminSerialWrap.hidden = isMoving;
  }
  if (cameraAdminStreamUserWrap) {
    cameraAdminStreamUserWrap.hidden = isMoving;
  }
  if (cameraAdminStreamPasswordWrap) {
    cameraAdminStreamPasswordWrap.hidden = isMoving;
  }
  if (cameraAdminTypeHelp) {
    cameraAdminTypeHelp.textContent = isStaticLike
      ? "La cámara fija o PTZ necesita coordenadas y puede configurarse con el asistente RTSP."
      : isMoving
        ? "La cámara montada en dron o vehículo debe vincularse a un vehículo de la base para usar su posición actual."
        : "Si es fija o PTZ, tendrás que registrar su ubicación. Si es móvil, tendrás que enlazarla a un vehículo.";
  }

  if (cameraAdminLat) cameraAdminLat.disabled = !isStaticLike;
  if (cameraAdminLon) cameraAdminLon.disabled = !isStaticLike;
  if (cameraAdminAltitude) cameraAdminAltitude.disabled = !isStaticLike;
  if (cameraAdminAddress) cameraAdminAddress.disabled = !isStaticLike;
  if (cameraAdminReference) cameraAdminReference.disabled = !isStaticLike;
  if (cameraAdminVehicle) cameraAdminVehicle.disabled = !isMoving;
  if (cameraAdminVehiclePosition) cameraAdminVehiclePosition.disabled = !isMoving;
  if (cameraAdminMapOpen) {
    cameraAdminMapOpen.disabled = !isStaticLike;
  }
  if (cameraAdminMapSummary) {
    cameraAdminMapSummary.hidden = !isStaticLike;
  }
  if (!isStaticLike && isCameraAdminMapModalOpen()) {
    closeCameraAdminMapModal();
  }
  updateCameraAdminMapSummary();

  ensureCameraAdminDefaultProtocol({ force: true });
  renderCameraAdminVehicleOptions(cameraAdminOptionCatalog.vehicles);
  syncCameraAdminBrandState();
}

function syncRoleAdminFormState({ preserveDraft = true } = {}) {
  const selectedRole = findSelectedRoleAdminItem(lastRoleAdminSnapshot);
  const isEditing = Boolean(selectedRole);

  if (roleAdminDetailTitle) {
    roleAdminDetailTitle.textContent = isEditing
      ? `Editar ${String(selectedRole.nombre || selectedRole.codigo || "rol").trim() || "rol"}`
      : "Registrar nuevo rol";
  }

  if (roleAdminDetailCopy) {
    roleAdminDetailCopy.textContent = isEditing
      ? "Actualiza el código, el nombre visible o la jerarquía del rol seleccionado. Si tiene usuarios asignados, no podrás eliminarlo hasta liberarlo."
      : "Si seleccionas uno del panel derecho, aquí podrás ajustarlo o eliminarlo.";
  }

  if (roleAdminSubmit) {
    roleAdminSubmit.textContent = isEditing ? "Guardar rol" : "Crear rol";
  }

  if (roleAdminDelete) {
    roleAdminDelete.hidden = !isEditing;
    roleAdminDelete.disabled = !isEditing;
  }

  if (!preserveDraft || isEditing) {
    if (roleAdminCode) {
      roleAdminCode.value = isEditing ? String(selectedRole.codigo || selectedRole.rol || "") : "";
    }
    if (roleAdminName) {
      roleAdminName.value = isEditing ? String(selectedRole.nombre || selectedRole.label || "") : "";
    }
    if (roleAdminOrder) {
      roleAdminOrder.value = isEditing ? String(selectedRole.nivel_orden ?? "") : "";
    }
    if (roleAdminSystem) {
      roleAdminSystem.value = isEditing && selectedRole.es_sistema === false ? "false" : "true";
    }
  }
}

function resetRoleAdminForm({ preserveFeedback = false } = {}) {
  selectedRoleAdminId = null;
  if (roleAdminCode) roleAdminCode.value = "";
  if (roleAdminName) roleAdminName.value = "";
  if (roleAdminOrder) roleAdminOrder.value = "";
  if (roleAdminSystem) roleAdminSystem.value = "true";
  if (!preserveFeedback) {
    setRoleAdminFeedback("");
  }
  syncRoleAdminFormState({ preserveDraft: false });
  renderRoleAdminList(lastRoleAdminSnapshot);
}

function syncUserAdminFormState({ preserveDraft = true } = {}) {
  const selectedUser = findSelectedUserAdminItem(lastUserAdminSnapshot);
  const isEditing = Boolean(selectedUser);

  if (userAdminDetailTitle) {
    userAdminDetailTitle.textContent = isEditing
      ? `Editar ${String(selectedUser.usuario || "usuario").trim() || "usuario"}`
      : "Registrar nuevo usuario";
  }

  if (userAdminDetailCopy) {
    userAdminDetailCopy.textContent = isEditing
      ? "Actualiza el perfil general, el rol o la contraseña del usuario seleccionado. Si dejas la contraseña vacía, la actual se conserva."
      : "Completa el formulario para crear un acceso nuevo. Si seleccionas un usuario del panel derecho, aquí podrás actualizarlo o eliminarlo.";
  }

  if (userAdminPasswordHelp) {
    userAdminPasswordHelp.textContent = isEditing
      ? "Opcional al editar. Déjala en blanco para conservar la contraseña actual."
      : "Obligatoria al crear. Se guardará como credencial de acceso del nuevo usuario.";
  }

  if (userAdminSubmit) {
    userAdminSubmit.textContent = isEditing ? "Guardar cambios" : "Crear usuario";
  }

  if (userAdminDelete) {
    userAdminDelete.hidden = !isEditing;
    userAdminDelete.disabled = !isEditing;
  }

  if (!preserveDraft || isEditing) {
    if (userAdminUsername) {
      userAdminUsername.value = isEditing ? String(selectedUser.usuario || "") : "";
    }
    if (userAdminEmail) {
      userAdminEmail.value = isEditing ? String(selectedUser.email || "") : "";
    }
    if (userAdminName) {
      userAdminName.value = isEditing ? String(selectedUser.nombre || "") : "";
    }
    if (userAdminLastName) {
      userAdminLastName.value = isEditing ? String(selectedUser.apellido || "") : "";
    }
    if (userAdminPhone) {
      userAdminPhone.value = isEditing ? String(selectedUser.telefono || "") : "";
    }
    if (userAdminPassword) {
      userAdminPassword.value = "";
    }
    if (userAdminRole) {
      userAdminRole.value = isEditing ? String(selectedUser.rol || selectedUser.rol_codigo || "") : "";
    }
    if (userAdminActive) {
      userAdminActive.value = isEditing && selectedUser.activo === false ? "false" : "true";
    }
  }
}

function resetUserAdminForm({ preserveFeedback = false } = {}) {
  selectedUserAdminId = null;
  if (userAdminUsername) userAdminUsername.value = "";
  if (userAdminEmail) userAdminEmail.value = "";
  if (userAdminName) userAdminName.value = "";
  if (userAdminLastName) userAdminLastName.value = "";
  if (userAdminPhone) userAdminPhone.value = "";
  if (userAdminPassword) userAdminPassword.value = "";
  if (userAdminRole) userAdminRole.value = "";
  if (userAdminActive) userAdminActive.value = "true";
  if (!preserveFeedback) {
    setUserAdminFeedback("");
  }
  syncUserAdminFormState({ preserveDraft: false });
  renderUserAdminList(lastUserAdminSnapshot);
}

function syncOrganizationAdminFormState({ preserveDraft = true } = {}) {
  const selectedOrganization = findSelectedOrganizationAdminItem(lastOrganizationAdminSnapshot);
  const isEditing = Boolean(selectedOrganization);

  if (organizationAdminDetailTitle) {
    organizationAdminDetailTitle.textContent = isEditing
      ? `Editar ${String(selectedOrganization.nombre || "organizacion").trim() || "organizacion"}`
      : "Registrar nueva organización";
  }

  if (organizationAdminDetailCopy) {
    organizationAdminDetailCopy.textContent = isEditing
      ? "Actualiza el nombre, la descripcion, el propietario o el estado de la organizacion seleccionada."
      : "Completa el formulario para crear una organización nueva. Si seleccionas una del panel derecho, aquí podrás actualizarla o eliminarla.";
  }

  if (organizationAdminSubmit) {
    organizationAdminSubmit.textContent = isEditing ? "Guardar organización" : "Crear organización";
  }

  if (organizationAdminDelete) {
    organizationAdminDelete.hidden = !isEditing;
    organizationAdminDelete.disabled = !isEditing;
  }

  if (!preserveDraft || isEditing) {
    if (organizationAdminName) {
      organizationAdminName.value = isEditing ? String(selectedOrganization.nombre || "") : "";
    }
    if (organizationAdminDescription) {
      organizationAdminDescription.value = isEditing ? String(selectedOrganization.descripcion || "") : "";
    }
    if (organizationAdminOwner) {
      organizationAdminOwner.value = isEditing
        ? String(selectedOrganization.propietario_usuario_id || "")
        : "";
    }
    if (organizationAdminActive) {
      organizationAdminActive.value = isEditing && selectedOrganization.activa === false ? "false" : "true";
    }
  }
}

function resetOrganizationAdminForm({ preserveFeedback = false } = {}) {
  selectedOrganizationAdminId = null;
  if (organizationAdminName) organizationAdminName.value = "";
  if (organizationAdminDescription) organizationAdminDescription.value = "";
  if (organizationAdminOwner) organizationAdminOwner.value = "";
  if (organizationAdminActive) organizationAdminActive.value = "true";
  if (!preserveFeedback) {
    setOrganizationAdminFeedback("");
  }
  syncOrganizationAdminFormState({ preserveDraft: false });
  renderOrganizationAdminList(lastOrganizationAdminSnapshot);
}

function syncCameraAdminFormState({ preserveDraft = true } = {}) {
  const selectedCamera = findSelectedCameraAdminItem(lastCameraAdminSnapshot);
  const isEditing = Boolean(selectedCamera);

  if (cameraAdminDetailTitle) {
    cameraAdminDetailTitle.textContent = isEditing
      ? `Editar ${String(selectedCamera.nombre || "camara").trim() || "camara"}`
      : cameraAdminCreationMode === "rbox"
        ? "Registrar nueva R-BOX"
        : "Registrar nueva cámara";
  }

  if (cameraAdminDetailCopy) {
    cameraAdminDetailCopy.textContent = isEditing
      ? "Actualiza la cámara seleccionada, su organización, el stream o su modalidad fija/móvil. Si dejas la clave del stream vacía, la actual se conserva."
      : cameraAdminCreationMode === "rbox"
        ? "Prepara una R-BOX nueva con la base ROBIOTEC y completa sus datos operativos, ubicación o enlace móvil sin salir del directorio."
        : "Completa el formulario para crear una cámara nueva. Si seleccionas una del panel derecho, aquí podrás actualizarla o eliminarla.";
  }

  if (cameraAdminSubmit) {
    cameraAdminSubmit.textContent = isEditing
      ? "Guardar cámara"
      : cameraAdminCreationMode === "rbox"
        ? "Crear R-BOX"
        : "Crear cámara";
  }

  if (cameraAdminDelete) {
    cameraAdminDelete.hidden = !isEditing;
    cameraAdminDelete.disabled = !isEditing;
  }

  syncCameraAdminQuickActions(isEditing);

  if (!preserveDraft || isEditing) {
    if (cameraAdminName) cameraAdminName.value = isEditing ? String(selectedCamera.nombre || "") : "";
    if (cameraAdminDescription) cameraAdminDescription.value = isEditing ? String(selectedCamera.descripcion || "") : "";
    if (cameraAdminOrganization) {
      cameraAdminOrganization.value = isEditing ? String(selectedCamera.organizacion_id || "") : "";
    }
    if (cameraAdminOwner) {
      cameraAdminOwner.value = isEditing ? String(selectedCamera.propietario_usuario_id || "") : "";
    }
    if (cameraAdminType) {
      cameraAdminType.value = isEditing ? String(selectedCamera.tipo_camara_codigo || "") : "";
    }
    if (cameraAdminProtocol) {
      cameraAdminProtocol.value = isEditing ? String(selectedCamera.protocolo_codigo || "") : "";
    }
    if (cameraAdminStreamUrl) {
      cameraAdminStreamUrl.value = isEditing ? String(selectedCamera.url_stream || "") : "";
    }
    if (cameraAdminRtspUrl) {
      cameraAdminRtspUrl.value = isEditing ? String(selectedCamera.url_rtsp || "") : "";
    }
    if (cameraAdminCode) {
      cameraAdminCode.value = isEditing ? String(selectedCamera.codigo_unico || "") : "";
    }
    setCameraAdminBrandSelection(isEditing ? String(selectedCamera.marca || "") : "");
    if (cameraAdminModel) {
      cameraAdminModel.value = isEditing ? String(selectedCamera.modelo || "") : "";
    }
    if (cameraAdminSerial) {
      cameraAdminSerial.value = isEditing ? String(selectedCamera.numero_serie || "") : "";
    }
    if (cameraAdminStreamUser) {
      cameraAdminStreamUser.value = isEditing ? String(selectedCamera.usuario_stream || "") : "";
    }
    if (cameraAdminStreamPassword) {
      cameraAdminStreamPassword.value = "";
    }
    if (cameraAdminInferenceEnabled) {
      cameraAdminInferenceEnabled.value = isEditing && selectedCamera.hacer_inferencia === true ? "true" : "false";
    }
    if (cameraAdminActive) {
      cameraAdminActive.value = isEditing && selectedCamera.activa === false ? "false" : "true";
    }
    if (cameraAdminLat) {
      cameraAdminLat.value = isEditing && selectedCamera.latitud !== null && selectedCamera.latitud !== undefined
        ? String(selectedCamera.latitud)
        : "";
    }
    if (cameraAdminLon) {
      cameraAdminLon.value = isEditing && selectedCamera.longitud !== null && selectedCamera.longitud !== undefined
        ? String(selectedCamera.longitud)
        : "";
    }
    if (cameraAdminAltitude) {
      cameraAdminAltitude.value = isEditing && selectedCamera.altitud_m !== null && selectedCamera.altitud_m !== undefined
        ? String(selectedCamera.altitud_m)
        : "";
    }
    if (cameraAdminAddress) {
      cameraAdminAddress.value = isEditing ? String(selectedCamera.direccion || "") : "";
    }
    if (cameraAdminReference) {
      cameraAdminReference.value = isEditing ? String(selectedCamera.referencia || "") : "";
    }
    renderCameraAdminVehicleOptions(cameraAdminOptionCatalog.vehicles);
    if (cameraAdminVehicle) {
      cameraAdminVehicle.value = isEditing ? String(selectedCamera.vehiculo_id || "") : "";
    }
    if (cameraAdminVehiclePosition) {
      cameraAdminVehiclePosition.value = isEditing ? String(selectedCamera.vehiculo_posicion || "") : "";
    }
    applyCameraAdminRtspDraft(isEditing ? deriveCameraAdminRtspDraft(selectedCamera) : null);
  }

  syncCameraAdminInferenceName();

  cameraAdminLastGeneratedStreamUrl = buildCameraAdminGeneratedStreamUrl({
    protocolCode: ensureCameraAdminDefaultProtocol(),
    uniqueCode: cameraAdminCode && cameraAdminCode.value,
    inferenceEnabled: isCameraAdminInferenceEnabledSelected(),
  });
  cameraAdminStreamUrlAutoManaged = Boolean(
    cameraAdminLastGeneratedStreamUrl
    && cameraAdminStreamUrl
    && cameraAdminStreamUrl.value.trim() === cameraAdminLastGeneratedStreamUrl
  );
  syncCameraAdminGeneratedStreamUrl();
  syncCameraAdminTypeState();
  syncCameraAdminBrandState();
}

function resetCameraAdminForm({ preserveFeedback = false, creationMode = "camera" } = {}) {
  cameraAdminCreationMode = creationMode === "rbox" ? "rbox" : "camera";
  selectedCameraAdminId = null;
  if (cameraAdminName) cameraAdminName.value = "";
  if (cameraAdminDescription) cameraAdminDescription.value = "";
  if (cameraAdminOrganization) cameraAdminOrganization.value = "";
  if (cameraAdminOwner) cameraAdminOwner.value = "";
  if (cameraAdminType) cameraAdminType.value = "";
  if (cameraAdminProtocol) cameraAdminProtocol.value = "";
  if (cameraAdminStreamUrl) cameraAdminStreamUrl.value = "";
  if (cameraAdminRtspUrl) cameraAdminRtspUrl.value = "";
  if (cameraAdminCode) cameraAdminCode.value = "";
  if (cameraAdminBrand) cameraAdminBrand.value = "";
  if (cameraAdminBrandCustom) cameraAdminBrandCustom.value = "";
  if (cameraAdminModel) cameraAdminModel.value = "";
  if (cameraAdminSerial) cameraAdminSerial.value = "";
  if (cameraAdminStreamUser) cameraAdminStreamUser.value = "";
  if (cameraAdminStreamPassword) cameraAdminStreamPassword.value = "";
  if (cameraAdminInferenceEnabled) cameraAdminInferenceEnabled.value = "false";
  resetCameraAdminRtspBuilderFields();
  if (cameraAdminActive) cameraAdminActive.value = "true";
  if (cameraAdminLat) cameraAdminLat.value = "";
  if (cameraAdminLon) cameraAdminLon.value = "";
  if (cameraAdminAltitude) cameraAdminAltitude.value = "";
  if (cameraAdminAddress) cameraAdminAddress.value = "";
  if (cameraAdminReference) cameraAdminReference.value = "";
  if (cameraAdminVehicle) cameraAdminVehicle.value = "";
  if (cameraAdminVehiclePosition) cameraAdminVehiclePosition.value = "";
  cameraAdminStreamUrlAutoManaged = false;
  cameraAdminLastGeneratedStreamUrl = "";
  if (!preserveFeedback) {
    setCameraAdminFeedback("");
  }
  syncCameraAdminFormState({ preserveDraft: false });
  renderCameraAdminList(lastCameraAdminSnapshot);
}

function prepareCameraAdminRboxPreset() {
  resetCameraAdminForm({ preserveFeedback: true, creationMode: "rbox" });
  setCameraAdminBrandSelection("ROBIOTEC");
  if (cameraAdminCode) {
    cameraAdminCode.value = "R-BOX-";
  }
  if (cameraAdminName) {
    cameraAdminName.focus();
    cameraAdminName.select();
  }
  setCameraAdminFeedback("Base R-BOX lista. Completa nombre, organización, stream y el resto de datos para continuar.", "info");
}

function renderUserAdminSummary(users) {
  const source = Array.isArray(users) ? users : [];
  const scopedRoleCount = source.filter((item) => {
    const roleValue = item && (item.rol_normalizado || item.rol || item.rol_codigo);
    return normalizeAccessRoleValue(roleValue) === userAdminScopeRole;
  }).length;

  if (roleAdminTotal) {
    roleAdminTotal.textContent = String(lastRoleAdminSnapshot.length);
  }
  if (userAdminTotal) {
    userAdminTotal.textContent = String(source.length);
  }
  if (organizationAdminTotal) {
    organizationAdminTotal.textContent = String(lastOrganizationAdminSnapshot.length);
  }
  if (cameraAdminTotal) {
    cameraAdminTotal.textContent = String(lastCameraAdminSnapshot.length);
  }
  if (userAdminDevelopers) {
    userAdminDevelopers.textContent = String(scopedRoleCount);
  }
  if (userAdminUpdated) {
    userAdminUpdated.textContent = lastUserAdminUpdatedAt > 0
      ? formatDateTime(lastUserAdminUpdatedAt)
      : "--";
  }
}

function renderRoleAdminList(roles) {
  if (!roleAdminRailList) return;
  const source = Array.isArray(roles) ? roles : [];
  if (source.length === 0) {
    roleAdminRailList.innerHTML = '<div class="user-admin-empty">No hay roles registrados para mostrar todavía.</div>';
    return;
  }

  roleAdminRailList.innerHTML = source.map((item) => {
    const itemId = normalizeRoleAdminId(item && item.id);
    const roleCode = String(item && (item.codigo || item.rol) || "rol").trim() || "rol";
    const roleLabel = String(item && (item.nombre || item.label || roleCode) || roleCode).trim() || roleCode;
    const roleUsers = Number(item && item.usuarios_asignados || 0);
    const level = Number(item && item.nivel_orden || 0);
    const roleMeta = [
      `Nivel ${level}`,
      `${roleUsers} usuario${roleUsers === 1 ? "" : "s"}`,
      item && item.es_sistema ? "Sistema" : "Personalizado",
    ].join(" · ");
    return `
      <button
        class="user-admin-summary-item ${itemId === selectedRoleAdminId ? "is-active" : ""}"
        type="button"
        data-role-admin-id="${escapeHtml(String(itemId || ""))}"
      >
        <span class="user-admin-summary-top">
          <strong>${escapeHtml(roleLabel)}</strong>
          <span class="user-admin-role-pill">${escapeHtml(roleCode)}</span>
        </span>
        <span class="user-admin-summary-meta">${escapeHtml(roleMeta)}</span>
      </button>
    `;
  }).join("");
}

function renderUserAdminList(users) {
  if (!userAdminRailList) return;
  const source = Array.isArray(users) ? users : [];
  if (source.length === 0) {
    userAdminRailList.innerHTML = '<div class="user-admin-empty">No hay usuarios registrados para mostrar todavía.</div>';
    return;
  }

  userAdminRailList.innerHTML = source.map((item) => {
    const itemId = normalizeUserAdminId(item && item.id);
    const username = String(item && item.usuario || "usuario").trim() || "usuario";
    const roleLabel = String(item && (item.rol_label || item.rol_nombre || item.rol) || "sin rol").trim() || "sin rol";
    const displayName = String(item && item.display_name || "").trim();
    const email = String(item && item.email || "").trim();
    const activeLabel = item && item.activo === false ? "Inactiva" : "Activa";
    const meta = [displayName, email, activeLabel].filter(Boolean).join(" · ") || `ID ${String(itemId || "--")}`;
    return `
      <button
        class="user-admin-summary-item ${itemId === selectedUserAdminId ? "is-active" : ""}"
        type="button"
        data-user-admin-id="${escapeHtml(String(itemId || ""))}"
      >
        <span class="user-admin-summary-top">
          <strong>${escapeHtml(username)}</strong>
          <span class="user-admin-role-pill">${escapeHtml(roleLabel)}</span>
        </span>
        <span class="user-admin-summary-meta">${escapeHtml(meta)}</span>
      </button>
    `;
  }).join("");
}

function renderOrganizationAdminList(organizations) {
  if (!organizationAdminRailList) return;
  const source = Array.isArray(organizations) ? organizations : [];
  if (source.length === 0) {
    organizationAdminRailList.innerHTML = '<div class="user-admin-empty">No hay organizaciones registradas para mostrar todavía.</div>';
    return;
  }

  organizationAdminRailList.innerHTML = source.map((item) => {
    const itemId = normalizeOrganizationAdminId(item && item.id);
    const name = String(item && item.nombre || "organizacion").trim() || "organizacion";
    const ownerDisplay = String(item && (item.propietario_display_name || item.propietario_usuario) || "sin propietario").trim() || "sin propietario";
    const ownerRole = String(item && (item.propietario_rol_nombre || item.propietario_rol_codigo) || "").trim();
    const activeLabel = item && item.activa === false ? "Inactiva" : "Activa";
    const description = String(item && item.descripcion || "").trim();
    const meta = [ownerDisplay, ownerRole, activeLabel].filter(Boolean).join(" · ");
    return `
      <button
        class="user-admin-summary-item ${itemId === selectedOrganizationAdminId ? "is-active" : ""}"
        type="button"
        data-organization-admin-id="${escapeHtml(String(itemId || ""))}"
      >
        <span class="user-admin-summary-top">
          <strong>${escapeHtml(name)}</strong>
          <span class="user-admin-role-pill">${escapeHtml(activeLabel)}</span>
        </span>
        <span class="user-admin-summary-meta">${escapeHtml(description || meta || `ID ${String(itemId || "--")}`)}</span>
        <span class="user-admin-summary-meta">${escapeHtml(meta || `ID ${String(itemId || "--")}`)}</span>
      </button>
    `;
  }).join("");
}

function renderCameraAdminList(cameras) {
  if (!cameraAdminRailList) return;
  const source = Array.isArray(cameras) ? cameras : [];
  if (source.length === 0) {
    cameraAdminRailList.innerHTML = '<div class="user-admin-empty">No hay cámaras registradas para mostrar todavía.</div>';
    return;
  }

  cameraAdminRailList.innerHTML = source.map((item) => {
    const itemId = normalizeCameraAdminId(item && item.id);
    const name = String(item && item.nombre || "camara").trim() || "camara";
    const typeLabel = String(item && (item.tipo_camara_nombre || item.tipo_camara_codigo) || "").trim();
    const orgLabel = String(item && item.organizacion_nombre || "").trim();
    const activeLabel = item && item.activa === false ? "Inactiva" : "Activa";
    const motionLabel = item && item.vehiculo_nombre
      ? `${String(item.vehiculo_nombre || "").trim()}${item.vehiculo_posicion ? ` · ${String(item.vehiculo_posicion).trim()}` : ""}`
      : (item && item.latitud !== null && item.latitud !== undefined && item.longitud !== null && item.longitud !== undefined
        ? `Lat ${Number(item.latitud).toFixed(4)} · Lon ${Number(item.longitud).toFixed(4)}`
        : "Sin ubicación visible");
    const meta = [typeLabel, orgLabel, activeLabel, motionLabel].filter(Boolean).join(" · ");
    return `
      <button
        class="user-admin-summary-item ${itemId === selectedCameraAdminId ? "is-active" : ""}"
        type="button"
        data-camera-admin-id="${escapeHtml(String(itemId || ""))}"
      >
        <span class="user-admin-summary-top">
          <strong>${escapeHtml(name)}</strong>
          <span class="user-admin-role-pill">${escapeHtml(typeLabel || "Cámara")}</span>
        </span>
        <span class="user-admin-summary-meta">${escapeHtml(meta)}</span>
      </button>
    `;
  }).join("");
}

function renderCameraAdmin(cameras, options, { preserveDraft = true } = {}) {
  lastCameraAdminSnapshot = Array.isArray(cameras) ? [...cameras] : [];
  cameraAdminOptionCatalog = options && typeof options === "object"
    ? {
        organizations: Array.isArray(options.organizations) ? [...options.organizations] : [],
        owners: Array.isArray(options.owners) ? [...options.owners] : [],
        camera_types: Array.isArray(options.camera_types) ? [...options.camera_types] : [],
        protocols: Array.isArray(options.protocols) ? [...options.protocols] : [],
        vehicles: Array.isArray(options.vehicles) ? [...options.vehicles] : [],
        brand_presets: Array.isArray(options.brand_presets) ? [...options.brand_presets] : [],
        stream_server: options.stream_server && typeof options.stream_server === "object"
          ? { ...options.stream_server }
          : null,
      }
    : {
        organizations: [],
        owners: [],
        camera_types: [],
        protocols: [],
        vehicles: [],
        brand_presets: [],
        stream_server: null,
      };

  if (
    selectedCameraAdminId !== null
    && !lastCameraAdminSnapshot.some((item) => normalizeCameraAdminId(item && item.id) === selectedCameraAdminId)
  ) {
    selectedCameraAdminId = null;
  }

  renderCameraAdminOrganizationOptions(cameraAdminOptionCatalog.organizations);
  renderCameraAdminOwnerOptions(cameraAdminOptionCatalog.owners);
  renderCameraAdminTypeOptions(cameraAdminOptionCatalog.camera_types);
  renderCameraAdminProtocolOptions(cameraAdminOptionCatalog.protocols);
  renderCameraAdminVehicleOptions(cameraAdminOptionCatalog.vehicles);
  renderCameraAdminBrandOptions(cameraAdminOptionCatalog.brand_presets);
  syncCameraAdminFormState({ preserveDraft });
  renderCameraAdminList(lastCameraAdminSnapshot);
}

function renderUserAdmin(users, roles, { preserveDraft = true, roleOptions = roles } = {}) {
  lastUserAdminSnapshot = Array.isArray(users) ? [...users] : [];
  lastRoleAdminSnapshot = Array.isArray(roles) ? [...roles] : [];
  userAdminRoles = Array.isArray(roleOptions) ? [...roleOptions] : [];

  renderUserAdminRoleOptions(userAdminRoles);
  renderUserAdminSummary(lastUserAdminSnapshot);

  if (selectedRoleAdminId !== null && !findSelectedRoleAdminItem(lastRoleAdminSnapshot)) {
    selectedRoleAdminId = null;
  }
  if (selectedUserAdminId !== null && !findSelectedUserAdminItem(lastUserAdminSnapshot)) {
    selectedUserAdminId = null;
  }

  syncRoleAdminFormState({ preserveDraft });
  renderRoleAdminList(lastRoleAdminSnapshot);
  syncUserAdminFormState({ preserveDraft });
  renderUserAdminList(lastUserAdminSnapshot);
}

function renderOrganizationAdmin(organizations, users, { preserveDraft = true } = {}) {
  lastOrganizationAdminSnapshot = Array.isArray(organizations) ? [...organizations] : [];
  renderOrganizationAdminOwnerOptions(users);
  if (
    selectedOrganizationAdminId !== null
    && !findSelectedOrganizationAdminItem(lastOrganizationAdminSnapshot)
  ) {
    selectedOrganizationAdminId = null;
  }
  syncOrganizationAdminFormState({ preserveDraft });
  renderOrganizationAdminList(lastOrganizationAdminSnapshot);
}

async function refreshUserAdmin({ preserveDraft = true } = {}) {
  const shouldLoadUserPanel = Boolean(
    userAdminForm
    || userAdminRailList
    || userAdminTotal
    || userAdminDevelopers
    || roleAdminForm
    || roleAdminRailList
    || roleAdminTotal,
  );
  const shouldLoadOrganizationPanel = Boolean(
    organizationAdminForm
    || organizationAdminRailList
    || organizationAdminTotal,
  );
  const shouldLoadCameraPanel = Boolean(
    cameraAdminForm
    || cameraAdminRailList
    || cameraAdminTotal,
  );

  if (!shouldLoadUserPanel && !shouldLoadOrganizationPanel && !shouldLoadCameraPanel) return;

  try {
    const shouldLoadRoleDirectory = shouldLoadUserPanel && isRoleAdminSectionVisible();
    const [roleOptions, users, roles, organizations, cameraOptions, cameras] = await Promise.all([
      shouldLoadUserPanel
        ? fetchJson("/api/user-role-options", { timeoutMs: 4000 })
        : Promise.resolve([]),
      (shouldLoadUserPanel || shouldLoadOrganizationPanel || shouldLoadCameraPanel)
        ? fetchJson("/api/users", { timeoutMs: 4000 })
        : Promise.resolve([]),
      shouldLoadRoleDirectory
        ? fetchJson("/api/user-roles", { timeoutMs: 4000 })
        : Promise.resolve([]),
      (shouldLoadOrganizationPanel || shouldLoadCameraPanel)
        ? fetchJson("/api/organizations", { timeoutMs: 4000 })
        : Promise.resolve([]),
      shouldLoadCameraPanel
        ? fetchJson("/api/camera-form-options", { timeoutMs: 4000 })
        : Promise.resolve({}),
      shouldLoadCameraPanel
        ? fetchJson("/api/cameras", { timeoutMs: 4000 })
        : Promise.resolve([]),
    ]);
    lastUserAdminUpdatedAt = Math.floor(Date.now() / 1000);

    if (shouldLoadUserPanel) {
      renderUserAdmin(users, roles, { preserveDraft, roleOptions });
    } else {
      lastUserAdminSnapshot = Array.isArray(users) ? [...users] : [];
    }

    if (shouldLoadOrganizationPanel) {
      renderOrganizationAdmin(organizations, users, { preserveDraft });
    }
    if (shouldLoadCameraPanel) {
      renderCameraAdmin(cameras, cameraOptions, { preserveDraft });
    }

    renderUserAdminSummary(lastUserAdminSnapshot);
  } catch (error) {
    renderUserAdminSummary(lastUserAdminSnapshot);
    if (roleAdminRailList && !lastRoleAdminSnapshot.length) {
      roleAdminRailList.innerHTML = '<div class="user-admin-empty">No se pudo cargar el directorio de roles.</div>';
    }
    if (userAdminRailList && !lastUserAdminSnapshot.length) {
      userAdminRailList.innerHTML = '<div class="user-admin-empty">No se pudo cargar el directorio de usuarios.</div>';
    }
    if (organizationAdminRailList && !lastOrganizationAdminSnapshot.length) {
      organizationAdminRailList.innerHTML = '<div class="user-admin-empty">No se pudo cargar el directorio de organizaciones.</div>';
    }
    if (cameraAdminRailList && !lastCameraAdminSnapshot.length) {
      cameraAdminRailList.innerHTML = '<div class="user-admin-empty">No se pudo cargar el directorio de cámaras.</div>';
    }
    const message = friendlyRoleAdminError(error);
    setRoleAdminFeedback(message, "error");
    setUserAdminFeedback(friendlyUserAdminError(error), "error");
    setOrganizationAdminFeedback(friendlyOrganizationAdminError(error), "error");
    setCameraAdminFeedback(friendlyCameraAdminError(error), "error");
  }
}

async function submitRoleAdminForm(event) {
  event.preventDefault();
  if (!roleAdminCode || !roleAdminName || !roleAdminOrder || !roleAdminSubmit) return;

  const code = roleAdminCode.value.trim();
  const name = roleAdminName.value.trim();
  const level = roleAdminOrder.value.trim();
  const isSystem = String(roleAdminSystem && roleAdminSystem.value || "true").trim() !== "false";
  const isEditing = selectedRoleAdminId !== null;

  if (!code) {
    setRoleAdminFeedback("Ingresa un código para el rol.", "error");
    return;
  }
  if (!name) {
    setRoleAdminFeedback("Ingresa un nombre visible para el rol.", "error");
    return;
  }
  if (!level) {
    setRoleAdminFeedback("Ingresa el nivel jerárquico del rol.", "error");
    return;
  }

  const originalLabel = roleAdminSubmit.textContent || (isEditing ? "Guardar rol" : "Crear rol");
  roleAdminSubmit.disabled = true;
  if (roleAdminReset) roleAdminReset.disabled = true;
  if (roleAdminDelete) roleAdminDelete.disabled = true;
  roleAdminSubmit.textContent = isEditing ? "Guardando..." : "Creando...";
  setRoleAdminFeedback(
    isEditing ? "Actualizando rol en la base de datos..." : "Creando rol en la base de datos...",
    "info",
  );

  try {
    const payload = await fetchJson(
      isEditing ? `/api/user-roles/${selectedRoleAdminId}` : "/api/user-roles",
      {
        method: isEditing ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          codigo: code,
          nombre: name,
          nivel_orden: Number(level),
          es_sistema: isSystem,
        }),
        timeoutMs: 10000,
      },
    );

    const nextSelectedId = normalizeRoleAdminId(payload && payload.role && payload.role.id);
    selectedRoleAdminId = nextSelectedId;
    await refreshUserAdmin({ preserveDraft: false });
    setRoleAdminFeedback(
      isEditing ? "Rol actualizado correctamente." : "Rol creado correctamente.",
      "success",
    );
  } catch (error) {
    setRoleAdminFeedback(friendlyRoleAdminError(error), "error");
  } finally {
    roleAdminSubmit.disabled = false;
    if (roleAdminReset) roleAdminReset.disabled = false;
    roleAdminSubmit.textContent = originalLabel;
    syncRoleAdminFormState({ preserveDraft: true });
  }
}

async function deleteSelectedRoleAdmin() {
  if (selectedRoleAdminId === null || !roleAdminDelete) return;
  const selectedRole = findSelectedRoleAdminItem(lastRoleAdminSnapshot);
  const label = String(selectedRole && (selectedRole.nombre || selectedRole.codigo) || "este rol").trim() || "este rol";
  if (!window.confirm(`¿Eliminar el rol ${label}? Esta acción no se puede deshacer.`)) {
    return;
  }

  const originalLabel = roleAdminDelete.textContent || "Eliminar rol";
  roleAdminDelete.disabled = true;
  if (roleAdminSubmit) roleAdminSubmit.disabled = true;
  if (roleAdminReset) roleAdminReset.disabled = true;
  roleAdminDelete.textContent = "Eliminando...";
  setRoleAdminFeedback(`Eliminando ${label} del catálogo...`, "info");

  try {
    await fetchJson(`/api/user-roles/${selectedRoleAdminId}`, {
      method: "DELETE",
      timeoutMs: 10000,
    });
    selectedRoleAdminId = null;
    await refreshUserAdmin({ preserveDraft: false });
    setRoleAdminFeedback("Rol eliminado correctamente.", "success");
  } catch (error) {
    setRoleAdminFeedback(friendlyRoleAdminError(error), "error");
  } finally {
    roleAdminDelete.textContent = originalLabel;
    if (roleAdminSubmit) roleAdminSubmit.disabled = false;
    if (roleAdminReset) roleAdminReset.disabled = false;
    syncRoleAdminFormState({ preserveDraft: true });
  }
}

async function submitUserAdminForm(event) {
  event.preventDefault();
  if (!userAdminUsername || !userAdminEmail || !userAdminName || !userAdminRole || !userAdminSubmit) return;

  const username = userAdminUsername.value.trim();
  const email = userAdminEmail.value.trim();
  const name = userAdminName.value.trim();
  const lastName = userAdminLastName ? userAdminLastName.value.trim() : "";
  const phone = userAdminPhone ? userAdminPhone.value.trim() : "";
  const password = userAdminPassword ? userAdminPassword.value : "";
  const role = String(userAdminRole.value || "").trim();
  const active = String(userAdminActive && userAdminActive.value || "true").trim() !== "false";
  const isEditing = selectedUserAdminId !== null;

  if (!username) {
    setUserAdminFeedback("Ingresa un nombre de usuario.", "error");
    return;
  }
  if (!email) {
    setUserAdminFeedback("Ingresa un correo electrónico.", "error");
    return;
  }
  if (!name) {
    setUserAdminFeedback("Ingresa el nombre principal del usuario.", "error");
    return;
  }
  if (!role) {
    setUserAdminFeedback("Selecciona un rol para la cuenta.", "error");
    return;
  }
  if (!isEditing && !password.trim()) {
    setUserAdminFeedback("La contraseña es obligatoria al crear un usuario.", "error");
    return;
  }

  const originalLabel = userAdminSubmit.textContent || (isEditing ? "Guardar cambios" : "Crear usuario");
  userAdminSubmit.disabled = true;
  if (userAdminReset) userAdminReset.disabled = true;
  if (userAdminDelete) userAdminDelete.disabled = true;
  userAdminSubmit.textContent = isEditing ? "Guardando..." : "Creando...";
  setUserAdminFeedback(
    isEditing ? "Actualizando usuario en la base de datos..." : "Creando usuario en la base de datos...",
    "info",
  );

  try {
    const payload = await fetchJson(
      isEditing ? `/api/users/${selectedUserAdminId}` : "/api/users",
      {
        method: isEditing ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          usuario: username,
          email,
          nombre: name,
          apellido: lastName,
          telefono: phone,
          password,
          rol: role,
          activo: active,
        }),
        timeoutMs: 10000,
      },
    );

    const nextSelectedId = normalizeUserAdminId(payload && payload.user && payload.user.id);
    selectedUserAdminId = nextSelectedId;
    await refreshUserAdmin({ preserveDraft: false });
    setUserAdminFeedback(
      isEditing ? "Usuario actualizado correctamente." : "Usuario creado correctamente.",
      "success",
    );
  } catch (error) {
    setUserAdminFeedback(friendlyUserAdminError(error), "error");
  } finally {
    userAdminSubmit.disabled = false;
    if (userAdminReset) userAdminReset.disabled = false;
    userAdminSubmit.textContent = originalLabel;
    syncUserAdminFormState({ preserveDraft: true });
  }
}

async function deleteSelectedUserAdmin() {
  if (selectedUserAdminId === null || !userAdminDelete) return;
  const selectedUser = findSelectedUserAdminItem(lastUserAdminSnapshot);
  const label = String(selectedUser && selectedUser.usuario || "este usuario").trim() || "este usuario";
  if (!window.confirm(`¿Eliminar al usuario ${label}? Esta acción no se puede deshacer.`)) {
    return;
  }

  const originalLabel = userAdminDelete.textContent || "Eliminar usuario";
  userAdminDelete.disabled = true;
  if (userAdminSubmit) userAdminSubmit.disabled = true;
  if (userAdminReset) userAdminReset.disabled = true;
  userAdminDelete.textContent = "Eliminando...";
  setUserAdminFeedback(`Eliminando a ${label} del sistema...`, "info");

  try {
    await fetchJson(`/api/users/${selectedUserAdminId}`, {
      method: "DELETE",
      timeoutMs: 10000,
    });
    selectedUserAdminId = null;
    await refreshUserAdmin({ preserveDraft: false });
    setUserAdminFeedback("Usuario eliminado correctamente.", "success");
  } catch (error) {
    setUserAdminFeedback(friendlyUserAdminError(error), "error");
  } finally {
    userAdminDelete.textContent = originalLabel;
    if (userAdminSubmit) userAdminSubmit.disabled = false;
    if (userAdminReset) userAdminReset.disabled = false;
    syncUserAdminFormState({ preserveDraft: true });
  }
}

async function submitOrganizationAdminForm(event) {
  event.preventDefault();
  if (!organizationAdminName || !organizationAdminOwner || !organizationAdminSubmit) return;

  const name = organizationAdminName.value.trim();
  const description = organizationAdminDescription ? organizationAdminDescription.value.trim() : "";
  const ownerUserId = String(organizationAdminOwner.value || "").trim();
  const active = String(organizationAdminActive && organizationAdminActive.value || "true").trim() !== "false";
  const isEditing = selectedOrganizationAdminId !== null;

  if (!name) {
    setOrganizationAdminFeedback("Ingresa un nombre para la organización.", "error");
    return;
  }
  if (!ownerUserId) {
    setOrganizationAdminFeedback("Selecciona un propietario para la organización.", "error");
    return;
  }

  const originalLabel = organizationAdminSubmit.textContent || (isEditing ? "Guardar organización" : "Crear organización");
  organizationAdminSubmit.disabled = true;
  if (organizationAdminReset) organizationAdminReset.disabled = true;
  if (organizationAdminDelete) organizationAdminDelete.disabled = true;
  organizationAdminSubmit.textContent = isEditing ? "Guardando..." : "Creando...";
  setOrganizationAdminFeedback(
    isEditing ? "Actualizando organización en la base de datos..." : "Creando organización en la base de datos...",
    "info",
  );

  try {
    const payload = await fetchJson(
      isEditing ? `/api/organizations/${selectedOrganizationAdminId}` : "/api/organizations",
      {
        method: isEditing ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nombre: name,
          descripcion: description,
          propietario_usuario_id: Number(ownerUserId),
          activa: active,
        }),
        timeoutMs: 10000,
      },
    );

    const nextSelectedId = normalizeOrganizationAdminId(payload && payload.organization && payload.organization.id);
    selectedOrganizationAdminId = nextSelectedId;
    await refreshUserAdmin({ preserveDraft: false });
    setOrganizationAdminFeedback(
      isEditing ? "Organización actualizada correctamente." : "Organización creada correctamente.",
      "success",
    );
  } catch (error) {
    setOrganizationAdminFeedback(friendlyOrganizationAdminError(error), "error");
  } finally {
    organizationAdminSubmit.disabled = false;
    if (organizationAdminReset) organizationAdminReset.disabled = false;
    organizationAdminSubmit.textContent = originalLabel;
    syncOrganizationAdminFormState({ preserveDraft: true });
  }
}

async function deleteSelectedOrganizationAdmin() {
  if (selectedOrganizationAdminId === null || !organizationAdminDelete) return;
  const selectedOrganization = findSelectedOrganizationAdminItem(lastOrganizationAdminSnapshot);
  const label = String(selectedOrganization && selectedOrganization.nombre || "esta organización").trim() || "esta organización";
  if (!window.confirm(`¿Eliminar la organización ${label}? Esta acción no se puede deshacer.`)) {
    return;
  }

  const originalLabel = organizationAdminDelete.textContent || "Eliminar organización";
  organizationAdminDelete.disabled = true;
  if (organizationAdminSubmit) organizationAdminSubmit.disabled = true;
  if (organizationAdminReset) organizationAdminReset.disabled = true;
  organizationAdminDelete.textContent = "Eliminando...";
  setOrganizationAdminFeedback(`Eliminando ${label} del sistema...`, "info");

  try {
    await fetchJson(`/api/organizations/${selectedOrganizationAdminId}`, {
      method: "DELETE",
      timeoutMs: 10000,
    });
    selectedOrganizationAdminId = null;
    await refreshUserAdmin({ preserveDraft: false });
    setOrganizationAdminFeedback("Organización eliminada correctamente.", "success");
  } catch (error) {
    setOrganizationAdminFeedback(friendlyOrganizationAdminError(error), "error");
  } finally {
    organizationAdminDelete.textContent = originalLabel;
    if (organizationAdminSubmit) organizationAdminSubmit.disabled = false;
    if (organizationAdminReset) organizationAdminReset.disabled = false;
    syncOrganizationAdminFormState({ preserveDraft: true });
  }
}

function buildCameraAdminRtspPayload() {
  const preset = getSelectedCameraAdminBrandPreset();
  if (!preset) {
    throw new Error("invalid_camera_rtsp_brand");
  }

  const ip = cameraAdminRtspIp ? cameraAdminRtspIp.value.trim() : "";
  const port = cameraAdminRtspPort ? cameraAdminRtspPort.value.trim() : "";
  const channel = cameraAdminRtspChannel ? cameraAdminRtspChannel.value.trim() : "";
  const substream = cameraAdminRtspSubstream ? cameraAdminRtspSubstream.value === "true" : false;
  const customPath = cameraAdminRtspPath ? cameraAdminRtspPath.value.trim() : "";
  const streamUser = cameraAdminStreamUser ? cameraAdminStreamUser.value.trim() : "";
  const streamPassword = cameraAdminStreamPassword ? cameraAdminStreamPassword.value : "";

  if (!ip) {
    throw new Error("invalid_camera_rtsp_ip");
  }

  return {
    marca: preset.code,
    ip,
    puerto: port,
    canal: channel,
    substream,
    ruta_personalizada: customPath,
    usuario: streamUser,
    password: streamPassword,
  };
}

async function requestCameraAdminRtspUrlValue() {
  const payload = await fetchJson("/api/camera-rtsp-preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildCameraAdminRtspPayload()),
    timeoutMs: 8000,
  });
  return String(payload && payload.url || "").trim();
}

async function generateCameraAdminRtspUrl() {
  try {
    buildCameraAdminRtspPayload();
  } catch (error) {
    setCameraAdminFeedback(friendlyCameraAdminError(error), "error");
    return;
  }

  if (cameraAdminRtspGenerate) {
    cameraAdminRtspGenerate.disabled = true;
    cameraAdminRtspGenerate.textContent = "Generando...";
  }
  setCameraAdminRtspPreview("Generando la URL RTSP con la plantilla de la marca seleccionada...");

  try {
    const url = await requestCameraAdminRtspUrlValue();
    if (cameraAdminRtspUrl) {
      cameraAdminRtspUrl.value = url;
    }
    setCameraAdminRtspPreview("URL RTSP generada y copiada al campo “URL RTSP”.");
    setCameraAdminFeedback("La URL RTSP se generó correctamente a partir de la marca seleccionada.", "success");
  } catch (error) {
    setCameraAdminRtspPreview("");
    setCameraAdminFeedback(friendlyCameraAdminError(error), "error");
  } finally {
    if (cameraAdminRtspGenerate) {
      cameraAdminRtspGenerate.disabled = false;
      cameraAdminRtspGenerate.textContent = "Generar URL RTSP";
    }
  }
}

async function submitCameraAdminForm(event) {
  event.preventDefault();
  if (
    !cameraAdminName
    || !cameraAdminOrganization
    || !cameraAdminOwner
    || !cameraAdminType
    || !cameraAdminProtocol
    || !cameraAdminSubmit
  ) {
    return;
  }

  syncCameraAdminInferenceName();

  const name = cameraAdminName.value.trim();
  const selectedCamera = findSelectedCameraAdminItem(lastCameraAdminSnapshot);
  const description = cameraAdminDescription ? cameraAdminDescription.value.trim() : "";
  const organizationId = String(cameraAdminOrganization.value || "").trim();
  const ownerUserId = String(cameraAdminOwner.value || "").trim();
  const typeCode = String(cameraAdminType.value || "").trim();
  const isMovingType = cameraAdminIsMovingType(String(typeCode || "").trim().toLowerCase());
  const protocolCode = String(ensureCameraAdminDefaultProtocol({ force: true }) || "").trim();
  let streamUrl = cameraAdminStreamUrl ? cameraAdminStreamUrl.value.trim() : "";
  let rtspUrl = cameraAdminRtspUrl ? cameraAdminRtspUrl.value.trim() : "";
  const uniqueCode = cameraAdminCode ? cameraAdminCode.value.trim() : "";
  const brand = getCameraAdminBrandValue();
  const model = cameraAdminModel ? cameraAdminModel.value.trim() : "";
  const serial = cameraAdminSerial ? cameraAdminSerial.value.trim() : "";
  const streamUser = cameraAdminStreamUser ? cameraAdminStreamUser.value.trim() : "";
  const streamPassword = cameraAdminStreamPassword ? cameraAdminStreamPassword.value : "";
  const inferenceEnabled = String(cameraAdminInferenceEnabled && cameraAdminInferenceEnabled.value || "false").trim() === "true";
  const active = String(cameraAdminActive && cameraAdminActive.value || "true").trim() !== "false";
  const lat = cameraAdminLat ? cameraAdminLat.value.trim() : "";
  const lon = cameraAdminLon ? cameraAdminLon.value.trim() : "";
  const altitude = cameraAdminAltitude ? cameraAdminAltitude.value.trim() : "";
  const address = cameraAdminAddress ? cameraAdminAddress.value.trim() : "";
  const reference = cameraAdminReference ? cameraAdminReference.value.trim() : "";
  const vehicleId = cameraAdminVehicle ? String(cameraAdminVehicle.value || "").trim() : "";
  const vehiclePosition = cameraAdminVehiclePosition ? cameraAdminVehiclePosition.value.trim() : "";
  const isEditing = selectedCameraAdminId !== null;
  const creationLabel = cameraAdminCreationMode === "rbox" ? "R-BOX" : "cámara";

  if (!name) {
    setCameraAdminFeedback("Ingresa un nombre para la cámara.", "error");
    return;
  }
  if (!organizationId) {
    setCameraAdminFeedback("Selecciona una organización para la cámara.", "error");
    return;
  }
  if (!ownerUserId) {
    setCameraAdminFeedback("Selecciona un responsable para la cámara.", "error");
    return;
  }
  if (!typeCode) {
    setCameraAdminFeedback("Selecciona el tipo de cámara.", "error");
    return;
  }
  if (!protocolCode) {
    setCameraAdminFeedback("No pude resolver el protocolo interno de la cámara.", "error");
    return;
  }
  if (!isMovingType && !uniqueCode && !rtspUrl) {
    setCameraAdminFeedback("Ingresa el código único o configura una URL RTSP para la cámara.", "error");
    return;
  }
  if (isMovingType && !uniqueCode) {
    setCameraAdminFeedback("Las cámaras montadas en dron o vehículo necesitan código único para generar el stream interno.", "error");
    return;
  }
  if (!isMovingType) {
    const numericLat = Number(lat);
    const numericLon = Number(lon);
    if (
      !lat
      || !lon
      || !Number.isFinite(numericLat)
      || !Number.isFinite(numericLon)
      || (Math.abs(numericLat) < 0.000001 && Math.abs(numericLon) < 0.000001)
    ) {
      setCameraAdminFeedback("Las cámaras fijas o PTZ necesitan latitud y longitud.", "error");
      return;
    }
  }
  if (isMovingType && !vehicleId) {
    setCameraAdminFeedback("Las cámaras móviles deben quedar enlazadas a un vehículo.", "error");
    return;
  }

  const originalLabel = cameraAdminSubmit.textContent || (isEditing ? "Guardar cámara" : "Crear cámara");
  cameraAdminSubmit.disabled = true;
  if (cameraAdminReset) cameraAdminReset.disabled = true;
  if (cameraAdminRbox) cameraAdminRbox.disabled = true;
  if (cameraAdminDelete) cameraAdminDelete.disabled = true;
  cameraAdminSubmit.textContent = isEditing ? "Guardando..." : "Creando...";
  setCameraAdminFeedback(
    isEditing ? "Actualizando cámara en la base de datos..." : `Creando ${creationLabel} en la base de datos...`,
    "info",
  );

  try {
    if (!streamUrl) {
      streamUrl = buildCameraAdminGeneratedStreamUrl({
        protocolCode,
        uniqueCode,
        inferenceEnabled,
      });
      if (streamUrl) {
        if (cameraAdminStreamUrl) {
          cameraAdminStreamUrl.value = streamUrl;
        }
        cameraAdminStreamUrlAutoManaged = true;
        cameraAdminLastGeneratedStreamUrl = streamUrl;
      }
    }

    if (isMovingType) {
      rtspUrl = "";
    } else if (!rtspUrl || shouldRegenerateCameraAdminRtspUrl(selectedCamera, rtspUrl)) {
      const selectedBrandPreset = getSelectedCameraAdminBrandPreset();
      if (selectedBrandPreset) {
        setCameraAdminRtspPreview(
          rtspUrl
            ? "Regenerando la URL RTSP con los datos técnicos actualizados antes de guardar..."
            : "Generando la URL RTSP automáticamente antes de guardar...",
        );
        rtspUrl = await requestCameraAdminRtspUrlValue();
        if (cameraAdminRtspUrl) {
          cameraAdminRtspUrl.value = rtspUrl;
        }
      }
    }

    if (!streamUrl && !rtspUrl) {
      setCameraAdminFeedback(
        isMovingType
          ? "No pude generar la URL interna del stream. Revisa el código único de la cámara."
          : "Completa la configuración RTSP de la cámara o pega una URL RTSP válida.",
        "error",
      );
      return;
    }

    const payload = await fetchJson(
      isEditing ? `/api/cameras/${selectedCameraAdminId}` : "/api/cameras",
      {
        method: isEditing ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nombre: name,
          descripcion: description,
          organizacion_id: Number(organizationId),
          propietario_usuario_id: Number(ownerUserId),
          tipo_camara_codigo: typeCode,
          protocolo_codigo: protocolCode,
          url_stream: streamUrl,
          url_rtsp: rtspUrl,
          ip_camaras_fijas: !isMovingType && cameraAdminRtspIp ? cameraAdminRtspIp.value.trim() : "",
          codigo_unico: uniqueCode,
          marca: isMovingType ? "" : brand,
          modelo: isMovingType ? "" : model,
          numero_serie: isMovingType ? "" : serial,
          usuario_stream: isMovingType ? "" : streamUser,
          password_stream: isMovingType ? "" : streamPassword,
          hacer_inferencia: inferenceEnabled,
          activa: active,
          latitud: lat,
          longitud: lon,
          altitud_m: altitude,
          direccion: address,
          referencia: reference,
          vehiculo_id: vehicleId,
          vehiculo_posicion: vehiclePosition,
        }),
        timeoutMs: 12000,
      },
    );

    if (isEditing && payload && payload.camera) {
      const currentRuntimeName = String(selectedCamera && selectedCamera.nombre || "").trim();
      if (currentRuntimeName) {
        const runtimeCamera = getCameraByName(currentRuntimeName);
        if (runtimeCamera) {
          runtimeCamera.camera_id = normalizeCameraAdminId(payload.camera.id);
          setCameraInferenceEnabledState(
            currentRuntimeName,
            Boolean(payload.camera.hacer_inferencia),
          );
        }
      }
    }

    selectedCameraAdminId = normalizeCameraAdminId(payload && payload.camera && payload.camera.id);
    await refreshUserAdmin({ preserveDraft: false });
    setCameraAdminFeedback(
      isEditing ? "Cámara actualizada correctamente." : `${creationLabel} creada correctamente.`,
      "success",
    );
  } catch (error) {
    setCameraAdminFeedback(friendlyCameraAdminError(error), "error");
  } finally {
    cameraAdminSubmit.disabled = false;
    if (cameraAdminReset) cameraAdminReset.disabled = false;
    if (cameraAdminRbox) cameraAdminRbox.disabled = false;
    cameraAdminSubmit.textContent = originalLabel;
    syncCameraAdminFormState({ preserveDraft: true });
  }
}

async function deleteSelectedCameraAdmin() {
  if (selectedCameraAdminId === null || !cameraAdminDelete) return;
  const selectedCamera = findSelectedCameraAdminItem(lastCameraAdminSnapshot);
  const label = String(selectedCamera && selectedCamera.nombre || "esta cámara").trim() || "esta cámara";
  if (!window.confirm(`¿Eliminar la cámara ${label}? Esta acción no se puede deshacer.`)) {
    return;
  }

  const originalLabel = cameraAdminDelete.textContent || "Eliminar cámara";
  cameraAdminDelete.disabled = true;
  if (cameraAdminSubmit) cameraAdminSubmit.disabled = true;
  if (cameraAdminReset) cameraAdminReset.disabled = true;
  if (cameraAdminRbox) cameraAdminRbox.disabled = true;
  cameraAdminDelete.textContent = "Eliminando...";
  setCameraAdminFeedback(`Eliminando ${label} del sistema...`, "info");

  try {
    await fetchJson(`/api/cameras/${selectedCameraAdminId}`, {
      method: "DELETE",
      timeoutMs: 12000,
    });
    selectedCameraAdminId = null;
    await refreshUserAdmin({ preserveDraft: false });
    setCameraAdminFeedback("Cámara eliminada correctamente.", "success");
  } catch (error) {
    setCameraAdminFeedback(friendlyCameraAdminError(error), "error");
  } finally {
    cameraAdminDelete.textContent = originalLabel;
    if (cameraAdminSubmit) cameraAdminSubmit.disabled = false;
    if (cameraAdminReset) cameraAdminReset.disabled = false;
    if (cameraAdminRbox) cameraAdminRbox.disabled = false;
    syncCameraAdminFormState({ preserveDraft: true });
  }
}

function formatEventTime(ts) {
  if (!ts) return "--";
  const date = new Date(ts * 1000);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatDateTime(ts) {
  if (!ts) return "--";
  const date = new Date(ts * 1000);
  return date.toLocaleString([], {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function basename(path) {
  const raw = String(path || "").trim();
  if (!raw) return "";
  const parts = raw.split(/[\\/]+/);
  return parts[parts.length - 1] || raw;
}

function getConfiguredLocations() {
  return DEVICES
    .map((device) => resolveConfiguredLocationItem(device))
    .filter((device) => Number.isFinite(Number(device && device.lat)) && Number.isFinite(Number(device && device.lon)))
    .sort((left, right) => {
      if (left.camera_name === activeCamera) return -1;
      if (right.camera_name === activeCamera) return 1;
      return String(left.camera_name || "").localeCompare(String(right.camera_name || ""));
    });
}

function isMountedCameraDevice(device) {
  if (!device || typeof device !== "object") return false;
  const cameraType = String(device.camera_type || "").trim().toLowerCase();
  return ["vehicle", "drone"].includes(cameraType);
}

function findAssociatedVehicleTelemetry(cameraName, items = lastTelemetrySnapshot) {
  const normalizedCameraName = String(cameraName || "").trim();
  if (!normalizedCameraName) return null;
  const source = Array.isArray(items) ? items : [];
  return source.find((item) => {
    if (!item || typeof item !== "object") return false;
    if (String(item.device_kind || "").trim().toLowerCase() !== "vehicle") return false;
    return String(item.camera_name || "").trim() === normalizedCameraName;
  }) || null;
}

function resolveConfiguredLocationItem(device) {
  if (!device || typeof device !== "object") return null;
  const associatedTelemetry = findAssociatedVehicleTelemetry(device.camera_name);
  if (associatedTelemetry && hasValidCoordinates(associatedTelemetry)) {
    return {
      ...device,
      lat: Number(associatedTelemetry.lat),
      lon: Number(associatedTelemetry.lon),
      altitude: associatedTelemetry.altitude,
      vehicle_type: String(associatedTelemetry.vehicle_type || device.vehicle_type || "").trim(),
      vehicle_name: String(associatedTelemetry.display_name || device.vehicle_name || "").trim(),
      marker_kind: telemetryMarkerKind(associatedTelemetry),
    };
  }
  return {
    ...device,
    marker_kind: telemetryMarkerKind({
      device_kind: isMountedCameraDevice(device) ? "vehicle" : "camera",
      vehicle_type: String(device.vehicle_type || "").trim().toLowerCase().startsWith("drone")
        ? "dron"
        : (isMountedCameraDevice(device) ? "automovil" : ""),
      camera_type: device.camera_type,
    }),
  };
}

function hasValidCoordinates(item) {
  return Number.isFinite(Number(item && item.lat)) && Number.isFinite(Number(item && item.lon));
}

function buildSynchronizedTelemetrySnapshot(items) {
  const merged = new Map();
  const source = Array.isArray(items) ? items : [];

  source.forEach((item) => {
    if (!item || typeof item !== "object") return;
    const deviceId = String(item.device_id || item.camera_name || "").trim();
    if (!deviceId) return;
    merged.set(deviceId, {
      ...item,
      device_id: deviceId,
      camera_name: String(item.camera_name || item.display_name || deviceId).trim() || deviceId,
      display_name: String(item.display_name || item.camera_name || deviceId).trim() || deviceId,
    });
  });

  DEVICES.forEach((device) => {
    if (!device || typeof device !== "object") return;
    const deviceId = String(device.device_id || device.camera_name || "").trim();
    if (!deviceId) return;
    if (isMountedCameraDevice(device)) {
      const mountedTelemetry = findAssociatedVehicleTelemetry(device.camera_name, Array.from(merged.values()));
      if (mountedTelemetry) {
        const mountedDeviceId = String(mountedTelemetry.device_id || "").trim();
        if (mountedDeviceId) {
          merged.set(mountedDeviceId, {
            ...mountedTelemetry,
            camera_name: String(device.camera_name || mountedTelemetry.camera_name || mountedDeviceId).trim() || mountedDeviceId,
            capabilities: {
              ...(mountedTelemetry.capabilities && typeof mountedTelemetry.capabilities === "object" ? mountedTelemetry.capabilities : {}),
              ...(device.capabilities && typeof device.capabilities === "object" ? device.capabilities : {}),
            },
            mounted_camera_id: device.camera_id ?? null,
            mounted_camera_type: String(device.camera_type || "").trim(),
          });
          return;
        }
      }
    }

    const existing = merged.get(deviceId);
    const nextItem = existing
      ? {
          ...existing,
          device_id: deviceId,
          camera_name: String(existing.camera_name || device.camera_name || deviceId).trim() || deviceId,
          display_name: String(
            existing.display_name
            || existing.camera_name
            || device.camera_name
            || deviceId,
          ).trim() || deviceId,
          device_kind: String(existing.device_kind || "camera"),
          capabilities: existing.capabilities && typeof existing.capabilities === "object"
            ? existing.capabilities
            : (device.capabilities || {}),
        }
      : {
          device_id: deviceId,
          camera_name: String(device.camera_name || deviceId).trim() || deviceId,
          display_name: String(device.camera_name || deviceId).trim() || deviceId,
          freshness: "unavailable",
          device_kind: "camera",
          capabilities: device.capabilities || {},
        };

    if (!hasValidCoordinates(nextItem) && hasValidCoordinates(device)) {
      nextItem.lat = Number(device.lat);
      nextItem.lon = Number(device.lon);
    }

    merged.set(deviceId, nextItem);
  });

  return Array.from(merged.values())
    .sort((left, right) => telemetryLabel(left).localeCompare(telemetryLabel(right)));
}

function formatLocationCoordinate(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "--";
  return numeric.toFixed(6);
}

function locationCapabilityTags(device) {
  const capabilities = device && typeof device.capabilities === "object" && device.capabilities
    ? device.capabilities
    : {};
  return Object.entries(LOCATION_TAG_LABELS)
    .filter(([key]) => Boolean(capabilities[key]))
    .map(([, label]) => label)
    .join(" · ");
}

function renderLocationSummary(items) {
  if (!locationsSummary) return;
  if (!Array.isArray(items) || items.length === 0) {
    locationsSummary.innerHTML = '<div class="empty-state">Sin ubicaciones configuradas.</div>';
    return;
  }

  locationsSummary.innerHTML = items.map((item) => {
    const isActive = item.camera_name === activeCamera;
    const tags = locationCapabilityTags(item);
    return `
      <button class="location-row ${isActive ? "is-active" : ""}" type="button" data-camera-name="${String(item.camera_name || "")}">
        <div class="location-row-head">
          <strong>${String(item.camera_name || item.device_id || "").toUpperCase()}</strong>
          <span class="location-row-status">Ubicada</span>
        </div>
        <div class="telemetry-detail">Lat: ${formatLocationCoordinate(item.lat)} · Lon: ${formatLocationCoordinate(item.lon)}</div>
        <div class="telemetry-detail">${tags || "Sin capacidades adicionales"}</div>
      </button>
    `;
  }).join("");
}

function ensureLocationsMap() {
  if (locationsMapInstance) return true;
  if (!locationsMap) return false;
  if (typeof window.L === "undefined") {
    locationsMap.innerHTML = '<div class="empty-state map-empty">Mapa no disponible sin acceso al CDN de Leaflet.</div>';
    return false;
  }

  locationsMapInstance = window.L.map(locationsMap, {
    zoomControl: true,
    attributionControl: true,
  }).setView([0, 0], 2);

  addSatelliteTileLayers(locationsMapInstance);
  return true;
}

function updateLocationsMap(items) {
  if (!locationsMap && !locationsSummary) return;
  renderLocationSummary(items);
  if (!ensureLocationsMap()) return;

  locationsMapInstance.invalidateSize();
  const bounds = [];
  const nextIds = new Set();

  items.forEach((item) => {
    const lat = Number(item.lat);
    const lon = Number(item.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;

    const cameraName = String(item.camera_name || "");
    const isActive = item.camera_name === activeCamera;
    const powered = isCameraPowered(cameraName);
    let marker = locationMarkers.get(item.device_id);
        if (!marker) {
      marker = createMapMarker(locationsMapInstance, lat, lon, {
        powered,
        active: isActive,
        markerKind: String(item.marker_kind || "camera"),
      });
      marker.on("click", () => {
        selectCameraFromMap(String(marker.__cameraName || ""), { focusMarker: false });
      });
      locationMarkers.set(item.device_id, marker);
    } else {
      marker.setLatLng([lat, lon]);
      updateMapMarkerStyle(marker, {
        powered,
        active: isActive,
        markerKind: String(item.marker_kind || "camera"),
      });
    }
    marker.__cameraName = cameraName;

    bindPrettyTooltip(marker, String(item.camera_name || item.device_id || "").toUpperCase());
    bindPrettyPopup(marker, `
      <strong>${String(item.camera_name || item.device_id || "").toUpperCase()}</strong><br>
      Estado: ${cameraPowerLabel(cameraName)}<br>
      Lat: ${formatLocationCoordinate(item.lat)}<br>
      Lon: ${formatLocationCoordinate(item.lon)}<br>
      ${locationCapabilityTags(item) || "Sin capacidades adicionales"}
    `);

    nextIds.add(item.device_id);
    bounds.push([lat, lon]);
  });

  for (const [deviceId, marker] of locationMarkers.entries()) {
    if (!nextIds.has(deviceId)) {
      locationsMapInstance.removeLayer(marker);
      locationMarkers.delete(deviceId);
    }
  }

  lastLocationCoordinates = bounds;
  const nextSignature = mapCoordinateSignature(bounds);

  if (
    bounds.length > 0
    && (
      !locationsMapAutoFitDone
      || lastLocationMarkerCount !== bounds.length
      || nextSignature !== lastLocationBoundsSignature
    )
  ) {
    fitMapToCoordinates(locationsMapInstance, bounds, {
      maxZoom: 17,
      singleZoom: 15,
    });
    locationsMapAutoFitDone = true;
    lastLocationBoundsSignature = nextSignature;
  }
  if (bounds.length === 0) {
    lastLocationBoundsSignature = "";
  }
  lastLocationMarkerCount = bounds.length;
}

function focusLocation(cameraName) {
  if (!cameraName) return;
  const device = getDeviceByCamera(cameraName);
  const locationMarker = device ? locationMarkers.get(device.device_id) : null;
  if (locationMarker && locationsMapInstance) {
    locationsMapInstance.flyTo(locationMarker.getLatLng(), Math.max(locationsMapInstance.getZoom(), 15), {
      duration: 0.6,
    });
    locationMarker.openPopup();
    return;
  }

  const telemetryMarker = device
    ? mapMarkers.get(device.device_id)
    : Array.from(mapMarkers.values()).find((marker) => String(marker.__cameraName || "") === cameraName);
  if (!telemetryMarker || !mapInstance) return;
  mapInstance.flyTo(telemetryMarker.getLatLng(), Math.max(mapInstance.getZoom(), 15), {
    duration: 0.6,
  });
  telemetryMarker.openPopup();
}

function renderLocationsPanel() {
  updateLocationsMap(getConfiguredLocations());
}

function severityClass(severity) {
  switch ((severity || "").toLowerCase()) {
    case "error":
      return "sev-error";
    case "warning":
      return "sev-warning";
    default:
      return "sev-info";
  }
}

async function refreshStatus() {
  if (document.visibilityState === "hidden") return;
  CAMERAS.forEach((camera) => {
    const playback = resolveCameraPlaybackTarget(camera.name);
    const video = getVideoByCamera(camera.name);
    const isActive = camera.name === activeCamera;
    const hasDirectVideo = Boolean(
      video
      && (
        video.srcObject
        || video.currentSrc
        || video.getAttribute("src")
      )
    );

    let labelText = "Lista";
    let hasError = false;
    if (playback.mode === "unsupported") {
      labelText = "URL no compatible";
      hasError = true;
    } else if (embeddedViewerSessions.has(camera.name)) {
      labelText = "En vivo web";
    } else if (isActive && hasDirectVideo) {
      labelText = "En vivo";
    } else if (isActive && playback.mode !== "none") {
      labelText = "Cargando";
    }

    cameraStatuses.set(camera.name, {
      rawStatus: labelText.toLowerCase(),
      hasError,
      labelText,
    });
    updateSelectorState(camera.name, labelText);
  });
  refreshRenderedMapMarkers();
}

function prettifyEventType(value) {
  return String(value || "evento")
    .replaceAll("_", " ")
    .replace(/\s+/g, " ")
    .trim();
}

function logEntryKey(entry) {
  return String(entry && entry.entry_id || "");
}

function deviceMatchesLogFilter(deviceId, entry) {
  if (!deviceId) return true;
  const normalizedDeviceId = String(deviceId).trim();
  const candidates = new Set([
    String(entry && entry.device_id || "").trim(),
    String(entry && entry.camera_name || "").trim(),
    String(entry && entry.meta || "").trim(),
  ]);
  return candidates.has(normalizedDeviceId);
}

function buildLogDeviceOptions(vehicleEntries, telemetrySnapshot) {
  const options = [];
  const seen = new Set();
  const vehicles = Array.isArray(vehicleEntries) ? vehicleEntries : [];
  const telemetry = Array.isArray(telemetrySnapshot) ? telemetrySnapshot : [];

  vehicles.forEach((item) => {
    const deviceId = String(item.identifier || "").trim();
    if (!deviceId || seen.has(deviceId)) return;
    seen.add(deviceId);
    const typeLabel = String(item.vehicle_type || "").trim().toLowerCase() === "dron" ? "Dron" : "Vehiculo";
    options.push({
      value: deviceId,
      label: `${String(item.label || deviceId).trim()} · ${typeLabel}`,
    });
  });

  telemetry.forEach((item) => {
    const deviceId = String(item.device_id || "").trim();
    if (!deviceId || seen.has(deviceId)) return;
    if (String(item.device_kind || "").trim().toLowerCase() !== "vehicle") return;
    seen.add(deviceId);
    const typeLabel = String(item.vehicle_type || "").trim().toLowerCase() === "dron" ? "Dron" : "Vehiculo";
    options.push({
      value: deviceId,
      label: `${String(item.display_name || deviceId).trim()} · ${typeLabel}`,
    });
  });

  return options.sort((left, right) => left.label.localeCompare(right.label));
}

function syncEventDeviceFilter(vehicleEntries, telemetrySnapshot) {
  if (!eventsDeviceFilter) return;
  const options = buildLogDeviceOptions(vehicleEntries, telemetrySnapshot);
  const nextMarkup = [
    '<option value="">Todos los dispositivos</option>',
    ...options.map((item) => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`),
  ].join("");

  if (eventsDeviceFilter.innerHTML !== nextMarkup) {
    eventsDeviceFilter.innerHTML = nextMarkup;
  }

  const availableIds = new Set(options.map((item) => item.value));
  if (activeLogsDeviceId && !availableIds.has(activeLogsDeviceId)) {
    activeLogsDeviceId = "";
  }
  if (eventsDeviceFilter.value !== activeLogsDeviceId) {
    eventsDeviceFilter.value = activeLogsDeviceId;
  }
}

function buildTelemetryLogEntries(telemetrySnapshot, selectedDeviceId) {
  if (!selectedDeviceId) return [];
  const item = (Array.isArray(telemetrySnapshot) ? telemetrySnapshot : [])
    .find((entry) => String(entry.device_id || "").trim() === selectedDeviceId);
  if (!item) return [];

  const extra = item.extra && typeof item.extra === "object" ? item.extra : {};
  const ts = Number(extra.last_update_ts || item.source_ts || item.received_ts || 0) || Date.now() / 1000;
  const entries = [];
  const addEntry = (suffix, title, detail, severity = "info") => {
    if (!detail) return;
    entries.push({
      entry_id: `tlog-${selectedDeviceId}-${suffix}`,
      entry_kind: "tlog",
      ts,
      severity,
      title,
      meta: String(item.display_name || item.device_id || selectedDeviceId).toUpperCase(),
      device_id: String(item.device_id || selectedDeviceId).trim(),
      camera_name: String(item.camera_name || selectedDeviceId).trim(),
      source: "telemetry",
      detail,
      payload: extra,
    });
  };

  addEntry(
    "freshness",
    "Estado de enlace",
    `${String(item.freshness || "unavailable").toUpperCase()} · ${String(item.device_status || "unknown").toUpperCase()}`,
    item.freshness === "lost" ? "error" : item.freshness === "stale" ? "warning" : "info",
  );
  addEntry("mode", "Modo de vuelo", extra.mode ? String(extra.mode).toUpperCase() : "");
  addEntry("armed", "Estado de armado", extra.armed === undefined || extra.armed === null ? "" : (extra.armed ? "ARMADO" : "DESARMADO"));
  addEntry(
    "battery",
    "Bateria",
    extra.battery_remaining_pct === undefined || extra.battery_remaining_pct === null
      ? ""
      : `${Math.round(Number(extra.battery_remaining_pct) || 0)}% · ${extra.battery_voltage_v ? `${Number(extra.battery_voltage_v).toFixed(2)} V` : "Sin voltaje"}`,
    Number(extra.battery_remaining_pct) <= 20 ? "warning" : "info",
  );
  addEntry(
    "position",
    "Posicion",
    item.lat === undefined || item.lat === null || item.lon === undefined || item.lon === null
      ? ""
      : `Lat ${Number(item.lat).toFixed(6)} · Lon ${Number(item.lon).toFixed(6)} · Alt ${item.altitude === undefined || item.altitude === null ? "--" : Number(item.altitude).toFixed(2)} m`,
  );
  addEntry(
    "motion",
    "Movimiento",
    `${item.speed === undefined || item.speed === null ? "--" : Number(item.speed).toFixed(2)} km/h · Heading ${item.heading === undefined || item.heading === null ? "--" : Number(item.heading).toFixed(0)}°`,
  );
  addEntry("status", "Estado del sistema", extra.system_status_text ? String(extra.system_status_text).toUpperCase() : "");

  return entries;
}

function buildLogEntries(events, telemetrySnapshot, vehicleEntries) {
  const sourceEvents = Array.isArray(events) ? events : [];
  const normalizedEvents = sourceEvents.map((event) => {
    const payload = event.payload && typeof event.payload === "object" ? event.payload : {};
    const detail = payload.recognized_name || payload.filename || payload.device_status || payload.label || payload.identifier || "";
    return {
      entry_id: `event-${String(event.event_id || Math.random())}`,
      entry_kind: "event",
      ts: Number(event.ts) || 0,
      severity: String(event.severity || "info"),
      title: prettifyEventType(event.event_type),
      meta: String(event.camera_name || event.device_id || "").toUpperCase(),
      device_id: String(event.device_id || "").trim(),
      camera_name: String(event.camera_name || "").trim(),
      source: String(event.source || "system"),
      detail: String(detail || ""),
      payload,
      raw: event,
    };
  });

  if (activeLogsMode === "tlogs") {
    if (!activeLogsDeviceId) {
      return [];
    }
    const relatedEvents = normalizedEvents.filter((entry) => deviceMatchesLogFilter(activeLogsDeviceId, entry));
    return [
      ...buildTelemetryLogEntries(telemetrySnapshot, activeLogsDeviceId),
      ...relatedEvents,
    ].sort((left, right) => (Number(right.ts) || 0) - (Number(left.ts) || 0));
  }

  return normalizedEvents
    .filter((entry) => deviceMatchesLogFilter(activeLogsDeviceId, entry))
    .filter((entry) => activeLogsMode !== "alerts" || ["warning", "error"].includes(String(entry.severity || "").toLowerCase()))
    .sort((left, right) => (Number(right.ts) || 0) - (Number(left.ts) || 0));
}

function syncSelectedLogEntry(entries) {
  const source = Array.isArray(entries) ? entries : [];
  const selected = source.find((entry) => logEntryKey(entry) === selectedLogEntryId) || null;
  if (selected) return selected;
  selectedLogEntryId = source.length > 0 ? logEntryKey(source[0]) : null;
  return source.length > 0 ? source[0] : null;
}

function renderLogsFeed(entries) {
  if (!eventsFeed) return;
  const source = Array.isArray(entries) ? entries : [];
  if (source.length === 0) {
    eventsFeed.innerHTML = activeLogsMode === "tlogs"
      ? '<div class="empty-state">Selecciona un dron o vehículo para revisar su tlog.</div>'
      : '<div class="empty-state">No hay logs disponibles para este filtro.</div>';
    return;
  }

  eventsFeed.innerHTML = source.slice(0, 40).map((entry) => `
    <article class="event-item ${selectedLogEntryId === logEntryKey(entry) ? "is-active" : ""}" data-log-entry-id="${escapeHtml(logEntryKey(entry))}" tabindex="0">
      <div class="event-topline">
        <span class="event-severity ${severityClass(entry.severity)}">${escapeHtml(String(entry.severity || "info").toUpperCase())}</span>
        <span class="event-time">${escapeHtml(formatEventTime(entry.ts))}</span>
      </div>
      <div class="event-title">${escapeHtml(entry.title)}</div>
      <div class="event-meta">${escapeHtml(entry.meta || String(entry.source || "").toUpperCase())}</div>
      ${entry.detail ? `<div class="event-detail">${escapeHtml(entry.detail)}</div>` : ""}
    </article>
  `).join("");
}

function renderLogsSummary(entries, telemetrySnapshot, vehicleEntries) {
  if (!eventsSummary) return;
  const source = Array.isArray(entries) ? entries : [];
  const telemetry = Array.isArray(telemetrySnapshot) ? telemetrySnapshot : [];
  const vehicles = Array.isArray(vehicleEntries) ? vehicleEntries : [];
  const warningCount = source.filter((entry) => String(entry.severity || "").toLowerCase() === "warning").length;
  const errorCount = source.filter((entry) => String(entry.severity || "").toLowerCase() === "error").length;
  const connectedTelemetry = telemetry.filter((entry) => String(entry.freshness || "") === "fresh").length;

  eventsSummary.innerHTML = [
    { label: "Modo activo", value: activeLogsMode === "general" ? "Generales" : activeLogsMode === "alerts" ? "Alertas" : "TLogs" },
    { label: "Items visibles", value: String(source.length) },
    { label: "Warnings", value: String(warningCount) },
    { label: "Errores", value: String(errorCount) },
    { label: "Vehiculos", value: String(vehicles.length) },
    { label: "Telemetria viva", value: String(connectedTelemetry) },
  ].map((item) => `
    <article class="logs-summary-card">
      <span>${escapeHtml(item.label)}</span>
      <strong>${escapeHtml(item.value)}</strong>
    </article>
  `).join("");
}

function renderLogsDetail(entry) {
  if (!eventsDetail) return;
  if (!entry) {
    eventsDetail.innerHTML = '<div class="logs-detail-empty">Selecciona un log del feed para revisar su detalle aquí.</div>';
    return;
  }

  const payloadPreview = entry.payload && typeof entry.payload === "object" && Object.keys(entry.payload).length > 0
    ? JSON.stringify(entry.payload, null, 2)
    : "";

  eventsDetail.innerHTML = `
    <div class="logs-detail-card">
      <span class="logs-detail-kicker">${escapeHtml(activeLogsMode === "general" ? "Log general" : activeLogsMode === "alerts" ? "Alerta" : "TLog / telemetria")}</span>
      <strong class="logs-detail-title">${escapeHtml(entry.title)}</strong>
      <p class="logs-detail-copy">${escapeHtml(entry.detail || "Sin detalle extendido para este registro.")}</p>
      <div class="logs-detail-meta-grid">
        <div class="logs-detail-meta-row"><span>Severidad</span><strong>${escapeHtml(String(entry.severity || "info").toUpperCase())}</strong></div>
        <div class="logs-detail-meta-row"><span>Fuente</span><strong>${escapeHtml(String(entry.source || "system").toUpperCase())}</strong></div>
        <div class="logs-detail-meta-row"><span>Dispositivo</span><strong>${escapeHtml(String(entry.device_id || entry.camera_name || "--"))}</strong></div>
        <div class="logs-detail-meta-row"><span>Hora</span><strong>${escapeHtml(formatEventTime(entry.ts))}</strong></div>
      </div>
      ${payloadPreview ? `<pre class="logs-detail-pre">${escapeHtml(payloadPreview)}</pre>` : ""}
    </div>
  `;
}

function applyLogsModeUi() {
  if (!logsModeSwitch) return;
  const buttons = Array.from(logsModeSwitch.querySelectorAll("[data-log-mode]"));
  buttons.forEach((button) => {
    button.classList.toggle("is-active", button.getAttribute("data-log-mode") === activeLogsMode);
  });
}

function renderLogsDashboard(events, telemetrySnapshot, vehicleEntries) {
  syncEventDeviceFilter(vehicleEntries, telemetrySnapshot);
  applyLogsModeUi();

  const entries = buildLogEntries(events, telemetrySnapshot, vehicleEntries);
  const selected = syncSelectedLogEntry(entries);
  renderLogsFeed(entries);
  renderLogsSummary(entries, telemetrySnapshot, vehicleEntries);
  renderLogsDetail(selected);
}

async function refreshEvents() {
  if (!eventsFeed) return;
  if (document.visibilityState === "hidden") return;
  try {
    const [events, telemetry, vehicles] = await Promise.all([
      fetchJson("/api/events?limit=60", { timeoutMs: 4000 }),
      fetchJson("/api/telemetry", { timeoutMs: 4000 }),
      fetchJson("/api/vehicle-registry?limit=120", { timeoutMs: 4000 }),
    ]);
    lastEventsSnapshot = Array.isArray(events) ? events : [];
    lastLogsTelemetry = Array.isArray(telemetry) ? telemetry : [];
    lastLogVehicleRegistry = Array.isArray(vehicles) ? vehicles : [];
    renderLogsDashboard(lastEventsSnapshot, lastLogsTelemetry, lastLogVehicleRegistry);
  } catch (error) {
    eventsFeed.innerHTML = '<div class="empty-state">No se pudo cargar el centro de logs.</div>';
    if (eventsSummary) {
      eventsSummary.innerHTML = '<div class="empty-state">Resumen no disponible.</div>';
    }
    if (eventsDetail) {
      eventsDetail.innerHTML = '<div class="logs-detail-empty">No fue posible cargar el detalle de logs.</div>';
    }
  }
}

function renderVehicleRegistrySummary(items) {
  if (vehicleRegistryTotal) {
    vehicleRegistryTotal.textContent = Array.isArray(items) ? String(items.length) : "0";
  }

  if (vehicleRegistryCameras) {
    const manualEntries = (Array.isArray(items) ? items : []).filter((item) => item.entry_kind === "manual");
    const totalCameras = manualEntries.reduce((count, item) => {
      const links = Array.isArray(item && item.camera_links) ? item.camera_links : [];
      return count + links.length;
    }, 0);
    vehicleRegistryCameras.textContent = String(totalCameras);
  }

  if (vehicleRegistryUpdated) {
    const newestTs = Array.isArray(items) && items.length > 0
      ? Math.max(...items.map((item) => Number(item.ts) || 0))
      : 0;
    vehicleRegistryUpdated.textContent = newestTs ? formatDateTime(newestTs) : "--";
  }
}

function buildVehicleRegistryItems(evidenceItems, manualItems) {
  const evidence = Array.isArray(evidenceItems) ? evidenceItems : [];
  const manual = Array.isArray(manualItems) ? manualItems : [];

  return [
    ...manual.map((item) => ({
      entry_kind: "manual",
      registration_id: String(item.registration_id || "").trim(),
      id: Number(item.id || 0) || null,
      ts: Number(item.ts) || 0,
      vehicle_type: String(item.vehicle_type || "").trim().toLowerCase(),
      vehicle_type_code: normalizeVehicleTypeCode(item.vehicle_type_code || item.tipo_vehiculo_codigo || item.vehicle_type),
      vehicle_type_name: String(item.vehicle_type_name || item.tipo_vehiculo_nombre || "").trim(),
      label: String(item.label || "").trim(),
      identifier: String(item.identifier || "").trim(),
      notes: String(item.notes || "").trim(),
      source: String(item.source || "vehicle_registry"),
      telemetry_mode: String(item.telemetry_mode || "manual").trim().toLowerCase(),
      api_base_url: String(item.api_base_url || "").trim(),
      api_device_id: String(item.api_device_id || "").trim(),
      has_live_telemetry: Boolean(item.has_live_telemetry),
      organizacion_id: Number(item.organizacion_id || 0) || null,
      organizacion_nombre: String(item.organizacion_nombre || "").trim(),
      propietario_usuario_id: Number(item.propietario_usuario_id || 0) || null,
      propietario_usuario: String(item.propietario_usuario || "").trim(),
      propietario_display_name: String(item.propietario_display_name || item.propietario_usuario || "").trim(),
      camera_name: String(item.camera_name || "").trim(),
      camera_links: Array.isArray(item.camera_links) ? item.camera_links : [],
    })),
    ...evidence.map((item) => ({
      entry_kind: "evidence",
      ts: Number(item.ts) || 0,
      camera_name: String(item.camera_name || item.device_id || "").trim(),
      file_path: String(item.file_path || "").trim(),
      metadata: item.metadata && typeof item.metadata === "object" ? item.metadata : {},
    })),
  ];
}

function vehicleRegistryManualKey(item) {
  return vehicleRegistrySelectionKey(item);
}

function findSelectedVehicleRegistryItem(items) {
  const source = Array.isArray(items) ? items : [];
  if (!selectedVehicleRegistryKey) return null;
  return source.find((item) => vehicleRegistryManualKey(item) === selectedVehicleRegistryKey) || null;
}

function renderVehicleRegistrySummaryItem(item) {
  const isDrone = isDroneVehicleTypeCode(item.vehicle_type_code || item.vehicle_type);
  const itemKey = vehicleRegistryManualKey(item);
  const title = String(item.label || item.identifier || "registro manual").trim() || "registro manual";
  const identifier = String(item.identifier || "--").trim() || "--";
  return `
    <button
      class="vehicle-registry-summary-item ${selectedVehicleRegistryKey === itemKey ? "is-active" : ""}"
      type="button"
      data-vehicle-registry-key="${escapeHtml(itemKey)}"
    >
      <span class="vehicle-registry-summary-top">
        <strong>${escapeHtml(title.toUpperCase())}</strong>
        <span class="vehicle-registry-summary-pill">${escapeHtml(String(item.vehicle_type_name || (isDrone ? "Dron" : "Auto")))}</span>
      </span>
      <span class="vehicle-registry-summary-identifier">${escapeHtml(identifier)}</span>
      <span class="vehicle-registry-summary-time">${escapeHtml(formatDateTime(item.ts))}</span>
    </button>
  `;
}

function renderManualVehicleRegistryItem(item) {
  const badgeLabel = String(item.vehicle_type_name || item.vehicle_type || "vehiculo").toUpperCase();
  const telemetryMode = String(item.telemetry_mode || "manual").trim().toLowerCase() || "manual";
  const hasApiConnection = Boolean(String(item.api_device_id || item.identifier || "").trim());
  const cameraLinks = Array.isArray(item.camera_links) ? item.camera_links : [];
  const telemetryBadge = telemetryMode === "api"
      ? "API"
      : "Sin telemetría";
  const manualSummary = [badgeLabel, "Manual", telemetryBadge]
    .filter(Boolean)
    .join(" ");

  return `
    <article class="vehicle-item vehicle-item-manual">
      <div class="vehicle-item-top">
        <div class="vehicle-item-heading">
          <div class="vehicle-item-title">${escapeHtml(String(item.label || "registro manual").toUpperCase())}</div>
          <div class="vehicle-item-time">${escapeHtml(formatDateTime(item.ts))}</div>
          <div class="vehicle-item-manual-summary">${escapeHtml(manualSummary)}</div>
        </div>
        <div class="vehicle-item-badges">
          <span class="vehicle-item-badge">${badgeLabel}</span>
          <span class="vehicle-item-badge vehicle-item-badge-soft">Manual</span>
          ${item.has_live_telemetry ? `<span class="vehicle-item-badge vehicle-item-badge-soft">${escapeHtml(telemetryBadge)}</span>` : ""}
        </div>
      </div>
      <div class="vehicle-item-actions">
        <button
          class="camera-register-secondary"
          type="button"
          data-vehicle-action="edit"
          data-vehicle-registration-id="${escapeHtml(String(item.registration_id || ""))}"
        >
          Editar
        </button>
        <button
          class="camera-register-secondary camera-register-danger"
          type="button"
          data-vehicle-action="delete"
          data-vehicle-registration-id="${escapeHtml(String(item.registration_id || ""))}"
        >
          Eliminar
        </button>
      </div>
      <div class="vehicle-item-manual-grid">
        <article class="vehicle-item-detail-card">
          <span class="vehicle-item-detail-label">Identificador</span>
          <strong class="vehicle-item-detail-value vehicle-item-detail-value-code">${escapeHtml(String(item.identifier || "--"))}</strong>
        </article>
        <article class="vehicle-item-detail-card">
          <span class="vehicle-item-detail-label">Modo de telemetría</span>
          <strong class="vehicle-item-detail-value">${escapeHtml(telemetryBadge)}</strong>
        </article>
        <article class="vehicle-item-detail-card">
          <span class="vehicle-item-detail-label">Organización</span>
          <strong class="vehicle-item-detail-value">${escapeHtml(String(item.organizacion_nombre || "--"))}</strong>
        </article>
        <article class="vehicle-item-detail-card">
          <span class="vehicle-item-detail-label">Propietario</span>
          <strong class="vehicle-item-detail-value">${escapeHtml(String(item.propietario_display_name || item.propietario_usuario || "--"))}</strong>
        </article>
        ${telemetryMode === "api" && hasApiConnection ? `
          <article class="vehicle-item-detail-card">
            <span class="vehicle-item-detail-label">ID esperado</span>
            <strong class="vehicle-item-detail-value vehicle-item-detail-value-code">${escapeHtml(String(item.api_device_id || item.identifier || "--"))}</strong>
          </article>
        ` : ""}
        ${cameraLinks.length > 0 ? `
          <article class="vehicle-item-detail-card vehicle-item-detail-card-wide">
            <span class="vehicle-item-detail-label">Cámaras asociadas</span>
            <div class="vehicle-item-link-pills">
              ${cameraLinks.map((camera) => `
                <span class="vehicle-item-link-pill">
                  <small>${escapeHtml(String(camera.position || camera.posicion || "montaje").trim() || "montaje")}</small>
                  <strong>${escapeHtml(String(camera.camera_name || camera.camara_nombre || "--").trim() || "--")}</strong>
                </span>
              `).join("")}
            </div>
          </article>
        ` : ""}
        ${item.notes ? `
          <article class="vehicle-item-detail-card vehicle-item-detail-card-wide">
            <span class="vehicle-item-detail-label">Notas operativas</span>
            <div class="vehicle-item-notes">${escapeHtml(String(item.notes))}</div>
          </article>
        ` : ""}
      </div>
    </article>
  `;
}

function renderVehicleRegistrySection({ tone, kicker, title, description, items, emptyMessage, renderer }) {
  const source = Array.isArray(items) ? items : [];
  const countLabel = source.length === 1 ? "1 registro" : `${source.length} registros`;
  return `
    <section class="vehicle-registry-section ${tone ? `is-${tone}` : ""}">
      <div class="vehicle-registry-section-head">
        <div class="vehicle-registry-section-copy">
          <span class="vehicle-registry-section-kicker">${escapeHtml(kicker)}</span>
          <strong>${escapeHtml(title)}</strong>
          ${description ? `<p>${escapeHtml(description)}</p>` : ""}
        </div>
        <span class="vehicle-registry-section-count">${escapeHtml(countLabel)}</span>
      </div>
      <div class="vehicle-registry-section-list">
        ${source.length > 0
          ? source.map((entry) => renderer(entry)).join("")
          : `<div class="vehicle-registry-section-empty">${escapeHtml(emptyMessage)}</div>`}
      </div>
    </section>
  `;
}

function renderVehicleRegistry(items) {
  if (!vehicleRegistryDetail && !vehicleRegistryRailList) return;

  const source = Array.isArray(items) ? items : [];
  lastVehicleRegistrySnapshot = source;
  renderVehicleRegistrySummary(source);

  const sorted = [...source].sort((a, b) => (Number(b.ts) || 0) - (Number(a.ts) || 0));
  const manualEntries = sorted.filter((item) => item.entry_kind === "manual");
  const droneEntries = manualEntries.filter((item) => String(item.vehicle_type || "").trim().toLowerCase() === "dron");
  const carEntries = manualEntries.filter((item) => String(item.vehicle_type || "").trim().toLowerCase() !== "dron");
  const selectedItem = findSelectedVehicleRegistryItem(manualEntries);

  if (selectedVehicleRegistryKey && !selectedItem) {
    selectedVehicleRegistryKey = null;
  }

  if (vehicleRegistryDetailTitle) {
    vehicleRegistryDetailTitle.textContent = selectedItem
      ? String(selectedItem.label || selectedItem.identifier || "Detalle del registro").trim() || "Detalle del registro"
      : manualEntries.length > 0
        ? "Selecciona un registro"
        : "Sin registros manuales";
  }

  if (vehicleRegistryDetailCopy) {
    vehicleRegistryDetailCopy.textContent = selectedItem
      ? `Registrado el ${formatDateTime(selectedItem.ts)}. Revisa aqui la informacion completa del ${String(selectedItem.vehicle_type || "vehiculo").trim() || "vehiculo"} seleccionado.`
      : manualEntries.length > 0
        ? "Haz clic en un dron o auto del panel derecho para ver su información completa aquí."
        : "Todavía no hay drones o autos registrados manualmente para mostrar en detalle.";
  }

  if (vehicleRegistryDetail) {
    vehicleRegistryDetail.innerHTML = selectedItem
      ? renderManualVehicleRegistryItem(selectedItem)
      : manualEntries.length > 0
        ? '<div class="vehicle-registry-detail-empty">Selecciona un dron o un auto del panel derecho para abrir su ficha completa en este espacio.</div>'
        : '<div class="empty-state">Sin vehículos registrados todavía.</div>';
  }

  if (vehicleRegistryRailList) {
    vehicleRegistryRailList.innerHTML = [
      renderVehicleRegistrySection({
        tone: "drones",
        kicker: "Clasificacion",
        title: "Drones registrados",
        description: "Aqui aparecen los drones registrados manualmente dentro del sistema.",
        items: droneEntries,
        emptyMessage: "No se encuentran drones registrados.",
        renderer: renderVehicleRegistrySummaryItem,
      }),
      renderVehicleRegistrySection({
        tone: "vehicles",
        kicker: "Clasificacion",
        title: "Autos / carros registrados",
        description: "Aqui se muestran los automoviles, camionetas o unidades registradas manualmente dentro del sistema.",
        items: carEntries,
        emptyMessage: "No se encuentran vehiculos registrados.",
        renderer: renderVehicleRegistrySummaryItem,
      }),
    ].join("");
  }
}

async function refreshVehicleRegistry() {
  if (!vehicleRegistryDetail && !vehicleRegistryRailList) return;
  if (document.visibilityState === "hidden") return;
  try {
    const [evidence, manual] = await Promise.all([
      fetchJson("/api/evidence?kind=plate_snapshot&limit=80", { timeoutMs: 4000 }),
      fetchJson("/api/vehicle-registry?limit=80", { timeoutMs: 4000 }),
    ]);
    renderVehicleRegistry(buildVehicleRegistryItems(evidence, manual));
  } catch (error) {
    renderVehicleRegistrySummary([]);
    if (vehicleRegistryDetailTitle) {
      vehicleRegistryDetailTitle.textContent = "Sin detalle disponible";
    }
    if (vehicleRegistryDetailCopy) {
      vehicleRegistryDetailCopy.textContent = "No fue posible cargar los registros manuales en este momento.";
    }
    if (vehicleRegistryDetail) {
      vehicleRegistryDetail.innerHTML = '<div class="empty-state">No se pudo cargar el registro manual de vehículos.</div>';
    }
    if (vehicleRegistryRailList) {
      vehicleRegistryRailList.innerHTML = '<div class="empty-state">No se pudo cargar el registro complementario.</div>';
    }
  }
}

function colorForFreshness(freshness) {
  switch ((freshness || "").toLowerCase()) {
    case "fresh":
      return "#22c55e";
    case "stale":
      return "#f59e0b";
    case "lost":
      return "#ef4444";
    default:
      return "#94a3b8";
  }
}

function formatTelemetryValue(value, suffix = "") {
  if (value === null || value === undefined || value === "") return "--";
  const numeric = Number(value);
  if (Number.isFinite(numeric)) {
    return `${numeric.toFixed(2)}${suffix}`;
  }
  return `${value}${suffix}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function toFiniteNumber(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function clampNumber(value, min, max) {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, value));
}

function normalizeDegrees(value) {
  const numeric = toFiniteNumber(value);
  if (numeric === null) return null;
  const normalized = numeric % 360;
  return normalized < 0 ? normalized + 360 : normalized;
}

function telemetryFreshnessLabel(value) {
  const text = String(value || "unavailable").trim().toUpperCase();
  return text || "UNAVAILABLE";
}

function telemetryBatteryTone(batteryPct) {
  if (batteryPct === null) return "unknown";
  if (batteryPct <= 15) return "critical";
  if (batteryPct <= 25) return "warning";
  return "good";
}

function headingCardinalLabel(value) {
  const normalized = normalizeDegrees(value);
  if (normalized === null) return "--";
  const directions = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"];
  return directions[Math.round(normalized / 45) % directions.length];
}

function telemetryLabel(item) {
  return String(item && (item.display_name || item.camera_name || item.device_id) || "").trim();
}

function isRegisteredVehicleTelemetry(item) {
  if (!item || typeof item !== "object") return false;
  return String(item.device_kind || "").trim().toLowerCase() === "vehicle"
    || ["dron", "automovil"].includes(String(item.vehicle_type || "").trim().toLowerCase());
}

function telemetryMarkerKind(item) {
  if (!item || typeof item !== "object") return "camera";
  const normalizedVehicleType = String(item.vehicle_type || "").trim().toLowerCase();
  if (normalizedVehicleType === "dron") {
    return "drone";
  }
  if (normalizedVehicleType === "automovil") {
    return "car";
  }
  return String(item.device_kind || "").trim().toLowerCase() === "vehicle" ? "car" : "camera";
}

function isSelectedTelemetryItem(item) {
  if (!item || typeof item !== "object") return false;
  if (activeTelemetryDeviceId) {
    return String(item.device_id || "").trim() === activeTelemetryDeviceId;
  }
  return Boolean(activeCamera && item.camera_name === activeCamera);
}

function getVisibleTelemetryItems(items) {
  const source = Array.isArray(items) ? items : [];
  if (!activeTelemetryDeviceId) {
    return source;
  }
  return source.filter((item) => String(item.device_id || "").trim() === activeTelemetryDeviceId);
}

function getSelectableTelemetryItems(items) {
  return (Array.isArray(items) ? items : [])
    .filter((item) => {
      if (!isRegisteredVehicleTelemetry(item)) return false;
      const freshness = String(item && item.freshness || "").trim().toLowerCase();
      return Boolean(item && item.has_live_telemetry) || (freshness && freshness !== "unavailable");
    })
    .sort((left, right) => telemetryLabel(left).localeCompare(telemetryLabel(right)));
}

function getSelectedTelemetryItem(items) {
  const source = Array.isArray(items) ? items : [];
  if (!activeTelemetryDeviceId) {
    return null;
  }
  return source.find((item) => String(item.device_id || "").trim() === activeTelemetryDeviceId) || null;
}

function setTelemetrySelection(deviceId, { recenter = true } = {}) {
  activeTelemetryDeviceId = String(deviceId || "").trim() || null;
  if (telemetryDeviceFilter && document.activeElement !== telemetryDeviceFilter) {
    telemetryDeviceFilter.value = activeTelemetryDeviceId || "";
  }
  syncTelemetryMapOverlayFromTelemetrySelection(lastTelemetrySnapshot);
  if (recenter) {
    requestTelemetryMapRecenter();
  }
}

function syncTelemetryDeviceFilter(items) {
  if (!telemetryDeviceFilter) return;

  const droneItems = getSelectableTelemetryItems(items);
  const availableIds = new Set(
    droneItems
      .map((item) => String(item.device_id || "").trim())
      .filter(Boolean),
  );

  if (activeTelemetryDeviceId && !availableIds.has(activeTelemetryDeviceId)) {
    activeTelemetryDeviceId = null;
  }

  const nextValue = activeTelemetryDeviceId || "";
  const nextMarkup = [
    '<option value="">Todos los dispositivos</option>',
    ...droneItems.map((item) => {
      const label = telemetryLabel(item) || String(item.device_id || "");
      return `<option value="${String(item.device_id || "")}">${label.toUpperCase()}</option>`;
    }),
  ].join("");
  const isFocused = document.activeElement === telemetryDeviceFilter;
  const optionsChanged = nextMarkup !== lastTelemetryFilterSignature;

  if (optionsChanged && !isFocused) {
    telemetryDeviceFilter.innerHTML = nextMarkup;
    lastTelemetryFilterSignature = nextMarkup;
  }
  if (!isFocused && telemetryDeviceFilter.value !== nextValue) {
    telemetryDeviceFilter.value = nextValue;
  }
  telemetryDeviceFilter.disabled = droneItems.length === 0;
}

function telemetryHighlights(item) {
  const extra = item && typeof item.extra === "object" && item.extra ? item.extra : {};
  const parts = [];

  if (extra.drone_label) parts.push(`Alias: ${String(extra.drone_label)}`);
  if (extra.mode) parts.push(`Modo: ${String(extra.mode)}`);
  if (extra.armed !== undefined && extra.armed !== null) {
    parts.push(`Armado: ${extra.armed ? "Sí" : "No"}`);
  }
  if (extra.battery_remaining_pct !== undefined && extra.battery_remaining_pct !== null) {
    parts.push(`Batería: ${formatTelemetryValue(extra.battery_remaining_pct, "%")}`);
  }
  if (extra.satellites_visible !== undefined && extra.satellites_visible !== null) {
    parts.push(`Sat: ${extra.satellites_visible}`);
  }
  if (extra.gps_fix_type !== undefined && extra.gps_fix_type !== null) {
    parts.push(`Fix: ${extra.gps_fix_type}`);
  }
  if (extra.system_status_text) {
    parts.push(`Estado: ${String(extra.system_status_text)}`);
  }
  if (extra.system_id !== undefined && extra.system_id !== null) {
    parts.push(`SYS: ${extra.system_id}`);
  }
  if (extra.component_id !== undefined && extra.component_id !== null) {
    parts.push(`COMP: ${extra.component_id}`);
  }

  return parts.slice(0, 3).join(" · ");
}

function resolveTelemetryTimestamp(item) {
  if (!item || typeof item !== "object") {
    return { raw: null, epochSec: null, timeLabel: "--" };
  }

  const extra = item.extra && typeof item.extra === "object" ? item.extra : {};
  const candidates = [
    item.timestamp,
    extra.timestamp,
    extra.gps_api_timestamp,
    item.source_ts,
    extra.source_ts,
    item.received_ts,
  ];

  for (const value of candidates) {
    if (value === undefined || value === null || value === "") continue;

    if (typeof value === "number" && Number.isFinite(value)) {
      const epochSec = value > 99999999999 ? value / 1000 : value;
      const date = new Date(epochSec * 1000);
      if (!Number.isNaN(date.getTime())) {
        return {
          raw: value,
          epochSec,
          timeLabel: date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
        };
      }
      continue;
    }

    const text = String(value).trim();
    if (!text) continue;

    if (/^\d+(\.\d+)?$/.test(text)) {
      const numeric = Number(text);
      if (Number.isFinite(numeric)) {
        const epochSec = numeric > 99999999999 ? numeric / 1000 : numeric;
        const date = new Date(epochSec * 1000);
        if (!Number.isNaN(date.getTime())) {
          return {
            raw: value,
            epochSec,
            timeLabel: date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
          };
        }
      }
      continue;
    }

    const date = new Date(text);
    if (!Number.isNaN(date.getTime())) {
      return {
        raw: value,
        epochSec: date.getTime() / 1000,
        timeLabel: date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
      };
    }
  }

  return { raw: null, epochSec: null, timeLabel: "--" };
}

function resolveTelemetrySpeed(item) {
  if (!item || typeof item !== "object" || !Number.isFinite(Number(item.lat)) || !Number.isFinite(Number(item.lon))) {
    return 0;
  }

  const { epochSec } = resolveTelemetryTimestamp(item);
  if (epochSec === null) {
    return 0;
  }

  if (!window.__lastTelemetrySpeed) window.__lastTelemetrySpeed = {};
  const extra = item.extra && typeof item.extra === "object" ? item.extra : {};
  const id = String(item.vehicle_id || extra.vehicle_id || item.device_id || extra.gps_api_id || "").trim();
  if (!id) {
    return 0;
  }

  const prev = window.__lastTelemetrySpeed[id];
  const directSpeed = toFiniteNumber(item && item.speed);
  const previousFilteredSpeed = prev && typeof prev.filteredSpeed === "number" ? prev.filteredSpeed : 0;
  let nextFilteredSpeed = previousFilteredSpeed;
  let stationaryCount = prev && Number.isInteger(prev.stationaryCount) ? prev.stationaryCount : 0;
  let rawSpeed = directSpeed !== null && directSpeed > 0 ? directSpeed : null;
  let distanceMeters = null;
  let dt = null;

  if (
    prev
    && typeof prev.lat === "number"
    && typeof prev.lon === "number"
    && typeof prev.epochSec === "number"
    && prev.epochSec !== epochSec
  ) {
    const R = 6371e3;
    const toRad = (deg) => deg * Math.PI / 180;
    const dLat = toRad(Number(item.lat) - prev.lat);
    const dLon = toRad(Number(item.lon) - prev.lon);
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
      + Math.cos(toRad(prev.lat)) * Math.cos(toRad(Number(item.lat)))
      * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    distanceMeters = R * c;
    dt = epochSec - prev.epochSec;

    if (
      rawSpeed === null
      && dt > 0
      && dt <= TELEMETRY_SPEED_MAX_SAMPLE_GAP_SEC
      && distanceMeters >= TELEMETRY_SPEED_MIN_MOVEMENT_METERS
    ) {
      rawSpeed = (distanceMeters / dt) * 3.6;
    }
  }

  const appearsStationary = (
    distanceMeters !== null
    && distanceMeters < TELEMETRY_SPEED_MIN_MOVEMENT_METERS
    && dt !== null
    && dt > 0
  ) || (directSpeed !== null && directSpeed <= TELEMETRY_SPEED_MIN_VISIBLE_KMH);

  if (rawSpeed !== null && rawSpeed > 0) {
    stationaryCount = 0;
    nextFilteredSpeed = previousFilteredSpeed > 0
      ? (previousFilteredSpeed * (1 - TELEMETRY_SPEED_SMOOTHING_FACTOR)) + (rawSpeed * TELEMETRY_SPEED_SMOOTHING_FACTOR)
      : rawSpeed;
  } else if (appearsStationary) {
    stationaryCount += 1;
    if (stationaryCount >= TELEMETRY_SPEED_STATIONARY_CONFIRMATIONS) {
      nextFilteredSpeed = previousFilteredSpeed * TELEMETRY_SPEED_ZERO_DECAY_FACTOR;
    }
  }

  if (nextFilteredSpeed < TELEMETRY_SPEED_MIN_VISIBLE_KMH) {
    nextFilteredSpeed = 0;
  }

  window.__lastTelemetrySpeed[id] = {
    lat: Number(item.lat),
    lon: Number(item.lon),
    epochSec,
    filteredSpeed: nextFilteredSpeed,
    stationaryCount,
  };

  return nextFilteredSpeed;
}

function miningConcessionForItem(item) {
  if (!item || typeof item !== "object") return null;
  const deviceId = String(item.device_id || "").trim();
  if (!deviceId || deviceId !== selectedMiningConcessionDeviceId) return null;
  return selectedMiningConcessionInfo && typeof selectedMiningConcessionInfo === "object"
    ? selectedMiningConcessionInfo
    : null;
}

function buildMiningConcessionLookupKey(item) {
  if (!item || typeof item !== "object" || !hasValidCoordinates(item)) return "";
  return [
    String(item.device_id || "").trim(),
    Number(item.lat).toFixed(6),
    Number(item.lon).toFixed(6),
  ].join("|");
}

function miningConcessionPopupMarkup(properties) {
  const data = properties && typeof properties === "object" ? properties : {};
  return `
    <strong>${escapeHtml(String(data.nombre_concesion || "Concesion minera"))}</strong><br>
    Codigo catastral: ${escapeHtml(String(data.codigo_catastral || "--"))}<br>
    Estado actual: ${escapeHtml(String(data.estado_actual || "--"))}<br>
    Empresa / Titular: ${escapeHtml(String(data.empresa || "--"))}<br>
    Fase del recurso mineral: ${escapeHtml(String(data.fase_recurso_mineral || "--"))}<br>
    Tipo de mineral: ${escapeHtml(String(data.tipo_mineral || "--"))}
  `;
}

function buildMiningConcessionNoteMarkup(item) {
  const concession = miningConcessionForItem(item);
  if (!concession) return "";
  return `
    <aside class="telemetry-concession-card">
      <span class="telemetry-concession-kicker">Concesion minera detectada</span>
      <strong class="telemetry-concession-title">${escapeHtml(String(concession.nombre_concesion || "--"))}</strong>
      <div class="telemetry-concession-grid">
        <article class="telemetry-concession-item">
          <span>Codigo catastral</span>
          <strong>${escapeHtml(String(concession.codigo_catastral || "--"))}</strong>
        </article>
        <article class="telemetry-concession-item">
          <span>Estado actual</span>
          <strong>${escapeHtml(String(concession.estado_actual || "--"))}</strong>
        </article>
        <article class="telemetry-concession-item">
          <span>Empresa / Titular</span>
          <strong>${escapeHtml(String(concession.empresa || "--"))}</strong>
        </article>
        <article class="telemetry-concession-item">
          <span>Fase recurso mineral</span>
          <strong>${escapeHtml(String(concession.fase_recurso_mineral || "--"))}</strong>
        </article>
        <article class="telemetry-concession-item">
          <span>Tipo de mineral</span>
          <strong>${escapeHtml(String(concession.tipo_mineral || "--"))}</strong>
        </article>
      </div>
    </aside>
  `;
}

function miningConcessionStyle(feature) {
  const properties = feature && feature.properties && typeof feature.properties === "object"
    ? feature.properties
    : {};
  const isActive = Boolean(
    selectedMiningConcessionInfo
    && properties.fid !== undefined
    && Number(properties.fid) === Number(selectedMiningConcessionInfo.fid),
  );
  return {
    color: isActive ? "#f97316" : "#f59e0b",
    weight: isActive ? 2.8 : 1.6,
    opacity: isActive ? 0.98 : 0.72,
    fillColor: isActive ? "#f59e0b" : "#facc15",
    fillOpacity: isActive ? 0.2 : 0.08,
  };
}

function refreshMiningConcessionLayerStyles() {
  if (!miningConcessionLayer) return;
  miningConcessionLayer.eachLayer((layer) => {
    if (typeof layer.setStyle === "function") {
      layer.setStyle(miningConcessionStyle(layer.feature));
    }
  });
}

function clearMiningConcessionsLayer() {
  if (miningConcessionViewportRefreshTimerId) {
    clearTimeout(miningConcessionViewportRefreshTimerId);
    miningConcessionViewportRefreshTimerId = null;
  }
  if (miningConcessionLayer) {
    miningConcessionLayer.clearLayers();
  }
  lastMiningConcessionViewportKey = "";
}

function syncMiningToggleUi() {
  if (!telemetryMiningToggle) return;
  telemetryMiningToggle.checked = miningConcessionLayerEnabled;
}

function applyMiningLayerVisibility() {
  syncMiningToggleUi();
  if (!miningConcessionLayerEnabled) {
    clearMiningConcessionsLayer();
    return;
  }
  scheduleMiningConcessionsViewportRefresh(40);
}

function setMiningLayerEnabled(enabled) {
  miningConcessionLayerEnabled = Boolean(enabled);
  persistMiningLayerEnabled(miningConcessionLayerEnabled);
  applyMiningLayerVisibility();
}

function ensureMiningConcessionsLayer() {
  if (!mapInstance || typeof window.L === "undefined") return null;
  if (miningConcessionLayer) return miningConcessionLayer;

  miningConcessionLayer = window.L.geoJSON([], {
    style: miningConcessionStyle,
    onEachFeature: (feature, layer) => {
      layer.bindPopup(miningConcessionPopupMarkup(feature && feature.properties));
    },
  }).addTo(mapInstance);

  return miningConcessionLayer;
}

async function refreshMiningConcessionsViewport() {
  if (!miningConcessionLayerEnabled) {
    clearMiningConcessionsLayer();
    return;
  }
  if (!mapInstance) return;
  const layer = ensureMiningConcessionsLayer();
  if (!layer) return;

  if (mapInstance.getZoom() < ARCOM_CONCESSION_MIN_ZOOM) {
    clearMiningConcessionsLayer();
    return;
  }

  const bounds = mapInstance.getBounds();
  if (!bounds) return;
  const bbox = [
    bounds.getWest().toFixed(6),
    bounds.getSouth().toFixed(6),
    bounds.getEast().toFixed(6),
    bounds.getNorth().toFixed(6),
  ].join(",");
  const viewportKey = `${bbox}|${mapInstance.getZoom()}`;
  if (viewportKey === lastMiningConcessionViewportKey) {
    refreshMiningConcessionLayerStyles();
    return;
  }

  const requestId = ++miningConcessionViewportRequestId;
  try {
    const payload = await fetchJson(`/api/arcom/concessions?bbox=${encodeURIComponent(bbox)}&limit=${ARCOM_CONCESSION_VIEW_LIMIT}`, {
      timeoutMs: 12000,
    });
    if (requestId !== miningConcessionViewportRequestId) return;
    layer.clearLayers();
    const features = Array.isArray(payload && payload.features) ? payload.features : [];
    if (features.length > 0) {
      layer.addData(features);
      refreshMiningConcessionLayerStyles();
    }
    lastMiningConcessionViewportKey = viewportKey;
  } catch (error) {
    if (requestId !== miningConcessionViewportRequestId) return;
    layer.clearLayers();
    lastMiningConcessionViewportKey = "";
  }
}

function scheduleMiningConcessionsViewportRefresh(delayMs = 220) {
  if (miningConcessionViewportRefreshTimerId) {
    clearTimeout(miningConcessionViewportRefreshTimerId);
  }
  miningConcessionViewportRefreshTimerId = window.setTimeout(() => {
    miningConcessionViewportRefreshTimerId = null;
    void refreshMiningConcessionsViewport();
  }, delayMs);
}

async function refreshSelectedMiningConcession(item) {
  const nextLookupKey = buildMiningConcessionLookupKey(item);
  const nextDeviceId = String(item && item.device_id || "").trim();

  if (!nextLookupKey || !nextDeviceId) {
    const hadValue = Boolean(selectedMiningConcessionInfo || selectedMiningConcessionDeviceId);
    selectedMiningConcessionLookupKey = "";
    selectedMiningConcessionDeviceId = "";
    selectedMiningConcessionInfo = null;
    refreshMiningConcessionLayerStyles();
    if (hadValue) {
      renderTelemetryFocus(lastTelemetrySnapshot);
    }
    return;
  }

  if (
    nextLookupKey === selectedMiningConcessionLookupKey
    && nextDeviceId === selectedMiningConcessionDeviceId
  ) {
    return;
  }

  selectedMiningConcessionLookupKey = nextLookupKey;
  const requestId = ++miningConcessionLookupRequestId;

  try {
    const payload = await fetchJson(
      `/api/arcom/concession-lookup?lat=${encodeURIComponent(String(Number(item.lat)))}&lon=${encodeURIComponent(String(Number(item.lon)))}`,
      { timeoutMs: 8000 },
    );
    if (requestId !== miningConcessionLookupRequestId) return;

    selectedMiningConcessionDeviceId = nextDeviceId;
    selectedMiningConcessionInfo = payload && payload.found && payload.concession
      ? payload.concession
      : null;
  } catch (error) {
    if (requestId !== miningConcessionLookupRequestId) return;
    selectedMiningConcessionLookupKey = "";
    selectedMiningConcessionDeviceId = nextDeviceId;
    selectedMiningConcessionInfo = null;
  }

  refreshMiningConcessionLayerStyles();
  renderTelemetryFocus(lastTelemetrySnapshot);
}

function telemetryListMarkup(items) {
  const selectable = getSelectableTelemetryItems(items);
  if (selectable.length === 0) {
    return '<div class="empty-state">No hay vehículos con telemetría disponible.</div>';
  }

  return `
    <div class="telemetry-focus-summary">
      <div class="telemetry-focus-summary-head">
        <strong>Selecciona un vehículo para abrir su panel</strong>
      </div>
      <div class="telemetry-summary telemetry-summary-embedded">
        ${selectable.map((item) => `
          <article class="telemetry-row ${isSelectedTelemetryItem(item) ? "is-active" : ""} is-registered-drone" data-telemetry-device-id="${escapeHtml(String(item.device_id || ""))}" data-selectable="true">
            <div class="telemetry-title telemetry-title-compact">
              <strong>${telemetryLabel(item).toUpperCase()}</strong>
            </div>
          </article>
        `).join("")}
      </div>
    </div>
  `;
}

function renderTelemetryFocus(items) {
  if (!telemetryFocusCard) return;
  if (!Array.isArray(items) || items.length === 0) {
    telemetryFocusCard.innerHTML = '<div class="empty-state">Sin telemetría disponible.</div>';
    return;
  }

  const item = getSelectedTelemetryItem(items);
  if (!item) {
    telemetryFocusCard.innerHTML = activeTelemetryDeviceId
      ? '<div class="empty-state">No hay telemetría para el vehículo seleccionado.</div>'
      : telemetryListMarkup(items);
    return;
  }

  const extra = item && typeof item.extra === "object" && item.extra ? item.extra : {};
  const batteryPct = (() => {
    const value = toFiniteNumber(extra.battery_remaining_pct);
    return value === null ? null : clampNumber(value, 0, 100);
  })();
  const batteryFill = batteryPct === null ? 8 : clampNumber(batteryPct, 6, 100);
  const batteryTone = telemetryBatteryTone(batteryPct);
  const batteryVoltage = toFiniteNumber(extra.battery_voltage_v);
  const batteryCurrent = toFiniteNumber(extra.current_battery_a);
  const batteryTemperature = toFiniteNumber(extra.battery_temperature_c);
  const rollDeg = toFiniteNumber(extra.roll_deg);
  const pitchDeg = toFiniteNumber(extra.pitch_deg);
  const yawDeg = normalizeDegrees(extra.yaw_deg);
  const headingDeg = normalizeDegrees(item.heading ?? extra.yaw_deg);
  const pitchShift = pitchDeg === null ? 0 : clampNumber(pitchDeg * 1.15, -28, 28);
  const batteryCaption = [
    batteryVoltage === null ? null : `Voltaje ${formatTelemetryValue(batteryVoltage, " V")}`,
    batteryCurrent === null ? null : `Corriente ${formatTelemetryValue(batteryCurrent, " A")}`,
    batteryTemperature === null ? null : `Temp ${formatTelemetryValue(batteryTemperature, "°C")}`,
  ].filter(Boolean).join(" · ") || "Esperando lectura eléctrica.";
  const messageType = extra.last_message_type ? String(extra.last_message_type) : "--";
  const { timeLabel: hora } = resolveTelemetryTimestamp(item);
  const speed = resolveTelemetrySpeed(item);

  const GPS_FIX_LABELS = ["Sin GPS", "Sin fix", "2D fix", "3D fix", "DGPS", "RTK Float", "RTK Fixed"];
  const gpsFixLabel = extra.gps_fix_type != null ? (GPS_FIX_LABELS[extra.gps_fix_type] ?? `Fix ${extra.gps_fix_type}`) : "--";
  const armedLabel = extra.armed === true ? "ARMADO" : extra.armed === false ? "DESARMADO" : "--";
  const sysStatusLabel = extra.system_status_text ? String(extra.system_status_text).toUpperCase() : "--";
  const satsLabel = extra.satellites_visible != null ? String(extra.satellites_visible) : "--";

  const motionStats = [
    { label: "ID API",      value: String(extra.api_device_id || extra.gps_api_id || "--") },
    { label: "Hora",        value: hora },
    { label: "Velocidad",   value: formatTelemetryValue(speed, " km/h") },
    { label: "Altitud",     value: formatTelemetryValue(item.altitude ?? 0, " m") },
    { label: "Latitud",     value: formatLocationCoordinate(item.lat ?? 0) },
    { label: "Longitud",    value: formatLocationCoordinate(item.lon ?? 0) },
    { label: "Estado",      value: armedLabel },
    { label: "Sistema",     value: sysStatusLabel },
    { label: "Fix GPS",     value: gpsFixLabel },
    { label: "Satélites",   value: satsLabel },
  ];
  const label = escapeHtml(telemetryLabel(item).toUpperCase());
  const typeLabel = escapeHtml(String(item.vehicle_type || item.device_kind || "vehiculo").trim().toUpperCase() || "VEHICULO");
  const identifier = escapeHtml(String(item.device_id || "--"));
  const note = item.notes ? `<div class="telemetry-focus-note">Notas: ${escapeHtml(String(item.notes))}</div>` : "";
  const miningConcessionNote = buildMiningConcessionNoteMarkup(item);
  const batteryValueText = batteryPct === null ? "--" : `${Math.round(batteryPct)}%`;
  const batterySummary = batteryPct === null ? "Sin lectura de batería" : `${Math.round(batteryPct)}% disponible`;
  const rollStyle = `${(rollDeg ?? 0).toFixed(2)}deg`;
  const pitchStyle = `${pitchShift.toFixed(2)}px`;
  const yawStyle = `${(yawDeg ?? headingDeg ?? 0).toFixed(2)}deg`;

  telemetryFocusCard.innerHTML = `
    <div class="telemetry-focus-content">
      <div class="telemetry-focus-top">
        <div class="telemetry-focus-identity">
          <span class="telemetry-focus-kicker">${typeLabel}</span>
          <strong class="telemetry-focus-name">${label}</strong>
          <div class="telemetry-focus-meta">ID ${identifier}</div>
        </div>
        <span class="telemetry-focus-freshness" style="color:${colorForFreshness(item.freshness)}">${telemetryFreshnessLabel(item.freshness)}</span>
      </div>

      <div class="telemetry-battery-card" data-level="${batteryTone}">
        <div class="telemetry-battery-copy">
          <span class="telemetry-battery-kicker">Batería</span>
          <strong>${escapeHtml(batterySummary)}</strong>
        </div>
        <div class="telemetry-battery-visual">
          <div class="telemetry-battery-icon">
            <div class="telemetry-battery-fill" style="width:${batteryFill}%"></div>
          </div>
          <span class="telemetry-battery-value">${escapeHtml(batteryValueText)}</span>
        </div>
      </div>

      <div class="telemetry-focus-info-grid">
        ${miningConcessionNote}
        <div class="telemetry-focus-stats">
          ${motionStats.map((stat) => `
            <article class="telemetry-focus-stat">
              <span>${escapeHtml(stat.label)}</span>
              <strong>${escapeHtml(stat.value)}</strong>
            </article>
          `).join("")}
        </div>
      </div>
      ${note}
    </div>
  `;
}

function ensureMap() {
  if (mapInstance) return true;
  if (!telemetryMap) return false;
  if (typeof window.L === "undefined") {
    telemetryMap.innerHTML = '<div class="empty-state map-empty">Mapa no disponible sin acceso al CDN de Leaflet.</div>';
    return false;
  }

  mapInstance = window.L.map(telemetryMap, {
    zoomControl: true,
    attributionControl: true,
  }).setView([0, 0], 2);

  applyTelemetryMapStyle(activeTelemetryMapStyle, { persist: false });
  setTelemetryMapManualControl(false);
  const onManualMapInteraction = () => {
    if (Date.now() < telemetryMapProgrammaticInteractionUntil) {
      return;
    }
    setTelemetryMapManualControl(true);
  };
  mapInstance.on("dragstart", onManualMapInteraction);
  mapInstance.on("zoomstart", onManualMapInteraction);
  mapInstance.on("moveend", () => {
    scheduleMiningConcessionsViewportRefresh();
  });
  mapInstance.on("zoomend", () => {
    scheduleMiningConcessionsViewportRefresh();
  });
  ensureMiningConcessionsLayer();
  applyMiningLayerVisibility();
  return true;
}

function updateMap(items) {
  if (!telemetryMap && !telemetryFocusCard) return;
  renderTelemetryFocus(items);
  const selectedItem = getSelectedTelemetryItem(items);
  void refreshSelectedMiningConcession(selectedItem);
  if (!ensureMap()) {
    return;
  }
  mapInstance.invalidateSize();

  const visibleItems = getVisibleTelemetryItems(items);
  const valid = Array.isArray(visibleItems)
    ? visibleItems.filter((item) => hasValidCoordinates(item))
    : [];
  const nextIds = new Set();
  const bounds = [];

  valid.forEach((item) => {
    const lat = Number(item.lat);
    const lon = Number(item.lon);
    const cameraName = String(item.camera_name || "");
    const powered = isCameraPowered(cameraName);
    const isActive = isSelectedTelemetryItem(item);
    let marker = mapMarkers.get(item.device_id);
    if (!marker) {
      marker = createMapMarker(mapInstance, lat, lon, {
        powered,
        active: isActive,
        markerKind: telemetryMarkerKind(item),
      });
      marker.on("click", () => {
        if (telemetryDeviceFilter && marker.__deviceId && marker.__isRegisteredVehicle) {
          setTelemetrySelection(marker.__deviceId, { recenter: true });
          if (marker.__cameraName) {
            selectCameraFromMap(marker.__cameraName, { focusMarker: false });
          }
          return;
        }
        if (marker.__cameraName) {
          setTelemetrySelection("", { recenter: false });
          selectCameraFromMap(marker.__cameraName, { focusMarker: false });
        }
      });
      mapMarkers.set(item.device_id, marker);
    } else {
      marker.setLatLng([lat, lon]);
      updateMapMarkerStyle(marker, {
        powered,
        active: isActive,
        markerKind: telemetryMarkerKind(item),
      });
    }
    marker.__cameraName = cameraName;
    marker.__deviceId = String(item.device_id || "");
    marker.__isRegisteredVehicle = isRegisteredVehicleTelemetry(item);
    marker.__markerKind = telemetryMarkerKind(item);
    bindPrettyTooltip(
      marker,
      `${telemetryLabel(item).toUpperCase()} · ${String(item.freshness || "unavailable").toUpperCase()}`,
    );
    bindPrettyPopup(marker, `
      <strong>${telemetryLabel(item).toUpperCase()}</strong><br>
      ID: ${String(item.device_id || "--")}<br>
      ID API: ${escapeHtml(String((item.extra && (item.extra.api_device_id || item.extra.gps_api_id)) || "--"))}<br>
      ${item.vehicle_type ? `Tipo: ${String(item.vehicle_type).toUpperCase()}<br>` : ""}
      Estado cámara: ${cameraName ? cameraPowerLabel(cameraName) : "Sin cámara asociada"}<br>
      Telemetría: ${String(item.freshness || "unavailable").toUpperCase()}<br>
      Lat: ${lat.toFixed(6)}<br>
      Lon: ${lon.toFixed(6)}<br>
      Velocidad: ${formatTelemetryValue(resolveTelemetrySpeed(item), " km/h")}<br>
      Hora: ${escapeHtml(resolveTelemetryTimestamp(item).timeLabel)}<br>
      Rumbo: ${formatTelemetryValue(item.heading, "°")}<br>
      Altitud: ${formatTelemetryValue(item.altitude, " m")}<br>
      ${item.notes ? `Notas: ${String(item.notes)}<br>` : ""}
      ${telemetryHighlights(item) || "Sin detalles extendidos"}
    `);
    nextIds.add(item.device_id);
    bounds.push([lat, lon]);
  });

  for (const [deviceId, marker] of mapMarkers.entries()) {
    if (!nextIds.has(deviceId)) {
      mapInstance.removeLayer(marker);
      mapMarkers.delete(deviceId);
    }
  }

  lastTelemetryCoordinates = bounds;
  const nextSignature = mapCoordinateSignature(bounds);

  if (!telemetryMapManualControl && bounds.length > 0 && (!mapAutoFitDone || nextSignature !== lastTelemetryBoundsSignature)) {
    markTelemetryMapProgrammaticInteraction();
    fitMapToCoordinates(mapInstance, bounds, {
      maxZoom: 15,
      singleZoom: 14,
    });
    mapAutoFitDone = true;
    lastTelemetryBoundsSignature = nextSignature;
  }
  if (bounds.length === 0) {
    lastTelemetryBoundsSignature = "";
  }
  scheduleMiningConcessionsViewportRefresh(120);
}

async function refreshTelemetry() {
  if (!telemetryMap && !telemetryFocusCard) return;
  if (document.visibilityState === "hidden") return;
  try {
    const telemetry = await fetchJson("/api/telemetry", { timeoutMs: 4000 });
    lastTelemetrySnapshot = buildSynchronizedTelemetrySnapshot(telemetry);
    if (telemetryOverlaySourceKind === "telemetry") {
      syncTelemetryMapOverlayFromTelemetrySelection(lastTelemetrySnapshot);
    }
    syncTelemetryDeviceFilter(lastTelemetrySnapshot);
    updateMap(lastTelemetrySnapshot);
  } catch (error) {
    if (telemetryOverlaySourceKind === "telemetry") {
      syncTelemetryMapOverlayFromTelemetrySelection(lastTelemetrySnapshot);
    }
    syncTelemetryDeviceFilter(lastTelemetrySnapshot);
    updateMap(lastTelemetrySnapshot);
  }
}

function stopAll() {
  for (const [name, timer] of reconnectTimers.entries()) {
    clearTimeout(timer);
    reconnectTimers.delete(name);
  }
  for (const name of CAMERAS.map((camera) => camera.name)) {
    const token = (connectionTokens.get(name) || 0) + 1;
    connectionTokens.set(name, token);
    connectInFlight.delete(name);
    closePeer(name);
    closeEmbeddedViewer(name);
  }
  resetTelemetryMapOverlaySurface();
  clearMiningConcessionsLayer();
}

function startPolling() {
  if (!statusIntervalId) {
    statusIntervalId = setInterval(refreshStatus, STATUS_REFRESH_MS);
  }
  if (eventsFeed && !eventIntervalId) {
    eventIntervalId = setInterval(refreshEvents, EVENT_REFRESH_MS);
  }
  if ((telemetryMap || telemetryFocusCard) && !telemetryIntervalId) {
    telemetryIntervalId = setInterval(refreshTelemetry, TELEMETRY_REFRESH_MS);
  }
  if ((vehicleRegistryDetail || vehicleRegistryRailList) && !vehicleRegistryIntervalId) {
    vehicleRegistryIntervalId = setInterval(refreshVehicleRegistry, VEHICLE_REGISTRY_REFRESH_MS);
  }
}

function stopPolling() {
  for (const timerId of [statusIntervalId, eventIntervalId, telemetryIntervalId, vehicleRegistryIntervalId]) {
    if (timerId) clearInterval(timerId);
  }
  statusIntervalId = null;
  eventIntervalId = null;
  telemetryIntervalId = null;
  vehicleRegistryIntervalId = null;
}

if (audioToggle) {
  audioToggle.addEventListener("click", () => {
    if (!activeCamera || !supportsAudio(activeCamera)) return;
    audioEnabled = !audioEnabled;
    applyAudioState();
  });
}

if (audioVolume) {
  audioVolume.addEventListener("input", applyAudioState);
}

if (cameraRegisterOpen) {
  cameraRegisterOpen.addEventListener("click", openCameraRegisterModal);
}

if (vehicleRegisterOpen) {
  vehicleRegisterOpen.addEventListener("click", () => {
    void openVehicleRegisterModal();
  });
}

if (cameraRegisterForm) {
  cameraRegisterForm.addEventListener("submit", registerCamera);
}

if (vehicleRegisterForm) {
  vehicleRegisterForm.addEventListener("submit", registerVehicle);
}

if (roleAdminForm) {
  roleAdminForm.addEventListener("submit", submitRoleAdminForm);
}

if (userAdminForm) {
  userAdminForm.addEventListener("submit", submitUserAdminForm);
}

if (organizationAdminForm) {
  organizationAdminForm.addEventListener("submit", submitOrganizationAdminForm);
}

if (cameraAdminForm) {
  cameraAdminForm.addEventListener("submit", submitCameraAdminForm);
}

if (cameraRegisterName) {
  cameraRegisterName.addEventListener("input", () => setCameraRegisterFeedback(""));
}

if (vehicleRegisterType) {
  vehicleRegisterType.addEventListener("change", () => {
    updateVehicleRegisterTypeCopy();
    setVehicleRegisterFeedback("");
  });
}

if (vehicleRegisterTelemetryMode) {
  vehicleRegisterTelemetryMode.addEventListener("change", () => {
    updateVehicleRegisterTypeCopy();
    setVehicleRegisterFeedback("");
  });
}

if (vehicleRegisterOrganization) {
  vehicleRegisterOrganization.addEventListener("change", () => setVehicleRegisterFeedback(""));
}

if (vehicleRegisterOwner) {
  vehicleRegisterOwner.addEventListener("change", () => setVehicleRegisterFeedback(""));
}

if (vehicleRegisterLabel) {
  vehicleRegisterLabel.addEventListener("input", () => setVehicleRegisterFeedback(""));
}

if (vehicleRegisterIdentifier) {
  vehicleRegisterIdentifier.addEventListener("input", () => setVehicleRegisterFeedback(""));
}

if (vehicleRegisterNotes) {
  vehicleRegisterNotes.addEventListener("input", () => setVehicleRegisterFeedback(""));
}

if (vehicleRegisterCameraList) {
  vehicleRegisterCameraList.addEventListener("change", (event) => {
    const checkbox = event.target instanceof Element
      ? event.target.closest("[data-vehicle-camera-checkbox]")
      : null;
    if (!(checkbox instanceof HTMLInputElement)) return;
    const cameraId = String(checkbox.getAttribute("data-vehicle-camera-checkbox") || "").trim();
    const positionInput = vehicleRegisterCameraList.querySelector(`[data-vehicle-camera-position="${cameraId}"]`);
    if (positionInput instanceof HTMLInputElement) {
      positionInput.disabled = !checkbox.checked;
      if (!checkbox.checked) {
        positionInput.value = "";
      }
    }
    const card = checkbox.closest(".vehicle-register-camera-item");
    if (card) {
      card.classList.toggle("is-selected", checkbox.checked);
    }
    setVehicleRegisterFeedback("");
  });
}

if (roleAdminCode) {
  roleAdminCode.addEventListener("input", () => setRoleAdminFeedback(""));
}

if (roleAdminName) {
  roleAdminName.addEventListener("input", () => setRoleAdminFeedback(""));
}

if (roleAdminOrder) {
  roleAdminOrder.addEventListener("input", () => setRoleAdminFeedback(""));
}

if (roleAdminSystem) {
  roleAdminSystem.addEventListener("change", () => setRoleAdminFeedback(""));
}

if (userAdminUsername) {
  userAdminUsername.addEventListener("input", () => setUserAdminFeedback(""));
}

if (userAdminEmail) {
  userAdminEmail.addEventListener("input", () => setUserAdminFeedback(""));
}

if (userAdminName) {
  userAdminName.addEventListener("input", () => setUserAdminFeedback(""));
}

if (userAdminLastName) {
  userAdminLastName.addEventListener("input", () => setUserAdminFeedback(""));
}

if (userAdminPhone) {
  userAdminPhone.addEventListener("input", () => setUserAdminFeedback(""));
}

if (userAdminPassword) {
  userAdminPassword.addEventListener("input", () => setUserAdminFeedback(""));
}

if (userAdminRole) {
  userAdminRole.addEventListener("change", () => setUserAdminFeedback(""));
}

if (userAdminActive) {
  userAdminActive.addEventListener("change", () => setUserAdminFeedback(""));
}

if (organizationAdminName) {
  organizationAdminName.addEventListener("input", () => setOrganizationAdminFeedback(""));
}

if (organizationAdminDescription) {
  organizationAdminDescription.addEventListener("input", () => setOrganizationAdminFeedback(""));
}

if (organizationAdminOwner) {
  organizationAdminOwner.addEventListener("change", () => setOrganizationAdminFeedback(""));
}

if (organizationAdminActive) {
  organizationAdminActive.addEventListener("change", () => setOrganizationAdminFeedback(""));
}

[
  cameraAdminName,
  cameraAdminDescription,
  cameraAdminRtspUrl,
  cameraAdminCode,
  cameraAdminBrand,
  cameraAdminModel,
  cameraAdminSerial,
  cameraAdminStreamUser,
  cameraAdminStreamPassword,
  cameraAdminLat,
  cameraAdminLon,
  cameraAdminAltitude,
  cameraAdminAddress,
  cameraAdminReference,
  cameraAdminVehiclePosition,
].forEach((field) => {
  if (!field) return;
  field.addEventListener("input", () => setCameraAdminFeedback(""));
});

if (cameraAdminStreamUrl) {
  cameraAdminStreamUrl.addEventListener("input", () => {
    const currentValue = cameraAdminStreamUrl.value.trim();
    const generatedValue = buildCameraAdminGeneratedStreamUrl({
      protocolCode: ensureCameraAdminDefaultProtocol(),
      uniqueCode: cameraAdminCode && cameraAdminCode.value,
      inferenceEnabled: isCameraAdminInferenceEnabledSelected(),
    });
    cameraAdminStreamUrlAutoManaged = Boolean(generatedValue && currentValue === generatedValue);
    if (cameraAdminLastGeneratedStreamUrl && currentValue !== cameraAdminLastGeneratedStreamUrl) {
      cameraAdminStreamUrlAutoManaged = false;
    }
    setCameraAdminFeedback("");
  });
}

[
  cameraAdminOrganization,
  cameraAdminOwner,
  cameraAdminBrand,
  cameraAdminProtocol,
  cameraAdminInferenceEnabled,
  cameraAdminActive,
  cameraAdminVehicle,
].forEach((field) => {
  if (!field) return;
  field.addEventListener("change", () => setCameraAdminFeedback(""));
});

[cameraAdminLat, cameraAdminLon].forEach((field) => {
  if (!field) return;
  field.addEventListener("input", () => {
    updateCameraAdminMapSummary();
  });
});

if (cameraAdminType) {
  cameraAdminType.addEventListener("change", () => {
    setCameraAdminFeedback("");
    syncCameraAdminTypeState();
    if (cameraAdminUsesRtspAssistantType()) {
      openCameraAdminMapModal();
    }
  });
}

if (cameraAdminBrand) {
  cameraAdminBrand.addEventListener("change", () => {
    setCameraAdminFeedback("");
    syncCameraAdminBrandState();
  });
}

if (cameraAdminBrandCustom) {
  cameraAdminBrandCustom.addEventListener("input", () => {
    setCameraAdminFeedback("");
  });
}

if (cameraAdminProtocol) {
  cameraAdminProtocol.addEventListener("change", () => {
    syncCameraAdminGeneratedStreamUrl();
    syncCameraAdminStreamUrlState();
  });
}

if (cameraAdminCode) {
  cameraAdminCode.addEventListener("input", () => {
    syncCameraAdminGeneratedStreamUrl();
    syncCameraAdminStreamUrlState();
  });
}

if (cameraAdminName) {
  cameraAdminName.addEventListener("change", () => {
    syncCameraAdminInferenceName();
  });
}

if (cameraAdminInferenceEnabled) {
  cameraAdminInferenceEnabled.addEventListener("change", () => {
    syncCameraAdminInferenceName();
    syncCameraAdminGeneratedStreamUrl();
    syncCameraAdminStreamUrlState();
  });
}

[
  cameraAdminRtspIp,
  cameraAdminRtspPort,
  cameraAdminRtspChannel,
  cameraAdminRtspSubstream,
  cameraAdminRtspPath,
  cameraAdminRtspUrl,
  cameraAdminStreamUser,
  cameraAdminStreamPassword,
].forEach((field) => {
  if (!field) return;
  const eventName = field.tagName === "SELECT" ? "change" : "input";
  field.addEventListener(eventName, () => {
    setCameraAdminRtspPreview("");
    setCameraAdminFeedback("");
    syncCameraAdminStreamUrlState();
  });
});

if (cameraAdminRtspGenerate) {
  cameraAdminRtspGenerate.addEventListener("click", () => {
    void generateCameraAdminRtspUrl();
  });
}

if (cameraAdminMapOpen) {
  cameraAdminMapOpen.addEventListener("click", openCameraAdminMapModal);
}

if (cameraAdminMapClose) {
  cameraAdminMapClose.addEventListener("click", closeCameraAdminMapModal);
}

if (cameraAdminMapCancel) {
  cameraAdminMapCancel.addEventListener("click", closeCameraAdminMapModal);
}

if (cameraAdminMapBackdrop) {
  cameraAdminMapBackdrop.addEventListener("click", closeCameraAdminMapModal);
}

if (cameraAdminMapApply) {
  cameraAdminMapApply.addEventListener("click", applyCameraAdminMapSelection);
}

if (roleAdminReset) {
  roleAdminReset.addEventListener("click", () => resetRoleAdminForm());
}

if (userAdminReset) {
  userAdminReset.addEventListener("click", () => resetUserAdminForm());
}

if (organizationAdminReset) {
  organizationAdminReset.addEventListener("click", () => resetOrganizationAdminForm());
}

if (cameraAdminReset) {
  cameraAdminReset.addEventListener("click", () => resetCameraAdminForm({ creationMode: "camera" }));
}

if (cameraAdminRbox) {
  cameraAdminRbox.addEventListener("click", prepareCameraAdminRboxPreset);
}

if (roleAdminDelete) {
  roleAdminDelete.addEventListener("click", () => {
    void deleteSelectedRoleAdmin();
  });
}

if (userAdminDelete) {
  userAdminDelete.addEventListener("click", () => {
    void deleteSelectedUserAdmin();
  });
}

if (organizationAdminDelete) {
  organizationAdminDelete.addEventListener("click", () => {
    void deleteSelectedOrganizationAdmin();
  });
}

if (cameraAdminDelete) {
  cameraAdminDelete.addEventListener("click", () => {
    void deleteSelectedCameraAdmin();
  });
}

if (platePreviewCopy) {
  platePreviewCopy.addEventListener("click", () => {
    void copyPlatePreviewText();
  });
}

if (platePreviewChoices.length) {
  const initialPlateChoice = platePreviewChoices.find((choice) => choice.classList.contains("is-active"))
    || platePreviewChoices[0];
  const initialPlateValue = String(platePreviewOutput?.value || "").trim()
    || String(initialPlateChoice?.dataset.plateValue || "").trim();
  if (initialPlateValue) {
    if (platePreviewOutput) {
      platePreviewOutput.value = initialPlateValue;
    }
    syncPlatePreviewChoiceState(initialPlateValue);
  }

  platePreviewChoices.forEach((choice) => {
    choice.addEventListener("click", () => {
      void setPlatePreviewSelection(choice.dataset.plateValue, choice.dataset.plateFile);
    });
  });
}

[plateFileModalBackdrop, plateFileClose].forEach((control) => {
  if (!control) return;
  control.addEventListener("click", closePlateFileModal);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && plateFileModal && !plateFileModal.hidden) {
    closePlateFileModal();
  }
});

if (userAdminRefresh) {
  userAdminRefresh.addEventListener("click", () => {
    setRoleAdminFeedback("");
    setUserAdminFeedback("");
    setOrganizationAdminFeedback("");
    setCameraAdminFeedback("");
    void refreshUserAdmin({ preserveDraft: true });
  });
}

[
  vehicleRegisterApiDeviceId,
].forEach((field) => {
  if (!field) return;
  field.addEventListener("input", () => setVehicleRegisterFeedback(""));
});

if (cameraRegisterSource) {
  cameraRegisterSource.addEventListener("input", () => setCameraRegisterFeedback(""));
}

if (cameraRegisterLat) {
  cameraRegisterLat.addEventListener("input", () => {
    setCameraRegisterFeedback("");
    syncCameraRegisterMarkerFromInputs();
  });
}

if (cameraRegisterLon) {
  cameraRegisterLon.addEventListener("input", () => {
    setCameraRegisterFeedback("");
    syncCameraRegisterMarkerFromInputs();
  });
}

if (cameraRegisterClose) {
  cameraRegisterClose.addEventListener("click", closeCameraRegisterModal);
}

if (vehicleRegisterClose) {
  vehicleRegisterClose.addEventListener("click", closeVehicleRegisterModal);
}

if (vehicleRegisterDelete) {
  vehicleRegisterDelete.addEventListener("click", () => {
    if (!editingVehicleRegistrationId) return;
    void deleteVehicleRegistryEntry(editingVehicleRegistrationId, { closeModal: true });
  });
}

if (cameraRegisterCancel) {
  cameraRegisterCancel.addEventListener("click", closeCameraRegisterModal);
}

if (vehicleRegisterCancel) {
  vehicleRegisterCancel.addEventListener("click", closeVehicleRegisterModal);
}

if (cameraRegisterBackdrop) {
  cameraRegisterBackdrop.addEventListener("click", closeCameraRegisterModal);
}

if (vehicleRegisterBackdrop) {
  vehicleRegisterBackdrop.addEventListener("click", closeVehicleRegisterModal);
}

if (telemetryDeviceFilter) {
  telemetryDeviceFilter.addEventListener("change", () => {
    setTelemetrySelection(telemetryDeviceFilter.value, { recenter: true });
  });
  telemetryDeviceFilter.addEventListener("blur", () => {
    syncTelemetryDeviceFilter(lastTelemetrySnapshot);
  });
}

if (logsModeSwitch) {
  logsModeSwitch.addEventListener("click", (event) => {
    const button = event.target instanceof Element ? event.target.closest("[data-log-mode]") : null;
    if (!button) return;
    const nextMode = String(button.getAttribute("data-log-mode") || "").trim();
    if (!nextMode || nextMode === activeLogsMode) return;
    activeLogsMode = nextMode;
    selectedLogEntryId = null;
    renderLogsDashboard(lastEventsSnapshot, lastLogsTelemetry, lastLogVehicleRegistry);
  });
}

if (eventsDeviceFilter) {
  eventsDeviceFilter.addEventListener("change", () => {
    activeLogsDeviceId = String(eventsDeviceFilter.value || "").trim();
    selectedLogEntryId = null;
    renderLogsDashboard(lastEventsSnapshot, lastLogsTelemetry, lastLogVehicleRegistry);
  });
}

if (eventsFeed) {
  const selectLogEntryFromTarget = (target) => {
    const row = target instanceof Element ? target.closest("[data-log-entry-id]") : null;
    if (!row) return;
    const nextId = String(row.getAttribute("data-log-entry-id") || "").trim();
    if (!nextId) return;
    selectedLogEntryId = nextId;
    renderLogsDashboard(lastEventsSnapshot, lastLogsTelemetry, lastLogVehicleRegistry);
  };

  eventsFeed.addEventListener("click", (event) => {
    selectLogEntryFromTarget(event.target);
  });

  eventsFeed.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const row = event.target instanceof Element ? event.target.closest("[data-log-entry-id]") : null;
    if (!row) return;
    event.preventDefault();
    selectedLogEntryId = String(row.getAttribute("data-log-entry-id") || "").trim();
    renderLogsDashboard(lastEventsSnapshot, lastLogsTelemetry, lastLogVehicleRegistry);
  });
}

if (telemetryFocusCard) {
  telemetryFocusCard.addEventListener("click", (event) => {
    const row = event.target instanceof Element
      ? event.target.closest("[data-telemetry-device-id][data-selectable='true']")
      : null;
    if (!row) return;
    setTelemetrySelection(row.getAttribute("data-telemetry-device-id"), { recenter: true });
  });
}

if (telemetryMapRecenter) {
  telemetryMapRecenter.addEventListener("click", requestTelemetryMapRecenter);
}

if (telemetryMiningToggle) {
  telemetryMiningToggle.addEventListener("change", () => {
    setMiningLayerEnabled(telemetryMiningToggle.checked);
  });
}

if (telemetryMapStyleSelect) {
  telemetryMapStyleSelect.value = activeTelemetryMapStyle;
  telemetryMapStyleSelect.addEventListener("change", () => {
    applyTelemetryMapStyle(String(telemetryMapStyleSelect.value || "satellite").trim().toLowerCase());
    if (mapInstance) {
      window.requestAnimationFrame(() => {
        try {
          mapInstance.invalidateSize();
        } catch (error) {}
      });
    }
  });
}

if (telemetryMapOverlayClose) {
  telemetryMapOverlayClose.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    hideTelemetryMapOverlay();
  });
}

if (locationsSummary) {
  locationsSummary.addEventListener("click", (event) => {
    const row = event.target instanceof Element ? event.target.closest("[data-camera-name]") : null;
    if (!row) return;
    const cameraName = row.getAttribute("data-camera-name") || "";
    if (!cameraName) return;
    selectCameraFromMap(cameraName, { focusMarker: true });
  });
}

if (vehicleRegistryRailList) {
  vehicleRegistryRailList.addEventListener("click", (event) => {
    const button = event.target instanceof Element
      ? event.target.closest("[data-vehicle-registry-key]")
      : null;
    if (!button) return;
    const nextKey = String(button.getAttribute("data-vehicle-registry-key") || "").trim();
    if (!nextKey) return;
    selectedVehicleRegistryKey = nextKey;
    renderVehicleRegistry(lastVehicleRegistrySnapshot);
  });
}

if (vehicleRegistryDetail) {
  vehicleRegistryDetail.addEventListener("click", (event) => {
    const button = event.target instanceof Element
      ? event.target.closest("[data-vehicle-action][data-vehicle-registration-id]")
      : null;
    if (!button) return;
    const registrationId = normalizeVehicleRegistrationId(button.getAttribute("data-vehicle-registration-id"));
    if (!registrationId) return;
    const action = String(button.getAttribute("data-vehicle-action") || "").trim().toLowerCase();
    const item = findVehicleRegistryItemByRegistrationId(registrationId);
    if (!item) return;
    if (action === "edit") {
      void openVehicleRegisterModal(item);
      return;
    }
    if (action === "delete") {
      void deleteVehicleRegistryEntry(registrationId);
    }
  });
}

if (roleAdminRailList) {
  roleAdminRailList.addEventListener("click", (event) => {
    const button = event.target instanceof Element
      ? event.target.closest("[data-role-admin-id]")
      : null;
    if (!button) return;
    selectedRoleAdminId = normalizeRoleAdminId(button.getAttribute("data-role-admin-id"));
    setRoleAdminFeedback("");
    syncRoleAdminFormState({ preserveDraft: false });
    renderRoleAdminList(lastRoleAdminSnapshot);
  });
}

if (userAdminRailList) {
  userAdminRailList.addEventListener("click", (event) => {
    const button = event.target instanceof Element
      ? event.target.closest("[data-user-admin-id]")
      : null;
    if (!button) return;
    selectedUserAdminId = normalizeUserAdminId(button.getAttribute("data-user-admin-id"));
    setUserAdminFeedback("");
    syncUserAdminFormState({ preserveDraft: false });
    renderUserAdminList(lastUserAdminSnapshot);
  });
}

if (organizationAdminRailList) {
  organizationAdminRailList.addEventListener("click", (event) => {
    const button = event.target instanceof Element
      ? event.target.closest("[data-organization-admin-id]")
      : null;
    if (!button) return;
    selectedOrganizationAdminId = normalizeOrganizationAdminId(button.getAttribute("data-organization-admin-id"));
    setOrganizationAdminFeedback("");
    syncOrganizationAdminFormState({ preserveDraft: false });
    renderOrganizationAdminList(lastOrganizationAdminSnapshot);
  });
}

if (cameraAdminRailList) {
  cameraAdminRailList.addEventListener("click", (event) => {
    const button = event.target instanceof Element
      ? event.target.closest("[data-camera-admin-id]")
      : null;
    if (!button) return;
    selectedCameraAdminId = normalizeCameraAdminId(button.getAttribute("data-camera-admin-id"));
    setCameraAdminFeedback("");
    syncCameraAdminFormState({ preserveDraft: false });
    renderCameraAdminList(lastCameraAdminSnapshot);
  });
}

if (focusClose) {
  focusClose.addEventListener("click", clearFocus);
}

if (dashboardCameraPreviewClose) {
  dashboardCameraPreviewClose.addEventListener("click", () => {
    clearDashboardPinnedCamera();
  });
}

dashboardMobilePanelButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const nextView = String(button.dataset.dashboardMobileView || "").trim().toLowerCase();
    setDashboardMobilePanel(nextView || "map");
  });
});

if (sidebarToggle) {
  sidebarToggle.addEventListener("click", () => {
    if (!appShell) return;
    if (isMobileSidebarViewport()) {
      applySidebarState(!appShell.classList.contains("is-sidebar-collapsed"));
      return;
    }
    const willCollapse = !appShell.classList.contains("is-sidebar-collapsed");
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, willCollapse ? "1" : "0");
    applySidebarState(willCollapse);
  });
}

sidebarNavLinks.forEach((link) => {
  link.addEventListener("click", () => {
    sidebarNavLinks.forEach((item) => item.classList.remove("is-current"));
    logoutButtons.forEach((button) => button.classList.remove("is-current"));
    link.classList.add("is-current");
    closeMobileSidebar();
  });
});

logoutButtons.forEach((button) => {
  button.addEventListener("click", (event) => {
    event.preventDefault();
    closeMobileSidebar();
    void performLogout();
  });
});

document.addEventListener("pointerdown", (event) => {
  if (!appShell || !isMobileSidebarViewport()) return;
  if (appShell.classList.contains("is-sidebar-collapsed")) return;
  if (!(event.target instanceof Element)) return;
  if (event.target.closest("#sidebar-toggle")) return;
  if (event.target.closest("#app-sidebar")) return;
  closeMobileSidebar();
});

window.addEventListener("beforeunload", () => {
  stopPolling();
  stopAll();
});

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") {
    stopPolling();
    stopAll();
  } else {
    syncStreaming();
    startPolling();
    refreshStatus();
    refreshTelemetry();
    refreshEvents();
    refreshVehicleRegistry();
    refreshVehicleRegistryFormOptions();
    refreshUserAdmin({ preserveDraft: true });
    if (telemetryOverlayCameraName) {
      void renderTelemetryMapOverlayPreview();
    }
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && isCameraAdminMapModalOpen()) {
    closeCameraAdminMapModal();
    return;
  }
  if (event.key === "Escape" && isCameraRegisterModalOpen()) {
    closeCameraRegisterModal();
    return;
  }
  if (event.key === "Escape" && telemetryMapOverlayBox && !telemetryMapOverlayBox.hidden) {
    hideTelemetryMapOverlay();
    return;
  }
  if (event.key === "Escape" && isVehicleRegisterModalOpen()) {
    closeVehicleRegisterModal();
    return;
  }
  if (event.key === "Escape" && isMobileSidebarViewport() && appShell && !appShell.classList.contains("is-sidebar-collapsed")) {
    closeMobileSidebar();
  }
});

window.addEventListener("resize", syncViewportMetrics);
window.addEventListener("resize", syncStreaming);
window.addEventListener("resize", syncSidebarForViewport);
window.addEventListener("orientationchange", syncViewportMetrics);
window.addEventListener("orientationchange", syncStreaming);
window.addEventListener("hashchange", setActiveSidebarLink);
if (navigator.connection && typeof navigator.connection.addEventListener === "function") {
  navigator.connection.addEventListener("change", syncStreaming);
}
if (window.visualViewport && typeof window.visualViewport.addEventListener === "function") {
  window.visualViewport.addEventListener("resize", syncViewportMetrics);
}

activeTheme = resolveInitialTheme();
miningConcessionLayerEnabled = resolveInitialMiningLayerEnabled();
applyTheme(activeTheme, { persist: false });
ensureThemeToggle();
observeLayoutChanges();
syncViewportMetrics();
syncSidebarForViewport();
syncSidebarLinkLabels();
setActiveSidebarLink();
if (pageUsesDashboardMobilePanels()) {
  setDashboardMobilePanel(getDashboardPinnedCameraNames().length > 0 ? "cameras" : "map", { force: true });
}
updateCameraRegisterLocationSummary();
updateCameraAdminMapSummary();
updateTelemetryMapOverlayCopy();
updateVehicleRegisterTypeCopy();
syncMiningToggleUi();
renderSwitcher();
applyCapabilityBadges();
bindCardInteractions();
if (!pageSupportsStreaming()) {
  activeCamera = null;
}
updateFocusUi();
syncStreaming();
startPolling();
refreshStatus();
refreshTelemetry();
refreshEvents();
refreshVehicleRegistry();
refreshVehicleRegistryFormOptions();
refreshUserAdmin({ preserveDraft: true });
})();
