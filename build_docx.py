#!/usr/bin/env python3
"""Build a .docx study sheet from song-study data.json (unified schema).

Consumes the current data.json shape: dict-form grammar_points/culture_notes/
singing_tips, vocab_table, sources_lyrics/sources_bg, and an optional
structured `verification` block. Fonts come from the data.json `font_*` fields
with system defaults; Word substitutes missing families at render time (no
guarantee of glyph coverage — the embedded family is only a preference).
"""

import sys
import os
import json

sys.stdout.reconfigure(encoding="utf-8")

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml

from scripts.validate import verification_lines, validate_schema, check_coverage
from scripts.atomic import atomic_replace

# ============================================================
# FONT + COLOR CONFIG (system defaults; overridden by data.json)
# ============================================================
FONT_SC_BODY = "SimSun"
FONT_SC_HEAD = "Microsoft YaHei"
FONT_JP_BODY = "MS Mincho"
FONT_JP_HEAD = "Meiryo"
FONT_EN = "Arial"

DEEP_BLUE = "2C3E50"
AMBER = "B85C3A"
GOLD_BORDER = "D4A574"
LIGHT_BLUE = "D6E4F0"
WARM_BEIGE = "F5EBE0"
LIGHT_GREEN = "E8F0E4"
LIGHT_PURPLE = "EDE8F5"
LIGHT_GRAY = "F8F8F8"

# ============================================================
# DOCX HELPERS
# ============================================================
def set_font(run, cjk, en=FONT_EN, size=Pt(11), bold=False, color=None):
    run.font.size = size
    run.bold = bold
    run.font.name = en
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = parse_xml('<w:rFonts ' + nsdecls("w") + " />")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:eastAsia"), cjk)
    rFonts.set(qn("w:ascii"), en)
    rFonts.set(qn("w:hAnsi"), en)
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def add_p(doc, text, cjk=FONT_SC_BODY, en=FONT_EN, size=Pt(11), bold=False,
          color=None, space_after=Pt(6)):
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_font(run, cjk=cjk, en=en, size=size, bold=bold, color=color)
    p.paragraph_format.space_after = space_after
    return p


def shade_cell(cell, color):
    shading = parse_xml('<w:shd ' + nsdecls("w") + ' w:val="clear" w:fill="' + color + '"/>')
    cell._element.get_or_add_tcPr().append(shading)


def make_table(doc, headers, rows, header_color, data_cjk=FONT_SC_BODY,
               header_cjk=FONT_SC_HEAD):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        shade_cell(cell, header_color)
        p = cell.paragraphs[0]
        run = p.add_run(h)
        set_font(run, cjk=header_cjk, en=FONT_EN, size=Pt(10), bold=True)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for r_idx, row in enumerate(rows):
        for c_idx, val in enumerate(row):
            cell = table.rows[r_idx + 1].cells[c_idx]
            if r_idx % 2 == 1:
                shade_cell(cell, LIGHT_GRAY)
            p = cell.paragraphs[0]
            run = p.add_run(str(val))
            set_font(run, cjk=data_cjk, en=FONT_EN, size=Pt(9.5))
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
    doc.add_paragraph()
    return table


def add_quote(doc, text, cjk=FONT_SC_BODY, size=Pt(10)):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.8)
    pPr = p._element.get_or_add_pPr()
    borders = parse_xml(
        '<w:pBdr ' + nsdecls("w") + ">"
        '<w:left w:val="single" w:sz="12" w:color="' + GOLD_BORDER + '" w:space="8"/>'
        "</w:pBdr>"
    )
    pPr.append(borders)
    run = p.add_run(text)
    set_font(run, cjk=cjk, en=FONT_EN, size=size)
    run.italic = True
    return p


def add_grammar_title(doc, text, cjk=FONT_SC_HEAD):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(text)
    set_font(run, cjk=cjk, en=FONT_EN, size=Pt(11), bold=True, color=AMBER)
    return p


def add_singing_tip(doc, title, problem, solution, title_cjk=FONT_SC_HEAD,
                    body_cjk=FONT_SC_BODY):
    p_title = doc.add_paragraph()
    p_title.paragraph_format.space_before = Pt(8)
    p_title.paragraph_format.space_after = Pt(2)
    set_font(p_title.add_run(title), cjk=title_cjk, en=FONT_EN, size=Pt(11), bold=True)

    p_prob = doc.add_paragraph()
    p_prob.paragraph_format.left_indent = Cm(0.3)
    set_font(p_prob.add_run(problem), cjk=body_cjk, en=FONT_EN, size=Pt(10.5))

    p_sol = doc.add_paragraph()
    p_sol.paragraph_format.left_indent = Cm(0.6)
    p_sol.paragraph_format.space_after = Pt(6)
    set_font(p_sol.add_run("→ " + solution), cjk=body_cjk, en=FONT_EN, size=Pt(10.5))


