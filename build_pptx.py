#!/usr/bin/env python3
"""Build lyric-card PPTX — v2 orchestrator.

Thin driver: load data.json → build SongVisualProfile → generate background →
render cover + one page per lyric group, dispatching to the 8 layout archetypes
in scripts/pptx_layouts.py. `--preview` emits a short archetype demo + montage
instead of the full deck.
"""

import sys, os, json, hashlib, re
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE_TYPE

sys.stdout.reconfigure(encoding="utf-8")

from scripts.pptx_palette import rgb
from scripts.pptx_background import generate_mood_background
from scripts.pptx_profile import build_profile, resolve_page_intent
from scripts.pptx_layouts import (
    SLIDE_W_EMU, SLIDE_H_EMU, CONTENT_W_EMU, LEFT_MARGIN_EMU, BOTTOM_MARGIN_EMU,
    RIGHT_SAFE_EMU, GAP_LINES, CN_FS, estimate_line_height, resolve_line,
    render_cover, render_archetype, add_background, add_section_label,
    add_footer, _add_run, _set_cjk_font,
)
from scripts.pptx_furigana import reset_reading_warnings, get_reading_warnings


# ── Metadata extraction ──────────────────────────────────────────────────────

def _extract_meta(d: dict, is_japanese: bool):
    info = {row[0]: row[1] for row in d.get("info_rows", [])}
    artist = info.get("演唱者", info.get("作曲", ""))
    album = info.get("所属专辑", info.get("所属作品", ""))
    release = info.get("发行日期", info.get("首演年份", ""))
    tieup = info.get("Tie-up", "")

    subtitle = ""
    if is_japanese:
        song_name_row = info.get("歌曲名", "")
        if "（" in song_name_row:
            paren = song_name_row.split("（", 1)[1].rstrip("）")
            subtitle = paren.split(" / ")[0]

    meta_parts = []
    if album and "未收" not in album:
        meta_parts.append(album)
    if release:
        m = re.search(r"(\d{4})", release)
        if m:
            meta_parts.append(m.group(1))
    if tieup and is_japanese:
        short = tieup.replace("日曜劇場", "").replace("（", "").replace("）", "")
        if len(short) > 30:
            short = short[:28] + "…"
        meta_parts.append(short)

    return subtitle, meta_parts


# ── Page planning ────────────────────────────────────────────────────────────

def _pair_lines(lines):
    """Group JP lyric lines into 1–2 line pages, avoiding overflow."""
    pairs = []
    i, n = 0, len(lines)
    usable_h = SLIDE_H_EMU - BOTTOM_MARGIN_EMU
    while i < n:
        cur = lines[i]
        cur_cc = len(cur[0])
        if cur_cc >= 19 or i == n - 1:
            pairs.append([cur]); i += 1; continue
        nxt = lines[i + 1]
        nxt_cc = len(nxt[0])
        if nxt_cc >= 19:
            pairs.append([cur]); i += 1; continue
        h_cur = estimate_line_height(*resolve_line(cur[0], cur[1], True))
        h_nxt = estimate_line_height(*resolve_line(nxt[0], nxt[1], True))
        if h_cur + h_nxt + GAP_LINES <= usable_h:
            pairs.append([cur, nxt]); i += 2
        else:
            pairs.append([cur]); i += 1
    return pairs


def _group_english_lines(lines, max_per_slide=5):
    groups = []
    i, n = 0, len(lines)
    while i < n:
        remaining = n - i
        if remaining <= max_per_slide:
            groups.append(lines[i:]); break
        size = max_per_slide
        if remaining - size == 1:
            size = max_per_slide - 1
        groups.append(lines[i:i + size]); i += size
    return groups


def _curve_by_section(profile: dict) -> dict:
    return {c["section"]: c for c in profile.get("emotionalCurve", [])}


def plan_pages(sections, is_japanese: bool, profile: dict):
    """Return [(section_name, archetype_id, [lines], energy, darkness, slash)] in order.

    Archetype + energy/darkness/slash come from the director's emotionalCurve
    (one entry per section), never a hardcoded section→layout map. Missing
    entries fall back to L1 / neutral energy / no slash.
    """
    curve = _curve_by_section(profile)
    pages = []
    for sname, lines in sections:
        if not lines:
            continue
        c = curve.get(sname, {})
        arch = c.get("arch", "L1")
        energy = c.get("energy", 0.5)
        darkness = c.get("darkness", 0.3)
        slash = c.get("slash")
        groups = _pair_lines(lines) if is_japanese else _group_english_lines(lines)
        for g in groups:
            pages.append((sname, arch, g, energy, darkness, slash))
    return pages


