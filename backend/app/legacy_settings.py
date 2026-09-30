"""Read historical settings without reactivating retired paid API features."""
from typing import Any

RETIRED_API_SETTING_KEYS = frozenset({
    'enableOpenAIScoring',
    'ensureSelectedOpenAIScored',
    'ensure_selected_openai_scored',
    'openaiCandidateLimit',
    'openaiFallbackToRuleScore',
    'openaiFinalistScoringLimit',
    'openaiModel',
    'openaiScoring',
    'openai_candidate_limit',
    'openai_fallback_to_rule_score',
    'openai_finalist_scoring_limit',
    'openai_model',
    'subtitleCorrectionBatchSize',
    'subtitleCorrectionContextSegments',
    'subtitleCorrectionFallbackEnabled',
    'subtitleCorrectionMinConfidence',
    'subtitleCorrectionMode',
    'subtitleCorrectionModel',
    'subtitleCorrectionReasoningEffort',
    'subtitleCorrectionScope',
    'subtitleCorrectionSuspicionThreshold',
    'subtitle_correction_batch_size',
    'subtitle_correction_context_segments',
    'subtitle_correction_fallback_enabled',
    'subtitle_correction_min_confidence',
    'subtitle_correction_mode',
    'subtitle_correction_model',
    'subtitle_correction_reasoning_effort',
    'subtitle_correction_scope',
    'subtitle_correction_suspicion_threshold',
    'transcriptCorrectionGlossary',
    'transcript_correction_glossary',
    'useOpenAIScoring',
    'use_openai_scoring',
})


def without_retired_api_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in settings.items() if key not in RETIRED_API_SETTING_KEYS}
