import json
from pathlib import Path

import pytest
from PIL import Image, ImageChops
from sqlalchemy.orm import sessionmaker

from test_api_routes import client as client
from app.db import get_db
from app.jobs.queue import get_enqueue_thumbnail_regeneration
from app.jobs.thumbnail_regeneration import run_export_thumbnail_regeneration
from app.main import app
from app.models import ExportItem, Job, Video
from app.render import render_thumbnail as renderer
from app.render.thumbnail_fonts import thumbnail_font_path
from app.storage.paths import get_storage_paths
from app.thumbnail_style import ThumbnailTextStyles


TEXT_STYLES = {
    "heading": {"fontPreset": "keifont", "fontSize": 38, "color": "#FF0000", "autoFit": True},
    "upper": {"fontPreset": "dela_gothic", "fontSize": 108, "color": "#00FF00", "autoFit": False},
    "lower": {"fontPreset": "mplus_rounded_extrabold", "fontSize": 72, "color": "#0000FF", "autoFit": True},
}


def frame_runner(command):
    Image.new("RGB", (1280, 720), "#667788").save(command[-1], format="JPEG")


def real_test_renderer(*args, **kwargs):
    return renderer.render_normal_thumbnail(*args, **kwargs, command_runner=frame_runner)


def seed_thumbnail(api):
    storage = app.dependency_overrides[get_storage_paths]()
    job_dir = storage.job_outputs("job_thumbnail_style")
    video_path = job_dir / "normal" / "normal_01.mp4"
    metadata_path = video_path.with_suffix(".json")
    output_path = job_dir / "thumbnails" / "normal" / "normal_01.jpg"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    source_path = storage.uploads / "thumbnail_source.mp4"
    source_path.write_bytes(b"source")
    video_path.write_bytes(b"completed video unchanged")
    real_test_renderer(source_path, output_path, frame_time=4, eyebrow="見出し", title_first_line="上行", title_second_line="下行")
    metadata_path.write_text(
        json.dumps(
            {
                "candidate_id": "normal",
                "start": 10,
                "thumbnail_status": "ready",
                "thumbnail_path": str(output_path),
                "thumbnail_frame_seconds": 4,
                "thumbnail_render_revision": 0,
                "thumbnail_kicker": "見出し",
                "thumbnail_line1": "上行",
                "thumbnail_line2": "下行",
                "thumbnail_crop_mode": "close",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with next(app.dependency_overrides[get_db]()) as db:
        job = Job(
            id="job_thumbnail_style",
            video_id="vid_thumbnail_style",
            status="completed",
            progress=100,
            current_step="Completed",
            settings_json={},
        )
        source = Video(id=job.video_id, original_filename="source.mp4", stored_path=str(source_path))
        export = ExportItem(
            id="exp_thumbnail_style",
            job_id=job.id,
            video_id=job.video_id,
            candidate_id="normal",
            type="normal",
            title="サムネ書式確認",
            duration=20,
            score=90,
            video_path=str(video_path),
            metadata_path=str(metadata_path),
        )
        db.add_all([source, job, export])
        db.commit()
        factory = sessionmaker(bind=db.get_bind())
    return storage, factory, metadata_path, output_path, video_path


def test_three_roles_render_with_independent_fonts_sizes_colors(tmp_path, monkeypatch):
    captured = {}
    original_fit = renderer._fit_text

    def record_fit(text, font_path, **kwargs):
        fit = original_fit(text, font_path, **kwargs)
        captured[text] = (Path(font_path).name, fit.font.size)
        return fit

    monkeypatch.setattr(renderer, "_fit_text", record_fit)
    output = tmp_path / "styled.jpg"
    real_test_renderer(
        "source", output, frame_time=4, eyebrow="見出し", title_first_line="上行", title_second_line="下行", text_styles=TEXT_STYLES
    )
    assert captured == {
        "見出し": ("keifont.ttf", 38),
        "上行": ("DelaGothicOne-Regular.ttf", 108),
        "下行": ("MPLUSRounded1c-ExtraBold.ttf", 72),
    }
    image = Image.open(output).convert("RGB")
    assert image.size == (1280, 720)
    for channel in range(3):
        assert sum(pixel[channel] > 220 and all(pixel[c] < 45 for c in range(3) if c != channel) for pixel in image.getdata()) > 100


@pytest.mark.parametrize(
    "preset,filename",
    [
        ("genei_kiwami_go", "GenEiKiwamiGo.ttf"),
        ("genei_mono_go", "GenEiMonoGothic-Bold.ttf"),
        ("genei_antique", "GenEiAntiqueNv6-M.ttf"),
    ],
)
def test_genei_fonts_render_normal_thumbnails(tmp_path, preset, filename):
    styles = ThumbnailTextStyles().model_dump(by_alias=True)
    styles["heading"]["fontPreset"] = preset
    validated = ThumbnailTextStyles.model_validate(styles)
    assert thumbnail_font_path(preset, tmp_path / "default.ttf").name == filename

    output = tmp_path / f"{preset}.jpg"
    real_test_renderer(
        "source", output, frame_time=4, eyebrow="日本語の見出し",
        title_first_line="", title_second_line="", text_styles=validated.model_dump(by_alias=True),
    )
    assert Image.open(output).size == (1280, 720)


@pytest.mark.parametrize("role,sizes", [("heading", (60, 70)), ("upper", (120, 140)), ("lower", (120, 140))])
def test_manual_sizes_change_long_text_instead_of_hitting_auto_fit_ceiling(tmp_path, monkeypatch, role, sizes):
    text = "長い文言でも指定したサイズで表示"
    captured = []
    original_fit = renderer._fit_text

    def record_fit(*args, **kwargs):
        fit = original_fit(*args, **kwargs)
        captured.append(fit.font.size)
        return fit

    monkeypatch.setattr(renderer, "_fit_text", record_fit)
    images = {}
    styles = ThumbnailTextStyles().model_dump(by_alias=True)
    for auto_fit in (True, False):
        for size in sizes:
            styles[role].update(fontSize=size, autoFit=auto_fit)
            output = tmp_path / f"{role}-{auto_fit}-{size}.jpg"
            real_test_renderer(
                "source", output, frame_time=4, text_styles=styles,
                eyebrow=text if role == "heading" else "",
                title_first_line=text if role == "upper" else "",
                title_second_line=text if role == "lower" else "",
            )
            images[auto_fit, size] = output.read_bytes()
            if not auto_fit:
                assert captured[-1] == size
    # The old maximum-size behavior silently produced the same image.
    assert images[True, sizes[0]] == images[True, sizes[1]]
    assert images[False, sizes[0]] != images[False, sizes[1]]


def test_saved_role_settings_flow_through_api_worker_and_results(client):  # noqa: F811
    storage, factory, metadata_path, output_path, video_path = seed_thumbnail(client)
    old_image = Image.open(output_path).copy()
    queued = []
    app.dependency_overrides[get_enqueue_thumbnail_regeneration] = lambda: lambda export_id, revision: queued.append((export_id, revision))
    endpoint = "/api/exports/exp_thumbnail_style/thumbnail/regenerate"
    response = client.post(endpoint, json={"frameSeconds": 4, "cropMode": "close", "textStyles": TEXT_STYLES})
    assert response.status_code == 202, response.text
    assert queued == [("exp_thumbnail_style", 1)]
    pending = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert pending["thumbnail_text_styles"] == TEXT_STYLES
    assert pending["thumbnail_advance_frame"] is False
    run_export_thumbnail_regeneration(*queued[-1], session_factory=factory, paths=storage, normal_renderer=real_test_renderer)
    assert ImageChops.difference(old_image, Image.open(output_path)).getbbox() is not None
    assert video_path.read_bytes() == b"completed video unchanged"
    result = client.get("/api/jobs/job_thumbnail_style/results").json()["normalClips"][0]
    assert result["thumbnailTextStyles"] == TEXT_STYLES
    assert result["thumbnailKicker"] == "見出し"
    assert result["thumbnailCropMode"] == "close"
    assert result["thumbnailRenderRevision"] == 1
    # The existing alternate-frame action keeps the saved text styles.
    assert client.post(endpoint, json={"frameSeconds": 4, "advanceFrame": True}).status_code == 202
    seen = {}

    def capture_renderer(*args, **kwargs):
        seen.update(kwargs)
        return real_test_renderer(*args, **kwargs)

    run_export_thumbnail_regeneration(
        *queued[-1], session_factory=factory, paths=storage, normal_renderer=capture_renderer, frame_selector=lambda *args, **kwargs: 6
    )
    assert seen["text_styles"] == TEXT_STYLES
    assert video_path.read_bytes() == b"completed video unchanged"


@pytest.mark.parametrize("patch", [{"fontPreset": "../bad.ttf"}, {"fontSize": 500}, {"color": "red"}, {"fontSize": 11}])
def test_invalid_font_settings_rejected_without_metadata_changes(client, patch):  # noqa: F811
    _, _, metadata_path, _, _ = seed_thumbnail(client)
    before = metadata_path.read_bytes()
    styles = ThumbnailTextStyles.model_validate(TEXT_STYLES).model_dump(by_alias=True)
    styles["heading"].update(patch)
    response = client.post("/api/exports/exp_thumbnail_style/thumbnail/regenerate", json={"frameSeconds": 4, "textStyles": styles})
    assert response.status_code == 422
    assert metadata_path.read_bytes() == before


def test_character_presets_keep_all_three_text_styles(client):  # noqa: F811
    payload = {
        "presets": [{"name": "書式テスト", "settings": {"normalThumbnailStyle": {"textStyles": TEXT_STYLES}}}],
        "selectedName": "書式テスト",
    }
    assert client.put("/api/preferences/character-presets", json=payload).status_code == 200
    saved = client.get("/api/preferences/character-presets").json()["presets"][0]["settings"]
    assert saved["normalThumbnailStyle"]["textStyles"] == TEXT_STYLES
