import math
import time
from datetime import date
from typing import Any

import httpx

from app.intelligence.common import YouTubeError

METRICS = ("views", "engagedViews", "estimatedMinutesWatched", "averageViewDuration", "averageViewPercentage",
           "likes", "comments", "shares", "subscribersGained", "subscribersLost")
MAX_REQUESTS = 90
DISCOVERY_LIMIT = 200
INITIAL_LIMIT = 50
REPORT_PAGE_SIZE = 200
RETRYABLE_STATUS = {500, 502, 503, 504}
RETRY_DELAYS = (0.25, 0.5)


def response_error(response: httpx.Response) -> YouTubeError:
    try:
        reasons = [row.get("reason") for row in response.json().get("error", {}).get("errors", [])]
    except (ValueError, AttributeError, TypeError):
        reasons = []
    status = response.status_code
    if status == 401:
        code = "RECONNECT_REQUIRED"
    elif status == 429 or (status == 403 and any(reason in {"quotaExceeded", "dailyLimitExceeded"} for reason in reasons
                                               if isinstance(reason, str))):
        code = "QUOTA_EXCEEDED"
    elif status == 403:
        code = "FORBIDDEN"
    elif 500 <= status < 600:
        code = "API_5XX"
    else:
        code = {400: "API_BAD_REQUEST", 404: "API_NOT_FOUND", 409: "API_CONFLICT", 410: "API_GONE"}.get(status, "API_HTTP_ERROR")
    return YouTubeError(code, http_status=status, reasons=reasons)


