"""
Draw text the way the game does, from a defaultFont.font/.dds pair, to check glyphs
before starting the game. Arabic is joined and reversed here with the same rules
the Lua mod will use.

  python preview.py <dir with defaultFont.font/.dds> out.png "النص" ["more lines" ...]
"""

import os
import sys
import unicodedata

import numpy as np
from PIL import Image

from add_arabic_glyphs import ATLAS, DDS_HEADER, EDGE, bc4_decode, read_font

# ---------------------------------------------------------------- shaping

FORMS = {}          # base letter -> {isolated, final, initial, medial: codepoint}
LIGATURES = {}      # (lam, alef) -> {isolated, final: codepoint}
for cp in list(range(0xFB50, 0xFC00)) + list(range(0xFE70, 0xFEFD)):
    dec = unicodedata.decomposition(chr(cp)).split()
    if not dec or dec[0] not in ('<isolated>', '<final>', '<initial>', '<medial>'):
        continue
    form, bases = dec[0][1:-1], tuple(int(x, 16) for x in dec[1:])
    if len(bases) == 1:
        FORMS.setdefault(bases[0], {})[form] = cp
    elif bases[0] == 0x0644 and len(bases) == 2:
        LIGATURES.setdefault(bases[1], {})[form] = cp


def joins_left(cp):
    """Can this letter connect to the letter after it?"""
    if cp == 0x0649:    # alef maksura: its joining forms are Uighur only
        return False
    f = FORMS.get(cp, {})
    return 'initial' in f or 'medial' in f


def joins_right(cp):
    f = FORMS.get(cp, {})
    return 'final' in f or 'medial' in f or cp == 0x0640


def shape(text):
    cps = [ord(c) for c in text if not 0x064B <= ord(c) <= 0x0652]   # drop harakat
    out, i = [], 0
    while i < len(cps):
        cp = cps[i]
        prev = cps[i - 1] if i > 0 else None
        prev_joins = prev is not None and joins_left(prev)
        if cp == 0x0644 and i + 1 < len(cps) and cps[i + 1] in LIGATURES:
            lig = LIGATURES[cps[i + 1]]
            out.append(lig['final'] if prev_joins else lig['isolated'])
            i += 2
            continue
        nxt = cps[i + 1] if i + 1 < len(cps) else None
        f = FORMS.get(cp)
        if not f:
            out.append(cp)
        else:
            left = joins_left(cp) and nxt is not None and joins_right(nxt)
            right = prev_joins and joins_right(cp)
            form = {(True, True): 'medial', (True, False): 'final',
                    (False, True): 'initial', (False, False): 'isolated'}[right, left]
            out.append(f.get(form) or f.get('isolated', cp))
        i += 1
    return ''.join(map(chr, out))


def is_rtl(ch):
    return unicodedata.bidirectional(ch) in ('R', 'AL')


def visual(text):
    """Reverse an Arabic line, keeping runs of Latin letters and digits in reading order."""
    s = shape(text)
    if not any(is_rtl(c) for c in s):
        return s
    # Latin letters are L, Arabic letters R, digits N. Digits after Latin text join it
    # ("Simulator 22"); other digits stay their own left-to-right run but count as
    # right-to-left for their neighbours. Spaces and punctuation are left-to-right
    # only between two L, as in "Farming Simulator 22".
    kinds = []
    for c in s:
        b = unicodedata.bidirectional(c)
        kinds.append('L' if b == 'L' else 'N' if b in ('EN', 'AN') else 'R' if is_rtl(c) else None)
    last = 'R'
    for i, k in enumerate(kinds):
        if k == 'N' and last == 'L':
            kinds[i] = 'L'
        elif k in ('L', 'R'):
            last = k
    ltr = []
    for i, k in enumerate(kinds):
        if k is None:
            before = next((x for x in reversed(kinds[:i]) if x), 'R')
            after = next((x for x in kinds[i + 1:] if x), 'R')
            ltr.append(before == after == 'L')
        else:
            ltr.append(k in ('L', 'N'))
    runs, start = [], 0
    for i in range(1, len(s) + 1):
        if i == len(s) or ltr[i] != ltr[start]:
            runs.append((s[start:i], ltr[start]))
            start = i
    mirror = str.maketrans('()[]{}<>«»', ')(][}{><»«')
    return ''.join(r if is_ltr else r[::-1].translate(mirror) for r, is_ltr in reversed(runs))


# ---------------------------------------------------------------- rendering

def render(font_dir, lines, bold=False, scale=2, ordered=False):
    """Draw lines; ordered=True when they are already in visual order (from the mod)."""
    _, glyphs = read_font(os.path.join(font_dir, 'defaultFont.font'))
    dds = open(os.path.join(font_dir, 'defaultFont.dds'), 'rb').read()
    atlas = bc4_decode(dds[DDS_HEADER:], ATLAS, ATLAS).astype(np.float32)
    line_h, width = 56, 1400
    canvas = np.zeros((line_h * len(lines) + 20, width), np.float32)
    missing = set()
    for n, line in enumerate(lines):
        pen, base = 10.0, 15 + line_h * n + 40
        for ch in (line if ordered else visual(line)):
            g = glyphs.get(ord(ch))
            if g is None:
                missing.add(ch)
                continue
            x, y, w, h, xo, yo, adv = g[1 if bold else 0]
            if w and h:
                px, py = int(round(pen + xo)), base - yo
                box = atlas[y:y + h, x:x + w]
                # the same soft edge the game's text shader draws around the outline
                alpha = np.clip((box - EDGE) / 12.5 + 0.5, 0, 1)
                region = canvas[py:py + h, px:px + w]
                region[:] = np.maximum(region, alpha[:region.shape[0], :region.shape[1]])
            pen += adv
    img = Image.fromarray((255 - canvas * 255).astype(np.uint8))
    return img.resize((img.width * scale // 2, img.height * scale // 2)), missing


if __name__ == '__main__':
    font_dir, out = sys.argv[1], sys.argv[2]
    lines = sys.argv[3:]
    regular, missing = render(font_dir, lines)
    bold, _ = render(font_dir, lines, bold=True)
    sheet = Image.new('L', (regular.width, regular.height * 2), 255)
    sheet.paste(regular, (0, 0))
    sheet.paste(bold, (0, regular.height))
    sheet.save(out)
    if missing:
        print('Missing characters:', ' '.join(sorted(missing)))
