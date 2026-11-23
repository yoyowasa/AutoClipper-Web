"""Engine, model and reasoning effort per host-bridge lane, chosen on the top screen.

The choice is saved to storage/codex_bridge/engine.json; the host bridge re-reads it before every
request (launcher/bridge_engine_settings.py), so no restart is needed. Choices are limited to the
catalog the running bridge publishes in its status file, or to the built-in defaults without one.
"""
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.storage.json_io import write_json_atomic
from app.storage.paths import StoragePaths

Engine = Literal["codex", "claude"]
ENGINES: tuple[Engine, ...] = ("codex", "claude")
DEFAULT_MODELS = {"codex": "gpt-6.1-sol", "claude": "claude-opus-5-5"}
DEFAULT_EFFORT = "medium"
# Same values as launcher/bridge_engine_settings.py (a test keeps them equal).
CLAUDE_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-2")
CLAUDE_EFFORTS = ("low", "medium", "high", "xhigh", "max")
CODEX_FALLBACK_MODELS = ("gpt-6.1-sol",)
CODEX_FALLBACK_EFFORTS = ("low", "medium", "high", "xhigh", "max")
MODEL_ID = r"^[a-z0-9][a-z0-9.\-]{0,63}$"
EFFORT_ID = r"^[a-z]{2,10}$"
MAX_FILE_BYTES = 64 * 1024


class LaneSetting(BaseModel):
    model_config = ConfigDict(extra="forbid")
    engine: Engine
    model: str = Field(pattern=MODEL_ID)
    effort: str = Field(pattern=EFFORT_ID)


class EngineSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    normal: LaneSetting
    analysis: LaneSetting


class CatalogModel(BaseModel):
    id: str = Field(pattern=MODEL_ID)
    efforts: list[str] = Field(min_length=1, max_length=10)


class EngineCatalog(BaseModel):
    codex: list[CatalogModel] = Field(min_length=1, max_length=30)
    claude: list[CatalogModel] = Field(min_length=1, max_length=30)


class BridgeEngineRead(BaseModel):
    saved: EngineSettings
    active: EngineSettings | None
    catalog: EngineCatalog
    catalogSource: Literal["bridge", "builtin"]
    bridgeState: str | None


def builtin_catalog() -> EngineCatalog:
    return EngineCatalog(
        codex=[CatalogModel(id=model, efforts=list(CODEX_FALLBACK_EFFORTS)) for model in CODEX_FALLBACK_MODELS],
        claude=[CatalogModel(id=model, efforts=list(CLAUDE_EFFORTS)) for model in CLAUDE_MODELS],
    )


def _read_object(path: Path) -> dict:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def bridge_status(paths: StoragePaths) -> dict:
    return _read_object(paths.bridge_status)


def current_catalog(status: dict) -> tuple[EngineCatalog, Literal["bridge", "builtin"]]:
    try:
        return EngineCatalog.model_validate(status.get("engineCatalog")), "bridge"
    except ValidationError:
        return builtin_catalog(), "builtin"


def _choice(engine: Engine, model, effort, catalog: EngineCatalog) -> LaneSetting:
    models = {item.id: item.efforts for item in getattr(catalog, engine)}
    default_model = DEFAULT_MODELS[engine] if DEFAULT_MODELS[engine] in models else next(iter(models))
    chosen = model if isinstance(model, str) and model in models else default_model
    efforts = models[chosen]
    default_effort = DEFAULT_EFFORT if DEFAULT_EFFORT in efforts else efforts[0]
    return LaneSetting(engine=engine, model=chosen,
                       effort=effort if isinstance(effort, str) and effort in efforts else default_effort)


def _engine(value) -> Engine | None:
    engine = str(value or "").strip().lower()
    return engine if engine in ENGINES else None  # type: ignore[return-value]


def saved_settings(paths: StoragePaths, catalog: EngineCatalog | None = None) -> EngineSettings:
    """The saved choice, read the same way as the bridge (old {"engine", "analysisEngine"} files too)."""
    catalog = catalog or current_catalog(bridge_status(paths))[0]
    data = _read_object(paths.bridge_engine_settings)
    lanes = data.get("lanes") if isinstance(data.get("lanes"), dict) else {}
    normal = lanes.get("normal") if isinstance(lanes.get("normal"), dict) else {}
    analysis = lanes.get("analysis") if isinstance(lanes.get("analysis"), dict) else {}
    normal_engine = _engine(normal.get("engine")) or _engine(data.get("engine")) or "codex"
    analysis_engine = (_engine(analysis.get("engine")) or _engine(data.get("analysisEngine"))
                       or _engine(data.get("engine")) or "codex")
    return EngineSettings(
        normal=_choice(normal_engine, normal.get("model") if _engine(normal.get("engine")) == normal_engine else None,
                       normal.get("effort"), catalog),
        analysis=_choice(analysis_engine,
                         analysis.get("model") if _engine(analysis.get("engine")) == analysis_engine else None,
                         analysis.get("effort"), catalog),
    )


def active_settings(status: dict) -> EngineSettings | None:
    """What the running bridge reports it uses; None when it is not ready or reports no models."""
    if status.get("state") != "ready":
        return None
    try:
        return EngineSettings(
            normal=LaneSetting(engine=status.get("engine"), model=status.get("model"),
                               effort=status.get("reasoningEffort")),
            analysis=LaneSetting(engine=status.get("analysisEngine"), model=status.get("analysisModel"),
                                 effort=status.get("analysisReasoningEffort")),
        )
    except ValidationError:
        return None


def read_bridge_engine(paths: StoragePaths) -> BridgeEngineRead:
    status = bridge_status(paths)
    catalog, source = current_catalog(status)
    state = status.get("state")
    return BridgeEngineRead(saved=saved_settings(paths, catalog), active=active_settings(status), catalog=catalog,
                            catalogSource=source, bridgeState=state if isinstance(state, str) else None)


def unsupported_choice(settings: EngineSettings, catalog: EngineCatalog) -> str | None:
    for lane, label in (("normal", "通常の作業"), ("analysis", "自己分析")):
        choice: LaneSetting = getattr(settings, lane)
        efforts = {item.id: item.efforts for item in getattr(catalog, choice.engine)}.get(choice.model)
        if efforts is None:
            return f"{label}のモデル {choice.model} は {choice.engine} で選べません。"
        if choice.effort not in efforts:
            return f"{label}の深さ {choice.effort} は {choice.model} で選べません。"
    return None


def save_bridge_engine(paths: StoragePaths, settings: EngineSettings) -> None:
    # engine / analysisEngine keep an older bridge build on the same engines until it is restarted.
    write_json_atomic(paths.bridge_engine_settings, {
        "engine": settings.normal.engine,
        "analysisEngine": settings.analysis.engine,
        "lanes": settings.model_dump(mode="json"),
    })
