from app.audio.silence_detect import SilenceSegment
from app.audio.volume_features import AudioFeatures
from app.candidates.deduplicate import (
    deduplicate_candidates,
    time_overlap_ratio,
    transcript_similarity,
)
from app.candidates.merge_boundaries import Candidate
from app.scoring.rule_score import (
    apply_rule_score,
    incomplete_boundary_penalty,
    score_candidate,
    score_candidates,
)
from app.scoring.clip_preferences import CandidateClipPreference


def make_candidate(
    candidate_id: str,
    start: float,
    end: float,
    transcript_text: str,
    candidate_type: str = "short",
    rule_score: float | None = None,
) -> Candidate:
    return Candidate(
        id=candidate_id,
        type=candidate_type,  # type: ignore[arg-type]
        start=start,
        end=end,
        duration=end - start,
        transcript_text=transcript_text,
        rule_score=rule_score,
    )


def test_score_candidates_adds_rule_score_to_every_candidate() -> None:
    candidates = [
        make_candidate(
            "cand_good",
            0.0,
            45.0,
            "why automation fails before teams fix the important mistake",
        ),
        make_candidate("cand_plain", 60.0, 100.0, "plain operational update with details"),
    ]
    audio_features = AudioFeatures(
        duration=120.0,
        silence_ratio=0.1,
        speech_density=0.9,
        volume_peak=0.5,
        silent_seconds=12.0,
        speech_seconds=108.0,
    )

    scored = score_candidates(candidates, audio_features=audio_features)

    assert all(candidate.rule_score is not None for candidate in scored)
    assert scored[0].rule_score is not None
    assert scored[1].rule_score is not None
    assert scored[0].rule_score > scored[1].rule_score


def test_rule_score_penalizes_silence_and_bad_audio_peak() -> None:
    candidate = make_candidate(
        "cand",
        0.0,
        40.0,
        "why this important fix matters before launch",
    )
    good_audio = AudioFeatures(
        duration=40.0,
        silence_ratio=0.05,
        speech_density=0.95,
        volume_peak=0.5,
        silent_seconds=2.0,
        speech_seconds=38.0,
    )
    weak_audio = AudioFeatures(
        duration=40.0,
        silence_ratio=0.7,
        speech_density=0.3,
        volume_peak=0.03,
        silent_seconds=28.0,
        speech_seconds=12.0,
    )

    good_score = score_candidate(candidate, audio_features=good_audio)
    weak_score = score_candidate(candidate, audio_features=weak_audio)

    assert good_score.final_score > weak_score.final_score
    assert weak_score.silence_score == 0.0
    assert weak_score.audio_peak_score == 2.0


def test_rule_score_uses_candidate_local_silence_ratio() -> None:
    candidate = make_candidate("cand", 10.0, 50.0, "why automation fix matters now")
    audio_features = AudioFeatures(
        duration=100.0,
        silence_ratio=0.0,
        speech_density=1.0,
        volume_peak=0.5,
        silent_seconds=0.0,
        speech_seconds=100.0,
    )
    silence_segments = [SilenceSegment(start=20.0, end=45.0, duration=25.0)]

    breakdown = score_candidate(
        candidate,
        audio_features=audio_features,
        silence_segments=silence_segments,
    )

    assert breakdown.silence_score == 0.0
    assert breakdown.speech_density_score == 6.0


def test_rule_score_detects_japanese_hooks_and_guidance() -> None:
    candidate = make_candidate(
        "cand_japanese",
        0.0,
        120.0,
        "実は一週間休んだ理由とホロライブ運動会を欠席した経緯を説明します",
        candidate_type="normal",
    )
    preference = CandidateClipPreference(
        preset="important",
        guidance="ホロライブ運動会を欠席した理由",
    )

    breakdown = score_candidate(candidate, selection_preference=preference)

    assert breakdown.hook_score > 0
    assert breakdown.guidance_score > 0
    assert breakdown.transcript_length_score > 0


