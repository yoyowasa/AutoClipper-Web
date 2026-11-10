"""Intentional defects in real files, not declarations in render metadata."""

import shutil
import subprocess
import av
import pytest
from app.candidates.merge_boundaries import Candidate
import app.inspection.media as media
from app.video.probe import VideoMetadata


@pytest.fixture
def movies(tmp_path, monkeypatch, request):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg required for real MP4 defect fixtures")
    if not shutil.which("ffprobe"):
        # Windows development's portable FFmpeg lacks ffprobe. Read the actual
        # file with PyAV here; Linux CI exercises the production ffprobe path.
        def probe(path):
            with av.open(str(path)) as container:
                v = next(iter(container.streams.video), None)
                a = next(iter(container.streams.audio), None)

                def seconds(s):
                    return float(s.duration * s.time_base) if s is not None and s.duration is not None else None

                duration = seconds(v)
                return VideoMetadata(
                    duration=duration,
                    width=v.width if v else None,
                    height=v.height if v else None,
                    fps=float(v.average_rate) if v and v.average_rate else None,
                    nominal_fps=float(v.base_rate) if v and v.base_rate else None,
                    has_audio=a is not None,
                    video_stream_duration=duration,
                    audio_stream_duration=seconds(a),
                    container_duration=container.duration / av.time_base if container.duration is not None else None,
                )

        monkeypatch.setattr(media, "probe_metadata", probe)
    source = tmp_path / "source.mp4"

    def ffmpeg(args):
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", *args], check=True, capture_output=True, timeout=60)

    fps = getattr(request, "param", 25)
    # At 60fps, a frame is not an integer number of 8kHz samples.
    # High-frequency noise makes the resulting fractional phase error visible.
    audio = ("anoisesrc=a=0.1:r=48000:d=12:seed=248,highpass=f=2500,highpass=f=2500,lowpass=f=3700" if fps == 60
             else "aevalsrc=0.1*sin(2*PI*(200*t+10*t*t)):s=16000:d=12")
    ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=s=640x360:r={fps}:d=12",
            "-f",
            "lavfi",
            "-i",
            audio,
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
        ]
    )
    candidate = Candidate(id="normal", type="normal", start=0, end=12, duration=12, transcript_text="")

    def transform(*options):
        target = tmp_path / "output.mp4"
        ffmpeg(["-i", str(source), *options, "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-y", str(target)])
        return target

    return source, candidate, transform, tmp_path


def test_real_normal_mp4_passes(movies):
    source, candidate, _transform, _folder = movies
    digest, checks = media.inspect_media(source, candidate, dimensions=(640, 360), source=source)
    assert digest and all(c.outcome == "pass" for c in checks), checks
    opening = media.inspect_opening(source, candidate, source)
    assert opening.outcome == "pass"
    piece, = opening.evidence["pieces"]
    assert piece["readStartSeconds"] == piece["alignmentOffsetSeconds"] == piece["maxAlignmentSeconds"] == 0
    assert piece["correlation"] == piece["rawCorrelation"]


@pytest.mark.parametrize(
    "options,code",
    [
        (("-t", "2"), "DURATION_MISMATCH"),
        (("-an",), "STREAM_MISSING"),
        (("-vf", "scale=320:240"), "DIMENSIONS_INVALID"),
        (("-af", "atrim=end=2"), "AV_DURATION_MISMATCH"),
        (("-vf", "drawbox=color=black:t=fill"), "BLACK_INTERVAL"),
        (("-vf", "loop=loop=-1:size=1:start=0", "-t", "12"), "FREEZE_INTERVAL"),
        (("-af", "volume=0"), "SILENCE_INTERVAL"),
    ],
)
def test_real_corrupted_mp4_is_detected(movies, options, code):
    source, candidate, transform, _folder = movies
    _digest, checks = media.inspect_media(transform(*options), candidate, dimensions=(640, 360), source=source)
    assert any(c.code == code and c.outcome == "fail" for c in checks), checks


def test_static_source_is_recorded_without_misclassifying_faithful_export(movies):
    _source, candidate, transform, _folder = movies
    frozen = transform("-vf", "loop=loop=-1:size=1:start=0", "-t", "12")
    _, checks = media.inspect_media(frozen, candidate, dimensions=(640, 360), source=frozen)
    freeze = next(c for c in checks if c.code == "FREEZE_INTERVAL")
    assert freeze.outcome == "pass" and freeze.evidence["detected"] and freeze.evidence["unexpected"] == []


