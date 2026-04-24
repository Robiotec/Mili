from __future__ import annotations

import json
import logging
import os
import select
import shlex
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional


class SSHError(Exception):
    """Error general de conexión o ejecución SSH."""


class SSHConnectionError(SSHError):
    """Error al establecer conexión SSH."""


class SSHCommandError(SSHError):
    """Error al ejecutar comando remoto por SSH."""


DEFAULT_CROPS_SSH_HOST = "100.93.62.24"
DEFAULT_CROPS_SSH_USER = "robiotec"
DEFAULT_CROPS_SSH_PORT = 22
DEFAULT_CROPS_SSH_KEY_PATH = str(Path.home() / ".ssh" / "id_ed25519")
DEFAULT_CROPS_REMOTE_MANIFEST_PATH = (
    "/home/robiotec/Documents/VICTOR/Object_Recognition/unified/results/manifest.jsonl"
)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def get_default_crops_remote_manifest_path() -> str:
    return (
        os.getenv("CROPS_REMOTE_MANIFEST_PATH", DEFAULT_CROPS_REMOTE_MANIFEST_PATH).strip()
        or DEFAULT_CROPS_REMOTE_MANIFEST_PATH
    )


def build_default_crops_ssh_config(
    *,
    connect_timeout: Optional[int] = None,
    command_timeout: Optional[int] = None,
    max_retries: Optional[int] = None,
    retry_delay: Optional[int] = None,
    log_level: int = logging.INFO,
) -> "SSHConfig":
    """
    Construye la configuración SSH base para leer los crops remotos.
    Se puede sobrescribir con variables CROPS_SSH_* sin tocar código.
    """
    host = (
        os.getenv("CROPS_SSH_HOST", DEFAULT_CROPS_SSH_HOST).strip()
        or DEFAULT_CROPS_SSH_HOST
    )
    user = (
        os.getenv("CROPS_SSH_USER", DEFAULT_CROPS_SSH_USER).strip()
        or DEFAULT_CROPS_SSH_USER
    )
    key_path = os.getenv("CROPS_SSH_KEY_PATH", DEFAULT_CROPS_SSH_KEY_PATH).strip()
    if key_path:
        key_path = str(Path(key_path).expanduser())
    return SSHConfig(
        host=host,
        user=user,
        port=_env_int("CROPS_SSH_PORT", DEFAULT_CROPS_SSH_PORT),
        key_path=key_path or None,
        connect_timeout=(
            connect_timeout
            if connect_timeout is not None
            else _env_int("CROPS_SSH_CONNECT_TIMEOUT", 10)
        ),
        command_timeout=(
            command_timeout
            if command_timeout is not None
            else _env_int("CROPS_SSH_COMMAND_TIMEOUT", 30)
        ),
        max_retries=(
            max(1, max_retries)
            if max_retries is not None
            else max(1, _env_int("CROPS_SSH_MAX_RETRIES", 3))
        ),
        retry_delay=(
            max(0, retry_delay)
            if retry_delay is not None
            else max(0, _env_int("CROPS_SSH_RETRY_DELAY", 4))
        ),
        strict_host_key_checking=(
            os.getenv("CROPS_SSH_STRICT_HOST_KEY_CHECKING", "accept-new").strip()
            or "accept-new"
        ),
        log_level=log_level,
    )


@dataclass
class SSHConfig:
    host: str
    user: str
    port: int = 22
    key_path: Optional[str] = None
    connect_timeout: int = 10
    command_timeout: int = 60
    max_retries: int = 3
    retry_delay: int = 5
    server_alive_interval: int = 15
    server_alive_count_max: int = 3
    strict_host_key_checking: str = "accept-new"
    batch_mode: bool = True
    tcp_keepalive: bool = True
    log_level: int = logging.INFO


@dataclass
class SSHResult:
    success: bool
    returncode: int
    stdout: str
    stderr: str
    attempts: int
    command: Optional[str] = None


