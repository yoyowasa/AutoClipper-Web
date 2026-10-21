"""Copy only allowlisted hints from the exact selection/title input artifacts."""

import json

from app.intelligence.performance_schema import UsedPerformanceHint


def recorded_performance_hints(paths, job_id, clip_id, format):
    from app.jobs.title_hook_suggestions import title_hook_suggestion_input_path

    root = paths.job_outputs(job_id)
    candidates = [(root / name, "selection") for name in ("codex_initial_selection_summary.json", "codex_reselection_summary.json")]
    candidates.append((title_hook_suggestion_input_path(root, clip_id), "title_hook"))
    hints = []
    for path, target in candidates:
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for raw in payload.get("performanceHints", []):
            hint = UsedPerformanceHint.model_validate(raw)
            value = hint.model_dump(by_alias=True, mode="json")
            if hint.target == target and hint.format == format and value not in hints:
                hints.append(value)
    return hints
