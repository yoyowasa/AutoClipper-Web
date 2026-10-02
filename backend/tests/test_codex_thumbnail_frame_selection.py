from pathlib import Path

import pytest
from PIL import Image

from app.jobs.codex_thumbnail_frame_selection import select_codex_thumbnail_frame_seconds
from app.scoring.thumbnail_frame_rank import ThumbnailFrameRanking


class FakeRanker:
    def __init__(self) -> None:
        self.payload = None

    def generate(self, payload, sheets):
        self.payload = payload
        assert len(sheets) == 2
        assert all(sheet.is_file() and Image.open(sheet).size == (1280, 720) for sheet in sheets)
        return ThumbnailFrameRanking(rankedFrameIds=[6, 2, 1, 0, 3, 4, 5, 7])


def test_codex_uses_real_frames_copy_and_nearby_subtitles_and_avoids_current(tmp_path: Path) -> None:
    ranker = FakeRanker()
    extracted = []

    def extractor(_source, path, timestamp):
        extracted.append(timestamp)
        Image.new("RGB", (1280, 720), (len(extracted) * 15, 20, 20)).save(path)
        return path

    saved = [{"id": f"frame_{i:02d}", "second": second} for i, second in enumerate((5., 15., 25., 35., 45., 55., 65., 75.))]
    for item in saved:
        Image.new("RGB", (1280, 720), "white").save(tmp_path / f'{item["id"]}.jpg')
    selected = select_codex_thumbnail_frame_seconds(
        "source.mp4", clip_start=100, clip_end=180, current_frame_seconds=65,
        variant_index=0, storage_root=tmp_path, temp_root=tmp_path / "temp",
        job_id="job", export_id="exp", text={"heading": "北斎", "upper": "波の秘密", "lower": ""},
        design="sopia", segments=[{"start": 64, "end": 66, "text": "北斎の波について"}],
        extractor=extractor, ranker=ranker, saved_candidates=saved, candidate_directory=tmp_path,
    )
    assert extracted == []  # Ranking only opens persisted JPEGs.
    assert selected == pytest.approx(25)  # Top candidate 6 is the already saved frame.
    assert ranker.payload["thumbnailText"]["upper"] == "波の秘密"
    assert ranker.payload["candidateFrames"][6]["nearbySubtitles"] == ["北斎の波について"]
    assert not list((tmp_path / "temp").iterdir())


def test_codex_rejects_duplicate_ranked_candidates() -> None:
    with pytest.raises(ValueError):
        ThumbnailFrameRanking(rankedFrameIds=[0] * 8)


def test_codex_only_shows_verified_late_character_frames(tmp_path: Path) -> None:
    extracted = []

    def extractor(_source, path, timestamp):
        extracted.append(timestamp)
        Image.new("RGB", (1280, 720), "white").save(path)
        return path

    saved = [{"id": f"frame_{i:02d}", "second": float(second)} for i, second in enumerate(range(92, 99))]
    for item in saved:
        Image.new("RGB", (1280, 720), "white").save(tmp_path / f'{item["id"]}.jpg')
    selected = select_codex_thumbnail_frame_seconds(
        "source.mp4", clip_start=0, clip_end=100, current_frame_seconds=10,
        variant_index=0, storage_root=tmp_path, temp_root=tmp_path / "temp",
        job_id="job", export_id="exp", text={"heading": "", "upper": "", "lower": ""},
        design="sopia", segments=[], extractor=extractor, ranker=FakeRanker(),
        saved_candidates=saved, candidate_directory=tmp_path,
    )
    assert extracted == []
    assert 92 <= selected <= 98
