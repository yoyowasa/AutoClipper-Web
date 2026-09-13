import json
from pathlib import Path

import pytest

from app.overlay_text import (
    fit_overlay_text,
    normalize_overlay_text,
    overlay_font_size_scale,
)


CASES_PATH = Path(__file__).parent / "fixtures" / "overlay_text_fit_cases.json"


@pytest.mark.parametrize(
    "case",
    json.loads(CASES_PATH.read_text(encoding="utf-8")),
    ids=lambda case: case["name"],
)
def test_overlay_fit_matches_shared_golden_cases(case: dict[str, object]) -> None:
    options = case["options"]
    assert isinstance(options, dict)
    result = fit_overlay_text(
        str(case["text"]),
        output_width=int(options["outputWidth"]),
        font_name=str(options["fontName"]),
        font_size=int(options["fontSize"]),
        margin_x=int(options["marginX"]),
        outline_width=int(options["outlineWidth"]),
        shadow=int(options["shadow"]),
        alignment=int(options["alignment"]),
        x_percent=float(options["xPercent"]),
        min_font_size=(
            int(options["minFontSize"])
            if "minFontSize" in options
            else None
        ),
    )
    expected = case["expected"]
    assert isinstance(expected, dict)
    assert list(result.lines) == expected["lines"]
    assert result.effective_font_size == expected["effectiveFontSize"]
    assert result.max_width_px == pytest.approx(expected["maxWidthPx"])
    assert result.fits is expected["fits"]
    assert result.overflow_reason == expected["overflowReason"]
    assert overlay_font_size_scale(str(options["fontName"])) == pytest.approx(
        options["fontSizeScale"]
    )
    assert "".join(result.lines) == normalize_overlay_text(
        str(case["text"])
    ).replace("\n", "")


def test_manual_break_is_preserved_while_font_size_shrinks() -> None:
    result = fit_overlay_text(
        "一行目はこの位置から動かさず固定する\n二行目も指定どおりの位置で表示する",
        output_width=1080,
        font_name="Noto Sans JP Black",
        font_size=112,
        margin_x=86,
        outline_width=5,
        shadow=2,
        alignment=5,
        x_percent=50,
    )

    assert result.lines == (
        "一行目はこの位置から動かさず固定する",
        "二行目も指定どおりの位置で表示する",
    )
    assert result.effective_font_size < 112
    assert result.fits is True
