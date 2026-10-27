"""
Add Arabic glyphs to Farming Simulator 22's only texture font.

The game draws every text with shared/font/defaultFont.font + defaultFont.dds:
  .font  12-byte header (float size, float ?, u32 glyph count; the engine reads only
         that many records), then one 28-byte record per
         character sorted by codepoint: u32 codepoint, then two 12-byte variants
         (regular, bold): u16 x, u16 y, u8 w, u8 h, i8 xOffset, i8 yOffset, f32 advance.
         xOffset is the box's left edge from the pen, yOffset its top above the baseline.
  .dds   4096x4096 BC4 (one channel), no mipmaps. Each glyph is a signed distance
         field: 128 on the outline, +12.5 per pixel inside, clamped to 0..208.

The engine neither joins Arabic letters nor writes right to left, so we add the
presentation forms (U+FE70..FEFC and a few Persian ones); the Lua mod picks the
right form and reverses the order before calling renderText.

Usage:
  python add_arabic_glyphs.py --game "<game dir>"            install (keeps .original backups)
  python add_arabic_glyphs.py --game "<game dir>" --out DIR  write the result to DIR only
  python add_arabic_glyphs.py --game "<game dir>" --restore  put the original font back
"""

import argparse
import hashlib
import os
import shutil
import struct
import sys
import unicodedata

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ATLAS = 4096
HEADER = 12
RECORD = 28
DDS_HEADER = 148
EDGE = 128.0
SLOPE = 12.5            # SDF value per output pixel, measured on the original atlas
MAX_VALUE = 208.0       # brightest value found in the original atlas
EM = 40                 # pixel size the original glyphs were made at (header float)
PAD = 2                 # pixels kept around each outline, as in the original boxes
GAP = 2                 # empty pixels between packed boxes
SUPER = 4               # supersampling used to build the distance field


# ---------------------------------------------------------------- characters

def arabic_codepoints():
    cps = [0x060C, 0x061B, 0x061F, 0x0640, 0x0671,
           0x067E, 0x0686, 0x0698, 0x06A9, 0x06AF, 0x06CC]
    cps += range(0x0621, 0x063B)
    cps += range(0x0641, 0x064B)
    cps += range(0x0660, 0x066E)
    cps += [c for c in range(0xFE70, 0xFEFD) if c != 0xFE75]
    for a, b in [(0xFB56, 0xFB59), (0xFB7A, 0xFB7D), (0xFB8A, 0xFB8B),
                 (0xFB8E, 0xFB95), (0xFBFC, 0xFBFF)]:
        cps += range(a, b + 1)
    return sorted(set(cps))


# ---------------------------------------------------------------- font file

def read_font(path):
    data = open(path, 'rb').read()
    count = struct.unpack_from('<I', data, 8)[0]
    if len(data) != HEADER + count * RECORD:
        sys.exit('Unexpected .font size: %d bytes for %d glyphs' % (len(data), count))
    header = data[:HEADER]
    glyphs = {}
    for off in range(HEADER, len(data), RECORD):
        cp = struct.unpack_from('<I', data, off)[0]
        glyphs[cp] = [struct.unpack_from('<HHBBbbf', data, off + 4 + 12 * i) for i in range(2)]
    return header, glyphs


def pack_font(header, glyphs):
    out = bytearray(header[:8] + struct.pack('<I', len(glyphs)))
    for cp in sorted(glyphs):
        out += struct.pack('<I', cp)
        for v in glyphs[cp]:
            out += struct.pack('<HHBBbbf', *v)
    return bytes(out)


# ---------------------------------------------------------------- BC4

def bc4_decode(data, w, h):
    bw, bh = w // 4, h // 4
    a = np.frombuffer(data, np.uint8, bw * bh * 8).reshape(-1, 8)
    r0 = a[:, 0].astype(np.int32)
    r1 = a[:, 1].astype(np.int32)
    bits = np.zeros(len(a), np.uint64)
    for i in range(6):
        bits |= a[:, 2 + i].astype(np.uint64) << np.uint64(8 * i)
    idx = np.stack([((bits >> np.uint64(3 * k)) & np.uint64(7)).astype(np.int64) for k in range(16)], 1)
    pal = bc4_palette(r0, r1)
    px = np.take_along_axis(pal, idx, 1)
    return px.reshape(bh, bw, 4, 4).transpose(0, 2, 1, 3).reshape(h, w).astype(np.uint8)


