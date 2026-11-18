"""Draws the plugin icon: three gauge lines, the top one in the plan gradient.

Run with Pillow installed: python3 tools/make_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
SCALE = 4                      # drawn larger, then reduced: smooth edges
BACKGROUND = (24, 24, 28)
QUIET = (86, 86, 94)
# The violet of the plan signature, as a smooth ramp in one hue from light to
# deep. The terminal's 256 colours are too coarse for a large surface.
STOPS = [(0.0, (222, 216, 255)), (0.55, (176, 140, 255)), (1.0, (128, 92, 246))]


def ramp(t):
    t = max(0.0, min(1.0, t))
    for (a, ca), (b, cb) in zip(STOPS, STOPS[1:]):
        if t <= b:
            u = (t - a) / (b - a)
            return tuple(round(x + (y - x) * u) for x, y in zip(ca, cb))
    return STOPS[-1][1]


def main():
    s = SIZE * SCALE
    img = Image.new("RGB", (s, s), BACKGROUND)
    left = int(s * 0.22)
    height = int(s * 0.055)
    rows = ((0.36, 0.56, True), (0.50, 0.38, False), (0.64, 0.22, False))
    for y_share, length, colored in rows:
        top = int(s * y_share) - height // 2
        width = int(s * length)
        if colored:
            fill = Image.new("RGB", (width, height))
            px = ImageDraw.Draw(fill)
            for x in range(width):
                px.line([(x, 0), (x, height)], fill=ramp(x / (width - 1)))
        else:
            fill = Image.new("RGB", (width, height), QUIET)
        mask = Image.new("L", (width, height), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, width - 1, height - 1],
                                               radius=height // 2, fill=255)
        img.paste(fill, (left, top), mask)
    img = img.resize((SIZE, SIZE), Image.LANCZOS)
    target = Path(__file__).resolve().parent.parent / ".claude-plugin" / "icon.png"
    img.save(target, optimize=True)
    print(target)


if __name__ == "__main__":
    main()
