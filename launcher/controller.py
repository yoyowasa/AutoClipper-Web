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
MIN_FREE_DISK_GB = 20.0


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


def find_docker_executable() -> str | None:
    docker = shutil.which("docker")
    if docker:
        return docker
    candidate = DOCKER_BIN_DIR / "docker.exe"
    return str(candidate) if candidate.is_file() else None


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
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.command_runner = command_runner
        self.url_checker = url_checker
        self.port_checker = port_checker
        self.path_opener = path_opener
        self.browser_opener = browser_opener
        self.docker_finder = docker_finder
        self.sleeper = sleeper
        self.compose_file = self.project_root / "docker-compose.yml"
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

    def redact(self, text: str) -> str:
        redacted = text
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

    def _compose(
        self, args: Sequence[str], timeout: float | None = 60.0
    ) -> CommandResult:
        return self._docker(["compose", *args], timeout=timeout)

    def runtime_status(self) -> RuntimeStatus:
        services: dict[str, ServiceState] = {}
        if self.docker_executable and self.compose_file.is_file():
            result = self._compose(["ps", "--format", "json"], timeout=15.0)
            if result.returncode == 0:
                services = parse_compose_ps(result.stdout)
        return RuntimeStatus(
            services=services,
            backend_ready=self.url_checker(BACKEND_URL, '"status":"ok"', 2.0),
            frontend_ready=self.url_checker(FRONTEND_URL, "AutoClipper", 2.0),
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
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

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
        rebuild: bool = False,
        timeout: float = 180.0,
        open_browser: bool = True,
    ) -> StartResult:
        report = self.preflight()
        if not report.ok:
            raise LauncherError(
                "preflight_failed",
                "起動前確認に失敗しました。",
                "\n".join(report.errors),
            )
        if report.already_running:
            if open_browser:
                self.open_app()
            return StartResult(already_running=True, status=report.runtime_status)

        args = ["up", "-d"]
        if rebuild:
            args.append("--build")
        result = self._compose(args, timeout=None if rebuild else 180.0)
        if result.returncode != 0:
            raise LauncherError(
                "compose_start_failed",
                "Docker servicesの起動に失敗しました。",
                result.output,
            )

        status = self.wait_until_ready(timeout=timeout)
        if open_browser:
            self.open_app()
        return StartResult(already_running=False, status=status)

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

    def open_app(self) -> None:
        self.browser_opener(FRONTEND_URL)

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
        return ", ".join(parts)