def select_preview_pages(pages):
    """Pick one page per archetype, forcing L5 via a 2-line page."""
    selected, seen = [], set()
    for p in pages:
        if p[1] not in seen:
            selected.append(p); seen.add(p[1])
    if "L5" not in seen:
        for p in pages:
            if len(p[2]) == 2:
                selected.append((p[0], "L5", p[2], p[3], p[4], None)); break
    return selected


# ── English slide (minimal) ─────────────────────────────────────────────────

def _render_english_slide(slide, lines, profile, bg_buf, section, page_num, total_pages):
    palette, fonts = profile["palette"], profile["font"]
    add_background(slide, bg_buf)
    add_section_label(slide, section, palette, fonts)
    footer = f"{profile['title']}  ·  {profile['artist']}  —  {page_num} / {total_pages}"
    add_footer(slide, footer, palette, fonts)

    max_len = max(len(lt[0]) for lt in lines)
    fs = 42 if max_len <= 15 else 38 if max_len <= 25 else 34 if max_len <= 35 else 30
    y = int(Inches(1.4))
    gap = int(Pt(26))
    for en, cn in lines:
        tf = slide.shapes.add_textbox(LEFT_MARGIN_EMU, y, CONTENT_W_EMU, int(Pt(fs + 10)))
        tf.text_frame.word_wrap = True
        p = tf.text_frame.paragraphs[0]
        _add_run(p, en, fonts["en"], fonts["en"], size=Pt(fs), color=palette["TEXT_JP"])
        y += int(Pt(fs + 14))
        tf_cn = slide.shapes.add_textbox(LEFT_MARGIN_EMU, y, CONTENT_W_EMU, int(Pt(CN_FS + 6)))
        tf_cn.text_frame.word_wrap = True
        _add_run(tf_cn.text_frame.paragraphs[0], cn, fonts["cn"], fonts["romaji"],
                 size=Pt(CN_FS), color=palette["TEXT_CN"])
        y += int(Pt(CN_FS + 6)) + gap


# ── Build ───────────────────────────────────────────────────────────────────

def _new_deck(profile, bg_buf, subtitle, meta_parts):
    """Fresh Presentation sized to the deck, with the cover already drawn."""
    prs = Presentation()
    prs.slide_width = SLIDE_W_EMU
    prs.slide_height = SLIDE_H_EMU
    s0 = prs.slides.add_slide(prs.slide_layouts[6])
    render_cover(s0, profile, bg_buf, subtitle, meta_parts)
    return prs


def _render_pages(prs, pages, profile, is_japanese, seed, bg_buf, specs_map=None):
    """Render all lyric pages; return per-page resolved spec lists (for the critic)."""
    total_pages = len(pages)
    resolved = []
    assets = profile.get("visual_assets")
    prev_section = None
    section_page_idx = 0
    for idx, (section, arch, group, energy, darkness, slash) in enumerate(pages, start=1):
        if section != prev_section:
            section_page_idx = 0
            prev_section = section
        else:
            section_page_idx += 1
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        if is_japanese:
            override = specs_map[idx - 1] if specs_map else None
            intent = resolve_page_intent(assets, section, section_page_idx)
            specs = render_archetype(slide, arch, group, profile, section, idx, total_pages,
                                     dark=(darkness >= 0.6), energy=energy, slash=slash,
                                     motifs=profile.get("visualMotifs"),
                                     keywords=profile.get("keywords"),
                                     seed=seed, page_specs_override=override,
                                     page_intent=intent)
            resolved.append(specs or [])
        else:
            _render_english_slide(slide, group, profile, bg_buf, section, idx, total_pages)
            resolved.append([])
    return resolved


