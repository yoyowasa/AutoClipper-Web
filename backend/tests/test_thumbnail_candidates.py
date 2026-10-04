import json
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import shutil
import subprocess

import numpy as np
from PIL import Image
import pytest

from app.jobs import thumbnail_candidates as candidates
from app.jobs.queue import get_enqueue_thumbnail_candidates, get_enqueue_thumbnail_preview, get_enqueue_thumbnail_regeneration
from app.jobs.thumbnail_regeneration import run_export_thumbnail_regeneration
from app.jobs.thumbnails import write_export_metadata
from app.models import ExportItem, Job
from app.storage.paths import StoragePaths
from app.main import app
from app.render.video_subject_layout import place_video_subject, video_subject_layout
from app.render import render_thumbnail as renderer
from test_api_routes import client as client
from test_thumbnail_character_assets import add_asset, asset_thumbnail as asset_thumbnail, generate_batch
from test_thumbnail_text_styles import TEXT_STYLES, seed_thumbnail, real_test_renderer


ENDPOINT = "/api/exports/exp_thumbnail_style/thumbnail"
FACE = (.5, .3, .15, .18)


def noisy_image(size=(960, 540)):
    return Image.fromarray(np.random.default_rng(123).integers(0, 256, (size[1], size[0], 3), dtype=np.uint8))


def seed_frames(storage, metadata, *, close=True):
    frames = [{"id": f"frame_{i:02d}", "second": second, "face": list(FACE), "score": 3 - i * .1,
               "width": 1920, "height": 1080, "close_available": close} for i, second in enumerate((4., 8., 12.))]
    directory = candidates.candidate_directory(storage.job_outputs("job_thumbnail_style"), "exp_thumbnail_style")
    directory.mkdir(parents=True, exist_ok=True)
    for frame in frames:
        Image.new("RGB", (1920, 1080), "#669977").save(directory / f'{frame["id"]}.jpg')
        Image.new("RGB", (240, 135), "#669977").save(directory / f'{frame["id"]}.small.jpg')
    saved = json.loads(metadata.read_text(encoding="utf-8"))
    saved.update(thumbnail_candidates_version=1, thumbnail_frame_candidates=frames,
                 thumbnail_frame_candidate_id=frames[0]["id"])
    write_export_metadata(metadata, saved)
    return frames


def test_scoring_size_margins_sharpness_and_centrality():
    image = noisy_image()
    def score(face):
        result = candidates.evaluate_thumbnail_frame(image, 1, (1920, 1080), detector=lambda _: face)
        return result.score if result else None
    assert score((.5, .3, .15, .18)) > score((.8, .3, .15, .18))
    assert score((.5, .3, .15, .18)) > score((.5, .3, .1, .12))
    assert score((.5, .02, .1, .12)) is None  # no top margin
    assert score((.5, .9, .1, .12)) is None  # chest outside source
    assert score((.5, .3, .03, .05)) is None  # enlargement exceeds two
    assert candidates.evaluate_thumbnail_frame(Image.new("RGB", image.size), 0, (1920, 1080), detector=lambda _: FACE) is None


def test_thinning_similar_nearby_frames_scores_and_twelve_limit():
    pool = [candidates.ThumbnailFrameCandidate(i * 5., FACE, 30 - i, i) for i in range(20)]
    pool += [candidates.ThumbnailFrameCandidate(.5, FACE, 100, 0)]
    result = candidates.thin_thumbnail_candidates(pool)
    assert len(result) == 12 and result[0].second == .5
    assert 0 not in [c.second for c in result]
    assert [c.score for c in result] == sorted([c.score for c in result], reverse=True)


@pytest.mark.parametrize("design", ["raden", "sopia"])
def test_bust_close_layout_and_adjustment(design):
    frame = renderer._load_template(renderer.DEFAULT_NORMAL_TEMPLATE_PATH if design == "raden" else
                                    renderer.SOPIA_NORMAL_TEMPLATE_PATH)["frame"]
    bust = video_subject_layout((1920, 1080), FACE, frame)
    close = video_subject_layout((1920, 1080), FACE, frame, mode="close")
    assert bust.fits and close.fits
    assert (FACE[1] * 1080 - bust.top) / bust.crop_height == pytest.approx(.3)
    assert bust.top + bust.crop_height == pytest.approx((FACE[1] + FACE[3] * 2.5) * 1080)
    assert FACE[3] * 1080 / close.crop_height == pytest.approx(.45)
    adjusted = video_subject_layout((1920, 1080), FACE, frame, scale=1.2, offset_x=20, offset_y=-30)
    assert adjusted.upscale == pytest.approx(bust.upscale * 1.2)
    assert adjusted.top == pytest.approx(FACE[1] * 1080 - adjusted.crop_height * .3 + 30 / adjusted.upscale)
    layer = place_video_subject(noisy_image((1920, 1080)), FACE, frame)
    assert layer.size == (frame["width"], frame["height"])


