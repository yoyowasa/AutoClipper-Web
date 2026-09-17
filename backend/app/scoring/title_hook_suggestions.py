import base64
import json
import re
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.posting_metadata import NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX, PostTitleIntent, ensure_publication_title_suffix


TITLE_HOOK_PROMPT_VERSION = "title_hook_suggestions_v7"
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
与えられた選定済みclipの修正字幕と代表フレームだけを根拠に、投稿用セットを作成してください。

【作成の目的】
視聴者が公開タイトルとサムネイルを見て「この動画を見たい」と思う文言を作る。
動画の内容との一致は全案の必須条件。その条件を満たした案同士は、見たくなる強さで比較する。
動画内の事実を脚色せず、省略や組み合わせによって元の意味を変えない。
答え・理由・対象・結末を隠す、ギャップを出す、強い言葉や印象的な発言を使うことは積極的に行ってよい。
強い表現を無難な説明へ薄めない。意味を変えない短縮・言い換えも使う。
内容を漏れなく説明するのではなく、最も見たくなる見どころを切り出す。

【3案の作り方と選定】
- suggestionsは3案固定。既存形式に合わせてintentはfactual、engagement、conciseを1案ずつ使用する。
- intentにかかわらず、3案すべて内容に忠実で、短く、視聴者が見たくなる案にする。
  「事実だけの案」「興味だけの案」「短いだけの案」に分業しない。
- 動画にある見どころ、隠す情報、強く出す言葉、見せ方を変え、単なる言い換えではない3案を作る。
- 情報ギャップ、意外性・対比、強い言葉、発言・反応、知りたいことへの答えから、素材に合う切り口を選ぶ。
  疑問形や答えを隠す構成を、すべての案に強制しない。
- reasonには「視聴者が何に引っ掛かり、何を見たくなるか」を簡潔に書く。
- recommendedSuggestionId: 動画の内容と一致する3案のうち、最も見たくなる案のid。
  normalはpublicationTitleと通常サムネ文言の組み合わせで、shortはpublicationTitleを中心に評価する。
  説明の丁寧さや穏当さで選ばない。

【公開タイトルと通常サムネ】
- publicationTitle: YouTube公開用。字幕から確認できる人物・状況・出来事を使い、見る理由となる言葉をなるべく前に置く。
- 動画全体の要約で終わらせず、気になる発言・疑問・ギャップ・出来事・得られる理解のうち、最も強い見どころを軸にする。
- clipTypeがnormalならpublicationTitle末尾には入力のnormalTitleSuffixを付ける。空欄なら何も付けない。
- 未指定の人物名・所属を補わない。overlayTitleには末尾を付けない。
- clipTypeがnormalならthumbnailKicker、thumbnailLine1、thumbnailLine2に通常サムネ用の短い文言を書く。
  thumbnailKickerは話題をつかむ手掛かりとなる小見出し、thumbnailLine1とthumbnailLine2は最も気になる言葉を置く主見出し2行にする。
  主見出しは各行12文字以内を目安に短く自然にする。文字数の下限は設けず、短く成立する文言を引き延ばさない。
- normalの公開タイトルとサムネは別々に要約せず、組み合わせて見たときの「見たい」を作る。
  片方で気になる言葉を出し、もう片方で必要な文脈や別の引きを補う。
- 答えを隠す場合は、タイトルとサムネの組み合わせでも確認したくなる点を残す。何の話か分からないだけの文言にはしない。
- clipTypeがnormalならthumbnailFrameSecondsに、人物の表情と内容が最も伝わる場面をclip先頭からの相対秒で指定する。
- clipTypeがshortならthumbnailKicker、thumbnailLine1、thumbnailLine2は空文字、thumbnailFrameSecondsはnullにする。
  ショートは完成動画のフック場面を別処理で切り出す。

