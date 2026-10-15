MESSAGES = {
    "OWN_OAUTH_REQUIRED": "自チャンネルのYouTube接続を確認してください。",
    "DERIVED_NOT_ALLOWED": "分析の利用条件が未承認です。",
    "STATISTICS_BUSY": "同期中です。完了後に分析してください。",
    "STATISTICS_FAILED": "分析前の同期に失敗しました。前回の分析は保持しています。",
    "CODEX_EVIDENCE_UNAVAILABLE": "保持期限内の分析用統計がありません。同期してから分析してください。",
    "CODEX_CONTEXT_TOO_LARGE": "分析の入力が上限を超えています。入力の分割が必要です。",
    "CODEX_INVALID_OUTPUT": "分析の形式・根拠を検証できませんでした。前回の分析は保持しています。",
    "CODEX_STALE_EVIDENCE": "分析中に根拠が更新されたか、期限が切れました。再実行してください。",
    "CODEX_TIMEOUT": "分析が制限時間を超えました。前回の分析は保持しています。",
    "CODEX_BRIDGE_UNAVAILABLE": "Codex中継が利用できません。起動・更新後の再起動を確認してください。",
    "CODEX_FAILED": "Codexの分析に失敗しました。ChatGPTログインと利用状況を確認してください。",
    "QUEUE_FAILED": "分析をキューに登録できませんでした。",
    "WORKER_INTERRUPTED": "分析のworkerが中断されました。必要なら再実行してください。",
}


class AnalysisError(Exception):
    def __init__(self, code: str):
        self.code = code if code in MESSAGES else "CODEX_FAILED"
        super().__init__(MESSAGES[self.code])
