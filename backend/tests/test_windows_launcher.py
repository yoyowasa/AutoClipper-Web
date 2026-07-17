from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from launcher.controller import CommandResult, LauncherController, LauncherError, parse_compose_ps  # noqa: E402


def compose_ps(*, running: bool = True) -> str:
    state = "running" if running else "exited"
    rows = (
        {"Service": name, "State": state, "Health": "healthy" if name == "backend" else ""}
        for name in ("backend", "frontend", "worker", "redis")
    )
    return "\n".join(json.dumps(row) for row in rows)


class FakeRunner:
    def __init__(self, *, daemon_ok: bool = True, compose_ok: bool = True, ps_output: str | None = None, up_ok: bool = True) -> None:
        self.daemon_ok = daemon_ok
        self.compose_ok = compose_ok
        self.ps_output = ps_output if ps_output is not None else compose_ps(running=False)
        self.up_ok = up_ok
        self.calls: list[tuple[list[str], Path, float | None]] = []

    def __call__(self, command: list[str], cwd: Path, timeout: float | None) -> CommandResult:
        command = list(command)
        self.calls.append((command, cwd, timeout))
        if command[-2:] == ["compose", "version"]:
            return CommandResult(0 if self.compose_ok else 1, "Docker Compose", "")
        if command[-1:] == ["info"]:
            return CommandResult(0 if self.daemon_ok else 1, "Docker info", "daemon unavailable")
        if command[-3:] == ["ps", "--format", "json"]:
            return CommandResult(0, self.ps_output, "")
        if "up" in command:
            return CommandResult(0 if self.up_ok else 1, "started" if self.up_ok else "", "start failed")
        if command[-2:] == ["compose", "stop"]:
            return CommandResult(0, "stopped", "")
        if "logs" in command:
            return CommandResult(0, "worker | safe log", "")
        return CommandResult(0, "", "")


def make_project(tmp_path: Path, *, env_text: str = "OPENAI_API_KEY=test-secret\n") -> Path:
    root = tmp_path / "AutoClipper Web"
    root.mkdir()
    (root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (root / ".env").write_text(env_text, encoding="utf-8")
    return root


def make_controller(
    root: Path,
    runner: FakeRunner,
    *,
    ready: bool = False,
    docker: str | None = "docker.exe",
    ports: set[int] | None = None,
    url_values: list[bool] | None = None,
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
        sleeper=lambda _seconds: None,
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
    controller = make_controller(make_project(tmp_path), FakeRunner(daemon_ok=False))

    report = controller.preflight()

    assert report.daemon_ready is False
    assert any("Docker daemon" in error for error in report.errors)


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

    assert opened == ["http://localhost:3000/upload"]


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


def test_stop_preserves_volumes_and_data(tmp_path: Path) -> None:
    runner = FakeRunner()
    controller = make_controller(make_project(tmp_path), runner)

    controller.stop()

    stop_call = runner.calls[-1][0]
    assert stop_call[-2:] == ["compose", "stop"]
    assert "down" not in stop_call
    assert "-v" not in stop_call


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
