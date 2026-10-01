#!/usr/bin/env python3
"""Schema + coverage + line-ID + output validation for song-study data.json.

Separates *errors* (structural breakage, duplicate/mismatched line IDs, missing
lyrics — these must block delivery) from *warnings* (old-schema drift that still
builds but should be migrated). Exit code reflects errors only.

Line-count metrics are reported in three distinct buckets so the stale "62 行"
class of claim can't recur:
  - occurrences   — every sung line, repeats included (what renderers consume)
  - unique_source — de-duplicated original-text lines (the "real" lyric count)
  - split_rows    — render-time row splits (reported by build_pptx, not here)
"""

import sys
import os
import json
from collections import Counter

VALID_LANGUAGES = {"ja", "en", "zh", "mixed"}
VERIFY_STATUSES = {"已核验", "局部待核验", "文本不完整", "未获取到", "使用范围受限", "待核验"}
CHECK_LABELS = {
    "song_version": "歌曲及版本识别",
    "lyric_text": "歌词来源与文本比对",
    "reading_translation": "注音及翻译检查",
    "structure": "文件结构检查",
    "render": "渲染是否成功",
    "visual": "人工视觉检查",
}

try:
    from scripts.dataload import load_song
except ImportError:  # running as `python scripts/validate.py` directly
    from dataload import load_song


def _is_jp_line(line) -> bool:
    return isinstance(line, (list, tuple)) and len(line) == 3


def validate_schema(d: dict, lines=None, language=None) -> tuple[list[str], list[str]]:
    """Return (warnings, errors) for structural/schema problems in d.

    `language` is the detected language from dataload (used to know whether
    dict-form lines carry jp/romaji/zh vs en/zh). Omit to treat as JP.
    """
    warnings: list[str] = []
    errors: list[str] = []

    if "schema_version" not in d:
        warnings.append("缺 schema_version 字段（旧 schema，建议补 \"2.1\"）")
    if "language" not in d:
        warnings.append("缺 language 字段，将从列数启发式推导（建议显式写 ja/en/zh/mixed）")
    elif d["language"] not in VALID_LANGUAGES:
        errors.append(f"language 非法值 {d['language']!r}，应为 {sorted(VALID_LANGUAGES)}")

    for req in ("title", "lyric_sections"):
        if not d.get(req):
            errors.append(f"缺必填字段 {req!r}")

    ls = d.get("lyric_sections")
    if isinstance(ls, list):
        for i, sec in enumerate(ls):
            if not isinstance(sec, (list, tuple)) or len(sec) != 2:
                errors.append(f"lyric_sections[{i}] 不是 [段名, [行...]] 结构")
                continue
            name, lines_in_sec = sec
            if not name or not str(name).strip():
                errors.append(f"lyric_sections[{i}] 段名为空")
            if not isinstance(lines_in_sec, list) or not lines_in_sec:
                warnings.append(f"段 {name!r} 无歌词行")
                continue
            arities = {len(ln) for ln in lines_in_sec if isinstance(ln, (list, tuple, dict))}
            tuple_arities = {len(ln) for ln in lines_in_sec if isinstance(ln, (list, tuple))}
            if len(tuple_arities) > 1:
                errors.append(f"段 {name!r} 行 arity 不一致 {sorted(tuple_arities)}")
            for j, ln in enumerate(lines_in_sec):
                if isinstance(ln, dict):
                    need = ("jp", "romaji", "zh") if language != "en" else ("en", "zh")
                    for k in need:
                        if not ln.get(k) or not str(ln[k]).strip():
                            warnings.append(f"段 {name!r} 第{j}行字段 {k!r} 为空")
                elif isinstance(ln, (list, tuple)):
                    if any(not isinstance(c, str) or not c.strip() for c in ln):
                        warnings.append(f"段 {name!r} 第{j}行有空白字段")
                else:
                    errors.append(f"段 {name!r} 第{j}行不是列表/元组/对象")

    info = d.get("info_rows")
    if isinstance(info, list):
        for i, row in enumerate(info):
            if not isinstance(row, (list, tuple)) or len(row) != 2:
                warnings.append(f"info_rows[{i}] 不是 [键, 值] 成对结构")

    v = d.get("verification")
    if v is not None:
        if not isinstance(v, dict):
            warnings.append("verification 应为对象")
        else:
            checks = v.get("checks")
            if not isinstance(checks, dict) or not checks:
                warnings.append("verification 缺 checks（6 项分项检查），旧 schema 建议补")
            else:
                for key, label in CHECK_LABELS.items():
                    ch = checks.get(key)
                    if not isinstance(ch, dict) or not ch.get("status"):
                        warnings.append(f"verification.checks 缺分项 {label} ({key!r})")
                    elif ch["status"] not in VERIFY_STATUSES:
                        warnings.append(
                            f"verification.checks.{key} status {ch['status']!r} "
                            f"不在标准状态词表 {sorted(VERIFY_STATUSES)}")
            if not v.get("fingerprint"):
                warnings.append("verification 缺 fingerprint（内容指纹），建议补以便检测文本变更")

    if lines is not None:
        if not lines:
            errors.append("歌词缺失：lyric_sections 无任何歌词行")
        else:
            w, e = check_ids(lines, v if isinstance(v, dict) else None)
            warnings.extend(w)
            errors.extend(e)

    return warnings, errors


