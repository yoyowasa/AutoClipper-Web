import hashlib
import json
from pathlib import Path

import pytest

from app.candidates.merge_boundaries import Candidate
from app.scoring.heatmap import annotate_candidates_with_heatmap
from app.scoring.rule_score import HEATMAP_SCORE_MAX, score_candidate
from app.video.heatmap import (
    HeatmapSegment,
    HeatmapSidecarError,
    duration_tolerance_seconds,
    heatmap_sidecar_path,
    load_heatmap_for_video,
    parse_heatmap_sidecar,
    validate_heatmap_sidecar,
    write_heatmap_sidecar,
)


def _payload(media: bytes = b"video bytes") -> dict[str, object]:
    return {
        "schema_version": 1,
        "source": {
            "name": "youtube_most_replayed",
            "video_id": "BaW_jenozKc",
            "fetched_at": "2026-08-02T03:30:00Z",
            "extractor": "yt-dlp",
            "extractor_version": "2026.07.04",
        },
        "media": {
            "filename": "sample.mp4",
            "sha256": hashlib.sha256(media).hexdigest(),
            "size_bytes": len(media),
        },
        "duration_seconds": 120.0,
        "heatmap_available": True,
        "heatmap": [
            {"start_time": 10.0, "end_time": 15.0, "value": 0.8},
            {"start_time": 30.0, "end_time": 35.0, "value": 0.4},
        ],
    }


def _raw(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def test_valid_sidecar_parses_and_binds_to_media() -> None:
    media = b"video bytes"
    sidecar = validate_heatmap_sidecar(
        _raw(_payload(media)),
        expected_filename="sample.mp4",
        actual_size_bytes=len(media),
        actual_sha256=hashlib.sha256(media).hexdigest(),
        actual_duration=120.5,
    )

    assert sidecar.schema_version == 1
    assert sidecar.source.name == "youtube_most_replayed"
    assert [segment.value for segment in sidecar.heatmap] == [0.8, 0.4]


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda payload: payload.update(schema_version=True), "heatmap_contract_invalid"),
        (
            lambda payload: payload["source"].update(name="other"),  # type: ignore[union-attr]
            "heatmap_contract_invalid",
        ),
        (
            lambda payload: payload["source"].update(fetched_at="2026-08-02T12:30:00+09:00"),  # type: ignore[union-attr]
            "heatmap_contract_invalid",
        ),
        (lambda payload: payload.update(heatmap_available=False), "heatmap_contract_invalid"),
        (
            lambda payload: payload.update(
                heatmap=[
                    {"start_time": 30.0, "end_time": 35.0, "value": 0.4},
                    {"start_time": 10.0, "end_time": 15.0, "value": 0.8},
                ]
            ),
            "heatmap_contract_invalid",
        ),
        (
            lambda payload: payload.update(
                heatmap=[{"start_time": 10.0, "end_time": 10.0, "value": 0.8}]
            ),
            "heatmap_contract_invalid",
        ),
        (
            lambda payload: payload.update(
                heatmap=[{"start_time": 10.0, "end_time": 15.0, "value": "0.8"}]
            ),
            "heatmap_contract_invalid",
        ),
    ],
)
def test_sidecar_rejects_invalid_contract(mutate: object, expected_code: str) -> None:
    payload = _payload()
    mutate(payload)  # type: ignore[operator]

    with pytest.raises(HeatmapSidecarError) as caught:
        parse_heatmap_sidecar(_raw(payload))

    assert caught.value.code == expected_code


def test_sidecar_rejects_non_finite_json_number() -> None:
    raw = _raw(_payload()).replace(b'"value": 0.8', b'"value": NaN')

    with pytest.raises(HeatmapSidecarError) as caught:
        parse_heatmap_sidecar(raw)

    assert caught.value.code == "heatmap_json_invalid"


@pytest.mark.parametrize(
    ("expected_filename", "size_delta", "sha256_hex", "expected_code"),
    [
        ("other.mp4", 0, None, "heatmap_media_filename_mismatch"),
        ("sample.mp4", 1, None, "heatmap_media_size_mismatch"),
        ("sample.mp4", 0, "0" * 64, "heatmap_media_sha256_mismatch"),
    ],
)
def test_sidecar_rejects_media_binding_mismatch(
    expected_filename: str,
    size_delta: int,
    sha256_hex: str | None,
    expected_code: str,
) -> None:
    media = b"video bytes"
    with pytest.raises(HeatmapSidecarError) as caught:
        validate_heatmap_sidecar(
            _raw(_payload(media)),
            expected_filename=expected_filename,
            actual_size_bytes=len(media) + size_delta,
            actual_sha256=sha256_hex or hashlib.sha256(media).hexdigest(),
        )

    assert caught.value.code == expected_code


