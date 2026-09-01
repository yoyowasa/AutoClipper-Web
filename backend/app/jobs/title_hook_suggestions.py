import json
import os
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.jobs.subtitle_review import (
    SubtitleReviewDocument,
    load_subtitle_review,
    subtitle_review_output_path,
)
from app.jobs.subtitle_review_preview import subtitle_review_document_lock
from app.models import Job, Video
from app.posting_metadata import (
    YouTubePostingProfile,
    YouTubeTitleCandidate,
    build_post_metadata_revision_hash,
    build_youtube_posting_copy,
    ensure_publication_title_suffix,
)
from app.scoring.codex_title_hook_suggestions import (
    CodexTitleHookSuggestionError,
    CodexTitleHookSuggestionGenerator,
)
from app.scoring.title_hook_suggestions import (
    TITLE_HOOK_PROMPT_VERSION,
    OpenAITitleHookSuggestionGenerator,
    TitleHookSuggestion,
    TitleHookSuggestionResult,
    extract_representative_frames,
    normalize_title_hook_suggestions,
)
from app.storage.paths import StoragePaths, get_storage_paths


TITLE_HOOK_SUGGESTIONS_DIRNAME = "title_hook_suggestions"
TITLE_HOOK_GENERATION_CANCELLED_ERROR = (
    "subtitle review is no longer awaiting title/hook suggestions"
)
TitleHookSuggestionState = Literal["queued", "generating", "ready", "failed"]


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat()


class TitleHookDraftSegment(BaseModel):
    segment_id: str = Field(alias="segmentId")
    text: str

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class TitleHookSuggestionInputSegment(BaseModel):
    segment_id: str = Field(alias="segmentId")
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    source_start: float = Field(ge=0, alias="sourceStart")
    source_end: float = Field(ge=0, alias="sourceEnd")
    text: str

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class TitleHookSuggestionInput(BaseModel):
    version: int = 1
    prompt_version: str = Field(alias="promptVersion")
    job_id: str = Field(alias="jobId")
    clip_id: str = Field(alias="clipId")
    clip_type: Literal["normal", "short"] = Field(alias="clipType")
    clip_start: float = Field(ge=0, alias="clipStart")
    clip_end: float = Field(gt=0, alias="clipEnd")
    clip_duration: float = Field(gt=0, alias="clipDuration")
    input_hash: str = Field(min_length=64, max_length=64, alias="inputHash")
    draft_hash: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        alias="draftHash",
    )
    revision_hash: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        alias="revisionHash",
    )
    provider: Literal["codex", "openai"] = "openai"
    model: str = Field(min_length=1)
    segments: list[TitleHookSuggestionInputSegment] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    def prompt_payload(self) -> dict[str, Any]:
        return {
            "clipType": self.clip_type,
            "clipDurationSeconds": self.clip_duration,
            "timestampSemantics": "clip_relative_seconds",
            "subtitleStatus": "available" if any(item.text.strip() for item in self.segments) else "unavailable",
            "segments": [
                {
                    "segmentId": item.segment_id,
                    "start": item.start,
                    "end": item.end,
                    "text": item.text,
                }
                for item in self.segments
            ],
        }


class TitleHookSuggestionsDocument(BaseModel):
    clip_id: str = Field(alias="clipId")
    state: TitleHookSuggestionState
    input_hash: str = Field(min_length=64, max_length=64, alias="inputHash")
    draft_hash: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        alias="draftHash",
    )
    revision_hash: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        alias="revisionHash",
    )
    provider: Literal["codex", "openai"] = "openai"
    thread_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        alias="threadId",
    )
    model: str
    suggestions: list[TitleHookSuggestion] = Field(default_factory=list)
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
    error: str | None = None
    generated_at: str | None = Field(default=None, alias="generatedAt")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


def _clip_digest(clip_id: str) -> str:
    return sha256(clip_id.encode("utf-8")).hexdigest()[:24]


def title_hook_suggestions_path(output_dir: str | Path, clip_id: str) -> Path:
    return Path(output_dir) / TITLE_HOOK_SUGGESTIONS_DIRNAME / f"{_clip_digest(clip_id)}.json"


