"""One inspection pass; no repair or HTTP side effects."""

import json
from tempfile import TemporaryDirectory
from app.inspection.media import inspect_media, inspect_opening
from app.inspection.subtitles import inspect_subtitles
from app.inspection.content import inspect_content
from app.render.subtitles_ass import SubtitleLayout
from app.render.render_short import SHORT_BANNER_HEIGHT


def inspect_export(export, candidate, *, source, segments, settings, video, paths, job_id, selector=None):
    dimensions = (1080, 1920) if candidate.type == "short" else (video.width or 1920, video.height or 1080)
    digest, checks = inspect_media(export.video_path, candidate, dimensions=dimensions, source=source)
    if any(c.outcome != "pass" for c in checks):
        return digest, checks
    paths.temp.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="final-inspection-", dir=paths.temp) as directory:
        layout = (
            SubtitleLayout.short(settings=settings) if candidate.type == "short" else SubtitleLayout.normal(*dimensions, settings=settings)
        )
        banners = (
            SHORT_BANNER_HEIGHT if candidate.type == "short" and settings.get("shortTopBannerEnabled") else 0,
            SHORT_BANNER_HEIGHT if candidate.type == "short" and settings.get("shortBottomBannerEnabled") else 0,
        )
        checks += inspect_subtitles(
            export.video_path,
            candidate,
            segments,
            layout=layout,
            directory=directory,
            banners=banners,
            enabled=settings.get("burnSubtitles", True),
        )
        checks.append(inspect_opening(export.video_path, candidate, source))
        if any(c.outcome != "pass" for c in checks):
            return digest, checks
        from app.jobs.thumbnails import thumbnail_path_from_export

        try:
            with open(export.metadata_path, encoding="utf-8") as file:
                metadata = json.load(file)
        except (OSError, ValueError):
            metadata = {}
        metadata["publication_title"] = export.title
        checks += inspect_content(
            export.video_path,
            candidate,
            source=source,
            segments=segments,
            thumbnail=thumbnail_path_from_export(export),
            metadata=metadata,
            directory=directory,
            paths=paths,
            job_id=job_id,
            selector=selector,
        )
    return digest, checks