【動画内タイトルとフック】
- overlayTitle: 動画内表示用。最大2行を想定し、短く読みやすくする。
- hookText: 冒頭から興味を引く短い文。publicationTitleの丸写しにしない。
- hookSceneStart / hookSceneEnd: clip先頭を0秒とする相対秒。1.5〜3.0秒でclip内に収める。
根拠のあるフックを作れない案はhookTextを空文字、hookSceneStartとhookSceneEndをnullにしてください。
挨拶、宣伝、長い前置きを優先しないでください。

【説明文とハッシュタグ】
- youtubeDescription: clip内容の説明本文だけを書く。未提供の元動画URL、人物名、数値、固有名詞を創作しない。
- clipTypeがnormalなら、冒頭に内容を具体的にまとめた2〜4文を書く。
- normalの要約後は空行を入れ、clip相対時刻による4〜8件のチャプターを「00:00 見どころ」の形式で付ける。最初は必ず00:00にする。
- clipTypeがshortなら、結末まで分かる具体的な1〜2文だけを書き、チャプターは付けない。
- 元配信、出演、ハッシュタグ、タグは別処理で追加するためyoutubeDescriptionへ書かない。
- hashtags: 字幕から根拠を持てる3〜5個。#から始め、空白を含めない。
- descriptionEvidenceSegmentIds: 説明欄を直接裏付けるsegmentId。

