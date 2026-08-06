from __future__ import annotations

import json
import math
import os
import shutil
import socket
import subprocess
import time
import urllib.request
import webbrowser
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path


REQUIRED_SERVICES = ("backend", "frontend", "worker", "redis")
BACKEND_URL = "http://localhost:8000/health"
FRONTEND_URL = "http://localhost:3000/upload"
DOCKER_BIN_DIR = Path(r"C:\Program Files\Docker\Docker\resources\bin")
DOCKER_DESKTOP_EXE = Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe")
MIN_FREE_DISK_GB = 20.0
RUNTIME_PROFILES = {"recommended", "gpu", "cpu"}
GPU_PREFLIGHT_SCHEMA_VERSION = 1
GPU_RUNTIME_LIBRARIES = ["libcublas.so.12", "libcudnn.so.9"]


@dataclass(frozen=True)
class HostGpu:
    name: str | None = None
    driver: str | None = None
    memory_total_mib: int | None = None

    @property
    def available(self) -> bool:
        return bool(self.name)


@dataclass(frozen=True)
class RuntimeProfile:
    key: str
    label: str
    whisper_model: str
    language: str
    device: str
    compute_type: str

    @property
    def transcription_label(self) -> str:
        return (
            f"{self.whisper_model} / {self.language} / "
            f"{self.device} / {self.compute_type}"
        )


CPU_PROFILE = RuntimeProfile("cpu", "CPU compatible", "base", "ja", "cpu", "auto")
GPU_PROFILE = RuntimeProfile("gpu", "GPU recommended", "turbo", "ja", "cuda", "float16")


@dataclass(frozen=True)
class GpuSupport:
    host: HostGpu
    docker_runtime_available: bool
    compose_override_exists: bool

    @property
    def available(self) -> bool:
        return (
            self.host.available
            and self.docker_runtime_available
            and self.compose_override_exists
        )

    @property
    def unavailable_reason(self) -> str | None:
        if not self.host.available:
            return "NVIDIA GPUを検出できません"
        if not self.docker_runtime_available:
            return "Docker NVIDIA runtimeを利用できません"
        if not self.compose_override_exists:
            return "docker-compose.gpu.ymlが見つかりません"
        return None


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def output(self) -> str:
        return "\n".join(
            part for part in (self.stdout.strip(), self.stderr.strip()) if part
        )


@dataclass(frozen=True)
class ServiceState:
    name: str
    state: str = "not_created"
    health: str | None = None
    status: str | None = None

    @property
    def running(self) -> bool:
        return self.state.lower() == "running"


@dataclass(frozen=True)
class RuntimeStatus:
    services: dict[str, ServiceState] = field(default_factory=dict)
    backend_ready: bool = False
    frontend_ready: bool = False
    worker_profile: str | None = None

    @property
    def all_services_running(self) -> bool:
        return all(
            self.services.get(name, ServiceState(name)).running
            for name in REQUIRED_SERVICES
        )

    @property
    def ready(self) -> bool:
        return self.all_services_running and self.backend_ready and self.frontend_ready


@dataclass(frozen=True)
class PreflightReport:
    docker_available: bool
    daemon_ready: bool
    compose_available: bool
    compose_file_exists: bool
    env_exists: bool
    openai_key_configured: bool
    disk_free_gb: float
    runtime_status: RuntimeStatus
    gpu_support: GpuSupport
    recommended_profile: RuntimeProfile
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def already_running(self) -> bool:
        return self.runtime_status.ready


@dataclass(frozen=True)
class StartResult:
    already_running: bool
    status: RuntimeStatus
    requested_profile: str
    runtime_profile: RuntimeProfile
    gpu_name: str | None
    gpu_override_enabled: bool
    fallback_used: bool = False
    fallback_reason: str | None = None
    docker_desktop_started: bool = False


