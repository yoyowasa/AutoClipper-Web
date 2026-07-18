from __future__ import annotations

import csv
import subprocess
from pathlib import Path
from typing import Any

import pytest

from app.audio.reasoning_quality_audit import (
    apply_review_csv,
    build_review_document,
    build_review_items,
    extract_audio_snippets,
    group_counts,
    index_changes,
    render_markdown,
    summarize_review,
    write_review_csv,
)


def segments() -> list[dict[str, Any]]:
    return [
        {"start": 0.0, "end": 1.0, "text": "元の一", "confidence": 0.9},
        {"start": 1.0, "end": 2.0, "text": "元の二", "confidence": 0.8},
        {"start": 2.0, "end": 3.0, "text": "元の三", "confidence": 0.7},
        {"start": 3.0, "end": 4.0, "text": "元の四", "confidence": 0.6},
    ]


def change(index: int, before: str, after: str) -> dict[str, Any]:
    return {
        "index": index,
        "start": float(index),
        "end": float(index + 1),
        "before": before,
        "after": after,
        "reason": "asr_error",
        "confidence": 0.95,
    }


def test_review_items_split_all_four_comparison_groups() -> None:
    source = segments()
    default_changes = [
        change(0, "元の一", "既定一"),
        change(2, "元の三", "共通三"),
        change(3, "元の四", "既定四"),
    ]
    none_changes = [
        change(1, "元の二", "なし二"),
        change(2, "元の三", "共通三"),
        change(3, "元の四", "なし四"),
    ]

    items = build_review_items(source, default_changes, none_changes, context_count=1)

    assert group_counts(items) == {
        "default_only": 1,
        "none_only": 1,
        "shared_same_text": 1,
        "shared_different_text": 1,
    }
    assert items[0]["none"]["output_text"] == "元の一"
    assert items[0]["context_after"][0]["index"] == 1
    assert items[2]["same_corrected_text"] is True
    assert items[3]["default"]["output_text"] == "既定四"
    assert items[3]["none"]["output_text"] == "なし四"


def test_change_validation_rejects_duplicates_and_source_mismatch() -> None:
    source = segments()
    duplicate = [change(0, "元の一", "修正"), change(0, "元の一", "別修正")]
    mismatch = [change(0, "違う原文", "修正")]

    with pytest.raises(ValueError, match="duplicate"):
        index_changes(duplicate, segments=source, label="default")
    with pytest.raises(ValueError, match="does not match"):
        index_changes(mismatch, segments=source, label="default")


def test_review_summary_calculates_recall_harm_and_important_misses() -> None:
    items = build_review_items(
        segments(),
        [
            change(0, "元の一", "既定一"),
            change(2, "元の三", "共通三"),
            change(3, "元の四", "既定四"),
        ],
        [
            change(1, "元の二", "なし二"),
            change(2, "元の三", "共通三"),
            change(3, "元の四", "なし四"),
        ],
    )
    labels = [
        ("useful_correction", "missed_correction", ["proper_noun"]),
        ("missed_correction", "useful_correction", []),
        ("useful_correction", "useful_correction", []),
        ("harmful_correction", "equivalent_alternative", []),
    ]
    for item, (default_label, none_label, term_types) in zip(items, labels, strict=True):
        item["review"]["default_label"] = default_label
        item["review"]["none_label"] = none_label
        item["review"]["term_types"] = term_types
    document = build_review_document(items, source_paths={})

    summary = summarize_review(document)

    assert summary["status"] == "complete"
    assert summary["none_useful_recall_vs_default"] == 0.5
    assert summary["default_harmful_rate"] == pytest.approx(1 / 3)
    assert summary["none_harmful_rate"] == 0
    assert summary["none_important_missed_corrections"]["proper_noun"] == 1
    assert "none useful recall vs default: `0.5`" in render_markdown(document, summary)


def test_partial_review_does_not_invent_quality_metrics() -> None:
    items = build_review_items(segments(), [change(0, "元の一", "既定一")], [])
    document = build_review_document(items, source_paths={})

    summary = summarize_review(document)

    assert summary["status"] == "partial"
    assert summary["reviewed_items"] == 0
    assert summary["none_useful_recall_vs_default"] is None
    assert summary["default_harmful_rate"] is None


def test_audio_extraction_uses_safe_docker_paths(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    video = storage_root / "uploads" / "sample.mp4"
    output_dir = storage_root / "temp" / "audit"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    items = build_review_items(segments(), [change(0, "元の一", "既定一")], [])
    commands: list[list[str]] = []

    def fake_runner(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    extract_audio_snippets(
        items,
        video_path=video,
        output_dir=output_dir,
        docker_service="worker",
        storage_root=storage_root,
        runner=fake_runner,
    )

    command = commands[0]
    assert command[:6] == ["docker", "compose", "exec", "-T", "worker", "ffmpeg"]
    assert "/app/storage/uploads/sample.mp4" in command
    assert any(value.startswith("/app/storage/temp/audit/audio/") for value in command)
    assert "-vn" in command


def test_csv_review_round_trip_is_excel_friendly(tmp_path: Path) -> None:
    items = build_review_items(segments(), [change(0, "元の一", "既定一")], [])
    document = build_review_document(items, source_paths={})
    csv_path = tmp_path / "review.csv"
    write_review_csv(items, csv_path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0].keys())
    rows[0]["default_label"] = "useful_correction"
    rows[0]["none_label"] = "missed_correction"
    rows[0]["preferred_output"] = "default"
    rows[0]["term_types"] = "proper_noun;technical_term"
    rows[0]["notes"] = "要確認"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    updated = apply_review_csv(document, csv_path)
    review = updated["items"][0]["review"]

    assert review["default_label"] == "useful_correction"
    assert review["none_label"] == "missed_correction"
    assert review["term_types"] == ["proper_noun", "technical_term"]
