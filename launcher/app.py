from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk
from typing import Any

from .controller import (
    CPU_PROFILE,
    GPU_PROFILE,
    LauncherController,
    LauncherError,
    PreflightReport,
    REQUIRED_SERVICES,
    StartResult,
)


ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "storage" / "temp" / "launcher" / "launcher.log"


def configure_logging() -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("autoclipper.launcher")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = RotatingFileHandler(
            LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


class LauncherApp:
    def __init__(self, root: tk.Tk, controller: LauncherController) -> None:
        self.root = root
        self.controller = controller
        self.logger = configure_logging()
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.busy = False
        self.service_vars = {
            name: tk.StringVar(value="確認中") for name in REQUIRED_SERVICES
        }
        self.backend_var = tk.StringVar(value="確認中")
        self.frontend_var = tk.StringVar(value="確認中")
        self.docker_var = tk.StringVar(value="確認中")
        self.openai_var = tk.StringVar(value="確認中")
        self.disk_var = tk.StringVar(value="確認中")
        self.runtime_profile_var = tk.StringVar(value="確認中")
        self.transcription_var = tk.StringVar(value="確認中")
        self.gpu_var = tk.StringVar(value="確認中")
        self.worker_runtime_var = tk.StringVar(value="確認中")
        self.fallback_var = tk.StringVar(value="確認中")
        self.operation_var = tk.StringVar(value="起動前確認を実行しています")
        self.action_buttons: list[ttk.Button] = []
        self._build_ui()
        self.root.after(100, self._drain_events)
        self._run_async(
            "Docker Desktop・AutoClipper自動起動",
            lambda: self.controller.start(profile="recommended"),
            self._apply_start_result,
        )

    def _build_ui(self) -> None:
        self.root.title("AutoClipper Launcher")
        self.root.geometry("980x720")
        self.root.minsize(820, 620)

        style = ttk.Style(self.root)
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure(
            "Primary.TButton", font=("Segoe UI", 11, "bold"), padding=(14, 10)
        )
        style.configure("Action.TButton", padding=(10, 8))

        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text="AutoClipper", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            outer, text="Docker版AutoClipperの起動、確認、停止", foreground="#555555"
        ).pack(anchor=tk.W, pady=(0, 14))

        status_frame = ttk.LabelFrame(outer, text="Runtime status", padding=12)
        status_frame.pack(fill=tk.X)
        for index, name in enumerate(REQUIRED_SERVICES):
            ttk.Label(status_frame, text=name.capitalize()).grid(
                row=0, column=index, sticky=tk.W, padx=(0, 28)
            )
            ttk.Label(
                status_frame,
                textvariable=self.service_vars[name],
                style="Status.TLabel",
            ).grid(row=1, column=index, sticky=tk.W, padx=(0, 28))
        ttk.Label(status_frame, text="Backend health").grid(
            row=2, column=0, sticky=tk.W, pady=(12, 0)
        )
        ttk.Label(status_frame, textvariable=self.backend_var).grid(
            row=3, column=0, sticky=tk.W
        )
        ttk.Label(status_frame, text="Frontend").grid(
            row=2, column=1, sticky=tk.W, pady=(12, 0)
        )
        ttk.Label(status_frame, textvariable=self.frontend_var).grid(
            row=3, column=1, sticky=tk.W
        )
        ttk.Label(status_frame, text="Docker").grid(
            row=2, column=2, sticky=tk.W, pady=(12, 0)
        )
        ttk.Label(status_frame, textvariable=self.docker_var).grid(
            row=3, column=2, sticky=tk.W
        )
        ttk.Label(status_frame, text="OpenAI key").grid(
            row=2, column=3, sticky=tk.W, pady=(12, 0)
        )
        ttk.Label(status_frame, textvariable=self.openai_var).grid(
            row=3, column=3, sticky=tk.W
        )
        ttk.Label(status_frame, text="Disk free").grid(
            row=4, column=0, sticky=tk.W, pady=(12, 0)
        )
        ttk.Label(status_frame, textvariable=self.disk_var).grid(
            row=5, column=0, sticky=tk.W
        )
        ttk.Label(status_frame, text="Runtime profile").grid(
            row=4, column=1, sticky=tk.W, pady=(12, 0)
        )
        ttk.Label(status_frame, textvariable=self.runtime_profile_var).grid(
            row=5, column=1, sticky=tk.W
        )
        ttk.Label(status_frame, text="GPU").grid(
            row=4, column=2, sticky=tk.W, pady=(12, 0)
        )
        ttk.Label(status_frame, textvariable=self.gpu_var).grid(
            row=5, column=2, sticky=tk.W
        )
        ttk.Label(status_frame, text="Docker worker").grid(
            row=4, column=3, sticky=tk.W, pady=(12, 0)
        )
        ttk.Label(status_frame, textvariable=self.worker_runtime_var).grid(
            row=5, column=3, sticky=tk.W
        )
        ttk.Label(status_frame, text="Transcription").grid(
            row=6, column=0, columnspan=2, sticky=tk.W, pady=(12, 0)
        )
        ttk.Label(status_frame, textvariable=self.transcription_var).grid(
            row=7, column=0, columnspan=2, sticky=tk.W
        )
        ttk.Label(status_frame, text="Fallback").grid(
            row=6, column=2, columnspan=2, sticky=tk.W, pady=(12, 0)
        )
        ttk.Label(status_frame, textvariable=self.fallback_var).grid(
            row=7, column=2, columnspan=2, sticky=tk.W
        )

        primary = ttk.Frame(outer)
        primary.pack(fill=tk.X, pady=(14, 8))
        self._button(
            primary,
            "推奨設定で起動",
            lambda: self._start(False, "recommended"),
            "Primary.TButton",
        ).pack(side=tk.LEFT)
        self._button(
            primary, "CPU互換設定で起動", lambda: self._start(False, "cpu")
        ).pack(side=tk.LEFT, padx=(8, 0))
        self._button(primary, "Open App", self._open_app).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        self._button(primary, "Stop Services", self._stop).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        self._button(primary, "Refresh", self._refresh).pack(side=tk.LEFT, padx=(8, 0))

        utilities = ttk.Frame(outer)
        utilities.pack(fill=tk.X, pady=(0, 12))
        self._button(utilities, "Open Outputs", self.controller.open_outputs).pack(
            side=tk.LEFT
        )
        self._button(utilities, "Open Uploads", self.controller.open_uploads).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        self._button(utilities, "Docker Logs", self._show_logs).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        self._button(utilities, "Launcher Log", self._show_launcher_log).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        self._button(
            utilities,
            "GPU必須で起動",
            lambda: self._start(False, "gpu"),
        ).pack(side=tk.LEFT, padx=(8, 0))
        self._button(
            utilities,
            "再ビルドして起動",
            lambda: self._start(True, "recommended"),
        ).pack(side=tk.RIGHT)

        ttk.Label(outer, textvariable=self.operation_var).pack(anchor=tk.W, pady=(0, 6))
        self.console = scrolledtext.ScrolledText(
            outer, height=16, wrap=tk.WORD, font=("Yu Gothic UI", 10), state=tk.DISABLED
        )
        self.console.pack(fill=tk.BOTH, expand=True)
        self._append(
            "Launcherを起動しました。Docker DesktopとAutoClipperを自動起動します。"
        )

    def _button(
        self,
        parent: ttk.Frame,
        text: str,
        command: Callable[[], Any],
        style: str = "Action.TButton",
    ) -> ttk.Button:
        button = ttk.Button(
            parent, text=text, command=lambda: self._invoke(command), style=style
        )
        self.action_buttons.append(button)
        return button

    def _invoke(self, command: Callable[[], Any]) -> None:
        try:
            command()
        except Exception as exc:
            self._handle_error(exc)

    def _set_busy(self, busy: bool, label: str | None = None) -> None:
        self.busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        for button in self.action_buttons:
            button.configure(state=state)
        if label:
            self.operation_var.set(label)

    def _run_async(
        self, label: str, operation: Callable[[], Any], success: Callable[[Any], None]
    ) -> None:
        if self.busy:
            return
        self._set_busy(True, f"{label}中...")
        self._append(f"{label}を開始")

        def worker() -> None:
            try:
                result = operation()
                self.events.put(("success", (label, success, result)))
            except Exception as exc:
                self.events.put(("error", (label, exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "success":
                    label, callback, result = payload
                    self._set_busy(False, f"{label}完了")
                    callback(result)
                    self._append(f"{label}完了")
                else:
                    label, exc = payload
                    self._set_busy(False, f"{label}失敗")
                    self._handle_error(exc)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _append(self, message: str) -> None:
        safe = self.controller.redact(str(message))
        self.console.configure(state=tk.NORMAL)
        self.console.insert(tk.END, safe.rstrip() + "\n")
        self.console.see(tk.END)
        self.console.configure(state=tk.DISABLED)
        self.logger.info(safe.replace("\n", " | "))

    def _handle_error(self, exc: Exception) -> None:
        if isinstance(exc, LauncherError):
            message = exc.message
            detail = exc.detail
        else:
            message = str(exc)
            detail = None
        combined = message if not detail else f"{message}\n{detail}"
        combined = self.controller.redact(combined)
        self._append(f"ERROR: {combined}")
        messagebox.showerror("AutoClipper Launcher", combined)

    def _apply_preflight(self, report: PreflightReport) -> None:
        status = report.runtime_status
        for name in REQUIRED_SERVICES:
            service = status.services.get(name)
            self.service_vars[name].set(service.state if service else "not created")
        self.backend_var.set("ready" if status.backend_ready else "not ready")
        self.frontend_var.set("ready" if status.frontend_ready else "not ready")
        self.docker_var.set(
            "ready" if report.daemon_ready and report.compose_available else "not ready"
        )
        self.openai_var.set(
            "configured" if report.openai_key_configured else "not configured"
        )
        self.disk_var.set(f"{report.disk_free_gb:.1f} GB")
        actual_profile = status.worker_profile
        profile = (
            GPU_PROFILE
            if actual_profile == "gpu"
            else CPU_PROFILE
            if actual_profile == "cpu"
            else report.recommended_profile
        )
        self.runtime_profile_var.set(profile.label)
        self.transcription_var.set(profile.transcription_label)
        self.gpu_var.set(report.gpu_support.host.name or "not detected")
        self.worker_runtime_var.set(
            "GPU override enabled"
            if actual_profile == "gpu"
            else "CPU compose"
            if actual_profile == "cpu"
            else "not started"
        )
        self.fallback_var.set(
            "false"
            if report.gpu_support.available or actual_profile == "gpu"
            else report.gpu_support.unavailable_reason or "false"
        )
        for warning in report.warnings:
            self._append(f"WARNING: {warning}")
        for error in report.errors:
            self._append(f"ERROR: {error}")
        if report.already_running:
            self.operation_var.set("AutoClipperは起動済みです")

    def _refresh(self) -> None:
        self._run_async("状態更新", self.controller.preflight, self._apply_preflight)

    def _apply_start_result(self, result: StartResult) -> None:
        if result.docker_desktop_started:
            self._append("Docker Desktopを自動起動しました。")
        self._append(
            "既に起動済みです。"
            if result.already_running
            else "4 servicesが起動しました。"
        )
        self._refresh_after_operation()
        self.runtime_profile_var.set(result.runtime_profile.label)
        self.transcription_var.set(result.runtime_profile.transcription_label)
        self.gpu_var.set(result.gpu_name or "not detected")
        self.worker_runtime_var.set(
            "GPU override enabled"
            if result.gpu_override_enabled
            else "CPU compose"
        )
        self.fallback_var.set(result.fallback_reason or "false")
        self._append(
            f"Runtime profile: {result.runtime_profile.label}; "
            f"Transcription: {result.runtime_profile.transcription_label}; "
            f"Fallback: {result.fallback_reason or 'false'}"
        )

    def _start(self, rebuild: bool, profile: str) -> None:
        label = "再ビルドして起動" if rebuild else "AutoClipper起動"

        self._run_async(
            label,
            lambda: self.controller.start(profile=profile, rebuild=rebuild),
            self._apply_start_result,
        )

    def _stop(self) -> None:
        if not messagebox.askyesno(
            "Stop Services",
            "AutoClipper servicesを停止します。DB・outputs・volumeは削除しません。",
        ):
            return
        self._run_async(
            "Stop",
            self.controller.stop,
            lambda _result: self._refresh_after_operation(),
        )

    def _show_logs(self) -> None:
        self._run_async(
            "Docker logs取得",
            self.controller.recent_logs,
            lambda output: self._append(output or "ログはありません。"),
        )

    def _show_launcher_log(self) -> None:
        if LOG_PATH.is_file():
            self._append(
                LOG_PATH.read_text(encoding="utf-8", errors="replace")[-20_000:]
            )
        else:
            self._append("Launcher logはまだありません。")

    def _open_app(self) -> None:
        self.controller.open_app()
        self._append("Web UIを開きました。")

    def _refresh_after_operation(self) -> None:
        report = self.controller.preflight()
        self._apply_preflight(report)


def main() -> int:
    root = tk.Tk()
    app = LauncherApp(root, LauncherController(ROOT))
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
    return 0 if app else 1