def test_opening_comes_from_the_confirmed_source_range(movies):
    source, candidate, transform, _folder = movies
    candidate.start, candidate.end, candidate.duration = 5, 9, 4
    wrong = transform("-t", "4")
    assert media.inspect_opening(wrong, candidate, source).outcome == "fail"
    correct = transform("-ss", "5", "-t", "4")
    check = media.inspect_opening(correct, candidate, source)
    assert check.outcome == "pass", check


def test_opening_checks_hook_and_body_against_their_distinct_source_ranges(movies):
    source, candidate, _transform, folder = movies
    candidate.type, candidate.start, candidate.end, candidate.duration = "short", 5, 9, 4
    candidate.hook_scene_start, candidate.hook_scene_end = 2, 3
    output = folder / "hook-body.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(source),
            "-filter_complex",
            "[0:v]trim=start=2:end=3,setpts=PTS-STARTPTS[h];"
            "[0:a]atrim=start=2:end=3,asetpts=PTS-STARTPTS[ha];"
            "[0:v]trim=start=5:end=9,setpts=PTS-STARTPTS[b];"
            "[0:a]atrim=start=5:end=9,asetpts=PTS-STARTPTS[ba];"
            "[h][ha][b][ba]concat=n=2:v=1:a=1[v][a]",
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            str(output),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    check = media.inspect_opening(output, candidate, source)
    assert check.outcome == "pass", check
    assert [(p["outputStart"], p["sourceStart"]) for p in check.evidence["pieces"]] == [(0, 2), (1, 5)]


@pytest.mark.parametrize("hook_seconds", [1.42, 2.58, 2.84, 1.96])
def test_fractional_hook_concat_frame_padding_is_aligned_without_relaxing_correlation(movies, hook_seconds):
    from app.render.render_normal import build_render_normal_command

    source, candidate, _transform, folder = movies
    candidate.start, candidate.end, candidate.duration = 5, 9, 4
    candidate.hook_scene_start, candidate.hook_scene_end = 5.2, 5.2 + hook_seconds
    output = folder / "fractional-hook.mp4"
    subprocess.run(build_render_normal_command(source, output, 5, 9,
        hook_scene_start=candidate.hook_scene_start, hook_scene_end=candidate.hook_scene_end),
        check=True, capture_output=True, timeout=60)
    check = media.inspect_opening(output, candidate, source)
    assert check.outcome == "pass", check
    hook, body = check.evidence["pieces"]
    assert hook["alignmentOffsetSeconds"] == 0
    assert 0 <= body["alignmentOffsetSeconds"] <= body["maxAlignmentSeconds"] <= min(1 / 25, media.OPENING_MAX_JOIN_ALIGNMENT_SECONDS)
    assert body["correlation"] >= media.OPENING_CORRELATION_MIN == 0.9


@pytest.mark.parametrize("movies", [60], indirect=True)
@pytest.mark.parametrize("hook_seconds,body_start,expected", [(2.38, 5, "pass"), (2.38, 4, "fail"), (2.4, 5, "pass")])
def test_60fps_hook_opening_uses_frame_boundary(movies, hook_seconds, body_start, expected):
    from app.render.render_normal import build_render_normal_command

    source, candidate, _transform, folder = movies
    candidate.start, candidate.end, candidate.duration = 5, 9, 4
    candidate.hook_scene_start, candidate.hook_scene_end = 5.2, 5.2 + hook_seconds
    output = folder / "hook-60fps.mp4"
    subprocess.run(build_render_normal_command(source, output, body_start, body_start + 4,
        hook_scene_start=candidate.hook_scene_start, hook_scene_end=candidate.hook_scene_end),
        check=True, capture_output=True, timeout=60)
    check = media.inspect_opening(output, candidate, source)
    assert check.outcome == expected, check
    hook, body = check.evidence["pieces"]
    assert hook["alignmentOffsetSeconds"] == 0
    assert hook["correlation"] >= media.OPENING_CORRELATION_MIN
    boundary = 143 / 60 if hook_seconds == 2.38 else 2.4
    assert body["readStartSeconds"] == pytest.approx(boundary)
    assert body["alignmentOffsetSeconds"] == pytest.approx(boundary - hook_seconds)
    assert body["maxAlignmentSeconds"] == pytest.approx(1 / 60)
    if hook_seconds == 2.4:
        assert body["correlation"] == body["rawCorrelation"]
    elif expected == "pass":
        assert body["rawCorrelation"] < media.OPENING_CORRELATION_MIN <= body["correlation"]


