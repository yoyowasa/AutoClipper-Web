"""Compare decoded MP4 pixels to fresh glyph references from confirmed cues.

No export ASS/metadata is trusted as proof of what the MP4 actually displays.
The shared timing/font code defines the expectation, not the observation.
"""

from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import re
import subprocess
import threading
import numpy as np
from app.inspection.models import Check
from app.render.filters import ass_filter
from app.render.subtitles_ass import build_ass_document

SAMPLE_FPS = 5
PIXEL_TOLERANCE = 60
GLYPH_MATCH_MIN = 0.72
LINGER_GRACE_SECONDS = 0.25
SAMPLE_WIDTH = 480


def ass_second(value):
    h, m, s = value.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def reference_document(candidate, segments, layout):
    text = build_ass_document(candidate, segments, layout=layout, top_title="")
    lines, events = [], set()
    for line in text.splitlines():
        if line.startswith("Dialogue:"):
            fields = line.split(",", 9)
            if not fields[3].startswith("Subtitle"):
                continue
            events.add((ass_second(fields[1]), ass_second(fields[2]), re.sub(r"\{[^}]*\}", "", fields[9])))
        lines.append(line)
    return "\n".join(lines) + "\n", sorted(events)


@contextmanager
def frames(command, width, height, channels, timeout):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    timer = threading.Timer(timeout, process.kill)
    timer.daemon = True
    timer.start()

    def stream():
        size = width * height * channels
        while True:
            data = process.stdout.read(size)
            if not data:
                break
            if len(data) != size:
                raise ValueError("incomplete raster frame")
            yield np.frombuffer(data, dtype=np.uint8).reshape(height, width, channels)
        if process.wait(timeout=10) != 0:
            raise ValueError("raster decoding failed")

    try:
        yield stream()
    finally:
        timer.cancel()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        process.stdout.close()


def glyph_score(actual, expected):
    mask = expected[:, :, 3] >= 240
    if mask.sum() < 8:
        return None
    colors = expected[:, :, :3][mask]
    observed = actual[mask]
    bins = (colors // 64).astype(np.int16)
    keys = bins[:, 0] * 16 + bins[:, 1] * 4 + bins[:, 2]
    matched = np.max(np.abs(observed.astype(np.int16) - colors.astype(np.int16)), axis=1) <= PIXEL_TOLERANCE
    groups = [(keys == k) for k in np.unique(keys)]
    scores = [float(matched[g].mean()) for g in groups if g.sum() >= max(8, len(colors) * 0.03)]
    return min(scores) if scores else None


def inspect_subtitles(path, candidate, segments, *, layout, directory, banners=(0, 0), enabled=True):
    if not enabled:
        return [Check(code="SUBTITLE_PIXELS_MISMATCH", outcome="pass", evidence={"disabledBySettings": True})]
    reference, events = reference_document(candidate, segments, layout)
    if not events:
        return [Check(code="SUBTITLE_PIXELS_MISMATCH", outcome="pass", evidence={"expectedCues": 0})]
    overlaps = [[a[0], b[0]] for a, b in zip(events, events[1:]) if b[0] < a[1] - 0.02 and a[2] != b[2]]
    checks = [
        Check(
            code="SUBTITLE_OVERLAP",
            outcome="fail" if overlaps else "pass",
            evidence={"intervals": overlaps, "expectedAssSha256": sha256(reference.encode()).hexdigest()},
        )
    ]
    reference_path = Path(directory) / "expected-subtitles.ass"
    reference_path.write_text(reference, encoding="utf-8")
    width = min(SAMPLE_WIDTH, layout.width)
    height = max(2, round(layout.height * width / layout.width / 2) * 2)
    duration = max(e[1] for e in events) + 0.4
    prefix = ["ffmpeg", "-v", "error", "-nostdin"]
    actual_cmd = [
        *prefix,
        "-i",
        str(path),
        "-t",
        str(duration),
        "-vf",
        f"fps={SAMPLE_FPS},scale={width}:{height}",
        "-an",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]
    expected_cmd = [
        *prefix,
        "-f",
        "lavfi",
        "-i",
        f"color=c=black@0:s={layout.width}x{layout.height}:r={SAMPLE_FPS}:d={duration},format=rgba",
        "-vf",
        ass_filter(reference_path) + f":alpha=1,scale={width}:{height}",
        "-an",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "-",
    ]
    bad, clipped, collision, lingering = [], [], [], []
    covered = set()
    visible_frames, decoded_frames = 0, 0
    previous, last_visible = None, 0
    top, bottom = (round(v * height / layout.height) for v in banners)
    try:
        with frames(actual_cmd, width, height, 3, max(120, duration * 2 + 30)) as actual:
            with frames(expected_cmd, width, height, 4, max(120, duration * 2 + 30)) as expected:
                from itertools import zip_longest

                for index, pair in enumerate(zip_longest(actual, expected)):
                    observed, glyph = pair
                    if observed is None or glyph is None:
                        # The last reference frame can be one frame longer due to fps rounding.
                        if index / SAMPLE_FPS < max(e[1] for e in events) - 0.2:
                            raise ValueError("raster stream ended before final cue")
                        break
                    decoded_frames += 1
                    second = index / SAMPLE_FPS
                    alpha = glyph[:, :, 3]
                    if np.count_nonzero(alpha >= 240) < 8:
                        if previous is not None and second - last_visible > LINGER_GRACE_SECONDS:
                            score = glyph_score(observed, previous)
                            if score is not None and score >= 0.95 and len(lingering) < 20:
                                lingering.append(second)
                        continue
                    visible_frames += 1
                    previous, last_visible = glyph, second
                    covered.update(i for i, (start, end, _text) in enumerate(events) if start - 0.1 <= second <= end + 0.1)
                    if np.any(alpha[:2] > 32) or np.any(alpha[-2:] > 32) or np.any(alpha[:, :2] > 32) or np.any(alpha[:, -2:] > 32):
                        if len(clipped) < 20:
                            clipped.append(second)
                    if (top and np.any(alpha[:top] > 32)) or (bottom and np.any(alpha[height - bottom :] > 32)):
                        if len(collision) < 20:
                            collision.append(second)
                    score = glyph_score(observed, glyph)
                    if (score is None or score < GLYPH_MATCH_MIN) and len(bad) < 20:
                        bad.append({"second": second, "score": score})
    except (OSError, ValueError, subprocess.SubprocessError):
        return checks + [Check(code="SUBTITLE_DECODE_FAILED", outcome="unknown")]
    for code, values in (
        ("SUBTITLE_OUT_OF_FRAME", clipped),
        ("SUBTITLE_BANNER_COLLISION", collision),
        ("SUBTITLE_LINGERS", lingering),
        ("SUBTITLE_PIXELS_MISMATCH", bad),
    ):
        checks.append(
            Check(
                code=code,
                outcome="fail" if values else "pass",
                evidence={
                    "samples": values,
                    "fps": SAMPLE_FPS,
                    "decodedFrames": decoded_frames,
                    "visibleFrames": visible_frames,
                    "matchThreshold": GLYPH_MATCH_MIN,
                },
                second=(values[0]["second"] if isinstance(values[0], dict) else values[0]) if values else None,
            )
        )
    if not visible_frames:
        checks.append(Check(code="SUBTITLE_REFERENCE_EMPTY", outcome="fail"))
    elif len(covered) < len(events):
        checks.append(
            Check(code="SUBTITLE_SAMPLE_UNAVAILABLE", outcome="unknown", evidence={"missingCueCount": len(events) - len(covered)})
        )
    return checks
