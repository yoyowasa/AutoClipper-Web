from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import launcher.controller as launcher_controller  # noqa: E402
from launcher.app import LauncherApp  # noqa: E402
from launcher.controller import (  # noqa: E402
    CommandResult,
    HostGpu,
    LauncherController,
    LauncherError,
    find_docker_executable,
    parse_compose_ps,
)


def test_runtime_profiles_use_japanese_transcription() -> None:
    assert launcher_controller.CPU_PROFILE.language == "ja"
    assert launcher_controller.GPU_PROFILE.language == "ja"


def compose_ps(*, running: bool = True) -> str:
    state = "running" if running else "exited"
    rows = (
        {"Service": name, "State": state, "Health": "healthy" if name == "backend" else ""}
        for name in ("backend", "frontend", "worker", "redis")
    )
    return "\n".join(json.dumps(row) for row in rows)


class FakeRunner:
    def __init__(
        self,
        *,
        daemon_ok: bool = True,
        compose_ok: bool = True,
        ps_output: str | None = None,
        up_ok: bool = True,
        docker_gpu: bool = False,
        worker_profile: str = "cpu",
        gpu_preflight_ok: bool = True,
        gpu_preflight_ok_after_build: bool | None = None,
        legacy_gpu_preflight: bool = False,
        non_object_gpu_preflight: bool = False,
        desktop_cli_ok: bool = True,
        desktop_start_ok: bool = True,
        daemon_ready_after_desktop_start: bool = True,
        desktop_start_null_output: bool = False,
    ) -> None:
        self.daemon_ok = daemon_ok
        self.compose_ok = compose_ok
        self.ps_output = ps_output if ps_output is not None else compose_ps(running=False)
        self.up_ok = up_ok
        self.docker_gpu = docker_gpu
        self.worker_profile = worker_profile
        self.gpu_preflight_ok = gpu_preflight_ok
        self.gpu_preflight_ok_after_build = gpu_preflight_ok_after_build
        self.legacy_gpu_preflight = legacy_gpu_preflight
        self.non_object_gpu_preflight = non_object_gpu_preflight
        self.desktop_cli_ok = desktop_cli_ok
        self.desktop_start_ok = desktop_start_ok
        self.daemon_ready_after_desktop_start = daemon_ready_after_desktop_start
        self.desktop_start_null_output = desktop_start_null_output
        self.calls: list[tuple[list[str], Path, float | None]] = []

    def __call__(self, command: list[str], cwd: Path, timeout: float | None) -> CommandResult:
        command = list(command)
        self.calls.append((command, cwd, timeout))
        if command[-2:] == ["compose", "version"]:
            return CommandResult(0 if self.compose_ok else 1, "Docker Compose", "")
        if command[-2:] == ["desktop", "version"]:
            return CommandResult(
                0 if self.desktop_cli_ok else 1,
                "Docker Desktop CLI" if self.desktop_cli_ok else "",
                "desktop command unavailable" if not self.desktop_cli_ok else "",
            )
        if command[1:3] == ["desktop", "start"]:
            if self.daemon_ready_after_desktop_start:
                self.daemon_ok = True
            if self.desktop_start_null_output:
                return CommandResult(0, None, None)  # type: ignore[arg-type]
            return CommandResult(
                0 if self.desktop_start_ok else 1,
                "Docker Desktop starting" if self.desktop_start_ok else "",
                "desktop start failed" if not self.desktop_start_ok else "",
            )
        if command[-3:-1] == ["info", "--format"]:
            runtimes = {"runc": {}}
            if self.docker_gpu:
                runtimes["nvidia"] = {}
            return CommandResult(0, json.dumps(runtimes), "")
        if command[-1:] == ["info"]:
            return CommandResult(0 if self.daemon_ok else 1, "Docker info", "daemon unavailable")
        if command[-3:] == ["ps", "--format", "json"]:
            return CommandResult(0, self.ps_output, "")
        if "up" in command:
            self.worker_profile = (
                "gpu" if any("docker-compose.gpu.yml" in part for part in command) else "cpu"
            )
            if (
                self.worker_profile == "gpu"
                and "--build" in command
            ):
                self.legacy_gpu_preflight = False
                self.non_object_gpu_preflight = False
                if self.gpu_preflight_ok_after_build is not None:
                    self.gpu_preflight_ok = self.gpu_preflight_ok_after_build
            if self.up_ok:
                self.ps_output = compose_ps()
            return CommandResult(0 if self.up_ok else 1, "started" if self.up_ok else "", "start failed")
        if "AUTOCLIPPER_RUNTIME_PROFILE" in " ".join(command):
            return CommandResult(0, self.worker_profile, "")
        if "app.audio.gpu_preflight" in command:
            if self.non_object_gpu_preflight:
                return CommandResult(0, "[]", "")
            report = {
                "ok": self.gpu_preflight_ok,
                "actual_device": "cuda" if self.gpu_preflight_ok else "cpu",
                "actual_compute_type": "float16" if self.gpu_preflight_ok else "int8",
                "fallback_used": False,
            }
            if not self.legacy_gpu_preflight:
                report["preflight_schema_version"] = 1
                report["cuda_runtime_libraries"] = ["libcublas.so.12", "libcudnn.so.9"]
            return CommandResult(0 if self.gpu_preflight_ok else 1, json.dumps(report), "")
        if "stop" in command and "worker" in command:
            return CommandResult(0, "stopped", "")
        if "logs" in command:
            return CommandResult(0, "worker | safe log", "")
        return CommandResult(0, "", "")