def title_hook_suggestion_input_path(output_dir: str | Path, clip_id: str) -> Path:
    return Path(output_dir) / TITLE_HOOK_SUGGESTIONS_DIRNAME / f"{_clip_digest(clip_id)}.input.json"


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.{uuid4().hex}.tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
    return path


def write_title_hook_suggestions(
    document: TitleHookSuggestionsDocument,
    path: str | Path,
) -> Path:
    return _write_json_atomic(
        Path(path),
        document.model_dump(by_alias=True, mode="json"),
    )


def load_title_hook_suggestions(path: str | Path) -> TitleHookSuggestionsDocument:
    return TitleHookSuggestionsDocument.model_validate_json(Path(path).read_text(encoding="utf-8"))


def write_title_hook_suggestion_input(
    request: TitleHookSuggestionInput,
    path: str | Path,
) -> Path:
    return _write_json_atomic(
        Path(path),
        request.model_dump(by_alias=True, mode="json"),
    )


def load_title_hook_suggestion_input(path: str | Path) -> TitleHookSuggestionInput:
    return TitleHookSuggestionInput.model_validate_json(Path(path).read_text(encoding="utf-8"))


def build_title_hook_suggestion_input(
    document: SubtitleReviewDocument,
    clip_id: str,
    drafts: Sequence[TitleHookDraftSegment],
    *,
    model: str,
    provider: Literal["codex", "openai"] = "codex",
) -> TitleHookSuggestionInput:
    clip = next((item for item in document.clips if item.id == clip_id), None)
    if clip is None:
        raise KeyError(clip_id)
    allowed_ids = set(clip.segment_ids)
    requested_ids = [draft.segment_id for draft in drafts]
    if len(requested_ids) != len(set(requested_ids)):
        raise ValueError("duplicate subtitle segment update")
    if set(requested_ids) - allowed_ids:
        raise ValueError("subtitle segment does not belong to the selected clip")
    if set(requested_ids) != allowed_ids:
        raise ValueError("all subtitle segments for the selected clip are required")
    stored_by_id = {segment.id: segment for segment in document.segments}
    draft_by_id = {draft.segment_id: draft for draft in drafts}
    missing_ids = [segment_id for segment_id in requested_ids if segment_id not in stored_by_id]
    if missing_ids:
        raise KeyError(missing_ids[0])

    input_segments: list[TitleHookSuggestionInputSegment] = []
    for segment_id in sorted(requested_ids, key=lambda item: stored_by_id[item].index):
        stored = stored_by_id[segment_id]
        relative_start = min(clip.duration, max(0.0, stored.start - clip.start))
        relative_end = min(clip.duration, max(relative_start, stored.end - clip.start))
        input_segments.append(
            TitleHookSuggestionInputSegment(
                segmentId=segment_id,
                start=round(relative_start, 3),
                end=round(relative_end, 3),
                sourceStart=round(stored.start, 3),
                sourceEnd=round(stored.end, 3),
                text=draft_by_id[segment_id].text.strip(),
            )
        )

    normalized_model = model.strip() or "gpt-5.5"
    revision_hash = build_post_metadata_revision_hash(
        clip_id=clip.id,
        clip_type=clip.type,
        start=clip.start,
        end=clip.end,
        segments=input_segments,
    )
    hash_payload = {
        "promptVersion": TITLE_HOOK_PROMPT_VERSION,
        "provider": provider,
        "model": normalized_model,
        "revisionHash": revision_hash,
    }
    encoded = json.dumps(
        hash_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    input_hash = sha256(encoded.encode("utf-8")).hexdigest()
    ordered_segment_ids = [item.segment_id for item in input_segments]
    draft_payload = [
        {"segmentId": segment_id, "text": draft_by_id[segment_id].text}
        for segment_id in ordered_segment_ids
    ]
    draft_hash = sha256(
        json.dumps(
            draft_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return TitleHookSuggestionInput(
        promptVersion=TITLE_HOOK_PROMPT_VERSION,
        jobId=document.job_id,
        clipId=clip.id,
        clipType=clip.type,
        clipStart=clip.start,
        clipEnd=clip.end,
        clipDuration=clip.duration,
        inputHash=input_hash,
        draftHash=draft_hash,
        revisionHash=revision_hash,
        provider=provider,
        model=normalized_model,
        segments=input_segments,
    )


def queued_title_hook_suggestions(
    request: TitleHookSuggestionInput,
    *,
    thread_id: str | None = None,
) -> TitleHookSuggestionsDocument:
    return TitleHookSuggestionsDocument(
        clipId=request.clip_id,
        state="queued",
        inputHash=request.input_hash,
        draftHash=request.draft_hash,
        revisionHash=request.revision_hash,
        provider=request.provider,
        threadId=thread_id,
        model=request.model,
    )


def failed_title_hook_suggestions(
    request: TitleHookSuggestionInput,
    error: str,
) -> TitleHookSuggestionsDocument:
    return TitleHookSuggestionsDocument(
        clipId=request.clip_id,
        state="failed",
        inputHash=request.input_hash,
        draftHash=request.draft_hash,
        revisionHash=request.revision_hash,
        provider=request.provider,
        model=request.model,
        error=error,
        generatedAt=_utc_iso(),
    )


def openai_api_key_is_configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


class TitleHookSuggestionGeneratorProtocol(Protocol):
    def generate(
        self,
        payload: dict[str, Any],
        frame_paths: Sequence[Path],
    ) -> TitleHookSuggestionResult:
        pass


FrameExtractor = Callable[..., list[Path]]
SessionFactory = Callable[[], Session]


def _safe_generation_error(exc: Exception) -> str:
    if isinstance(exc, CodexTitleHookSuggestionError):
        return f"title/hook generation failed ({exc.code})"
    if isinstance(exc, RuntimeError) and str(exc) == "OPENAI_API_KEY is not configured":
        return str(exc)
    return f"title/hook generation failed ({exc.__class__.__name__})"


def _generation_context_is_active(
    session_factory: SessionFactory,
    job_id: str,
    review_path: Path,
) -> bool:
    try:
        with session_factory() as db:
            job = db.get(Job, job_id)
            if job is None or job.status != "awaiting_subtitle_review":
                return False
        if not review_path.is_file():
            return False
        return load_subtitle_review(review_path).state == "awaiting_review"
    except Exception:
        return False


def _cancelled_title_hook_suggestions(
    request: TitleHookSuggestionInput,
) -> TitleHookSuggestionsDocument:
    return failed_title_hook_suggestions(
        request,
        TITLE_HOOK_GENERATION_CANCELLED_ERROR,
    )


def _validate_suggestion_evidence(
    result: TitleHookSuggestionResult,
    request: TitleHookSuggestionInput,
) -> None:
    allowed_ids = {item.segment_id for item in request.segments}
    referenced_ids = set(result.description_evidence_segment_ids)
    for suggestion in result.suggestions:
        referenced_ids.update(suggestion.evidence_segment_ids)
    unknown_ids = referenced_ids - allowed_ids
    if unknown_ids:
        raise ValueError("title/hook suggestion referenced an unknown subtitle segment")


def _same_generation_context(
    state: TitleHookSuggestionsDocument,
    request: TitleHookSuggestionInput,
) -> bool:
    return (
        state.draft_hash == request.draft_hash
        and state.revision_hash == request.revision_hash
        and state.provider == request.provider
    )


def generate_title_hook_suggestions_for_auto(
    *,
    document: SubtitleReviewDocument,
    clip_id: str,
    source_path: str | Path,
    paths: StoragePaths,
    model: str,
    generator: TitleHookSuggestionGeneratorProtocol | None = None,
    frame_extractor: FrameExtractor = extract_representative_frames,
) -> TitleHookSuggestionsDocument:
    """Generate a current Codex proposal without requiring an active review stop.

    The automatic pipeline calls this before the subtitle-review document is first
    published.  It deliberately has no OpenAI fallback: an unavailable host bridge
    raises and the caller routes the job to human review.
    """

    clip = next((item for item in document.clips if item.id == clip_id), None)
    if clip is None:
        raise KeyError(clip_id)
    segments_by_id = {segment.id: segment for segment in document.segments}
    request = build_title_hook_suggestion_input(
        document,
        clip_id,
        [
            TitleHookDraftSegment(
                segmentId=segment_id,
                text=segments_by_id[segment_id].text,
            )
            for segment_id in clip.segment_ids
        ],
        model=model,
        provider="codex",
    )
    job_dir = paths.job_outputs(document.job_id)
    state_path = title_hook_suggestions_path(job_dir, clip_id)
    input_path = title_hook_suggestion_input_path(job_dir, clip_id)
    previous_thread_id: str | None = None
    if state_path.is_file():
        try:
            cached = load_title_hook_suggestions(state_path)
        except (OSError, ValueError, json.JSONDecodeError):
            cached = None
        if cached is not None:
            previous_thread_id = cached.thread_id
            if (
                cached.state == "ready"
                and cached.input_hash == request.input_hash
                and cached.draft_hash == request.draft_hash
                and cached.revision_hash == request.revision_hash
                and cached.provider == "codex"
            ):
                return cached

    active_generator = generator or CodexTitleHookSuggestionGenerator(
        storage_root=paths.root,
        job_id=document.job_id,
        clip_id=clip_id,
        model=request.model,
        thread_id=previous_thread_id,
    )
    temp_root = paths.temp / document.job_id / TITLE_HOOK_SUGGESTIONS_DIRNAME
    temp_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f"{_clip_digest(clip_id)}-", dir=temp_root) as temporary_dir:
        try:
            frame_paths = frame_extractor(
                source_path,
                clip_start=request.clip_start,
                clip_end=request.clip_end,
                output_dir=Path(temporary_dir),
            )
        except Exception:
            frame_paths = []
        if not frame_paths and not any(item.text.strip() for item in request.segments):
            raise ValueError(
                "title/hook generation requires subtitles or representative frames"
            )
        result = active_generator.generate(request.prompt_payload(), frame_paths)

    _validate_suggestion_evidence(result, request)
    suggestions = normalize_title_hook_suggestions(
        result,
        clip_duration=request.clip_duration,
        clip_type=request.clip_type,
    )
    recommended_index = next(
        (
            index
            for index, suggestion in enumerate(result.suggestions)
            if suggestion.id == result.recommended_suggestion_id
        ),
        0,
    )
    recommended_id = suggestions[recommended_index].id
    artifact = TitleHookSuggestionsDocument(
        clipId=clip_id,
        state="ready",
        inputHash=request.input_hash,
        draftHash=request.draft_hash,
        revisionHash=request.revision_hash,
        provider="codex",
        threadId=getattr(active_generator, "last_thread_id", previous_thread_id),
        model=request.model,
        suggestions=suggestions,
        recommendedSuggestionId=recommended_id,
        youtubeDescription=result.youtube_description,
        hashtags=result.hashtags,
        descriptionEvidenceSegmentIds=result.description_evidence_segment_ids,
        generatedAt=_utc_iso(),
    )
    write_title_hook_suggestion_input(request, input_path)
    write_title_hook_suggestions(artifact, state_path)
    return artifact


def apply_recommended_title_hook_suggestions(
    document: SubtitleReviewDocument,
    artifact: TitleHookSuggestionsDocument,
    *,
    youtube_source_title: str = "",
    youtube_source_url: str = "",
    youtube_posting_profile: YouTubePostingProfile | dict[str, Any] | None = None,
) -> SubtitleReviewDocument:
    """Apply the generated recommendation while preserving its evidence contract."""

    if artifact.state != "ready" or not artifact.revision_hash:
        raise ValueError("title/hook suggestions are not ready")
    clip = next((item for item in document.clips if item.id == artifact.clip_id), None)
    if clip is None:
        raise KeyError(artifact.clip_id)
    recommended = next(
        (
            item
            for item in artifact.suggestions
            if item.id == artifact.recommended_suggestion_id
        ),
        None,
    )
    if recommended is None:
        raise ValueError("recommended title/hook suggestion is unavailable")

    if clip.original_title is None:
        clip.original_title = clip.title
    clip.title = recommended.overlay_title
    clip.publication_title = ensure_publication_title_suffix(
        recommended.publication_title,
        clip_type=clip.type,
    )
    clip.title_edited = True
    clip.hook_text = recommended.hook_text
    clip.hook_duration_seconds = recommended.hook_duration_seconds
    clip.hook_scene_start = (
        None
        if recommended.hook_scene_start is None
        else round(clip.start + recommended.hook_scene_start, 3)
    )
    clip.hook_scene_end = (
        None
        if recommended.hook_scene_end is None
        else round(clip.start + recommended.hook_scene_end, 3)
    )
    clip.thumbnail_kicker = recommended.thumbnail_kicker
    clip.thumbnail_line1 = recommended.thumbnail_line1
    clip.thumbnail_line2 = recommended.thumbnail_line2
    clip.thumbnail_frame_seconds = recommended.thumbnail_frame_seconds
    clip.title_candidates = [
        YouTubeTitleCandidate(
            id=item.id,
            title=ensure_publication_title_suffix(
                item.publication_title,
                clip_type=clip.type,
            ),
            intent=item.intent,
            reason=item.reason,
            evidenceSegmentIds=item.evidence_segment_ids,
        )
        for item in artifact.suggestions
        if item.intent is not None
    ]
    clip.recommended_title_id = recommended.id
    clip.selected_title_id = recommended.id
    posting_copy = build_youtube_posting_copy(
        clip_type=clip.type,
        source_title=youtube_source_title,
        source_url=youtube_source_url,
        profile=youtube_posting_profile,
        fallback_description=artifact.youtube_description,
        topic_hashtags=artifact.hashtags,
    )
    clip.youtube_description = posting_copy.description
    clip.youtube_hashtags = posting_copy.hashtags
    clip.youtube_tags = posting_copy.tags
    clip.description_evidence_segment_ids = list(
        artifact.description_evidence_segment_ids
    )
    clip.post_metadata_source = "codex"
    clip.post_metadata_revision_hash = artifact.revision_hash
    return document


def run_title_hook_suggestion_generation(
    job_id: str,
    clip_id: str,
    input_hash: str,
    session_factory: SessionFactory = SessionLocal,
    paths: StoragePaths | None = None,
    generator: TitleHookSuggestionGeneratorProtocol | None = None,
    frame_extractor: FrameExtractor = extract_representative_frames,
) -> list[str]:
    storage_paths = paths or get_storage_paths()
    job_dir = storage_paths.job_outputs(job_id)
    state_path = title_hook_suggestions_path(job_dir, clip_id)
    input_request_path = title_hook_suggestion_input_path(job_dir, clip_id)
    review_path = subtitle_review_output_path(job_dir)

    with subtitle_review_document_lock(job_dir):
        if not state_path.is_file() or not input_request_path.is_file():
            return ["superseded"]
        state = load_title_hook_suggestions(state_path)
        request = load_title_hook_suggestion_input(input_request_path)
        if (
            state.state not in {"queued", "generating"}
            or state.input_hash != input_hash
            or request.input_hash != input_hash
            or not _same_generation_context(state, request)
        ):
            return ["superseded"]
        if not _generation_context_is_active(session_factory, job_id, review_path):
            write_title_hook_suggestions(
                _cancelled_title_hook_suggestions(request),
                state_path,
            )
            return ["cancelled"]
        generating = state.model_copy(
            update={
                "state": "generating",
                "suggestions": [],
                "recommended_suggestion_id": None,
                "youtube_description": "",
                "hashtags": [],
                "description_evidence_segment_ids": [],
                "error": None,
                "generated_at": None,
            }
        )
        write_title_hook_suggestions(generating, state_path)

    active_generator = generator
    generation_thread_id = state.thread_id
    try:
        with session_factory() as db:
            job = db.get(Job, job_id)
            if job is None:
                raise ValueError(f"job not found: {job_id}")
            video = db.get(Video, job.video_id)
            if video is None:
                raise ValueError(f"video not found for job: {job_id}")
            source_path = storage_paths.resolve_stored_file(video.stored_path)

        frame_paths: list[Path] = []
        temp_root = storage_paths.temp / job_id / TITLE_HOOK_SUGGESTIONS_DIRNAME
        temp_root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=f"{_clip_digest(clip_id)}-", dir=temp_root) as temporary_dir:
            try:
                frame_paths = frame_extractor(
                    source_path,
                    clip_start=request.clip_start,
                    clip_end=request.clip_end,
                    output_dir=Path(temporary_dir),
                )
            except Exception:
                frame_paths = []
            if not frame_paths and not any(item.text.strip() for item in request.segments):
                raise ValueError("title/hook generation requires subtitles or representative frames")
            with subtitle_review_document_lock(job_dir):
                if not state_path.is_file() or not input_request_path.is_file():
                    return ["superseded"]
                active_state = load_title_hook_suggestions(state_path)
                active_request = load_title_hook_suggestion_input(input_request_path)
                if (
                    active_state.state not in {"queued", "generating"}
                    or active_state.input_hash != input_hash
                    or active_request.input_hash != input_hash
                    or not _same_generation_context(active_state, active_request)
                ):
                    return ["superseded"]
                if not _generation_context_is_active(
                    session_factory,
                    job_id,
                    review_path,
                ):
                    write_title_hook_suggestions(
                        _cancelled_title_hook_suggestions(active_request),
                        state_path,
                    )
                    return ["cancelled"]
                request = active_request
                generation_thread_id = active_state.thread_id
            if active_generator is None and request.provider == "openai":
                if not openai_api_key_is_configured():
                    raise RuntimeError("OPENAI_API_KEY is not configured")
                active_generator = OpenAITitleHookSuggestionGenerator(model=request.model)
            if active_generator is None:
                active_generator = CodexTitleHookSuggestionGenerator(
                    storage_root=storage_paths.root,
                    job_id=job_id,
                    clip_id=clip_id,
                    model=request.model,
                    thread_id=generation_thread_id,
                )
            result = active_generator.generate(request.prompt_payload(), frame_paths)
            generation_thread_id = getattr(
                active_generator,
                "last_thread_id",
                generation_thread_id,
            )

        _validate_suggestion_evidence(result, request)
        suggestions = normalize_title_hook_suggestions(
            result,
            clip_duration=request.clip_duration,
            clip_type=request.clip_type,
        )
        recommended_index = next(
            (
                index
                for index, suggestion in enumerate(result.suggestions)
                if suggestion.id == result.recommended_suggestion_id
            ),
            0,
        )
        next_state = TitleHookSuggestionsDocument(
            clipId=clip_id,
            state="ready",
            inputHash=input_hash,
            draftHash=request.draft_hash,
            revisionHash=request.revision_hash,
            provider=request.provider,
            threadId=generation_thread_id,
            model=request.model,
            suggestions=suggestions,
            recommendedSuggestionId=suggestions[recommended_index].id,
            youtubeDescription=result.youtube_description,
            hashtags=result.hashtags,
            descriptionEvidenceSegmentIds=result.description_evidence_segment_ids,
            generatedAt=_utc_iso(),
        )
        result_state = "ready"
    except Exception as exc:
        if active_generator is not None:
            generation_thread_id = getattr(
                active_generator,
                "last_thread_id",
                generation_thread_id,
            )
        next_state = failed_title_hook_suggestions(
            request,
            _safe_generation_error(exc),
        ).model_copy(update={"thread_id": generation_thread_id})
        result_state = "failed"

    with subtitle_review_document_lock(job_dir):
        if not state_path.is_file():
            return ["superseded"]
        active_state = load_title_hook_suggestions(state_path)
        if not input_request_path.is_file():
            return ["superseded"]
        active_request = load_title_hook_suggestion_input(input_request_path)
        if (
            active_state.state not in {"queued", "generating"}
            or active_state.input_hash != input_hash
            or active_request.input_hash != input_hash
            or not _same_generation_context(active_state, active_request)
        ):
            return ["superseded"]
        if not _generation_context_is_active(session_factory, job_id, review_path):
            write_title_hook_suggestions(
                _cancelled_title_hook_suggestions(active_request),
                state_path,
            )
            return ["cancelled"]
        next_state = next_state.model_copy(
            update={
                "draft_hash": active_request.draft_hash,
                "revision_hash": active_request.revision_hash,
                "provider": active_request.provider,
            }
        )
        write_title_hook_suggestions(next_state, state_path)
    return [result_state]