def test_rule_score_penalizes_generic_outro_when_requested() -> None:
    outro = make_candidate(
        "cand_outro",
        0.0,
        90.0,
        "動画アップされたらぜひご覧ください。本日の配信はこの辺で終わりにしようと思います。"
        "ご視聴ありがとうございました。次の動画でお会いしましょう。バイバイ。",
        candidate_type="normal",
    )
    focused = make_candidate(
        "cand_focused",
        100.0,
        190.0,
        "実は配信を休んだ理由があります。運動会の直前に倒れてしまった経緯を説明します。",
        candidate_type="normal",
    )
    preference = CandidateClipPreference(
        preset="important",
        exclude_intro_outro=True,
        exclude_promotional_content=True,
    )

    outro_score = score_candidate(outro, selection_preference=preference)
    focused_score = score_candidate(focused, selection_preference=preference)
    scored_outro = apply_rule_score(outro, selection_preference=preference)

    assert outro_score.generic_content_penalty == 25.0
    assert focused_score.final_score > outro_score.final_score
    assert "generic_intro_outro" in scored_outro.risk_flags
    assert "promotional_content" in scored_outro.risk_flags


def test_incomplete_boundary_penalty_detects_fragments() -> None:
    assert incomplete_boundary_penalty("because this is unfinished and") >= 20.0
    assert incomplete_boundary_penalty("Complete thought with a clear ending.") == 0.0


def test_apply_rule_score_preserves_candidate_fields() -> None:
    candidate = make_candidate("cand", 0.0, 45.0, "how to fix the important mistake")

    scored = apply_rule_score(candidate)

    assert scored.id == candidate.id
    assert scored.type == candidate.type
    assert scored.start == candidate.start
    assert scored.end == candidate.end
    assert scored.rule_score is not None


def test_time_overlap_ratio_uses_shorter_candidate() -> None:
    left = make_candidate("left", 0.0, 60.0, "first candidate")
    right = make_candidate("right", 30.0, 70.0, "second candidate")

    assert time_overlap_ratio(left, right) == 0.75


def test_deduplicate_removes_high_time_overlap_and_keeps_higher_score() -> None:
    lower = make_candidate(
        "lower",
        0.0,
        60.0,
        "why automation fails before launch",
        rule_score=50.0,
    )
    higher = make_candidate(
        "higher",
        5.0,
        62.0,
        "why automation fails before launch with detail",
        rule_score=80.0,
    )
    separate = make_candidate(
        "separate",
        120.0,
        165.0,
        "separate useful segment",
        rule_score=40.0,
    )

    deduped = deduplicate_candidates([lower, higher, separate], time_overlap_threshold=0.8)

    assert [candidate.id for candidate in deduped] == ["higher", "separate"]


def test_deduplicate_removes_near_identical_transcript_text() -> None:
    first = make_candidate(
        "first",
        0.0,
        45.0,
        "How to fix the automation mistake before launch",
        rule_score=70.0,
    )
    duplicate = make_candidate(
        "duplicate",
        80.0,
        125.0,
        "how to fix the automation mistake before launch!",
        rule_score=65.0,
    )
    different = make_candidate(
        "different",
        160.0,
        205.0,
        "A different operational lesson for the next phase",
        rule_score=60.0,
    )

    deduped = deduplicate_candidates([first, duplicate, different])

    assert [candidate.id for candidate in deduped] == ["first", "different"]
    assert transcript_similarity(first.transcript_text, duplicate.transcript_text) >= 0.9


def test_deduplicate_keeps_different_types_by_default() -> None:
    short = make_candidate("short", 0.0, 45.0, "same text", candidate_type="short", rule_score=50.0)
    normal = make_candidate("normal", 0.0, 120.0, "same text", candidate_type="normal", rule_score=80.0)

    deduped = deduplicate_candidates([short, normal])

    assert {candidate.id for candidate in deduped} == {"short", "normal"}


def test_deduplicate_can_remove_across_types_when_requested() -> None:
    short = make_candidate("short", 0.0, 45.0, "same text", candidate_type="short", rule_score=50.0)
    normal = make_candidate("normal", 0.0, 120.0, "same text", candidate_type="normal", rule_score=80.0)

    deduped = deduplicate_candidates([short, normal], deduplicate_across_types=True)

    assert [candidate.id for candidate in deduped] == ["normal"]