class YouTubeClient:
    def __init__(self, access_token: str, *, budget_seconds: int = 120, transport=None, clock=time.monotonic, sleep=time.sleep):
        self._token = access_token
        self._transport = transport
        self._clock = clock
        self._sleep = sleep
        self._deadline = clock() + budget_seconds
        self.requests = 0

    def get(self, endpoint: str, params: dict[str, Any], *, analytics: bool = False) -> dict[str, Any]:
        if endpoint not in ({"reports"} if analytics else {"channels", "playlistItems", "videos"}):
            raise YouTubeError("API_REJECTED")
        base = "https://youtubeanalytics.googleapis.com/v2/" if analytics else "https://www.googleapis.com/youtube/v3/"
        try:
            for attempt in range(len(RETRY_DELAYS) + 1):
                remaining = self._deadline - self._clock()
                if remaining <= 0 or self.requests >= MAX_REQUESTS:
                    raise YouTubeError("SYNC_LIMIT")
                self.requests += 1
                with httpx.Client(transport=self._transport, timeout=min(10, remaining), follow_redirects=False) as client:
                    response = client.get(base + endpoint, params=params, headers={"Authorization": "Bearer " + self._token})
                if self._clock() >= self._deadline:
                    raise YouTubeError("SYNC_LIMIT")
                if response.status_code == 200:
                    result = response.json()
                    if not isinstance(result, dict):
                        raise YouTubeError("INVALID_RESPONSE")
                    return result
                if response.status_code not in RETRYABLE_STATUS or attempt == len(RETRY_DELAYS):
                    raise response_error(response)
                delay = RETRY_DELAYS[attempt]
                if self.requests >= MAX_REQUESTS or self._deadline - self._clock() <= delay:
                    raise YouTubeError("SYNC_LIMIT")
                self._sleep(delay)
        except httpx.HTTPError:
            raise YouTubeError("SYNC_LIMIT" if self._clock() >= self._deadline else "NETWORK_ERROR") from None
        except ValueError:
            raise YouTubeError("INVALID_RESPONSE") from None

    def identity(self) -> dict[str, Any]:
        items = self.get("channels", {"part": "snippet,contentDetails", "mine": "true"}).get("items", [])
        if len(items) != 1:
            raise YouTubeError("CHANNEL_MISMATCH")
        return items[0]

    def uploads(self, playlist_id: str) -> tuple[list[str], bool]:
        ids: list[str] = []
        token, seen = "", set()
        while len(ids) < DISCOVERY_LIMIT:
            params = {"part": "contentDetails", "playlistId": playlist_id, "maxResults": 50}
            if token:
                params["pageToken"] = token
            result = self.get("playlistItems", params)
            ids.extend(item["contentDetails"]["videoId"] for item in result.get("items", []))
            token = result.get("nextPageToken", "")
            if not token or len(ids) >= DISCOVERY_LIMIT:
                return list(dict.fromkeys(ids[:DISCOVERY_LIMIT])), bool(token)
            if token in seen:
                raise YouTubeError("INVALID_RESPONSE")
            seen.add(token)
        return ids, True

    def videos(self, ids: list[str]):
        for offset in range(0, len(ids), 50):
            batch = ids[offset:offset + 50]
            result = self.get("videos", {"part": "snippet,contentDetails,statistics,status,liveStreamingDetails", "id": ",".join(batch)})
            yield batch, result.get("items", [])

    def report(self, channel_id: str, start: date, end: date, dimensions: str = "", video_ids: list[str] | None = None):
        single_page = dimensions == "day,video"
        if single_page and (not video_ids or end < start or len(video_ids) * ((end - start).days + 1) > REPORT_PAGE_SIZE):
            raise YouTubeError("API_BAD_REQUEST")
        # The API permits adding a multi-value filter as a dimension. A single
        # video uses the base report and we attach that known ID to the result.
        single_video = bool(video_ids and len(video_ids) == 1 and "video" in dimensions.split(","))
        wire_dimensions = ",".join(key for key in dimensions.split(",") if not (single_video and key == "video"))
        params = {"ids": "channel==" + channel_id, "startDate": str(start), "endDate": str(end),
                  "metrics": ",".join(METRICS), "maxResults": REPORT_PAGE_SIZE}
        if wire_dimensions:
            params.update(dimensions=wire_dimensions, sort="-views" if "video" in wire_dimensions.split(",") else wire_dimensions)
        if video_ids:
            params["filters"] = "video==" + ",".join(video_ids)
        expected = set(METRICS) | (set(wire_dimensions.split(",")) if wire_dimensions else set())
        rows, seen, index = [], set(), 1
        while True:
            result = self.get("reports", {**params, "startIndex": index}, analytics=True)
            columns = [column.get("name") for column in result.get("columnHeaders", [])]
            raw = result.get("rows", [])
            if not isinstance(raw, list) or len(rows) + len(raw) > 2000:
                raise YouTubeError("SYNC_LIMIT")
            if len(raw) > REPORT_PAGE_SIZE:
                raise YouTubeError("INVALID_RESPONSE")
            if raw and (set(columns) != expected or len(columns) != len(expected)):
                raise YouTubeError("INVALID_RESPONSE")
            for values in raw:
                if not isinstance(values, list) or len(values) != len(columns):
                    raise YouTubeError("INVALID_RESPONSE")
                row = dict(zip(columns, values))
                if single_video:
                    row["video"] = video_ids[0]
                for metric in METRICS:
                    value = row[metric]
                    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                             or not math.isfinite(value) or (metric != "likes" and value < 0)):
                        raise YouTubeError("INVALID_RESPONSE")
                key = tuple(row.get(d) for d in dimensions.split(",")) if dimensions else ("aggregate",)
                if any(not isinstance(value, str) for value in key) or key in seen:
                    raise YouTubeError("INVALID_RESPONSE")
                seen.add(key)
                if "day" in row and not start <= date.fromisoformat(row["day"]) <= end:
                    raise YouTubeError("INVALID_RESPONSE")
                if "video" in row and video_ids and row["video"] not in video_ids:
                    raise YouTubeError("CHANNEL_MISMATCH")
                rows.append(row)
            if single_page or len(raw) < REPORT_PAGE_SIZE:
                return rows
            index += len(raw)