def test_frame_alignment_is_skipped_if_boundary_exceeds_50ms(monkeypatch):
    import numpy as np

    reads = []

    def samples(path, start, duration):
        reads.append((path, start))
        return np.arange(8000)

    monkeypatch.setattr(media, "audio_samples", samples)
    monkeypatch.setattr(media, "probe_metadata", lambda _: VideoMetadata(None, None, None, 10, True))
    candidate = Candidate(id="slow", type="short", start=1, end=5, duration=4, transcript_text="",
                          hook_scene_start=2, hook_scene_end=3.01)
    result = media.inspect_opening("output", candidate, "source")
    body = result.evidence["pieces"][1]
    assert body["maxAlignmentSeconds"] == 0.05
    assert body["alignmentOffsetSeconds"] == 0
    assert [start for path, start in reads if path == "output"] == pytest.approx([0, 1.01])


def test_real_black_mp4_is_repaired_and_reinspected_through_the_controller(movies):
    from types import SimpleNamespace
    import json
    from PIL import Image
    from app.candidates.select_candidates import CandidateSelection
    from app.inspection.content import ContentReview
    from app.inspection.service import inspect_final_outputs
    from app.storage.paths import StoragePaths

    source, candidate, transform, folder = movies
    output = transform("-vf", "drawbox=color=black:t=fill")
    image = folder / "thumbnail.jpg"
    Image.new("RGB", (640, 360), "blue").save(image)
    metadata = folder / "output.json"
    metadata.write_text(json.dumps({"thumbnail_path": str(image), "thumbnail_status": "ready"}), encoding="utf-8")
    export = SimpleNamespace(job_id="job_real", candidate_id=candidate.id, title="", video_path=str(output), metadata_path=str(metadata))
    paths = StoragePaths(folder)
    calls = []

    def repair(id, action):
        calls.append((id, action))
        shutil.copyfile(source, output)
        return export, candidate

    reviewer = SimpleNamespace(
        generate=lambda payload, images: ContentReview.model_validate(
            {
                "findings": [
                    {"kind": kind, "outcome": "pass", "reason": "supported", "evidence_ids": ["output-0", "thumbnail"]}
                    for kind in ("content", "thumbnail")
                ]
            }
        )
    )
    result = inspect_final_outputs(
        exports=[export],
        selection=CandidateSelection(normalClips=[candidate]),
        source=source,
        segments=[],
        settings={"burnSubtitles": False},
        video=SimpleNamespace(width=640, height=360),
        paths=paths,
        job_id="job_real",
        repair=repair,
        selector=reviewer,
    )
    record = json.loads(paths.final_output_inspection("job_real", candidate.id).read_text(encoding="utf-8"))
    assert result == [export] and calls == [(candidate.id, "rerender_same")]
    assert record["outcome"] == "pass" and len(record["attempts"]) == 2
    assert any(c["code"] == "BLACK_INTERVAL" and c["outcome"] == "fail" for c in record["attempts"][0]["checks"])
    assert all(c["outcome"] == "pass" for c in record["attempts"][1]["checks"])


def test_output_decode_failure_is_repairable_but_missing_source_comparison_is_not(movies, monkeypatch):
    source, candidate, _transform, _folder = movies

    def decode(path, **kwargs):
        raise subprocess.CalledProcessError(1, "ffmpeg")

    monkeypatch.setattr(media, "anomalies", decode)
    _, checks = media.inspect_media(source, candidate, dimensions=(640, 360), source=source)
    assert checks[-1].code == "MEDIA_UNREADABLE" and checks[-1].outcome == "fail"
    calls = []

    def only_output(path, **kwargs):
        calls.append(path)
        if len(calls) > 1:
            raise FileNotFoundError("synthetic unavailable source")
        return {"BLACK_INTERVAL": [], "FREEZE_INTERVAL": [], "SILENCE_INTERVAL": []}

    monkeypatch.setattr(media, "anomalies", only_output)
    _, checks = media.inspect_media(source, candidate, dimensions=(640, 360), source=source)
    assert checks[-1].code == "SOURCE_SCAN_UNAVAILABLE" and checks[-1].outcome == "unknown"
