"""Manual framing follows automatic decisions, with an explicit comparison record."""

from app.production_choices import ChoiceCandidate, append_choice


def framing_edit_error(document, clip) -> str | None:
    if not document.subtitle_only_auto:
        return None
    if document.state not in {"awaiting_review", "completed"}:
        return "書き出し中は画角を変更できません。完了後に調整してください。"
    if not clip.confirmed:
        return "画角は字幕を確定し、自動決定が終わってから詳細編集で調整できます。"
    if clip.automatic_decision_state != "ready":
        return "画角の自動決定が終わるまでお待ちください。"
    return None


def record_manual_framing(document, clip, before) -> None:
    keys = {"framingOffsetX": "framing_offset_x", "framingOffsetY": "framing_offset_y",
            "framingZoom": "framing_zoom", "shortLayout": "short_layout"}
    values = {key: getattr(clip, attr) for key, attr in keys.items()}
    if values == {key: getattr(before, attr) for key, attr in keys.items()}:
        return
    automatic = next((c for c in reversed(document.choice_history)
                      if c.clipId == clip.id and c.kind == "framing" and c.source in {"automatic", "fallback"}), None)
    candidates = [ChoiceCandidate(id="manual_adjustment", values=values, outcome="selected")]
    if automatic:
        candidates.insert(0, ChoiceCandidate(id=automatic.id, values=automatic.values, outcome="not_selected",
                                            reason="人が自動画角から調整しました。"))
    append_choice(document.choice_history, kind="framing", clipId=clip.id, stage="applied", source="manual",
                  policyVersion="manual-framing-after-confirm-v1", inputRevision=clip.automatic_decision_revision,
                  reason="字幕確定後に人が画角を調整して承認しました。", values=values, candidates=candidates,
                  selectedIds=["manual_adjustment"], recommendedId=automatic.id if automatic else None)

