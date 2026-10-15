import json
import logging

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from app.config import Settings
from app.intelligence.common import YouTubeError
from app.intelligence.secret_files import read_private_json, write_private_json
from app.storage.paths import StoragePaths

SCOPES = ("https://www.googleapis.com/auth/youtube.readonly", "https://www.googleapis.com/auth/yt-analytics.readonly")


class NoCredentialLogs(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return False


# These libraries log authorization headers, grant bodies and token responses at
# DEBUG. Suppress at their emitting logger even if the operator enables DEBUG.
for logger_name in ("requests_oauthlib.oauth2_session", "oauthlib.oauth2.rfc6749.clients.base",
                    "oauthlib.oauth2.rfc6749.clients.web_application", "google_auth_oauthlib.flow"):
    logging.getLogger(logger_name).addFilter(NoCredentialLogs())


class BoundedRequest(Request):
    def __call__(self, *args, **kwargs):
        kwargs["timeout"] = 10
        return super().__call__(*args, **kwargs)


def oauth_flow(paths: StoragePaths, config: Settings, *, state: str, verifier: str) -> Flow:
    try:
        client = read_private_json(paths.google_client)
        installed = client["installed"]
        if (installed["auth_uri"] != "https://accounts.google.com/o/oauth2/auth"
                or installed["token_uri"] != "https://oauth2.googleapis.com/token"):
            raise ValueError("Invalid endpoints")
        return Flow.from_client_config(client, scopes=list(SCOPES), state=state, code_verifier=verifier,
                                       redirect_uri=config.youtube_oauth_redirect_uri)
    except FileNotFoundError:
        raise YouTubeError("CLIENT_NOT_CONFIGURED") from None
    except Exception:
        raise YouTubeError("CLIENT_INVALID") from None


def persist_credentials(paths: StoragePaths, channel_id: str, credentials: Credentials) -> None:
    if not credentials.refresh_token:
        raise YouTubeError("OAUTH_FAILED")
    if credentials.granted_scopes is not None and not set(SCOPES).issubset(credentials.granted_scopes):
        raise YouTubeError("SCOPES_MISSING")
    write_private_json(paths.youtube_token(channel_id), json.loads(credentials.to_json()))


def load_credentials(paths: StoragePaths, channel_id: str) -> Credentials:
    try:
        info = read_private_json(paths.youtube_token(channel_id))
        # Credentials must never send a refresh token to a configurable endpoint.
        if info.get("token_uri") != "https://oauth2.googleapis.com/token":
            raise YouTubeError("RECONNECT_REQUIRED")
        credentials = Credentials.from_authorized_user_info(info, list(SCOPES))
        if not credentials.valid:
            credentials.refresh(BoundedRequest())
            persist_credentials(paths, channel_id, credentials)
        return credentials
    except RefreshError as error:
        # Inspect only to classify; never render or log the original response.
        code = "RECONNECT_REQUIRED" if "invalid_grant" in str(error) else "OAUTH_FAILED"
        raise YouTubeError(code) from None
    except YouTubeError:
        raise
    except Exception:
        raise YouTubeError("RECONNECT_REQUIRED") from None
