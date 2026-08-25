import hashlib
import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.audio.transcribe_faster_whisper import TranscriptSegment, transcript_output_path
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.jobs.subtitle_review import (
    SubtitleReviewDocument,
    apply_reviewed_clip_content,
    apply_reviewed_text,
)
from app.models import Job, Video
from app.render.render_exact_review_preview import (
    ExactPreviewPaths,
    LivePreviewPaths,
    build_live_subtitle_review_preview_spec,
    build_subtitle_review_preview_spec,
    exact_subtitle_review_preview_paths,
    live_subtitle_review_preview_paths,
    subtitle_review_preview_spec_hash,
)
from app.storage.paths import StoragePaths


SUBTITLE_REVIEW_DOCUMENT_LOCK_FILENAME = ".subtitle_review.lock"


@dataclass(frozen=True)
class SubtitleReviewPreviewInputs:
    candidate: Candidate
    candidate_index: int
    overlay_title_expected: bool
    transcript_segments: list[TranscriptSegment]
    settings: dict[str, object]
    source_fingerprint: str
    source_width: int | None
    source_height: int | None


def exact_subtitle_review_preview_is_ready(
    paths: ExactPreviewPaths,
    expected_spec_hash: str,
) -> bool:
    try:
        if not all(
            path.is_file() and path.stat().st_size > 0
            for path in (paths.video_path, paths.subtitle_path, paths.spec_path)
        ):
            return False
        spec_payload = json.loads(paths.spec_path.read_text(encoding="utf-8"))
        return (
            isinstance(spec_payload, dict)
            and subtitle_review_preview_spec_hash(spec_payload)
            == expected_spec_hash
        )
    except (json.JSONDecodeError, OSError, TypeError, UnicodeError, ValueError):
        return False


def live_subtitle_review_preview_is_ready(
    paths: LivePreviewPaths,
    expected_spec_hash: str,
) -> bool:
    try:
        if not all(
            path.is_file() and path.stat().st_size > 0
            for path in (paths.video_path, paths.spec_path)
        ):
            return False
        spec_payload = json.loads(paths.spec_path.read_text(encoding="utf-8"))
        return (
            isinstance(spec_payload, dict)
            and subtitle_review_preview_spec_hash(spec_payload)
            == expected_spec_hash
        )
    except (json.JSONDecodeError, OSError, TypeError, UnicodeError, ValueError):
        return False


def exact_subtitle_review_preview_error_path(
    output_dir: str | Path,
    clip_id: str,
    spec_hash: str,
) -> Path:
    paths = exact_subtitle_review_preview_paths(output_dir, clip_id, spec_hash)
    return paths.video_path.with_suffix(".error.json")