def build_pptx(json_path, out_path=None, preview=False):
    from scripts.dataload import load_song
    d, meta = load_song(json_path)
    is_japanese = meta["language"] == "ja"

    # Schema + coverage + line-ID validation. Errors block delivery (non-zero
    # exit); warnings never do. Frozen baselines (derived IDs) only warn.
    from scripts.validate import validate_schema, check_coverage
    v_warn, v_err = validate_schema(d, meta["lines"], meta["language"])
    _n, c_warn = check_coverage(d)
    for w in v_warn + c_warn:
        print(f"  [validate] {w}")
    if v_err:
        for e in v_err:
            print(f"  [validate] ERROR: {e}")
        print("  [validate] 存在 errors，中止构建（不产出交付文件）。")
        sys.exit(1)

    if (d.get("visual_profile") or {}).get("renderVersion") in (3, 4):
        from scripts.pptx_editorial import build_editorial
        if out_path is None:
            base = d.get("title", "song").replace("歌曲学习：", "")
            folder = os.path.join(os.path.dirname(json_path), "_preview") if preview else os.path.dirname(json_path)
            out_path = os.path.join(folder, base + ("_preview" if preview else "") + ".pptx")
        return build_editorial(d, meta, out_path, preview)

    profile = build_profile(d)
    subtitle, meta_parts = _extract_meta(d, is_japanese)

    seed = int(hashlib.md5(d.get("title", "song").encode()).hexdigest()[:8], 16) % 10000
    bg_buf = generate_mood_background(seed=seed, base_color=profile["bg"])

    pages = plan_pages(meta["sections"], is_japanese, profile)
    if preview:
        pages = select_preview_pages(pages)

    reset_reading_warnings()
    prs = _new_deck(profile, bg_buf, subtitle, meta_parts)
    resolved_specs = _render_pages(prs, pages, profile, is_japanese, seed, bg_buf)

    # Visual Critic + one deterministic rework, then stop. Only for songs with a
    # visual_assets block — old frozen baselines (no visual_assets) keep the
    # native-shape path and are not judged by the engine's critic.
    from scripts.pptx_critic import critique, nudge_specs
    _assets = profile.get("visual_assets", {})
    has_assets = bool(_assets.get("base") or _assets.get("sections"))
    if has_assets:
        ok, failures, _report = critique(pages, resolved_specs, profile, prs)
        if not ok and any(resolved_specs):
            nudged = nudge_specs(resolved_specs, pages, failures)
            print("  [critic] 机械 FAIL，按确定性 nudge 重建一次…")
            reset_reading_warnings()
            prs = _new_deck(profile, bg_buf, subtitle, meta_parts)
            _render_pages(prs, pages, profile, is_japanese, seed, bg_buf, nudged)
            critique(pages, nudged, profile, prs)
            print("  [critic] 已返工一次，无条件停止。")
    else:
        print("\n  [critic] 跳过：无 visual_assets（旧歌回退路径，不参与引擎评审）\n")

    if out_path is None:
        base = d.get("title", "song").replace("歌曲学习：", "")
        out_path = os.path.join(os.path.dirname(json_path), f"{base}.pptx")
        if preview:
            out_path = os.path.join(os.path.dirname(json_path), "_preview",
                                    f"{base}_preview.pptx")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    from scripts.atomic import atomic_replace
    atomic_replace(out_path, lambda tmp: prs.save(tmp))

    _verify(meta["sections"], is_japanese, pages, profile)
    _review_visual(d, is_japanese, pages, prs)

    warnings = get_reading_warnings()
    report_path = os.path.splitext(out_path)[0] + "_reading_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(warnings) if warnings else "无告警，全部对齐。\n")
    if warnings:
        print("\n  读音对齐告警：")
        for w in warnings:
            print(f"    {w}")
    else:
        print("\n  读音对齐：无告警，全部对齐。")
    print(f"OK: {out_path} ({os.path.getsize(out_path)} bytes)")

    if preview:
        from scripts.render_preview import generate_montage
        labels = ["cover"] + [p[1] for p in pages]
        generate_montage(out_path, os.path.splitext(out_path)[0] + "_montage.png",
                         labels=labels)


def _verify(sections, is_japanese, pages, profile):
    total_input = 0
    bad_arity = 0
    for sname, lines in sections:
        total_input += len(lines)
        if is_japanese:
            for ln in lines:
                if not (isinstance(ln, (list, tuple)) and len(ln) == 3):
                    bad_arity += 1
    print(f"\n{'='*60}")
    print(f"  VERIFY: {profile.get('title','song')} ({'JP' if is_japanese else 'EN'})")
    print(f"  Input lines: {total_input}   Output slides: {len(pages)} (+cover)")
    if bad_arity:
        print(f"  [warn] {bad_arity} 行非 3 列（日文路径应为 [原文,罗马音,翻译]）")
    print(f"  Fonts: JP={profile['font']['jp']}  CN={profile['font']['cn']}  "
          f"EN={profile['font']['en']}")
    print(f"  Accent: #{profile['accent']}   bg: #{profile['bg']}")
    print(f"  Archetypes used: {sorted({p[1] for p in pages})}")
    reasons = profile.get("visualMotifReasons", {})
    if reasons:
        print(f"  visualMotifs (director's reason):")
        for mt, why in reasons.items():
            print(f"    - {mt}: {why}")
    print(f"{'='*60}\n")


