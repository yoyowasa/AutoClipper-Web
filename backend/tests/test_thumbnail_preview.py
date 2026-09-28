import json
from io import BytesIO

from PIL import Image
from app.jobs.queue import get_enqueue_thumbnail_preview
from app.jobs.thumbnail_preview import run_thumbnail_preview_prepare
from app.main import app
from app.render import render_thumbnail as renderer
from test_api_routes import client as client
from test_thumbnail_text_styles import seed_thumbnail, TEXT_STYLES, real_test_renderer


ENDPOINT = "/api/exports/exp_thumbnail_style/thumbnail/preview"
TEXT = {"heading": "見出し", "upper": "変更した上行", "lower": "下行"}


def frame_extractor(source, output, timestamp):
    Image.new("RGB", (1280, 720), "#667788").save(output, format="JPEG")


def prepare(api):
    storage, factory, metadata, thumbnail, video = seed_thumbnail(api)
    queue = []
    app.dependency_overrides[get_enqueue_thumbnail_preview] = lambda: lambda *args: queue.append(args)
    response = api.post(ENDPOINT + "/prepare")
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "queued"
    assert len(queue) == 1
    run_thumbnail_preview_prepare(*queue[-1], session_factory=factory, paths=storage, extractor=frame_extractor)
    ready = api.post(ENDPOINT + "/prepare").json()
    assert ready["state"] == "ready"
    assert len(queue) == 1
    return storage, factory, metadata, thumbnail, video, queue, ready["frameKey"]


