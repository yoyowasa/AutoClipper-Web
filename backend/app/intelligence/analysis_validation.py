from app.intelligence.analysis_input import AnalysisContext
from app.intelligence.analysis_schema import Review
from app.intelligence.recommendation_rules import FRAMEWORK_VERSION


def validate_review(output, context: AnalysisContext) -> Review:
    review = Review.model_validate(output)
    payload = context.payload
    if (review.id != payload["review_id"] or review.channel_id != payload["channel"]["id"]
            or review.batch_run_id != payload["batch"]["run_id"]
            or review.recommendation_framework_version != FRAMEWORK_VERSION):
        raise ValueError("CODEX_INVALID_OUTPUT")
    for item in [*review.findings, *review.proposals]:
        if not set(item.evidence_ids) <= context.evidence.keys():
            raise ValueError("CODEX_INVALID_OUTPUT")
    for proposal in review.proposals:
        baseline = context.videos.get(proposal.baseline_video_id)
        if not baseline or baseline["format"] != proposal.format or proposal.primary_metric != "views":
            raise ValueError("CODEX_INVALID_OUTPUT")
        if not any(context.evidence[id]["video_id"] == proposal.baseline_video_id
                   and context.evidence[id]["source"] in {"youtube_analytics", "youtube_public"} for id in proposal.evidence_ids):
            raise ValueError("CODEX_INVALID_OUTPUT")
    for finding in review.findings:
        if finding.format != "all" and any(
            item["video_id"] and context.videos[item["video_id"]]["format"] != finding.format
            for item in (context.evidence[id] for id in finding.evidence_ids)
        ):
            finding.format = "all"
    return review