【根拠と出力】
- evidenceSegmentIds: その案を直接裏付ける入力字幕のsegmentIdだけを返す。
画像と字幕が矛盾する場合は字幕を優先します。
指定されたJSON schemaだけを返してください。"""

class TitleHookSuggestion(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    publication_title: str = Field(min_length=1, max_length=100, alias="publicationTitle")
    overlay_title: str = Field(min_length=1, max_length=80, alias="overlayTitle")
    hook_text: str = Field(max_length=120, alias="hookText")
    hook_duration_seconds: float = Field(ge=1.5, le=3.0, alias="hookDurationSeconds")
    hook_scene_start: float | None = Field(ge=0, alias="hookSceneStart")
    hook_scene_end: float | None = Field(gt=0, alias="hookSceneEnd")
    thumbnail_kicker: str = Field(default="", max_length=40, alias="thumbnailKicker")
    thumbnail_line1: str = Field(default="", max_length=60, alias="thumbnailLine1")
    thumbnail_line2: str = Field(default="", max_length=60, alias="thumbnailLine2")
    thumbnail_frame_seconds: float | None = Field(
        default=None,
        ge=0,
        alias="thumbnailFrameSeconds",
    )
    reason: str = Field(min_length=1, max_length=300)
    intent: PostTitleIntent | None = None
    evidence_segment_ids: list[str] = Field(
        default_factory=list,
        max_length=64,
        alias="evidenceSegmentIds",
    )

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
    recommended_suggestion_id: str | None = Field(
        default=None,
        alias="recommendedSuggestionId",
    )
    youtube_description: str = Field(
        default="",
        max_length=2000,
        alias="youtubeDescription",
    )
    hashtags: list[str] = Field(default_factory=list, max_length=5)
    description_evidence_segment_ids: list[str] = Field(
        default_factory=list,
        max_length=64,
        alias="descriptionEvidenceSegmentIds",
    )

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    @model_validator(mode="after")
    def normalize_legacy_contract(self) -> "TitleHookSuggestionResult":
        suggestion_ids = [item.id for item in self.suggestions]
        if len(suggestion_ids) != len(set(suggestion_ids)):
            raise ValueError("suggestion IDs must be unique")
        intents: tuple[PostTitleIntent, ...] = ("factual", "engagement", "concise")
        for index, suggestion in enumerate(self.suggestions):
            if suggestion.intent is None:
                suggestion.intent = intents[index]
        if {item.intent for item in self.suggestions} != set(intents):
            raise ValueError("suggestion intents must contain factual, engagement, and concise")
        if self.recommended_suggestion_id is None:
            self.recommended_suggestion_id = self.suggestions[0].id
        if self.recommended_suggestion_id not in suggestion_ids:
            raise ValueError("recommended suggestion ID is unknown")
        if len(self.hashtags) != len(set(self.hashtags)):
            raise ValueError("hashtags must be unique")
        if len(self.description_evidence_segment_ids) != len(
            set(self.description_evidence_segment_ids)
        ):
            raise ValueError("description evidence segment IDs must be unique")
        for suggestion in self.suggestions:
            if len(suggestion.evidence_segment_ids) != len(
                set(suggestion.evidence_segment_ids)
            ):
                raise ValueError("suggestion evidence segment IDs must be unique")
        return self


class GeneratedTitleHookSuggestion(TitleHookSuggestion):
    intent: PostTitleIntent
    evidence_segment_ids: list[str] = Field(
        max_length=64,
        alias="evidenceSegmentIds",
    )


class GeneratedTitleHookSuggestionResult(BaseModel):
    suggestions: list[GeneratedTitleHookSuggestion] = Field(min_length=3, max_length=3)
    recommended_suggestion_id: str = Field(
        min_length=1,
        max_length=40,
        alias="recommendedSuggestionId",
    )
    youtube_description: str = Field(
        min_length=1,
        max_length=2000,
        alias="youtubeDescription",
    )
    hashtags: list[str] = Field(min_length=3, max_length=5)
    description_evidence_segment_ids: list[str] = Field(
        max_length=64,
        alias="descriptionEvidenceSegmentIds",
    )

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    @model_validator(mode="after")
    def validate_generated_contract(self) -> "GeneratedTitleHookSuggestionResult":
        compatible = TitleHookSuggestionResult.model_validate(
            self.model_dump(by_alias=True, mode="json")
        )
        if any(
            not value.startswith("#") or any(char.isspace() for char in value)
            for value in self.hashtags
        ):
            raise ValueError("hashtags must start with # and contain no whitespace")
        if not compatible.youtube_description:
            raise ValueError("youtube description must not be empty")
        return self

    def to_compatible(self) -> TitleHookSuggestionResult:
        return TitleHookSuggestionResult.model_validate(
            self.model_dump(by_alias=True, mode="json")
        )


TITLE_HOOK_GENERATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "minLength": 1, "maxLength": 40},
                    "intent": {
                        "type": "string",
                        "enum": ["factual", "engagement", "concise"],
                    },
                    "publicationTitle": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 100,
                    },
                    "overlayTitle": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 80,
                    },
                    "hookText": {"type": "string", "maxLength": 120},
                    "hookDurationSeconds": {
                        "type": "number",
                        "minimum": 1.5,
                        "maximum": 3.0,
                    },
                    "hookSceneStart": {
                        "anyOf": [
                            {"type": "number", "minimum": 0},
                            {"type": "null"},
                        ]
                    },
                    "hookSceneEnd": {
                        "anyOf": [
                            {"type": "number", "exclusiveMinimum": 0},
                            {"type": "null"},
                        ]
                    },
                    "thumbnailKicker": {"type": "string", "maxLength": 40},
                    "thumbnailLine1": {"type": "string", "maxLength": 60},
                    "thumbnailLine2": {"type": "string", "maxLength": 60},
                    "thumbnailFrameSeconds": {
                        "anyOf": [
                            {"type": "number", "minimum": 0},
                            {"type": "null"},
                        ]
                    },
                    "reason": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 300,
                    },
                    "evidenceSegmentIds": {
                        "type": "array",
                        "minItems": 0,
                        "maxItems": 64,
                        "items": {"type": "string", "minLength": 1, "maxLength": 128},
                    },
                },
                "required": [
                    "id",
                    "intent",
                    "publicationTitle",
                    "overlayTitle",
                    "hookText",
                    "hookDurationSeconds",
                    "hookSceneStart",
                    "hookSceneEnd",
                    "thumbnailKicker",
                    "thumbnailLine1",
                    "thumbnailLine2",
                    "thumbnailFrameSeconds",
                    "reason",
                    "evidenceSegmentIds",
                ],
                "additionalProperties": False,
            },
        },
        "recommendedSuggestionId": {
            "type": "string",
            "minLength": 1,
            "maxLength": 40,
        },
        "youtubeDescription": {
            "type": "string",
            "minLength": 1,
            "maxLength": 2000,
        },
        "hashtags": {
            "type": "array",
            "minItems": 3,
            "maxItems": 5,
            "items": {
                "type": "string",
                "minLength": 2,
                "maxLength": 40,
                "pattern": r"^#[^#\s]+$",
            },
        },
        "descriptionEvidenceSegmentIds": {
            "type": "array",
            "minItems": 0,
            "maxItems": 64,
            "items": {"type": "string", "minLength": 1, "maxLength": 128},
        },
    },
    "required": [
        "suggestions",
        "recommendedSuggestionId",
        "youtubeDescription",
        "hashtags",
        "descriptionEvidenceSegmentIds",
    ],
    "additionalProperties": False,
}


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
        "schema": TITLE_HOOK_GENERATION_SCHEMA,
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
                return GeneratedTitleHookSuggestionResult.model_validate_json(
                    _extract_response_text(response)
                ).to_compatible()
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
    clip_type: str = "short",
    suffix: str = NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX,
) -> list[TitleHookSuggestion]:
    normalized: list[TitleHookSuggestion] = []
    for index, suggestion in enumerate(result.suggestions, start=1):
        thumbnail_update = _normalized_thumbnail_fields(
            suggestion,
            clip_duration=clip_duration,
            clip_type=clip_type,
        )
        if suggestion.hook_scene_start is None or suggestion.hook_scene_end is None:
            normalized.append(
                suggestion.model_copy(
                    update={
                        "id": f"suggestion_{index}",
                        "publication_title": ensure_publication_title_suffix(
                            suggestion.publication_title,
                            clip_type=clip_type,
                            suffix=suffix,
                        ),
                        "hook_duration_seconds": round(
                            min(3.0, max(1.5, suggestion.hook_duration_seconds)),
                            3,
                        ),
                        **thumbnail_update,
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
                    "publication_title": ensure_publication_title_suffix(
                        suggestion.publication_title,
                        clip_type=clip_type,
                        suffix=suffix,
                    ),
                    "hook_duration_seconds": round(duration, 3),
                    "hook_scene_start": round(start, 3),
                    "hook_scene_end": round(end, 3),
                    **thumbnail_update,
                }
            )
        )
    return normalized


def _normalized_thumbnail_fields(
    suggestion: TitleHookSuggestion,
    *,
    clip_duration: float,
    clip_type: str,
) -> dict[str, str | float | None]:
    if clip_type != "normal":
        return {
            "thumbnail_kicker": "",
            "thumbnail_line1": "",
            "thumbnail_line2": "",
            "thumbnail_frame_seconds": None,
        }

    fallback_line1, fallback_line2 = _fallback_thumbnail_lines(suggestion.overlay_title)
    frame_seconds = suggestion.thumbnail_frame_seconds
    if frame_seconds is None:
        if suggestion.hook_scene_start is not None and suggestion.hook_scene_end is not None:
            frame_seconds = (suggestion.hook_scene_start + suggestion.hook_scene_end) / 2
        else:
            frame_seconds = clip_duration * 0.38
    frame_seconds = min(max(0.0, frame_seconds), clip_duration)
    return {
        "thumbnail_kicker": suggestion.thumbnail_kicker or "今回の見どころ",
        "thumbnail_line1": suggestion.thumbnail_line1 or fallback_line1,
        "thumbnail_line2": suggestion.thumbnail_line2 or fallback_line2,
        "thumbnail_frame_seconds": round(frame_seconds, 3),
    }


def _fallback_thumbnail_lines(title: str) -> tuple[str, str]:
    explicit_lines = [line.strip() for line in title.splitlines() if line.strip()]
    if len(explicit_lines) >= 2:
        return explicit_lines[0][:60], " ".join(explicit_lines[1:])[:60]
    normalized = " ".join(title.split()).strip()
    if len(normalized) <= 18:
        return normalized[:60], ""
    midpoint = len(normalized) // 2
    return normalized[:midpoint].rstrip()[:60], normalized[midpoint:].lstrip()[:60]