def _review_visual(d, is_japanese, pages, prs):
    """Programmatic visual review — checkable invariants only.

    Honest scope: this model cannot read rendered images, so the review asserts
    what the object model can prove (anchor presence, phrase-grouping dup, dark
    page count, overflow). Aesthetic qualities (composition variety, whitespace
    balance, brightness curve) still need human eyes on the montage.
    """
    print(f"\n{'='*60}")
    print(f"  VISUAL REVIEW")
    print(f"{'='*60}")
    if not is_japanese:
        print("  (non-JP deck — programmatic review skipped)")
        print(f"{'='*60}\n")
        return True

    from collections import Counter
    engine_mode = bool(d.get("visual_assets"))
    # Per-page source text counts across jp + romaji + cn. A romaji string may
    # legitimately also be the JP base (English loan-phrases like "WATCH ME DO…")
    # or the CN translation, so the dedup guard compares each rendered string
    # against how many times that exact string appears in *all three* source
    # fields — not just the romaji column. The bug it still catches: the old
    # phrase-grouping split rendered a romaji once per sub-line.
    page_text = []
    for _s, _a, group, _e, _d, _sl in pages:
        c = Counter()
        for jp, romaji, cn in group:
            for t in (jp, romaji, cn):
                if t and t.strip():
                    c[t.strip()] += 1
        page_text.append(c)

    ok = True
    safe_bottom = SLIDE_H_EMU - BOTTOM_MARGIN_EMU
    # Textboxes in this system reserve ~6–8pt of empty padding around the actual
    # glyphs (base +8pt height/+6pt width; romaji & CN +6pt height). The check
    # targets *visible* text crossing the safe edge, so an 8pt allowance absorbs
    # that padding while still catching a real clip — which is on the order of
    # inches, not points (the L6 bug ran ~3in past the slide bottom).
    tol = int(Pt(8))
    for idx, slide in enumerate(prs.slides):
        if idx == 0:
            continue  # cover
        decorative = 0
        text_runs = []
        for shape in slide.shapes:
            st = shape.shape_type
            if st == MSO_SHAPE_TYPE.PICTURE:
                continue
            if st in (MSO_SHAPE_TYPE.AUTO_SHAPE, MSO_SHAPE_TYPE.FREEFORM):
                decorative += 1
                continue
            if getattr(shape, "has_text_frame", False):
                max_fs = 0.0
                short_text = 0
                label = ""
                for p in shape.text_frame.paragraphs:
                    for r in p.runs:
                        t = r.text.strip()
                        if t:
                            text_runs.append(t)
                            short_text = max(short_text, len(t))
                            if not label:
                                label = t[:14]
                        if r.font.size is not None:
                            max_fs = max(max_fs, r.font.size.pt)
                # giant kanji / number anchors are textboxes with big short text;
                # very large ghost text (≥100pt) may be a multi-char kana word
                is_giant = max_fs >= 100 and short_text <= 8
                is_number = 40 <= max_fs < 100 and short_text <= 4
                if is_giant or is_number:
                    decorative += 1
                # final-rendered boundary check: a textbox's top+height is where
                # its glyphs actually land, so any text box whose bottom clears the
                # slide's safe area means visible text is clipped off-canvas. The
                # footer (top ≥ safe_bottom) lives in the bottom margin by design,
                # so it's exempt; full-width center/right containers are skipped on
                # the right check because their box spans the slide while the text
                # inside is centered.
                if short_text and shape.top < safe_bottom:
                    if shape.top + shape.height > safe_bottom + tol:
                        print(f"  [FAIL] slide {idx}: text '{label}' bottom "
                              f"{shape.top + shape.height} exceeds safe {safe_bottom}")
                        ok = False
                if short_text and shape.width < RIGHT_SAFE_EMU:
                    if shape.left + shape.width > RIGHT_SAFE_EMU + tol:
                        print(f"  [FAIL] slide {idx}: text '{label}' right "
                              f"{shape.left + shape.width} exceeds safe {RIGHT_SAFE_EMU}")
                        ok = False
        if decorative == 0 and not engine_mode:
            print(f"  [FAIL] slide {idx}: no anchor shape")
            ok = False
        rc = Counter(text_runs)
        for ro, expected in page_text[idx - 1].items():
            got = rc.get(ro, 0)
            if got > expected:
                print(f"  [FAIL] slide {idx}: text '{ro}' rendered x{got}, expected x{expected}")
                ok = False
    dark_sections = sorted({s for s, _a, _g, _e, _d, _sl in pages if _d >= 0.6})
    print(f"  dark-inversion sections = {len(dark_sections)} "
          f"({'OK' if len(dark_sections) <= 1 else 'FAIL, want ≤1'})")
    if len(dark_sections) > 1:
        ok = False
    print(f"  result: {'PASS' if ok else 'FAIL'} (aesthetic judgment still needs the montage)")
    print(f"{'='*60}\n")
    return ok


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: PYTHONUTF8=1 python build_pptx.py <data.json> [--preview]")
        sys.exit(1)
    args = sys.argv[1:]
    preview = "--preview" in args
    args = [a for a in args if a != "--preview"]
    build_pptx(args[0], args[1] if len(args) > 1 else None, preview=preview)
