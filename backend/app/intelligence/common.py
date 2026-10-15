import re
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
    "API_5XX": "YouTube APIの一時的な障害で取得できないレポートがあります。時間をおいて同期してください。",
    "API_BAD_REQUEST": "YouTube APIが要求の条件を受け付けませんでした（400）。",
    "API_NOT_FOUND": "YouTube APIの取得対象が見つかりませんでした（404）。",
    "API_CONFLICT": "YouTube APIで要求が競合しました（409）。",
    "API_GONE": "YouTube APIの取得対象が利用できなくなりました（410）。",
    "API_HTTP_ERROR": "YouTube APIがHTTPエラーを返しました。同期履歴のステータスを確認してください。",
    "INVALID_RESPONSE": "YouTube APIの応答を検証できませんでした。",
    "SYNC_LIMIT": "同期の上限時間またはリクエスト数に達しました。",
    "SYNC_FAILED": "同期を完了できませんでした。",
    "QUEUE_FAILED": "同期をキューへ登録できませんでした。",
    "WORKER_INTERRUPTED": "同期のworkerが中断されました。もう一度同期してください。",
}


class YouTubeError(Exception):
    """Only allowlisted codes may escape provider/credential handling."""

    def __init__(self, code: str, *, http_status: int | None = None, reasons=()):
        self.code = code if code in ERROR_MESSAGES else "SYNC_FAILED"
        self.http_status = http_status
        # Only structured reason identifiers, never the provider's message/body.
        self.reasons = sorted({reason for reason in reasons
                               if isinstance(reason, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", reason)})[:10]
        super().__init__(ERROR_MESSAGES[self.code])

    def details(self) -> dict:
        return {"reason": self.code, "httpStatus": self.http_status, "googleReasons": self.reasons}
