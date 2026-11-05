"""Shared pixel geometry for overlay validation and bounded repair."""
from app.overlay_text import fit_overlay_text, overlay_text_width_units, overlay_font_size_scale
from pydantic import BaseModel, Field


class OverlayLayoutNotice(BaseModel):
    role: str
    start: float
    end: float
    text: str
    failed: bool = False
    boundary: str
    overflow_px: float = Field(alias="overflowPx")
    font_size_before: int = Field(alias="fontSizeBefore")
    font_size_after: int = Field(alias="fontSizeAfter")
    shift_px: float = Field(alias="shiftPx")


def _text_vertical_bounds(
    *,
    y_percent: float,
    alignment: int,
    line_count: int,
    font_size: int,
    outline_width: int,
    shadow: int,
    output_height: int,
) -> tuple[float, float]:
    visual_height = max(1, line_count) * font_size * 1.20 + 2 * (
        outline_width + shadow
    )
    anchor_y = output_height * min(100.0, max(0.0, y_percent)) / 100.0
    row = (min(9, max(1, alignment)) - 1) // 3
    if row == 0:
        return anchor_y - visual_height, anchor_y
    if row == 2:
        return anchor_y, anchor_y + visual_height
    return anchor_y - visual_height / 2, anchor_y + visual_height / 2



def measure_overlay(row, *, width, height, style=None):
    style = style or row["style"]
    fit = fit_overlay_text(row["text"], output_width=width, font_name=style.font_name, font_size=style.font_size,
        margin_x=style.margin_x, outline_width=style.outline_width + style.outer_outline_width,
        shadow=style.shadow, alignment=style.alignment, x_percent=style.x_percent, max_lines=row["max_lines"])
    low, high = _text_vertical_bounds(y_percent=style.y_percent, alignment=style.alignment,
        line_count=len(fit.lines), font_size=fit.effective_font_size,
        outline_width=style.outline_width + style.outer_outline_width, shadow=style.shadow, output_height=height)
    overflow = max(0., row["safe_top"] - low, high - row["safe_bottom"])
    boundary = "画面外"
    if low < row["safe_top"] and row["safe_top"] > 0:
        boundary = "上の帯"
    elif high > row["safe_bottom"] and row["safe_bottom"] < height:
        boundary = "下の帯"
    if not fit.fits:
        # Width units are the same deterministic estimate used by fit_overlay_text.
        overflow = max(overflow, max((overlay_text_width_units(line) * fit.effective_font_size
                                     * overlay_font_size_scale(style.font_name) - fit.max_width_px
                                     for line in fit.lines), default=0.))
        boundary = "画面外（横幅）"
    return {"fitsWidth": fit.fits, "effectiveFontSize": fit.effective_font_size, "lineCount": len(fit.lines),
        "verticalBounds": [round(low, 2), round(high, 2)], "safeBounds": [row["safe_top"], row["safe_bottom"]],
        "overflowPx": round(overflow, 2), "boundary": boundary,
        "fits": fit.fits and low >= row["safe_top"] and high <= row["safe_bottom"]}
