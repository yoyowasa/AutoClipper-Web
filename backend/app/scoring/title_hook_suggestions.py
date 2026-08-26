import base64
import json
import re
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


TITLE_HOOK_PROMPT_VERSION = "title_hook_suggestions_v1"
REPRESENTATIVE_FRAME_RATIOS = (0.12, 0.38, 0.62, 0.88)
TRANSIENT_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
TRANSIENT_ERROR_NAMES = {
    "APIConnectionError",
    "APITimeoutError",
    "InternalServerError",
    "RateLimitError",
}
OPENAI_REQUEST_TIMEOUT_SECONDS = 120.0

SYSTEM_PROMPT = """あなたは日本語動画の編集者です。
与えられた選定済みclipの修正字幕と代表フレームだけを根拠に、次の3案を作成してください。
- publicationTitle: 公開ページ用。人物・状況・出来事が分かる、事実に基づくタイトル。
- overlayTitle: 動画内表示用。短く、読みやすく、publicationTitleの丸写しにしない。
- hookText: 冒頭0〜0.3秒から興味を引く短い文。字幕にない事実や人物名を創作しない。
- hookSceneStart / hookSceneEnd: clip先頭を0秒とする相対秒。1.5〜3.0秒で、clipの範囲内。
根拠のあるフックを作れない案はhookTextを空文字、hookSceneStartとhookSceneEndをnullにしてください。
3案は表現だけでなく着眼点も変えてください。挨拶、宣伝、長い前置きを優先しないでください。
画像と字幕が矛盾する場合は字幕の発言内容を優先し、不明な固有名詞を推測しないでください。
指定されたJSON schemaだけを返してください。"""


class TitleHookSuggestion(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    publication_title: str = Field(min_length=1, max_length=100, alias="publicationTitle")
    overlay_title: str = Field(min_length=1, max_length=80, alias="overlayTitle")
    hook_text: str = Field(max_length=120, alias="hookText")
    hook_duration_seconds: float = Field(ge=1.5, le=3.0, alias="hookDurationSeconds")
    hook_scene_start: float | None = Field(ge=0, alias="hookSceneStart")
    hook_scene_end: float | None = Field(gt=0, alias="hookSceneEnd")
    reason: str = Field(min_length=1, max_length=300)

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    @model_validator(mode="after")
    def validate_scene_order(self) -> "TitleHookSuggestion":
        if (self.hook_scene_start is None) != (self.hook_scene_end is None):
            raise ValueError("hook scene requires both start and end")
        if self.hook_scene_start is None or self.hook_scene_end is None:
            if self.hook_text:
                raise ValueError("hook text must be empty when hook scene is not set")
            return self
        if self.hook_scene_end <= self.hook_scene_start:
            raise ValueError("hook scene end must be greater than start")
        return self


class TitleHookSuggestionResult(BaseModel):
    suggestions: list[TitleHookSuggestion] = Field(min_length=3, max_length=3)

    model_config = ConfigDict(extra="forbid")


class OpenAIResponsesResource(Protocol):
    def create(self, **kwargs: Any) -> Any:
        pass


class OpenAIClientProtocol(Protocol):
    responses: OpenAIResponsesResource


def title_hook_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "title_hook_suggestions",
        "strict": True,
        "schema": TitleHookSuggestionResult.model_json_schema(by_alias=True),
    }


def _extract_response_text(response: Any) -> str:
    output_parsed = getattr(response, "output_parsed", None)
    if output_parsed is not None:
        return json.dumps(output_parsed, ensure_ascii=False)

    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text)

    if isinstance(response, dict):
        if response.get("output_text"):
            return str(response["output_text"])
        if response.get("output_parsed") is not None:
            return json.dumps(response["output_parsed"], ensure_ascii=False)
        output = response.get("output", [])
    else:
        output = getattr(response, "output", [])

    for item in output or []:
        content = item.get("content", []) if isinstance(item, dict) else getattr(item, "content", [])
        for content_item in content or []:
            text = content_item.get("text") if isinstance(content_item, dict) else getattr(content_item, "text", None)
            if text:
                return str(text)
    raise ValueError("OpenAI response did not include output text")


def _load_default_client() -> OpenAIClientProtocol:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai package is not installed") from exc
    return OpenAI(max_retries=0, timeout=OPENAI_REQUEST_TIMEOUT_SECONDS)


def _image_content(path: Path) -> dict[str, str]:
    suffix = path.suffix.lower()
    media_type = "image/png" if suffix == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "input_image",
        "image_url": f"data:{media_type};base64,{encoded}",
    }


