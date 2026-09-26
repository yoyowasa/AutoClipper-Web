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


def prepare(client):  # noqa: F811 - imported pytest fixture is passed to this helper
    storage, factory, metadata, thumbnail, video = seed_thumbnail(client)
    queue = []
    app.dependency_overrides[get_enqueue_thumbnail_preview] = lambda: lambda *args: queue.append(args)
    response = client.post(ENDPOINT + "/prepare")
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "queued"
    assert len(queue) == 1
    run_thumbnail_preview_prepare(*queue[-1], session_factory=factory, paths=storage, extractor=frame_extractor)
    ready = client.post(ENDPOINT + "/prepare").json()
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
    response = client.post(ENDPOINT, json={"frameKey": key, "text": TEXT, "textStyles": TEXT_STYLES})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "no-store"
    assert response.content == expected.read_bytes()
    assert Image.open(BytesIO(response.content)).size == (1280, 720)
    changed = json.loads(json.dumps(TEXT_STYLES))
    changed["heading"] = {"fontPreset": "chikara", "fontSize": 64, "color": "#FFFF00"}
    next_response = client.post(ENDPOINT, json={"frameKey": key, "text": {**TEXT, "lower": ""}, "textStyles": changed})
    assert next_response.status_code == 200
    assert next_response.content != response.content
    assert [path.read_bytes() for path in (metadata, thumbnail, video)] == before
    assert len(queue) == 1


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
