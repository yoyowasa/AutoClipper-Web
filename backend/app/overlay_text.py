def normalize_overlay_text(text: str, *, max_lines: int = 2) -> str:
    """Keep manual title/hook line breaks while bounding rendered lines."""
    normalized_newlines = (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\u2028", "\n")
        .replace("\u2029", "\n")
        .replace("\\N", "\n")
    )
    lines = [
        " ".join(line.split()).strip()
        for line in normalized_newlines.split("\n")
    ]
    lines = [line for line in lines if line]
    if not lines:
        return ""

    line_limit = max(1, max_lines)
    if len(lines) > line_limit:
        lines = [*lines[: line_limit - 1], " ".join(lines[line_limit - 1 :])]
    return "\n".join(lines)
