from uuid import uuid4

from app.candidates.merge_boundaries import SubtitleStyleOverride
from app.jobs.subtitle_review import SubtitleReviewDocument, _refresh_counts
from app.schemas import SubtitleStructureRequest


def edit_subtitle_structure(document: SubtitleReviewDocument, request: SubtitleStructureRequest) -> set[str]:
    by_id = {s.id: s for s in document.segments}
    if len({item.segment_id for item in request.segments}) != len(request.segments):
        raise ValueError("字幕の指定が重複しています。")
    if any(item.segment_id not in by_id for item in request.segments):
        raise KeyError("字幕が見つかりません。")
    selected = sorted([by_id[item.segment_id] for item in request.segments], key=lambda s: (s.start, s.end))
    for item in request.segments:
        if by_id[item.segment_id].text != item.before:
            raise RuntimeError("字幕が別の操作で更新されています。画面を読み直してください。")
    first = selected[0]
    style_sources = list(selected)
    affected = set(first.affected_clip_ids)
    if any(set(s.affected_clip_ids) != affected for s in selected):
        raise ValueError("別の動画と共有する範囲が異なるため、この２区間は結合できません。")
    texts = {item.segment_id: item.text for item in request.segments}
    propagate_first_style = True
    if request.action == "merge":
        positions = [document.segments.index(s) for s in selected]
        if len(selected) != 2 or positions[1] != positions[0] + 1:
            raise ValueError("隣り合う２区間を指定してください。")
        if selected[1].start < first.end - 0.001:
            raise ValueError("時間が重なる区間は結合できません。")
        replacements = [
            first.model_copy(
                update={
                    "id": f"seg_{uuid4().hex}",
                    "end": selected[-1].end,
                    "text": "".join(texts[s.id].strip() for s in selected),
                    "original_text": "".join(s.original_text for s in selected),
                    "source_indices": sorted({i for s in selected for i in (s.source_indices or [s.index])}),
                    "preserve_segmentation": True,
                    "single_line": True,
                    "edited": True,
                }
            )
        ]
    elif request.action == "split":
        text = texts[first.id]
        offset = request.split_offset
        point = request.split_time
        if len(selected) != 1 or offset is None or point is None:
            raise ValueError("分割位置と時刻を指定してください。")
        if not 0 < offset < len(text) or not first.start + 0.01 <= point <= first.end - 0.01:
            raise ValueError("字幕の内側に分割位置と時刻を指定してください。")
        if not text[:offset].strip() or not text[offset:].strip():
            raise ValueError("分割後の両方に文字を残してください。")
        replacements = [
            first.model_copy(
                update={
                    "id": f"seg_{uuid4().hex}",
                    "start": start,
                    "end": end,
                    "text": content.strip(),
                    "source_indices": first.source_indices or [first.index],
                    "preserve_segmentation": True,
                    "single_line": first.single_line,
                    "edited": True,
                }
            )
            for start, end, content in [(first.start, point, text[:offset]), (point, first.end, text[offset:])]
        ]
    elif request.action == "insert":
        text = texts[first.id]
        point = request.split_time
        if len(selected) != 1 or point is None or request.insert_position is None:
            raise ValueError("追加位置と時刻を指定してください。")
        if not first.start + 0.05 <= point <= first.end - 0.05:
            raise ValueError("字幕区間の内側に追加時刻を指定してください。")
        pieces = (
            [(first.start, point, "", ""), (point, first.end, text, first.original_text)]
            if request.insert_position == "before"
            else [(first.start, point, text, first.original_text), (point, first.end, "", "")]
        )
        replacements = [
            first.model_copy(
                update={
                    "id": f"seg_{uuid4().hex}",
                    "start": start,
                    "end": end,
                    "text": content,
                    "original_text": original_text,
                    "source_indices": first.source_indices or [first.index],
                    "preserve_segmentation": True,
                    "edited": True,
                }
            )
            for start, end, content, original_text in pieces
        ]
    elif request.action == "delete":
        if len(selected) != 1:
            raise ValueError("削除する字幕を１行指定してください。")
        position = document.segments.index(first)
        candidates = [
            document.segments[index]
            for index in (position + 1, position - 1)
            if 0 <= index < len(document.segments)
            and set(document.segments[index].affected_clip_ids) == affected
        ]
        if not candidates:
            raise ValueError("この字幕は対象動画内の最後の１行なので削除できません。")
        neighbor = candidates[0]
        replacements = [
            neighbor.model_copy(
                update={
                    "source_indices": sorted(
                        {
                            *(neighbor.source_indices or [neighbor.index]),
                            *(first.source_indices or [first.index]),
                        }
                    ),
                    "preserve_segmentation": True,
                    "edited": True,
                }
            )
        ]
        selected.append(neighbor)
        propagate_first_style = False
    else:
        if len(selected) != 1:
            raise ValueError("字幕を１区間指定してください。")
        replacements = [
            first.model_copy(
                update={
                    "text": texts[first.id],
                    "preserve_segmentation": True,
                    "single_line": request.single_line,
                    "edited": True,
                }
            )
        ]
    removed = {s.id for s in selected}
    if any(len(s.text) > 4000 for s in replacements):
        raise ValueError("１区間の字幕は4000文字以内にしてください。")
    document.segments = sorted([s for s in document.segments if s.id not in removed] + replacements, key=lambda s: (s.start, s.end))
    for clip in document.clips:
        if clip.id not in affected:
            continue
        clip.confirmed = False
        clip.segment_ids = [s.id for s in document.segments if clip.id in s.affected_clip_ids]
        old_ranges = {(s.start, s.end) for s in style_sources}
        first_style = next((s.style for s in clip.subtitle_styles if (s.start, s.end) == (first.start, first.end)), None)
        clip.subtitle_styles = [s for s in clip.subtitle_styles if (s.start, s.end) not in old_ranges]
        if first_style and propagate_first_style:
            clip.subtitle_styles.extend(SubtitleStyleOverride(start=s.start, end=s.end, style=first_style) for s in replacements)
    _refresh_counts(document)
    return affected
