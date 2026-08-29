import json
from pathlib import Path
from uuid import uuid4


RERENDER_PUBLICATION_UNRESOLVED_FILENAME = ".rerender_publication_unresolved"


def rerender_publication_marker_path(job_dir: Path) -> Path:
    return job_dir / RERENDER_PUBLICATION_UNRESOLVED_FILENAME


def rerender_publication_is_unresolved(job_dir: Path) -> bool:
    return rerender_publication_marker_path(job_dir).exists()


def mark_rerender_publication_unresolved(
    job_dir: Path,
    *,
    job_id: str,
    render_revision: int,
) -> Path:
    marker = rerender_publication_marker_path(job_dir)
    marker.parent.mkdir(parents=True, exist_ok=True)
    temporary = marker.with_name(f"{marker.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(
                {
                    "version": 1,
                    "jobId": job_id,
                    "renderRevision": render_revision,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(marker)
    finally:
        temporary.unlink(missing_ok=True)
    return marker


def clear_rerender_publication_unresolved(job_dir: Path) -> None:
    rerender_publication_marker_path(job_dir).unlink(missing_ok=True)
