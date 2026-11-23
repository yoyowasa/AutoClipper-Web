"""Engine, model and reasoning effort per bridge lane, read from storage/codex_bridge/engine.json.

The screen saves the choice; the bridge reads it before every request, so a change applies to the
next request without a restart. Only models and efforts from the catalog are accepted: an unknown
value falls back to the engine's default instead of reaching a CLI.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ENGINE_CODEX = "codex"
ENGINE_CLAUDE = "claude"
ENGINES = (ENGINE_CODEX, ENGINE_CLAUDE)
LANES = ("normal", "analysis")
DEFAULT_MODELS = {ENGINE_CODEX: "gpt-6.1-sol", ENGINE_CLAUDE: "claude-opus-5-5"}
DEFAULT_EFFORT = "medium"
CODEX_EFFORTS = ("low", "medium", "high", "xhigh", "max", "ultra")
CLAUDE_EFFORTS = ("low", "medium", "high", "xhigh", "max")
# Subscription models of the Claude Code CLI (`claude --model`); the CLI has no catalog file.
CLAUDE_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-2")
# Used when the Codex model cache cannot be read.
CODEX_FALLBACK_MODELS = ("gpt-6.1-sol",)
MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9.\-]{0,63}$")
MAX_CACHE_BYTES = 2 * 1024 * 1024
MAX_SETTINGS_BYTES = 4096


@dataclass(frozen=True)
class LaneSetting:
    engine: str
    model: str
    effort: str

    def fields(self, prefix: str = "") -> dict[str, str]:
        if not prefix:
            return {"engine": self.engine, "model": self.model, "reasoningEffort": self.effort}
        return {f"{prefix}Engine": self.engine, f"{prefix}Model": self.model,
                f"{prefix}ReasoningEffort": self.effort}


def _codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured) if configured else Path.home() / ".codex"


def codex_models(codex_home: Path | None = None) -> list[dict[str, Any]]:
    """Listed models of the Codex CLI's own model cache: ids and efforts only, nothing else is copied."""
    path = (codex_home or _codex_home()) / "models_cache.json"
    models: list[dict[str, Any]] = []
    try:
        if path.stat().st_size <= MAX_CACHE_BYTES:
            raw = json.loads(path.read_text(encoding="utf-8")).get("models")
            for item in raw if isinstance(raw, list) else []:
                if not isinstance(item, dict) or item.get("visibility") != "list":
                    continue
                slug = item.get("slug")
                levels = [level.get("effort") if isinstance(level, dict) else level
                          for level in item.get("supported_reasoning_levels") or []]
                efforts = [effort for effort in CODEX_EFFORTS if effort in levels]
                if isinstance(slug, str) and MODEL_ID.fullmatch(slug) and efforts:
                    models.append({"id": slug, "efforts": efforts})
    except (OSError, ValueError, AttributeError):
        models = []
    if not models:
        models = [{"id": model, "efforts": list(CODEX_EFFORTS[:5])} for model in CODEX_FALLBACK_MODELS]
    return models[:30]


def engine_catalog(codex_home: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    return {
        ENGINE_CODEX: codex_models(codex_home),
        ENGINE_CLAUDE: [{"id": model, "efforts": list(CLAUDE_EFFORTS)} for model in CLAUDE_MODELS],
    }


def _choice(engine: str, model: Any, effort: Any, catalog: dict[str, list[dict[str, Any]]]) -> LaneSetting:
    models = {item["id"]: item["efforts"] for item in catalog[engine]}
    default_model = DEFAULT_MODELS[engine] if DEFAULT_MODELS[engine] in models else next(iter(models))
    chosen_model = model if isinstance(model, str) and model in models else default_model
    efforts = models[chosen_model]
    default_effort = DEFAULT_EFFORT if DEFAULT_EFFORT in efforts else efforts[0]
    return LaneSetting(engine, chosen_model, effort if isinstance(effort, str) and effort in efforts else default_effort)


def _engine(value: Any) -> str | None:
    engine = str(value or "").strip().lower()
    return engine if engine in ENGINES else None


def read_lane_settings(settings_file: Path, catalog: dict[str, list[dict[str, Any]]], *,
                       engine_override: str | None = None) -> dict[str, LaneSetting]:
    """Lane settings from the file; the old {"engine", "analysisEngine"} form keeps working."""
    try:
        if settings_file.stat().st_size > MAX_SETTINGS_BYTES:
            raise ValueError("settings_too_large")
        data = json.loads(settings_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("settings_invalid")
    except (OSError, ValueError):
        data = {}
    lanes = data.get("lanes") if isinstance(data.get("lanes"), dict) else {}
    normal = lanes.get("normal") if isinstance(lanes.get("normal"), dict) else {}
    analysis = lanes.get("analysis") if isinstance(lanes.get("analysis"), dict) else {}
    normal_engine = _engine(engine_override) or _engine(normal.get("engine")) or _engine(data.get("engine")) \
        or ENGINE_CODEX
    analysis_engine = (_engine(analysis.get("engine")) or _engine(data.get("analysisEngine"))
                       or _engine(engine_override) or _engine(data.get("engine")) or ENGINE_CODEX)
    # A lane saved for another engine keeps that engine's default model instead of a foreign id.
    return {
        "normal": _choice(normal_engine, normal.get("model") if _engine(normal.get("engine")) == normal_engine
                          else None, normal.get("effort"), catalog),
        "analysis": _choice(analysis_engine, analysis.get("model") if _engine(analysis.get("engine")) == analysis_engine
                            else None, analysis.get("effort"), catalog),
    }
