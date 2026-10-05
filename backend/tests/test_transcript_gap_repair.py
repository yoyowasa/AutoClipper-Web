import json
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest
from fastapi.testclient import TestClient

from test_api_routes import client as client
from test_subtitle_bulk_correction import seed_review
from app.audio.transcript_gap_repair import repair_transcript_gaps
from app.audio.transcript_postprocess import postprocess_transcript_segments, repair_known_transcript_artifact_segments
from app.audio.transcript_repair_merge import merge_repair
from app.audio.transcribe_faster_whisper import (
    FasterWhisperTranscriptionEngine, TranscriptSegment, TranscriptWord, write_transcript_segments,
)
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.jobs.subtitle_review import build_subtitle_review, load_subtitle_review, write_subtitle_review
from app.jobs.summaries import build_transcript_summary
from app.audio.silence_detect import write_silence_segments


def segment(start: float, end: float, text: str, **kwargs) -> TranscriptSegment:
    return TranscriptSegment(start=start, end=end, text=text,
                             words=[TranscriptWord(start=start, end=end, word=text)], **kwargs)


def wav(tmp_path: Path, duration: float = 40) -> Path:
    path = tmp_path / "audio.wav"
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(b"\0\0" * int(duration * 16000))
    return path


class Model:
    def __init__(self, reread, fail=False):
        self.reread = reread
        self.fail = fail
        self.calls = []

    def transcribe(self, path, **options):
        with wave.open(path, "rb") as reader:
            self.calls.append((reader.getnframes() / reader.getframerate(), options))
        if self.fail:
            raise RuntimeError("fake repair failed")
        return [SimpleNamespace(**{**item.model_dump(), "words": [SimpleNamespace(**word.model_dump())
                              for word in (item.words or [])]}) for item in self.reread], None


def test_only_gap_is_reread_once_with_padding_and_original_text_is_preserved(tmp_path):
    baseline = [segment(0, 1, "前。"), segment(31, 40, "直後。")]
    # One decoded segment spans padding; only its words inside the gap are accepted.
    reread = TranscriptSegment(start=0, end=34, text="前 補った発話 直後", words=[
        TranscriptWord(start=0, end=1, word="前"), TranscriptWord(start=4, end=10, word="補った"),
        TranscriptWord(start=10, end=28, word="発話"), TranscriptWord(start=33, end=34, word="直後")])
    model = Model([reread])
    result, summary = repair_transcript_gaps(wav(tmp_path), lambda: model, baseline, duration=40, silence=[])
    assert len(model.calls) == 1
    assert model.calls[0] == (33, dict(language=None, beam_size=5, word_timestamps=True,
                                    vad_filter=False, condition_on_previous_text=False))
    assert [item.text for item in result] == ["前。", "補った発話", "直後。"]
    assert [(item.start, item.end) for item in result] == [(0, 1), (4, 28), (31, 40)]
    assert result[1].repaired and result[1].repair_windows[0].model_dump() == {"start": 0, "end": 33}
    assert not result[0].repaired and not result[2].repaired
    assert summary["repaired_segment_count"] == summary["added_segment_count"] == 1
    assert summary["added_characters"] == len("補った発話")
    assert summary["reread_interval_count"] == 1 and summary["reread_seconds"] == 33
    assert summary["elapsed_seconds"] >= 0
    assert baseline[1].text == "直後。" and not baseline[1].repaired


@pytest.mark.parametrize("gap,expected", [(2.999, 0), (3, 1)])
def test_word_gap_boundary_and_silence_subtraction(tmp_path, gap, expected):
    model = Model([])
    baseline = [segment(0, 1, "前"), segment(1 + gap, 10, "後")]
    _, summary = repair_transcript_gaps(wav(tmp_path, 10), lambda: model, baseline, duration=10, silence=[])
    assert summary["reread_interval_count"] == expected
    model = Model([])
    _, summary = repair_transcript_gaps(wav(tmp_path, 10), lambda: model, baseline, duration=10, silence=[(1, 1 + gap)])
    assert summary["reread_interval_count"] == 0


def test_uses_word_times_even_when_segment_envelope_covers_gap(tmp_path):
    baseline = [TranscriptSegment(start=0, end=40, text="前後", words=[
        TranscriptWord(start=0, end=1, word="前"), TranscriptWord(start=31, end=40, word="後")])]
    model = Model([])
    _, summary = repair_transcript_gaps(wav(tmp_path), lambda: model, baseline, duration=40, silence=[])
    assert summary["planned_interval_count"] == 1 and model.calls[0][0] == 33


