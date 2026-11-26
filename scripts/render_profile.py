#!/usr/bin/env python3
"""Render the fastfetch-style profile card in assets/profile-card.svg.

The portrait is a truecolor terminal pixel mosaic made from assets/avatar.jpg
(the headshot from jamesgosnell.com), cut out of its studio backdrop and faded
into the card background.

Run from the repository root with Python 3 and Pillow:
    python scripts/render_profile.py
"""

from __future__ import annotations

import argparse
import base64
import html
import io
from collections import deque
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

BACKGROUND = "#161b22"
BG_RGB = (22, 27, 34)
TEXT = "#c9d1d9"
MUTED = "#697787"
KEY = "#ffa657"
VALUE = "#a5d6ff"

ROWS: tuple[tuple[str, str, str], ...] = (
    ("section", "Who am I?", ""),
    ("meta", "Name", "James R. Gosnell"),
    ("meta", "Role", "Co-founder & CEO at Leadlord"),
    ("meta", "Building", "AI tools for lawyers & regulated firms"),
    ("meta", "Education", "UdeM law grad · Marianopolis alum"),
    ("meta", "Based in", "Montréal, Québec"),
    ("blank", "", ""),
    ("meta", "Open Source", "agentdictate-windows"),
    ("meta", "Stack", "Next.js · TypeScript · Supabase"),
    ("meta", "Languages", "English · Français"),
    ("meta", "Principle", "Work hard, play hard."),
    ("meta", "Offline", "Skiing · Sailing"),
    ("blank", "", ""),
    ("section", "Contact", ""),
    ("meta", "GitHub", "github.com/JamesRGosnell"),
    ("meta", "Website", "jamesgosnell.com"),
    ("meta", "LinkedIn", "linkedin.com/in/james-gosnell"),
    ("blank", "", ""),
    ("section", "Projects", ""),
    ("meta", "Leadlord", "Compliant marketing campaigns"),
    ("meta", "Supacorp", "Corporate records & minute books"),
    ("meta", "Cleardeal", "AI real estate title review"),
    ("meta", "Law Library", "Free Québec law course notes"),
    ("meta", "agentdictate", "Windows voice dictation"),
)

FONT_SIZE = 16
CELL_WIDTH = 9.64
ROW_HEIGHT = 20
ROW_START = 60
RIGHT_X = 456
VALUE_X = RIGHT_X + 14 * CELL_WIDTH
WIDTH = 1006
HEIGHT = ROW_START + (len(ROWS) - 1) * ROW_HEIGHT + 30

PORTRAIT_X = 22
PORTRAIT_Y = 48
PORTRAIT_WIDTH = 392
PORTRAIT_HEIGHT = ROW_START + (len(ROWS) - 1) * ROW_HEIGHT - PORTRAIT_Y + 4
GRID_COLS = 100
GRID_ROWS = round(GRID_COLS * PORTRAIT_HEIGHT / PORTRAIT_WIDTH)
BLOCK_SCALE = 4

# Crop of the 832x1248 headshot: hair to mid-chest, centred on the face.
CROP_TOP = 105 / 1248
CROP_BOTTOM = 690 / 1248
CROP_CENTER_X = 410 / 832


def smoothstep(value: float) -> float:
    v = max(0.0, min(1.0, value))
    return v * v * (3.0 - 2.0 * v)


def text(x: float, y: float, content: str, color: str, extra: str = "") -> str:
    return f'<text x="{x:g}" y="{y:g}" fill="{color}"{extra}>{html.escape(content)}</text>'


def metadata_svg() -> str:
    out: list[str] = []
    for i, (kind, label, value) in enumerate(ROWS):
        y = ROW_START + i * ROW_HEIGHT
        if kind == "section":
            out.append(text(RIGHT_X, y, label, TEXT))
        elif kind == "meta":
            out.append(text(RIGHT_X, y, label + ":", KEY, ' font-weight="bold"'))
            out.append(text(VALUE_X, y, value, VALUE))
    return "\n  ".join(out)


def segment_foreground(source: Image.Image) -> Image.Image:
    """Flood-fill the blue studio backdrop from the borders; keep the biggest blob."""
    w, h = source.size
    px = source.load()
    candidate = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            # Backdrop: clearly blue and brighter than the navy suit.
            if b - r >= 20 and lum >= 28 and b >= 42:
                candidate[y * w + x] = 1

    background = bytearray(w * h)
    queue: deque[tuple[int, int]] = deque()

    def seed(x: int, y: int) -> None:
        i = y * w + x
        if candidate[i] and not background[i]:
            background[i] = 1
            queue.append((x, y))

    for x in range(w):
        seed(x, 0)
    for y in range(h):
        seed(0, y)
        seed(w - 1, y)
    while queue:
        cx, cy = queue.popleft()
        for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
            if 0 <= nx < w and 0 <= ny < h:
                i = ny * w + nx
                if candidate[i] and not background[i]:
                    background[i] = 1
                    queue.append((nx, ny))

    visited = bytearray(w * h)
    best: list[int] = []
    for start in range(w * h):
        if background[start] or visited[start]:
            continue
        comp = [start]
        visited[start] = 1
        q = deque([start])
        while q:
            i = q.popleft()
            cx, cy = i % w, i // w
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if 0 <= nx < w and 0 <= ny < h:
                    j = ny * w + nx
                    if not background[j] and not visited[j]:
                        visited[j] = 1
                        comp.append(j)
                        q.append(j)
        if len(comp) > len(best):
            best = comp

    fg = bytearray(w * h)
    for i in best:
        fg[i] = 255
    mask = Image.frombytes("L", (w, h), bytes(fg))
    # Close small holes (shirt shadows, curls) then soften the edge.
    mask = mask.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
    return mask.filter(ImageFilter.GaussianBlur(radius=2.0))