def add_separator(doc):
    doc.add_paragraph()
    sep = doc.add_paragraph()
    sep.paragraph_format.space_after = Pt(12)
    r = sep.add_run("─" * 40)
    set_font(r, cjk=FONT_SC_BODY, en=FONT_EN, size=Pt(8), color=DEEP_BLUE)


def add_verify_block(doc, text, cjk=FONT_SC_BODY):
    doc.add_paragraph()
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    pPr = p._element.get_or_add_pPr()
    borders = parse_xml(
        '<w:pBdr ' + nsdecls("w") + ">"
        '<w:left w:val="single" w:sz="12" w:color="' + DEEP_BLUE + '" w:space="8"/>'
        "</w:pBdr>"
    )
    pPr.append(borders)
    shading = parse_xml('<w:shd ' + nsdecls("w") + ' w:val="clear" w:fill="F8F8F8"/>')
    pPr.append(shading)
    set_font(p.add_run(text), cjk=cjk, en=FONT_EN, size=Pt(9))


# ============================================================
# SCHEMA DETECTION (language is resolved by scripts/dataload.py)
# ============================================================

def _is_jp_vocab(vocab_table):
    if vocab_table and vocab_table[0]:
        first = str(vocab_table[0][0])
        return any("぀" <= c <= "ヿ" or "一" <= c <= "鿿" for c in first)
    return True


def _split_note(text):
    """Split a culture note into (title, body) on the first full-width colon."""
    idx = text.find("：")
    if 0 < idx <= 30:
        return text[:idx], text[idx + 1:]
    return "", text


# ============================================================
# BUILD DOCX FROM JSON DATA
# ============================================================

