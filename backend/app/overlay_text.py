import math
from dataclasses import dataclass


OVERLAY_MAX_LINES = 2
OVERLAY_HORIZONTAL_SAFE_RATIO = 0.05
OVERLAY_MIN_FONT_SIZE_RATIO = 0.55
OVERLAY_MIN_FONT_SIZE_PX = 36

_PUNCTUATION_BREAKS = frozenset("。、！？!?")
_SOFT_JA_BOUNDARIES = frozenset("でにはをがともやへ")
_FONT_SIZE_SCALES = {
    "851CHIKARA-YOWAKU": 1.0,
    "Keifont": 1024 / 1134,
    "Mushin": 1.0,
    "AnkokuZombic": 1.0,
    "GN-KMBFont-UB-NewstyleKanaB": 1024 / 1230,
    "Tanuki Permanent Marker": 1.0,
    "Noto Serif CJK JP": 1000 / 1437,
    "Rounded Mplus 1c ExtraBold": 1000 / 1395,
    "Corporate-Logo-Bold-ver3": 1000 / 1400,
    "851CHIKARA-DZUYOKU-KANA-A": 1.0,
}
_DEFAULT_FONT_SIZE_SCALE = 1000 / 1448


@dataclass(frozen=True)
class OverlayTextFit:
    lines: tuple[str, ...]
    effective_font_size: int
    max_width_px: float
    fits: bool
    overflow_reason: str | None = None

    @property
    def ass_text(self) -> str:
        return "\\N".join(self.lines)


def normalize_overlay_text(text: str, *, max_lines: int = OVERLAY_MAX_LINES) -> str:
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


def overlay_character_width(character: str) -> float:
    """Return a deterministic display-width weight shared with the browser preview."""
    if not character:
        return 0.0
    code_point = ord(character)
    if (
        0x0300 <= code_point <= 0x036F
        or 0x1AB0 <= code_point <= 0x1AFF
        or 0x1DC0 <= code_point <= 0x1DFF
        or 0x20D0 <= code_point <= 0x20FF
        or 0xFE00 <= code_point <= 0xFE0F
        or 0xFE20 <= code_point <= 0xFE2F
        or code_point == 0x200D
    ):
        return 0.0
    if character.isspace():
        return 0.5
    if code_point <= 0x7F or 0xFF61 <= code_point <= 0xFF9F:
        return 0.55
    if (
        0x1100 <= code_point <= 0x115F
        or 0x2329 <= code_point <= 0x232A
        or 0x2E80 <= code_point <= 0xA4CF
        or 0xAC00 <= code_point <= 0xD7A3
        or 0xF900 <= code_point <= 0xFAFF
        or 0xFE10 <= code_point <= 0xFE19
        or 0xFE30 <= code_point <= 0xFE6F
        or 0xFF01 <= code_point <= 0xFF60
        or 0xFFE0 <= code_point <= 0xFFE6
        or 0x1F000 <= code_point <= 0x1FAFF
        or 0x20000 <= code_point <= 0x3FFFD
    ):
        return 1.0
    return 0.65


def overlay_text_width_units(text: str) -> float:
    return sum(overlay_character_width(character) for character in text)


def overlay_font_size_scale(font_name: str | None) -> float:
    return _FONT_SIZE_SCALES.get((font_name or "").strip(), _DEFAULT_FONT_SIZE_SCALE)


def balanced_overlay_lines(text: str, *, max_lines: int = OVERLAY_MAX_LINES) -> tuple[str, ...]:
    manual_lines = tuple(text.split("\n"))
    if len(manual_lines) > 1 or max_lines <= 1:
        return manual_lines[: max(1, max_lines)]
    if len(text) <= 1:
        return (text,)

    characters = list(text)
    total_width = overlay_text_width_units(text)
    best_index = 1
    best_score = math.inf
    for index in range(1, len(characters)):
        left = "".join(characters[:index])
        left_width = overlay_text_width_units(left)
        right_width = total_width - left_width
        previous = characters[index - 1]
        following = characters[index]
        if previous in _PUNCTUATION_BREAKS:
            boundary_penalty = 0.0
        elif previous.isspace() or following.isspace():
            boundary_penalty = total_width * 0.02
        elif previous in _SOFT_JA_BOUNDARIES:
            boundary_penalty = total_width * 0.04
        else:
            boundary_penalty = total_width * 0.12
        score = max(left_width, right_width) + abs(left_width - right_width) * 0.2 + boundary_penalty
        if score < best_score:
            best_index = index
            best_score = score
    return ("".join(characters[:best_index]), "".join(characters[best_index:]))


def _overlay_max_width(
    *,
    output_width: int,
    margin_x: int,
    outline_width: int,
    shadow: int,
    alignment: int,
    x_percent: float,
) -> float:
    safe_margin = max(float(margin_x), output_width * OVERLAY_HORIZONTAL_SAFE_RATIO)
    left_edge = safe_margin
    right_edge = output_width - safe_margin
    anchor_x = output_width * min(100.0, max(0.0, x_percent)) / 100.0
    column = (min(9, max(1, int(alignment))) - 1) % 3
    if column == 0:
        available = right_edge - anchor_x
    elif column == 2:
        available = anchor_x - left_edge
    else:
        available = 2 * min(anchor_x - left_edge, right_edge - anchor_x)
    edge_effect = 2 * max(0, outline_width + shadow)
    return max(1.0, available - edge_effect)


def fit_overlay_text(
    text: str,
    *,
    output_width: int,
    font_name: str,
    font_size: int,
    margin_x: int,
    outline_width: int,
    shadow: int,
    alignment: int,
    x_percent: float,
    max_lines: int = OVERLAY_MAX_LINES,
    min_font_size: int | None = None,
) -> OverlayTextFit:
    clean_text = normalize_overlay_text(text, max_lines=max_lines)
    requested_font_size = max(1, int(font_size))
    maximum_width = _overlay_max_width(
        output_width=max(1, int(output_width)),
        margin_x=max(0, int(margin_x)),
        outline_width=max(0, int(outline_width)),
        shadow=max(0, int(shadow)),
        alignment=alignment,
        x_percent=x_percent,
    )
    if not clean_text:
        return OverlayTextFit((), requested_font_size, maximum_width, True)

    scale = overlay_font_size_scale(font_name)
    one_line_width = overlay_text_width_units(clean_text) * requested_font_size * scale
    if "\n" not in clean_text and one_line_width <= maximum_width:
        lines = (clean_text,)
    else:
        lines = balanced_overlay_lines(clean_text, max_lines=max_lines)

    widest_line_units = max(overlay_text_width_units(line) for line in lines)
    fitted_font_size = (
        requested_font_size
        if widest_line_units <= 0
        else min(requested_font_size, math.floor(maximum_width / (widest_line_units * scale)))
    )
    default_minimum = max(
        OVERLAY_MIN_FONT_SIZE_PX,
        math.floor(requested_font_size * OVERLAY_MIN_FONT_SIZE_RATIO + 0.5),
    )
    resolved_minimum = min(
        requested_font_size,
        max(1, int(min_font_size if min_font_size is not None else default_minimum)),
    )
    fits = fitted_font_size >= resolved_minimum
    effective_font_size = max(resolved_minimum, fitted_font_size)
    return OverlayTextFit(
        lines=lines,
        effective_font_size=effective_font_size,
        max_width_px=maximum_width,
        fits=fits,
        overflow_reason=None if fits else "min_font_size",
    )
