"""
Draw the mod's icon (256x256) and save it as the uncompressed BGRA .dds the
mod uses, plus a .png copy for the repository.

  python make_icon.py <icon_arabicLanguage.dds> <icon.png>
  python make_icon.py <icon_arabicLanguage.dds> <icon.png> <picture> x0 y0 x1 y1

Arabic is shaped with preview.visual(), since Pillow here has no shaping.
"""

import math
import struct
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from preview import visual

SIZE = 256
SS = 4                      # supersampling
W = SIZE * SS
FONT_BOLD = r'C:\Windows\Fonts\segoeuib.ttf'
FONT_BLACK = r'C:\Windows\Fonts\seguibl.ttf'


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def rounded_mask(radius):
    mask = Image.new('L', (W, W), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, W - 1), radius, fill=255)
    return mask


def draw():
    img = Image.new('RGBA', (W, W))
    d = ImageDraw.Draw(img)

    # sunset sky
    horizon = int(W * 0.58)
    for y in range(horizon):
        t = y / horizon
        d.line((0, y, W, y), fill=lerp((22, 60, 110), (250, 170, 70), t ** 1.4) + (255,))

    # sun with a soft glow
    sun = Image.new('RGBA', (W, W), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sun)
    cx, cy, r = W * 0.5, horizon - W * 0.02, W * 0.17
    sd.ellipse((cx - r * 1.9, cy - r * 1.9, cx + r * 1.9, cy + r * 1.9), fill=(255, 210, 120, 90))
    sun = sun.filter(ImageFilter.GaussianBlur(W * 0.04))
    ImageDraw.Draw(sun).ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 226, 140, 255))
    img.alpha_composite(sun)

    # distant hills
    for depth, colour in ((0.0, (58, 110, 60)), (0.05, (44, 92, 46))):
        pts = [(0, W)]
        for x in range(0, W + 1, 8):
            pts.append((x, horizon - W * (0.035 - depth)
                        + math.sin(x / W * 6.3 + depth * 40) * W * 0.018))
        pts.append((W, W))
        d.polygon(pts, fill=colour + (255,))

    # ploughed field rows running to the horizon
    field_top = horizon + int(W * 0.03)
    d.rectangle((0, field_top, W, W), fill=(96, 150, 48, 255))
    vanish = (W * 0.5, field_top - W * 0.25)
    for i in range(-14, 15):
        x0 = W * 0.5 + i * W * 0.11
        colour = (150, 196, 70, 255) if i % 2 else (70, 120, 36, 255)
        x1 = x0 + W * 0.055
        top = lambda x: vanish[0] + (x - vanish[0]) * 0.18
        d.polygon([(top(x0), field_top), (top(x1), field_top), (x1, W), (x0, W)], fill=colour)

    # dark band so the title reads on any background
    band = Image.new('RGBA', (W, W), (0, 0, 0, 0))
    ImageDraw.Draw(band).rectangle((0, int(W * 0.05), W, int(W * 0.47)), fill=(0, 0, 0, 70))
    img.alpha_composite(band.filter(ImageFilter.GaussianBlur(W * 0.03)))

    title = visual('تعريب')
    font = ImageFont.truetype(FONT_BOLD, int(W * 0.27))
    box = d.textbbox((0, 0), title, font=font)
    tx = (W - (box[2] - box[0])) / 2 - box[0]
    ty = W * 0.27 - (box[3] + box[1]) / 2

    shadow = Image.new('RGBA', (W, W), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((tx + W * 0.012, ty + W * 0.016), title, font=font, fill=(0, 0, 0, 170))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(W * 0.012)))
    d.text((tx, ty), title, font=font, fill=(255, 255, 255, 255),
           stroke_width=int(W * 0.006), stroke_fill=(120, 70, 10, 255))

    # "FS22" badge
    badge_font = ImageFont.truetype(FONT_BLACK, int(W * 0.1))
    label = 'FS22'
    bb = d.textbbox((0, 0), label, font=badge_font)
    bw, bh = bb[2] - bb[0] + W * 0.07, bb[3] - bb[1] + W * 0.045
    bx, by = (W - bw) / 2, W * 0.78
    d.rounded_rectangle((bx, by, bx + bw, by + bh), bh / 2, fill=(255, 196, 40, 255),
                        outline=(255, 255, 255, 255), width=int(W * 0.008))
    d.text((bx + (bw - (bb[2] - bb[0])) / 2 - bb[0], by + (bh - (bb[3] - bb[1])) / 2 - bb[1]),
           label, font=badge_font, fill=(40, 60, 20, 255))

    img.putalpha(rounded_mask(int(W * 0.12)))
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def save_dds(img, path):
    header = struct.pack('<4sIIIIIII44xIIIIIIIIIIII4x',
                         b'DDS ', 124, 0x100F, SIZE, SIZE, SIZE * 4, 0, 1,
                         32, 0x41, 0, 32, 0xFF0000, 0xFF00, 0xFF, 0xFF000000, 0x1000, 0, 0, 0)
    r, g, b, a = img.split()
    open(path, 'wb').write(header + Image.merge('RGBA', (b, g, r, a)).tobytes())


def from_image(path, box):
    """Square crop (x0 y0 x1 y1) of a picture, with the icon's rounded corners."""
    img = Image.open(path).convert('RGBA').crop(box).resize((W, W), Image.LANCZOS)
    img.putalpha(rounded_mask(int(W * 0.12)))
    return img.resize((SIZE, SIZE), Image.LANCZOS)


if __name__ == '__main__':
    # python make_icon.py out.dds out.png [picture x0 y0 x1 y1]
    if len(sys.argv) > 3:
        icon = from_image(sys.argv[3], tuple(int(v) for v in sys.argv[4:8]))
    else:
        icon = draw()
    save_dds(icon, sys.argv[1])
    icon.save(sys.argv[2])