def test_live_preview_matches_saved_renderer_without_changing_exports_or_extracting_video(client, tmp_path, monkeypatch):  # noqa: F811
    _, _, metadata, thumbnail, video, queue, key = prepare(client)
    before = [path.read_bytes() for path in (metadata, thumbnail, video)]
    expected = tmp_path / "expected.jpg"
    real_test_renderer("source", expected, frame_time=14, eyebrow=TEXT["heading"], title_first_line=TEXT["upper"],
                       title_second_line=TEXT["lower"], subject_anchor_x=1, face_height_ratio=0.34, text_styles=TEXT_STYLES)

    def forbidden_extract(*args, **kwargs):
        raise AssertionError("preview HTTP request must not process video")

    monkeypatch.setattr(renderer, "extract_thumbnail_frame", forbidden_extract)
    response = client.post(ENDPOINT, json={"frameKey": key, "text": TEXT, "textStyles": TEXT_STYLES},
                           headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "no-store"
    assert "x-thumbnail-text-regions" in response.headers["access-control-expose-headers"].lower()
    regions = json.loads(response.headers["x-thumbnail-text-regions"])
    assert set(regions) == {"heading", "upper", "lower"}
    assert all(region["width"] > 0 and region["height"] > 0 for region in regions.values())
    assert response.content == expected.read_bytes()
    assert Image.open(BytesIO(response.content)).size == (1280, 720)
    changed = json.loads(json.dumps(TEXT_STYLES))
    changed["heading"] = {"fontPreset": "chikara", "fontSize": 64, "color": "#FFFF00"}
    next_response = client.post(ENDPOINT, json={"frameKey": key, "text": {**TEXT, "lower": ""}, "textStyles": changed})
    assert next_response.status_code == 200
    assert next_response.content != response.content
    assert [path.read_bytes() for path in (metadata, thumbnail, video)] == before
    assert len(queue) == 1


def test_preview_text_regions_follow_saved_offsets_and_align_to_template(client):  # noqa: F811
    _, _, _, _, _, _, key = prepare(client)
    base = {"frameKey": key, "text": TEXT, "textStyles": TEXT_STYLES}
    first = client.post(ENDPOINT, json=base)
    assert first.status_code == 200, first.text
    regions = json.loads(first.headers["x-thumbnail-text-regions"])
    styles = json.loads(json.dumps(TEXT_STYLES))
    styles["upper"]["offsetX"] += 27
    styles["upper"]["offsetY"] -= 13
    moved = client.post(ENDPOINT, json={**base, "textStyles": styles})
    assert moved.status_code == 200, moved.text
    changed = json.loads(moved.headers["x-thumbnail-text-regions"])
    assert abs(changed["upper"]["x"] - regions["upper"]["x"] - 27) <= 1
    assert abs(changed["upper"]["y"] - regions["upper"]["y"] + 13) <= 1
    assert changed["lower"] == regions["lower"]
    for design in ("raden", "sopia"):
        path = renderer.DEFAULT_NORMAL_TEMPLATE_PATH if design == "raden" else renderer.SOPIA_NORMAL_TEMPLATE_PATH
        template = renderer._load_template(path)
        box = template["text"]["eyebrow_box"]
        assert (box["x"], box["y"]) == (27, 27)
        assert box["height"] == 118
        assert regions["heading"]["targetCenterX"] == box["x"] + box["width"] // 2


def test_template_switch_previews_immediately_without_saving(client):  # noqa: F811
    _, _, metadata, thumbnail, video, queue, key = prepare(client)
    before = [path.read_bytes() for path in (metadata, thumbnail, video)]
    base = {"frameKey": key, "text": TEXT, "textStyles": TEXT_STYLES}
    raden = client.post(ENDPOINT, json={**base, "design": "raden"})
    sopia = client.post(ENDPOINT, json={**base, "design": "sopia"})
    assert raden.status_code == 200, raden.text
    assert sopia.status_code == 200, sopia.text
    assert raden.content != sopia.content
    assert [path.read_bytes() for path in (metadata, thumbnail, video)] == before
    assert len(queue) == 1
    invalid = client.post(ENDPOINT, json={**base, "design": "custom"})
    assert invalid.status_code == 409


def test_subject_placement_preview_uses_saved_renderer_without_mutating_files(client, tmp_path):  # noqa: F811
    _, _, metadata, thumbnail, video, _, key = prepare(client)
    before = [path.read_bytes() for path in (metadata, thumbnail, video)]
    placement = {"scale": 0.7, "offsetX": -65, "offsetY": 25}
    expected = tmp_path / "placed.jpg"
    real_test_renderer(
        "source", expected, frame_time=14, eyebrow=TEXT["heading"],
        title_first_line=TEXT["upper"], title_second_line=TEXT["lower"],
        subject_anchor_x=1, face_height_ratio=0.34, text_styles=TEXT_STYLES,
        subject_scale=0.7, subject_offset_x=-65, subject_offset_y=25,
    )
    response = client.post(ENDPOINT, json={
        "frameKey": key, "text": TEXT, "textStyles": TEXT_STYLES,
        "subjectPlacement": placement,
    })
    assert response.status_code == 200, response.text
    assert response.content == expected.read_bytes()
    assert [path.read_bytes() for path in (metadata, thumbnail, video)] == before


def test_changed_source_frame_invalidates_old_preview_and_prepares_once(client):  # noqa: F811
    storage, factory, metadata, _, _, queue, old_key = prepare(client)
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    payload["thumbnail_frame_seconds"] = 6
    metadata.write_text(json.dumps(payload), encoding="utf-8")
    assert client.post(ENDPOINT, json={"frameKey": old_key, "text": TEXT, "textStyles": TEXT_STYLES}).status_code == 409
    fresh = client.post(ENDPOINT + "/prepare").json()
    assert fresh["frameKey"] != old_key
    client.post(ENDPOINT + "/prepare")
    assert len(queue) == 2
    run_thumbnail_preview_prepare(*queue[-1], session_factory=factory, paths=storage, extractor=frame_extractor)
    assert client.post(ENDPOINT, json={"frameKey": fresh["frameKey"], "text": TEXT, "textStyles": TEXT_STYLES}).status_code == 200


def test_preview_preparation_can_retry_worker_failure(client):  # noqa: F811
    storage, factory, _, _, _ = seed_thumbnail(client)
    queue = []
    app.dependency_overrides[get_enqueue_thumbnail_preview] = lambda: lambda *args: queue.append(args)
    client.post(ENDPOINT + "/prepare")

    def fail(*args):
        raise RuntimeError("frame extraction failed")

    run_thumbnail_preview_prepare(*queue[-1], session_factory=factory, paths=storage, extractor=fail)
    assert client.post(ENDPOINT + "/prepare").json()["state"] == "failed"
    assert client.post(ENDPOINT + "/prepare?force=true").json()["state"] == "queued"
    assert len(queue) == 2
    assert queue[0] != queue[1]
    run_thumbnail_preview_prepare(*queue[-1], session_factory=factory, paths=storage, extractor=frame_extractor)
    assert client.post(ENDPOINT + "/prepare").json()["state"] == "ready"


def test_preview_rejects_unprepared_or_invalid_draft(client):  # noqa: F811
    _, _, metadata, thumbnail, video = seed_thumbnail(client)
    before = [path.read_bytes() for path in (metadata, thumbnail, video)]
    assert client.post(ENDPOINT, json={"frameKey": "0" * 64, "text": TEXT, "textStyles": TEXT_STYLES}).status_code == 409
    bad = json.loads(json.dumps(TEXT_STYLES))
    bad["heading"]["fontPreset"] = "../../font.ttf"
    assert client.post(ENDPOINT, json={"frameKey": "0" * 64, "text": TEXT, "textStyles": bad}).status_code == 422
    assert [path.read_bytes() for path in (metadata, thumbnail, video)] == before
