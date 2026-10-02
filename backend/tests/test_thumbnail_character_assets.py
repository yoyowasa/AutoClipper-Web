import json
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

from PIL import Image, ImageDraw
import pytest

from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.jobs.queue import get_enqueue_thumbnail_preview, get_enqueue_thumbnail_regeneration
from app.jobs.thumbnail_character_assets import choose_character_asset
from app.jobs.thumbnail_preview import run_thumbnail_preview_prepare
from app.jobs.thumbnail_regeneration import run_export_thumbnail_regeneration
from app.jobs.thumbnails import generate_export_thumbnails, read_export_metadata, write_export_metadata
from app.main import app
from app.models import CharacterAsset, ExportItem, Job
from app.render.character_asset_layout import ASSET_ROUGH_WARNING, character_asset_layout, place_character_asset
from app.render import render_thumbnail as renderer
from app.scoring.thumbnail_emotion import CodexThumbnailEmotionSelector, EMOTION_SCHEMA, ThumbnailEmotion
from test_api_routes import client as client
from test_thumbnail_text_styles import seed_thumbnail, TEXT_STYLES, real_test_renderer


FACE = {"x": .35, "y": .16, "w": .3, "h": .28}
ENDPOINT = "/api/exports/exp_thumbnail_style/thumbnail"


@pytest.fixture()
def asset_thumbnail(client):  # noqa: F811
    storage, factory, metadata, thumbnail, video = seed_thumbnail(client)
    response = client.put("/api/preferences/character-presets", json={
        "presets": [{"name": "表情素材", "settings": {}}], "selectedName": "表情素材",
    })
    assert response.status_code == 200
    preset_id = response.json()["presets"][0]["id"]
    with factory() as db:
        db.get(Job, "job_thumbnail_style").settings_json = {"characterPresetId": preset_id}
        db.commit()
    return SimpleNamespace(api=client, storage=storage, factory=factory, preset=preset_id,
                           metadata=metadata, thumbnail=thumbnail, video=video)


def add_asset(context, emotion="joy", slot=1, *, face_box=FACE, preset=None):
    identifier = "asset_" + uuid4().hex
    preset = preset or context.preset
    path = context.storage.character_asset(preset, emotion, identifier)
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (320, 430))
    draw = ImageDraw.Draw(image)
    draw.rectangle((65, 65, 255, 425), fill=(40, 190, 130, 255))
    draw.ellipse((110, 70, 205, 190), fill=(230, 130, 80, 255))
    image.save(path)
    with context.factory() as db:
        db.add(CharacterAsset(id=identifier, preset_id=preset, emotion=emotion, slot=slot,
                              file_path=path.relative_to(context.storage.root).as_posix(), width=320, height=430,
                              face_box=face_box, has_alpha=True, warnings=[]))
        db.commit()
    return identifier, path


class Selector:
    def __init__(self, emotion="anger", fail=False):
        self.emotion, self.fail, self.calls = emotion, fail, []

    def generate(self, payload, images):
        self.calls.append((payload, images))
        if self.fail:
            raise RuntimeError("unavailable")
        return {"emotion": self.emotion, "reason": "驚きを語る字幕と文言に合います。"}


def choose(context, selector):
    with context.factory() as db:
        export = db.get(ExportItem, "exp_thumbnail_style")
        return choose_character_asset(db, context.storage, db.get(Job, export.job_id), export,
                                      read_export_metadata(export), selector=selector)


def test_only_one_emotion_skips_codex_and_legacy_preset_name_works(asset_thumbnail):
    identifier, _ = add_asset(asset_thumbnail, "fun")
    selector = Selector(fail=True)
    with asset_thumbnail.factory() as db:
        db.get(Job, "job_thumbnail_style").settings_json = {"characterPresetName": "表情素材"}
        db.commit()
    chosen = choose(asset_thumbnail, selector)
    assert chosen.asset.id == identifier and chosen.asset.emotion == "fun"
    assert chosen.selection_source == "single_emotion" and selector.calls == []