def check_ids(lines, verification) -> tuple[list[str], list[str]]:
    """Validate persisted line IDs: duplicates / empties are errors.

    Frozen baselines (bare tuples → derived IDs) only warn, never error.
    `lines` is the meta["lines"] list from dataload.load_song.
    """
    warnings: list[str] = []
    errors: list[str] = []
    derived = [r for r in lines if r.get("derived")]
    persisted = [r for r in lines if not r.get("derived")]

    if derived:
        warnings.append(
            f"{len(derived)} 行无持久化 ID（旧 schema，运行时按行号派生，建议补显式 id 字段）")

    seen = Counter(r["id"] for r in lines)
    dup = {i: n for i, n in seen.items() if n > 1}
    for i, n in dup.items():
        errors.append(f"行 ID 重复 {i!r} 出现 {n} 次")

    for r in persisted:
        if not r.get("id") or not str(r["id"]).strip():
            errors.append(f"段 {r['section']!r} 有持久化行缺 id 字段")

    # verification.lines keys must reference real line IDs (mismatch = error).
    if verification and isinstance(verification.get("lines"), dict):
        vlines = verification["lines"]
        ids = {r["id"] for r in lines}
        for lid in vlines:
            if lid not in ids:
                errors.append(f"verification.lines 引用了不存在的行 ID {lid!r}")
        missing = [r["id"] for r in persisted if r["id"] not in vlines]
        if missing:
            warnings.append(
                f"verification.lines 缺 {len(missing)} 行的逐行核验状态（如 {missing[0]!r}）")
    return warnings, errors


def check_coverage(d: dict) -> tuple[int, list[str]]:
    """Return (total_line_count, warnings) about dup/empty/coverage."""
    warnings: list[str] = []
    total = 0
    for sec in d.get("lyric_sections", []):
        if not isinstance(sec, (list, tuple)) or len(sec) != 2:
            continue
        name, lines = sec
        if not isinstance(lines, list):
            continue
        total += len(lines)
        prev_jp = None
        for j, ln in enumerate(lines):
            if isinstance(ln, dict):
                jp = ln.get("jp") or ln.get("en")
            elif _is_jp_line(ln):
                jp = ln[0]
            elif isinstance(ln, (list, tuple)) and len(ln) == 2:
                jp = ln[0]
            else:
                continue
            if prev_jp == jp:
                warnings.append(f"段 {name!r} 第{j}行与上一行原文重复: {jp!r}")
            prev_jp = jp
    if total == 0:
        warnings.append("歌词总行数为 0")
    return total, warnings


def line_metrics(lines) -> dict:
    """Return {occurrences, unique_source} from the persisted line records."""
    occurrences = len(lines)
    unique = len({(r.get("jp") or r.get("en") or "").strip() for r in lines})
    return {"occurrences": occurrences, "unique_source": unique}


def lyric_completeness(d: dict, meta: dict) -> dict:
    """Completeness signals beyond raw counts: first/last line, section order,
    repeated sections, and source coverage.

    Returns facts for the verification render. None is a hard pass/fail on its
    own — structural breakage is caught by validate_schema/check_ids. The point
    here is to surface what a bare line count hides: whether the song actually
    starts and ends where it should, which sections repeat (and whether the
    repeat is identical or varied). Two *separate* coverage numbers are exposed:
    `cited_lines` (how many lines carry a per-line verification entry — citation
    association) and `text_compared` (a hand-recorded field stating whether the
    line text was actually compared against a retrieved source). A non-empty
    citation is NOT content verification; the two must never be conflated.
    """
    lines = meta.get("lines", [])
    occurrences = len(lines)
    unique = len({(r.get("jp") or r.get("en") or "").strip() for r in lines})

    first = last = None
    if lines:
        f, l = lines[0], lines[-1]
        first = f"{f['section']}　{(f.get('jp') or f.get('en') or '').strip()}"
        last = f"{l['section']}　{(l.get('jp') or l.get('en') or '').strip()}"

    sections = meta.get("sections", [])
    section_order = [s[0] for s in sections if s and s[0]]

    sec_texts = {}
    for sname, slines in sections:
        jp_set = set()
        for tup in slines:
            if isinstance(tup, (list, tuple)) and tup:
                t = str(tup[0]).strip()
                if t:
                    jp_set.add(t)
        sec_texts[sname] = jp_set

    repeats = []
    names = section_order
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = sec_texts.get(names[i], set()), sec_texts.get(names[j], set())
            if not a or not b:
                continue
            inter = len(a & b)
            small = min(len(a), len(b))
            if small and inter / small >= 0.5:
                kind = "完全相同" if a == b else "有变化"
                repeats.append(f"{names[i]} ≈ {names[j]}（{inter}/{small} 行重合，{kind}）")

    ver = d.get("verification")
    lyrics_src = []
    vlines = {}
    text_compared = None
    if isinstance(ver, dict):
        lyrics_src = (ver.get("lyrics") or {}).get("sources", [])
        vlines = ver.get("lines", {}) or {}
        text_compared = (ver.get("lyrics") or {}).get("text_compared")
    if not text_compared:
        text_compared = "未记录（无逐行文本比对说明）"
    cited = sum(1 for r in lines if r.get("id") in vlines)

    return {
        "occurrences": occurrences,
        "unique_source": unique,
        "first_line": first,
        "last_line": last,
        "section_order": section_order,
        "repeated_sections": repeats,
        "source_count": len(lyrics_src),
        "cited_lines": cited,
        "text_compared": text_compared,
    }


