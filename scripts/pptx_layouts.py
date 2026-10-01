"""8 layout archetypes for lyric-card slides.

Self-contained rendering: shared chrome (background, section label, footer,
ghost text), the ruby+base+romaji+CN line block, cover, and a dispatcher that
maps an archetype id to a distinct composition. Consumed by build_pptx.py.
"""

import copy

from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE
from lxml import etree

from scripts.pptx_palette import rgb
from scripts.pptx_furigana import align_reading, plan_ruby, _has_kanji
from scripts.pptx_profile import GEOMETRY

# ── Geometry ─────────────────────────────────────────────────────────────────

SLIDE_W_EMU = int(Inches(GEOMETRY["slide_w_in"]))
SLIDE_H_EMU = int(Inches(GEOMETRY["slide_h_in"]))
RIGHT_SAFE_EMU = int(SLIDE_W_EMU * GEOMETRY["right_safe_fraction"])
LEFT_MARGIN_EMU = int(Inches(GEOMETRY["left_margin_in"]))
BOTTOM_MARGIN_EMU = int(Inches(GEOMETRY["bottom_margin_in"]))
CONTENT_W_EMU = RIGHT_SAFE_EMU - LEFT_MARGIN_EMU

TOP_Y = int(Inches(1.1))

# ── Typography ───────────────────────────────────────────────────────────────

FURIGANA_FS = 13.0
ROMAJI_FS = 20.0
CN_FS = 17.0
SECTION_FS = 14.0
FOOTER_FS = 9.0
ROMAJI_SPACING = 1.5

FURIGANA_GAP = int(Pt(1))
GAP_AFTER_BASE = int(Pt(14))
GAP_SPLIT = int(Pt(10))
GAP_LINES = int(Pt(56))

EMU_PER_PT = 12700


def _char_w_em(fs_pt: float) -> int:
    return int(fs_pt * EMU_PER_PT)


def _text_w_em(text: str, fs_pt: float) -> int:
    return len(text) * _char_w_em(fs_pt)


# ── Font sizing ──────────────────────────────────────────────────────────────

def jp_font_size(char_count: int) -> int:
    if char_count <= 7:
        return 64
    if char_count <= 12:
        return 60
    if char_count <= 16:
        return 56
    return 52


def reduce_tier(fs: int) -> int:
    if fs >= 64:
        return 60
    if fs >= 60:
        return 56
    if fs >= 56:
        return 52
    return 48


# ── Line resolution (tokenize + font size + split) ───────────────────────────

def _find_split_pos(text: str, units: list) -> int:
    half = len(text) // 2
    MIN_SIDE = 5
    search = min(5, len(text) // 3)
    boundaries = {}
    char_pos = 0
    for u in units:
        char_pos += len(u["base"])
        boundaries[char_pos] = not u["ruby"]
    for particle in ["を", "は", "が", "に", "で", "の", "も", "へ", "と"]:
        idx = 0
        while True:
            idx = text.find(particle, idx)
            if idx == -1:
                break
            boundaries.setdefault(idx + len(particle), True)
            idx += 1
    for punct in ["、", "。", "！", "？", "…", "〜", "～"]:
        idx = 0
        while True:
            idx = text.find(punct, idx)
            if idx == -1:
                break
            boundaries.setdefault(idx + len(punct), True)
            idx += 1

    def _score(pos, is_kana, dist):
        left, right = pos, len(text) - pos
        if left < MIN_SIDE or right < MIN_SIDE:
            return -1
        return (2 if is_kana else 1) * (search - dist + 1)

    best_pos, best_score = None, -1
    for pos, is_kana in boundaries.items():
        dist = abs(pos - half)
        if dist <= search:
            s = _score(pos, is_kana, dist)
            if s > best_score:
                best_score, best_pos = s, pos
    if best_pos is not None:
        return best_pos
    best_any, best_dist = None, len(text)
    for pos in boundaries:
        dist = abs(pos - half)
        if dist < best_dist:
            best_dist, best_pos = dist, pos
    return best_pos or half


def _split_units(units: list) -> list:
    full_text = "".join(u["base"] for u in units)
    split_at = _find_split_pos(full_text, units)
    left, right = [], []
    acc = 0
    for u in units:
        n = len(u["base"])
        if acc < split_at:
            if acc + n <= split_at:
                left.append(u)
            else:
                k = split_at - acc
                lpart, rpart = u["base"][:k], u["base"][k:]
                if lpart:
                    left.append({"base": lpart, "ruby": u["ruby"] if _has_kanji(lpart) else ""})
                if rpart:
                    right.append({"base": rpart, "ruby": u["ruby"] if _has_kanji(rpart) else ""})
            acc += n
        else:
            right.append(u)
    return [x for x in (left, right) if x] or [units]


def resolve_line(jp: str, romaji: str = None, is_paired: bool = False,
                 size_boost: float = 1.0):
    """Return (list_of_sub_units, list_of_font_sizes) for one lyric line."""
    units = align_reading(jp, romaji)
    full_text = "".join(u["base"] for u in units)
    cc = len(full_text)
    fs = int(jp_font_size(cc) * size_boost)

    needs_split = cc >= 18
    if not needs_split and _text_w_em(full_text, fs) > CONTENT_W_EMU:
        needs_split = True

    if needs_split:
        sub_lists = _split_units(units)
        font_sizes = []
        for st in sub_lists:
            st_text = "".join(u["base"] for u in st)
            st_fs = min(int(jp_font_size(len(st_text)) * size_boost), fs)
            while st_fs > 40 and _text_w_em(st_text, st_fs) > CONTENT_W_EMU:
                st_fs -= 4
            font_sizes.append(st_fs)
    else:
        sub_lists = [units]
        while fs > 40 and _text_w_em(full_text, fs) > CONTENT_W_EMU:
            fs -= 4
        font_sizes = [fs]

    if is_paired:
        font_sizes = [reduce_tier(f) for f in font_sizes]
    return sub_lists, font_sizes


def estimate_line_height(sub_lists: list, font_sizes: list) -> int:
    furi_h = int(Pt(FURIGANA_FS + 2))
    total = 0
    for i, (st, fs) in enumerate(zip(sub_lists, font_sizes)):
        total += furi_h + FURIGANA_GAP + int(Pt(fs + 8))
        if i < len(sub_lists) - 1:
            total += GAP_SPLIT
    total += GAP_AFTER_BASE
    total += int(Pt(ROMAJI_FS + 6))
    total += int(Pt(2))
    total += int(Pt(CN_FS + 6))
    return total


# ── Low-level run/font helpers ───────────────────────────────────────────────

_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def _set_cjk_font(run, cjk: str, latin: str = "Arial"):
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(f"{_NS}ea")
    if ea is None:
        ea = etree.SubElement(rPr, f"{_NS}ea")
    ea.set("typeface", cjk)
    run.font.name = latin


def _add_run(p, text, cjk, latin="Arial", size=Pt(14), color=None):
    run = p.add_run()
    run.text = text
    run.font.size = size
    if color:
        run.font.color.rgb = rgb(color)
    _set_cjk_font(run, cjk, latin)
    return run


def _set_char_spacing(run, spacing_pt: float):
    rPr = run._r.get_or_add_rPr()
    spc = etree.SubElement(rPr, f"{_NS}spc")
    spc.set("val", str(int(spacing_pt * 100)))


def _darken_hex(hex_str: str, frac: float) -> str:
    r = int(hex_str[0:2], 16)
    g = int(hex_str[2:4], 16)
    b = int(hex_str[4:6], 16)
    return f"{int(r * (1 - frac)):02x}{int(g * (1 - frac)):02x}{int(b * (1 - frac)):02x}"


# ── Chrome ───────────────────────────────────────────────────────────────────

def add_background(slide, bg_buf):
    bg_buf.seek(0)
    slide.shapes.add_picture(bg_buf, 0, 0, SLIDE_W_EMU, SLIDE_H_EMU)


def add_section_label(slide, text, palette, fonts):
    tf = slide.shapes.add_textbox(int(Inches(0.4)), int(Pt(16)), int(Inches(4)), int(Pt(24)))
    tf.text_frame.word_wrap = True
    _add_run(tf.text_frame.paragraphs[0], text, fonts["jp"], fonts["romaji"],
             size=Pt(SECTION_FS), color=palette["TEXT_SECTION"])


def add_footer(slide, text, palette, fonts):
    tf = slide.shapes.add_textbox(
        LEFT_MARGIN_EMU, SLIDE_H_EMU - int(Pt(10)) - int(Pt(18)),
        RIGHT_SAFE_EMU - LEFT_MARGIN_EMU, int(Pt(18)))
    tf.text_frame.word_wrap = False
    p = tf.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.RIGHT
    _add_run(p, text, fonts["cn"], fonts["romaji"], size=Pt(FOOTER_FS),
             color=palette["TEXT_FOOTER"])


def add_ghost_text(slide, text, profile):
    """Giant watermark of the section name, bottom-right, bg-darkened."""
    if not text:
        return
    color = _darken_hex(profile["bg"], 0.10)
    n = len(text)
    if n <= 4:
        fs = 120.0
    elif n <= 10:
        fs = 96.0
    else:
        fs = 72.0
    w = _text_w_em(text, fs)
    h = int(Pt(fs + 12))
    x = SLIDE_W_EMU - w - int(Inches(0.3))
    y = SLIDE_H_EMU - BOTTOM_MARGIN_EMU - h
    x = max(int(Inches(0.3)), x)
    tf = slide.shapes.add_textbox(x, y, w, h)
    tf.text_frame.word_wrap = False
    p = tf.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.RIGHT
    _add_run(p, text, profile["font"]["jp"], profile["font"]["romaji"],
             size=Pt(fs), color=color)


def add_accent_rule(slide, x, y, w, palette):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, int(Pt(1.2)))
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(palette["ACCENT"])
    shape.line.fill.background()
    return shape