def test_sidecar_duration_uses_documented_consumer_tolerance() -> None:
    media = b"video bytes"
    tolerance = duration_tolerance_seconds(120.0)
    assert tolerance == 2.0

    validate_heatmap_sidecar(
        _raw(_payload(media)),
        expected_filename="sample.mp4",
        actual_size_bytes=len(media),
        actual_sha256=hashlib.sha256(media).hexdigest(),
        actual_duration=120.0 + tolerance,
    )
    with pytest.raises(HeatmapSidecarError) as caught:
        validate_heatmap_sidecar(
            _raw(_payload(media)),
            expected_filename="sample.mp4",
            actual_size_bytes=len(media),
            actual_sha256=hashlib.sha256(media).hexdigest(),
            actual_duration=120.0 + tolerance + 0.01,
        )
    assert caught.value.code == "heatmap_duration_mismatch"


def test_worker_loads_available_sidecar_and_falls_back_when_unavailable(tmp_path: Path) -> None:
    media = b"video bytes"
    media_path = tmp_path / "stored.mp4"
    media_path.write_bytes(media)
    available = validate_heatmap_sidecar(
        _raw(_payload(media)),
        expected_filename="sample.mp4",
        actual_size_bytes=len(media),
        actual_sha256=hashlib.sha256(media).hexdigest(),
    )
    write_heatmap_sidecar(available, heatmap_sidecar_path(media_path))

    loaded = load_heatmap_for_video(
        media_path,
        original_filename="sample.mp4",
        actual_duration=120.0,
        max_sidecar_size_bytes=1024 * 1024,
    )
    assert loaded.summary["status"] == "applied"
    assert len(loaded.segments) == 2

    unavailable_payload = _payload(media)
    unavailable_payload["heatmap_available"] = False
    unavailable_payload["heatmap"] = []
    unavailable = validate_heatmap_sidecar(
        _raw(unavailable_payload),
        expected_filename="sample.mp4",
        actual_size_bytes=len(media),
        actual_sha256=hashlib.sha256(media).hexdigest(),
    )
    write_heatmap_sidecar(unavailable, heatmap_sidecar_path(media_path))

    fallback = load_heatmap_for_video(
        media_path,
        original_filename="sample.mp4",
        actual_duration=120.0,
        max_sidecar_size_bytes=1024 * 1024,
    )
    assert fallback.segments == []
    assert fallback.summary["status"] == "unavailable"
    assert fallback.summary["fallback_reason"] == "heatmap_unavailable"


def test_worker_falls_back_explicitly_for_tampered_media(tmp_path: Path) -> None:
    media = b"video bytes"
    media_path = tmp_path / "stored.mp4"
    media_path.write_bytes(media)
    sidecar = validate_heatmap_sidecar(
        _raw(_payload(media)),
        expected_filename="sample.mp4",
        actual_size_bytes=len(media),
        actual_sha256=hashlib.sha256(media).hexdigest(),
    )
    write_heatmap_sidecar(sidecar, heatmap_sidecar_path(media_path))
    media_path.write_bytes(b"other bytes")

    loaded = load_heatmap_for_video(
        media_path,
        original_filename="sample.mp4",
        actual_duration=120.0,
        max_sidecar_size_bytes=1024 * 1024,
    )

    assert loaded.segments == []
    assert loaded.summary["status"] == "invalid_fallback"
    assert loaded.summary["fallback_reason"] == "heatmap_media_sha256_mismatch"


def test_empty_heatmap_clears_stale_candidate_features() -> None:
    candidate = Candidate(
        id="cand_stale_heatmap",
        type="short",
        start=10.0,
        end=30.0,
        duration=20.0,
        transcript_text="complete standalone point",
        heatmap_value=0.9,
        heatmap_overlap_seconds=10.0,
        heatmap_score=9.0,
    )

    cleared = annotate_candidates_with_heatmap([candidate], [])[0]

    assert cleared.heatmap_value is None
    assert cleared.heatmap_overlap_seconds is None
    assert cleared.heatmap_score is None


def test_heatmap_is_a_bounded_supporting_rule_score_signal() -> None:
    candidate = Candidate(
        id="cand_short_heatmap",
        type="short",
        start=10.0,
        end=30.0,
        duration=20.0,
        transcript_text="why this important fix works",
    )
    segments = [HeatmapSegment(start_time=10.0, end_time=20.0, value=1.0)]
    annotated = annotate_candidates_with_heatmap([candidate], segments)[0]

    baseline = score_candidate(candidate)
    scored = score_candidate(annotated)

    assert annotated.heatmap_value == 1.0
    assert annotated.heatmap_overlap_seconds == 10.0
    assert scored.heatmap_score == HEATMAP_SCORE_MAX
    assert scored.final_score == min(100.0, baseline.final_score + HEATMAP_SCORE_MAX)
