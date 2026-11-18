"""Renders the README images from the code itself, so they never go stale.

    python3 tools/render_images.py

Needs Pillow and a monospaced font (DejaVu Sans Mono by default, or set
CCSL_FONT and CCSL_FONT_BOLD).
"""

import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ccsl import config, draw, i18n, themes  # noqa: E402
from ccsl.model import Gauge, Status  # noqa: E402

OUT = ROOT / "docs" / "images"
SCALE = 2
FONT_SIZE = 15
PAD = 28
LINE_GAP = 9
FONT = os.environ.get("CCSL_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
BOLD = os.environ.get("CCSL_FONT_BOLD",
                      "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf")

VARIANTS = {
    "dark": {"bg": (22, 22, 26), "fg": (222, 222, 228), "light": False},
    "light": {"bg": (250, 250, 250), "fg": (36, 36, 40), "light": True},
}
SGR = re.compile(r"\x1b\[([0-9;]*)m")


def xterm(index):
    if index < 16:
        basic = [(0, 0, 0), (205, 49, 49), (13, 188, 121), (229, 229, 16), (36, 114, 200),
                 (188, 63, 188), (17, 168, 205), (229, 229, 229)]
        return basic[index % 8]
    if index >= 232:
        v = 8 + (index - 232) * 10
        return v, v, v
    i = index - 16
    steps = (0, 95, 135, 175, 215, 255)
    return steps[i // 36], steps[(i // 6) % 6], steps[i % 6]


def spans(text, fg):
    """(characters, colour, bold) runs of an ANSI-coloured line."""
    color, bold, out, pos = fg, False, [], 0
    for match in SGR.finditer(text):
        if match.start() > pos:
            out.append((text[pos:match.start()], color, bold))
        codes = [int(c) for c in match.group(1).split(";") if c] or [0]
        i = 0
        while i < len(codes):
            if codes[i] == 0:
                color, bold = fg, False
            elif codes[i] == 1:
                bold = True
            elif codes[i] == 38 and i + 2 < len(codes) and codes[i + 1] == 5:
                color = xterm(codes[i + 2])
                i += 2
            i += 1
        pos = match.end()
    if pos < len(text):
        out.append((text[pos:], color, bold))
    return out


def render(blocks, name, width_chars):
    """blocks: list of lists of ANSI lines; an empty list draws a gap."""
    regular = ImageFont.truetype(FONT, FONT_SIZE * SCALE)
    strong = ImageFont.truetype(BOLD, FONT_SIZE * SCALE)
    char_w = regular.getlength("M")
    line_h = (FONT_SIZE + LINE_GAP) * SCALE
    for variant, look in VARIANTS.items():
        lines = [line for block in blocks(look["light"]) for line in block]
        used = max(draw.visible_len(line) for line in lines)
        w = int(PAD * 2 * SCALE + char_w * min(width_chars, used))
        h = int(PAD * 2 * SCALE + line_h * len(lines) - LINE_GAP * SCALE)
        img = Image.new("RGB", (w, h), look["bg"])
        pen = ImageDraw.Draw(img)
        y = PAD * SCALE
        for line in lines:
            x = PAD * SCALE
            for chars, color, bold in spans(line, look["fg"]):
                for ch in chars:
                    pen.text((x, y), ch, font=strong if bold else regular,
                             fill=color if color != (None,) else look["fg"])
                    x += char_w
            y += line_h
        OUT.mkdir(parents=True, exist_ok=True)
        target = OUT / "{}-{}.png".format(name, variant)
        img.save(target, optimize=True)
        print(target)


def status(plan, tier, model, effort, week, scoped, five, ctx, cost, project=None,
           project_usd=None, lang="en"):
    now = datetime.now(timezone.utc).astimezone().replace(hour=21, minute=0)
    reset = now + timedelta(days=2, hours=11)
    return Status(week=Gauge("week", i18n.t("week", lang), week, reset),
                  scoped=Gauge("model_week", "Fable", scoped, reset),
                  five_hour=Gauge("five_hour", "5h", five), context=Gauge(
                      "context", i18n.t("context", lang), ctx),
                  plan=plan, plan_tier=tier, model=model, effort=effort,
                  directory="~/code/aurora", branch="main", cost_usd=cost,
                  project=project, project_usd=project_usd)


def cfg_for(theme, light, project=True, lang="en"):
    cfg = config.load(path=Path(os.devnull), env={})
    cfg.update(theme=theme, _lang=lang, _light=light)
    cfg["show"].update(cost=True, project=project)
    return cfg


def hero(light):
    cfg = cfg_for("calm-two-line", light)
    s = status("Ultra", "ultra", "Fable 5", "xhigh", 64, 41, 18, 32, 4.73,
               project="aurora", project_usd=1284.40)
    return [themes.render(s, cfg, 108, True).split("\n")]


def layouts(light):
    blocks = []
    examples = (
        ("calm-one-line", status("Max 20x", "max_20x", "Opus 5", "high", 38, 22, 9, 14, 2.41)),
        ("calm-two-line", status("Max 5x", "max_5x", "Sonnet 5", "medium", 57, 44, 31, 48, 0.86)),
        ("expressive", status("Pro", "pro", "Opus 5", "max", 86, 93, 64, 71, 7.10)),
        ("traffic", status("Max 20x", "max_20x", "Haiku 5", None, 12, 8, 3, 6, 0.12)),
    )
    for theme, s in examples:
        cfg = cfg_for(theme, light, project=False)
        label = draw.paint(theme, "quiet", True)
        blocks.append([label] + themes.render(s, cfg, 108, True).split("\n") + [""])
    blocks[-1] = blocks[-1][:-1]
    return blocks


def tiers(light):
    line = []
    for tier, text in (("pro", "PRO"), ("max_5x", "MAX 5×"), ("max_20x", "MAX 20×"),
                       ("ultra", "ULTRA")):
        ramp = draw.for_background(draw.plan_ramp("violet", tier), draw.FAMILIES["violet"],
                                   light)
        line.append(draw.gradient(text, ramp, True))
    return [["        ".join(line)]]


if __name__ == "__main__":
    render(hero, "hero", 108)
    render(layouts, "layouts", 108)
    render(tiers, "tiers", 44)
