import math
from types import SimpleNamespace

import pytest
from PIL import Image

from app.jobs import thumbnail_candidates as candidates
from app.render.thumbnail_face import detect_thumbnail_face
from app.render.video_subject_layout import video_subject_layout
from test_thumbnail_candidates import noisy_image, FACE


def test_upright_detection_does_not_rotate():
    calls = []
    def detector(image):
        calls.append(image)
        return FACE
    assert detect_thumbnail_face(Image.new("RGB", (960, 540)), detector=detector) == FACE
    assert len(calls) == 1


@pytest.mark.parametrize("degrees", [-10, 10, -15, 15])
def test_rotated_center_returns_to_original_coordinates(degrees):
    from app.render.thumbnail_face import THUMBNAIL_FACE_ROTATIONS
    original = (.85, .62, .1, .18)
    radians = math.radians(degrees)
    dx, dy = (original[0] - .5) * 960, (original[1] - .5) * 540
    rotated = (.5 + (math.cos(radians) * dx + math.sin(radians) * dy) / 960,
               .5 + (-math.sin(radians) * dx + math.cos(radians) * dy) / 540, .1, .18)
    answers = iter([None] * (1 + THUMBNAIL_FACE_ROTATIONS.index(degrees)) + [rotated])
    actual = detect_thumbnail_face(Image.new("RGB", (1920, 1080)), detector=lambda _: next(answers))
    assert actual == pytest.approx(original)


def test_no_face_stays_missing():
    assert detect_thumbnail_face(Image.new("RGB", (960, 540)), detector=lambda _: None) is None


@pytest.mark.parametrize("face", [(.8515, .6249, .0969, .1722), (.8829, .6148, .1, .1778)])
@pytest.mark.parametrize("design", ["raden", "sopia"])
def test_visible_chest_at_bottom_is_fitted_without_exceeding_upscale(face, design):
    from app.render import render_thumbnail as renderer
    template = renderer.DEFAULT_NORMAL_TEMPLATE_PATH if design == "raden" else renderer.SOPIA_NORMAL_TEMPLATE_PATH
    frame = renderer._load_template(template)["frame"]
    layout = video_subject_layout((1920, 1080), face, frame)
    assert layout.fits and layout.upscale <= 2
    assert layout.top >= 0
    assert layout.top + layout.crop_height == pytest.approx(1080)
    assert (face[1] * 1080 - layout.top) / layout.crop_height == pytest.approx(.3)
    assert face[3] * 1080 / layout.crop_height <= .45
    # A face too low to retain the chest still fails; do not hide missing pixels.
    assert not video_subject_layout((1920, 1080), (.85, .9, .1, .18), frame).fits


def test_existing_proposed_time_survives_scan_grid_and_twelve_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(candidates, "probe_metadata", lambda _: SimpleNamespace(width=1920, height=1080))
    def scanner(*args):
        for i in range(20):
            yield i * 5., noisy_image()
    calls = []
    def extractor(source, path, second):
        calls.append(second)
        noisy_image((1920, 1080)).save(path)
    saved = candidates.extract_thumbnail_candidates(
        "unused", clip_start=100, clip_end=200, directory=tmp_path, preferred_second=32.38,
        scanner=scanner, extractor=extractor, detector=lambda _: FACE,
    )
    assert len(saved) == 12
    assert 32.38 in [c["second"] for c in saved]
    assert 132.38 in calls
    assert not list(tmp_path.glob(".preferred-*"))


def test_invalid_proposed_time_is_not_extracted(tmp_path, monkeypatch):
    monkeypatch.setattr(candidates, "probe_metadata", lambda _: SimpleNamespace(width=1920, height=1080))
    assert candidates.extract_thumbnail_candidates(
        "unused", clip_start=100, clip_end=200, directory=tmp_path, preferred_second=101,
        scanner=lambda *args: iter([]), extractor=lambda *args: pytest.fail("out-of-range extract"),
    ) == []


def test_cutout_uses_validated_face_without_losing_rotated_detection(tmp_path, monkeypatch):
    from app.render import render_thumbnail as renderer
    frame = tmp_path / "frame.jpg"
    Image.new("RGB", (960, 540)).save(frame)
    model = tmp_path / "model.onnx"
    model.write_bytes(b"fake")
    monkeypatch.setattr(renderer, "anime_matte_path", lambda: model)
    monkeypatch.setattr(renderer, "detect_anime_face", lambda _: pytest.fail("must reuse candidate face"))
    faces = []
    def matte(image, face, **kwargs):
        faces.append(face)
        return Image.new("L", image.size, 255)
    monkeypatch.setattr(renderer, "anime_character_mask", matte)
    for face in (FACE, (.85, .62, .1, .18), FACE):
        assert renderer._anime_subject_for_frame(frame, video_face=face)[0] == face
    assert faces == [FACE, (.85, .62, .1, .18)]  # Cache also keys the chosen face.


def test_recommendation_uses_content_time_only_among_eligible_frames():
    pool = [{"id": "highest_visual_score", "second": 20.0}, {"id": "content_proposal", "second": 32.38}]
    assert candidates.recommended_thumbnail_frame(pool, 32.38) == pool[1]
    assert candidates.recommended_thumbnail_frame(pool, 10) == pool[0]
    assert candidates.recommended_thumbnail_frame([], 32.38) is None


def test_dedicated_thumbnail_copy_keeps_the_automatically_selected_subject():
    from app.scoring.thumbnail_copy import THUMBNAIL_COPY_PROMPT, THUMBNAIL_COPY_PROMPT_VERSION
    assert THUMBNAIL_COPY_PROMPT_VERSION == "thumbnail_copy_v4"
    assert "別の逸話だけを売りにしてタイトルの中心をすり替えない" in THUMBNAIL_COPY_PROMPT
    assert "字幕にある数と単位・対象、素材・技法、時代の対比" in THUMBNAIL_COPY_PROMPT
    assert "数字があるだけで優先せず" in THUMBNAIL_COPY_PROMPT
