#!/usr/bin/env python3
"""Make the jog-screen artwork shown for tracks without a cover.

    make_labels.py "Kalte" "Studio"            # left decks, right decks
    make_labels.py "Kalte" "Studio" out_dir    # default: ~/.config/ddj1000-screens

The DDJ-1000 shows only the top half of the 80x80 artwork, so the text is
drawn there. Restart the service afterwards:
    systemctl --user restart ddj1000-screens
"""
import io
import os
import sys

from PIL import Image, ImageDraw, ImageFont

SIZE = 320                     # drawn at 4x, downsampled to 80x80
MAX_JPEG = 32 * 58 - 2
FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "arialbd.ttf",
]


def font(size):
    for path in FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def label(text, accent=(0, 170, 255)):
    im = Image.new("RGB", (SIZE, SIZE), (0, 0, 0))
    d = ImageDraw.Draw(im)
    size = 150
    while size > 20:
        f = font(size)
        left, top, right, bottom = d.textbbox((0, 0), text, font=f, anchor="mm")
        if right - left <= SIZE * 0.86 and bottom - top <= SIZE * 0.36:
            break
        size -= 2
    d.text((SIZE / 2, SIZE * 0.23), text, font=f, fill=(255, 255, 255), anchor="mm")
    d.line((SIZE * 0.12, SIZE * 0.44, SIZE * 0.88, SIZE * 0.44), fill=accent, width=8)
    return im.resize((80, 80), Image.LANCZOS)


def jpeg(im):
    for quality in range(90, 15, -5):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, subsampling=2, progressive=False)
        if len(buf.getvalue()) <= MAX_JPEG:
            return buf.getvalue()
    raise SystemExit("label does not fit in %d bytes" % MAX_JPEG)


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    out = sys.argv[3] if len(sys.argv) > 3 else os.path.expanduser("~/.config/ddj1000-screens")
    os.makedirs(out, exist_ok=True)
    for side, text in (("left", sys.argv[1]), ("right", sys.argv[2])):
        path = os.path.join(out, side + ".jpg")
        open(path, "wb").write(jpeg(label(text)))
        print("wrote", path)


if __name__ == "__main__":
    main()
