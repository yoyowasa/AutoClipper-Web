"""Real encoded MP4 regression cases, independent of export-side metadata."""

import shutil
import subprocess
import pytest
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate, ClipTextStyle
from app.inspection.subtitles import inspect_subtitles
from app.render.filters import ass_filter
from app.render.subtitles_ass import SubtitleLayout, write_ass_for_candidate


@pytest.fixture
def encoded(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg is required for actual final-MP4 pixel inspection")
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=640x360:r=25:d=4",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=997:sample_rate=16000:duration=4",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-y",
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=45,
    )
    candidate = Candidate(id="test", type="normal", start=0, end=4, duration=4, transcript_text="Confirmed subtitle")
    segments = [TranscriptSegment(start=0.6, end=2.8, text="Confirmed subtitle", preserve_segmentation=True)]
    layout = SubtitleLayout.normal(640, 360)

    def burn(*, cues=segments, clip=candidate, rate=None):
        file = tmp_path / f"render-{len(list(tmp_path.glob('render-*.mp4')))}.mp4"
        ass = write_ass_for_candidate(clip, cues, file.with_suffix(".ass"), layout=layout, top_title="")
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-i",
                str(source),
                "-vf",
                (f"fps={rate}," if rate else "") + ass_filter(ass),
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-preset",
                "ultrafast",
                "-c:a",
                "copy",
                "-y",
                str(file),
            ],
            check=True,
            capture_output=True,
            timeout=45,
        )
        return file

    return source, candidate, segments, layout, burn, tmp_path


def test_correct_encoded_subtitles_pass(encoded):
    _source, candidate, segments, layout, burn, folder = encoded
    checks = inspect_subtitles(burn(), candidate, segments, layout=layout, directory=folder)
    assert all(c.outcome == "pass" for c in checks), [c.model_dump() for c in checks]


@pytest.mark.parametrize("rate", [25, "60000/1001", 60])
def test_real_frame_timestamps_are_used_at_fractional_caption_boundaries(encoded, rate):
    _source, candidate, _segments, layout, burn, folder = encoded
    # Old fps=5 decoded a future frame (e.g. 1.48s) but compared it against
    # reference glyphs at 1.4s. All three rates must retain their actual PTS.
    cues = [
        TranscriptSegment(start=0.62, end=1.42, text="First confirmed caption", preserve_segmentation=True),
        TranscriptSegment(start=1.42, end=2.88, text="Second confirmed caption", preserve_segmentation=True),
    ]
    checks = inspect_subtitles(burn(cues=cues, rate=rate), candidate, cues, layout=layout, directory=folder)
    assert all(c.outcome == "pass" for c in checks), [c.model_dump() for c in checks]


def test_short_cue_requires_an_observed_interior_frame_and_missing_pixels_still_fail(encoded):
    source, candidate, _segments, layout, burn, folder = encoded
    cues = [TranscriptSegment(start=0.8, end=0.99, text="Brief confirmed cue", preserve_segmentation=True)]
    checks = inspect_subtitles(burn(cues=cues), candidate, cues, layout=layout, directory=folder)
    assert all(c.outcome == "pass" for c in checks), [c.model_dump() for c in checks]
    assert next(c for c in checks if c.code == "SUBTITLE_PIXELS_MISMATCH").evidence["interiorSamples"] == 1
    checks = inspect_subtitles(source, candidate, cues, layout=layout, directory=folder)
    assert any(c.code == "SUBTITLE_PIXELS_MISMATCH" and c.outcome == "fail" for c in checks)


def test_cue_between_native_frames_cannot_be_accepted_without_pixel_evidence(encoded):
    _source, candidate, _segments, layout, burn, folder = encoded
    cues = [TranscriptSegment(start=0.801, end=0.819, text="Unobservable cue", preserve_segmentation=True)]
    checks = inspect_subtitles(burn(cues=cues), candidate, cues, layout=layout, directory=folder)
    assert any(c.outcome != "pass" for c in checks)


@pytest.mark.parametrize("fault", ["missing", "shifted", "different_text"])
def test_missing_or_shifted_or_wrong_burned_subtitles_are_detected(encoded, fault):
    source, candidate, segments, layout, burn, folder = encoded
    cues = (
        [s.model_copy(update={"start": s.start + 0.8, "end": s.end + 0.8}) for s in segments]
        if fault == "shifted"
        else [s.model_copy(update={"text": "Different words"}) for s in segments]
    )
    file = source if fault == "missing" else burn(cues=cues)
    # The sidecar can claim anything; inspection consumes actual decoded pixels.
    file.with_suffix(".json").write_text('{"subtitlesCorrect":true}', encoding="utf-8")
    checks = inspect_subtitles(file, candidate, segments, layout=layout, directory=folder)
    assert any(c.code == "SUBTITLE_PIXELS_MISMATCH" and c.outcome == "fail" for c in checks)


def test_caption_at_outside_position_is_detected(encoded):
    _source, candidate, segments, layout, burn, folder = encoded
    candidate.subtitle_style = ClipTextStyle(positionMode="explicit", positionOverride=True, xPercent=95, yPercent=70)
    checks = inspect_subtitles(burn(clip=candidate), candidate, segments, layout=layout, directory=folder)
    assert any(c.code == "SUBTITLE_OUT_OF_FRAME" and c.outcome == "fail" for c in checks), [c.model_dump() for c in checks]


def test_actual_subtitle_band_collision_and_overlapping_cues_are_detected(encoded):
    _source, candidate, segments, layout, burn, folder = encoded
    # Explicit normal layout allows a small fixture for the same pixel-band test.
    checks = inspect_subtitles(burn(), candidate, segments, layout=layout, directory=folder, banners=(0, 180))
    assert any(c.code == "SUBTITLE_BANNER_COLLISION" and c.outcome == "fail" for c in checks)
    overlapping = [*segments, segments[0].model_copy(update={"start": 1.0, "end": 3.0, "text": "Another confirmed cue"})]
    checks = inspect_subtitles(burn(cues=overlapping), candidate, overlapping, layout=layout, directory=folder)
    assert any(c.code == "SUBTITLE_OVERLAP" and c.outcome == "fail" for c in checks)
