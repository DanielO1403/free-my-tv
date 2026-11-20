"""Makes the home screen's background: tools/bg-source.jpg as a 1920 x 1080 black-and-white halftone.

    python3 tools/make_bg.py

The source (a 16:9 crop of the engraving) is levelled and drawn as a 45-degree dot screen: one round black dot per
cell, its size following the cell's darkness, the way a printed halftone does. The result is 1-bit, so the TV shows it
crisp at any scale. web/bg.png is also the screensaver's background.
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'tools', 'bg-source.jpg')
OUT = os.path.join(ROOT, 'web', 'bg.png')

WIDTH, HEIGHT = 1920, 1080
CELL = 9          # distance between neighbouring dots, in pixels
BLACK, WHITE = 85, 220   # levels: everything below BLACK is solid, above WHITE is blank
GAMMA = 0.9
MAX_RADIUS = 1.15  # times half a cell, so solid areas close up instead of leaving white corners
SUPERSAMPLE = 3


def crop_16x9(im):
    """Center crop to 16:9 without stretching."""
    want = WIDTH / float(HEIGHT)
    w, h = im.size
    if w / float(h) > want:
        nw = int(h * want)
        x = (w - nw) // 2
        return im.crop((x, 0, x + nw, h))
    nh = int(w / want)
    y = (h - nh) // 2
    return im.crop((0, y, w, y + nh))


def levels(im):
    lut = []
    for v in range(256):
        t = (v - BLACK) / float(WHITE - BLACK)
        t = 0.0 if t < 0 else (1.0 if t > 1 else t)
        lut.append(int(255 * (t ** GAMMA)))
    return im.point(lut)


def halftone(im):
    # Draw at 3x and shrink, so each dot gets a round edge before the 1-bit cut. The screen is turned 45 degrees,
    # which is how printed halftones look and keeps the dots from lining up with the picture's own lines.
    scale = SUPERSAMPLE
    sheet = Image.new('L', (WIDTH * scale, HEIGHT * scale), 255)
    draw = ImageDraw.Draw(sheet)
    dot = im.filter(ImageFilter.GaussianBlur(CELL / 2.0))
    step = CELL / math.sqrt(2)
    span = int((WIDTH + HEIGHT) / step) + 4
    radius_max = CELL / 2.0 * MAX_RADIUS
    for i in range(-span, span + 1):
        for j in range(-span, span + 1):
            x = (i - j) * step + CELL
            y = (i + j) * step + CELL
            if x < -CELL or x > WIDTH + CELL or y < -CELL or y > HEIGHT + CELL:
                continue
            v = dot.getpixel((max(0, min(WIDTH - 1, int(x))), max(0, min(HEIGHT - 1, int(y)))))
            radius = radius_max * ((1.0 - v / 255.0) ** 0.5)
            if radius <= 0.2:
                continue
            draw.ellipse([(x - radius) * scale, (y - radius) * scale,
                          (x + radius) * scale, (y + radius) * scale], fill=0)
    return sheet.resize((WIDTH, HEIGHT), Image.LANCZOS).point(lambda v: 0 if v < 128 else 255, '1')


def main():
    im = Image.open(SRC).convert('L')
    im = crop_16x9(im).resize((WIDTH, HEIGHT), Image.LANCZOS)
    im = levels(im)
    halftone(im).save(OUT, optimize=True)
    print('wrote %s (%d bytes)' % (os.path.relpath(OUT, ROOT), os.path.getsize(OUT)))


if __name__ == '__main__':
    main()
