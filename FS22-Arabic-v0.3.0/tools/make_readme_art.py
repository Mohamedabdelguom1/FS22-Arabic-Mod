"""
Draw the coloured step cards shown on the repository page.

  python make_readme_art.py <out dir>

Arabic is shaped with preview.visual(), since Pillow here has no shaping.
"""

import math
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from preview import visual

W, H = 1000, 240
SS = 2
FONT = r'C:\Windows\Fonts\segoeuib.ttf'
FONT_REG = r'C:\Windows\Fonts\segoeui.ttf'

STEPS = [
    ('1', 'حمّل ملف التثبيت', 'FS22-Arabic-Installer.zip  ثم فكّ ضغطه',
     ((30, 110, 220), (70, 170, 255)), 'download'),
    ('2', 'شغّل Install.bat', 'دبل كليك… وانتظر دقيقة واحدة',
     ((30, 150, 70), (110, 200, 70)), 'gear'),
    ('3', 'افتح اللعبة وفعّل المود', 'اختر الحفظ ثم فعّل Arabic Language',
     ((220, 110, 20), (255, 185, 40)), 'play'),
]


def gradient(size, a, b):
    img = Image.new('RGB', size)
    d = ImageDraw.Draw(img)
    for x in range(size[0]):
        t = x / (size[0] - 1)
        d.line((x, 0, x, size[1]), fill=tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)))
    return img


def icon(d, kind, cx, cy, r, colour):
    if kind == 'download':
        d.rectangle((cx - r * 0.18, cy - r * 0.75, cx + r * 0.18, cy + r * 0.05), fill=colour)
        d.polygon([(cx - r * 0.5, cy - r * 0.05), (cx + r * 0.5, cy - r * 0.05), (cx, cy + r * 0.5)], fill=colour)
        d.rectangle((cx - r * 0.75, cy + r * 0.62, cx + r * 0.75, cy + r * 0.8), fill=colour)
    elif kind == 'gear':
        teeth = []
        for i in range(16):
            a = i * math.pi / 8
            rr = r * (0.8 if i % 2 == 0 else 0.6)
            for da in (-0.17, 0.17):
                teeth.append((cx + rr * math.cos(a + da), cy + rr * math.sin(a + da)))
        d.polygon(teeth, fill=colour)
        d.ellipse((cx - r * 0.25, cy - r * 0.25, cx + r * 0.25, cy + r * 0.25), fill=(255, 255, 255, 255))
    else:
        d.polygon([(cx - r * 0.45, cy - r * 0.65), (cx - r * 0.45, cy + r * 0.65), (cx + r * 0.65, cy)], fill=colour)


def card(num, title, subtitle, colours, kind):
    w, h = W * SS, H * SS
    pad = 14 * SS
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))

    shadow = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((pad, pad + 8 * SS, w - pad, h - pad + 4 * SS), 36 * SS, fill=(0, 0, 0, 90))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(10 * SS)))

    body = gradient((w - 2 * pad, h - 2 * pad), colours[1], colours[0]).convert('RGBA')
    mask = Image.new('L', body.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, body.size[0] - 1, body.size[1] - 1), 36 * SS, fill=255)
    img.paste(body, (pad, pad), mask)
    d = ImageDraw.Draw(img)

    # number badge on the right (Arabic reads from the right)
    r = 62 * SS
    cx, cy = w - pad - 40 * SS - r, h // 2
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 255))
    nf = ImageFont.truetype(FONT, 80 * SS)
    d.text((cx, cy), num, font=nf, fill=colours[0] + (255,), anchor='mm')

    # icon on the left, in a white circle
    ir = 64 * SS
    ix = pad + 40 * SS + ir
    d.ellipse((ix - ir, cy - ir, ix + ir, cy + ir), fill=(255, 255, 255, 255))
    icon(d, kind, ix, cy, ir * 0.7, colours[0] + (255,))

    right = cx - r - 30 * SS
    tf = ImageFont.truetype(FONT, 58 * SS)
    sf = ImageFont.truetype(FONT_REG, 34 * SS)
    d.text((right + 3 * SS, cy - 30 * SS + 3 * SS), visual(title), font=tf, fill=(0, 0, 0, 70), anchor='rs')
    d.text((right, cy - 30 * SS), visual(title), font=tf, fill=(255, 255, 255, 255), anchor='rs')
    d.text((right, cy + 45 * SS), visual(subtitle), font=sf, fill=(255, 255, 255, 235), anchor='rs')
    return img.resize((W, H), Image.LANCZOS)


if __name__ == '__main__':
    out = sys.argv[1]
    for i, step in enumerate(STEPS, 1):
        card(*step).save(os.path.join(out, 'step%d.png' % i))