# ── Lyric line block ─────────────────────────────────────────────────────────

def render_line_block(slide, units, base_fs, romaji, cn, x_origin, y,
                      palette, fonts, align="left", with_annotations=True,
                      bold=False, tracking=0.0):
    """Render ruby + base + romaji + CN for one line. Returns y after block.

    align: "left" | "center" | "right" — positions the base text via x_origin,
    and controls the romaji/CN textbox alignment + span so nothing overruns
    the slide's right safe edge.
    """
    base_text = "".join(u["base"] for u in units)
    ruby_fs, placements, drop = plan_ruby(units, base_fs, CONTENT_W_EMU,
                                          ruby_start_pt=FURIGANA_FS)

    furi_h = int(Pt(FURIGANA_FS + 2))
    if not drop:
        for p in placements:
            tf = slide.shapes.add_textbox(x_origin + p["x"], y, p["w"], furi_h)
            tf.text_frame.word_wrap = False
            tf.text_frame.margin_left = 0
            tf.text_frame.margin_right = 0
            para = tf.text_frame.paragraphs[0]
            para.alignment = PP_ALIGN.CENTER
            _add_run(para, p["text"], fonts["furigana"], fonts["romaji"],
                     size=Pt(ruby_fs), color=palette["TEXT_FURIGANA"])

    base_y = y if drop else y + furi_h + FURIGANA_GAP
    base_h = int(Pt(base_fs + 8))
    base_w = min(_text_w_em(base_text, base_fs) + int(Pt(6)), CONTENT_W_EMU)
    tf = slide.shapes.add_textbox(x_origin, base_y, base_w, base_h)
    tf.text_frame.word_wrap = False
    para = tf.text_frame.paragraphs[0]
    para.alignment = PP_ALIGN.LEFT
    run = _add_run(para, base_text, fonts["jp"], fonts["romaji"],
                   size=Pt(base_fs), color=palette["TEXT_JP"])
    if bold:
        run.font.bold = True
    if tracking:
        _set_char_spacing(run, tracking)
    y = base_y + base_h + GAP_AFTER_BASE

    if not with_annotations:
        return y
    return render_annotations(slide, romaji, cn, x_origin, y, palette, fonts, align)


def render_annotations(slide, romaji, cn, x_origin, y, palette, fonts, align="left"):
    """Render romaji + CN once for a whole logical line. Returns y after.

    Split out so a line broken into N sub-lines renders its annotations exactly
    once (the phrase-grouping fix), regardless of how many base sub-lines exist.
    """
    if align == "center":
        ann_x, ann_w, ann_align = 0, SLIDE_W_EMU, PP_ALIGN.CENTER
    elif align == "right":
        ann_x, ann_w, ann_align = 0, RIGHT_SAFE_EMU, PP_ALIGN.RIGHT
    else:
        ann_x, ann_w, ann_align = x_origin, RIGHT_SAFE_EMU - x_origin, PP_ALIGN.LEFT

    ro_h = int(Pt(ROMAJI_FS + 6))
    tf_ro = slide.shapes.add_textbox(ann_x, y, ann_w, ro_h)
    tf_ro.text_frame.word_wrap = True
    pr = tf_ro.text_frame.paragraphs[0]
    pr.alignment = ann_align
    run = _add_run(pr, romaji, fonts["romaji"], fonts["romaji"],
                   size=Pt(ROMAJI_FS), color=palette["TEXT_ROMAJI"])
    _set_char_spacing(run, ROMAJI_SPACING)
    y += ro_h + int(Pt(2))

    cn_h = int(Pt(CN_FS + 6))
    tf_cn = slide.shapes.add_textbox(ann_x, y, ann_w, cn_h)
    tf_cn.text_frame.word_wrap = True
    pc = tf_cn.text_frame.paragraphs[0]
    pc.alignment = ann_align
    _add_run(pc, cn, fonts["cn"], fonts["romaji"], size=Pt(CN_FS),
             color=palette["TEXT_CN"])
    return y + cn_h


