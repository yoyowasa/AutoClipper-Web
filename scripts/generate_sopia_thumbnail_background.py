"""Generate the copyright-free geometric background for the Sopia thumbnail."""

from math import cos, pi, sin
from pathlib import Path
from random import Random

from PIL import Image, ImageDraw, ImageFilter


OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "backend/app/assets/thumbnail_templates/sopia_normal_v1/background.png"
)
WIDTH, HEIGHT = 1280, 720


def main() -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT))
    pixels = image.load()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            glow = max(0.0, 1.0 - ((x - 1050) ** 2 / 800000 + (y - 270) ** 2 / 300000))
            bottom = y / HEIGHT
            pixels[x, y] = (
                round(6 + 17 * glow + 11 * bottom),
                round(17 + 25 * glow + 9 * bottom),
                round(42 + 43 * glow + 23 * bottom),
            )

    overlay = Image.new("RGBA", image.size)
    draw = ImageDraw.Draw(overlay, "RGBA")
    # Fine engineering grid stays dim enough for the headline to remain legible.
    for x in range(0, WIDTH, 48):
        draw.line((x, 0, x, HEIGHT), fill=(91, 147, 190, 15), width=1)
    for y in range(0, HEIGHT, 48):
        draw.line((0, y, WIDTH, y), fill=(91, 147, 190, 15), width=1)

    # An orbital instrument sweeps behind the portrait rather than through the text.
    for radius, color, stroke in [
        (440, (82, 208, 244, 42), 3),
        (526, (190, 149, 246, 35), 2),
        (618, (82, 208, 244, 24), 2),
    ]:
        cx, cy = 1065, 412
        draw.arc((cx - radius, cy - radius, cx + radius, cy + radius), 76, 292, fill=color, width=stroke)
    for angle in range(-80, 180, 32):
        radians = angle * pi / 180
        cx, cy, radius = 1065, 412, 526
        x, y = cx + radius * cos(radians), cy + radius * sin(radians)
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(169, 227, 255, 128))

    rng = Random(24)
    for _ in range(125):
        x, y = rng.randrange(32, WIDTH - 32), rng.randrange(50, HEIGHT - 50)
        r = rng.choice((1, 1, 1, 2))
        alpha = rng.randrange(30, 95)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(188, 220, 255, alpha))

    # Top and bottom rails echo Raden's framed composition, in laboratory colors.
    draw.rounded_rectangle((35, 31, 1245, 689), radius=15, outline=(99, 213, 243, 120), width=2)
    draw.line((55, 176, 464, 176), fill=(119, 218, 243, 138), width=3)
    draw.line((55, 184, 320, 184), fill=(218, 173, 247, 90), width=2)
    draw.line((55, 657, 422, 657), fill=(119, 218, 243, 130), width=3)
    draw.line((55, 664, 222, 664), fill=(218, 173, 247, 90), width=2)

    # Small molecule and star details occupy margins only.
    for cx, cy, scale in ((91, 217, 1.0), (1178, 104, 0.8), (1172, 621, 1.2)):
        points = [(cx + 22 * scale * cos(i * pi / 3), cy + 22 * scale * sin(i * pi / 3)) for i in range(6)]
        draw.line(points + [points[0]], fill=(139, 220, 248, 105), width=2)
        draw.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=(222, 188, 250, 135))
    for cx, cy in ((535, 71), (528, 628), (1210, 399)):
        draw.line((cx - 10, cy, cx + 10, cy), fill=(255, 221, 165, 170), width=2)
        draw.line((cx, cy - 10, cx, cy + 10), fill=(255, 221, 165, 170), width=2)

    image = Image.alpha_composite(image.convert("RGBA"), overlay.filter(ImageFilter.GaussianBlur(0.35)))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(OUTPUT, optimize=True)


if __name__ == "__main__":
    main()
