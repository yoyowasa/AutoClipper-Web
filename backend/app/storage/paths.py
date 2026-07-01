from dataclasses import dataclass
from pathlib import Path

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

    def ensure(self) -> None:
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.temp.mkdir(parents=True, exist_ok=True)
        self.outputs.mkdir(parents=True, exist_ok=True)

    def resolve_stored_file(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return self.root / path

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
