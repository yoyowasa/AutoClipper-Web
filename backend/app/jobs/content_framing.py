"""One bounded framing request per confirmed subtitle/content revision."""

import json
from tempfile import TemporaryDirectory

from app.production_choices import value_hash
from app.render.render_thumbnail import extract_thumbnail_frame
from app.scoring.short_framing import CodexShortFramingSelector, SHORT_FRAMING_VERSION, ShortFramingChoice
from app.storage.json_io import write_json_atomic


def framing_input(document, clip) -> dict:
    # Clip-local evidence; shared segments must not leak neighbouring clip text.
    segments = [{"id": s.id, "start": max(s.start, clip.start) - clip.start,
                 "end": min(s.end, clip.end) - clip.start, "text": s.text}
                for s in document.segments if s.id in clip.segment_ids and s.end > clip.start and s.start < clip.end]
    duration = clip.end - clip.start
    times = [duration * fraction for fraction in (.1, .5, .9)]
    if clip.hook_scene_start is not None and clip.hook_scene_end is not None:
        times.append((clip.hook_scene_start + clip.hook_scene_end) / 2 - clip.start)
    return {"promptVersion": SHORT_FRAMING_VERSION, "title": clip.title, "hook": clip.hook_text,
            "publicationTitle": clip.publication_title, "subtitles": segments,
            "frames": [{"id": f"frame-{i}", "second": round(second, 3)} for i, second in enumerate(times)],
            "timeBasis": "clip", "duration": duration}


def choose_content_framing(document, clip, *, paths, source, selector=None, extractor=extract_thumbnail_frame):
    payload = framing_input(document, clip)
    source_stat = source.stat()
    revision = value_hash({"input": payload, "source": [source_stat.st_size, source_stat.st_mtime_ns],
                           "range": [clip.start, clip.end]})
    artifact = paths.short_framing_decision(document.job_id, clip.id, revision)
    if artifact.is_file():
        saved = json.loads(artifact.read_text(encoding="utf-8"))
        if saved["inputRevision"] != revision:
            raise ValueError("画角の入力記録が一致しません。")
        choice = ShortFramingChoice.model_validate(saved["choice"])
        choice.validate_evidence(payload)
        return choice, revision
    paths.temp.mkdir(parents=True, exist_ok=True)
    selector = selector or CodexShortFramingSelector(storage_root=paths.root, job_id=document.job_id, clip_id=clip.id)
    with TemporaryDirectory(prefix="short-framing-", dir=paths.temp) as folder:
        from pathlib import Path
        frames = [extractor(source, Path(folder) / f"{frame['id']}.jpg", clip.start + frame["second"])
                  for frame in payload["frames"]]
        choice = selector.generate(payload, frames)
    choice.validate_evidence(payload)
    write_json_atomic(artifact, {"inputRevision": revision, "input": payload, "choice": choice.model_dump(by_alias=True)})
    return choice, revision