def test_codex_gets_only_text_and_registered_emotions_and_nearby_subtitles(asset_thumbnail):
    add_asset(asset_thumbnail)
    identifier, _ = add_asset(asset_thumbnail, "anger")
    (asset_thumbnail.metadata.parent.parent / "reviewed_transcript_segments.json").write_text(json.dumps([
        {"start": 0, "end": 2, "text": "遠い字幕"}, {"start": 12, "end": 16, "text": "びっくりした"},
    ]), encoding="utf-8")
    selector = Selector()
    chosen = choose(asset_thumbnail, selector)
    payload, images = selector.calls[0]
    assert payload["availableEmotions"] == ["joy", "anger"] and images == []
    assert payload["nearbySubtitles"] == ["びっくりした"]
    assert payload["videoTitle"] == "サムネ書式確認" and payload["thumbnailText"]["upper"] == "上行"
    assert chosen.asset.id == identifier and chosen.selection_source == "codex"


@pytest.mark.parametrize("emotion,fail", [("anger", True), ("sorrow", False), ("neutral", False)])
def test_failed_or_unregistered_emotion_is_visible_fallback(asset_thumbnail, emotion, fail):
    identifier, _ = add_asset(asset_thumbnail)
    add_asset(asset_thumbnail, "anger")
    chosen = choose(asset_thumbnail, Selector(emotion, fail))
    assert chosen.asset.id == identifier and chosen.selection_source == "fallback"
    assert chosen.warnings == ["表情を自動で選べませんでした（仮に喜を使用）"]
    assert chosen.metadata()["thumbnail_emotion_reason"]


def test_asset_rotation_uses_last_publication_time_and_other_characters_do_not_count(asset_thumbnail):
    first, _ = add_asset(asset_thumbnail)
    second, _ = add_asset(asset_thumbnail, slot=2)
    data = json.loads(asset_thumbnail.metadata.read_text(encoding="utf-8"))
    data.update(thumbnail_character_preset_id=asset_thumbnail.preset, thumbnail_character_asset_id=first,
                thumbnail_character_asset_used_at="2026-10-02T12:00:00")
    write_export_metadata(asset_thumbnail.metadata, data)
    assert choose(asset_thumbnail, Selector()).asset.id == second
    data["thumbnail_character_preset_id"] = "another-character"
    write_export_metadata(asset_thumbnail.metadata, data)
    assert choose(asset_thumbnail, Selector()).asset.id == first


@pytest.mark.parametrize("design", ["raden", "sopia"])
@pytest.mark.parametrize("size", [(320, 430), (800, 320), (400, 400)], ids=["portrait", "landscape", "square"])
def test_complete_asset_fits_frame_preserves_center_and_bottom_for_both_templates(design, size):
    template = renderer._load_template(renderer.DEFAULT_NORMAL_TEMPLATE_PATH if design == "raden" else renderer.SOPIA_NORMAL_TEMPLATE_PATH)
    frame = template["frame"]
    layout = character_asset_layout(size, frame, FACE)
    assert 0 <= layout.x and layout.x + layout.width <= frame["width"]
    assert 0 <= layout.y and layout.y + layout.height == frame["height"]
    assert layout.x + layout.width / 2 == pytest.approx(frame["width"] * frame["face_target_x"], abs=.5)
    assert layout.width / layout.height == pytest.approx(size[0] / size[1], abs=.01)
    image = Image.new("RGBA", size, (80, 180, 130, 255))
    ImageDraw.Draw(image).rectangle((0, size[1] - 20, size[0] - 1, size[1] - 1), fill=(255, 0, 180, 255))
    layer = place_character_asset(image, frame, FACE, scale=1, offset_x=0, offset_y=0, info=None)
    box = (layout.x, layout.y, layout.x + layout.width, layout.y + layout.height)
    assert layer.getbbox() == box
    # Compare every pixel against the whole original, including its bottom marker.
    assert layer.crop(box).tobytes() == image.resize((layout.width, layout.height), Image.Resampling.LANCZOS).tobytes()
    assert character_asset_layout(size, frame, None) == layout
    assert character_asset_layout(size, frame, {"x": .1, "y": .1, "w": .1, "h": .1}) == layout
    assert character_asset_layout(size, {**frame, "min_crop_height_ratio": .99}, FACE) == layout