def build_docx(json_path, out_path):
    from scripts.dataload import load_song
    d, meta = load_song(json_path)

    # Errors block delivery (non-zero exit); warnings never do.
    v_warn, v_err = validate_schema(d, meta["lines"], meta["language"])
    _n, c_warn = check_coverage(d)
    for w in v_warn + c_warn:
        print(f"  [validate] {w}")
    if v_err:
        for e in v_err:
            print(f"  [validate] ERROR: {e}")
        print("  [validate] 存在 errors，中止构建（不产出交付文件）。")
        sys.exit(1)

    language = meta["language"]
    is_jp = language == "ja"

    doc = Document()
    for section in doc.sections:
        section.page_width = Cm(21)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2.54)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(2.0)
        section.right_margin = Cm(2.0)

    sc_body = d.get("font_cn_body", FONT_SC_BODY)
    sc_head = d.get("font_cn_heading", FONT_SC_HEAD)
    jp_body = d.get("font_jp_body", FONT_JP_BODY)
    jp_head = d.get("font_jp_heading", FONT_JP_HEAD)

    title = d.get("title", "song").replace("歌曲学习：", "")
    add_p(doc, title, cjk=sc_head, size=Pt(18), bold=True, color=DEEP_BLUE, space_after=Pt(4))
    add_separator(doc)

    # Basic Info
    info_rows = d.get("info_rows", [])
    if info_rows:
        add_p(doc, "基本信息", cjk=sc_head, size=Pt(15), bold=True, space_after=Pt(8))
        make_table(doc, ["项目", "内容"], info_rows, LIGHT_BLUE, data_cjk=sc_body,
                   header_cjk=sc_head)

    # Background
    bg_paras = d.get("bg_paras", [])
    if bg_paras:
        add_p(doc, "背景故事", cjk=sc_head, size=Pt(15), bold=True, space_after=Pt(8))
        for para in bg_paras:
            add_p(doc, para, cjk=sc_body, size=Pt(11), space_after=Pt(6))

    # Lyrics
    lyric_sections = meta["sections"]
    if lyric_sections:
        add_p(doc, "歌词", cjk=sc_head, size=Pt(15), bold=True, space_after=Pt(4))
        for section_name, lines in lyric_sections:
            if section_name:
                add_p(doc, section_name, cjk=sc_head, size=Pt(11), bold=True,
                      color=DEEP_BLUE, space_after=Pt(4))
            if is_jp:
                make_table(doc, ["原文", "发音（罗马字）", "中文翻译"], lines, WARM_BEIGE,
                           data_cjk=jp_body, header_cjk=sc_head)
            else:
                make_table(doc, ["原文", "中文翻译"], lines, WARM_BEIGE,
                           data_cjk=sc_body, header_cjk=sc_head)

    # Language Learning (only when vocab/grammar present)
    vocab_table = d.get("vocab_table", [])
    grammar_points = d.get("grammar_points", [])
    culture_notes = d.get("culture_notes", [])
    if vocab_table or grammar_points or culture_notes:
        add_p(doc, "语言学习", cjk=sc_head, size=Pt(15), bold=True, space_after=Pt(8))

    if vocab_table:
        add_p(doc, "核心词汇", cjk=sc_head, size=Pt(13), bold=True, space_after=Pt(4))
        is_jp_vocab = _is_jp_vocab(vocab_table)
        if is_jp_vocab:
            make_table(doc, ["原文", "读音", "词性", "释义", "等级"], vocab_table,
                       LIGHT_GREEN, data_cjk=jp_body, header_cjk=sc_head)
        else:
            make_table(doc, ["单词/短语", "音标/发音提示", "词性", "释义", "难度"],
                       vocab_table, LIGHT_GREEN, data_cjk=sc_body, header_cjk=sc_head)
        if d.get("vocab_note"):
            add_p(doc, d["vocab_note"], cjk=sc_body, size=Pt(9), space_after=Pt(4))

    if grammar_points:
        add_p(doc, "语法点", cjk=sc_head, size=Pt(13), bold=True, space_after=Pt(4))
        for gp in grammar_points:
            name = gp.get("name", "")
            section = gp.get("section", "")
            quote = gp.get("quote", "")
            analysis = gp.get("analysis", "")
            extra = gp.get("extra", "")
            add_grammar_title(doc, name, cjk=sc_head)
            if quote:
                sec = str(section).strip().strip("[]")
                prefix = f"[{sec}] " if sec else ""
                add_p(doc, f"{prefix}「{quote}」", cjk=jp_body, size=Pt(10),
                      space_after=Pt(2))
            if analysis:
                add_p(doc, analysis, cjk=sc_body, size=Pt(10.5), space_after=Pt(4))
            if extra:
                add_p(doc, extra, cjk=sc_body, size=Pt(10), color="555555",
                      space_after=Pt(8))

    if culture_notes:
        add_p(doc, "文化笔记", cjk=sc_head, size=Pt(13), bold=True, space_after=Pt(6))
        for note in culture_notes:
            title, body = _split_note(note)
            if title:
                add_grammar_title(doc, title, cjk=sc_head)
            add_p(doc, body if body else note, cjk=sc_body, size=Pt(10.5), space_after=Pt(8))

    # Singing Tips
    singing_tips = d.get("singing_tips", [])
    if singing_tips:
        add_p(doc, "演唱技巧", cjk=sc_head, size=Pt(15), bold=True, space_after=Pt(8))
        for tip in singing_tips:
            add_singing_tip(doc, tip.get("name", ""), tip.get("problem", ""),
                            tip.get("solution", ""), title_cjk=sc_head, body_cjk=sc_body)

    # Appendix
    sources_lyrics = d.get("sources_lyrics", [])
    sources_bg = d.get("sources_bg", [])
    if sources_lyrics or sources_bg:
        add_separator(doc)
        add_p(doc, "附录", cjk=sc_head, size=Pt(15), bold=True, space_after=Pt(8))
        if sources_lyrics:
            add_p(doc, "歌词来源", cjk=sc_head, size=Pt(13), bold=True, space_after=Pt(4))
            for s in sources_lyrics:
                add_p(doc, s, cjk=sc_body, size=Pt(9), space_after=Pt(2))
        if sources_bg:
            add_p(doc, "背景信息来源", cjk=sc_head, size=Pt(13), bold=True, space_after=Pt(4))
            for s in sources_bg:
                add_p(doc, s, cjk=sc_body, size=Pt(9), space_after=Pt(2))

    # Verification (six separate checks, not one collapsed verdict)
    ver_lines = verification_lines(d)
    if ver_lines:
        add_verify_block(doc, ver_lines[0], cjk=sc_body)
        for extra in ver_lines[1:]:
            add_p(doc, extra, cjk=sc_body, size=Pt(9), space_after=Pt(2))

    atomic_replace(out_path, lambda tmp: doc.save(tmp))
    print("OK: " + out_path + " (" + str(os.path.getsize(out_path)) + " bytes)")


# ============ MAIN ============
def _discover_songs(root):
    songs = []
    if not os.path.isdir(root):
        return songs
    for name in sorted(os.listdir(root)):
        if name.startswith("_"):
            continue
        sub = os.path.join(root, name)
        dj = os.path.join(sub, "data.json")
        if os.path.isfile(dj):
            songs.append((dj, os.path.join(sub, name + ".docx")))
    return songs


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python build_docx.py <json_data_file> [out.docx]")
        print("  or: python build_docx.py --all")
        sys.exit(1)

    if sys.argv[1] == "--all":
        root = os.environ.get("SONG_STUDY_DATA", r"E:\song-study")
        songs = _discover_songs(root)
        for json_path, out_path in songs:
            try:
                build_docx(json_path, out_path)
            except Exception as e:
                print(f"FAIL: {json_path} -> {e}")
    else:
        json_path = sys.argv[1]
        if len(sys.argv) > 2:
            out_path = sys.argv[2]
        else:
            dirpath = os.path.dirname(json_path) or "."
            dirname = os.path.basename(os.path.normpath(dirpath))
            out_path = os.path.join(dirpath, dirname + ".docx")
        build_docx(json_path, out_path)