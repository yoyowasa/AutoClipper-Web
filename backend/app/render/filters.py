import os
from pathlib import Path


def ffmpeg_filter_path(path: str | Path) -> str:
    value = str(path).replace("\\", "/")
    value = value.replace(":", "\\:")
    value = value.replace("'", "\\'")
    return value


def ass_filter(subtitle_path: str | Path, fonts_dir: str | Path | None = None) -> str:
    configured_fonts_dir = fonts_dir if fonts_dir is not None else os.getenv("ASS_FONTS_DIR")
    value = f"ass='{ffmpeg_filter_path(subtitle_path)}'"
    if configured_fonts_dir:
        value += f":fontsdir='{ffmpeg_filter_path(configured_fonts_dir)}'"
    return value


def loudnorm_filter() -> str:
    return "loudnorm=I=-16:TP=-1.5:LRA=11"