def test_exact_two_upscale_and_close_unavailable():
    fh = 720 / (2 * 1080) * .7 / 2.5
    assert video_subject_layout((1920, 1080), (.5, .3, .1, fh), candidates.PERSON_FRAME).fits
    assert not video_subject_layout((1920, 1080), (.5, .3, .1, fh - .0001), candidates.PERSON_FRAME).fits
    assert not video_subject_layout((1920, 1080), (.5, .3, .1, .12), candidates.PERSON_FRAME, mode="close").fits


def test_extraction_range_score_order_and_cached_images(tmp_path, monkeypatch):
    monkeypatch.setattr(candidates, "probe_metadata", lambda _: SimpleNamespace(width=1920, height=1080))
    calls = []
    def scanner(source, start, end, size):
        calls.append((start, end, size))
        for second in (0., .5, 5., 10.):
            yield second, noisy_image()
    extracted = []
    def extractor(source, path, second):
        extracted.append(second)
        noisy_image((1920, 1080)).save(path)
    saved = candidates.extract_thumbnail_candidates("source", clip_start=100, clip_end=120, directory=tmp_path,
                                                   scanner=scanner, extractor=extractor, detector=lambda _: FACE)
    assert calls == [(100, 120, (1920, 1080))]
    assert len(saved) == 3 and all(c["close_available"] for c in saved)
    assert extracted == [100., 105., 110.]
    assert len(list(tmp_path.glob("*.jpg"))) == 6
    assert Image.open(tmp_path / "frame_00.small.jpg").size == (240, 135)


def test_numpy_detector_values_are_saved_as_plain_json(tmp_path, monkeypatch):
    # OpenCV-backed detectors yield NumPy scalars; comparisons on them produce numpy.bool, which json cannot encode.
    numpy_face = tuple(np.float64(value) for value in FACE)
    assert type(video_subject_layout((1920, 1080), numpy_face, candidates.PERSON_FRAME, mode="close").fits) is bool
    monkeypatch.setattr(candidates, "probe_metadata", lambda _: SimpleNamespace(width=1920, height=1080))
    def scanner(source, start, end, size):
        yield 0., noisy_image()
    def extractor(source, path, second):
        noisy_image((1920, 1080)).save(path)
    saved = candidates.extract_thumbnail_candidates("source", clip_start=0, clip_end=10, directory=tmp_path,
                                                   scanner=scanner, extractor=extractor, detector=lambda _: numpy_face)
    assert len(saved) == 1
    json.dumps(saved)
    candidate = saved[0]
    assert type(candidate["close_available"]) is bool
    assert all(type(value) is float for value in [candidate["second"], candidate["score"], *candidate["face"]])


def test_legacy_export_queues_once_worker_persists_even_empty_and_http_never_scans(client, monkeypatch):  # noqa: F811
    storage, factory, metadata, thumbnail, video = seed_thumbnail(client)
    queue, scans = [], []
    app.dependency_overrides[get_enqueue_thumbnail_candidates] = lambda: lambda *args: queue.append(args)
    def extract(*args, **kwargs):
        scans.append(kwargs)
        return []
    monkeypatch.setattr(candidates, "extract_thumbnail_candidates", extract)
    before = metadata.read_bytes()
    for _ in range(2):
        assert client.post(ENDPOINT + "/candidates/prepare").json()["state"] == "queued"
    assert len(queue) == 1 and not scans and metadata.read_bytes() == before
    for _ in range(2):
        candidates.run_thumbnail_candidate_extraction(*queue[0], session_factory=factory, paths=storage)
    assert len(scans) == 1 and scans[0]["clip_start"] == 10 and scans[0]["clip_end"] == 30
    ready = client.post(ENDPOINT + "/candidates/prepare").json()
    assert ready["state"] == "ready" and ready["candidates"] == [] and ready["reason"]
    assert json.loads(metadata.read_text(encoding="utf-8"))["thumbnail_candidates_version"] == 1
    assert len(queue) == 1