def render_line_full(slide, sub_lists, font_sizes, romaji, cn, y, palette, fonts,
                     align="left", x_override=None, with_annotations=True,
                     bold=False, tracking=0.0):
    """Render one logical line: all split sub-lines' base, then one romaji+cn.

    Each sub-line gets its own x via _x_for_alignment (or x_override for
    indented layouts). Annotations are emitted once at the end.
    """
    for st, fs in zip(sub_lists, font_sizes):
        base_text = "".join(u["base"] for u in st)
        x = x_override if x_override is not None else _x_for_alignment(base_text, fs, align)
        y = render_line_block(slide, st, fs, romaji, cn, x, y, palette, fonts,
                              align, with_annotations=False, bold=bold, tracking=tracking)
    if with_annotations:
        ann_origin = x_override if x_override is not None else (
            LEFT_MARGIN_EMU if align == "left" else 0)
        y = render_annotations(slide, romaji, cn, ann_origin, y, palette, fonts, align)
    return y


# ── Visual anchors ─────────────────────────────────────────────────────────────

def add_vertical_rule(slide, x, y, h, palette, width_pt=1.2):
    """Thin amber vertical hairline anchor."""
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, int(Pt(width_pt)), h)
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(palette["ACCENT"])
    shape.line.fill.background()
    return shape


def add_number_anchor(slide, number, x, y, palette, fonts, size=110):
    """Large editorial number (01/02…) as a quiet left-side anchor."""
    tf = slide.shapes.add_textbox(x, y, int(Pt(size + 40)), int(Pt(size + 12)))
    tf.text_frame.word_wrap = False
    p = tf.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    _add_run(p, number, fonts["romaji"], fonts["romaji"], size=Pt(size),
             color=palette.get("TEXT_SECTION", "B0A89E"))
    return tf


def add_giant_kanji(slide, text, x, y, palette, fonts, fs=200, color=None):
    """Giant background kanji watermark from a lyric keyword."""
    if not text:
        return None
    if color is None:
        color = palette.get("TEXT_SECTION", "B0A89E")
    w = _text_w_em(text, fs)
    h = int(Pt(fs + 12))
    tf = slide.shapes.add_textbox(x, y, w, h)
    tf.text_frame.word_wrap = False
    p = tf.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    _add_run(p, text, fonts["jp"], fonts["romaji"], size=Pt(fs), color=color)
    return tf


def add_circle(slide, x, y, d, palette, filled=False):
    """Outline (or filled) circle anchor."""
    shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, x, y, d, d)
    if filled:
        shape.fill.solid()
        shape.fill.fore_color.rgb = rgb(palette["ACCENT"])
        shape.line.fill.background()
    else:
        shape.fill.background()
        shape.line.color.rgb = rgb(palette["ACCENT"])
        shape.line.width = Pt(1.5)
    return shape


def add_brush_stroke(slide, x, y, length, palette, angle=-25, width_pt=14,
                     color=None, tint_white=0.0):
    """A short thick diagonal brushstroke — painting, not geometry.

    Rounded-corner rectangle rotated off-axis; soft rounded ends read as a
    single loaded brushstroke rather than a clean rule. ``tint_white`` lightens
    the accent toward white (0=full accent, 1=white) so strokes can sit near
    text without killing legibility, or stay saturated at the margins.
    """
    color = color or palette["ACCENT"]
    if tint_white:
        color = _mix_hex(color, "FFFFFF", tint_white)
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y,
                                   length, int(Pt(width_pt)))
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(color)
    shape.line.fill.background()
    shape.rotation = angle
    try:
        shape.adjustments[0] = 0.45
    except Exception:
        pass
    return shape


def add_smudge(slide, x, y, d, palette, color=None, tint_white=0.35):
    """Soft filled color patch — a '涂抹/晕开' mark, not a hard disc.

    Filled oval shifted toward white so it reads as a watercolor bloom at the
    paper's edge rather than a solid dot.
    """
    color = color or palette["ACCENT"]
    color = _mix_hex(color, "FFFFFF", tint_white)
    shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, x, y, d, d)
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(color)
    shape.line.fill.background()
    return shape


def add_upward_sweep(slide, palette, accent=None, count=3, base_x_in=1.0,
                     base_y_in=6.0, step_x_in=2.3, step_y_in=0.6, angle=-30,
                     length_in=1.6):
    """Rising brushstroke cluster — the '向上扫出' forward-momentum gesture.

    Each stroke sits higher and further right than the last, so the eye travels
    bottom-left → top-right (向前/奔跑). Bottom-edge placement keeps it a
    momentum cue under the lyric, not a competing block.
    """
    color = accent or palette["ACCENT"]
    for i in range(count):
        x = int(Inches(base_x_in + i * step_x_in))
        y = int(Inches(base_y_in - i * step_y_in))
        length = int(Inches(length_in + 0.4 * (i % 2)))
        add_brush_stroke(slide, x, y, length, palette, angle=angle,
                         width_pt=max(6, 13 - 3 * i), color=color,
                         tint_white=0.12 * i)
    return None


def add_diagonal_slash(slide, x, y, length, palette, width_pt=1.5, angle=-35):
    """Sharp diagonal slash anchor — knife/gun imagery, not the calm circle.

    A thin rectangle rotated off-axis, so the shape_type stays AUTO_SHAPE and
    the auto visual review still counts it as a real anchor.
    """
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, length, int(Pt(width_pt)))
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(palette["ACCENT"])
    shape.line.fill.background()
    shape.rotation = angle
    return shape


def add_diagonal_span(slide, palette, length_in=17.0, width_pt=3.0, angle=-28,
                      x_off=0.0, y_off=0.0, tint_hex=None):
    """Full-page diagonal color block — a compositional cut, not a corner accent.

    A rotated rectangle whose length/angle/width/offset are set by the section's
    emotion (via its ``slash`` spec), so the same slash motif reads as a short
    shallow tremor in a verse and a long thick knife-cut in the climax. Drawn
    before the text so transparent textboxes let it cut through the layout.
    ``tint_hex`` softens the accent toward that color (e.g. white on light pages)
    so the cut stays visible without eating lyric legibility.
    """
    color = palette["ACCENT"]
    if tint_hex:
        color = _mix_hex(color, tint_hex, 0.45)
    length = int(Inches(length_in))
    h = int(Pt(width_pt))
    x = (SLIDE_W_EMU - length) // 2 + int(Inches(x_off))
    y = (SLIDE_H_EMU - h) // 2 + int(Inches(y_off))
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, length, h)
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(color)
    shape.line.fill.background()
    shape.rotation = angle
    return shape


def _x_for_alignment(base_text: str, base_fs: float, align: str) -> int:
    w = _text_w_em(base_text, base_fs)
    if align == "center":
        return (SLIDE_W_EMU - w) // 2
    if align == "right":
        return RIGHT_SAFE_EMU - w
    return LEFT_MARGIN_EMU


# ── Archetype dispatcher ─────────────────────────────────────────────────────

