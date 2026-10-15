import hashlib
import hmac
import logging
import os
import re
import secrets
from datetime import timedelta
from uuid import uuid4

from app.config import Settings
from app.intelligence.common import YouTubeError, now
from app.intelligence.credentials import oauth_flow
from app.intelligence.secret_files import read_private_json, write_private_json
from app.storage.paths import StoragePaths

COOKIE = "autoclipper_youtube_oauth"
STATE_TTL_SECONDS = 600


class RedactOAuthCallback(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) == 5:
            args = list(record.args)
            if isinstance(args[2], str) and args[2].split("?", 1)[0].rstrip("/") == "/api/intelligence/oauth/callback":
                args[2] = "/api/intelligence/oauth/callback"
                record.args = tuple(args)
        return True


logging.getLogger("uvicorn.access").addFilter(RedactOAuthCallback())


def begin_oauth(paths: StoragePaths, config: Settings, channel_id: str) -> tuple[str, str]:
    state, nonce, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    flow = oauth_flow(paths, config, state=state, verifier=verifier)
    url, _ = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="false")
    write_private_json(paths.youtube_oauth_states / f"{hashlib.sha256(state.encode()).hexdigest()}.json", {
        "channel_id": channel_id, "state": state, "verifier": verifier,
        "nonce_hash": hashlib.sha256(nonce.encode()).hexdigest(),
        "expires_at": (now() + timedelta(seconds=STATE_TTL_SECONDS)).isoformat(),
    })
    return url, nonce


def complete_oauth(paths: StoragePaths, config: Settings, state: str, code: str, nonce: str):
    from datetime import datetime

    if not re.fullmatch(r"[A-Za-z0-9_-]{40,100}", state) or not nonce or not code or len(code) > 4096:
        raise YouTubeError("STATE_INVALID")
    path = paths.youtube_oauth_states / f"{hashlib.sha256(state.encode()).hexdigest()}.json"
    claimed = path.with_name(f".{uuid4().hex}.claimed")
    try:
        pending = read_private_json(path)
        if (datetime.fromisoformat(pending["expires_at"]) <= now()
                or not hmac.compare_digest(pending["state"], state)
                or not hmac.compare_digest(pending["nonce_hash"], hashlib.sha256(nonce.encode()).hexdigest())):
            raise YouTubeError("STATE_INVALID")
        os.replace(path, claimed)  # one successful consumer, even across processes
        flow = oauth_flow(paths, config, state=state, verifier=pending["verifier"])
        flow.fetch_token(code=code, timeout=10)
        return pending["channel_id"], flow.credentials
    except YouTubeError:
        raise
    except FileNotFoundError:
        raise YouTubeError("STATE_INVALID") from None
    except Exception:
        raise YouTubeError("OAUTH_FAILED") from None
    finally:
        claimed.unlink(missing_ok=True)