class LauncherError(RuntimeError):
    def __init__(self, code: str, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail


CommandRunner = Callable[[Sequence[str], Path, float | None], CommandResult]
UrlChecker = Callable[[str, str | None, float], bool]
PortChecker = Callable[[int], bool]
PathOpener = Callable[[Path], None]
GpuChecker = Callable[[], HostGpu]
DockerDesktopFinder = Callable[[], Path | None]
DesktopApplicationStarter = Callable[[Path], None]
MonotonicClock = Callable[[], float]


def find_docker_executable() -> str | None:
    docker = shutil.which("docker")
    if docker:
        return docker
    candidates = [DOCKER_BIN_DIR / "docker.exe"]
    program_files = os.environ.get("ProgramFiles")
    if program_files:
        candidates.insert(
            0,
            Path(program_files)
            / "Docker"
            / "Docker"
            / "resources"
            / "bin"
            / "docker.exe",
        )
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        local_root = Path(local_app_data)
        candidates.extend(
            [
                local_root / "Docker" / "resources" / "bin" / "docker.exe",
                local_root
                / "Programs"
                / "DockerDesktop"
                / "resources"
                / "bin"
                / "docker.exe",
            ]
        )
    for candidate in dict.fromkeys(candidates):
        if candidate.is_file():
            return str(candidate)
    return None


def find_docker_desktop_executable() -> Path | None:
    candidates = [DOCKER_DESKTOP_EXE]
    program_files = os.environ.get("ProgramFiles")
    if program_files:
        candidates.insert(
            0, Path(program_files) / "Docker" / "Docker" / "Docker Desktop.exe"
        )
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        local_root = Path(local_app_data)
        candidates.extend(
            [
                local_root / "Docker" / "Docker Desktop.exe",
                local_root
                / "Programs"
                / "DockerDesktop"
                / "Docker Desktop.exe",
            ]
        )
    for candidate in dict.fromkeys(candidates):
        if candidate.is_file():
            return candidate
    return None


def start_desktop_application(executable: Path) -> None:
    subprocess.Popen(
        [str(executable)],
        cwd=executable.parent,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        close_fds=True,
    )


def query_host_nvidia_gpu() -> HostGpu:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return HostGpu()
    first_line = completed.stdout.strip().splitlines()[0] if completed.stdout.strip() else ""
    values = [value.strip() for value in first_line.split(",")]
    if len(values) != 3:
        return HostGpu()
    try:
        memory_total_mib = int(float(values[2]))
    except ValueError:
        memory_total_mib = None
    return HostGpu(values[0] or None, values[1] or None, memory_total_mib)


def run_command(
    command: Sequence[str], cwd: Path, timeout: float | None = None
) -> CommandResult:
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(124, exc.stdout or "", exc.stderr or "command timed out")
    except OSError as exc:
        return CommandResult(127, "", str(exc))
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def check_url(url: str, expected_text: str | None = None, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            if response.status != 200:
                return False
            if expected_text is None:
                return True
            body = response.read().decode("utf-8", errors="replace")
            return expected_text in body
    except (OSError, ValueError):
        return False


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def open_local_path(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
        return
    subprocess.Popen(["xdg-open", str(path)])


def _parse_env_value(env_path: Path, key: str) -> str | None:
    if not env_path.is_file():
        return None
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if separator and name.strip() == key:
            return value.strip().strip('"').strip("'")
    return None


def parse_compose_ps(output: str) -> dict[str, ServiceState]:
    text = output.strip()
    if not text:
        return {}
    try:
        decoded = json.loads(text)
        rows = decoded if isinstance(decoded, list) else [decoded]
    except json.JSONDecodeError:
        rows = []
        for line in text.splitlines():
            try:
                decoded = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.extend(decoded if isinstance(decoded, list) else [decoded])

    states: dict[str, ServiceState] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        service = str(row.get("Service") or row.get("service") or "").strip()
        if not service:
            continue
        states[service] = ServiceState(
            name=service,
            state=str(row.get("State") or row.get("state") or "unknown"),
            health=str(row.get("Health") or row.get("health") or "").strip() or None,
            status=str(row.get("Status") or row.get("status") or "").strip() or None,
        )
    return states


class LauncherController:
    def __init__(
        self,
        project_root: str | Path,
        *,
        command_runner: CommandRunner = run_command,
        url_checker: UrlChecker = check_url,
        port_checker: PortChecker = port_in_use,
        path_opener: PathOpener = open_local_path,
        browser_opener: Callable[[str], bool] = webbrowser.open,
        docker_finder: Callable[[], str | None] = find_docker_executable,
        docker_desktop_finder: DockerDesktopFinder = find_docker_desktop_executable,
        desktop_application_starter: DesktopApplicationStarter = start_desktop_application,
        gpu_checker: GpuChecker = query_host_nvidia_gpu,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic_clock: MonotonicClock = time.monotonic,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.command_runner = command_runner
        self.url_checker = url_checker
        self.port_checker = port_checker
        self.path_opener = path_opener
        self.browser_opener = browser_opener
        self.docker_finder = docker_finder
        self.docker_desktop_finder = docker_desktop_finder
        self.desktop_application_starter = desktop_application_starter
        self.gpu_checker = gpu_checker
        self.sleeper = sleeper
        self.monotonic_clock = monotonic_clock
        self.compose_file = self.project_root / "docker-compose.yml"
        self.gpu_compose_file = self.project_root / "docker-compose.gpu.yml"
        self.env_file = self.project_root / ".env"
        self._docker_executable: str | None = None

    @property
    def docker_executable(self) -> str | None:
        if self._docker_executable is None:
            self._docker_executable = self.docker_finder()
        return self._docker_executable

    def _configured_openai_keys(self) -> tuple[str, ...]:
        values = (
            _parse_env_value(self.env_file, "OPENAI_API_KEY"),
            os.environ.get("OPENAI_API_KEY"),
        )
        return tuple(dict.fromkeys(value for value in values if value))

    def _sensitive_values(self) -> tuple[str, ...]:
        return self._configured_openai_keys()

    def redact(self, text: str | bytes | None) -> str:
        if text is None:
            redacted = ""
        elif isinstance(text, bytes):
            redacted = text.decode("utf-8", errors="replace")
        else:
            redacted = str(text)
        for value in self._sensitive_values():
            redacted = redacted.replace(value, "[REDACTED]")
        return redacted

    def _run(
        self, command: Sequence[str], timeout: float | None = 60.0
    ) -> CommandResult:
        result = self.command_runner(command, self.project_root, timeout)
        return CommandResult(
            result.returncode, self.redact(result.stdout), self.redact(result.stderr)
        )

    def _docker(
        self, args: Sequence[str], timeout: float | None = 60.0
    ) -> CommandResult:
        executable = self.docker_executable
        if not executable:
            return CommandResult(127, "", "docker executable not found")
        return self._run([executable, *args], timeout=timeout)

    def ensure_docker_daemon_ready(
        self, *, timeout: float = 180.0, poll_interval: float = 2.0
    ) -> bool:
        if not self.docker_executable:
            raise LauncherError(
                "docker_cli_missing",
                "Docker CLIが見つかりません。Docker Desktopをインストールしてください。",
            )

        timeout_budget = max(0.0, timeout)
        deadline = self.monotonic_clock() + timeout_budget

        def remaining_timeout(limit: float) -> float:
            return min(limit, max(0.0, deadline - self.monotonic_clock()))

        initial_timeout = remaining_timeout(20.0)
        if initial_timeout <= 0:
            raise LauncherError(
                "docker_daemon_start_timeout",
                "Docker daemonがtimeout内に準備完了しませんでした。",
            )
        initial = self._docker(["info"], timeout=initial_timeout)
        if initial.returncode == 0:
            return False

        desktop_cli_timeout = remaining_timeout(15.0)
        if desktop_cli_timeout <= 0:
            raise LauncherError(
                "docker_daemon_start_timeout",
                "Docker daemonがtimeout内に準備完了しませんでした。",
                initial.output,
            )
        desktop_cli = self._docker(
            ["desktop", "version"], timeout=desktop_cli_timeout
        )
        start_result = CommandResult(1, "", "Docker Desktop CLI is unavailable")
        if desktop_cli.returncode == 0:
            start_timeout = remaining_timeout(45.0)
            if start_timeout <= 0:
                raise LauncherError(
                    "docker_daemon_start_timeout",
                    "Docker daemonがtimeout内に準備完了しませんでした。",
                    initial.output,
                )
            start_result = self._docker(
                ["desktop", "start", "--detach", "--timeout", "30"],
                timeout=start_timeout,
            )

        if desktop_cli.returncode != 0:
            desktop_executable = self.docker_desktop_finder()
            if desktop_executable is None:
                raise LauncherError(
                    "docker_desktop_not_found",
                    "Docker Desktopを自動起動できませんでした。",
                    desktop_cli.output,
                )
            try:
                self.desktop_application_starter(desktop_executable)
            except OSError as exc:
                raise LauncherError(
                    "docker_desktop_start_failed",
                    "Docker Desktopを自動起動できませんでした。",
                    self.redact(str(exc)),
                ) from exc

        safe_poll_interval = max(0.1, poll_interval)
        attempts = max(1, math.ceil(timeout_budget / safe_poll_interval) + 1)
        last_result = initial
        for attempt in range(attempts):
            info_timeout = remaining_timeout(10.0)
            if info_timeout <= 0:
                break
            last_result = self._docker(["info"], timeout=info_timeout)
            if last_result.returncode == 0:
                return True
            if attempt >= attempts - 1 or self.monotonic_clock() >= deadline:
                break
            self.sleeper(
                min(
                    safe_poll_interval,
                    max(0.0, deadline - self.monotonic_clock()),
                )
            )

        detail = last_result.output
        if start_result.returncode != 0 and start_result.output:
            detail = "\n".join(part for part in (start_result.output, detail) if part)
        raise LauncherError(
            "docker_daemon_start_timeout",
            "Docker daemonがtimeout内に準備完了しませんでした。",
            detail
            or "Docker Desktop画面で利用規約、WSL更新、再起動要求を確認してください。",
        )

    def _compose(
        self, args: Sequence[str], timeout: float | None = 60.0
    ) -> CommandResult:
        return self._docker(["compose", *args], timeout=timeout)

    def _compose_for_profile(
        self,
        profile: RuntimeProfile,
        args: Sequence[str],
        timeout: float | None = 60.0,
    ) -> CommandResult:
        if profile.key == "gpu":
            return self._docker(
                [
                    "compose",
                    "-f",
                    str(self.compose_file),
                    "-f",
                    str(self.gpu_compose_file),
                    *args,
                ],
                timeout=timeout,
            )
        return self._compose(args, timeout=timeout)

    def _current_worker_profile(self) -> str | None:
        result = self._compose(
            [
                "exec",
                "-T",
                "worker",
                "python",
                "-c",
                "import os; print(os.getenv('AUTOCLIPPER_RUNTIME_PROFILE', ''))",
            ],
            timeout=15.0,
        )
        value = result.stdout.strip().splitlines()[-1].strip().lower() if result.stdout.strip() else ""
        return value if result.returncode == 0 and value in {"cpu", "gpu"} else None

    def _docker_nvidia_runtime_available(self) -> bool:
        result = self._docker(
            ["info", "--format", "{{json .Runtimes}}"], timeout=20.0
        )
        if result.returncode != 0:
            return False
        try:
            runtimes = json.loads(result.stdout)
        except json.JSONDecodeError:
            return False
        return isinstance(runtimes, dict) and "nvidia" in runtimes

    def _gpu_support(self, *, daemon_ready: bool) -> GpuSupport:
        return GpuSupport(
            host=self.gpu_checker(),
            docker_runtime_available=(
                self._docker_nvidia_runtime_available() if daemon_ready else False
            ),
            compose_override_exists=self.gpu_compose_file.is_file(),
        )

    def runtime_status(self) -> RuntimeStatus:
        services: dict[str, ServiceState] = {}
        if self.docker_executable and self.compose_file.is_file():
            result = self._compose(["ps", "--format", "json"], timeout=15.0)
            if result.returncode == 0:
                services = parse_compose_ps(result.stdout)
        worker_state = services.get("worker")
        worker_profile = (
            self._current_worker_profile()
            if worker_state is not None and worker_state.running
            else None
        )
        return RuntimeStatus(
            services=services,
            backend_ready=self.url_checker(BACKEND_URL, '"status":"ok"', 2.0),
            frontend_ready=self.url_checker(FRONTEND_URL, "AutoClipper", 2.0),
            worker_profile=worker_profile,
        )

    def preflight(self) -> PreflightReport:
        errors: list[str] = []
        warnings: list[str] = []
        docker_available = bool(self.docker_executable)
        compose_available = False
        daemon_ready = False

        if not docker_available:
            errors.append(
                "Docker CLIが見つかりません。Docker Desktopをインストールしてください。"
            )
        else:
            compose_result = self._docker(["compose", "version"], timeout=15.0)
            compose_available = compose_result.returncode == 0
            if not compose_available:
                errors.append(
                    "docker composeを利用できません。Docker Desktopを更新してください。"
                )
            daemon_result = self._docker(["info"], timeout=20.0)
            daemon_ready = daemon_result.returncode == 0
            if not daemon_ready:
                errors.append(
                    "Docker daemonへ接続できません。Docker Desktopを起動してください。"
                )

        compose_file_exists = self.compose_file.is_file()
        if not compose_file_exists:
            errors.append(f"compose fileが見つかりません: {self.compose_file}")

        env_exists = self.env_file.is_file()
        if not env_exists:
            warnings.append(
                ".envがありません。low_costは利用できますが、環境設定を確認してください。"
            )
        openai_key_configured = bool(self._configured_openai_keys())
        if not openai_key_configured:
            warnings.append(
                "OPENAI_API_KEY未設定: high_qualityはrule score fallbackまたは設定エラーになります。"
            )

        disk_free_gb = shutil.disk_usage(self.project_root).free / (1024**3)
        if disk_free_gb < MIN_FREE_DISK_GB:
            warnings.append(f"ディスク空き容量が少ないです: {disk_free_gb:.1f} GB")

        gpu_support = self._gpu_support(daemon_ready=daemon_ready)
        recommended_profile = GPU_PROFILE if gpu_support.available else CPU_PROFILE
        status = (
            self.runtime_status()
            if daemon_ready and compose_available and compose_file_exists
            else RuntimeStatus()
        )
        backend_state = status.services.get("backend")
        frontend_state = status.services.get("frontend")
        if (
            self.port_checker(8000)
            and not status.backend_ready
            and not (backend_state and backend_state.running)
        ):
            errors.append("port 8000がAutoClipper以外のprocessに使用されています。")
        elif backend_state and backend_state.running and not status.backend_ready:
            warnings.append("backend serviceは起動中ですが、healthはまだreadyではありません。")
        if (
            self.port_checker(3000)
            and not status.frontend_ready
            and not (frontend_state and frontend_state.running)
        ):
            errors.append("port 3000がAutoClipper以外のprocessに使用されています。")
        elif frontend_state and frontend_state.running and not status.frontend_ready:
            warnings.append("frontend serviceは起動中ですが、画面はまだreadyではありません。")
        redis_state = status.services.get("redis")
        if self.port_checker(6379) and not (redis_state and redis_state.running):
            errors.append("port 6379がAutoClipper以外のprocessに使用されています。")

        return PreflightReport(
            docker_available=docker_available,
            daemon_ready=daemon_ready,
            compose_available=compose_available,
            compose_file_exists=compose_file_exists,
            env_exists=env_exists,
            openai_key_configured=openai_key_configured,
            disk_free_gb=disk_free_gb,
            runtime_status=status,
            gpu_support=gpu_support,
            recommended_profile=recommended_profile,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _select_profile(
        requested_profile: str, report: PreflightReport
    ) -> tuple[RuntimeProfile, str | None]:
        normalized = str(requested_profile).strip().lower()
        if normalized not in RUNTIME_PROFILES:
            raise LauncherError(
                "runtime_profile_invalid",
                f"未対応のruntime profileです: {requested_profile}",
            )
        if normalized == "cpu":
            return CPU_PROFILE, None
        if normalized == "gpu":
            if not report.gpu_support.available:
                raise LauncherError(
                    "gpu_preflight_failed",
                    "GPU必須profileの起動前確認に失敗しました。",
                    report.gpu_support.unavailable_reason,
                )
            return GPU_PROFILE, None
        if report.gpu_support.available:
            return GPU_PROFILE, None
        return CPU_PROFILE, report.gpu_support.unavailable_reason

    def _verify_gpu_worker(
        self, *, attempts: int = 5, retry_interval: float = 2.0
    ) -> dict[str, object]:
        result = CommandResult(1, "", "GPU worker is not ready")
        for attempt in range(attempts):
            result = self._compose_for_profile(
                GPU_PROFILE,
                [
                    "exec",
                    "-T",
                    "worker",
                    "python",
                    "-m",
                    "app.audio.gpu_preflight",
                    "--device",
                    "cuda",
                    "--compute-type",
                    "float16",
                ],
                timeout=30.0,
            )
            if result.returncode == 0:
                break
            if attempt + 1 < attempts:
                self.sleeper(retry_interval)
        if result.returncode != 0:
            raise LauncherError(
                "gpu_worker_preflight_failed",
                "GPU workerのCUDA確認に失敗しました。",
                result.output,
            )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise LauncherError(
                "gpu_worker_preflight_invalid",
                "GPU workerの確認結果を解析できません。",
                result.output,
            ) from exc
        if not isinstance(payload, dict):
            raise LauncherError(
                "gpu_worker_preflight_invalid",
                "GPU workerの確認結果がJSON objectではありません。",
                result.output,
            )
        if not (
            payload.get("ok") is True
            and payload.get("preflight_schema_version") == GPU_PREFLIGHT_SCHEMA_VERSION
            and payload.get("cuda_runtime_libraries") == GPU_RUNTIME_LIBRARIES
            and payload.get("actual_device") == "cuda"
            and payload.get("actual_compute_type") == "float16"
            and payload.get("fallback_used") is False
        ):
            raise LauncherError(
                "gpu_worker_preflight_failed",
                "GPU workerが推奨profileで起動していません。",
                json.dumps(payload, ensure_ascii=False),
            )
        return payload

    def wait_until_ready(
        self, timeout: float = 180.0, poll_interval: float = 2.0
    ) -> RuntimeStatus:
        attempts = max(1, math.ceil(timeout / poll_interval))
        last_status = RuntimeStatus()
        for attempt in range(attempts):
            last_status = self.runtime_status()
            if last_status.ready:
                return last_status
            if attempt < attempts - 1:
                self.sleeper(poll_interval)
        raise LauncherError(
            "health_timeout",
            "AutoClipperの起動待機がtimeoutしました。",
            self.describe_status(last_status),
        )

    def start(
        self,
        *,
        profile: str = "recommended",
        rebuild: bool = False,
        timeout: float = 180.0,
        open_browser: bool = True,
    ) -> StartResult:
        docker_desktop_started = self.ensure_docker_daemon_ready(timeout=timeout)
        report = self.preflight()
        if not report.ok:
            raise LauncherError(
                "preflight_failed",
                "起動前確認に失敗しました。",
                "\n".join(report.errors),
            )
        requested_profile = str(profile).strip().lower()
        selected_profile, fallback_reason = self._select_profile(
            requested_profile, report
        )
        compatible_running_profile = report.runtime_status.worker_profile
        already_compatible = report.already_running and (
            compatible_running_profile == selected_profile.key
            or (
                selected_profile.key == "cpu"
                and compatible_running_profile is None
            )
        )
        gpu_runtime_repair_needed = False
        if already_compatible and selected_profile.key == "gpu":
            try:
                self._verify_gpu_worker()
            except LauncherError:
                already_compatible = False
                gpu_runtime_repair_needed = True
        if already_compatible and not rebuild:
            if open_browser:
                self.open_app(selected_profile.key)
            return StartResult(
                already_running=True,
                status=report.runtime_status,
                requested_profile=requested_profile,
                runtime_profile=selected_profile,
                gpu_name=report.gpu_support.host.name,
                gpu_override_enabled=selected_profile.key == "gpu",
                fallback_used=fallback_reason is not None,
                fallback_reason=fallback_reason,
                docker_desktop_started=docker_desktop_started,
            )

        profile_changed = (
            compatible_running_profile in {"cpu", "gpu"}
            and compatible_running_profile != selected_profile.key
        )
        rebuild_worker_for_profile = (
            profile_changed
            or gpu_runtime_repair_needed
            or selected_profile.key == "gpu"
        )
        worker_running = report.runtime_status.services.get(
            "worker", ServiceState("worker")
        ).running
        if worker_running and rebuild_worker_for_profile:
            running_profile = (
                GPU_PROFILE if compatible_running_profile == "gpu" else CPU_PROFILE
            )
            stop_result = self._compose_for_profile(
                running_profile, ["stop", "worker"], timeout=120.0
            )
            if stop_result.returncode != 0:
                raise LauncherError(
                    "worker_stop_failed",
                    "workerを安全に停止できませんでした。",
                    stop_result.output,
                )
        args = ["up", "-d"]
        if rebuild or rebuild_worker_for_profile:
            args.append("--build")
        if (
            report.runtime_status.all_services_running
            and rebuild_worker_for_profile
        ):
            args.extend(["--force-recreate", "worker"])
        result = self._compose_for_profile(
            selected_profile,
            args,
            timeout=None if rebuild or rebuild_worker_for_profile else 180.0,
        )
        if result.returncode != 0:
            raise LauncherError(
                "compose_start_failed",
                "Docker servicesの起動に失敗しました。",
                result.output,
            )

        if selected_profile.key == "gpu":
            try:
                self._verify_gpu_worker()
            except LauncherError as exc:
                if requested_profile == "gpu":
                    self._compose_for_profile(
                        GPU_PROFILE, ["stop", "worker"], timeout=120.0
                    )
                    raise
                fallback_reason = f"{exc.code}: {exc.message}"
                fallback = self._compose_for_profile(
                    CPU_PROFILE,
                    ["up", "-d", "--force-recreate", "worker"],
                    timeout=180.0,
                )
                if fallback.returncode != 0:
                    raise LauncherError(
                        "cpu_fallback_start_failed",
                        "GPU確認失敗後のCPU worker起動に失敗しました。",
                        fallback.output,
                    ) from exc
                selected_profile = CPU_PROFILE
        status = self.wait_until_ready(timeout=timeout)
        if open_browser:
            self.open_app(selected_profile.key)
        return StartResult(
            already_running=False,
            status=status,
            requested_profile=requested_profile,
            runtime_profile=selected_profile,
            gpu_name=report.gpu_support.host.name,
            gpu_override_enabled=selected_profile.key == "gpu",
            fallback_used=fallback_reason is not None,
            fallback_reason=fallback_reason,
            docker_desktop_started=docker_desktop_started,
        )

    def stop(self) -> CommandResult:
        result = self._compose(["stop"], timeout=120.0)
        if result.returncode != 0:
            raise LauncherError(
                "compose_stop_failed",
                "Docker servicesの停止に失敗しました。",
                result.output,
            )
        return result

    def recent_logs(self, tail: int = 200) -> str:
        tail = min(max(int(tail), 10), 2000)
        result = self._compose(
            ["logs", "--tail", str(tail), "--no-color"], timeout=30.0
        )
        if result.returncode != 0:
            raise LauncherError(
                "compose_logs_failed", "Docker logsを取得できません。", result.output
            )
        return result.output

    def open_app(self, runtime_profile: str | None = None) -> None:
        profile = runtime_profile or self.runtime_status().worker_profile
        url = FRONTEND_URL
        if profile in {"cpu", "gpu"}:
            url = f"{FRONTEND_URL}?runtimeProfile={profile}"
        self.browser_opener(url)

    def open_outputs(self) -> None:
        self.path_opener(self.project_root / "storage" / "outputs")

    def open_uploads(self) -> None:
        self.path_opener(self.project_root / "storage" / "uploads")

    @staticmethod
    def describe_status(status: RuntimeStatus) -> str:
        parts = []
        for service in REQUIRED_SERVICES:
            current = status.services.get(service, ServiceState(service))
            value = current.state
            if current.health:
                value += f"/{current.health}"
            parts.append(f"{service}={value}")
        parts.append(f"backend={'ready' if status.backend_ready else 'not_ready'}")
        parts.append(f"frontend={'ready' if status.frontend_ready else 'not_ready'}")
        parts.append(f"worker_profile={status.worker_profile or 'unknown'}")
        return ", ".join(parts)