def grade(source: Image.Image) -> Image.Image:
    """Lift the shadows a touch so dark curls and the navy suit read on #161b22."""
    out = source.point(lambda v: min(255, int(v * 1.08 + 6)))
    out = ImageEnhance.Contrast(out).enhance(1.08)
    out = ImageEnhance.Color(out).enhance(1.05)
    return out.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))


def portrait_svg(path: Path) -> str:
    with Image.open(path) as raw:
        source = ImageOps.exif_transpose(raw).convert("RGB")
    w, h = source.size
    alpha_full = segment_foreground(source)
    graded = grade(source)

    top = h * CROP_TOP
    crop_h = h * (CROP_BOTTOM - CROP_TOP)
    crop_w = crop_h * PORTRAIT_WIDTH / PORTRAIT_HEIGHT
    left = w * CROP_CENTER_X - crop_w / 2
    box = (round(left), round(top), round(left + crop_w), round(top + crop_h))

    rgb = graded.crop(box)
    alpha = alpha_full.crop(box)
    cw, ch = rgb.size
    rp, ap = rgb.load(), alpha.load()
    comp = Image.new("RGB", (cw, ch), BG_RGB)
    cp = comp.load()
    fa = Image.new("L", (cw, ch), 0)
    fp = fa.load()
    for y in range(ch):
        yy = y / max(1, ch - 1)
        bottom = smoothstep((0.99 - yy) / 0.22)
        for x in range(cw):
            xx = x / max(1, cw - 1)
            side = smoothstep(min(xx, 1.0 - xx) / 0.10)
            a = (ap[x, y] / 255.0) * bottom * side
            fp[x, y] = int(a * 255)
            r, g, b = rp[x, y]
            cp[x, y] = (
                int(r * a + BG_RGB[0] * (1 - a)),
                int(g * a + BG_RGB[1] * (1 - a)),
                int(b * a + BG_RGB[2] * (1 - a)),
            )

    small = comp.resize((GRID_COLS, GRID_ROWS), Image.Resampling.LANCZOS)
    small_a = fa.resize((GRID_COLS, GRID_ROWS), Image.Resampling.LANCZOS)
    sp, sap = small.load(), small_a.load()
    for y in range(GRID_ROWS):
        for x in range(GRID_COLS):
            if sap[x, y] < 10:
                sp[x, y] = BG_RGB

    crisp = small.resize((GRID_COLS * BLOCK_SCALE, GRID_ROWS * BLOCK_SCALE), Image.Resampling.NEAREST)
    buf = io.BytesIO()
    crisp.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return (
        f'<image x="{PORTRAIT_X}" y="{PORTRAIT_Y}" width="{PORTRAIT_WIDTH}" '
        f'height="{PORTRAIT_HEIGHT}" image-rendering="pixelated" aria-hidden="true" '
        f'href="data:image/png;base64,{b64}"/>'
    )


def profile_svg(portrait: Path) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!-- Generated by scripts/render_profile.py -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}" font-family="'DejaVu Sans Mono',Consolas,'SF Mono',Menlo,monospace" font-size="{FONT_SIZE}" role="img" aria-labelledby="title description">
  <title id="title">James R. Gosnell, GitHub profile</title>
  <desc id="description">A fastfetch-style profile card with a pixel portrait of James R. Gosnell, co-founder and CEO of Leadlord, a law graduate and software builder in Montréal.</desc>
  <rect width="{WIDTH}" height="{HEIGHT}" fill="{BACKGROUND}" rx="15"/>
  <text x="24" y="28" fill="{TEXT}"><tspan fill="{VALUE}">~</tspan><tspan fill="{MUTED}"> › </tspan>fastfetch</text>
  {portrait_svg(portrait)}
  <g>
  {metadata_svg()}
  </g>
</svg>
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portrait", default=Path("assets/avatar.jpg"), type=Path)
    parser.add_argument("--output", default=Path("assets/profile-card.svg"), type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(profile_svg(args.portrait), encoding="utf-8")
    print(f"wrote {args.output} ({args.output.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
