import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from test_api_routes import client as client
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.jobs.subtitle_review import (
    SubtitleReviewDocument,
    apply_reviewed_clip_content,
    build_subtitle_review,
    update_review_clip_content,
)
from app.jobs.title_hook_suggestions import build_title_hook_suggestion_input, TitleHookDraftSegment
from app.posting_metadata import NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX, write_youtube_posting_artifacts
from app.render.render_thumbnail import render_normal_thumbnail
from app.main import app
from app.db import get_db
from app.models import Job
from app.schemas import JobSettings
from app.short_banners import store_banner_image
from app.storage.paths import StoragePaths


def test_character_presets_migration_switch_and_job_snapshot(client: TestClient) -> None:  # noqa: F811
    old = {"profile": {"performerName": "儒烏風亭らでん", "affiliation": "ReGLOSS", "baseHashtags": ["#らでん"]}}
    assert client.put("/api/preferences/youtube-posting-profile", json=old).status_code == 200
    legacy = client.get("/api/preferences/character-presets").json()
    assert legacy["legacyImport"] is True
    raden = legacy["presets"][0]
    assert raden["settings"]["normalClipCount"] == 0
    assert raden["settings"]["normalTitleSuffix"] == NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX
    other = {
        "name": "別チャンネル／キャラB",
        "settings": {
            "channelName": "別チャンネル",
            "youtubePostingProfile": {"performerName": "キャラB", "baseHashtags": ["#キャラB"], "vspoPermissionNumber": "TEST-0123"},
            "normalTitleSuffix": "【キャラB切り抜き】",
            "normalThumbnailStyle": {"design": "plain", "backgroundColor": "#123456"},
            "shortTopBannerEnabled": False,
            "shortBottomBannerEnabled": False,
        },
    }
    saved = {"presets": [raden, other], "selectedName": other["name"]}
    assert client.put("/api/preferences/character-presets", json=saved).status_code == 200
    loaded = client.get("/api/preferences/character-presets").json()
    assert loaded["selectedName"] == other["name"]
    snapshot = loaded["presets"][1]["settings"]
    assert snapshot["youtubePostingProfile"]["vspoPermissionNumber"] == "TEST-0123"
    video = client.post("/api/videos/upload", files={"file": ("b.mp4", b"video", "video/mp4")}).json()
    created = client.post("/api/jobs", json={"videoId": video["videoId"], "settings": snapshot})
    assert created.status_code == 201
    client.put("/api/preferences/character-presets", json={"presets": [], "selectedName": ""})
    # Job keeps its snapshot even after presets are removed.
    with next(app.dependency_overrides[get_db]()) as db:
        job = {"settings": db.get(Job, created.json()["jobId"]).settings_json}
    assert job["settings"]["youtubePostingProfile"]["performerName"] == "キャラB"
    assert job["settings"]["normalTitleSuffix"] == "【キャラB切り抜き】"
    assert job["settings"]["normalThumbnailStyle"]["backgroundColor"] == "#123456"
    assert job["settings"]["shortTopBannerEnabled"] is False
    assert client.put("/api/preferences/character-presets", json={"presets": [other, other]}).status_code == 422
    unsafe = {"name": "bad", "settings": {"youtubeSourceUrl": "https://example.com/video"}}
    assert client.put("/api/preferences/character-presets", json={"presets": [unsafe]}).status_code == 422
    assert client.put("/api/preferences/character-presets", json={"presets": [], "selectedName": "missing"}).status_code == 422


@pytest.mark.parametrize("suffix", ["【キャラB切り抜き】", ""])
def test_character_suffix_survives_review_generation_and_posting(tmp_path: Path, suffix: str) -> None:
    candidate = Candidate(
        id="normal",
        type="normal",
        start=0,
        end=20,
        duration=20,
        transcript_text="話題",
        title="話題" + NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX,
    )
    selection = CandidateSelection(normalClips=[candidate], shorts=[])
    transcript = [TranscriptSegment(start=0, end=10, text="話題の内容")]
    document = build_subtitle_review("job", selection, transcript, render_settings={"normalTitleSuffix": suffix})
    document = SubtitleReviewDocument.model_validate(document.model_dump(by_alias=True))
    clip = document.clips[0]
    assert clip.publication_title == "話題" + suffix
    drafts = [TitleHookDraftSegment(segmentId=item.id, text=item.text) for item in document.segments]
    request = build_title_hook_suggestion_input(document, clip.id, drafts, model="test", provider="codex")
    assert request.prompt_payload()["normalTitleSuffix"] == suffix
    document = update_review_clip_content(document, clip.id, title="変更", hook_text="フック", hook_duration_seconds=3)
    output_selection = apply_reviewed_clip_content(selection, document)
    assert "らでん" not in output_selection.normal_clips[0].title
    paths = write_youtube_posting_artifacts(document.clips, tmp_path)
    packages = json.loads(next(path for path in paths if path.suffix == ".json").read_text(encoding="utf-8"))
    assert "らでん" not in json.dumps(packages, ensure_ascii=False)
    assert document.clips[0].publication_title.endswith(suffix)


@pytest.mark.parametrize("design", ["plain", "custom"])
def test_character_thumbnail_uses_its_background(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, design: str) -> None:
    import app.short_banners as assets

    paths = StoragePaths(tmp_path / "storage")
    monkeypatch.setattr(assets, "get_storage_paths", lambda: paths)
    image = io.BytesIO()
    Image.new("RGB", (320, 180), "#1246A0").save(image, format="PNG")
    asset_id = store_banner_image(image.getvalue(), paths)
    settings = JobSettings.model_validate(
        {"normalThumbnailStyle": {"design": design, "backgroundAssetId": asset_id, "backgroundColor": "#1246A0"}}
    )

    def frame_runner(command: list[str]) -> None:
        Image.new("RGB", (640, 360), "gray").save(command[-1], format="JPEG")

    result = render_normal_thumbnail(
        "source.mp4",
        tmp_path / "thumbnail.jpg",
        frame_time=1,
        eyebrow="",
        title_first_line="",
        title_second_line="",
        command_runner=frame_runner,
        character_style=settings.normal_thumbnail_style.model_dump(by_alias=True),
    )
    with Image.open(result.path) as output:
        pixel = output.convert("RGB").getpixel((10, 700))
        assert all(abs(a - b) <= 3 for a, b in zip(pixel, (18, 70, 160)))