def _frame_relative_seconds(
    path: Path,
    *,
    clip_duration: float,
    fallback_index: int,
    frame_count: int,
) -> float:
    match = re.fullmatch(r"frame_(\d+)", path.stem)
    if match is not None:
        frame_index = int(match.group(1)) - 1
        if 0 <= frame_index < len(REPRESENTATIVE_FRAME_RATIOS):
            return clip_duration * REPRESENTATIVE_FRAME_RATIOS[frame_index]
    return clip_duration * (fallback_index / (frame_count + 1))


class OpenAITitleHookSuggestionGenerator:
    def __init__(
        self,
        *,
        model: str = "gpt-5.5",
        client: OpenAIClientProtocol | None = None,
        max_retries: int = 3,
        retry_backoff_seconds: float = 0.25,
        sleep_func: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model
        self._client = client
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.sleep_func = sleep_func

    @property
    def client(self) -> OpenAIClientProtocol:
        if self._client is None:
            self._client = _load_default_client()
        return self._client

    def generate(
        self,
        payload: dict[str, Any],
        frame_paths: Sequence[Path],
    ) -> TitleHookSuggestionResult:
        user_content: list[dict[str, str]] = [
            {
                "type": "input_text",
                "text": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            }
        ]
        clip_duration = max(0.0, float(payload.get("clipDurationSeconds") or 0.0))
        for index, path in enumerate(frame_paths, start=1):
            relative_seconds = _frame_relative_seconds(
                path,
                clip_duration=clip_duration,
                fallback_index=index,
                frame_count=len(frame_paths),
            )
            user_content.append(
                {
                    "type": "input_text",
                    "text": f"次の代表フレームはclip相対{relative_seconds:.3f}秒です。",
                }
            )
            user_content.append(_image_content(path))
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.responses.create(
                    model=self.model,
                    input=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    text={"format": title_hook_response_format()},
                    store=False,
                )
                return TitleHookSuggestionResult.model_validate_json(
                    _extract_response_text(response)
                )
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                retryable = (
                    status_code in TRANSIENT_STATUS_CODES
                    or exc.__class__.__name__ in TRANSIENT_ERROR_NAMES
                )
                if not retryable or attempt >= self.max_retries:
                    raise
                self.sleep_func(self.retry_backoff_seconds * (2**attempt))
        raise RuntimeError("unreachable title/hook retry state")


FrameCommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def extract_representative_frames(
    input_path: str | Path,
    *,
    clip_start: float,
    clip_end: float,
    output_dir: str | Path,
    ffmpeg_bin: str = "ffmpeg",
    runner: FrameCommandRunner = subprocess.run,
) -> list[Path]:
    duration = clip_end - clip_start
    if duration <= 0:
        raise ValueError("clip end must be greater than start")
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    frames: list[Path] = []
    for index, ratio in enumerate(REPRESENTATIVE_FRAME_RATIOS, start=1):
        timestamp = clip_start + min(max(duration * ratio, 0.0), max(duration - 0.05, 0.0))
        output_path = destination / f"frame_{index}.jpg"
        try:
            runner(
                [
                    ffmpeg_bin,
                    "-y",
                    "-ss",
                    f"{timestamp:.3f}",
                    "-i",
                    str(input_path),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=960:-2:force_original_aspect_ratio=decrease",
                    "-q:v",
                    "3",
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception:
            continue
        if output_path.is_file() and output_path.stat().st_size > 0:
            frames.append(output_path)
    return frames


def normalize_title_hook_suggestions(
    result: TitleHookSuggestionResult,
    *,
    clip_duration: float,
) -> list[TitleHookSuggestion]:
    normalized: list[TitleHookSuggestion] = []
    for index, suggestion in enumerate(result.suggestions, start=1):
        if suggestion.hook_scene_start is None or suggestion.hook_scene_end is None:
            normalized.append(
                suggestion.model_copy(
                    update={
                        "id": f"suggestion_{index}",
                        "hook_duration_seconds": round(
                            min(3.0, max(1.5, suggestion.hook_duration_seconds)),
                            3,
                        ),
                    }
                )
            )
            continue
        if clip_duration < 1.5:
            raise ValueError("clip duration must be at least 1.5 seconds for a hook scene")
        requested_duration = suggestion.hook_scene_end - suggestion.hook_scene_start
        if requested_duration <= 0:
            requested_duration = suggestion.hook_duration_seconds
        duration = min(3.0, max(1.5, requested_duration), clip_duration)
        latest_start = max(0.0, clip_duration - duration)
        start = min(max(0.0, suggestion.hook_scene_start), latest_start)
        end = start + duration
        normalized.append(
            suggestion.model_copy(
                update={
                    "id": f"suggestion_{index}",
                    "hook_duration_seconds": round(duration, 3),
                    "hook_scene_start": round(start, 3),
                    "hook_scene_end": round(end, 3),
                }
            )
        )
    return normalized
