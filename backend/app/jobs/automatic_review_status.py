"""Safe, actionable status for automatically produced clips."""

from app.jobs.quality_gate import load_quality_gate_decision, quality_gate_decision_path


REASONS = {
    "tracking_subject_outside_safe_area": "追従する対象が安全な表示範囲からはみ出しています",
    "tracking_evidence_missing": "追従する対象の位置を確認する記録がありません",
    "tracking_samples_missing": "追従する対象の時刻ごとの位置を確認できませんでした",
    "tracking_time_coverage_insufficient": "追従する対象を複数の時刻で確認できませんでした",
    "rendered_overlay_contract_mismatch": "上下の帯が確定した設定と一致しませんでした",
    "render_failures_present": "動画の再書き出しに失敗しました",
    "export_count_mismatch": "必要な完成動画をすべて作成できませんでした",
    "rendered_media_artifact_missing": "完成動画または字幕ファイルを確認できませんでした",
    "rendered_stream_duration_unavailable": "完成動画の映像・音声の長さを確認できませんでした",
    "rendered_media_stream_contract_failed": "完成動画のサイズ・長さ・音声の検査に通りませんでした",
    "overlay_layout_outside_safe_area": "文字が安全な表示範囲からはみ出しています",
    "overlay_layout_evidence_incomplete": "文字の収まりを確認できませんでした",
    "content_gate_evaluation_failed": "書き出し前の品質検証を実行できませんでした",
    "post_render_gate_evaluation_failed": "完成動画の品質検証を実行できませんでした",
    "rendered_media_artifact_invalid": "完成動画の映像・音声の検証に通りませんでした",
    "post_render_visual_evidence_insufficient": "画角の収まりを自動で確認できませんでした",
    "post_render_visual_contract_failed": "画角または帯が表示範囲に収まっていません",
    "rendered_content_contract_mismatch": "完成動画と確定内容が一致しませんでした",
}


def automatic_stop_reasons(document, directory) -> list[str]:
    if not document.subtitle_only_auto or document.state != "awaiting_review":
        return []
    if not all(c.confirmed and c.automatic_decision_state == "ready" for c in document.clips):
        return []
    messages = []
    for stage, label in (("content", "書き出し前"), ("post_render", "完成動画")):
        path = quality_gate_decision_path(directory, stage)
        if not path.is_file():
            continue
        decision = load_quality_gate_decision(path)
        repair = next((check.evidence["automaticFramingRepair"] for check in decision.checks
                       if "automaticFramingRepair" in check.evidence), {})
        for check in decision.checks:
            if check.outcome == "pass":
                continue
            code = check.reason_code or check.code
            if check.code in {"content.human_subtitle_review", "content.preview_ready"}:
                continue
            detail = REASONS.get(code, f"品質条件を確認できませんでした（{code}）")
            items = [
                item for key in ("failures", "unknown") for item in check.evidence.get(key, [])
                if isinstance(item, dict) and (item.get("clipId") or item.get("candidateId"))
            ]
            evidence = str(items or check.evidence)
            if check.code in {"post_render.export_count", "post_render.render_failures"} and repair.get("failedClipIds"):
                evidence = str(repair["failedClipIds"])
            clips = [c for c in document.clips if c.id in evidence] or document.clips
            for clip in clips:
                index = [c.id for c in document.clips if c.type == clip.type].index(clip.id) + 1
                name = f"{'ショート' if clip.type == 'short' else '通常'}{index}"
                item = next((item for item in items if item.get("clipId", item.get("candidateId")) == clip.id), {})
                reason = REASONS.get(item.get("reason"), detail)
                if clip.id in repair.get("attemptedClipIds", []):
                    reason = f"安全な画角で再書き出ししましたが、{reason}"
                messages.append(f"{label}の検証で停止: {name}・元動画 {clip.start:.1f}〜{clip.end:.1f}秒: {reason}")
    return messages