def test_tall_asset_fits_height_first_and_scale_offsets_keep_bottom_anchor():
    frame = {"width": 692, "height": 720, "face_target_x": .68}
    size = (300, 1000)
    base = character_asset_layout(size, frame, None)
    assert base.scale == .72 and base.height == 720 and base.y == 0
    enlarged = character_asset_layout(size, frame, FACE, scale=1.25)
    assert enlarged.scale == pytest.approx(.9) and enlarged.height == 900 and enlarged.y == -180
    assert enlarged.x + enlarged.width / 2 == pytest.approx(692 * .68, abs=.5)
    moved = character_asset_layout(size, frame, None, scale=1.25, offset_x=35, offset_y=-20)
    assert (moved.x, moved.y) == (enlarged.x + 35, enlarged.y - 20)
    assert moved.y + moved.height == frame["height"] - 20


@pytest.mark.parametrize("design,expected", [("raden", 1.384), ("sopia", 720 / 430)])
def test_whole_asset_upscale_warning_still_uses_two_times_threshold(design, expected):
    template = renderer._load_template(renderer.DEFAULT_NORMAL_TEMPLATE_PATH if design == "raden" else renderer.SOPIA_NORMAL_TEMPLATE_PATH)
    frame = template["frame"]
    layout = character_asset_layout((320, 430), frame, FACE)
    assert layout.scale == pytest.approx(expected)
    info = {}
    place_character_asset(Image.new("RGBA", (320, 430)), frame, FACE, scale=1, offset_x=0, offset_y=0, info=info)
    assert info["warnings"] == []
    place_character_asset(Image.new("RGBA", (320, 430)), frame, FACE, scale=1.5, offset_x=0, offset_y=0, info=info)
    assert info["upscale"] > 2 and info["warnings"] == [ASSET_ROUGH_WARNING]
    place_character_asset(Image.new("RGBA", (320, 430)), frame, FACE,
                          scale=2 / layout.scale, offset_x=0, offset_y=0, info=info)
    assert info["upscale"] == 2 and info["warnings"] == []


def forbidden(*args, **kwargs):
    raise AssertionError("Asset thumbnail must not extract a video frame or reprocess the image")


def generate_batch(context, *, with_assets, monkeypatch):
    identifiers = [add_asset(context, slot=slot)[0] for slot in (1, 2)] if with_assets else []
    calls = []
    def normal_renderer(*args, **kwargs):
        calls.append(kwargs)
        return real_test_renderer(*args, **kwargs)
    def frame_selector(*args, **kwargs):
        assert not with_assets
        return kwargs["preferred_seconds"]
    if with_assets:
        monkeypatch.setattr(renderer, "extract_thumbnail_frame", forbidden)
        monkeypatch.setattr(renderer, "_anime_subject_for_frame", forbidden)
    with context.factory() as db:
        export = db.get(ExportItem, "exp_thumbnail_style")
        second_path = Path(export.metadata_path).with_name("normal_02.json")
        second_path.write_text("{}", encoding="utf-8")
        second = ExportItem(id="exp_second", job_id=export.job_id, video_id=export.video_id, candidate_id="second",
                            type="normal", title=export.title, duration=20, score=90,
                            video_path=str(second_path.with_suffix(".mp4")), metadata_path=str(second_path))
        candidates = [Candidate(id=identifier, type="normal", start=10, end=30, duration=20,
                                thumbnail_line1="上行", transcript_text="字幕", title="タイトル") for identifier in ("normal", "second")]
        result = generate_export_thumbnails(exports=[export, second], selection=CandidateSelection(normalClips=candidates),
            input_path=context.video, job_output_dir=context.storage.job_outputs(export.job_id),
            db=db, job=db.get(Job, export.job_id), paths=context.storage, normal_renderer=normal_renderer,
            normal_frame_selector=frame_selector, emotion_selector=Selector(fail=True))
        assert result.failures == [] and len(result.generated_paths) == 2
        saved = [read_export_metadata(item) for item in (export, second)]
    return identifiers, calls, saved


