"""Render captured terminal text to a PNG for documentation screenshots."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = r"C:\Windows\Fonts\consola.ttf"
BG, FG, BAR, DIM = (22, 27, 34), (201, 209, 217), (48, 54, 61), (139, 148, 158)
GREEN, YELLOW, CYAN = (63, 185, 80), (210, 153, 34), (88, 166, 255)


def colour(line: str) -> tuple[int, int, int]:
    stripped = line.lstrip()
    if stripped.startswith("$"):
        return GREEN
    if any(token in stripped for token in ("no-op", "passed", "verified", "True", "succeeded")):
        return GREEN
    if stripped.startswith(("=", "#")) or "Administrator Console" in stripped:
        return CYAN
    if any(token in stripped for token in ("create", "unknown", "missing")):
        return YELLOW
    return FG


def render(title: str, source: Path, target: Path) -> None:
    lines = source.read_text(encoding="utf-8").replace("\t", "    ").splitlines()
    font = ImageFont.truetype(FONT, 17)
    width_chars = max(len(line) for line in lines)
    char_w, line_h, pad, bar_h = 10, 24, 22, 38
    width = max(900, width_chars * char_w + pad * 2)
    height = bar_h + pad * 2 + line_h * len(lines)
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, bar_h), fill=BAR)
    for index, dot in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        draw.ellipse((14 + index * 24, 12, 28 + index * 24, 26), fill=dot)
    draw.text((width // 2 - len(title) * 4, 9), title, fill=DIM, font=font)
    for number, line in enumerate(lines):
        draw.text((pad, bar_h + pad + number * line_h), line, fill=colour(line), font=font)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)


if __name__ == "__main__":
    render(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]))
