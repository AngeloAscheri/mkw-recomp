# /// script
# requires-python = ">=3.14"
# dependencies = ["fonttools>=4.60"]
# ///
"""The game's fonts with the letters a translation needs and they lack, composed from their own pieces.

Why: the fonts of the game's European text (FOT-RodinNTLGPro EB and UB, which the race font sets fall back to for
every letter, and VDL-LogoG) have ç ö ü ı but not ğ Ğ ş Ş İ, so a Turkish text would show gaps (discussion #593). Each
missing letter is drawn here from the same font: the base letter plus the breve, dot or cedilla the font already has,
placed where that font places the same kind of mark (the diaeresis of ö/Ö, the cedilla of ç/Ç), so it keeps the font's
weight and style. Vietnamese (#873) needs ~100 letters (ă đ ơ ư, and those with two marks): see vietnamese() below.
Nothing of Nintendo's is shipped: the setup composes them from the player's own copy.

Font/<name>.bfotf.zs: zstd of a "bfotf", an OpenType font after an 8-byte header (the magic d9 9b 87 1a, then the
font's size, big-endian; padding may follow) with size and font XORed with the key a6 01 85 02 (measured 18/11/2026).

Usage:
  uv run tools/i18n/game_fonts.py missing tr           the letters of i18n/game/base/tr.tsv each game font lacks
  uv run tools/i18n/game_fonts.py build tr -o DIR      the composed fonts and their manifest lines (game_texts.py build)
The game copy is game/ in the repository (a link to your copy) or MKW_GAME.
"""

import argparse
import hashlib
import struct
import sys
import unicodedata
from compression import zstd
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

KEY = bytes.fromhex("a6018502")
MAGIC = bytes.fromhex("d99b871a")
# The fonts the European texts are drawn with (Font/*.bfcpx, the layouts' fnl1 lists). NinDev-RaceFontMoveR and
# nintendoP_RodinNTLG-EB have every letter of Western European and Turkish text, but not Vietnamese's.
FONTS = ("FOT-RodinNTLGPro-EB", "FOT-RodinNTLGPro-UB", "VDL-LogoG-Heavy", "VDL-LOGOG-ULTRA", "NinDev-RaceFontMoveR",
         "nintendoP_RodinNTLG-EB")  # fmt: skip
# letter -> (base, mark, reference letter whose mark sets the height, the reference's base)
ABOVE, BELOW = "above", "below"
RECIPES = {
    "ğ": ("g", "̆", ABOVE, "ö", "o"),
    "Ğ": ("G", "̆", ABOVE, "Ö", "O"),
    "İ": ("I", "̇", ABOVE, "Ö", "O"),
    "ş": ("s", "¸", BELOW, "ç", "c"),
    "Ş": ("S", "¸", BELOW, "Ç", "C"),
}


def decrypt(data: bytes) -> bytes:
    if data[:4] != MAGIC:
        raise ValueError("not a bfotf")
    (size,) = struct.unpack(">I", xor(data[4:8], 4))
    if size > len(data) - 8:  # VDL-LogoG-Heavy has one byte of padding after its font
        raise ValueError(f"bfotf of {len(data)} bytes says {size} after its header")
    return xor(data[8 : 8 + size], 8)


def encrypt(font: bytes) -> bytes:
    return MAGIC + xor(struct.pack(">I", len(font)), 4) + xor(font, 8)


