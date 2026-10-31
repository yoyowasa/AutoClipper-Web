"""Per-clip visual decisions after subtitle confirmation, before exact preview."""

from app.jobs.automatic_text_style import choose_emphasis, choose_text_styles
from app.jobs.quality_gate import _subtitle_events_for_review_clip
from app.production_choices import ChoiceCandidate, append_choice, choice_values, value_hash
from app.render.short_crop_decision import ShortCropDecision
from app.render.render_short import SHORT_BANNER_HEIGHT
from app.render.subtitles_ass import SubtitleLayout
from app.scoring.short_framing import SHORT_FRAMING_VERSION
from app.intelligence.choice_policy_runtime import frozen_policy, weight
from app.intelligence.choice_policy_schema import FRAMING_OPTIONS


VISUAL_DECISION_POLICY = "confirmed-subtitle-visuals-v2"


def decide_visuals(document, clip, *, settings, video, source, crop_resolver=None, content_choice=None, framing_revision=None,
                   content_fallback_reason=None, framing_only=False, targets=None):
    """Combine content intent with existing geometric detection and ASS fitting."""
    targets = set(targets) if targets is not None else {"framing", "text_style", "effects"}
    ranked, emphasis_reason = [], "unchanged_subtitle_emphasis"
    layout = (SubtitleLayout.short(settings) if clip.type == "short" else
              SubtitleLayout.normal(video.width or 1920, video.height or 1080, settings))
    top = SHORT_BANNER_HEIGHT if clip.type == "short" and document.short_top_banner_enabled else 0
    bottom = layout.height - (SHORT_BANNER_HEIGHT if clip.type == "short" and document.short_bottom_banner_enabled else 0)
    segments = [s for s in document.segments if s.id in set(clip.segment_ids)]
    if not framing_only:
        events, _ = _subtitle_events_for_review_clip(document, clip, width=layout.width, height=layout.height)
        if "text_style" in targets:
            choose_text_styles(clip, layout, events=events, top=top, bottom=bottom, settings=settings)
        if "effects" in targets:
            ranked, emphasis_reason = choose_emphasis(clip, segments, layout, top=top, bottom=bottom, settings=settings)
    manual_framing = "framing" in clip.manual_decision_fields
    preferred = content_choice.strategy if content_choice else None
    if not manual_framing and frozen_policy(settings, clip.type):
        learned = sorted(FRAMING_OPTIONS, key=lambda s: (-weight(settings, clip.type, f"framing.{s}"), s != preferred, s))[0]
        if weight(settings, clip.type, f"framing.{learned}") > (weight(settings, clip.type, f"framing.{preferred}") if preferred else 1):
            preferred = learned
    if clip.type == "short" and "framing" in targets:
        from app.audio.transcribe_faster_whisper import TranscriptSegment
        from app.render.render_short import resolve_short_crop_plan
        from app.video.speaker_detect import dialogue_windows_for_clip
        if not manual_framing:
            clip.short_layout = "auto"
            clip.framing_offset_x = clip.framing_offset_y = 0
            clip.framing_zoom = 1
        requested = clip.short_layout or document.short_layout
        plan, faces = (crop_resolver or resolve_short_crop_plan)(
            source, clip.start, clip.end, layout=requested, width=video.width, height=video.height,
            target_height=bottom - top, dialogue_windows=dialogue_windows_for_clip(
                clip.start, clip.end, [TranscriptSegment(start=s.start, end=s.end, text=s.text) for s in segments],
            ),
            **({"preferred_strategy": preferred} if preferred and not manual_framing else {}),
        )
        clip.automatic_crop = ShortCropDecision(start=clip.start, end=clip.end, width=video.width, height=video.height,
                                               target_height=bottom - top, layout=requested, plan=plan, faces=list(faces))
    revision = value_hash({"text": [(s.id, s.start, s.end, s.text) for s in segments],
                           "title": clip.title, "hook": clip.hook_text, "crop": clip.automatic_crop,
                           "styles": [clip.title_style, clip.hook_style, clip.subtitle_style, clip.subtitle_styles]})
    common = dict(clipId=clip.id, stage="applied", policyVersion=VISUAL_DECISION_POLICY, inputRevision=revision)
    crop = clip.automatic_crop
    content_values = ({"contentPreferredLayout": content_choice.strategy, "highlightType": content_choice.highlight_type,
                       "framingEvidenceIds": content_choice.evidence_ids, "framingDecisionRevision": framing_revision,
                       "framingReason": content_choice.reason} if content_choice and not manual_framing else {})
    fallback_reason = content_fallback_reason if clip.type == "short" and not manual_framing else None
    framing_common = {**common, **({"policyVersion": SHORT_FRAMING_VERSION} if content_values or fallback_reason else {})}
    if "framing" in targets:
        append_choice(document.choice_history, kind="framing",
                      source="manual" if manual_framing else "fallback" if fallback_reason else "automatic",
                      reason="explicit_manual_override_preserved" if manual_framing else
                      fallback_reason if fallback_reason else
                      content_choice.reason if content_choice else
                      crop.plan.fallback_reason or "existing_scene_crop_signals" if crop else "normal_source_frame_preserved",
                      values=choice_values({"shortLayout": clip.short_layout, "framingOffsetX": clip.framing_offset_x,
                          "framingOffsetY": clip.framing_offset_y, "framingZoom": clip.framing_zoom,
                          "resolvedLayout": crop.plan.strategy_order[0] if crop else "source",
                          "cropSignalSource": crop.plan.signal_source if crop else "source_video",
                          "cropFallbackReason": crop.plan.fallback_reason if crop else None, **content_values,
                          **({"policyPreferredLayout": preferred} if preferred else {})}), **framing_common)
        if content_values and crop and crop.plan.strategy_order[0] != preferred:
            append_choice(document.choice_history, kind="framing", source="fallback",
                          reason="内容に基づく画角を選びましたが、検出・幾何条件を満たせないため全体表示に置換しました。",
                          values=choice_values({**content_values, "resolvedLayout": crop.plan.strategy_order[0],
                                                "cropFallbackReason": crop.plan.fallback_reason}), **framing_common)
    if framing_only:
        return
    for role in (("title", "hook", "subtitle") if "text_style" in targets else ()):
        manual = f"{role}_style" in clip.manual_decision_fields
        append_choice(document.choice_history, kind="text_style", source="manual" if manual else "automatic",
                      reason="explicit_manual_override_preserved" if manual else "confirmed_text_fit_and_safe_area",
                      values=choice_values({f"{role}Style": getattr(clip, f"{role}_style").model_dump(by_alias=True)
                                            if getattr(clip, f"{role}_style") else None}), **common)
    if "effects" in targets:
        append_choice(document.choice_history, kind="effects",
                      source="manual" if "subtitle_styles" in clip.manual_decision_fields else "automatic",
                      timeBasis="source", reason=emphasis_reason,
                      values=choice_values({"subtitleStyles": [s.model_dump(by_alias=True) for s in clip.subtitle_styles],
                                            "emphasisSignal": next(("topic" if reason == "selected_copy_topic" else
                                                "number" if any(c.isdigit() for c in s.text) else "reaction"
                                                for s, _score, reason, selected in ranked if selected), "none"),
                                            "emphasisTopicWeight": weight(settings, clip.type, "effects.topic"),
                                            "emphasisNumberWeight": weight(settings, clip.type, "effects.number"),
                                            "emphasisReactionWeight": weight(settings, clip.type, "effects.reaction"),
                                            "additionalEffects": "none"}),
                      candidates=[ChoiceCandidate(id=s.id, outcome="selected" if selected else "not_selected", reason=reason,
                                                  values={"start": s.start, "end": s.end, "score": score})
                                  for s, score, reason, selected in ranked],
                      selectedIds=[s.id for s, _score, _reason, selected in ranked if selected], **common)