@pytest.mark.parametrize("with_assets", [False, True])
def test_auto_export_uses_assets_rotates_unpublished_batch_and_video_fallback(asset_thumbnail, monkeypatch, with_assets):
    ids, calls, saved = generate_batch(asset_thumbnail, with_assets=with_assets, monkeypatch=monkeypatch)
    assert [data["thumbnail_subject_source"] for data in saved] == ["asset" if with_assets else "video"] * 2
    if with_assets:
        assert [data["thumbnail_character_asset_id"] for data in saved] == ids
        assert all(data["thumbnail_emotion_selection_source"] == "single_emotion" for data in saved)
        assert all(data["thumbnail_character_asset_upscale"] < 2 for data in saved)
        assert all("character_asset_path" in call for call in calls)
    else:
        assert all("character_asset_path" not in call for call in calls)
        assert all(data["thumbnail_warnings"] == [] for data in saved)


def test_asset_preview_and_manual_regeneration_match_preserve_video_and_switch_back(asset_thumbnail, monkeypatch):
    context = asset_thumbnail
    identifier, _ = add_asset(context)
    queued, previews = [], []
    app.dependency_overrides[get_enqueue_thumbnail_preview] = lambda: lambda *args: previews.append(args)
    app.dependency_overrides[get_enqueue_thumbnail_regeneration] = lambda: lambda *args: queued.append(args)
    original_metadata, original_video = context.metadata.read_bytes(), context.video.read_bytes()
    source = {"subjectSource": "asset", "characterAssetId": identifier}
    monkeypatch.setattr(renderer, "extract_thumbnail_frame", forbidden)
    monkeypatch.setattr(renderer, "_anime_subject_for_frame", forbidden)
    listed = context.api.get(ENDPOINT + "/assets")
    assert listed.status_code == 200 and listed.json()["emotions"]["joy"][0]["id"] == identifier
    response = context.api.post(ENDPOINT + "/preview/prepare", params=source)
    assert response.status_code == 200 and len(previews) == 1
    run_thumbnail_preview_prepare(*previews[0], session_factory=context.factory, paths=context.storage, extractor=forbidden)
    key = context.api.post(ENDPOINT + "/preview/prepare", params=source).json()["frameKey"]
    text = {"heading": "見出し", "upper": "変更した上行", "lower": "下行"}
    placement = {"scale": 1.5, "offsetX": -35, "offsetY": 20}
    request = {**source, "text": text, "textStyles": TEXT_STYLES, "subjectPlacement": placement, "design": "sopia"}
    preview = context.api.post(ENDPOINT + "/preview", json={**request, "frameKey": key}, headers={"Origin": "http://localhost:3000"})
    assert preview.status_code == 200, preview.text
    assert json.loads(preview.headers["X-Thumbnail-Warnings"]) == [ASSET_ROUGH_WARNING]
    assert "x-thumbnail-warnings" in preview.headers["access-control-expose-headers"].lower()
    assert context.metadata.read_bytes() == original_metadata
    response = context.api.post(ENDPOINT + "/regenerate", json={**request, "frameSeconds": 4})
    assert response.status_code == 202, response.text
    run_export_thumbnail_regeneration(*queued[-1], session_factory=context.factory, paths=context.storage,
                                      frame_selector=forbidden, codex_frame_selector=forbidden)
    assert context.thumbnail.read_bytes() == preview.content and context.video.read_bytes() == original_video
    data = json.loads(context.metadata.read_text(encoding="utf-8"))
    assert data["thumbnail_character_asset_id"] == identifier and data["thumbnail_emotion_selection_source"] == "manual"
    assert data["thumbnail_warnings"] == [ASSET_ROUGH_WARNING]
    results = context.api.get("/api/jobs/job_thumbnail_style/results")
    assert results.status_code == 200, results.text
    item = results.json()["normalClips"][0]
    assert item["thumbnailSubjectSource"] == "asset" and item["thumbnailCharacterAssetId"] == identifier
    assert item["thumbnailWarnings"] == [ASSET_ROUGH_WARNING]
    back = context.api.post(ENDPOINT + "/regenerate", json={"subjectSource": "video", "frameSeconds": 4})
    assert back.status_code == 202
    monkeypatch.undo()
    run_export_thumbnail_regeneration(*queued[-1], session_factory=context.factory, paths=context.storage,
                                      normal_renderer=real_test_renderer)
    data = json.loads(context.metadata.read_text(encoding="utf-8"))
    assert data["thumbnail_status"] == "ready" and data["thumbnail_character_asset_id"] is None and data["thumbnail_warnings"] == []
    assert context.video.read_bytes() == original_video


