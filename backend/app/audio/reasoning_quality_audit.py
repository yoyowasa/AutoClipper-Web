from __future__ import annotations

import argparse
import copy
import csv
import json
import re
import subprocess
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any


REVIEW_LABELS = (
    "useful_correction",
    "harmful_correction",
    "unnecessary_style_change",
    "equivalent_alternative",
    "missed_correction",
    "uncertain",
)
TERM_TYPES = ("proper_noun", "numeric", "technical_term")
GROUPS = (
    "default_only",
    "none_only",
    "shared_same_text",
    "shared_different_text",
)


def load_json_array(path: Path, *, label: str) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or any(not isinstance(item, Mapping) for item in payload):
        raise ValueError(f"{label} must be a JSON array of objects")
    return [dict(item) for item in payload]


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def index_changes(
    changes: Sequence[Mapping[str, Any]],
    *,
    segments: Sequence[Mapping[str, Any]],
    label: str,
) -> dict[int, dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for raw_change in changes:
        change = dict(raw_change)
        index = int(change.get("index", -1))
        if index < 0 or index >= len(segments):
            raise ValueError(f"{label} change index is outside transcript: {index}")
        if index in indexed:
            raise ValueError(f"{label} contains duplicate change index: {index}")
        source_text = _normalize_text(segments[index].get("text"))
        before_text = _normalize_text(change.get("before"))
        if before_text and before_text != source_text:
            raise ValueError(f"{label} before text does not match transcript index {index}")
        if not _normalize_text(change.get("after")):
            raise ValueError(f"{label} corrected text is empty at index {index}")
        indexed[index] = change
    return indexed


def _context_segments(
    segments: Sequence[Mapping[str, Any]],
    *,
    index: int,
    context_count: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    before_start = max(0, index - context_count)
    after_end = min(len(segments), index + context_count + 1)

    def item(segment_index: int) -> dict[str, Any]:
        segment = segments[segment_index]
        return {
            "index": segment_index,
            "start": float(segment["start"]),
            "end": float(segment["end"]),
            "text": str(segment.get("text", "")),
        }

    before = [item(segment_index) for segment_index in range(before_start, index)]
    after = [item(segment_index) for segment_index in range(index + 1, after_end)]
    return before, after


def _change_output(change: Mapping[str, Any] | None, source_text: str) -> str:
    return str(change["after"]) if change is not None else source_text


def build_review_items(
    segments: Sequence[Mapping[str, Any]],
    default_changes: Sequence[Mapping[str, Any]],
    none_changes: Sequence[Mapping[str, Any]],
    *,
    context_count: int = 1,
    audio_padding_seconds: float = 0.35,
) -> list[dict[str, Any]]:
    if not segments:
        raise ValueError("transcript segments are empty")
    default_by_index = index_changes(default_changes, segments=segments, label="default")
    none_by_index = index_changes(none_changes, segments=segments, label="none")
    transcript_end = max(float(segment["end"]) for segment in segments)
    items: list[dict[str, Any]] = []
    for sequence, index in enumerate(sorted(default_by_index.keys() | none_by_index.keys()), start=1):
        default_change = default_by_index.get(index)
        none_change = none_by_index.get(index)
        source = segments[index]
        source_text = str(source.get("text", ""))
        default_output = _change_output(default_change, source_text)
        none_output = _change_output(none_change, source_text)
        if default_change is None:
            group = "none_only"
        elif none_change is None:
            group = "default_only"
        elif _normalize_text(default_output) == _normalize_text(none_output):
            group = "shared_same_text"
        else:
            group = "shared_different_text"
        context_before, context_after = _context_segments(
            segments,
            index=index,
            context_count=context_count,
        )
        audio_context_start = context_before[0]["start"] if context_before else float(source["start"])
        audio_context_end = context_after[-1]["end"] if context_after else float(source["end"])
        audio_start = max(0.0, audio_context_start - audio_padding_seconds)
        audio_end = min(transcript_end, audio_context_end + audio_padding_seconds)
        audio_relative_path = f"audio/{sequence:04d}_seg_{index:04d}_{group}.wav"
        items.append(
            {
                "review_id": f"segment_{index:04d}",
                "index": index,
                "group": group,
                "source": {
                    "start": float(source["start"]),
                    "end": float(source["end"]),
                    "text": source_text,
                    "confidence": source.get("confidence"),
                },
                "context_before": context_before,
                "context_after": context_after,
                "default": {
                    "changed": default_change is not None,
                    "output_text": default_output,
                    "reason": default_change.get("reason") if default_change else None,
                    "confidence": default_change.get("confidence") if default_change else None,
                },
                "none": {
                    "changed": none_change is not None,
                    "output_text": none_output,
                    "reason": none_change.get("reason") if none_change else None,
                    "confidence": none_change.get("confidence") if none_change else None,
                },
                "same_corrected_text": (
                    default_change is not None
                    and none_change is not None
                    and _normalize_text(default_output) == _normalize_text(none_output)
                ),
                "audio": {
                    "start": round(audio_start, 6),
                    "end": round(audio_end, 6),
                    "duration": round(audio_end - audio_start, 6),
                    "path": audio_relative_path,
                },
                "review": {
                    "default_label": None,
                    "none_label": None,
                    "preferred_output": None,
                    "term_types": [],
                    "notes": "",
                },
            }
        )
    return items


def group_counts(items: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(item.get("group", "")) for item in items)
    return {group: counts.get(group, 0) for group in GROUPS}


def _storage_container_path(path: Path, *, storage_root: Path) -> str:
    relative = path.resolve().relative_to(storage_root.resolve())
    return f"/app/storage/{relative.as_posix()}"


def extract_audio_snippets(
    items: Sequence[Mapping[str, Any]],
    *,
    video_path: Path,
    output_dir: Path,
    docker_service: str | None = None,
    storage_root: Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    if docker_service:
        if storage_root is None:
            raise ValueError("storage_root is required for Docker audio extraction")
        input_path = _storage_container_path(video_path, storage_root=storage_root)
    else:
        input_path = str(video_path.resolve())
    for position, item in enumerate(items, start=1):
        audio = item["audio"]
        output_path = output_dir / str(audio["path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if docker_service:
            assert storage_root is not None
            rendered_output_path = _storage_container_path(output_path, storage_root=storage_root)
            command = ["docker", "compose", "exec", "-T", docker_service, "ffmpeg"]
        else:
            rendered_output_path = str(output_path.resolve())
            command = ["ffmpeg"]
        command.extend(
            [
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{float(audio['start']):.6f}",
                "-i",
                input_path,
                "-t",
                f"{float(audio['duration']):.6f}",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                rendered_output_path,
            ]
        )
        runner(command, check=True, capture_output=True, text=True)
        if position % 25 == 0 or position == len(items):
            print(f"audio snippets: {position}/{len(items)}")


def build_review_document(
    items: Sequence[Mapping[str, Any]],
    *,
    source_paths: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "pending_review",
        "allowed_labels": list(REVIEW_LABELS),
        "allowed_term_types": list(TERM_TYPES),
        "review_rules": {
            "default_label": "Judge the default output against the audio and context.",
            "none_label": "Judge the none output against the audio and context.",
            "missed_correction": "Use when unchanged or incorrect output missed an audible correction.",
            "equivalent_alternative": "Use only when wording differs but meaning and audio fidelity are equivalent.",
        },
        "source_paths": dict(source_paths),
        "summary": {
            "unique_changed_indices": len(items),
            "group_counts": group_counts(items),
        },
        "items": [dict(item) for item in items],
    }


def write_review_csv(items: Sequence[Mapping[str, Any]], path: Path) -> None:
    fieldnames = [
        "review_id",
        "index",
        "group",
        "audio_path",
        "start",
        "end",
        "context_before",
        "source_text",
        "context_after",
        "default_output",
        "none_output",
        "default_label",
        "none_label",
        "preferred_output",
        "term_types",
        "notes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            writer.writerow(
                {
                    "review_id": item["review_id"],
                    "index": item["index"],
                    "group": item["group"],
                    "audio_path": item["audio"]["path"],
                    "start": item["source"]["start"],
                    "end": item["source"]["end"],
                    "context_before": " / ".join(segment["text"] for segment in item["context_before"]),
                    "source_text": item["source"]["text"],
                    "context_after": " / ".join(segment["text"] for segment in item["context_after"]),
                    "default_output": item["default"]["output_text"],
                    "none_output": item["none"]["output_text"],
                    "default_label": "",
                    "none_label": "",
                    "preferred_output": "",
                    "term_types": "",
                    "notes": "",
                }
            )


def apply_review_csv(document: Mapping[str, Any], path: Path) -> dict[str, Any]:
    updated = copy.deepcopy(dict(document))
    items = updated.get("items")
    if not isinstance(items, list):
        raise ValueError("review document must contain items")
    by_id = {str(item["review_id"]): item for item in items}
    seen: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            review_id = str(row.get("review_id", "")).strip()
            if review_id not in by_id:
                raise ValueError(f"review CSV contains unknown review_id: {review_id}")
            if review_id in seen:
                raise ValueError(f"review CSV contains duplicate review_id: {review_id}")
            seen.add(review_id)
            default_label = str(row.get("default_label", "")).strip() or None
            none_label = str(row.get("none_label", "")).strip() or None
            if default_label is not None and default_label not in REVIEW_LABELS:
                raise ValueError(f"invalid default_label: {default_label}")
            if none_label is not None and none_label not in REVIEW_LABELS:
                raise ValueError(f"invalid none_label: {none_label}")
            raw_term_types = str(row.get("term_types", "")).strip()
            term_types = [value.strip() for value in raw_term_types.split(";") if value.strip()]
            if any(term_type not in TERM_TYPES for term_type in term_types):
                raise ValueError(f"invalid term_types for {review_id}")
            by_id[review_id]["review"] = {
                "default_label": default_label,
                "none_label": none_label,
                "preferred_output": str(row.get("preferred_output", "")).strip() or None,
                "term_types": term_types,
                "notes": str(row.get("notes", "")).strip(),
            }
    return updated


def _validated_labels(review: Mapping[str, Any]) -> tuple[str | None, str | None]:
    default_label = review.get("default_label")
    none_label = review.get("none_label")
    if default_label is not None and default_label not in REVIEW_LABELS:
        raise ValueError(f"invalid default_label: {default_label}")
    if none_label is not None and none_label not in REVIEW_LABELS:
        raise ValueError(f"invalid none_label: {none_label}")
    return default_label, none_label


def summarize_review(document: Mapping[str, Any]) -> dict[str, Any]:
    items = document.get("items")
    if not isinstance(items, list):
        raise ValueError("review document must contain items")
    default_counts: Counter[str] = Counter()
    none_counts: Counter[str] = Counter()
    completed = 0
    default_changed_reviewed = 0
    none_changed_reviewed = 0
    default_useful_opportunities = 0
    none_retained_default_useful = 0
    none_important_misses: Counter[str] = Counter()
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError("review item must be an object")
        review = item.get("review")
        if not isinstance(review, Mapping):
            raise ValueError("review item is missing review fields")
        default_label, none_label = _validated_labels(review)
        term_types = review.get("term_types", [])
        if not isinstance(term_types, list) or any(term not in TERM_TYPES for term in term_types):
            raise ValueError(f"invalid term_types for index {item.get('index')}")
        if default_label is None or none_label is None:
            continue
        completed += 1
        default_counts[default_label] += 1
        none_counts[none_label] += 1
        if bool(item["default"]["changed"]):
            default_changed_reviewed += 1
        if bool(item["none"]["changed"]):
            none_changed_reviewed += 1
        if default_label == "useful_correction":
            default_useful_opportunities += 1
            if none_label in {"useful_correction", "equivalent_alternative"}:
                none_retained_default_useful += 1
        if none_label == "missed_correction":
            for term_type in term_types:
                none_important_misses[term_type] += 1

    def rate(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator, 6) if denominator else None

    total = len(items)
    return {
        "status": "complete" if completed == total else "partial",
        "reviewed_items": completed,
        "total_items": total,
        "completion_ratio": rate(completed, total),
        "group_counts": group_counts(items),
        "default_label_counts": dict(sorted(default_counts.items())),
        "none_label_counts": dict(sorted(none_counts.items())),
        "none_useful_recall_vs_default": rate(
            none_retained_default_useful,
            default_useful_opportunities,
        ),
        "none_useful_recall_numerator": none_retained_default_useful,
        "none_useful_recall_denominator": default_useful_opportunities,
        "default_harmful_rate": rate(
            default_counts["harmful_correction"],
            default_changed_reviewed,
        ),
        "none_harmful_rate": rate(
            none_counts["harmful_correction"],
            none_changed_reviewed,
        ),
        "none_important_missed_corrections": {
            term_type: none_important_misses.get(term_type, 0) for term_type in TERM_TYPES
        },
    }


def render_markdown(document: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
    counts = summary["group_counts"]
    lines = [
        "# GPT-5.5 Default vs None Quality Audit",
        "",
        f"- Status: `{summary['status']}`",
        f"- Reviewed: `{summary['reviewed_items']}/{summary['total_items']}`",
        f"- default-only: `{counts['default_only']}`",
        f"- none-only: `{counts['none_only']}`",
        f"- shared, same corrected text: `{counts['shared_same_text']}`",
        f"- shared, different corrected text: `{counts['shared_different_text']}`",
        "",
        "## Quality metrics",
        "",
        f"- none useful recall vs default: `{summary['none_useful_recall_vs_default']}`",
        f"- default harmful rate: `{summary['default_harmful_rate']}`",
        f"- none harmful rate: `{summary['none_harmful_rate']}`",
        f"- none important misses: `{json.dumps(summary['none_important_missed_corrections'], ensure_ascii=False)}`",
        "",
        "## Review labels",
        "",
        ", ".join(f"`{label}`" for label in document["allowed_labels"]),
        "",
        "Fill both model labels from the extracted audio and supplied transcript context, then rerun `summarize`.",
        "",
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit GPT-5.5 default vs none subtitle corrections without API calls.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--segments", type=Path, required=True)
    prepare.add_argument("--default-changes", type=Path, required=True)
    prepare.add_argument("--none-changes", type=Path, required=True)
    prepare.add_argument("--video", type=Path)
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.add_argument("--context-segments", type=int, default=1)
    prepare.add_argument("--audio-padding-seconds", type=float, default=0.35)
    prepare.add_argument("--extract-audio", action="store_true")
    prepare.add_argument("--docker-service")
    prepare.add_argument("--storage-root", type=Path)

    summarize = subparsers.add_parser("summarize")
    summarize.add_argument("--review", type=Path, required=True)
    summarize.add_argument("--labels-csv", type=Path)
    summarize.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.command == "prepare":
        segments = load_json_array(args.segments.resolve(), label="segments")
        default_changes = load_json_array(args.default_changes.resolve(), label="default changes")
        none_changes = load_json_array(args.none_changes.resolve(), label="none changes")
        items = build_review_items(
            segments,
            default_changes,
            none_changes,
            context_count=max(0, args.context_segments),
            audio_padding_seconds=max(0.0, args.audio_padding_seconds),
        )
        source_paths = {
            "segments": str(args.segments.resolve()),
            "default_changes": str(args.default_changes.resolve()),
            "none_changes": str(args.none_changes.resolve()),
            "video": str(args.video.resolve()) if args.video else "",
        }
        document = build_review_document(items, source_paths=source_paths)
        review_path = output_dir / "reasoning_quality_review.json"
        review_csv_path = output_dir / "reasoning_quality_review.csv"
        review_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_review_csv(items, review_csv_path)
        if args.extract_audio:
            if args.video is None:
                raise SystemExit("--video is required with --extract-audio")
            extract_audio_snippets(
                items,
                video_path=args.video.resolve(),
                output_dir=output_dir,
                docker_service=args.docker_service,
                storage_root=args.storage_root.resolve() if args.storage_root else None,
            )
        summary = summarize_review(document)
        summary_path = output_dir / "reasoning_quality_audit_summary.json"
        markdown_path = output_dir / "reasoning_quality_audit.md"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        markdown_path.write_text(render_markdown(document, summary), encoding="utf-8")
        print(review_path)
        print(review_csv_path)
        print(markdown_path)
        return 0

    document = json.loads(args.review.resolve().read_text(encoding="utf-8"))
    if args.labels_csv:
        document = apply_review_csv(document, args.labels_csv.resolve())
    summary = summarize_review(document)
    summary_path = output_dir / "reasoning_quality_audit_summary.json"
    markdown_path = output_dir / "reasoning_quality_audit.md"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(document, summary), encoding="utf-8")
    print(summary_path)
    print(markdown_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