def _mix_hex(a: str, b: str, t: float) -> str:
    t = max(0.0, min(1.0, t))
    ra, ga, ba = int(a[0:2], 16), int(a[2:4], 16), int(a[4:6], 16)
    rb, gb, bb = int(b[0:2], 16), int(b[2:4], 16), int(b[4:6], 16)
    return (f"{int(ra + (rb - ra) * t):02x}"
            f"{int(ga + (gb - ga) * t):02x}"
            f"{int(ba + (bb - ba) * t):02x}")


def _section_paper(warmth: float) -> tuple[str, str]:
    """Light-page paper gradient: cool-neutral → warm cream as warmth rises."""
    return _mix_hex("EEF0F1", "F7F1E4", warmth), _mix_hex("E2E6EA", "EDE7DA", warmth)


def _line_gap(density: float = 0.55) -> int:
    """Inter-line gap, tightened as density rises (less whitespace for busy songs)."""
    base = GAP_LINES - GAP_AFTER_BASE
    scale = 1.0 - 1.0 * max(0.0, min(1.0, density - 0.55))
    return int(base * scale)


def _page_gap(density: float, energy: float) -> int:
    """Inter-line gap, tightened further as a *page's* energy rises (chorus crowds)."""
    base = _line_gap(density)
    scale = 1.0 - 0.30 * max(0.0, energy - 0.3)
    return int(base * scale)