def test_cached_candidate_preview_and_next_frame_never_reread_video(client, monkeypatch):  # noqa: F811
    storage, factory, metadata, thumbnail, video = seed_thumbnail(client)
    frames = seed_frames(storage, metadata)
    queue = []
    app.dependency_overrides[get_enqueue_thumbnail_preview] = lambda: lambda *args: pytest.fail("cached preview enqueued video work")
    app.dependency_overrides[get_enqueue_thumbnail_regeneration] = lambda: lambda *args: queue.append(args)
    monkeypatch.setattr(renderer, "extract_thumbnail_frame", lambda *args, **kwargs: pytest.fail("video reread"))
    monkeypatch.setattr(candidates, "extract_thumbnail_candidates", lambda *args, **kwargs: pytest.fail("scan repeated"))
    prepared = client.post(ENDPOINT + "/preview/prepare?frameCandidateId=frame_01").json()
    assert prepared["state"] == "ready"
    response = client.post(ENDPOINT + "/preview", json={"frameKey": prepared["frameKey"], "frameCandidateId": "frame_01",
                                                       "cropMode": "close", "text": {"heading": "", "upper": "人物", "lower": ""},
                                                       "textStyles": TEXT_STYLES})
    assert response.status_code == 200
    assert client.get(ENDPOINT + "/candidates/frame_01/image").status_code == 200
    assert client.get(ENDPOINT + "/candidates/../image").status_code == 404
    assert client.post(ENDPOINT + "/regenerate", json={"frameSeconds": 4, "advanceFrame": True}).status_code == 202
    seen = {}
    def render(*args, **kwargs):
        seen.update(kwargs)
        return real_test_renderer(*args, **kwargs)
    run_export_thumbnail_regeneration(*queue[-1], paths=storage, session_factory=factory, normal_renderer=render,
                                     frame_selector=lambda *a, **k: pytest.fail("legacy search"))
    saved = json.loads(metadata.read_text(encoding="utf-8"))
    assert saved["thumbnail_status"] == "ready" and saved["thumbnail_frame_candidate_id"] == "frame_01"
    assert saved["thumbnail_frame_seconds"] == frames[1]["second"]
    assert seen["video_face"] == FACE and seen["video_crop_mode"] == "standard"
    assert saved["thumbnail_subject_source"] == "video" and saved["thumbnail_subject_reason"]


def test_close_outside_upscale_limit_rejected_and_old_modes_read_without_write(client):  # noqa: F811
    storage, _, metadata, _, _ = seed_thumbnail(client)
    seed_frames(storage, metadata, close=False)
    assert client.post(ENDPOINT + "/regenerate", json={
        "frameSeconds": 4, "frameCandidateId": "frame_00", "cropMode": "close",
    }).status_code == 422
    before = metadata.read_bytes()
    result = client.get("/api/jobs/job_thumbnail_style/results").json()["normalClips"][0]
    assert result["thumbnailCropMode"] == "close"
    assert metadata.read_bytes() == before


@pytest.mark.parametrize("with_assets", [False, True])
def test_video_has_priority_even_when_assets_registered(asset_thumbnail, monkeypatch, with_assets):  # noqa: F811
    storage = asset_thumbnail.storage
    seed_frames(storage, asset_thumbnail.metadata)
    def extract(source, **kwargs):
        # This stub exercises the export pipeline with saved originals, not video decoding.
        source_dir = candidates.candidate_directory(storage.job_outputs("job_thumbnail_style"), "exp_thumbnail_style")
        kwargs["directory"].mkdir(parents=True, exist_ok=True)
        import shutil
        if source_dir != kwargs["directory"]:
            for path in source_dir.glob("*.jpg"):
                shutil.copyfile(path, kwargs["directory"] / path.name)
        return json.loads(asset_thumbnail.metadata.read_text(encoding="utf-8"))["thumbnail_frame_candidates"]
    monkeypatch.setattr(candidates, "extract_thumbnail_candidates", extract)
    # Existing helper forbids video reads only when assets are preferred; disable that guard here.
    if with_assets:
        add_asset(asset_thumbnail)
    _, calls, saved = generate_batch(asset_thumbnail, with_assets=False, monkeypatch=monkeypatch)
    assert all(data["thumbnail_subject_source"] == "video" and data["thumbnail_subject_reason"] for data in saved)
    assert all("video_face" in call and "character_asset_path" not in call for call in calls)