def xor(data: bytes, start: int) -> bytes:
    """data XORed with the key as it falls at offset start of the file (the key restarts at offset 0)."""
    n = len(data)
    key = (KEY * (n // 4 + 2))[start % 4 : start % 4 + n]
    return (int.from_bytes(data, "little") ^ int.from_bytes(key, "little")).to_bytes(n, "little")


def bounds(glyphs, name: str) -> tuple[float, float, float, float]:
    pen = BoundsPen(glyphs)
    glyphs[name].draw(pen)
    return pen.bounds


def contours(glyphs, name: str) -> list[tuple[float, float, float, float]]:
    """The control-point box of each contour of a glyph."""
    pen = DecomposingRecordingPen(glyphs)
    glyphs[name].draw(pen)
    out, pts = [], []
    for op, args in pen.value:
        pts += args
        if op in ("closePath", "endPath") and pts:
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            out.append((min(xs), min(ys), max(xs), max(ys)))
            pts = []
    return out


def mark_shift(glyphs, cmap: dict[int, str], recipe: tuple[str, str, str, str, str]) -> tuple[float, float]:
    """How far the mark glyph moves: centred on the base letter, at the height the reference letter's own mark has."""
    base, mark, where, ref, ref_base = recipe
    bx0, _, bx1, _ = bounds(glyphs, cmap[ord(base)])
    mx0, my0, mx1, my1 = bounds(glyphs, cmap[ord(mark)])
    dx = (bx0 + bx1) / 2 - (mx0 + mx1) / 2
    if where == BELOW:
        # the cedilla can be one contour with the c: the reference's lowest point is the mark's
        return dx, bounds(glyphs, cmap[ord(ref)])[1] - my0
    top = bounds(glyphs, cmap[ord(ref_base)])[3]
    above = [c for c in contours(glyphs, cmap[ord(ref)]) if c[1] > top - 5]
    if not above:
        raise ValueError(f"no mark above {ref}")
    return dx, min(c[1] for c in above) - my0


# Vietnamese (#873): its letters with marks, which the game's fonts lack (all but those of Latin-1), drawn from the base
# letter and the font's own marks: the grave, acute, circumflex and tilde of à á â ã (À Á Â Ã for capitals), the
# breve, and the dot of i for the dot below. The hook above and the horn have no glyph in these fonts: the hook is the
# top of the font's "?" and the horn its "’", scaled. A tone mark over the circumflex goes beside it, at its right, as
# Vietnamese type sets ấ ầ ẩ, so the letter grows no taller; over the breve it stacks. Đ is the font's Ð (the same
# letter), đ the d with the font's hyphen as its bar.
GRAVE, ACUTE, CIRCUMFLEX, TILDE, BREVE, HOOK, HORN, DOT_BELOW = "̀", "́", "̂", "̃", "̆", "̉", "̛", "̣"  # fmt: skip
ABOVE_MARKS = (GRAVE, ACUTE, CIRCUMFLEX, TILDE, BREVE, HOOK)
FROM_LETTER = {GRAVE: "àÀ", ACUTE: "áÁ", CIRCUMFLEX: "âÂ", TILDE: "ãÃ"}  # (lower, upper), over a and A
IDENTITY = (1, 0, 0, 1, 0, 0)
Box = tuple[float, float, float, float]
Shape = list[tuple[Box, list]]  # contours: (box of their points, pen operations)


def outline(glyphs, name: str) -> Shape:
    pen = DecomposingRecordingPen(glyphs)
    glyphs[name].draw(pen)
    out, ops, pts = [], [], []
    for op, args in pen.value:
        ops.append((op, args))
        pts += args
        if op in ("closePath", "endPath"):
            if pts:
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                out.append(((min(xs), min(ys), max(xs), max(ys)), ops))
            ops, pts = [], []
    return out


def box(shape: Shape) -> Box:
    return (min(b[0] for b, _ in shape), min(b[1] for b, _ in shape), max(b[2] for b, _ in shape),
            max(b[3] for b, _ in shape))  # fmt: skip


def moved(b: Box, m: tuple) -> Box:
    return (b[0] * m[0] + m[4], b[1] * m[3] + m[5], b[2] * m[0] + m[4], b[3] * m[3] + m[5])


def fit(shape: Shape, scale: float, x0: float | None = None, y0: float | None = None, cx: float | None = None,
        y1: float | None = None) -> tuple[tuple, Box]:  # fmt: skip
    """The transform scaling shape and putting its left edge at x0 (or its centre at cx), its bottom at y0 (or its top
    at y1); and the box it then covers."""
    b = box(shape)
    dx = (x0 - b[0] * scale) if x0 is not None else (cx - (b[0] + b[2]) / 2 * scale)
    dy = (y0 - b[1] * scale) if y0 is not None else (y1 - b[3] * scale)
    m = (scale, 0, 0, scale, dx, dy)
    return m, moved(b, m)


class Marks:
    """A font's mark shapes for lower or upper case, each with the gap the font leaves between a letter and it."""

    def __init__(self, glyphs, cmap: dict[int, str], upper: bool):
        self.shapes: dict[str, Shape] = {}
        a = "A" if upper else "a"
        if ord(a) not in cmap:
            return
        top = box(outline(glyphs, cmap[ord(a)]))[3]
        for mark, letters in FROM_LETTER.items():
            if ord(letters[upper]) in cmap:
                shape = [c for c in outline(glyphs, cmap[ord(letters[upper])]) if c[0][1] > top - 5]
                if shape:
                    self.shapes[mark] = shape
        if not self.shapes.get(ACUTE):
            return
        self.gap = box(self.shapes[ACUTE])[1] - top
        height = box(self.shapes[ACUTE])[3] - box(self.shapes[ACUTE])[1]
        for cp in (0x306, 0x2D8):  # the combining breve, else the spacing one
            if cp in cmap:
                self.shapes[BREVE] = outline(glyphs, cmap[cp])
                break
        if ord("?") in cmap:  # the hook: "?" without its dot, as tall as the acute
            q = outline(glyphs, cmap[ord("?")])
            hook = [c for c in q if c[0][1] > min(b[1] for b, _ in q) + 1]
            if hook:
                self.shapes[HOOK] = hook
                self.hook_scale = height / (box(hook)[3] - box(hook)[1])
        # the horn: the closing quote, the apostrophe or the comma, whichever is one stroke (NinDev's quote has two)
        horns = [outline(glyphs, cmap[cp]) for cp in (0x2019, 0x27, 0x2C) if cp in cmap]
        if horns:
            self.shapes[HORN] = min(horns, key=len)
        if ord("i") in cmap:  # the dot below: the dot of i (its highest contour)
            dots = outline(glyphs, cmap[ord("i")])
            self.shapes[DOT_BELOW] = [max(dots, key=lambda c: c[0][1])]

    def scale(self, mark: str) -> float:
        return self.hook_scale if mark == HOOK else 1.0


def vietnamese(glyphs, cmap: dict[int, str], ch: str) -> tuple[str, list[tuple[Shape, tuple]], float] | None:
    """ch drawn from its base letter and marks: (the glyph its metrics come from, its parts, its advance width)."""
    nfd = unicodedata.normalize("NFD", ch)
    base, marks = nfd[0], nfd[1:]
    if ch == "đ":
        base, marks = "d", ""
        if ord(base) not in cmap:
            return None
    elif not marks or any(m not in ABOVE_MARKS + (HORN, DOT_BELOW) for m in marks) or ord(base) not in cmap:
        return None
    upper = base.isupper()
    font_marks = Marks(glyphs, cmap, upper)
    if not hasattr(font_marks, "gap"):
        return None
    base_box = box(outline(glyphs, cmap[ord(base)]))
    # start from the longest precomposed part the font has (â for ấ), else the base (ı for an i with a mark above)
    start, rest, above = base, marks, []
    for k in range(len(marks), 0, -1):
        pre = unicodedata.normalize("NFC", base + marks[:k])
        if len(pre) == 1 and ord(pre) in cmap:
            start, rest = pre, marks[k:]
            over = [c for c in outline(glyphs, cmap[ord(pre)]) if c[0][1] > base_box[3] - 5]
            above = [(m, box(over)) for m in marks[:k] if m in ABOVE_MARKS and over][-1:]
            break
    if start == "i" and any(m in ABOVE_MARKS for m in rest) and 0x131 in cmap:
        start = "ı"  # the marks sit where the dot was
        base_box = box(outline(glyphs, cmap[0x131]))
    name = cmap[ord(start)]
    width = glyphs[name].width
    parts = [(outline(glyphs, name), IDENTITY)]
    cx = (base_box[0] + base_box[2]) / 2
    right = base_box[2]
    if ch == "đ":  # the bar: the hyphen across the top of the stem, halfway between the x-height and the ascender
        if ord("-") not in cmap or ord("x") not in cmap:
            return None
        bar = outline(glyphs, cmap[ord("-")])
        hb, xh = box(bar), box(outline(glyphs, cmap[ord("x")]))[3]
        w = base_box[2] - base_box[0]
        sx, sy = 0.62 * w / (hb[2] - hb[0]), 0.8
        y = (xh + base_box[3]) / 2 - (hb[3] - hb[1]) * sy / 2
        m = (sx, 0, 0, sy, base_box[2] + 0.08 * w - hb[2] * sx, y - hb[1] * sy)
        return name, [*parts, (bar, m)], width
    for mark in rest:
        shape = font_marks.shapes.get(mark)
        if not shape:
            return None
        if mark == HORN:  # at the top right of o or u, rising past it
            acute, horn = box(font_marks.shapes[ACUTE]), box(shape)
            s = (acute[3] - acute[1]) / (horn[3] - horn[1])  # as tall as the acute
            w, h = base_box[2] - base_box[0], base_box[3] - base_box[1]
            m, b = fit(shape, s, x0=base_box[2] - 0.08 * w, y1=base_box[3] + 0.12 * h)
            right = max(right, b[2])
        elif mark == DOT_BELOW:  # under the baseline; on y beside its tail, at the right, as Vietnamese type sets ỵ
            w = base_box[2] - base_box[0]
            m, b = fit(shape, 1.0, cx=cx if base != "y" else base_box[0] + 0.8 * w, y1=-font_marks.gap)
        elif not above:
            m, b = fit(shape, font_marks.scale(mark), cx=cx, y0=base_box[3] + font_marks.gap)
        elif above[-1][0] == CIRCUMFLEX and mark in (ACUTE, GRAVE, HOOK):  # beside the circumflex, at its right
            prev = above[-1][1]
            s = 0.8 * font_marks.scale(mark)
            m, b = fit(shape, s, x0=prev[2] - 0.12 * (prev[2] - prev[0]), y0=prev[1] + 0.45 * (prev[3] - prev[1]))
            right = max(right, b[2])
        else:  # over the mark below it (the tone over a breve, the tilde over a circumflex)
            prev = above[-1][1]
            m, b = fit(shape, font_marks.scale(mark), cx=cx, y0=prev[3] + 0.35 * font_marks.gap)
        if mark in ABOVE_MARKS:
            above.append((mark, b))
        parts.append((shape, m))
    width = max(width, round(right + (width - base_box[2])))  # a horn or a side mark past the letter widens it
    return name, parts, width


def compose(font: TTFont, letters: str) -> list[str]:
    """Add each of letters the font lacks and has a recipe for; returns the letters added."""
    cmap = font.getBestCmap()
    glyphs = font.getGlyphSet()
    top = font["CFF "].cff.topDictIndex[0]
    cid = hasattr(top, "ROS")
    added = []
    for ch in letters:
        if ord(ch) in cmap:
            continue
        recipe = RECIPES.get(ch)
        if ch == "Đ" and ord("Ð") in cmap:  # Vietnamese D with stroke and Icelandic Eth are the same capital
            set_cmap(font, ch, cmap[ord("Ð")])
            added.append(ch)
            continue
        if recipe:
            if any(ord(c) not in cmap for c in recipe[:2] + recipe[3:]):
                continue
            base, mark = cmap[ord(recipe[0])], cmap[ord(recipe[1])]
            dx, dy = mark_shift(glyphs, cmap, recipe)
            parts = [(base, IDENTITY), (mark, (1, 0, 0, 1, dx, dy))]
            width = glyphs[base].width
        else:
            made = vietnamese(glyphs, cmap, ch)
            if not made:
                continue
            base, parts, width = made
        gid = font.getGlyphID(base)
        private = top.FDArray[top.FDSelect[gid]].Private if cid else top.Private
        pen = T2CharStringPen(None if width == private.defaultWidthX else width - private.nominalWidthX, glyphs)
        for part, m in parts:
            out = pen if m == IDENTITY else TransformPen(pen, m)
            if isinstance(part, str):
                glyphs[part].draw(out)
            else:
                for _, ops in part:
                    for op, args in ops:
                        getattr(out, op)(*args)
        name = f"cid{len(font.getGlyphOrder()):05d}"
        add_glyph(font, top, name, pen.getCharString(private=private, globalSubrs=top.CharStrings.globalSubrs),
                  top.FDSelect[gid] if cid else None, base, width)  # fmt: skip
        set_cmap(font, ch, name)
        added.append(ch)
    return added


def set_cmap(font: TTFont, ch: str, name: str) -> None:
    for table in font["cmap"].tables:
        if table.isUnicode():
            table.cmap[ord(ch)] = name


def add_glyph(font: TTFont, top, name: str, charstring, fd: int | None, like: str, width: int) -> None:
    """A new last glyph: its charstring, CID and font dict (fd None: not CID-keyed), and the metrics of the glyph it is
    drawn on with its own advance width."""
    cs = top.CharStrings
    cs.charStrings[name] = len(cs.charStringsIndex)
    cs.charStringsIndex.append(charstring)
    if fd is not None:
        top.FDSelect.gidArray.append(fd)
    order = font.getGlyphOrder() + [name]  # a new list: the CFF charset may be the font's glyph order list itself
    top.charset = order
    font.setGlyphOrder(order)
    font["hmtx"].metrics[name] = (width, font["hmtx"].metrics[like][1])
    if "vmtx" in font:
        font["vmtx"].metrics[name] = font["vmtx"].metrics[like]
    if "VORG" in font and like in font["VORG"].VOriginRecords:
        font["VORG"].VOriginRecords[name] = font["VORG"].VOriginRecords[like]


def read_font(font_dir: Path, name: str) -> bytes:
    """Font/<name>.bfotf(.zs) of the copy, packed as it is in the RomFS."""
    path = font_dir / f"{name}.bfotf.zs"
    return path.read_bytes() if path.exists() else zstd.compress((font_dir / f"{name}.bfotf").read_bytes())


def missing(font_dir: Path, text: str) -> dict[str, str]:
    """For each font, the letters of text it lacks (spaces and control characters aside)."""
    import io

    need = {c for c in text if c.isprintable() and not c.isspace()}
    out = {}
    for name in FONTS:
        font = TTFont(io.BytesIO(decrypt(zstd.decompress(read_font(font_dir, name)))), lazy=True)
        out[name] = "".join(sorted(c for c in need if ord(c) not in font.getBestCmap()))
    return out


def build(font_dir: Path, text: str, out: Path) -> list[str]:
    """The fonts lacking a letter of text, with it composed, into out/Font/; their overlay manifest lines. The letters
    no recipe covers are reported and left as the game draws them."""
    import io

    lines = []
    sha = hashlib.sha256
    tool = sha(Path(__file__).read_bytes()).hexdigest()[:16]
    for name, lack in missing(font_dir, text).items():
        if not lack:
            continue
        orig = read_font(font_dir, name)
        rel = f"Font/{name}.bfotf.zs"
        # the setup runs this every time (~6 s a font): the last result kept while the font, letters and tool match
        key = f"{sha(orig).hexdigest()} {lack} {tool}\n"
        key_path = out / f"{rel}.key"
        if (out / rel).is_file() and key_path.is_file() and key_path.read_text(encoding="utf-8") == key:
            data = (out / rel).read_bytes()
            lines.append(f"{rel}\t{len(data)}\t{sha(data).hexdigest()}\t{sha(orig).hexdigest()}")
            continue
        font = TTFont(io.BytesIO(decrypt(zstd.decompress(orig))))
        added = compose(font, lack)
        left = "".join(c for c in lack if c not in added)
        if left:
            print(f"{name}: no recipe for {left}", file=sys.stderr)
        if not added:
            continue
        buf = io.BytesIO()
        font.save(buf)
        data = zstd.compress(encrypt(buf.getvalue()))
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_bytes(data)
        key_path.write_text(key, encoding="utf-8")
        lines.append(f"{rel}\t{len(data)}\t{sha(data).hexdigest()}\t{sha(orig).hexdigest()}")
        print(f"{name}: {''.join(added)} composed", file=sys.stderr)
    return lines


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import game_texts

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("missing", "build"))
    ap.add_argument("lang", help="a translation in i18n/game/base, e.g. tr")
    ap.add_argument("-o", "--out", type=Path, help="build: the overlay folder (default build/lang/<lang>)")
    args = ap.parse_args()
    font_dir = game_texts.romfs_folder("Font")
    text = "".join(game_texts.read_translation(args.lang, 1 << 30).values())
    if args.cmd == "missing":
        for name, lack in missing(font_dir, text).items():
            print(f"{name}: {lack or '-'}")
        return 0
    out = args.out or game_texts.ROOT / "build" / "lang" / args.lang
    print("\n".join(build(font_dir, text, out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