def test_asset_regeneration_codex_fallback_is_reported_in_results(asset_thumbnail):
    context = asset_thumbnail
    identifier, _ = add_asset(context)
    add_asset(context, "anger")
    queued = []
    app.dependency_overrides[get_enqueue_thumbnail_regeneration] = lambda: lambda *args: queued.append(args)
    response = context.api.post(ENDPOINT + "/regenerate", json={"frameSeconds": 4, "subjectSource": "asset", "selectWithCodex": True})
    assert response.status_code == 202
    run_export_thumbnail_regeneration(*queued[-1], session_factory=context.factory, paths=context.storage,
                                      emotion_selector=Selector(fail=True), frame_selector=forbidden, codex_frame_selector=forbidden)
    item = context.api.get("/api/jobs/job_thumbnail_style/results").json()["normalClips"][0]
    assert item["thumbnailCharacterAssetId"] == identifier and item["thumbnailEmotionSelectionSource"] == "fallback"
    assert item["thumbnailWarnings"] == ["表情を自動で選べませんでした（仮に喜を使用）"]


def test_asset_regeneration_rejects_wrong_owner_emotion_and_queue_failure_restores_metadata(asset_thumbnail):
    context = asset_thumbnail
    identifier, _ = add_asset(context)
    other, _ = add_asset(context, preset="character_" + uuid4().hex)
    before = context.metadata.read_bytes()
    for body in ({"characterAssetId": other}, {"characterAssetId": identifier, "emotion": "anger"}):
        response = context.api.post(ENDPOINT + "/regenerate", json={"frameSeconds": 4, "subjectSource": "asset", **body})
        assert response.status_code == 422
        assert context.metadata.read_bytes() == before
    def fail_queue(*args):
        raise RuntimeError("offline")
    app.dependency_overrides[get_enqueue_thumbnail_regeneration] = lambda: fail_queue
    response = context.api.post(ENDPOINT + "/regenerate", json={
        "frameSeconds": 4, "subjectSource": "asset", "characterAssetId": identifier,
    })
    assert response.status_code == 503
    assert json.loads(context.metadata.read_text(encoding="utf-8")) == json.loads(before)


def test_text_only_emotion_bridge_contract_and_real_envelope(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import launcher.codex_bridge as bridge
    captured = {}
    def respond(_seconds):
        request = next((tmp_path / "codex_bridge" / "requests").glob("*.json"))
        envelope = json.loads(request.read_text(encoding="utf-8"))
        captured.update(envelope)
        response = tmp_path / "codex_bridge" / "responses" / f"{envelope['requestId']}.json"
        response.parent.mkdir(exist_ok=True)
        response.write_text(json.dumps({"schemaVersion": 1, "requestId": envelope["requestId"], "state": "ready",
                                       "output": {"emotion": "joy", "reason": "楽しそうな会話です。"}}), encoding="utf-8")
    generator = CodexThumbnailEmotionSelector(storage_root=tmp_path, job_id="job", clip_id="emotion_export",
                                              sleep_func=respond, timeout_seconds=1, poll_seconds=.01)
    result = generator.generate({"availableEmotions": ["joy", "anger"], "videoTitle": "タイトル"}, [])
    assert isinstance(result, ThumbnailEmotion) and result.emotion == "joy"
    assert captured["task"] in bridge.ALLOWED_REQUEST_TASKS and captured["images"] == []
    assert bridge._response_schema_sha256(EMOTION_SCHEMA) == bridge.EXPECTED_RESPONSE_SCHEMA_SHA256[generator.task]
    request = bridge.validate_request(captured, tmp_path)
    assert not request.image_paths and "thumbnail-emotion-v1" in request.prompt
    with pytest.raises(ValueError, match="thumbnail_emotion_images_not_allowed"):
        bridge.validate_request({**captured, "images": ["not-used.png"]}, tmp_path)
    for output in ({"emotion": "neutral", "reason": "なし"}, {"emotion": "joy", "reason": ""}):
        with pytest.raises(ValueError):
            generator.parse_output(output)