@pytest.mark.parametrize("overlap", [False, True])
def test_following_identical_sentence_retimes_without_changing_text_or_overlapping(overlap):
    original = [segment(0, 1, "前").model_dump(), segment(31, 40, "直後。").model_dump()]
    if overlap:
        original.insert(1, segment(29, 30, "別の既存字幕").model_dump())
    reread = [segment(29, 32, "直後").model_dump()]
    result, summary = merge_repair(original, reread, window=(0, 40), gaps=[(1, 31)], preserve_existing=True)
    following = next(item for item in result if item["text"] == "直後。")
    assert following["start"] == (31 if overlap else 29)
    assert following["end"] == (40 if overlap else 32)
    assert following["repaired"] is (not overlap)
    assert summary["retimed_segments"] == (0 if overlap else 1)
    assert len(result) == len(original)


def test_only_immediately_following_sentence_is_eligible_for_retiming():
    original = [segment(0, 1, "前").model_dump(), segment(31, 33, "直後").model_dump(),
                segment(33, 40, "その先").model_dump()]
    result, summary = merge_repair(original, [segment(20, 21, "前").model_dump()],
                                   window=(0, 40), gaps=[(1, 31)], preserve_existing=True)
    assert result[0] == original[0] and summary["retimed_segments"] == 0


def test_unchanged_timing_is_not_marked_as_repaired():
    baseline = [segment(31, 40, "直後。").model_dump()]
    result, summary = merge_repair(baseline, [segment(31, 40, "直後").model_dump()],
                                   window=(0, 40), gaps=[(0, 31)], preserve_existing=True)
    assert result == baseline and summary["retimed_segments"] == 0


def test_repair_failure_keeps_original_and_records_summary(tmp_path):
    baseline = [segment(0, 1, "前"), segment(31, 40, "後")]
    model = Model([], fail=True)
    result, summary = repair_transcript_gaps(wav(tmp_path), lambda: model, baseline, duration=40, silence=[])
    assert result == baseline and all(not item.repaired for item in baseline)
    assert summary["status"] == "failed" and summary["error_type"] == "RuntimeError"
    assert summary["reread_interval_count"] == 1 and summary["added_characters"] == 0
    transcript_summary = build_transcript_summary(result, transcription_engine="faster_whisper",
        used_fixture_transcript=False, transcription_diagnostics={"gap_repair": summary})
    assert transcript_summary["gap_repair"] == summary


def test_failure_after_first_window_does_not_publish_partial_repairs(tmp_path):
    baseline = [segment(0, 1, "前"), segment(10, 20, "中"), segment(31, 40, "後")]
    model = Model([segment(3, 4, "追加")])
    call = model.transcribe
    def fail_second(path, **options):
        if len(model.calls) == 1:
            raise RuntimeError("second window")
        return call(path, **options)
    model.transcribe = fail_second
    result, summary = repair_transcript_gaps(wav(tmp_path), lambda: model, baseline, duration=40, silence=[])
    assert result == baseline and summary["status"] == "failed" and summary["added_segment_count"] == 0


def test_missing_word_times_skips_without_loading_model(tmp_path):
    def fail_load():
        pytest.fail("must not load a model")
    baseline = [TranscriptSegment(start=0, end=1, text="legacy")]
    result, summary = repair_transcript_gaps(wav(tmp_path), fail_load, baseline, duration=40, silence=[])
    assert result == baseline and summary["reason"] == "word_timestamps_unavailable"


def test_engine_reuses_model_and_base_transcription_keeps_default_context(tmp_path, monkeypatch):
    model = Model([segment(0, 1, "前"), segment(31, 40, "後")])
    engine = FasterWhisperTranscriptionEngine(language="ja")
    engine._model = model
    monkeypatch.setattr(engine, "_resolve_runtime", lambda: SimpleNamespace(actual_device="cpu"))
    baseline = engine.transcribe(wav(tmp_path))
    assert "condition_on_previous_text" not in model.calls[0][1]
    engine.repair_gaps(wav(tmp_path), baseline, duration=40, silence=[])
    assert len(model.calls) == 2 and model.calls[1][1]["condition_on_previous_text"] is False