def check_outputs(song_dir: str) -> list[str]:
    """Check that .md/.docx/.pptx exist and are non-empty in song_dir."""
    problems: list[str] = []
    if not os.path.isdir(song_dir):
        return [f"输出目录不存在: {song_dir}"]
    for ext in ("md", "docx", "pptx"):
        found = [f for f in os.listdir(song_dir) if f.endswith("." + ext)]
        if not found:
            problems.append(f"缺 .{ext}")
        elif all(os.path.getsize(os.path.join(song_dir, f)) == 0 for f in found):
            problems.append(f".{ext} 文件为空")
    return problems


def check_fingerprint(d: dict, meta: dict) -> list[str]:
    """Warn when the persisted verification fingerprint no longer matches the
    current lyric text (a text edit happened after verification). Position /
    size-only changes don't affect the fingerprint."""
    warnings: list[str] = []
    v = d.get("verification")
    if not isinstance(v, dict):
        return warnings
    stored = v.get("fingerprint")
    if not stored:
        return warnings
    current = meta.get("fingerprint")
    if current and stored != current:
        warnings.append(
            f"内容指纹不匹配（已存 {stored}，当前 {current}）："
            "歌词/注音/翻译自核验后已变更，lyric_text 与 reading_translation 检查可能过期，需重新核验")
    return warnings


def verification_lines(d: dict) -> list[str]:
    """Concise per-check verification status lines for the formal outputs.

    Renders the six separate checks (not one collapsed verdict) so a reader
    sees exactly which dimension was verified and to what level. Old data with
    only prose ``verify_text`` falls back to that single line.
    """
    ver = d.get("verification")
    if not isinstance(ver, dict):
        if d.get("verify_text"):
            return [str(d["verify_text"])]
        return []

    lines: list[str] = []
    checks = ver.get("checks")
    if isinstance(checks, dict):
        for key, label in CHECK_LABELS.items():
            ch = checks.get(key)
            if not isinstance(ch, dict):
                continue
            st = ch.get("status", "")
            if not st:
                continue
            line = f"{label}：{st}"
            note = ch.get("note", "")
            if note:
                line += f"（{note}）"
            lines.append(line)
    license_ = ver.get("license", "")
    if license_:
        lines.append("使用范围：" + license_)
    fp = ver.get("fingerprint")
    if fp:
        lines.append("内容指纹：" + fp)
    return lines


def main(argv: list[str]) -> int:
    if not argv:
        print("Usage: python scripts/validate.py <data.json> [song_dir]")
        return 1
    d, meta = load_song(argv[0])
    warnings, errors = validate_schema(d, meta["lines"], meta["language"])
    total, cov = check_coverage(d)
    m = line_metrics(meta["lines"])
    comp = lyric_completeness(d, meta)

    print(f"VALIDATE: {d.get('title', '(无标题)')}")
    print(f"  演唱出现次数: {m['occurrences']}   源歌词唯一文本行数: {m['unique_source']}")
    print(f"  首行: {comp['first_line']}")
    print(f"  末行: {comp['last_line']}")
    print(f"  段落: {' → '.join(comp['section_order'])}")
    for r in comp["repeated_sections"]:
        print(f"  [repeat] {r}")
    print(f"  来源引用关联: {comp['cited_lines']}/{comp['occurrences']} 行有逐行核验状态")
    print(f"  实际文本比对: {comp['text_compared']}")
    for line in verification_lines(d):
        print(f"  [check] {line}")
    for w in check_fingerprint(d, meta):
        print(f"  [warn] {w}")
    for w in warnings:
        print(f"  [warn] {w}")
    for c in cov:
        print(f"  [warn] {c}")
    for e in errors:
        print(f"  [ERROR] {e}")
    if len(argv) > 1:
        for p in check_outputs(argv[1]):
            print(f"  [warn] {p}")
    print(f"  result: {'FAIL' if errors else 'PASS'} (warnings 不阻断)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