@dataclass
class ManifestSnapshot:
    exists: bool
    signature: Optional[str]
    manifest_by_plate: dict[str, dict]
    merged_by_plate: dict[str, dict]
    order: list[str]


class RobustSSHClient:
    def __init__(self, config: SSHConfig, logger: Optional[logging.Logger] = None) -> None:
        self.config = config
        self.logger = logger or self._build_default_logger()

    def _build_default_logger(self) -> logging.Logger:
        logger = logging.getLogger(f"RobustSSHClient:{self.config.user}@{self.config.host}")
        logger.setLevel(self.config.log_level)

        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "[%(asctime)s] [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        logger.propagate = False
        return logger

    def _build_base_command(self) -> list[str]:
        cmd = [
            "ssh",
            "-p", str(self.config.port),
            "-o", f"ConnectTimeout={self.config.connect_timeout}",
            "-o", f"ServerAliveInterval={self.config.server_alive_interval}",
            "-o", f"ServerAliveCountMax={self.config.server_alive_count_max}",
            "-o", f"StrictHostKeyChecking={self.config.strict_host_key_checking}",
            "-o", f"TCPKeepAlive={'yes' if self.config.tcp_keepalive else 'no'}",
            "-o", f"BatchMode={'yes' if self.config.batch_mode else 'no'}",
            "-o", "LogLevel=ERROR",
        ]

        if self.config.key_path:
            cmd.extend(["-i", self.config.key_path])

        cmd.append(f"{self.config.user}@{self.config.host}")
        return cmd

    def check_tcp_port(self, timeout: int = 3) -> bool:
        """
        Verifica si el puerto TCP del host está accesible.
        No garantiza autenticación SSH, solo conectividad básica.
        """
        self.logger.info(
            "Verificando acceso TCP a %s:%s...",
            self.config.host,
            self.config.port,
        )
        try:
            with socket.create_connection((self.config.host, self.config.port), timeout=timeout):
                self.logger.info("Puerto TCP accesible.")
                return True
        except OSError as exc:
            self.logger.warning("No se pudo acceder al puerto TCP: %s", exc)
            return False

    def run_command(
        self,
        remote_command: str,
        check: bool = False,
        max_retries: Optional[int] = None,
    ) -> SSHResult:
        """
        Ejecuta un comando remoto por SSH con reintentos.
        """
        if not remote_command.strip():
            raise ValueError("El comando remoto no puede estar vacío.")

        base_cmd = self._build_base_command()
        full_cmd = base_cmd + [remote_command]

        return self._run_with_retries(
            full_cmd=full_cmd,
            remote_command=remote_command,
            check=check,
            max_retries=max_retries,
        )

    def read_remote_text_file(
        self,
        remote_path: str,
        check: bool = False,
        max_retries: Optional[int] = None,
    ) -> SSHResult:
        """
        Lee un archivo remoto de forma segura escapando la ruta.
        """
        if not remote_path.strip():
            raise ValueError("La ruta remota no puede estar vacía.")

        return self.run_command(
            f"cat {shlex.quote(remote_path)}",
            check=check,
            max_retries=max_retries,
        )

    def start_stream_command(self, remote_command: str) -> subprocess.Popen[str]:
        """
        Inicia un comando remoto persistente y expone stdout en streaming.
        """
        if not remote_command.strip():
            raise ValueError("El comando remoto no puede estar vacío.")

        full_cmd = self._build_base_command() + [remote_command]

        try:
            return subprocess.Popen(
                full_cmd,
                text=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise SSHConnectionError("No se encontró el binario 'ssh' en el sistema.") from exc

    def stat_remote_file(self, remote_path: str, check: bool = False) -> tuple[bool, Optional[str]]:
        """
        Retorna si el archivo remoto existe y su firma básica.
        La firma combina mtime, tamaño e inode para detectar cambios rápido.
        """
        if not remote_path.strip():
            raise ValueError("La ruta remota no puede estar vacía.")

        quoted_path = shlex.quote(remote_path)
        command = (
            f"if [ -f {quoted_path} ]; then "
            "printf 'EXISTS\n'; "
            f"stat -c '%Y|%s|%i' {quoted_path}; "
            "else "
            "printf 'MISSING\n'; "
            "fi"
        )

        result = self.run_command(command, check=check)
        stdout_lines = result.stdout.splitlines()

        if not stdout_lines:
            return False, None

        status = stdout_lines[0].strip()
        if status != "EXISTS":
            return False, None

        signature = stdout_lines[1].strip() if len(stdout_lines) > 1 else ""
        return True, signature

    def open_interactive_shell(self) -> int:
        """
        Abre una sesión interactiva SSH.
        """
        cmd = self._build_base_command()
        self.logger.info("Abriendo sesión interactiva con %s@%s...", self.config.user, self.config.host)

        try:
            return subprocess.call(cmd)
        except FileNotFoundError as exc:
            raise SSHConnectionError("No se encontró el binario 'ssh' en el sistema.") from exc
        except Exception as exc:
            raise SSHConnectionError(f"Error inesperado al abrir sesión SSH: {exc}") from exc

    def _run_with_retries(
        self,
        full_cmd: list[str],
        remote_command: Optional[str],
        check: bool,
        max_retries: Optional[int] = None,
    ) -> SSHResult:
        last_result: Optional[SSHResult] = None
        attempt_limit = self.config.max_retries if max_retries is None else max(1, max_retries)

        for attempt in range(1, attempt_limit + 1):
            self.logger.info(
                "Intento %s/%s a %s@%s:%s",
                attempt,
                attempt_limit,
                self.config.user,
                self.config.host,
                self.config.port,
            )
            self.logger.info("Comando remoto: %s", remote_command)

            try:
                completed = subprocess.run(
                    full_cmd,
                    text=True,
                    capture_output=True,
                    timeout=self.config.command_timeout,
                    check=False,
                )

                result = SSHResult(
                    success=(completed.returncode == 0),
                    returncode=completed.returncode,
                    stdout=completed.stdout.strip(),
                    stderr=completed.stderr.strip(),
                    attempts=attempt,
                    command=remote_command,
                )

                if completed.returncode == 0:
                    self.logger.info("Comando ejecutado correctamente.")
                    return result

                self.logger.error(
                    "Fallo SSH. returncode=%s stderr=%s",
                    completed.returncode,
                    result.stderr or "(vacío)",
                )
                last_result = result

            except subprocess.TimeoutExpired as exc:
                self.logger.error("Timeout ejecutando SSH tras %s segundos.", self.config.command_timeout)
                last_result = SSHResult(
                    success=False,
                    returncode=124,
                    stdout=(exc.stdout or "").strip() if exc.stdout else "",
                    stderr=(exc.stderr or "").strip() if exc.stderr else "Timeout expirado",
                    attempts=attempt,
                    command=remote_command,
                )

            except FileNotFoundError as exc:
                raise SSHConnectionError("No se encontró el binario 'ssh' en el sistema.") from exc

            except Exception as exc:
                self.logger.exception("Error inesperado durante la ejecución SSH.")
                last_result = SSHResult(
                    success=False,
                    returncode=1,
                    stdout="",
                    stderr=str(exc),
                    attempts=attempt,
                    command=remote_command,
                )

            if attempt < attempt_limit:
                self.logger.info("Reintentando en %s segundos...", self.config.retry_delay)
                time.sleep(self.config.retry_delay)

        if check and last_result is not None:
            raise SSHCommandError(
                f"No se pudo ejecutar el comando remoto tras {last_result.attempts} intentos. "
                f"Último error: {last_result.stderr}"
            )

        if last_result is None:
            raise SSHCommandError("La ejecución SSH falló sin generar resultado.")

        return last_result

    def run_local_to_remote_script(
        self,
        local_script_path: str,
        interpreter: str = "bash",
        check: bool = False,
    ) -> SSHResult:
        """
        Envía un script local al host remoto y lo ejecuta por stdin.
        Ejemplo:
            interpreter='bash'
            interpreter='python3'
        """
        if not local_script_path.strip():
            raise ValueError("local_script_path no puede estar vacío.")

        ssh_cmd = self._build_base_command() + [interpreter]

        self.logger.info(
            "Ejecutando script local '%s' en remoto usando '%s'.",
            local_script_path,
            interpreter,
        )

        try:
            with open(local_script_path, "r", encoding="utf-8") as f:
                script_content = f.read()

            last_result: Optional[SSHResult] = None

            for attempt in range(1, self.config.max_retries + 1):
                self.logger.info("Intento %s/%s para script remoto.", attempt, self.config.max_retries)

                try:
                    completed = subprocess.run(
                        ssh_cmd,
                        input=script_content,
                        text=True,
                        capture_output=True,
                        timeout=self.config.command_timeout,
                        check=False,
                    )

                    result = SSHResult(
                        success=(completed.returncode == 0),
                        returncode=completed.returncode,
                        stdout=completed.stdout.strip(),
                        stderr=completed.stderr.strip(),
                        attempts=attempt,
                        command=f"{interpreter} < {local_script_path}",
                    )

                    if result.success:
                        self.logger.info("Script remoto ejecutado correctamente.")
                        return result

                    self.logger.error(
                        "Script remoto falló. returncode=%s stderr=%s",
                        result.returncode,
                        result.stderr or "(vacío)",
                    )
                    last_result = result

                except subprocess.TimeoutExpired as exc:
                    self.logger.error("Timeout ejecutando script remoto.")
                    last_result = SSHResult(
                        success=False,
                        returncode=124,
                        stdout=(exc.stdout or "").strip() if exc.stdout else "",
                        stderr=(exc.stderr or "").strip() if exc.stderr else "Timeout expirado",
                        attempts=attempt,
                        command=f"{interpreter} < {local_script_path}",
                    )

                if attempt < self.config.max_retries:
                    self.logger.info("Reintentando en %s segundos...", self.config.retry_delay)
                    time.sleep(self.config.retry_delay)

            if check and last_result is not None:
                raise SSHCommandError(
                    f"El script remoto falló tras {last_result.attempts} intentos. "
                    f"Último error: {last_result.stderr}"
                )

            if last_result is None:
                raise SSHCommandError("El script remoto falló sin generar resultado.")

            return last_result

        except FileNotFoundError as exc:
            missing_path = exc.filename or local_script_path
            if str(missing_path) == local_script_path:
                raise SSHError(f"No existe el archivo local: {local_script_path}") from exc
            raise SSHConnectionError("No se encontró el binario 'ssh' en el sistema.") from exc
        except SSHError:
            raise
        except Exception as exc:
            raise SSHError(f"Error ejecutando script remoto: {exc}") from exc


def empty_manifest_snapshot() -> ManifestSnapshot:
    return ManifestSnapshot(
        exists=False,
        signature=None,
        manifest_by_plate={},
        merged_by_plate={},
        order=[],
    )


def normalize_plate_key(raw_plate: object) -> Optional[str]:
    if raw_plate is None:
        return None

    plate = str(raw_plate).strip().upper()
    return plate or None


def parse_latest_manifest_lines(manifest_content: str) -> tuple[dict[str, dict], list[str]]:
    manifest_by_plate: dict[str, dict] = {}

    for raw_line in manifest_content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        plate = normalize_plate_key(item.get("plate"))
        if not plate:
            continue

        normalized_item = dict(item)
        normalized_item["plate"] = plate

        if plate in manifest_by_plate:
            del manifest_by_plate[plate]

        manifest_by_plate[plate] = normalized_item

    return manifest_by_plate, list(manifest_by_plate)


def parse_unique_plate_file_records(manifest_content: str) -> list[dict[str, str]]:
    records_by_plate: dict[str, dict[str, str]] = {}

    for raw_line in manifest_content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        if str(item.get("type") or "").strip().casefold() != "plate":
            continue

        plate = normalize_plate_key(item.get("plate"))
        if not plate:
            continue

        if plate in records_by_plate:
            del records_by_plate[plate]

        records_by_plate[plate] = {
            "plate": plate,
            "file": str(item.get("file") or "").strip(),
        }

    return list(reversed(list(records_by_plate.values())))


def parse_unique_plate_values(manifest_content: str) -> list[str]:
    return [
        record["plate"]
        for record in parse_unique_plate_file_records(manifest_content)
        if record.get("plate")
    ]


def iter_remote_path_candidates(
    remote_path: object,
    *,
    remote_manifest_path: str | None = None,
) -> list[str]:
    normalized_path = str(remote_path or "").strip()
    if not normalized_path:
        return []

    if normalized_path.startswith("/"):
        return [normalized_path]

    candidates: list[str] = []
    manifest_path = str(remote_manifest_path or "").strip()
    relative_path = PurePosixPath(normalized_path)

    if manifest_path:
        manifest_dir = PurePosixPath(manifest_path).parent
        project_dir = manifest_dir.parent
        if relative_path.parts[:1] == ("results",):
            candidates.extend(
                [
                    str(project_dir / relative_path),
                    str(manifest_dir / relative_path),
                ]
            )
        else:
            candidates.extend(
                [
                    str(manifest_dir / relative_path),
                    str(project_dir / relative_path),
                ]
            )

    candidates.append(normalized_path)

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized_candidate = str(candidate or "").strip()
        if not normalized_candidate or normalized_candidate in seen:
            continue
        seen.add(normalized_candidate)
        deduped.append(normalized_candidate)
    return deduped


def fetch_merged_item(
    client: RobustSSHClient,
    manifest_item: dict,
    *,
    remote_manifest_path: str | None = None,
) -> dict:
    detail_file = manifest_item.get("file")
    if not detail_file:
        return manifest_item

    detail_result: SSHResult | None = None
    for candidate_path in iter_remote_path_candidates(
        detail_file,
        remote_manifest_path=remote_manifest_path,
    ):
        detail_result = client.read_remote_text_file(candidate_path, check=False, max_retries=1)
        if detail_result.success:
            break

    if detail_result is None or not detail_result.success:
        return manifest_item

    try:
        detail_item = json.loads(detail_result.stdout)
    except json.JSONDecodeError:
        return manifest_item

    return {
        **manifest_item,
        **detail_item,
    }


def build_manifest_snapshot(
    client: RobustSSHClient,
    remote_manifest_path: str,
    signature: Optional[str],
    previous_snapshot: Optional[ManifestSnapshot] = None,
    fetch_details: bool = False,
    max_retries: int = 1,
) -> ManifestSnapshot:
    manifest_result = client.read_remote_text_file(
        remote_manifest_path,
        check=False,
        max_retries=max_retries,
    )
    if not manifest_result.success:
        if "No such file or directory" in (manifest_result.stderr or ""):
            return empty_manifest_snapshot()

        if previous_snapshot is not None:
            return ManifestSnapshot(
                exists=previous_snapshot.exists,
                signature=previous_snapshot.signature,
                manifest_by_plate=dict(previous_snapshot.manifest_by_plate),
                merged_by_plate=dict(previous_snapshot.merged_by_plate),
                order=list(previous_snapshot.order),
            )

        return empty_manifest_snapshot()

    manifest_by_plate, order = parse_latest_manifest_lines(manifest_result.stdout)

    previous_manifest_by_plate = previous_snapshot.manifest_by_plate if previous_snapshot else {}
    previous_merged_by_plate = previous_snapshot.merged_by_plate if previous_snapshot else {}

    merged_by_plate: dict[str, dict] = {}
    for plate in order:
        manifest_item = manifest_by_plate[plate]
        if previous_manifest_by_plate.get(plate) == manifest_item and plate in previous_merged_by_plate:
            merged_by_plate[plate] = previous_merged_by_plate[plate]
            continue

        if fetch_details:
            merged_by_plate[plate] = fetch_merged_item(
                client,
                manifest_item,
                remote_manifest_path=remote_manifest_path,
            )
        else:
            merged_by_plate[plate] = manifest_item

    return ManifestSnapshot(
        exists=True,
        signature=signature,
        manifest_by_plate=manifest_by_plate,
        merged_by_plate=merged_by_plate,
        order=order,
    )


def print_item_event(event_name: str, item: dict) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(
        f"[{timestamp}] [{event_name}] {json.dumps(item, ensure_ascii=False)}",
        flush=True,
    )


def print_plate_removed(plate: str, previous_item: Optional[dict] = None) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    payload = previous_item or {"plate": plate}
    print(
        f"[{timestamp}] [ELIMINADO] {json.dumps(payload, ensure_ascii=False)}",
        flush=True,
    )


class RemoteManifestWatcher(threading.Thread):
    def __init__(
        self,
        client: RobustSSHClient,
        remote_manifest_path: str,
        resync_interval: float = 2.0,
    ) -> None:
        super().__init__(daemon=True, name="remote-manifest-watcher")
        self.client = client
        self.remote_manifest_path = remote_manifest_path
        self.resync_interval = max(0.5, resync_interval)
        self.stop_event = threading.Event()
        self.current_snapshot: ManifestSnapshot = empty_manifest_snapshot()
        self.tail_process: Optional[subprocess.Popen[str]] = None

    def stop(self) -> None:
        self.stop_event.set()
        self._stop_tail_process()

    def run(self) -> None:
        self.current_snapshot = build_manifest_snapshot(
            client=self.client,
            remote_manifest_path=self.remote_manifest_path,
            signature=None,
            previous_snapshot=None,
            fetch_details=False,
            max_retries=1,
        )
        self._start_tail_process()
        next_resync_at = time.monotonic() + self.resync_interval

        try:
            while not self.stop_event.is_set():
                self._restart_tail_if_needed()

                timeout = max(0.0, min(0.25, next_resync_at - time.monotonic()))
                line = self._read_next_tail_line(timeout)
                if line is not None:
                    self._process_tail_line(line)

                if time.monotonic() >= next_resync_at:
                    self._resync_snapshot()
                    next_resync_at = time.monotonic() + self.resync_interval

        finally:
            self._stop_tail_process()

    def _start_tail_process(self) -> None:
        quoted_path = shlex.quote(self.remote_manifest_path)
        self.tail_process = self.client.start_stream_command(f"tail -n 0 -F {quoted_path}")

    def _stop_tail_process(self) -> None:
        process = self.tail_process
        self.tail_process = None

        if process is None:
            return

        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)

        if process.stdout is not None:
            process.stdout.close()

    def _restart_tail_if_needed(self) -> None:
        if self.stop_event.is_set():
            return

        if self.tail_process is not None and self.tail_process.poll() is None:
            return

        self._stop_tail_process()
        self._start_tail_process()

    def _read_next_tail_line(self, timeout: float) -> Optional[str]:
        process = self.tail_process
        if process is None or process.stdout is None:
            return None

        try:
            ready, _, _ = select.select([process.stdout], [], [], max(0.0, timeout))
        except (OSError, ValueError):
            return None

        if not ready:
            return None

        line = process.stdout.readline()
        if not line:
            return None

        return line.strip()

    def _process_tail_line(self, line: str) -> None:
        if not line:
            return

        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            return

        plate = normalize_plate_key(item.get("plate"))
        if not plate:
            return

        manifest_item = dict(item)
        manifest_item["plate"] = plate

        previous_manifest_item = self.current_snapshot.manifest_by_plate.get(plate)
        previous_merged_item = self.current_snapshot.merged_by_plate.get(plate)
        merged_item = fetch_merged_item(
            self.client,
            manifest_item,
            remote_manifest_path=self.remote_manifest_path,
        )

        if previous_manifest_item is None:
            print_item_event("AGREGADO", merged_item)
        elif previous_manifest_item != manifest_item or previous_merged_item != merged_item:
            print_item_event("ACTUALIZADO", merged_item)
        else:
            return

        self.current_snapshot.exists = True
        self.current_snapshot.manifest_by_plate[plate] = manifest_item
        self.current_snapshot.merged_by_plate[plate] = merged_item
        self._move_plate_to_end(plate)

    def _resync_snapshot(self) -> None:
        previous_snapshot = self.current_snapshot
        next_snapshot = build_manifest_snapshot(
            client=self.client,
            remote_manifest_path=self.remote_manifest_path,
            signature=None,
            previous_snapshot=previous_snapshot if previous_snapshot.exists else None,
            fetch_details=False,
            max_retries=1,
        )

        if not next_snapshot.exists:
            if previous_snapshot.exists:
                for plate in previous_snapshot.order:
                    print_plate_removed(plate, previous_snapshot.merged_by_plate.get(plate))
            self.current_snapshot = next_snapshot
            return

        if not previous_snapshot.exists:
            self.current_snapshot = next_snapshot
            return

        previous_plates = set(previous_snapshot.manifest_by_plate)
        current_plates = set(next_snapshot.manifest_by_plate)

        removed_plates = [plate for plate in previous_snapshot.order if plate not in current_plates]
        for plate in removed_plates:
            print_plate_removed(plate, previous_snapshot.merged_by_plate.get(plate))

        for plate in next_snapshot.order:
            manifest_item = next_snapshot.manifest_by_plate[plate]

            if plate not in previous_plates:
                merged_item = fetch_merged_item(
                    self.client,
                    manifest_item,
                    remote_manifest_path=self.remote_manifest_path,
                )
                next_snapshot.merged_by_plate[plate] = merged_item
                print_item_event("AGREGADO", merged_item)
                continue

            if previous_snapshot.manifest_by_plate.get(plate) != manifest_item:
                merged_item = fetch_merged_item(
                    self.client,
                    manifest_item,
                    remote_manifest_path=self.remote_manifest_path,
                )
                next_snapshot.merged_by_plate[plate] = merged_item

                if previous_snapshot.merged_by_plate.get(plate) != merged_item:
                    print_item_event("ACTUALIZADO", merged_item)

        self.current_snapshot = next_snapshot

    def _move_plate_to_end(self, plate: str) -> None:
        if plate in self.current_snapshot.order:
            self.current_snapshot.order.remove(plate)
        self.current_snapshot.order.append(plate)


if __name__ == "__main__":
    REMOTE_MANIFEST_PATH = get_default_crops_remote_manifest_path()
    MANIFEST_RESYNC_INTERVAL_SECONDS = 1.0

    config = build_default_crops_ssh_config(
        connect_timeout=10,
        command_timeout=30,
        max_retries=3,
        retry_delay=4,
        log_level=logging.WARNING,
    )

    client = RobustSSHClient(config)

    client.check_tcp_port()
    watcher = RemoteManifestWatcher(
        client=client,
        remote_manifest_path=REMOTE_MANIFEST_PATH,
        resync_interval=MANIFEST_RESYNC_INTERVAL_SECONDS,
    )
    watcher.start()

    print(
        f"Esperando cambios nuevos en: {REMOTE_MANIFEST_PATH}",
        flush=True,
    )

    try:
        while watcher.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDeteniendo monitoreo remoto...", flush=True)
        watcher.stop()
        watcher.join(timeout=5)
