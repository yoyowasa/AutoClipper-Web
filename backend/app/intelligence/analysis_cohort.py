"""Deterministic recent/performance sample; missing views never rank as zero."""

from datetime import date, timedelta

MAX_ANALYSIS_VIDEOS = 100
RECENT_PUBLICATION_DAYS = 90
PERFORMANCE_EXTREMES_PER_FORMAT = 5


def select_video_cohort(videos: dict, public_views: dict, last: date) -> tuple[dict, dict]:
    recent_start = str(last - timedelta(days=RECENT_PUBLICATION_DAYS - 1))
    chosen = set()
    for format in sorted({video["format"] for video in videos.values()}):
        ranked = sorted((id for id in videos if videos[id]["format"] == format and id in public_views),
                        key=lambda id: (public_views[id], id))
        chosen.update(ranked[:PERFORMANCE_EXTREMES_PER_FORMAT])
        chosen.update(ranked[-PERFORMANCE_EXTREMES_PER_FORMAT:])
    recent = sorted((id for id, video in videos.items() if (video["published_at"] or "")[:10] >= recent_start),
                    key=lambda id: (videos[id]["published_at"] or "", id), reverse=True)
    for id in recent:
        if len(chosen) >= MAX_ANALYSIS_VIDEOS:
            break
        chosen.add(id)
    selected = {id: video for id, video in videos.items() if id in chosen}
    return selected, {
        "eligible_videos": len(videos), "selected_videos": len(selected), "excluded_videos": len(videos) - len(selected),
        "recent_publication_start": recent_start, "recent_publication_days": RECENT_PUBLICATION_DAYS,
        "maximum_videos": MAX_ANALYSIS_VIDEOS, "performance_extremes_per_format": PERFORMANCE_EXTREMES_PER_FORMAT,
        "ranking_basis": "fresh_public_cumulative_views_within_each_format; missing values excluded from ranking",
        "selection_order": "performance top/bottom first, then newest publications in recent period",
    }
