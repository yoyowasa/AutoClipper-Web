"""Compare decoded MP4 pixels to fresh glyph references from confirmed cues.

No export ASS/metadata is trusted as proof of what the MP4 actually displays.
The shared timing/font code defines the expectation, not the observation.
"""

from contextlib import closing, contextmanager
from bisect import bisect_left
from hashlib import sha256
from pathlib import Path
import re
import subprocess
import threading
import time
import av
import numpy as np
from app.inspection.models import Check
from app.render.filters import ass_filter
from app.render.subtitles_ass import build_ass_document

SAMPLE_FPS = 5
PIXEL_TOLERANCE = 60
GLYPH_MATCH_MIN = 0.72
LINGER_GRACE_SECONDS = 0.25
SAMPLE_WIDTH = 480
ASS_CLOCK_PRECISION_SECONDS = 0.001


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


class _PipeReader:
    """Expose a forward-only read, including on Windows's non-seekable pipe."""

    def __init__(self, pipe):
        self.pipe = pipe

    def read(self, size):
        return self.pipe.read(size)


@contextmanager
def frames(command, timeout):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    timer = threading.Timer(timeout, process.kill)
    timer.daemon = True
    timer.start()

    def stream():
        # NUT retains the selected decoded frame's PTS. Raw rasters and an
        # index/fps clock lose that timestamp at subtitle transitions.
        with av.open(_PipeReader(process.stdout), format="nut") as container:
            for frame in container.decode(video=0):
                if frame.pts is None or frame.time_base is None:
                    raise ValueError("raster timestamp missing")
                yield float(frame.pts * frame.time_base), frame.to_ndarray(format="rgba")
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
    # Split after selecting real frames, before generating the fresh reference.
    # Both panels therefore represent exactly the same decoded PTS, even for
    # fractional/VFR input. The reference uses only confirmed ASS on transparent
    # black; none of the MP4's existing text pixels enter the glyph reference.
    graph = (
        f"[0:v]select='isnan(prev_selected_t)+gte(t-prev_selected_t,{1 / SAMPLE_FPS - 1e-6})',split[actual][reference];"
        f"[actual]scale={width}:{height},format=rgba[observed];"
        "[reference]format=rgba,colorchannelmixer=rr=0:gg=0:bb=0:aa=0,"
        + ass_filter(reference_path)
        + f":alpha=1,scale={width}:{height}[glyph];[observed][glyph]hstack=inputs=2[paired]"
    )
    command = [
        *prefix,
        "-i",
        str(path),
        "-t",
        str(duration),
        "-filter_complex",
        graph,
        "-map",
        "[paired]",
        "-an",
        "-fps_mode",
        "passthrough",
        "-c:v",
        "rawvideo",
        "-f",
        "nut",
        "-pix_fmt",
        "rgba",
        "-",
    ]
    bad, clipped, collision, lingering = [], [], [], []
    covered = set()
    transitions = sorted({t for start, end, _ in events for t in (start, end)})
    transition_samples = []
    visible_frames, decoded_frames = 0, 0
    previous, last_visible = None, 0
    last_sample = 0.0
    interior_samples = 0
    deadline = time.monotonic() + max(120, duration * 2 + 30)

    def sampled_frames():
        nonlocal interior_samples

        def remaining():
            seconds = deadline - time.monotonic()
            if seconds <= 0:
                raise ValueError("subtitle sampling deadline exceeded")
            return seconds

        with frames(command, remaining()) as paired:
            yield from paired
        # A short cue can fall between regular samples or only at a boundary.
        # Seek once to its interior, retaining original PTS for both panels.
        # Evidence is still decoded MP4 pixels, not an assumption that it exists.
        for index, (start, end, _text) in enumerate(events):
            if index in covered:
                continue
            at = command.index("-i")
            extra = command[:at] + ["-copyts", "-ss", str((start + end) / 2)] + command[at:]
            extra[-1:-1] = ["-frames:v", "1"]
            interior_samples += 1
            with frames(extra, remaining()) as paired:
                yield from paired

    top, bottom = (round(v * height / layout.height) for v in banners)
    try:
        with closing(sampled_frames()) as paired:
            for second, raster in paired:
                last_sample = max(last_sample, second)
                observed, glyph = raster[:, :width, :3], raster[:, width:, :]
                decoded_frames += 1
                at = bisect_left(transitions, second)
                # Libass consumes integer milliseconds. At a cue boundary,
                # differing render/MP4 time bases can round to either side.
                # Verify interior samples instead; a cue with no such sample
                # remains unknown, never silently passes.
                transition = any(abs(second - t) <= ASS_CLOCK_PRECISION_SECONDS for t in transitions[max(0, at - 1):at + 1])
                if transition:
                    transition_samples.append(second)
                alpha = glyph[:, :, 3]
                if np.count_nonzero(alpha >= 240) < 8:
                    if not transition and previous is not None and second - last_visible > LINGER_GRACE_SECONDS:
                        score = glyph_score(observed, previous)
                        if score is not None and score >= 0.95 and len(lingering) < 20:
                            lingering.append(second)
                    continue
                visible_frames += 1
                previous, last_visible = glyph, second
                if np.any(alpha[:2] > 32) or np.any(alpha[-2:] > 32) or np.any(alpha[:, :2] > 32) or np.any(alpha[:, -2:] > 32):
                    if len(clipped) < 20:
                        clipped.append(second)
                if (top and np.any(alpha[:top] > 32)) or (bottom and np.any(alpha[height - bottom :] > 32)):
                    if len(collision) < 20:
                        collision.append(second)
                if transition:
                    continue
                covered.update(i for i, (start, end, _text) in enumerate(events) if start < second < end)
                score = glyph_score(observed, glyph)
                if (score is None or score < GLYPH_MATCH_MIN) and len(bad) < 20:
                    bad.append({"second": second, "score": score})
        if last_sample < max(e[1] for e in events) - 1 / SAMPLE_FPS:
            raise ValueError("raster stream ended before final cue")
    except (OSError, ValueError, av.FFmpegError, subprocess.SubprocessError):
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
                    "transitionSamplesSkipped": len(transition_samples),
                    "transitionPrecisionSeconds": ASS_CLOCK_PRECISION_SECONDS,
                    "interiorSamples": interior_samples,
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
