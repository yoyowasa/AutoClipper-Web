from pathlib import Path
from datetime import UTC

from app.intelligence.analysis_prompt import analysis_prompt
from app.intelligence.analysis_schema import analysis_response_schema
from app.scoring.codex_title_hook_suggestions import CodexTitleHookSuggestionGenerator
from app.storage.paths import StoragePaths

ANALYSIS_MODEL = "gpt-6-astra"
ANALYSIS_EFFORT = "high"
ANALYSIS_TIMEOUT_SECONDS = 960


def cleanup_analysis_files(paths: StoragePaths, request_id: str | None) -> None:
    if request_id:
        for path in paths.analysis_bridge_files(request_id):
            path.unlink(missing_ok=True)


class ChannelAnalysisGenerator(CodexTitleHookSuggestionGenerator):
    task = "channel_self_analysis"
    response_schema = analysis_response_schema()
    system_prompt = ""

    def __init__(self, *, paths: StoragePaths, run_id: str, on_request, **kwargs):
        super().__init__(storage_root=paths.root, job_id=run_id, clip_id="analysis", model=ANALYSIS_MODEL,
                         timeout_seconds=ANALYSIS_TIMEOUT_SECONDS, **kwargs)
        self.on_request = on_request
        self.last_request_id = None

    def request_path(self, request_id: str) -> Path:
        if request_id != self.last_request_id:
            self.last_request_id = request_id
            self.on_request(request_id)
        return super().request_path(request_id)

    def parse_output(self, output: dict) -> dict:
        # Item validation belongs to analysis_validation, which preserves valid peers.
        return output

    def analyze(self, context):
        self.system_prompt = analysis_prompt(context.payload)
        self.expires_at = context.expires_at.replace(tzinfo=UTC)
        return self.generate({}, ())
