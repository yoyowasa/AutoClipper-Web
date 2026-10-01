from dataclasses import dataclass
from pathlib import Path
import re

from app.config import get_settings


@dataclass(frozen=True)
class StoragePaths:
    root: Path

    @property
    def uploads(self) -> Path:
        return self.root / "uploads"

    @property
    def temp(self) -> Path:
        return self.root / "temp"

    @property
    def outputs(self) -> Path:
        return self.root / "outputs"

    @property
    def heatmaps(self) -> Path:
        return self.root / "heatmaps"

    @property
    def banner_assets(self) -> Path:
        return self.root / "banner_assets"

    @property
    def character_assets(self) -> Path:
        return self.root / "character_assets"

    @property
    def models(self) -> Path:
        return self.root / "models"

    def character_asset(self, preset_id: str, emotion: str, asset_id: str) -> Path:
        from app.character_asset_rules import CHARACTER_EMOTIONS

        if (
            not re.fullmatch(r"character_[0-9a-f]{32}", preset_id)
            or emotion not in CHARACTER_EMOTIONS
            or not re.fullmatch(r"asset_[0-9a-f]{32}", asset_id)
        ):
            raise ValueError("Invalid character asset identifier")
        path = self.character_assets / preset_id / emotion / f"{asset_id}.png"
        self.character_assets.resolve().relative_to(self.root.resolve())
        path.resolve().relative_to(self.character_assets.resolve())
        return path

    @property
    def character_asset_candidates(self) -> Path:
        return self.root / "character_asset_candidates"

    def character_candidate_directory(self, preset_id: str, video_id: str) -> Path:
        if not re.fullmatch(r"character_[0-9a-f]{32}", preset_id) or not re.fullmatch(r"vid_[0-9a-f]{32}", video_id):
            raise ValueError("Invalid character candidate identifier")
        path = self.character_asset_candidates / preset_id / video_id
        self.character_asset_candidates.resolve().relative_to(self.root.resolve())
        path.resolve().relative_to(self.character_asset_candidates.resolve())
        return path

    def character_candidate(self, preset_id: str, video_id: str, candidate_id: str) -> Path:
        if not re.fullmatch(r"candidate_[0-9a-f]{32}", candidate_id):
            raise ValueError("Invalid character candidate identifier")
        return self.character_candidate_directory(preset_id, video_id) / f"{candidate_id}.png"

    def ensure(self) -> None:
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.temp.mkdir(parents=True, exist_ok=True)
        self.outputs.mkdir(parents=True, exist_ok=True)
        self.heatmaps.mkdir(parents=True, exist_ok=True)

    def resolve_stored_file(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return self.root / path

    def video_heatmap(self, video_id: str) -> Path:
        return self.heatmaps / f"{video_id}.heatmap.json"

    def resolve_video_heatmap(self, video_id: str, stored_path: str) -> Path:
        current = self.video_heatmap(video_id)
        if current.is_file():
            return current
        media_path = self.resolve_stored_file(stored_path)
        try:
            media_path.resolve(strict=False).relative_to(
                (self.uploads / ".blobs").resolve(strict=False)
            )
        except ValueError:
            pass
        else:
            return current
        return media_path.with_name(f"{media_path.name}.heatmap.json")

    def zip_path(self, job_id: str) -> Path:
        return self.job_outputs(job_id) / "download.zip"

    def job_outputs(self, job_id: str) -> Path:
        path = self.outputs / job_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def job_subtitles(self, job_id: str, clip_type: str) -> Path:
        folder_name = "shorts" if clip_type == "short" else "normal"
        path = self.job_outputs(job_id) / "subtitles" / folder_name
        path.mkdir(parents=True, exist_ok=True)
        return path


def get_storage_paths() -> StoragePaths:
    paths = StoragePaths(Path(get_settings().storage_root).resolve())
    paths.ensure()
    return paths