def _centered_y(resolved, extra_gap=0, gap=None) -> int:
    if gap is None:
        gap = _line_gap()
    h = sum(estimate_line_height(sub, fss) for sub, fss in resolved)
    if len(resolved) > 1:
        h += (len(resolved) - 1) * gap
    h += extra_gap
    return max(int(Inches(1.1)), (SLIDE_H_EMU - h) // 2)


def _block_height(resolved, gap) -> int:
    h = sum(estimate_line_height(sub, fss) for sub, fss in resolved)
    if len(resolved) > 1:
        h += (len(resolved) - 1) * gap
    return h


def _fit_centered(resolved, gap, top, bottom):
    """Center a resolved lyric block in [top, bottom]; shrink tiers if it won't fit.

    Returns (start_y, possibly_shrunk_resolved). reduce_tier floors at 48pt, so
    a two-line page that splits into several sub-lines keeps shrinking until its
    romaji/CN annotations clear the slide's safe bottom instead of running off
    the canvas edge.
    """
    avail = bottom - top
    cur = [(sub, list(fss)) for sub, fss in resolved]
    for _ in range(6):
        if _block_height(cur, gap) <= avail:
            break
        nxt = [(sub, [reduce_tier(f) for f in fss]) for sub, fss in cur]
        if _block_height(nxt, gap) >= _block_height(cur, gap):
            break  # reduce_tier hit its floor — nothing left to shrink
        cur = nxt
    return top + (avail - _block_height(cur, gap)) // 2, cur


# ── Page Composition Intent (intra-section page variation) ────────────────────
#
# Section keeps deciding identity (palette / typography / density / base
# visual_assets / energy range); page intent only shapes the *local* composition
# of one page within that section. role shifts the text block (anchor/align/gap/
# size/bold); relationship reshapes the motif geometry around the estimated text
# zone. Every change is a deterministic function of the director's per-page
# intent — never random, never an archetype rotation.

_NATURAL_ALIGN = {"L1": "left", "L2": "center", "L3": "right", "L4": "left",
                  "L5": "left", "L6": "center", "L7": "center", "L8": "center"}
_NATURAL_ANCHOR = {"L1": "top", "L2": "center", "L3": "center", "L4": "fit",
                   "L5": "top", "L6": "center", "L7": "center", "L8": "bottom"}
# Full-canvas substrate (paper_grain) must never be reshaped by a relationship —
# it has no geometry and recedes/fades would lighten the whole paper, not the
# brushwork.
_PAPER_SUBSTRATE = {"paper_grain"}


def _role_deltas(role, arch, energy):
    """Text-side deltas for a page role (relative to the arch's defaults).

    'inherit' for anchor/align means "keep the archetype's natural value"; the
    resolver below turns that into a concrete string. gap_scale/size_scale are
    multiplicative, bold is an override on top of the aggressive-song default.
    """
    d = {"anchor": "inherit", "align": "inherit", "gap_scale": 1.0,
         "size_scale": 1.0, "bold": False}
    if role == "continue":
        d["gap_scale"] = 0.95
    elif role == "build":
        d["gap_scale"] = 0.90
        d["size_scale"] = 1.05
        d["bold"] = energy >= 0.6
    elif role == "pause":
        d["anchor"] = "center"
        d["gap_scale"] = 1.12
        d["size_scale"] = 0.98
    elif role == "contrast":
        d["align"] = "flip"
        d["size_scale"] = 1.02
    elif role == "resolve":
        d["anchor"] = "center"
        d["align"] = "center"
        d["gap_scale"] = 1.05
    elif role == "peak":
        d["anchor"] = "center"
        d["align"] = "center"
        d["gap_scale"] = 0.85
        d["size_scale"] = 1.10
        d["bold"] = True
    return d


def _resolve_align(arch, delta_align):
    if delta_align == "center":
        return "center"
    if delta_align == "flip":
        nat = _NATURAL_ALIGN.get(arch, "left")
        return "right" if nat == "left" else "left"
    return _NATURAL_ALIGN.get(arch, "left")


def _resolve_anchor(arch, delta_anchor):
    if delta_anchor == "center":
        return "center"
    return _NATURAL_ANCHOR.get(arch, "top")


def _anchor_start_y(resolved, anchor, style):
    """Vertical start y for a resolved block under top/center/bottom anchor.

    'fit' is handled by the callers that need tier-shrinking (L4/L6); the
    plain branches here cover top/center/bottom for the rest.
    """
    gap = style["gap"]
    usable_bottom = SLIDE_H_EMU - BOTTOM_MARGIN_EMU
    if anchor == "bottom":
        h = _block_height(resolved, gap)
        return max(int(Inches(1.1)), usable_bottom - h - int(Inches(0.4)))
    if anchor == "top":
        return TOP_Y
    return _centered_y(resolved, gap=gap)


def _estimate_text_zone(arch, resolved, style):
    """Bounding box of the rendered lyric block, normalized to (cx, cy, w, h) 0–1.

    Drives the relationship transform so a motif can be grounded under, led
    toward, wrapped around, or cut across the actual text — not a fixed canvas
    point. Computed from the same pure helpers the archetypes use to place text.
    """
    gap = style["gap"]
    total_h = _block_height(resolved, gap)
    max_w = 0
    for sub, fss in resolved:
        for st, fs in zip(sub, fss):
            w = _text_w_em("".join(u["base"] for u in st), fs) + int(Pt(6))
            max_w = max(max_w, w)
    align = style.get("align", "left")
    if align == "center":
        cx = SLIDE_W_EMU / 2
    elif align == "right":
        cx = RIGHT_SAFE_EMU - max_w / 2
    else:
        cx = LEFT_MARGIN_EMU + max_w / 2
    anchor = style.get("anchor", "center")
    cy = _anchor_start_y(resolved, anchor, style) + total_h / 2
    return (cx / SLIDE_W_EMU, cy / SLIDE_H_EMU,
            max_w / SLIDE_W_EMU, total_h / SLIDE_H_EMU)


def _relationship_transform(spec, relationship, text_zone):
    """Reshape one motif spec by its relationship to the text (deep copy).

    The seven relationships are semantic: recede pushes the stroke into the
    background, support grounds it under the text, lead aims it at the text
    entrance, cross lets the text sit on a full-width band, frame wraps it,
    divide pushes it to the opposite side, expand grows it outward from the
    text. paper_grain is skipped (full-canvas substrate, no geometry).
    """
    s = copy.deepcopy(spec)
    if s.get("type") in _PAPER_SUBSTRATE:
        return s
    cx, cy, tw, th = text_zone
    if relationship == "recede":
        s["opacity"] = round(s.get("opacity", 1.0) * 0.70, 2)
        s["blur"] = round(s.get("blur", 0.0) + 0.15, 2)
    elif relationship == "support":
        s["y"] = round(min(1.0, cy + th * 0.6), 2)
    elif relationship == "lead":
        s["angle"] = round(s.get("angle", 0.0) - 25.0, 2)
        s["x"] = round(max(0.0, cx - 0.15), 2)
        s["y"] = round(max(0.0, cy - 0.10), 2)
    elif relationship == "cross":
        s["width"] = round(max(0.9, s.get("width", 0.5)), 2)
        s["opacity"] = round(min(0.5, s.get("opacity", 1.0)), 2)
        s["y"] = round(cy, 2)
    elif relationship == "frame":
        s["width"] = round(min(1.0, max(s.get("width", 0.4), tw) * 1.15), 2)
        s["height"] = round(min(1.0, max(s.get("height", 0.1), th) * 1.15), 2)
        s["opacity"] = round(s.get("opacity", 1.0) * 0.80, 2)
        s["x"] = round(cx, 2)
        s["y"] = round(cy, 2)
    elif relationship == "divide":
        s["x"] = round(0.18 if cx >= 0.5 else 0.82, 2)
    elif relationship == "expand":
        s["width"] = round(min(1.0, s.get("width", 0.4) * 1.25), 2)
        s["height"] = round(min(1.0, s.get("height", 0.1) * 1.25), 2)
        s["x"] = round(cx, 2)
        s["y"] = round(cy, 2)
    return s


def _has(motifs, key) -> bool:
    return key in (motifs or [])


def render_archetype(slide, arch_id, jp_lines, profile, section_name,
                     page_num, total_pages, dark=False, brightness=None,
                     motifs=None, keywords=None, seed=42, energy=0.5, slash=None,
                     page_specs_override=None, page_intent=None):
    """Render a page using one of 8 archetypes. jp_lines: [[jp, romaji, cn], ...]

    dark switches palette + background to the emotional inversion point.
    energy is the *page* energy from emotionalCurve — it drives weight/tracking/
    size/line-gap, so the curve shapes each page, not just whether a dark
    inversion appears. ``slash`` is the per-section diagonal-cut spec from the
    same emotionalCurve entry; only sections whose director wrote one get the
    cut (a punctuation mark, never a page watermark). motifs gate the other
    decorative anchors (circle / vertical_rule / number / giant_kanji) — an
    anchor only renders if the director put that motif in visualMotifs for a
    semantic/compositional reason. ``page_intent`` is the director's per-page
    {role, relationship} from visual_assets.pageIntents (None for old songs):
    role shifts the text block, relationship reshapes the motif geometry.
    """
    from scripts.pptx_background import generate_section_background, compose_section_background
    from scripts.pptx_profile import resolve_page_specs

    palette = profile["dark_palette"] if dark else profile["palette"]
    fonts = profile["font"]
    motifs = motifs or []
    keywords = keywords or profile.get("keywords", [])

    # Procedural engine: when the director wrote visual_assets, decoration comes
    # from the composited motif specs baked into the background PNG, and the
    # native-shape anchors (brush/smudge/rule/circle/number/giant_kanji) are all
    # suppressed — their role is replaced by the engine's raster motifs.
    assets = profile.get("visual_assets")
    use_engine = bool(assets and (assets.get("base") or assets.get("sections")))
    if use_engine:
        motifs = []
    ts = profile.get("type_spec", {})
    aggressive = ts.get("aggressive", False)

    # per-page style: emotionalCurve's energy + typographyDirection together set
    # bold/tracking/size-span/line-gap, so aggressive songs get heavier, tighter,
    # bigger, denser pages as energy climbs — a chorus visibly crowds in on a
    # verse rather than every page holding the same "restrained" posture.
    dyn = profile.get("dynamicRange", 0.3)
    accent_presence = profile.get("accentPresence", 0.0)
    accent = palette["ACCENT"]

    # Page Composition Intent: role (text-side deltas) + relationship (motif
    # geometry). Old songs pass page_intent=None → all-inherit, no transform.
    intent = page_intent or {}
    role = intent.get("role") or "introduce"
    relationship = intent.get("relationship") or None
    deltas = _role_deltas(role, arch_id, energy)

    # size_boost widens the font-size contrast as dynamicRange rises: a front
    # verse holds near the base size while a final chorus visibly expands. Calm
    # songs (dyn≈0.3) keep the old near-flat size; expressive songs (群青) push
    # the climax up ~15–20% without touching the quiet opening. The role's
    # size_scale then adds the intra-section step on top of that arc.
    size_boost = 1.0 + dyn * 0.45 * max(0.0, energy - 0.30)
    if aggressive:
        size_boost = max(size_boost, 1.0 + 0.22 * max(0.0, energy - 0.35))
    size_boost *= deltas["size_scale"]

    base_gap = (_page_gap(profile.get("density", 0.55), energy) if aggressive
                else _line_gap(profile.get("density", 0.55)))
    style = {
        "aggressive": aggressive,
        "bold": (aggressive and (ts.get("bold", False) or energy >= 0.6)) or deltas["bold"],
        "tracking": (ts.get("tracking", 0.0) if (aggressive and energy >= 0.7)
                     else (-0.4 if energy >= 0.75 else 0.0)),
        "gap": int(base_gap * deltas["gap_scale"]),
        "size_boost": size_boost,
        "accent_presence": accent_presence,
        "align": _resolve_align(arch_id, deltas["align"]),
        "anchor": _resolve_anchor(arch_id, deltas["anchor"]),
    }

    # brightness follows the curve: dynamicRange widens the light/dark swing so
    # a front verse stays dim/cold and a final chorus opens up toward glow.
    if brightness is None:
        if dark:
            brightness = 1.0
        elif aggressive:
            brightness = 0.90 + 0.20 * energy
        else:
            brightness = (0.92 - 0.10 * dyn) + 0.24 * dyn * energy

    if dark:
        left_hex, right_hex = "1C1E1F", "26282D"
    else:
        base_left, base_right = _section_paper(profile.get("warmth", 0.4))
        # accentPresence lets the accent color enter the paper itself (群青蓝 into
        # the page), not just sit as a thin rule — a song with real color presence
        # gets a blue-tinted paper, a calm one stays near-neutral.
        left_hex = _mix_hex(base_left, accent, accent_presence * 0.35)
        right_hex = _mix_hex(base_right, accent, accent_presence * 0.20)
    texture = 0.3 + 0.5 * min(1.0, profile.get("density", 0.55))

    # Resolve the lyric lines BEFORE the background so the page intent can size
    # the text, estimate its zone, and reshape the motif geometry around it.
    is_paired = len(jp_lines) == 2
    usable_bottom = SLIDE_H_EMU - BOTTOM_MARGIN_EMU
    sb = style["size_boost"]
    resolved = [resolve_line(jp, romaji, is_paired, size_boost=sb)
                for (jp, romaji, _c) in jp_lines]

    # In engine mode the motif geometry is reshaped by the page's relationship
    # around the estimated text zone. A nudged override (critic rework) is
    # already-final and used as-is so the transform isn't applied twice.
    if use_engine:
        text_zone = _estimate_text_zone(arch_id, resolved, style)
        if page_specs_override is not None:
            page_specs = page_specs_override
        else:
            raw_specs = resolve_page_specs(assets, section_name)
            if relationship:
                page_specs = [_relationship_transform(s, relationship, text_zone)
                              for s in raw_specs]
            else:
                page_specs = raw_specs
    else:
        page_specs = []

    # rising accent light band: the accent climbs through the background as the
    # page's energy rises, so the color lives in the main visual layer, not the
    # margins. In engine mode this sweep is replaced by the director's explicit
    # light_band/gradient_field motifs in visual_assets.
    tint_hex = accent if (not dark and accent_presence > 0.05) else None
    tint_strength = accent_presence * (0.30 + 0.55 * energy)
    if use_engine:
        bg_buf = compose_section_background(
            specs=page_specs, left_hex=left_hex, right_hex=right_hex,
            brightness=brightness, dark=dark, seed=seed)
    else:
        bg_buf = generate_section_background(
            seed=seed, left_hex=left_hex, right_hex=right_hex,
            brightness=brightness, dark=dark, texture_strength=texture,
            tint_hex=tint_hex, tint_strength=tint_strength)
    add_background(slide, bg_buf)

    # per-section diagonal cut — drawn under all chrome/text so the lyric block
    # reads through it. Only where the director wrote a ``slash`` spec for this
    # section (aggressive songs), so it punctuates key moments instead of
    # wallpapering every page. Suppressed in engine mode (a motif covers it).
    if aggressive and slash and not use_engine:
        add_diagonal_span(slide, palette,
                          length_in=slash.get("length", 17.0),
                          width_pt=slash.get("width", 3.0),
                          angle=slash.get("angle", -28),
                          x_off=slash.get("x", 0.0),
                          y_off=slash.get("y", 0.0),
                          tint_hex=("FFFFFF" if not dark else None))

    add_section_label(slide, section_name, palette, fonts)
    footer = f"{profile['title']}  ·  {profile['artist']}  —  {page_num} / {total_pages}"
    add_footer(slide, footer, palette, fonts)

    if arch_id == "L6":
        _arch_ghost_full(slide, jp_lines, resolved, palette, fonts, keywords, motifs, style)
    elif arch_id == "L7":
        _arch_framed_quote(slide, jp_lines, resolved, palette, fonts, style)
    elif arch_id == "L8":
        _arch_outro_fade(slide, jp_lines, resolved, palette, fonts, usable_bottom, motifs, style)
    elif arch_id == "L2":
        _arch_centered_title(slide, jp_lines, resolved, palette, fonts, is_paired, motifs, style)
    elif arch_id == "L3":
        _arch_asymmetric_right(slide, jp_lines, resolved, palette, fonts, is_paired, motifs, style)
    elif arch_id == "L4":
        _arch_indent_dropcap(slide, jp_lines, resolved, palette, fonts, page_num, is_paired, motifs, style)
    elif arch_id == "L5":
        _arch_two_column(slide, jp_lines, resolved, palette, fonts, is_paired, motifs, style)
    else:
        _arch_editorial_left(slide, jp_lines, resolved, palette, fonts, page_num, is_paired, motifs, style)
    return page_specs


def _arch_editorial_left(slide, jp_lines, resolved, palette, fonts, page_num, is_paired, motifs, style):
    if _has(motifs, "vertical_rule"):
        add_vertical_rule(slide, int(Inches(0.35)), int(Inches(1.15)), int(Inches(4.0)), palette)
    elif _has(motifs, "brush_stroke"):
        add_brush_stroke(slide, int(Inches(0.4)), int(Inches(1.0)), int(Inches(1.9)),
                         palette, angle=-24, width_pt=12)
    elif _has(motifs, "smudge"):
        add_smudge(slide, int(Inches(0.5)), int(Inches(1.0)), int(Inches(1.3)), palette)
    if _has(motifs, "diagonal_slash") and not style["aggressive"]:
        add_diagonal_slash(slide, int(Inches(0.3)), int(Inches(1.0)), int(Inches(1.4)), palette)
    if _has(motifs, "number"):
        add_number_anchor(slide, f"{page_num:02d}", int(Inches(0.5)), int(Inches(1.0)),
                          palette, fonts, size=44)
    y = _anchor_start_y(resolved, style["anchor"], style)
    for i, ((jp, romaji, cn), (sub, fss)) in enumerate(zip(jp_lines, resolved)):
        y = render_line_full(slide, sub, fss, romaji, cn, y, palette, fonts, style["align"],
                             bold=style["bold"], tracking=style["tracking"])
        if i < len(jp_lines) - 1:
            y += style["gap"]


def _arch_centered_title(slide, jp_lines, resolved, palette, fonts, is_paired, motifs, style):
    # The accent is load-bearing here, not a hairline: a rising brushstroke sweep
    # on the right (or a single thick stroke) frames the centered chorus so blue
    # participates in the composition itself.
    if _has(motifs, "upward_sweep"):
        add_upward_sweep(slide, palette, base_x_in=8.6, base_y_in=6.3,
                         step_x_in=1.7, step_y_in=0.7, count=3, angle=-32)
    elif _has(motifs, "brush_stroke"):
        add_brush_stroke(slide, int(Inches(9.8)), int(Inches(1.0)), int(Inches(2.0)),
                         palette, angle=-28, width_pt=15)
    y = _anchor_start_y(resolved, style["anchor"], style)
    rule_w = int(Inches(1.3))
    add_accent_rule(slide, (SLIDE_W_EMU - rule_w) // 2, y - int(Pt(22)), rule_w, palette)
    for i, ((jp, romaji, cn), (sub, fss)) in enumerate(zip(jp_lines, resolved)):
        y = render_line_full(slide, sub, fss, romaji, cn, y, palette, fonts, style["align"],
                             bold=style["bold"], tracking=style["tracking"])
        if i < len(jp_lines) - 1:
            y += style["gap"]
    add_accent_rule(slide, (SLIDE_W_EMU - rule_w) // 2, y + int(Pt(16)), rule_w, palette)


def _arch_framed_quote(slide, jp_lines, resolved, palette, fonts, style):
    y = _anchor_start_y(resolved, style["anchor"], style)
    rule_w = int(Inches(0.6))
    add_accent_rule(slide, (SLIDE_W_EMU - rule_w) // 2, y - int(Pt(14)), rule_w, palette)
    for i, ((jp, romaji, cn), (sub, fss)) in enumerate(zip(jp_lines, resolved)):
        y = render_line_full(slide, sub, fss, romaji, cn, y, palette, fonts, style["align"],
                             bold=style["bold"], tracking=style["tracking"])
        if i < len(jp_lines) - 1:
            y += style["gap"]
    add_accent_rule(slide, (SLIDE_W_EMU - rule_w) // 2, y + int(Pt(10)), rule_w, palette)


def _arch_asymmetric_right(slide, jp_lines, resolved, palette, fonts, is_paired, motifs, style):
    # focal counterweight on the left, text weighted right — a diagonal
    # composition, not the columnar stagger of L5.
    if _has(motifs, "diagonal_slash") and not style["aggressive"]:
        add_diagonal_slash(slide, int(Inches(1.0)), int(Inches(0.9)), int(Inches(1.6)), palette)
    elif _has(motifs, "smudge"):
        add_smudge(slide, int(Inches(0.8)), int(Inches(0.9)), int(Inches(1.6)), palette)
    elif _has(motifs, "brush_stroke"):
        add_brush_stroke(slide, int(Inches(0.9)), int(Inches(0.9)), int(Inches(2.0)),
                         palette, angle=-30, width_pt=13)
    elif _has(motifs, "circle"):
        d = int(Inches(2.2))
        add_circle(slide, int(Inches(1.0)), int(Inches(0.9)), d, palette)
    elif _has(motifs, "vertical_rule"):
        add_vertical_rule(slide, int(Inches(1.2)), int(Inches(1.1)), int(Inches(4.2)), palette)
    y = _anchor_start_y(resolved, style["anchor"], style)
    for i, ((jp, romaji, cn), (sub, fss)) in enumerate(zip(jp_lines, resolved)):
        y = render_line_full(slide, sub, fss, romaji, cn, y, palette, fonts, style["align"],
                             bold=style["bold"], tracking=style["tracking"])
        if i < len(jp_lines) - 1:
            y += style["gap"]


def _arch_indent_dropcap(slide, jp_lines, resolved, palette, fonts, page_num, is_paired, motifs, style):
    if _has(motifs, "diagonal_slash") and not style["aggressive"]:
        add_diagonal_slash(slide, int(Inches(0.5)), int(Inches(1.0)), int(Inches(1.4)), palette)
    elif _has(motifs, "brush_stroke"):
        add_brush_stroke(slide, int(Inches(0.5)), int(Inches(1.0)), int(Inches(1.8)),
                         palette, angle=-22, width_pt=12)
    elif _has(motifs, "smudge"):
        add_smudge(slide, int(Inches(0.6)), int(Inches(1.0)), int(Inches(1.2)), palette)
    elif _has(motifs, "number"):
        add_number_anchor(slide, f"{page_num:02d}", int(Inches(0.5)), int(Inches(1.0)),
                          palette, fonts, size=44)
    elif _has(motifs, "vertical_rule"):
        add_vertical_rule(slide, int(Inches(0.5)), int(Inches(1.0)), int(Inches(3.6)), palette)
    # Vertical fit first (may shrink tiers), then adaptive indent from the fitted
    # sizes: the left gutter must leave room for the widest base line to clear
    # the right safe edge (indent + text width + padding ≤ RIGHT_SAFE).
    usable_bottom = SLIDE_H_EMU - BOTTOM_MARGIN_EMU
    if style["anchor"] in ("fit", "center"):
        y, resolved = _fit_centered(resolved, style["gap"], TOP_Y, usable_bottom)
    else:
        y = _anchor_start_y(resolved, style["anchor"], style)
    max_w = 0
    for sub, fss in resolved:
        for st, fs in zip(sub, fss):
            max_w = max(max_w, _text_w_em("".join(u["base"] for u in st), fs) + int(Pt(6)))
    x_indent = min(int(Inches(2.2)), RIGHT_SAFE_EMU - max_w - int(Pt(8)))
    x_indent = max(int(Inches(1.0)), x_indent)
    for i, ((jp, romaji, cn), (sub, fss)) in enumerate(zip(jp_lines, resolved)):
        y = render_line_full(slide, sub, fss, romaji, cn, y, palette, fonts, style["align"],
                             x_override=x_indent, bold=style["bold"], tracking=style["tracking"])
        if i < len(jp_lines) - 1:
            y += style["gap"]


def _arch_two_column(slide, jp_lines, resolved, palette, fonts, is_paired, motifs, style):
    # central vertical spine splits the page into two columns; text staggers
    # across it (top-left → lower-right). Structurally distinct from L3's focal
    # circle + right-weight.
    if _has(motifs, "vertical_rule"):
        add_vertical_rule(slide, int(Inches(6.6)), int(Inches(1.1)), int(Inches(4.9)),
                          palette, width_pt=1.0)
    elif _has(motifs, "brush_stroke"):
        add_brush_stroke(slide, int(Inches(6.5)), int(Inches(1.1)), int(Inches(2.0)),
                         palette, angle=72, width_pt=10)
    elif _has(motifs, "smudge"):
        add_smudge(slide, int(Inches(6.4)), int(Inches(1.1)), int(Inches(1.1)), palette)
    if is_paired:
        (jp0, r0, c0), (jp1, r1, c1) = jp_lines
        (sub0, fss0), (sub1, fss1) = resolved
        # The stagger offset must still let the widest second-column sub-line
        # clear the right safe edge (a long line at 56–60pt is ~9in wide, so a
        # hard 3.2in x could shove it off-canvas). Clamp x1 to fit, floor at the
        # first column's x so the stagger never inverts.
        max_w1 = max(_text_w_em("".join(u["base"] for u in st), fs) + int(Pt(6))
                     for st, fs in zip(sub1, fss1))
        x1 = min(int(Inches(3.2)), RIGHT_SAFE_EMU - max_w1 - int(Pt(8)))
        x1 = max(int(Inches(1.4)), x1)
        render_line_full(slide, sub0, fss0, r0, c0, int(Inches(1.4)), palette, fonts, style["align"],
                         bold=style["bold"], tracking=style["tracking"])
        render_line_full(slide, sub1, fss1, r1, c1, int(Inches(4.6)), palette, fonts, style["align"],
                         x_override=x1, bold=style["bold"], tracking=style["tracking"])
    else:
        (jp, romaji, cn) = jp_lines[0]
        sub, fss = resolved[0]
        render_line_full(slide, sub, fss, romaji, cn, int(Inches(1.6)), palette, fonts, style["align"],
                         bold=style["bold"], tracking=style["tracking"])


def _arch_ghost_full(slide, jp_lines, resolved, palette, fonts, keywords, motifs, style):
    kw = keywords[0] if (_has(motifs, "giant_kanji") and keywords) else ""
    usable_bottom = SLIDE_H_EMU - BOTTOM_MARGIN_EMU
    if kw:
        n = len(kw)
        fs = 200 if n <= 2 else 160 if n <= 4 else 120
        w = _text_w_em(kw, fs)
        # Ghost keyword tinted by the accent when the song has real color presence
        # (群青 blue), else faded toward white as a neutral watermark.
        if style.get("accent_presence", 0.0) > 0.05:
            ghost_color = _mix_hex(palette.get("ACCENT", "3A5B9E"), "FFFFFF", 0.45)
        else:
            ghost_color = _mix_hex(palette.get("TEXT_SECTION", "B0A89E"), "FFFFFF", 0.55)
        h = int(Pt(fs + 12))
        add_giant_kanji(slide, kw, (SLIDE_W_EMU - w) // 2, (SLIDE_H_EMU - h) // 2,
                        palette, fonts, fs=fs, color=ghost_color)
        if style["anchor"] in ("center", "fit"):
            y, resolved = _fit_centered(resolved, style["gap"], TOP_Y, usable_bottom)
        else:
            y = _anchor_start_y(resolved, style["anchor"], style)
    else:
        y = _anchor_start_y(resolved, style["anchor"], style)
    if _has(motifs, "smudge"):
        add_smudge(slide, int(Inches(1.0)), int(Inches(5.8)), int(Inches(1.0)), palette)
    for i, ((jp, romaji, cn), (sub, fss)) in enumerate(zip(jp_lines, resolved)):
        y = render_line_full(slide, sub, fss, romaji, cn, y, palette, fonts, style["align"],
                             bold=style["bold"], tracking=style["tracking"])
        if i < len(jp_lines) - 1:
            y += style["gap"]


def _arch_outro_fade(slide, jp_lines, resolved, palette, fonts, usable_bottom, motifs, style):
    reduced = [(sub, [reduce_tier(f) for f in fss]) for sub, fss in resolved]
    if style["anchor"] == "bottom":
        total_h = _block_height(reduced, style["gap"])
        y = max(int(Inches(1.6)), usable_bottom - total_h - int(Inches(0.4)))
    else:
        y = _anchor_start_y(reduced, style["anchor"], style)
    if _has(motifs, "diagonal_slash") and not style["aggressive"]:
        add_diagonal_slash(slide, int(Inches(0.6)), int(Inches(5.9)), int(Inches(1.2)),
                           palette, angle=-20)
    elif _has(motifs, "smudge"):
        add_smudge(slide, int(Inches(0.6)), int(Inches(5.9)), int(Inches(0.7)), palette,
                   tint_white=0.55)
    elif _has(motifs, "circle"):
        add_circle(slide, int(Inches(0.6)), int(Inches(5.9)), int(Inches(0.4)), palette)
    elif _has(motifs, "vertical_rule"):
        add_vertical_rule(slide, int(Inches(0.6)), int(Inches(5.6)), int(Inches(0.9)), palette)
    for i, ((jp, romaji, cn), (sub, fss)) in enumerate(zip(jp_lines, reduced)):
        y = render_line_full(slide, sub, fss, romaji, cn, y, palette, fonts, style["align"],
                             bold=style["bold"], tracking=style["tracking"])
        if i < len(jp_lines) - 1:
            y += style["gap"]


# ── Cover ────────────────────────────────────────────────────────────────────

def render_cover(slide, profile, bg_buf, subtitle, meta_parts):
    palette = profile["palette"]
    fonts = profile["font"]
    add_background(slide, bg_buf)

    tf_label = slide.shapes.add_textbox(int(Inches(0.4)), int(Pt(16)), int(Inches(4)), int(Pt(24)))
    _add_run(tf_label.text_frame.paragraphs[0], "Lyric Cards", fonts["jp"],
             fonts["romaji"], size=Pt(SECTION_FS), color=palette["TEXT_SECTION"])

    title = profile["title"]
    n = len(title)
    if n <= 5:
        title_fs = 98
    elif n <= 10:
        title_fs = 90
    elif n <= 15:
        title_fs = 76
    else:
        title_fs = 63

    line_count = 1 + (1 if subtitle else 0) + (1 if profile["artist"] else 0) + (1 if meta_parts else 0)
    block_h = line_count * int(Pt(64)) + int(Pt(30))
    y = max(int(Inches(1.7)), (SLIDE_H_EMU - block_h) // 2)

    tf = slide.shapes.add_textbox(LEFT_MARGIN_EMU, y, CONTENT_W_EMU, block_h + int(Pt(40)))
    tf.text_frame.word_wrap = True

    p_title = tf.text_frame.paragraphs[0]
    p_title.alignment = PP_ALIGN.LEFT
    p_title.space_after = Pt(6)
    _add_run(p_title, title, fonts["jp"], fonts["romaji"], size=Pt(title_fs),
             color=palette["TEXT_JP"])

    y_cursor = y + int(Pt(title_fs + 14))

    if subtitle:
        p_sub = tf.text_frame.add_paragraph()
        p_sub.alignment = PP_ALIGN.LEFT
        p_sub.space_before = Pt(4)
        p_sub.space_after = Pt(6)
        _add_run(p_sub, subtitle, fonts["romaji"], fonts["romaji"], size=Pt(24),
                 color=palette["TEXT_ROMAJI"])
        y_cursor += int(Pt(34))

    # accent rule — native shape, no glyph-concat
    rule_w = int(Inches(1.2))
    add_accent_rule(slide, LEFT_MARGIN_EMU, y_cursor, rule_w, palette)
    y_cursor += int(Pt(28))

    if profile["artist"]:
        p_art = tf.text_frame.add_paragraph()
        p_art.alignment = PP_ALIGN.LEFT
        p_art.space_before = Pt(4)
        p_art.space_after = Pt(2)
        _add_run(p_art, profile["artist"], fonts["cn"], fonts["romaji"], size=Pt(20),
                 color=palette["TEXT_CN"])

    if meta_parts:
        p_meta = tf.text_frame.add_paragraph()
        p_meta.alignment = PP_ALIGN.LEFT
        p_meta.space_before = Pt(6)
        _add_run(p_meta, " · ".join(meta_parts), fonts["cn"], fonts["romaji"],
                 size=Pt(14), color=palette["TEXT_SECTION"])

    footer = f"{title}  ·  {profile['artist']}" if profile["artist"] else title
    add_footer(slide, footer, palette, fonts)
