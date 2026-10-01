#!/usr/bin/env python3
"""Build a .md study sheet from song-study data.json (unified schema).

Consumes the same scripts.dataload.load_song() normalized result as build_docx
and build_pptx, so the three outputs can't drift. Content lives in data.json;
this file only renders. Line counts and verification stats are computed from the
unified data (scripts.validate.line_metrics / lyric_completeness) — nothing is
hand-maintained here.
"""

import sys
import os
import json

sys.stdout.reconfigure(encoding="utf-8")

from scripts.dataload import load_song
from scripts.validate import (line_metrics, lyric_completeness, verification_lines,
                              validate_schema, check_coverage)
from scripts.atomic import atomic_replace


def _md_table(headers, rows):
    out = []
    out.append("| " + " | ".join(str(h) for h in headers) + " |")
    out.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        cells = [str(c).replace("|", "\\|").replace("\n", " ") for c in row]
        out.append("| " + " | ".join(cells) + " |")
    return out


def _is_jp_vocab(vocab_table):
    if vocab_table and vocab_table[0]:
        first = str(vocab_table[0][0])
        return any("぀" <= c <= "ヿ" or "一" <= c <= "鿿" for c in first)
    return True


def build_md(json_path, out_path=None):
    d, meta = load_song(json_path)
    language = meta["language"]
    is_jp = language == "ja"
    title = d.get("title", "song").replace("歌曲学习：", "")

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

    L = []
    L.append(f"# 歌曲学习：{title}")
    L.append("")
    L.append("---")
    L.append("")

    # 基本信息
    info_rows = d.get("info_rows", [])
    if info_rows:
        L.append("## 基本信息")
        L.append("")
        L.extend(_md_table(["项目", "内容"], info_rows))
        L.append("")

    # 歌词
    lyric_sections = meta["sections"]
    if lyric_sections:
        L.append("## 歌词")
        L.append("")
        for section_name, sec_lines in lyric_sections:
            if section_name:
                L.append(f"### {section_name}")
                L.append("")
            if is_jp:
                L.extend(_md_table(["原文", "发音（罗马字）", "中文翻译"], sec_lines))
            else:
                L.extend(_md_table(["原文", "中文翻译"], sec_lines))
            L.append("")

    # 背景故事
    bg_paras = d.get("bg_paras", [])
    if bg_paras:
        L.append("## 背景故事")
        L.append("")
        for para in bg_paras:
            L.append(para)
            L.append("")

    # 语言学习
    vocab_table = d.get("vocab_table", [])
    grammar_points = d.get("grammar_points", [])
    culture_notes = d.get("culture_notes", [])
    if vocab_table or grammar_points or culture_notes:
        L.append("## 语言学习")
        L.append("")

    if vocab_table:
        L.append("### 核心词汇")
        L.append("")
        if _is_jp_vocab(vocab_table):
            L.extend(_md_table(["原文", "读音", "词性", "释义", "等级"], vocab_table))
        else:
            L.extend(_md_table(["单词/短语", "音标/发音提示", "词性", "释义", "难度"], vocab_table))
        L.append("")
        if d.get("vocab_note"):
            L.append(f"> {d['vocab_note']}")
            L.append("")

    if grammar_points:
        L.append("### 语法点")
        L.append("")
        for gp in grammar_points:
            name = gp.get("name", "")
            section = gp.get("section", "")
            quote = gp.get("quote", "")
            analysis = gp.get("analysis", "")
            extra = gp.get("extra", "")
            line = f"- **{name}**"
            if section or quote:
                sec = str(section).strip().strip("[]")
                prefix = f"[{sec}] " if sec else ""
                line += f"（出处 {prefix}「{quote}」）"
            if analysis:
                line += f"：{analysis}"
            if extra:
                line += f" {extra}"
            L.append(line)
            L.append("")

    if culture_notes:
        L.append("### 文化笔记")
        L.append("")
        for note in culture_notes:
            L.append(f"- {note}")
            L.append("")

    # 演唱技巧
    singing_tips = d.get("singing_tips", [])
    if singing_tips:
        L.append("## 演唱技巧")
        L.append("")
        for tip in singing_tips:
            name = tip.get("name", "")
            problem = tip.get("problem", "")
            solution = tip.get("solution", "")
            if name:
                L.append(f"- **{name}**：{problem}")
                L.append(f"  → {solution}")
            L.append("")

    # 附录
    sources_lyrics = d.get("sources_lyrics", [])
    sources_bg = d.get("sources_bg", [])
    if sources_lyrics or sources_bg:
        L.append("---")
        L.append("")
        L.append("## 附录")
        L.append("")
        if sources_lyrics:
            L.append("### 歌词来源")
            L.append("")
            for s in sources_lyrics:
                L.append(f"- {s}")
            L.append("")
        if sources_bg:
            L.append("### 背景信息来源")
            L.append("")
            for s in sources_bg:
                L.append(f"- {s}")
            L.append("")

    # 校验（统计从统一数据计算）
    stats = line_metrics(meta["lines"])
    comp = lyric_completeness(d, meta)
    L.append("---")
    L.append("")
    L.append("> 校验状态（分项）：")
    L.append(">")
    for line in verification_lines(d):
        L.append(f"> {line}")
    L.append(">")
    L.append(f"> 歌词覆盖（自统一数据计算）：{stats['occurrences']} 出现 / {stats['unique_source']} 唯一文本")
    L.append(f"> 首行：{comp['first_line']}")
    L.append(f"> 末行：{comp['last_line']}")
    L.append(f"> 段落：{' → '.join(comp['section_order'])}")
    if comp["repeated_sections"]:
        for r in comp["repeated_sections"]:
            L.append(f"> 重复段：{r}")
    L.append(f"> 来源引用关联：{comp['cited_lines']}/{comp['occurrences']} 行有逐行核验状态")
    L.append(f"> 实际与来源文本比对：{comp['text_compared']}")
    L.append("")

    md = "\n".join(L)
    if out_path is None:
        dirpath = os.path.dirname(json_path) or "."
        dirname = os.path.basename(os.path.normpath(dirpath))
        out_path = os.path.join(dirpath, dirname + ".md")
    atomic_replace(out_path, lambda tmp: open(tmp, "w", encoding="utf-8").write(md))
    print(f"OK: {out_path} ({os.path.getsize(out_path)} bytes)")
    return out_path


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
            songs.append((dj, os.path.join(sub, name + ".md")))
    return songs


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python build_md.py <json_data_file> [out.md]")
        print("  or: python build_md.py --all")
        sys.exit(1)

    if sys.argv[1] == "--all":
        root = os.environ.get("SONG_STUDY_DATA", r"E:\song-study")
        for json_path, out_path in _discover_songs(root):
            try:
                build_md(json_path, out_path)
            except Exception as e:
                print(f"FAIL: {json_path} -> {e}")
    else:
        json_path = sys.argv[1]
        out_path = sys.argv[2] if len(sys.argv) > 2 else None
        build_md(json_path, out_path)
