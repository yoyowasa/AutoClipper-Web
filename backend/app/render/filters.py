from pathlib import Path


def ffmpeg_filter_path(path: str | Path) -> str:
    value = str(path).replace("\\", "/")
    value = value.replace(":", "\\:")
    value = value.replace("'", "\\'")
    return value


def ass_filter(subtitle_path: str | Path) -> str:
    return f"ass='{ffmpeg_filter_path(subtitle_path)}'"


def loudnorm_filter() -> str:
    return "loudnorm=I=-16:TP=-1.5:LRA=11"