def test_provenance_survives_postprocessing_storage_and_review(tmp_path):
    transcript = [segment(0, 1, "前"), segment(1, 31, "補修された字幕", repaired=True,
                  repairWindows=[{"start": 0, "end": 33}]), segment(31, 40, "後")]
    processed = postprocess_transcript_segments(transcript, {}).segments
    processed = repair_known_transcript_artifact_segments(processed)
    path = write_transcript_segments(processed, tmp_path / "transcript_segments.json")
    restored = [TranscriptSegment.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]
    assert restored[1].repaired and restored[1].repair_windows == transcript[1].repair_windows
    selection = CandidateSelection(normalClips=[Candidate(id="clip", type="normal", start=0, end=40, duration=40, transcript_text="字幕")])
    review = build_subtitle_review("job", selection, restored)
    write_silence_segments([], tmp_path / "silence_segments.json")
    review_path = write_subtitle_review(review, tmp_path / "subtitle_review.json")
    loaded = load_subtitle_review(review_path)
    assert loaded.clips[0].gaps == []
    repaired_rows = [row for row in loaded.segments if row.repaired]
    assert repaired_rows and all(row.repair_windows == transcript[1].repair_windows for row in repaired_rows)
    payload = loaded.model_dump(by_alias=True, mode="json")
    assert any(row["repaired"] and row["repairWindows"] for row in payload["segments"])


def test_review_api_returns_repair_provenance(client: TestClient):  # noqa: F811
    job_id, path, _ = seed_review(client)
    document = load_subtitle_review(path)
    document.segments[0].repaired = True
    from app.audio.transcribe_faster_whisper import RepairWindow
    document.segments[0].repair_windows = [RepairWindow(start=0, end=33)]
    write_subtitle_review(document, path)
    response = client.get(f"/api/jobs/{job_id}/subtitle-review")
    assert response.status_code == 200
    assert response.json()["segments"][0]["repaired"]
    assert response.json()["segments"][0]["repairWindows"] == [{"start": 0, "end": 33}]


@pytest.mark.parametrize("repair_failure,silence_failure", [(False, False), (True, False), (False, True)])
def test_pipeline_repairs_once_before_postprocess_and_continues_on_failure(client, monkeypatch, repair_failure, silence_failure):  # noqa: F811
    from test_real_pipeline import fake_transcript
    from app.audio.volume_features import build_audio_features
    from app.db import get_db
    from app.main import app
    from app.jobs.pipeline_common import AutoClipperPipelineDependencies
    import app.jobs.runner as runner
    from app.storage.paths import get_storage_paths
    from app.video.probe import VideoMetadata
    from app.video.scene_detect import SceneSegment

    upload = client.post("/api/videos/upload", files={"file": ("test.mp4", b"video", "video/mp4")}).json()
    created = client.post("/api/jobs", json={"videoId": upload["videoId"], "settings": {
        "normalClipCount": 1, "shortCount": 0, "selectionMode": "content", "initialSelectionMode": "automatic",
        "requireClipPlanReview": False, "transcriptNormalizeFullwidth": False,
        "transcriptReplacements": {"gaprepair": "afterpostprocess"},
    }}).json()
    events = []
    class Engine:
        diagnostics = {"actual_device": "cpu"}
        def __init__(self, **options):
            pass
        def transcribe(self, path):
            events.append("transcribe")
            return fake_transcript()
        def repair_gaps(self, path, baseline, **options):
            events.append("repair")
            if repair_failure:
                raise RuntimeError("fake failure")
            return [*baseline, segment(211, 220, "gaprepair", repaired=True,
                                      repairWindows=[{"start": 208, "end": 224}])], {"status": "completed"}

    original_postprocess = runner.postprocess_transcript_segments
    def postprocess(segments, settings):
        events.append("postprocess")
        return original_postprocess(segments, settings)
    monkeypatch.setattr(runner, "postprocess_transcript_segments", postprocess)
    def extract(source, output):
        Path(output).write_bytes(b"fake audio")
    def silence(path, duration):
        if silence_failure:
            raise RuntimeError("fake silence failure")
        return []
    def preview(source, output, **options):
        Path(output).write_bytes(b"fake preview")
        return Path(output)
    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda path: VideoMetadata(duration=240, width=1920, height=1080, fps=30, has_audio=True),
        extract_audio=extract, transcription_engine_factory=Engine, detect_silence=silence,
        compute_audio_features=lambda path, duration, silence: build_audio_features(duration, silence, 0.5),
        detect_scenes=lambda path: [SceneSegment(start=0, end=240)], detect_black_screen=lambda path: [],
        normal_renderer=preview, short_renderer=preview,
    )
    storage = app.dependency_overrides[get_storage_paths]()
    states = runner.run_autoclipper_job(created["jobId"], session_factory=lambda: next(app.dependency_overrides[get_db]()),
                                       paths=storage, dependencies=dependencies)
    assert states[-1] == "completed"
    assert events == (["transcribe", "postprocess"] if silence_failure else ["transcribe", "repair", "postprocess"])
    output = storage.job_outputs(created["jobId"])
    summary = json.loads((output / "transcript_summary.json").read_text(encoding="utf-8"))
    assert summary["gap_repair"]["status"] == ("skipped" if silence_failure else "failed" if repair_failure else "completed")
    raw = json.loads((output / "raw_transcript_segments.json").read_text(encoding="utf-8"))
    saved = json.loads((output / "transcript_segments.json").read_text(encoding="utf-8"))
    if not repair_failure and not silence_failure:
        assert raw[-1]["text"] == "gaprepair" and saved[-1]["text"] == "afterpostprocess"
        assert raw[-1]["repaired"] and saved[-1]["repaired"]
    else:
        assert len(raw) == len(fake_transcript())


