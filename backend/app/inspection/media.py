"""Probe and decode output and corresponding source intervals with local FFmpeg."""

import hashlib
import re
import subprocess
from pathlib import Path
import numpy as np
from app.inspection.models import Check
from app.video.probe import probe_metadata

DURATION_TOLERANCE_SECONDS = 0.5
ANOMALY_MIN_SECONDS = 3.0
FREEZE_MIN_SECONDS = 10.0
OPENING_CORRELATION_MIN = 0.9


def file_hash(path):
    with Path(path).open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def run(command, *, timeout=300):
    return subprocess.run(command, check=True, capture_output=True, timeout=timeout)


def source_pieces(candidate):
    hook = max(0, (candidate.hook_scene_end or 0) - (candidate.hook_scene_start or 0))
    return ([(0, hook, candidate.hook_scene_start)] if hook else []) + [(hook, hook + candidate.duration, candidate.start)]


def anomalies(path, *, start=0, duration=None):
    filters = "scale=160:-2,blackdetect=d=3:pix_th=0.10:pic_th=0.98,freezedetect=n=-50dB:d=10"
    command = ["ffmpeg", "-hide_banner", "-nostdin", "-ss", str(start), "-i", str(path)]
    if duration is not None:
        command += ["-t", str(duration)]
    result = run(
        [*command, "-vf", filters, "-af", "silencedetect=n=-50dB:d=3", "-f", "null", "-"], timeout=max(120, (duration or 1800) * 2 + 60)
    )
    text = result.stderr.decode("utf-8", errors="replace")
    ranges = {}
    for kind, prefix in (("BLACK_INTERVAL", "black"), ("FREEZE_INTERVAL", "freeze"), ("SILENCE_INTERVAL", "silence")):
        starts = [float(v) for v in re.findall(prefix + r"_start[:=]\s*([\d.]+)", text)]
        ends = [float(v) for v in re.findall(prefix + r"_end[:=]\s*([\d.]+)", text)]
        ranges[kind] = [(s, next((e for e in ends if e >= s), duration or s)) for s in starts]
    return ranges


def unexpected_ranges(output, source, pieces):
    result = {}
    for code, intervals in output.items():
        unmatched = []
        for start, end in intervals:
            covered = 0.0
            for lo, hi, _origin in pieces:
                for a, b in source[pieces.index((lo, hi, _origin))].get(code, []):
                    covered += max(0, min(end, hi, lo + b) - max(start, lo, lo + a))
            # Decode thresholds can move a boundary by a few frames. Never excuse
            # a new output defect just because some unrelated source scene is static.
            if end - start - covered > DURATION_TOLERANCE_SECONDS:
                unmatched.append([start, end])
        result[code] = unmatched
    return result


def inspect_media(path, candidate, *, dimensions, source):
    try:
        meta = probe_metadata(path)
        digest = file_hash(path)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None, [Check(code="MEDIA_UNREADABLE", outcome="fail")]
    expected = sum(hi - lo for lo, hi, _ in source_pieces(candidate))
    checks = [
        Check(code="STREAM_MISSING", outcome="pass" if meta.width and meta.height and meta.has_audio else "fail"),
        Check(
            code="DURATION_MISMATCH",
            outcome="pass" if meta.duration is not None and abs(meta.duration - expected) <= DURATION_TOLERANCE_SECONDS else "fail",
            evidence={"expected": expected, "observed": meta.duration},
        ),
        Check(
            code="DIMENSIONS_INVALID",
            outcome="pass" if (meta.width, meta.height) == dimensions else "fail",
            evidence={"expected": dimensions, "observed": [meta.width, meta.height]},
        ),
        Check(
            code="AV_DURATION_MISMATCH",
            outcome="pass"
            if meta.audio_stream_duration is not None
            and meta.video_stream_duration is not None
            and abs(meta.audio_stream_duration - meta.video_stream_duration) <= DURATION_TOLERANCE_SECONDS
            else "fail",
            evidence={"video": meta.video_stream_duration, "audio": meta.audio_stream_duration},
        ),
    ]
    if any(c.outcome != "pass" for c in checks):
        return digest, checks
    try:
        output = anomalies(path, duration=meta.duration)
    except (OSError, ValueError, subprocess.SubprocessError):
        return digest, checks + [Check(code="MEDIA_UNREADABLE", outcome="fail")]
    try:
        pieces = source_pieces(candidate)
        original = [anomalies(source, start=origin, duration=hi - lo) for lo, hi, origin in pieces]
        for code, intervals in unexpected_ranges(output, original, pieces).items():
            checks.append(
                Check(
                    code=code,
                    outcome="fail" if intervals else "pass",
                    evidence={"unexpected": intervals, "detected": output[code], "source": [r[code] for r in original]},
                    second=intervals[0][0] if intervals else None,
                )
            )
    except (OSError, ValueError, subprocess.SubprocessError):
        checks.append(Check(code="SOURCE_SCAN_UNAVAILABLE", outcome="unknown"))
    return digest, checks


def audio_samples(path, start, duration):
    data = run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-ss",
            str(start),
            "-i",
            str(path),
            "-t",
            str(duration),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "8000",
            "-f",
            "f32le",
            "-",
        ],
        timeout=60,
    ).stdout
    return np.frombuffer(data, dtype="<f4").astype(np.float64)


def inspect_opening(path, candidate, source):
    evidence = []
    try:
        for lo, hi, origin in source_pieces(candidate):
            duration = min(3, hi - lo)
            a, b = audio_samples(path, lo, duration), audio_samples(source, origin, duration)
            size = min(len(a), len(b))
            if size < 800:
                return Check(code="OPENING_UNVERIFIED", outcome="unknown", second=lo)
            a, b = a[:size] - a[:size].mean(), b[:size] - b[:size].mean()
            norm = np.linalg.norm(a) * np.linalg.norm(b)
            score = float(np.dot(a, b) / norm) if norm > 1e-8 else (1.0 if np.max(np.abs(a)) < 1e-4 and np.max(np.abs(b)) < 1e-4 else 0.0)
            evidence.append({"outputStart": lo, "sourceStart": origin, "seconds": duration, "correlation": score})
        return Check(
            code="OPENING_MISMATCH",
            outcome="pass" if all(e["correlation"] >= OPENING_CORRELATION_MIN for e in evidence) else "fail",
            evidence={"pieces": evidence},
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return Check(code="OPENING_UNVERIFIED", outcome="unknown")
