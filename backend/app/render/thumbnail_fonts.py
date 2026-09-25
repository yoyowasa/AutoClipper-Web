import os
from pathlib import Path

from app.thumbnail_style import ThumbnailFontPreset

THUMBNAIL_FONT_FILES: dict[ThumbnailFontPreset, str] = {
    "noto_black": "NotoSansJP-Black.ttf",
    "heavy": "SourceHanSansJP-Heavy.otf",
    "mplus_extrabold": "MPLUS1-ExtraBold.ttf",
    "mplus_rounded_extrabold": "MPLUSRounded1c-ExtraBold.ttf",
    "chikara": "851CHIKARA-DZUYOKU-kanaA.ttf",
    "chikara_yowaku": "851CHIKARA-YOWAKU.ttf",
    "keifont": "keifont.ttf",
    "mushin": "mushin.otf",
    "ankoku_zonji": "Zomzi.ttf",
    "tanuki_magic": "TanukiMagic.ttf",
    "genei_kiwami_go": "GenEiKiwamiGo.ttf",
    "genei_mono_go": "GenEiMonoGothic-Bold.ttf",
    "genei_antique": "GenEiAntiqueNv6-M.ttf",
    "gochi_kakutto": "851Gkktt_005.ttf",
    "nikkyou_sans": "NikkyouSans-mLKax.ttf",
    "dela_gothic": "DelaGothicOne-Regular.ttf",
    "corporate_logo": "Corporate-Logo-Bold-ver3.otf",
}


def thumbnail_font_path(preset: ThumbnailFontPreset, default_font: Path) -> Path:
    if preset == "noto_black":
        return default_font
    filename = THUMBNAIL_FONT_FILES[preset]
    # Match the existing ASS font mount, then the local checkout.
    roots = [Path(os.environ.get("ASS_FONTS_DIR", "/app/fonts")), Path(__file__).resolve().parents[3] / "frontend/public/fonts"]
    for root in roots:
        path = root / filename
        if path.is_file():
            return path
    raise FileNotFoundError(f"サムネイルの書体が見つかりません: {preset}")
