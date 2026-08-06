import json
from pathlib import Path

from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.jobs.clip_plan import build_clip_plan, load_clip_plan


def test_build_clip_plan_does_not_emit_known_mixed_script_error() -> None:
    selection = CandidateSelection(
        shorts=[
            Candidate(
                id="short_mixed_script",
                type="short",
                start=10.0,
                end=20.0,
                duration=10.0,
                transcript_text="その農منにしとったっちゃん",
                title="その農منにしとったっちゃん",
                boundary_refined=False,
            )
        ]
    )

    document = build_clip_plan(
        "job_mixed_script",
        selection,
        {"enableTranscriptPostProcessing": True},
    )

    assert document.clips[0].title == "その能面にしとったっちゃん"
    assert document.clips[0].transcript_excerpt == "その能面にしとったっちゃん"


def test_build_clip_plan_does_not_reapply_custom_transcript_replacements() -> None:
    selection = CandidateSelection(
        shorts=[
            Candidate(
                id="short_custom_replacement",
                type="short",
                start=10.0,
                end=20.0,
                duration=10.0,
                transcript_text="NewsPicks公式で能面を紹介",
                title="NewsPicks公式で能面を紹介",
                boundary_refined=False,
            )
        ]
    )

    document = build_clip_plan(
        "job_custom_replacement",
        selection,
        {
            "enableTranscriptPostProcessing": True,
            "transcriptReplacements": {"NewsPicks": "NewsPicks公式"},
        },
    )

    assert document.clips[0].title == "NewsPicks公式で能面を紹介"
    assert document.clips[0].transcript_excerpt == "NewsPicks公式で能面を紹介"


def test_load_clip_plan_postprocesses_legacy_transcript_text(tmp_path: Path) -> None:
    plan_path = tmp_path / "clip_plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "version": 3,
                "jobId": "job_legacy_title",
                "state": "awaiting_review",
                "revision": 1,
                "sourceVideoUrl": "/api/jobs/job_legacy_title/source-video",
                "sourceDuration": 120.0,
                "clips": [
                    {
                        "id": "short_01",
                        "type": "short",
                        "title": "その農منにしとったっちゃん",
                        "start": 10.0,
                        "end": 20.0,
                        "duration": 10.0,
                        "transcriptExcerpt": "農منをつけて活動しようと",
                    }
                ],
                "settings": {
                    "enableTranscriptPostProcessing": True,
                    "transcriptReplacements": {"NewsPicks": "NewsPicks公式"},
                },
                "createdAt": "2026-08-04T00:00:00+00:00",
                "updatedAt": "2026-08-04T00:00:00+00:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    document = load_clip_plan(plan_path)

    assert document.clips[0].title == "その能面にしとったっちゃん"
    assert document.clips[0].transcript_excerpt == "能面をつけて活動しようと"


def test_load_clip_plan_does_not_reapply_custom_transcript_replacements(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "clip_plan.json"
    payload = {
        "version": 3,
        "jobId": "job_idempotent_title",
        "state": "awaiting_review",
        "revision": 1,
        "sourceVideoUrl": "/api/jobs/job_idempotent_title/source-video",
        "sourceDuration": 120.0,
        "clips": [
            {
                "id": "short_01",
                "type": "short",
                "title": "NewsPicks公式で能面を紹介",
                "start": 10.0,
                "end": 20.0,
                "duration": 10.0,
                "transcriptExcerpt": "NewsPicks公式で能面を紹介",
            }
        ],
        "settings": {
            "enableTranscriptPostProcessing": True,
            "transcriptReplacements": {"NewsPicks": "NewsPicks公式"},
        },
        "createdAt": "2026-08-04T00:00:00+00:00",
        "updatedAt": "2026-08-04T00:00:00+00:00",
    }
    plan_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    first_load = load_clip_plan(plan_path)
    second_load = load_clip_plan(plan_path)

    assert first_load.clips[0].title == "NewsPicks公式で能面を紹介"
    assert first_load.clips[0].transcript_excerpt == "NewsPicks公式で能面を紹介"
    assert second_load.clips[0].title == first_load.clips[0].title
