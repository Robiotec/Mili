from typing import Any, Dict, Optional
from dataclasses import asdict, dataclass, field

@dataclass
class TelemetryData:
    connected: bool = False
    last_heartbeat: float = 0.0

    drone_id: Optional[str] = None
    drone_label: Optional[str] = None
    autopilot_uid: Optional[int] = None

    system_id: Optional[int] = None
    component_id: Optional[int] = None
    autopilot: Optional[int] = None
    vehicle_type: Optional[int] = None

    mode: str = "UNKNOWN"
    armed: bool = False
    autopilot_type: Optional[str] = None
    vehicle_type_name: Optional[str] = None
    system_status_text: Optional[str] = None

    battery_voltage_v: Optional[float] = None
    battery_remaining_pct: Optional[int] = None
    current_battery_a: Optional[float] = None
    battery_consumed_mah: Optional[int] = None
    battery_energy_hj: Optional[int] = None
    battery_temperature_c: Optional[float] = None
    battery_cell_voltages_v: list[float] = field(default_factory=list)
    cpu_load_pct: Optional[float] = None
    comm_drop_rate_pct: Optional[float] = None

    lat: Optional[float] = None
    lon: Optional[float] = None
    alt_rel_m: Optional[float] = None
    alt_abs_m: Optional[float] = None
    home_lat: Optional[float] = None
    home_lon: Optional[float] = None
    home_alt_m: Optional[float] = None

    roll_rad: Optional[float] = None
    pitch_rad: Optional[float] = None
    yaw_rad: Optional[float] = None

    roll_deg: Optional[float] = None
    pitch_deg: Optional[float] = None
    yaw_deg: Optional[float] = None
    rollspeed_rad_s: Optional[float] = None
    pitchspeed_rad_s: Optional[float] = None
    yawspeed_rad_s: Optional[float] = None

    groundspeed_m_s: Optional[float] = None
    airspeed_m_s: Optional[float] = None
    climb_m_s: Optional[float] = None
    heading_deg: Optional[int] = None
    throttle_pct: Optional[int] = None
    vel_north_m_s: Optional[float] = None
    vel_east_m_s: Optional[float] = None
    vel_down_m_s: Optional[float] = None
    wind_speed_m_s: Optional[float] = None
    wind_direction_deg: Optional[float] = None
    wind_speed_z_m_s: Optional[float] = None
    local_x_m: Optional[float] = None
    local_y_m: Optional[float] = None
    local_z_m: Optional[float] = None
    local_vx_m_s: Optional[float] = None
    local_vy_m_s: Optional[float] = None
    local_vz_m_s: Optional[float] = None

    gps_fix_type: Optional[int] = None
    satellites_visible: Optional[int] = None
    eph: Optional[float] = None
    epv: Optional[float] = None
    gps_speed_m_s: Optional[float] = None
    gps_course_deg: Optional[float] = None
    gps_alt_m: Optional[float] = None

    mav_type: Optional[str] = None
    system_status: Optional[int] = None
    mission_current_seq: Optional[int] = None
    rssi: Optional[int] = None
    time_unix_usec: Optional[int] = None
    time_boot_ms: Optional[int] = None
    last_status_text: Optional[str] = None

    last_message_type: Optional[str] = None
    last_update_ts: float = 0.0
    attitude_quaternion: Dict[str, Any] = field(default_factory=dict)
    imu_raw: Dict[str, Any] = field(default_factory=dict)
    imu_scaled_2: Dict[str, Any] = field(default_factory=dict)
    imu_scaled_3: Dict[str, Any] = field(default_factory=dict)
    imu_highres: Dict[str, Any] = field(default_factory=dict)
    pressure: Dict[str, Any] = field(default_factory=dict)
    pressure_2: Dict[str, Any] = field(default_factory=dict)
    pressure_3: Dict[str, Any] = field(default_factory=dict)
    power: Dict[str, Any] = field(default_factory=dict)
    hwstatus: Dict[str, Any] = field(default_factory=dict)
    vibration: Dict[str, Any] = field(default_factory=dict)
    ekf: Dict[str, Any] = field(default_factory=dict)
    ahrs2: Dict[str, Any] = field(default_factory=dict)
    ahrs3: Dict[str, Any] = field(default_factory=dict)
    global_position_cov: Dict[str, Any] = field(default_factory=dict)
    local_position_cov: Dict[str, Any] = field(default_factory=dict)
    gps2: Dict[str, Any] = field(default_factory=dict)
    rangefinder: Dict[str, Any] = field(default_factory=dict)
    distance_sensor: Dict[str, Any] = field(default_factory=dict)
    optical_flow: Dict[str, Any] = field(default_factory=dict)
    nav_controller: Dict[str, Any] = field(default_factory=dict)
    rc_inputs: Dict[str, Any] = field(default_factory=dict)
    servo_outputs: Dict[str, Any] = field(default_factory=dict)
    autopilot_version_info: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    status_texts: list[Dict[str, Any]] = field(default_factory=list)
    message_counts: Dict[str, int] = field(default_factory=dict)
    recent_messages: list[Dict[str, Any]] = field(default_factory=list)
    raw_messages: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