def cleanup_stale_subtitle_review_preview_artifacts(
    output_dir: str | Path,
    clip_id: str,
    current_spec_hash: str,
    *,
    retain_previous: int = 1,
) -> None:
    current_paths = exact_subtitle_review_preview_paths(
        output_dir,
        clip_id,
        current_spec_hash,
    )
    preview_dir = current_paths.video_path.parent
    if not preview_dir.is_dir():
        return
    current_key = current_paths.video_path.stem
    artifact_groups: dict[str, list[Path]] = {}
    try:
        children = list(preview_dir.iterdir())
    except OSError:
        return
    for path in children:
        if not path.is_file() or path.name.startswith("."):
            continue
        artifact_key = path.name.split(".", 1)[0].lower()
        if len(artifact_key) != 32 or any(
            character not in "0123456789abcdef" for character in artifact_key
        ):
            continue
        artifact_groups.setdefault(artifact_key, []).append(path)

    def latest_mtime_ns(artifact_key: str) -> int:
        values: list[int] = []
        for path in artifact_groups[artifact_key]:
            try:
                values.append(path.stat().st_mtime_ns)
            except OSError:
                continue
        return max(values, default=0)

    previous_keys = [key for key in artifact_groups if key != current_key]
    previous_keys.sort(key=latest_mtime_ns, reverse=True)
    retained_keys = {current_key, *previous_keys[: max(0, retain_previous)]}
    for artifact_key, artifact_paths in artifact_groups.items():
        if artifact_key in retained_keys:
            continue
        for path in artifact_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def cleanup_stale_live_subtitle_review_preview_artifacts(
    output_dir: str | Path,
    clip_id: str,
    current_spec_hash: str,
    *,
    retain_previous: int = 1,
) -> None:
    current_paths = live_subtitle_review_preview_paths(
        output_dir,
        clip_id,
        current_spec_hash,
    )
    preview_dir = current_paths.video_path.parent
    if not preview_dir.is_dir():
        return
    current_key = current_paths.video_path.stem
    artifact_groups: dict[str, list[Path]] = {}
    try:
        children = list(preview_dir.iterdir())
    except OSError:
        return
    for path in children:
        if not path.is_file() or path.name.startswith("."):
            continue
        artifact_key = path.name.split(".", 1)[0].lower()
        if len(artifact_key) != 32 or any(
            character not in "0123456789abcdef" for character in artifact_key
        ):
            continue
        artifact_groups.setdefault(artifact_key, []).append(path)

    def latest_mtime_ns(artifact_key: str) -> int:
        values: list[int] = []
        for path in artifact_groups[artifact_key]:
            try:
                values.append(path.stat().st_mtime_ns)
            except OSError:
                continue
        return max(values, default=0)

    previous_keys = [key for key in artifact_groups if key != current_key]
    previous_keys.sort(key=latest_mtime_ns, reverse=True)
    retained_keys = {current_key, *previous_keys[: max(0, retain_previous)]}
    for artifact_key, artifact_paths in artifact_groups.items():
        if artifact_key in retained_keys:
            continue
        for path in artifact_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def write_subtitle_review_preview_error(
    output_dir: str | Path,
    clip_id: str,
    spec_hash: str,
    message: str,
) -> Path:
    path = exact_subtitle_review_preview_error_path(
        output_dir,
        clip_id,
        spec_hash,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".error-{uuid4().hex[:12]}.tmp")
    temporary_path.write_text(
        json.dumps(
            {"specHash": spec_hash, "message": message[:2000]},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
    return path


def read_subtitle_review_preview_error(path: Path) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    message = payload.get("message") if isinstance(payload, dict) else None
    return message if isinstance(message, str) and message else None


@contextmanager
def subtitle_review_document_lock(
    output_dir: str | Path,
    *,
    timeout_seconds: float = 30.0,
    stale_seconds: float = 300.0,
) -> Iterator[None]:
    lock_path = Path(output_dir) / SUBTITLE_REVIEW_DOCUMENT_LOCK_FILENAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > stale_seconds:
                    lock_path.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError("timed out waiting for subtitle review document lock")
            time.sleep(0.02)
    try:
        os.write(descriptor, f"{os.getpid()}\n".encode("ascii"))
        yield
    finally:
        os.close(descriptor)
        lock_path.unlink(missing_ok=True)


def subtitle_review_source_fingerprint(video: Video, source_path: Path) -> str:
    stat = source_path.stat()
    payload = f"v1\0{video.id}\0{stat.st_size}\0{stat.st_mtime_ns}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def subtitle_review_preview_url(job_id: str, clip_id: str, spec_hash: str) -> str:
    return (
        f"/api/jobs/{job_id}/subtitle-review/clips/{clip_id}/preview-video"
        f"?specHash={spec_hash}"
    )


def live_subtitle_review_preview_url(
    job_id: str,
    clip_id: str,
    spec_hash: str,
) -> str:
    return (
        f"/api/jobs/{job_id}/subtitle-review/clips/{clip_id}/live-preview-video"
        f"?specHash={spec_hash}"
    )


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def load_subtitle_review_preview_inputs(
    *,
    job: Job,
    video: Video,
    document: SubtitleReviewDocument,
    paths: StoragePaths,
    clip_id: str,
) -> SubtitleReviewPreviewInputs:
    output_dir = paths.job_outputs(job.id)
    selection = CandidateSelection.model_validate(
        _read_json(output_dir / "selected_clips.json")
    )
    selection = apply_reviewed_clip_content(selection, document)
    all_candidates = [*selection.normal_clips, *selection.shorts]
    candidate = next((item for item in all_candidates if item.id == clip_id), None)
    if candidate is None:
        raise KeyError(clip_id)
    type_candidates = (
        selection.normal_clips if candidate.type == "normal" else selection.shorts
    )
    candidate_index = next(
        index
        for index, item in enumerate(type_candidates, start=1)
        if item.id == clip_id
    )
    review_clip = next(
        (item for item in document.clips if item.id == clip_id),
        None,
    )
    if review_clip is None:
        raise KeyError(clip_id)

    transcript_payload = _read_json(transcript_output_path(output_dir))
    if not isinstance(transcript_payload, list):
        raise ValueError("transcript_segments.json must contain a list")
    transcript_segments = [
        TranscriptSegment.model_validate(item) for item in transcript_payload
    ]
    reviewed_segments = apply_reviewed_text(transcript_segments, document)
    source_path = paths.resolve_stored_file(video.stored_path)
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    return SubtitleReviewPreviewInputs(
        candidate=candidate,
        candidate_index=candidate_index,
        overlay_title_expected=review_clip.overlay_title_expected,
        transcript_segments=reviewed_segments,
        settings=dict(job.settings_json or {}),
        source_fingerprint=subtitle_review_source_fingerprint(video, source_path),
        source_width=video.width,
        source_height=video.height,
    )


def current_subtitle_review_preview_spec(
    *,
    job: Job,
    video: Video,
    document: SubtitleReviewDocument,
    paths: StoragePaths,
    clip_id: str,
) -> tuple[dict[str, object], str, SubtitleReviewPreviewInputs]:
    inputs = load_subtitle_review_preview_inputs(
        job=job,
        video=video,
        document=document,
        paths=paths,
        clip_id=clip_id,
    )
    spec = build_subtitle_review_preview_spec(
        candidate=inputs.candidate,
        transcript_segments=inputs.transcript_segments,
        settings=inputs.settings,
        source_fingerprint=inputs.source_fingerprint,
        source_width=inputs.source_width,
        source_height=inputs.source_height,
        candidate_index=inputs.candidate_index,
        overlay_title_expected=inputs.overlay_title_expected,
    )
    return spec, subtitle_review_preview_spec_hash(spec), inputs


def refresh_subtitle_review_preview_states(
    *,
    job: Job,
    video: Video,
    document: SubtitleReviewDocument,
    paths: StoragePaths,
    clip_ids: set[str] | None = None,
) -> tuple[SubtitleReviewDocument, list[tuple[str, str]], bool]:
    queued: list[tuple[str, str]] = []
    changed = False
    output_dir = paths.job_outputs(job.id)
    selected_ids = (
        {clip.id for clip in document.clips}
        if clip_ids is None
        else clip_ids
    )
    for clip in document.clips:
        if clip.id not in selected_ids:
            continue
        try:
            spec, spec_hash, _inputs = current_subtitle_review_preview_spec(
                job=job,
                video=video,
                document=document,
                paths=paths,
                clip_id=clip.id,
            )
        except (FileNotFoundError, KeyError, OSError, ValueError):
            if (
                clip.preview_state != "failed"
                or clip.preview_video_url is not None
                or clip.preview_error != "preview inputs are unavailable"
                or clip.live_preview_video_url is not None
                or clip.live_preview_spec_hash is not None
            ):
                clip.preview_state = "failed"
                clip.preview_video_url = None
                clip.preview_error = "preview inputs are unavailable"
                clip.live_preview_video_url = None
                clip.live_preview_spec_hash = None
                clip.confirmed = False
                changed = True
            continue
        live_spec = build_live_subtitle_review_preview_spec(spec)
        live_spec_hash = subtitle_review_preview_spec_hash(live_spec)
        artifacts = exact_subtitle_review_preview_paths(
            output_dir,
            clip.id,
            spec_hash,
        )
        live_artifacts = live_subtitle_review_preview_paths(
            output_dir,
            clip.id,
            live_spec_hash,
        )
        cleanup_stale_subtitle_review_preview_artifacts(
            output_dir,
            clip.id,
            spec_hash,
        )
        cleanup_stale_live_subtitle_review_preview_artifacts(
            output_dir,
            clip.id,
            live_spec_hash,
        )
        live_ready = live_subtitle_review_preview_is_ready(
            live_artifacts,
            live_spec_hash,
        )
        next_live_url = (
            live_subtitle_review_preview_url(job.id, clip.id, live_spec_hash)
            if live_ready
            else None
        )
        if exact_subtitle_review_preview_is_ready(artifacts, spec_hash):
            try:
                exact_subtitle_review_preview_error_path(
                    output_dir,
                    clip.id,
                    spec_hash,
                ).unlink(missing_ok=True)
            except OSError:
                pass
            next_state = "ready"
            next_url = subtitle_review_preview_url(job.id, clip.id, spec_hash)
            next_error = None
            if not live_ready:
                queued.append((clip.id, spec_hash))
        elif error_message := read_subtitle_review_preview_error(
            exact_subtitle_review_preview_error_path(
                output_dir,
                clip.id,
                spec_hash,
            )
        ):
            next_state = "failed"
            next_url = None
            next_error = error_message
        elif (
            clip.preview_spec_hash == spec_hash
            and clip.preview_state == "failed"
        ):
            next_state = "failed"
            next_url = None
            next_error = clip.preview_error
        else:
            next_state = "queued"
            next_url = None
            next_error = None
            queued.append((clip.id, spec_hash))

        if (
            clip.preview_spec_hash != spec_hash
            or clip.preview_state != next_state
            or clip.preview_video_url != next_url
            or clip.preview_error != next_error
            or clip.live_preview_spec_hash != live_spec_hash
            or clip.live_preview_video_url != next_live_url
        ):
            if clip.preview_spec_hash != spec_hash:
                clip.confirmed = False
            clip.preview_spec_hash = spec_hash
            clip.preview_state = next_state
            clip.preview_video_url = next_url
            clip.preview_error = next_error
            clip.live_preview_spec_hash = live_spec_hash
            clip.live_preview_video_url = next_live_url
            changed = True
    if changed:
        document.confirmed_clip_count = sum(
            1 for clip in document.clips if clip.confirmed
        )
    return document, queued, changed


def current_preview_is_ready(
    *,
    job: Job,
    video: Video,
    document: SubtitleReviewDocument,
    paths: StoragePaths,
    clip_id: str,
) -> bool:
    clip = next((item for item in document.clips if item.id == clip_id), None)
    if clip is None:
        raise KeyError(clip_id)
    _spec, spec_hash, _inputs = current_subtitle_review_preview_spec(
        job=job,
        video=video,
        document=document,
        paths=paths,
        clip_id=clip_id,
    )
    if clip.preview_state != "ready" or clip.preview_spec_hash != spec_hash:
        return False
    artifacts = exact_subtitle_review_preview_paths(
        paths.job_outputs(job.id),
        clip_id,
        spec_hash,
    )
    return exact_subtitle_review_preview_is_ready(artifacts, spec_hash)