@pytest.mark.parametrize("duration", [None, 7200, 10800])
def test_initial_timeout_reserves_primary_and_repair_audio_passes(tmp_path, monkeypatch, duration):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db import Base
    from app.models import Job, Video
    from app.storage.paths import StoragePaths
    import app.jobs.timeouts as timeouts

    engine = create_engine("sqlite:///" + (tmp_path / "test.db").as_posix())
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    monkeypatch.setattr(timeouts, "SessionLocal", factory)
    monkeypatch.setattr(timeouts, "get_storage_paths", lambda: StoragePaths(tmp_path))
    with factory() as db:
        db.add(Video(id="video", original_filename="test.mp4", stored_path="test.mp4", duration=duration))
        db.add(Job(id="job", video_id="video", settings_json={"normalClipCount": 1, "shortCount": 0}))
        db.commit()
    render_budget = timeouts.media_timeout(1800)
    assert timeouts.job_media_timeout("job", selection=True) == render_budget
    assert timeouts.job_media_timeout("job") == render_budget + 2 * (duration or 10800)



def test_quality_fallback_releases_previous_model_and_repairs_selected_engine(tmp_path):
    from app.jobs.runner import _transcribe_with_faster_whisper
    events = []
    class Engine:
        diagnostics = {}
        def __init__(self, **kwargs):
            events.append("create")
        def transcribe(self, path):
            return []
        def release_model(self):
            events.append("release")
    engines = []
    options = dict(model="turbo", language="ja", device="cpu", compute_type="auto", engines=engines)
    _transcribe_with_faster_whisper(Engine, tmp_path / "unused.wav", **options)
    first = engines[0]
    _transcribe_with_faster_whisper(Engine, tmp_path / "unused.wav", **options)
    assert events == ["create", "release", "create"]
    assert len(engines) == 1 and engines[0] is not first


def test_one_segment_without_words_does_not_disable_repair_elsewhere(tmp_path):
    baseline = [TranscriptSegment(start=0, end=1, text="no words"), segment(31, 40, "後")]
    model = Model([segment(4, 7, "追加")])
    result, summary = repair_transcript_gaps(wav(tmp_path), lambda: model, baseline, duration=40, silence=[])
    assert summary["status"] == "completed" and summary["segments_without_word_timestamps"] == 1
    assert summary["added_segment_count"] == 1
    assert result[0] == baseline[0] and result[1].repaired


def test_retime_cannot_escape_reread_window():
    original = [segment(31, 40, "後").model_dump()]
    result, summary = merge_repair(original, [segment(29, 45, "後").model_dump()],
                                   window=(0, 40), gaps=[(0, 31)], preserve_existing=True)
    assert result == original and summary["skipped_retimes"][0]["reason"] == "outside_reread_window"


def test_partial_repair_leaves_only_remaining_audible_gap_markers(tmp_path):
    baseline = [segment(0, 1, "前"), segment(31, 40, "後")]
    repaired, _ = repair_transcript_gaps(wav(tmp_path), lambda: Model([segment(4, 28, "補修")]),
                                       baseline, duration=40, silence=[])
    selection = CandidateSelection(normalClips=[Candidate(id="clip", type="normal", start=0, end=40,
                                                          duration=40, transcript_text="字幕")])
    write_silence_segments([], tmp_path / "silence_segments.json")
    path = tmp_path / "subtitle_review.json"
    before = build_subtitle_review("job", selection, baseline)
    write_subtitle_review(before, path)
    assert [(gap.start, gap.end) for gap in load_subtitle_review(path).clips[0].gaps] == [(1, 31)]
    after = build_subtitle_review("job", selection, repaired)
    write_subtitle_review(after, path)
    assert [(gap.start, gap.end) for gap in load_subtitle_review(path).clips[0].gaps] == [(1, 4), (28, 31)]