def test_state_polling_does_not_wait_for_scan_lock(client, monkeypatch):  # noqa: F811
    storage, factory, _, _, _ = seed_thumbnail(client)
    queued, entered, release = [], Event(), Event()
    app.dependency_overrides[get_enqueue_thumbnail_candidates] = lambda: lambda *args: queued.append(args)
    assert client.post(ENDPOINT + "/candidates/prepare").json()["state"] == "queued"
    def slow_scan(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return []
    monkeypatch.setattr(candidates, "extract_thumbnail_candidates", slow_scan)
    with ThreadPoolExecutor() as pool:
        work = pool.submit(candidates.run_thumbnail_candidate_extraction, *queued[0], session_factory=factory, paths=storage)
        try:
            assert entered.wait(2)
            # The scan is still running when the HTTP state response arrives.
            assert client.post(ENDPOINT + "/candidates/prepare").json()["state"] == "queued"
            assert not work.done() and len(queued) == 1
        finally:
            release.set()
        work.result()


def test_asset_switch_ignores_video_close_restriction(asset_thumbnail):  # noqa: F811
    context = asset_thumbnail
    seed_frames(context.storage, context.metadata, close=False)
    identifier, _ = add_asset(context)
    queue = []
    app.dependency_overrides[get_enqueue_thumbnail_regeneration] = lambda: lambda *args: queue.append(args)
    response = context.api.post(ENDPOINT + "/regenerate", json={
        "frameSeconds": 4, "cropMode": "close", "subjectSource": "asset", "characterAssetId": identifier,
    })
    assert response.status_code == 202
    run_export_thumbnail_regeneration(*queue[-1], paths=context.storage, session_factory=context.factory,
                                     normal_renderer=real_test_renderer)
    saved = json.loads(context.metadata.read_text(encoding="utf-8"))
    assert saved["thumbnail_status"] == "ready" and saved["thumbnail_subject_source"] == "asset"


def test_cached_frames_participate_in_publication_and_rollback(tmp_path):
    from app.jobs.runner import _promote_subtitle_rerender
    canonical, staged = StoragePaths(tmp_path / "published"), StoragePaths(tmp_path / "staged")
    job_id, export_id = "job_cache", "exp_cache"
    export_dir = staged.job_outputs(job_id)
    video, metadata = export_dir / "normal.mp4", export_dir / "normal.json"
    video.write_bytes(b"new video")
    metadata.write_text('{"thumbnail_status":"failed"}', encoding="utf-8")
    export = ExportItem(id=export_id, job_id=job_id, video_id="vid", type="normal", duration=90, title="clip", score=1,
                        video_path=str(video), metadata_path=str(metadata))
    staged_frames = candidates.candidate_directory(export_dir, export_id)
    staged_frames.mkdir(parents=True)
    canonical_frames = candidates.candidate_directory(canonical.job_outputs(job_id), export_id)
    canonical_frames.mkdir(parents=True)
    for name in ("frame_00.jpg", "frame_00.small.jpg"):
        (staged_frames / name).write_bytes(b"new image")
        (canonical_frames / name).write_bytes(b"old image")
    db = SimpleNamespace(flush=lambda: None, rollback=lambda: None)
    _, _, promotion = _promote_subtitle_rerender(
        db=db, job=Job(id=job_id), previous_exports=[], staged_exports=[export], staging_paths=staged,
        storage_paths=canonical, staged_render_failures_path=export_dir / "render_failures.json",
    )
    assert all(path.read_bytes() == b"new image" for path in canonical_frames.glob("*.jpg"))
    assert not list(staged_frames.glob("*.jpg"))
    promotion.rollback()
    assert all(path.read_bytes() == b"old image" for path in canonical_frames.glob("*.jpg"))


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="FFmpeg is not installed")
def test_ffmpeg_scans_only_clip_at_two_fps_sequentially(tmp_path):
    video = tmp_path / "source.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=10",
                    "-t", "3", "-c:v", "mpeg4", str(video)], check=True)
    frames = list(candidates.sequential_clip_frames(video, 1, 2, (320, 240)))
    assert [second for second, _ in frames] == [0., .5]
    assert all(image.size == (960, 720) for _, image in frames)
