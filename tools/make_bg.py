"""Makes the home screen's background: tools/bg-source.jpg, cropped to 16:9 and scaled to 1920 x 1080.

    python3 tools/make_bg.py

No dithering: the engraving keeps its own tones. It is saved as a JPEG so the picture stays small in the package;
web/bg.jpg is also the screensaver's background.
"""
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'tools', 'bg-source.jpg')
OUT = os.path.join(ROOT, 'web', 'bg.jpg')

WIDTH, HEIGHT = 1920, 1080
QUALITY = 85


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


def main():
    im = Image.open(SRC).convert('L')
    im = crop_16x9(im).resize((WIDTH, HEIGHT), Image.LANCZOS)
    im.save(OUT, 'JPEG', quality=QUALITY, optimize=True, progressive=False)
    print('wrote %s (%d bytes)' % (os.path.relpath(OUT, ROOT), os.path.getsize(OUT)))


if __name__ == '__main__':
    main()