def bc4_palette(r0, r1):
    pal = np.zeros((len(r0), 8), np.int32)
    pal[:, 0], pal[:, 1] = r0, r1
    eight = r0 > r1
    for k in range(1, 7):
        pal[:, 1 + k] = ((7 - k) * r0 + k * r1) // 7
    for k in range(1, 5):
        pal[:, 1 + k] = np.where(eight, pal[:, 1 + k], ((5 - k) * r0 + k * r1) // 5)
    pal[:, 6] = np.where(eight, pal[:, 6], 0)
    pal[:, 7] = np.where(eight, pal[:, 7], 255)
    return pal


def bc4_encode(img):
    h, w = img.shape
    blocks = img.reshape(h // 4, 4, w // 4, 4).transpose(0, 2, 1, 3).reshape(-1, 16).astype(np.int32)
    r0 = blocks.max(1)
    r1 = blocks.min(1)
    pal = bc4_palette(r0, r1)
    idx = np.abs(blocks[:, :, None] - pal[:, None, :]).argmin(2).astype(np.uint64)
    bits = np.zeros(len(blocks), np.uint64)
    for k in range(16):
        bits |= idx[:, k] << np.uint64(3 * k)
    out = np.zeros((len(blocks), 8), np.uint8)
    out[:, 0], out[:, 1] = r0, r1
    for i in range(6):
        out[:, 2 + i] = ((bits >> np.uint64(8 * i)) & np.uint64(255)).astype(np.uint8)
    return out.tobytes()


# ---------------------------------------------------------------- distance field

def distance_to(mask):
    """Exact Euclidean distance from every pixel to the nearest True pixel."""
    h, w = mask.shape
    inf = float(h + w) ** 2
    # rows: distance along x to the nearest feature
    d = np.where(mask, 0.0, np.inf)
    for x in range(1, w):
        d[:, x] = np.minimum(d[:, x], d[:, x - 1] + 1)
    for x in range(w - 2, -1, -1):
        d[:, x] = np.minimum(d[:, x], d[:, x + 1] + 1)
    g2 = np.minimum(d * d, inf)
    # columns: min over y' of g2(y') + (y - y')^2
    ys = np.arange(h, dtype=np.float64)
    dy2 = (ys[:, None] - ys[None, :]) ** 2
    out = np.empty_like(g2)
    for x0 in range(0, w, 64):
        col = g2[:, x0:x0 + 64]
        out[:, x0:x0 + 64] = (col[None, :, :] + dy2[:, :, None]).min(1)
    return np.sqrt(out)


def render_glyph(font, cp):
    """Return (sdf box as uint8, xOffset, yOffset, advance) at EM pixels."""
    ch = chr(cp)
    advance = font.getlength(ch) / SUPER
    left, top, right, bottom = font.getbbox(ch, anchor='ls')
    if right <= left or bottom <= top:
        return None, 0, 0, advance
    # snap the canvas to whole output pixels so the box lines up with the pen grid
    x0 = (int(np.floor(left / SUPER)) - PAD - 2) * SUPER
    y0 = (int(np.floor(top / SUPER)) - PAD - 2) * SUPER
    x1 = (int(np.ceil(right / SUPER)) + PAD + 2) * SUPER
    y1 = (int(np.ceil(bottom / SUPER)) + PAD + 2) * SUPER
    canvas = Image.new('L', (x1 - x0, y1 - y0), 0)
    ImageDraw.Draw(canvas).text((-x0, -y0), ch, font=font, fill=255, anchor='ls')
    inside = np.array(canvas) >= 128
    sd = np.where(inside, distance_to(~inside) - 0.5, -(distance_to(inside) - 0.5)) / SUPER
    h, w = sd.shape
    sd = sd.reshape(h // SUPER, SUPER, w // SUPER, SUPER).mean((1, 3))
    val = np.clip(EDGE + SLOPE * sd, 0, MAX_VALUE)
    # trim to the outline plus PAD, like the original boxes
    keep = sd > -PAD - 0.25
    rows, cols = np.where(keep.any(1))[0], np.where(keep.any(0))[0]
    val = val[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
    x_off = x0 // SUPER + cols[0]
    y_off = -(y0 // SUPER + rows[0])
    return np.round(val).astype(np.uint8), x_off, y_off, advance


# ---------------------------------------------------------------- packing

def pack(boxes, first_row):
    """Shelf-pack boxes (list of (key, w, h)) below first_row. Returns key -> (x, y)."""
    order = sorted(boxes, key=lambda b: -b[2])
    pos, x, y, shelf = {}, 0, first_row, 0
    for key, w, h in order:
        if x + w > ATLAS:
            x, y, shelf = 0, y + shelf + GAP, 0
        if y + h > ATLAS:
            sys.exit('Not enough free space in the atlas.')
        pos[key] = (x, y)
        x += w + GAP
        shelf = max(shelf, h)
    return pos, y + shelf


# ---------------------------------------------------------------- main build

def build(src_font, src_dds, regular_path, bold_path):
    header, glyphs = read_font(src_font)
    dds = open(src_dds, 'rb').read()
    dxgi = struct.unpack_from('<I', dds, 128)[0]
    if dds[84:88] != b'DX10' or dxgi != 80 or struct.unpack_from('<II', dds, 12) != (ATLAS, ATLAS):
        sys.exit('Unexpected .dds format (expected 4096x4096 BC4).')
    atlas = bc4_decode(dds[DDS_HEADER:], ATLAS, ATLAS)

    # empty glyphs (space and friends) carry dummy coordinates, so only real boxes count
    used_bottom = max(y + h for v in glyphs.values() for x, y, w, h, *_ in v if w and h)
    first_row = (used_bottom + GAP + 3) // 4 * 4   # start on a fresh BC4 block row

    fonts = [ImageFont.truetype(p, EM * SUPER, layout_engine=ImageFont.Layout.BASIC)
             for p in (regular_path, bold_path)]
    new = [cp for cp in arabic_codepoints() if cp not in glyphs]
    rendered = {}
    for cp in new:
        for variant, font in enumerate(fonts):
            rendered[cp, variant] = render_glyph(font, cp)

    boxes = [(k, r[0].shape[1], r[0].shape[0]) for k, r in rendered.items() if r[0] is not None]
    pos, bottom = pack(boxes, first_row)

    atlas = atlas.copy()
    for cp in new:
        recs = []
        for variant in range(2):
            img, x_off, y_off, adv = rendered[cp, variant]
            if img is None:     # spaces and the like: nothing to draw
                recs.append((0, 0, 0, 0, 0, 0, adv))
                continue
            x, y = pos[cp, variant]
            h, w = img.shape
            atlas[y:y + h, x:x + w] = img
            recs.append((x, y, w, h, x_off, y_off, adv))
        glyphs[cp] = recs

    # only the new block rows are re-encoded; every original block stays byte-identical
    rows_end = min(ATLAS, (bottom + 3) // 4 * 4)
    start = first_row // 4 * (ATLAS // 4) * 8
    end = rows_end // 4 * (ATLAS // 4) * 8
    body = bytearray(dds[DDS_HEADER:])
    body[start:end] = bc4_encode(atlas[first_row:rows_end])
    new_dds = dds[:DDS_HEADER] + bytes(body)

    check = bc4_decode(bytes(body), ATLAS, ATLAS)
    err = np.abs(check[first_row:rows_end].astype(int) - atlas[first_row:rows_end]).max()
    print('Added %d characters (%d glyph boxes), rows %d-%d, max BC4 error %d'
          % (len(new), len(boxes), first_row, bottom, err))
    return pack_font(header, glyphs), new_dds, check, glyphs


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def replace(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--game', required=True, help='Farming Simulator 22 folder')
    ap.add_argument('--font', default=r'C:\Windows\Fonts\segoeui.ttf')
    ap.add_argument('--font-bold', default=r'C:\Windows\Fonts\segoeuib.ttf')
    ap.add_argument('--out', help='write the result here instead of into the game')
    ap.add_argument('--restore', action='store_true', help='put the original font back')
    args = ap.parse_args()

    base = os.path.join(args.game, 'shared', 'font', 'defaultFont')
    files = [base + '.font', base + '.dds']
    backups = [f + '.original' for f in files]

    if args.restore:
        if not all(os.path.exists(b) for b in backups):
            sys.exit('No backup found; nothing to restore.')
        for f, b in zip(files, backups):
            shutil.copyfile(b, f + '.tmp')
            os.replace(f + '.tmp', f)
        print('Original font restored.')
        return

    if args.out:
        # trial run: read the original (or its backup) and leave the game untouched
        sources = [b if os.path.exists(b) else f for f, b in zip(files, backups)]
        os.makedirs(args.out, exist_ok=True)
        targets = [os.path.join(args.out, os.path.basename(f)) for f in files]
    else:
        # the backup is made once and never overwritten, so every run starts from the original
        for f, b in zip(files, backups):
            if not os.path.exists(b):
                shutil.copyfile(f, b)
                if sha(f) != sha(b):
                    sys.exit('Backup of %s does not match; stopping.' % f)
                print('Backup saved:', b)
        sources, targets = backups, files

    font_data, dds_data, atlas, glyphs = build(sources[0], sources[1], args.font, args.font_bold)
    replace(targets[0], font_data)
    replace(targets[1], dds_data)
    print('Written:', *targets, sep='\n  ')


if __name__ == '__main__':
    main()
