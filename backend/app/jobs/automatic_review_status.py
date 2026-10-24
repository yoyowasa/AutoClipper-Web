"""Safe, actionable status for automatically produced clips."""

from app.jobs.quality_gate import load_quality_gate_decision, quality_gate_decision_path


REASONS = {
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
        for check in decision.checks:
            if check.outcome == "pass":
                continue
            code = check.reason_code or check.code
            if check.code in {"content.human_subtitle_review", "content.preview_ready"}:
                continue
            detail = REASONS.get(code, f"品質条件を確認できませんでした（{code}）")
            # The stored gate exposes IDs, not a new interpretation of its evidence.
            evidence = str(check.evidence)
            clips = [c for c in document.clips if c.id in evidence] or document.clips
            for clip in clips:
                messages.append(f"{label}の検証で停止: {clip.id}・元動画 {clip.start:.1f}〜{clip.end:.1f}秒: {detail}")
    return messages