def make_project(tmp_path: Path, *, env_text: str = "OPENAI_API_KEY=test-secret\n") -> Path:
    root = tmp_path / "AutoClipper Web"
    root.mkdir()
    (root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (root / "docker-compose.gpu.yml").write_text("services: {}\n", encoding="utf-8")
    (root / ".env").write_text(env_text, encoding="utf-8")
    return root


def compatible_bridge_status(
    module: Path,
    *,
    pid: int,
    state: str = "ready",
    **extra: object,
) -> dict[str, object]:
    return {
        "schemaVersion": launcher_controller.BRIDGE_PROTOCOL_VERSION,
        "state": state,
        "pid": pid,
        "bridgeBuildFingerprint": launcher_controller.bridge_build_fingerprint(module),
        "contractFingerprint": launcher_controller.BRIDGE_CONTRACT_FINGERPRINT,
        **extra,
    }


def make_controller(
    root: Path,
    runner: FakeRunner,
    *,
    ready: bool = False,
    docker: str | None = "docker.exe",
    ports: set[int] | None = None,
    url_values: list[bool] | None = None,
    gpu: HostGpu | None = None,
    docker_desktop: Path | None = Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe"),
    desktop_starter: Callable[[Path], None] | None = None,
    monotonic_clock: Callable[[], float] | None = None,
    background_process_starter: Callable[[list[str], Path], None] | None = None,
    process_checker: Callable[[int], bool] | None = None,
) -> LauncherController:
    values = iter(url_values or [])

    def url_checker(_url: str, _expected: str | None, _timeout: float) -> bool:
        if url_values is not None:
            return next(values, ready)
        return ready

    return LauncherController(
        root,
        command_runner=runner,
        url_checker=url_checker,
        port_checker=lambda port: port in (ports or set()),
        docker_finder=lambda: docker,
        docker_desktop_finder=lambda: docker_desktop,
        desktop_application_starter=desktop_starter or (lambda _path: None),
        gpu_checker=lambda: gpu or HostGpu(),
        sleeper=lambda _seconds: None,
        monotonic_clock=monotonic_clock or (lambda: 0.0),
        background_process_starter=background_process_starter
        or (lambda _command, _cwd: None),
        process_checker=process_checker or (lambda _pid: False),
        browser_opener=lambda _url: True,
    )


def test_parse_compose_ps_accepts_json_lines() -> None:
    states = parse_compose_ps(compose_ps())

    assert set(states) == {"backend", "frontend", "worker", "redis"}
    assert all(state.running for state in states.values())


def test_preflight_reports_missing_docker_cli(tmp_path: Path) -> None:
    controller = make_controller(make_project(tmp_path), FakeRunner(), docker=None)

    report = controller.preflight()

    assert report.ok is False
    assert any("Docker CLI" in error for error in report.errors)


def test_preflight_reports_daemon_unavailable(tmp_path: Path) -> None:
    runner = FakeRunner(daemon_ok=False)
    controller = make_controller(make_project(tmp_path), runner)

    report = controller.preflight()

    assert report.daemon_ready is False
    assert any("Docker daemon" in error for error in report.errors)
    assert not any("desktop" in call[0] for call in runner.calls)


def test_start_bootstraps_docker_desktop_before_compose(tmp_path: Path) -> None:
    runner = FakeRunner(daemon_ok=False, desktop_start_null_output=True)
    controller = make_controller(make_project(tmp_path), runner, ready=True)

    result = controller.start(timeout=4, open_browser=False)

    desktop_start_index = next(
        index
        for index, call in enumerate(runner.calls)
        if call[0][1:3] == ["desktop", "start"]
    )
    compose_index = next(
        index for index, call in enumerate(runner.calls) if "compose" in call[0]
    )
    assert desktop_start_index < compose_index
    assert result.docker_desktop_started is True
    assert result.status.ready is True


def test_start_does_not_relaunch_ready_docker_desktop(tmp_path: Path) -> None:
    runner = FakeRunner(ps_output=compose_ps())
    controller = make_controller(make_project(tmp_path), runner, ready=True)

    result = controller.start(open_browser=False)

    assert result.docker_desktop_started is False
    assert not any(call[0][1:3] == ["desktop", "start"] for call in runner.calls)


def test_start_falls_back_to_desktop_executable_without_cli_plugin(
    tmp_path: Path,
) -> None:
    runner = FakeRunner(daemon_ok=False, desktop_cli_ok=False)
    desktop_executable = Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe")
    started: list[Path] = []

    def start_desktop(path: Path) -> None:
        started.append(path)
        runner.daemon_ok = True

    controller = make_controller(
        make_project(tmp_path),
        runner,
        ready=True,
        docker_desktop=desktop_executable,
        desktop_starter=start_desktop,
    )

    result = controller.start(timeout=4, open_browser=False)

    assert started == [desktop_executable]
    assert result.docker_desktop_started is True


def test_start_reports_missing_docker_desktop(tmp_path: Path) -> None:
    runner = FakeRunner(daemon_ok=False, desktop_cli_ok=False)
    controller = make_controller(
        make_project(tmp_path), runner, docker_desktop=None
    )

    with pytest.raises(LauncherError) as error:
        controller.start(timeout=1, open_browser=False)

    assert error.value.code == "docker_desktop_not_found"
    assert not any("compose" in call[0] for call in runner.calls)


def test_start_reports_desktop_executable_launch_failure(tmp_path: Path) -> None:
    runner = FakeRunner(daemon_ok=False, desktop_cli_ok=False)

    def fail_start(_path: Path) -> None:
        raise OSError("launch failed test-secret")

    controller = make_controller(
        make_project(tmp_path), runner, desktop_starter=fail_start
    )

    with pytest.raises(LauncherError) as error:
        controller.start(timeout=1, open_browser=False)

    assert error.value.code == "docker_desktop_start_failed"
    assert "test-secret" not in error.value.detail
    assert "[REDACTED]" in error.value.detail
    assert not any("compose" in call[0] for call in runner.calls)


def test_start_reports_docker_daemon_timeout_before_compose(tmp_path: Path) -> None:
    runner = FakeRunner(
        daemon_ok=False,
        daemon_ready_after_desktop_start=False,
    )
    controller = make_controller(make_project(tmp_path), runner)

    with pytest.raises(LauncherError) as error:
        controller.start(timeout=0.1, open_browser=False)

    assert error.value.code == "docker_daemon_start_timeout"
    assert not any("compose" in call[0] for call in runner.calls)


def test_start_accepts_nonzero_desktop_start_when_daemon_becomes_ready(
    tmp_path: Path,
) -> None:
    runner = FakeRunner(
        daemon_ok=False,
        desktop_start_ok=False,
        daemon_ready_after_desktop_start=True,
    )
    controller = make_controller(
        make_project(tmp_path), runner, ready=True, docker_desktop=None
    )

    result = controller.start(timeout=4, open_browser=False)

    assert result.docker_desktop_started is True
    assert result.status.ready is True


def test_docker_start_timeout_is_a_hard_command_deadline(tmp_path: Path) -> None:
    now = [0.0]

    class AdvancingRunner(FakeRunner):
        def __call__(
            self, command: list[str], cwd: Path, timeout: float | None
        ) -> CommandResult:
            result = super().__call__(command, cwd, timeout)
            now[0] += timeout or 0.0
            return result

    runner = AdvancingRunner(daemon_ok=False)
    controller = make_controller(
        make_project(tmp_path),
        runner,
        monotonic_clock=lambda: now[0],
    )

    with pytest.raises(LauncherError) as error:
        controller.start(timeout=3.0, open_browser=False)

    assert error.value.code == "docker_daemon_start_timeout"
    assert runner.calls[0][0][-1] == "info"
    assert runner.calls[0][2] == pytest.approx(3.0)
    assert len(runner.calls) == 1


def test_find_docker_cli_in_per_user_desktop_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local_app_data = tmp_path / "LocalAppData"
    docker = (
        local_app_data
        / "Programs"
        / "DockerDesktop"
        / "resources"
        / "bin"
        / "docker.exe"
    )
    docker.parent.mkdir(parents=True)
    docker.write_text("", encoding="utf-8")
    monkeypatch.setattr(launcher_controller.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        launcher_controller, "DOCKER_BIN_DIR", tmp_path / "missing-docker-bin"
    )
    monkeypatch.delenv("ProgramFiles", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    assert find_docker_executable() == str(docker)


def test_preflight_reports_compose_unavailable(tmp_path: Path) -> None:
    controller = make_controller(make_project(tmp_path), FakeRunner(compose_ok=False))

    report = controller.preflight()

    assert report.compose_available is False
    assert any("docker compose" in error for error in report.errors)


def test_preflight_reports_missing_openai_key_without_exposing_a_value(tmp_path: Path) -> None:
    controller = make_controller(make_project(tmp_path, env_text="OPENAI_API_KEY=\n"), FakeRunner())

    report = controller.preflight()

    assert report.openai_key_configured is False
    assert any("OPENAI_API_KEY未設定" in warning for warning in report.warnings)
    assert all("sk-" not in warning for warning in report.warnings)


def test_preflight_accepts_and_redacts_openai_key_from_process_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "environment-secret")
    controller = make_controller(
        make_project(tmp_path, env_text="OPENAI_API_KEY=\n"), FakeRunner()
    )

    report = controller.preflight()

    assert report.openai_key_configured is True
    assert controller.redact("key=environment-secret") == "key=[REDACTED]"


def test_preflight_detects_port_conflict(tmp_path: Path) -> None:
    controller = make_controller(make_project(tmp_path), FakeRunner(), ports={8000, 6379})

    report = controller.preflight()

    assert report.ok is False
    assert any("port 8000" in error for error in report.errors)
    assert any("port 6379" in error for error in report.errors)


def test_preflight_allows_autoclipper_service_ports_while_health_is_starting(
    tmp_path: Path,
) -> None:
    runner = FakeRunner(ps_output=compose_ps())
    controller = make_controller(
        make_project(tmp_path),
        runner,
        ports={3000, 8000, 6379},
        ready=False,
    )

    report = controller.preflight()

    assert report.ok is True
    assert not any("port 3000" in error for error in report.errors)
    assert not any("port 8000" in error for error in report.errors)
    assert any("backend serviceは起動中" in warning for warning in report.warnings)
    assert any("frontend serviceは起動中" in warning for warning in report.warnings)


def test_start_uses_project_path_with_spaces_and_waits_for_health(tmp_path: Path) -> None:
    runner = FakeRunner(ps_output=compose_ps())
    controller = make_controller(
        make_project(tmp_path),
        runner,
        url_values=[False, False, True, True],
    )

    result = controller.start(timeout=4, open_browser=False)

    assert result.already_running is False
    up_call = next(call for call in runner.calls if "up" in call[0])
    assert up_call[0][-3:] == ["compose", "up", "-d"]
    assert up_call[1].name == "AutoClipper Web"


def test_start_does_not_duplicate_running_runtime(tmp_path: Path) -> None:
    runner = FakeRunner(ps_output=compose_ps())
    controller = make_controller(make_project(tmp_path), runner, ready=True)

    result = controller.start(open_browser=False)

    assert result.already_running is True
    assert not any("up" in call[0] for call in runner.calls)


def test_start_opens_upload_page_when_runtime_is_ready(tmp_path: Path) -> None:
    opened: list[str] = []
    runner = FakeRunner(ps_output=compose_ps())
    root = make_project(tmp_path)
    controller = LauncherController(
        root,
        command_runner=runner,
        url_checker=lambda _url, _expected, _timeout: True,
        port_checker=lambda _port: False,
        docker_finder=lambda: "docker.exe",
        browser_opener=lambda url: not opened.append(url),
    )

    controller.start()

    assert opened == ["http://localhost:3000/upload?runtimeProfile=cpu"]


def test_rebuild_start_uses_explicit_build_flag(tmp_path: Path) -> None:
    runner = FakeRunner(ps_output=compose_ps())
    controller = make_controller(
        make_project(tmp_path),
        runner,
        url_values=[False, False, True, True],
    )

    controller.start(rebuild=True, timeout=4, open_browser=False)

    up_call = next(call for call in runner.calls if "up" in call[0])
    assert up_call[0][-4:] == ["compose", "up", "-d", "--build"]


def test_recommended_start_uses_gpu_override_and_gpu_upload_profile(tmp_path: Path) -> None:
    opened: list[str] = []
    runner = FakeRunner(
        ps_output=compose_ps(),
        docker_gpu=True,
        worker_profile="cpu",
    )
    root = make_project(tmp_path)
    values = iter([False, False, True, True])
    controller = LauncherController(
        root,
        command_runner=runner,
        url_checker=lambda _url, _expected, _timeout: next(values, True),
        port_checker=lambda _port: False,
        docker_finder=lambda: "docker.exe",
        gpu_checker=lambda: HostGpu("NVIDIA Test GPU", "1.0", 16384),
        sleeper=lambda _seconds: None,
        browser_opener=lambda url: not opened.append(url),
    )

    result = controller.start(profile="recommended", timeout=4)

    up_call = next(call for call in runner.calls if "up" in call[0])
    assert str(root / "docker-compose.gpu.yml") in up_call[0]
    assert "--build" in up_call[0]
    assert any("app.audio.gpu_preflight" in call[0] for call in runner.calls)
    assert result.runtime_profile.key == "gpu"
    assert result.gpu_override_enabled is True
    assert result.fallback_used is False
    assert opened == ["http://localhost:3000/upload?runtimeProfile=gpu"]


def test_stopped_gpu_runtime_starts_without_forced_rebuild(tmp_path: Path) -> None:
    runner = FakeRunner(
        ps_output=compose_ps(running=False),
        docker_gpu=True,
        worker_profile="gpu",
    )
    controller = make_controller(
        make_project(tmp_path),
        runner,
        ready=True,
        gpu=HostGpu("NVIDIA Test GPU", "1.0", 16384),
    )

    result = controller.start(profile="recommended", open_browser=False)

    up_call = next(call for call in runner.calls if "up" in call[0])
    assert "--build" not in up_call[0]
    assert "--force-recreate" not in up_call[0]
    assert result.runtime_profile.key == "gpu"
    assert result.already_running is False


def test_running_gpu_profile_revalidates_worker_before_early_return(tmp_path: Path) -> None:
    runner = FakeRunner(
        ps_output=compose_ps(),
        docker_gpu=True,
        worker_profile="gpu",
    )
    controller = make_controller(
        make_project(tmp_path),
        runner,
        ready=True,
        gpu=HostGpu("NVIDIA Test GPU", "1.0", 16384),
    )

    result = controller.start(profile="gpu", open_browser=False)

    assert result.already_running is True
    assert any("app.audio.gpu_preflight" in call[0] for call in runner.calls)
    assert not any("up" in call[0] for call in runner.calls)


def test_broken_running_gpu_profile_rebuilds_worker_image(tmp_path: Path) -> None:
    runner = FakeRunner(
        ps_output=compose_ps(),
        docker_gpu=True,
        worker_profile="gpu",
        gpu_preflight_ok=False,
        gpu_preflight_ok_after_build=True,
    )
    controller = make_controller(
        make_project(tmp_path),
        runner,
        ready=True,
        gpu=HostGpu("NVIDIA Test GPU", "1.0", 16384),
    )

    result = controller.start(profile="gpu", open_browser=False)

    up_call = next(call for call in runner.calls if "up" in call[0])
    stop_index = next(index for index, call in enumerate(runner.calls) if "stop" in call[0])
    up_index = next(index for index, call in enumerate(runner.calls) if "up" in call[0])
    assert stop_index < up_index
    assert "--build" in up_call[0]
    assert "--force-recreate" in up_call[0]
    assert up_call[0][-1] == "worker"
    assert result.already_running is False
    assert result.runtime_profile.key == "gpu"


def test_legacy_running_gpu_preflight_rebuilds_before_reuse(tmp_path: Path) -> None:
    runner = FakeRunner(
        ps_output=compose_ps(),
        docker_gpu=True,
        worker_profile="gpu",
        legacy_gpu_preflight=True,
    )
    controller = make_controller(
        make_project(tmp_path),
        runner,
        ready=True,
        gpu=HostGpu("NVIDIA Test GPU", "1.0", 16384),
    )

    result = controller.start(profile="gpu", open_browser=False)

    stop_index = next(index for index, call in enumerate(runner.calls) if "stop" in call[0])
    up_index = next(index for index, call in enumerate(runner.calls) if "up" in call[0])
    up_call = runner.calls[up_index]
    assert stop_index < up_index
    assert "--build" in up_call[0]
    assert "--force-recreate" in up_call[0]
    assert result.already_running is False


def test_non_object_running_gpu_preflight_repairs_worker(tmp_path: Path) -> None:
    runner = FakeRunner(
        ps_output=compose_ps(),
        docker_gpu=True,
        worker_profile="gpu",
        non_object_gpu_preflight=True,
    )
    controller = make_controller(
        make_project(tmp_path),
        runner,
        ready=True,
        gpu=HostGpu("NVIDIA Test GPU", "1.0", 16384),
    )

    result = controller.start(profile="gpu", open_browser=False)

    stop_index = next(index for index, call in enumerate(runner.calls) if "stop" in call[0])
    up_index = next(index for index, call in enumerate(runner.calls) if "up" in call[0])
    assert stop_index < up_index
    assert "--build" in runner.calls[up_index][0]
    assert result.already_running is False


def test_cpu_and_gpu_compose_use_project_scoped_distinct_worker_images() -> None:
    cpu_compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    gpu_compose = (ROOT / "docker-compose.gpu.yml").read_text(encoding="utf-8")

    assert "image: ${COMPOSE_PROJECT_NAME:-autoclipperweb}-worker-cpu" in cpu_compose
    assert "image: ${COMPOSE_PROJECT_NAME:-autoclipperweb}-worker-gpu" in gpu_compose


def test_recommended_start_falls_back_to_cpu_with_visible_reason(tmp_path: Path) -> None:
    runner = FakeRunner(ps_output=compose_ps())
    controller = make_controller(
        make_project(tmp_path),
        runner,
        url_values=[False, False, True, True],
    )

    result = controller.start(profile="recommended", timeout=4, open_browser=False)

    assert result.runtime_profile.key == "cpu"
    assert result.fallback_used is True
    assert "NVIDIA GPU" in (result.fallback_reason or "")


def test_explicit_gpu_start_stops_when_gpu_preflight_is_unavailable(tmp_path: Path) -> None:
    controller = make_controller(make_project(tmp_path), FakeRunner())

    with pytest.raises(LauncherError, match="GPU必須") as error:
        controller.start(profile="gpu", open_browser=False)

    assert error.value.code == "gpu_preflight_failed"


def test_recommended_gpu_worker_failure_recreates_cpu_worker(tmp_path: Path) -> None:
    runner = FakeRunner(
        ps_output=compose_ps(),
        docker_gpu=True,
        worker_profile="cpu",
        gpu_preflight_ok=False,
    )
    controller = make_controller(
        make_project(tmp_path),
        runner,
        gpu=HostGpu("NVIDIA Test GPU", "1.0", 16384),
        url_values=[False, False, True, True, True, True],
    )

    result = controller.start(profile="recommended", timeout=4, open_browser=False)

    assert result.runtime_profile.key == "cpu"
    assert result.fallback_used is True
    assert "gpu_worker_preflight_failed" in (result.fallback_reason or "")
    cpu_fallback = [
        call
        for call in runner.calls
        if "up" in call[0]
        and "--force-recreate" in call[0]
        and not any("docker-compose.gpu.yml" in part for part in call[0])
    ]
    assert cpu_fallback


def test_explicit_gpu_worker_failure_stops_without_cpu_fallback(tmp_path: Path) -> None:
    runner = FakeRunner(
        ps_output=compose_ps(),
        docker_gpu=True,
        worker_profile="cpu",
        gpu_preflight_ok=False,
    )
    controller = make_controller(
        make_project(tmp_path),
        runner,
        gpu=HostGpu("NVIDIA Test GPU", "1.0", 16384),
        url_values=[False, False, True, True],
    )

    with pytest.raises(LauncherError) as error:
        controller.start(profile="GPU", timeout=4, open_browser=False)

    assert error.value.code == "gpu_worker_preflight_failed"
    assert any(call[0][-2:] == ["stop", "worker"] for call in runner.calls)
    assert not any(
        "up" in call[0]
        and "--force-recreate" in call[0]
        and not any("docker-compose.gpu.yml" in part for part in call[0])
        for call in runner.calls
    )


def test_start_reports_compose_failure(tmp_path: Path) -> None:
    controller = make_controller(make_project(tmp_path), FakeRunner(up_ok=False))

    with pytest.raises(LauncherError, match="Docker services") as error:
        controller.start(open_browser=False)

    assert error.value.code == "compose_start_failed"


def test_wait_until_ready_reports_timeout(tmp_path: Path) -> None:
    controller = make_controller(make_project(tmp_path), FakeRunner(), ready=False)

    with pytest.raises(LauncherError, match="timeout") as error:
        controller.wait_until_ready(timeout=1, poll_interval=1)

    assert error.value.code == "health_timeout"


def test_open_paths_use_expected_directories(tmp_path: Path) -> None:
    opened: list[Path] = []
    root = make_project(tmp_path)
    controller = LauncherController(
        root,
        command_runner=FakeRunner(),
        docker_finder=lambda: "docker.exe",
        port_checker=lambda _port: False,
        path_opener=opened.append,
    )

    controller.open_outputs()
    controller.open_uploads()

    assert opened == [root / "storage" / "outputs", root / "storage" / "uploads"]


def test_logs_and_errors_redact_openai_key(tmp_path: Path) -> None:
    class SecretRunner(FakeRunner):
        def __call__(self, command: list[str], cwd: Path, timeout: float | None) -> CommandResult:
            if "logs" in command:
                return CommandResult(0, "OPENAI_API_KEY=test-secret", "")
            return super().__call__(command, cwd, timeout)

    controller = make_controller(make_project(tmp_path), SecretRunner())

    output = controller.recent_logs()

    assert "test-secret" not in output
    assert "[REDACTED]" in output


def test_launcher_error_popup_redacts_openai_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = make_controller(make_project(tmp_path), FakeRunner())
    app = LauncherApp.__new__(LauncherApp)
    app.controller = controller
    appended: list[str] = []
    shown: list[str] = []
    app._append = appended.append  # type: ignore[method-assign]
    monkeypatch.setattr(
        "launcher.app.messagebox.showerror",
        lambda _title, message: shown.append(message),
    )

    app._handle_error(
        LauncherError("desktop_start_failed", "起動失敗", "detail=test-secret")
    )

    assert appended == ["ERROR: 起動失敗\ndetail=[REDACTED]"]
    assert shown == ["起動失敗\ndetail=[REDACTED]"]


def test_stop_preserves_volumes_and_data(tmp_path: Path) -> None:
    runner = FakeRunner()
    controller = make_controller(make_project(tmp_path), runner)

    controller.stop()

    stop_call = runner.calls[-1][0]
    assert stop_call[-2:] == ["compose", "stop"]
    assert "down" not in stop_call
    assert "-v" not in stop_call


def test_launcher_starts_codex_bridge_with_host_python(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    module = root / "launcher" / "codex_bridge.py"
    module.parent.mkdir()
    module.write_text("# bridge fixture\n", encoding="utf-8")
    observed: list[tuple[list[str], Path]] = []
    live_pids: set[int] = {321}

    def start_bridge(command: list[str], cwd: Path) -> None:
        observed.append((list(command), cwd))
        status = root / "storage" / "codex_bridge" / "status.json"
        status.parent.mkdir(parents=True, exist_ok=True)
        status.write_text(
            json.dumps(
                compatible_bridge_status(module, pid=321)
            ),
            encoding="utf-8",
        )

    controller = make_controller(
        root,
        FakeRunner(),
        background_process_starter=start_bridge,
        process_checker=lambda pid: pid in live_pids,
    )

    started = controller.ensure_codex_bridge_running(timeout=1, poll_interval=0.1)

    assert started is True
    assert observed == [
        (
            [
                sys.executable,
                str(module.resolve()),
                "serve",
                "--project-root",
                str(root.resolve()),
            ],
            root.resolve(),
        )
    ]


@pytest.mark.parametrize(
    "fingerprint_field",
    ["bridgeBuildFingerprint", "contractFingerprint"],
)
def test_launcher_restarts_live_bridge_when_fingerprint_is_stale(
    tmp_path: Path,
    fingerprint_field: str,
) -> None:
    root = make_project(tmp_path)
    module = root / "launcher" / "codex_bridge.py"
    module.parent.mkdir()
    module.write_text("# current bridge fixture\n", encoding="utf-8")
    status = root / "storage" / "codex_bridge" / "status.json"
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(
        json.dumps(
            {
                **compatible_bridge_status(module, pid=111),
                fingerprint_field: "0" * 64,
            }
        ),
        encoding="utf-8",
    )
    stop_request = root / "storage" / "codex_bridge" / "stop.request"
    observed: list[list[str]] = []

    def process_checker(pid: int) -> bool:
        if pid == 111:
            return not stop_request.exists()
        return pid == 222

    def start_bridge(command: list[str], _cwd: Path) -> None:
        observed.append(list(command))
        status.write_text(
            json.dumps(compatible_bridge_status(module, pid=222)),
            encoding="utf-8",
        )

    controller = make_controller(
        root,
        FakeRunner(),
        background_process_starter=start_bridge,
        process_checker=process_checker,
    )

    assert controller.ensure_codex_bridge_running(timeout=1, poll_interval=0.1)
    assert len(observed) == 1
    assert json.loads(status.read_text(encoding="utf-8"))["pid"] == 222
    assert not stop_request.exists()


def test_launcher_rejects_live_bridge_with_stale_contract_fingerprint(
    tmp_path: Path,
) -> None:
    root = make_project(tmp_path)
    module = root / "launcher" / "codex_bridge.py"
    module.parent.mkdir()
    module.write_text("# current bridge fixture\n", encoding="utf-8")
    status = root / "storage" / "codex_bridge" / "status.json"
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(
        json.dumps(
            {
                **compatible_bridge_status(module, pid=111),
                "contractFingerprint": "0" * 64,
            }
        ),
        encoding="utf-8",
    )
    controller = make_controller(
        root,
        FakeRunner(),
        process_checker=lambda pid: pid == 111,
    )

    assert controller.codex_bridge_ready() is False


def test_launcher_waits_for_stopped_bridge_process_to_exit_before_restart(
    tmp_path: Path,
) -> None:
    root = make_project(tmp_path)
    module = root / "launcher" / "codex_bridge.py"
    module.parent.mkdir()
    module.write_text("# current bridge fixture\n", encoding="utf-8")
    status = root / "storage" / "codex_bridge" / "status.json"
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(
        json.dumps(
            {
                **compatible_bridge_status(module, pid=111),
                "bridgeBuildFingerprint": "0" * 64,
            }
        ),
        encoding="utf-8",
    )
    stop_request = root / "storage" / "codex_bridge" / "stop.request"
    process_checks = 0
    observed: list[list[str]] = []

    def process_checker(pid: int) -> bool:
        nonlocal process_checks
        if pid == 111:
            process_checks += 1
            if stop_request.exists():
                status.write_text(
                    json.dumps(
                        compatible_bridge_status(module, pid=111, state="stopped")
                    ),
                    encoding="utf-8",
                )
            return process_checks < 4
        return pid == 222

    def start_bridge(command: list[str], _cwd: Path) -> None:
        observed.append(list(command))
        status.write_text(
            json.dumps(compatible_bridge_status(module, pid=222)),
            encoding="utf-8",
        )

    controller = make_controller(
        root,
        FakeRunner(),
        background_process_starter=start_bridge,
        process_checker=process_checker,
    )

    assert controller.ensure_codex_bridge_running(timeout=1, poll_interval=0.1)
    assert process_checks >= 4
    assert len(observed) == 1


def test_launcher_start_continues_when_codex_bridge_is_unavailable(
    tmp_path: Path,
) -> None:
    root = make_project(tmp_path)
    module = root / "launcher" / "codex_bridge.py"
    module.parent.mkdir()
    module.write_text("# bridge fixture\n", encoding="utf-8")

    def start_bridge(_command: list[str], _cwd: Path) -> None:
        status = root / "storage" / "codex_bridge" / "status.json"
        status.parent.mkdir(parents=True, exist_ok=True)
        status.write_text(
            json.dumps(
                compatible_bridge_status(
                    module,
                    pid=0,
                    state="error",
                    errorCode="codex_login_missing",
                )
            ),
            encoding="utf-8",
        )

    controller = make_controller(
        root,
        FakeRunner(),
        ready=True,
        background_process_starter=start_bridge,
        process_checker=lambda _pid: False,
    )

    result = controller.start(timeout=1, open_browser=False)

    assert result.status.ready is True
    assert controller.codex_bridge_error is not None
    assert controller.codex_bridge_error.code == "codex_login_missing"


def test_bridge_start_does_not_delete_existing_status_during_race(
    tmp_path: Path,
) -> None:
    root = make_project(tmp_path)
    module = root / "launcher" / "codex_bridge.py"
    module.parent.mkdir()
    module.write_text("# bridge fixture\n", encoding="utf-8")
    status = root / "storage" / "codex_bridge" / "status.json"
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(
        json.dumps(
                compatible_bridge_status(module, pid=111)
        ),
        encoding="utf-8",
    )
    existing_status_seen: list[bool] = []

    def start_bridge(_command: list[str], _cwd: Path) -> None:
        existing_status_seen.append(status.is_file())
        status.write_text(
            json.dumps(
                compatible_bridge_status(module, pid=222)
            ),
            encoding="utf-8",
        )

    controller = make_controller(
        root,
        FakeRunner(),
        background_process_starter=start_bridge,
        process_checker=lambda pid: pid == 222,
    )

    assert controller.ensure_codex_bridge_running(timeout=1) is True
    assert existing_status_seen == [True]


def test_launcher_stop_signals_live_codex_bridge(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    module = root / "launcher" / "codex_bridge.py"
    module.parent.mkdir()
    module.write_text("# bridge fixture\n", encoding="utf-8")
    status = root / "storage" / "codex_bridge" / "status.json"
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(
        json.dumps(
                compatible_bridge_status(module, pid=654)
        ),
        encoding="utf-8",
    )
    checks = iter([True, False])
    runner = FakeRunner()
    controller = make_controller(
        root,
        runner,
        process_checker=lambda _pid: next(checks),
    )

    result = controller.stop()

    assert result.returncode == 0
    assert runner.calls[-1][0][-2:] == ["compose", "stop"]
    stop_payload = json.loads(
        (root / "storage" / "codex_bridge" / "stop.request").read_text(
            encoding="utf-8"
        )
    )
    assert isinstance(stop_payload["requestedAt"], float)


def test_windows_entrypoint_quotes_project_path_and_does_not_reset_data() -> None:
    entrypoint = (ROOT / "Start AutoClipper.cmd").read_text(encoding="utf-8")

    assert 'cd /d "%~dp0"' in entrypoint
    assert "py -3.11 -m launcher" in entrypoint
    assert "sys.version_info >= (3,11)" in entrypoint
    assert "docker compose down" not in entrypoint
    assert "down -v" not in entrypoint


def test_launcher_console_uses_japanese_capable_windows_font() -> None:
    app_source = (ROOT / "launcher" / "app.py").read_text(encoding="utf-8")

    assert 'font=("Yu Gothic UI", 10)' in app_source
    assert "Consolas" not in app_source


def test_launcher_desktop_entrypoint_auto_starts_recommended_profile() -> None:
    app_source = (ROOT / "launcher" / "app.py").read_text(encoding="utf-8")

    assert 'lambda: self.controller.start(profile="recommended")' in app_source
    assert "Docker DesktopとAutoClipperを自動起動します" in app_source
