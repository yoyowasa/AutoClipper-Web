from app.audio.silence_detect import SilenceSegment
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import (
    Candidate,
    CandidateGenerationResult,
    CandidateGenerationSettings,
    generate_window_candidates,
    generate_window_candidates_with_summary,
    parse_generation_settings,
)
from app.video.scene_detect import SceneSegment


def generate_short_candidates(
    transcript_segments: list[TranscriptSegment],
    scene_segments: list[SceneSegment],
    silence_segments: list[SilenceSegment],
    settings: CandidateGenerationSettings | dict | None = None,
) -> list[Candidate]:
    parsed_settings = parse_generation_settings(settings)
    return generate_window_candidates(
        "short",
        transcript_segments=transcript_segments,
        scene_segments=scene_segments,
        silence_segments=silence_segments,
        min_duration=parsed_settings.short_min_duration,
        max_duration=parsed_settings.short_max_duration,
        step_seconds=parsed_settings.short_step_seconds,
        speech_boundary_tolerance=parsed_settings.speech_boundary_tolerance,
        max_candidates=parsed_settings.max_candidates,
    )


def generate_short_candidates_with_summary(
    transcript_segments: list[TranscriptSegment],
    scene_segments: list[SceneSegment],
    silence_segments: list[SilenceSegment],
    settings: CandidateGenerationSettings | dict | None = None,
    heartbeat=None,
) -> CandidateGenerationResult:
    parsed_settings = parse_generation_settings(settings)
    return generate_window_candidates_with_summary(
        "short",
        transcript_segments=transcript_segments,
        scene_segments=scene_segments,
        silence_segments=silence_segments,
        min_duration=parsed_settings.short_min_duration,
        max_duration=parsed_settings.short_max_duration,
        step_seconds=parsed_settings.short_step_seconds,
        speech_boundary_tolerance=parsed_settings.speech_boundary_tolerance,
        max_candidates=parsed_settings.max_candidates,
        settings=parsed_settings,
        heartbeat=heartbeat,
    )
