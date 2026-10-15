from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


ERROR_MESSAGES = {
    "CLIENT_NOT_CONFIGURED": "GoogleのDesktopクライアント設定を配置してください。",
    "CLIENT_INVALID": "Googleクライアント設定の形式を確認してください。",
    "STATE_INVALID": "認可の有効期限切れ、または不正な認可です。接続をやり直してください。",
    "CHANNEL_MISMATCH": "認可したチャンネルが指定したチャンネルIDと一致しません。",
    "RECONNECT_REQUIRED": "YouTubeへの再接続が必要です。",
    "OAUTH_FAILED": "Google認可を完了できませんでした。接続をやり直してください。",
    "SCOPES_MISSING": "動画とAnalyticsの読み取り権限を両方許可してください。",
    "QUOTA_EXCEEDED": "YouTube APIの利用枠を超えました。時間をおいて同期してください。",
    "FORBIDDEN": "YouTube APIの権限またはAPIの有効化を確認してください。",
    "NETWORK_ERROR": "YouTube APIに接続できませんでした。",
    "API_REJECTED": "YouTube APIが要求を受け付けませんでした。",
    "INVALID_RESPONSE": "YouTube APIの応答を検証できませんでした。",
    "SYNC_LIMIT": "同期の上限時間またはリクエスト数に達しました。",
    "SYNC_FAILED": "同期を完了できませんでした。",
    "QUEUE_FAILED": "同期をキューへ登録できませんでした。",
    "WORKER_INTERRUPTED": "同期のworkerが中断されました。もう一度同期してください。",
}


class YouTubeError(Exception):
    """Only allowlisted codes may escape provider/credential handling."""

    def __init__(self, code: str):
        self.code = code if code in ERROR_MESSAGES else "SYNC_FAILED"
        super().__init__(ERROR_MESSAGES[self.code])
