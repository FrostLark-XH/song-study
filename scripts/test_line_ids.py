#!/usr/bin/env python3
"""Line-ID stability tests: insert / reorder / cross-section move / text correction.

Proves persisted per-line IDs survive all four edit operations, so verification
metadata keyed by ID always follows the original line. `scripts/dataload.py`
never re-derives an ID for a line that already carries one — this test pins that
contract so it can't regress. Run: `python scripts/test_line_ids.py`. Exit 0 = pass.
"""

import os
import sys
import json
import copy
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.dataload import load_song
from scripts.validate import check_ids


def _mini():
    return {
        "schema_version": "2.1",
        "title": "line-id-test",
        "language": "ja",
        "lyric_sections": [
            ["[Verse 1]", [
                {"id": "[Verse 1]:L01", "jp": "あ", "romaji": "a", "zh": "阿"},
                {"id": "[Verse 1]:L02", "jp": "い", "romaji": "i", "zh": "伊"},
                {"id": "[Verse 1]:L03", "jp": "う", "romaji": "u", "zh": "宇"},
            ]],
            ["[Chorus]", [
                {"id": "[Chorus]:L01", "jp": "え", "romaji": "e", "zh": "欸"},
                {"id": "[Chorus]:L02", "jp": "お", "romaji": "o", "zh": "哦"},
            ]],
        ],
        "verification": {
            "status": "已核验",
            "lines": {
                "[Verse 1]:L01": "已核验", "[Verse 1]:L02": "已核验",
                "[Verse 1]:L03": "已核验", "[Chorus]:L01": "已核验",
                "[Chorus]:L02": "已核验",
            },
        },
    }


def _load(d):
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    try:
        return load_song(path)
    finally:
        os.unlink(path)


def _ids_by_jp(meta):
    return {r["jp"]: r["id"] for r in meta["lines"]}


failures = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f" — {detail}" if detail else ""))
    if not cond:
        failures.append(name)


def main(argv):
    # Baseline: all IDs persisted, none derived.
    _, meta0 = _load(_mini())
    check("baseline 无派生 ID", meta0["derived_id_count"] == 0,
          f"derived={meta0['derived_id_count']}")
    check("baseline 行数", len(meta0["lines"]) == 5, f"lines={len(meta0['lines'])}")

    # 1. Insert: new line mid-section with a fresh, previously-unused ID.
    d = copy.deepcopy(_mini())
    d["lyric_sections"][0][1].insert(
        2, {"id": "[Verse 1]:L02b", "jp": "う?", "romaji": "u?", "zh": "宇?"})
    _, meta = _load(d)
    before, after = _ids_by_jp(meta0), _ids_by_jp(meta)
    for jp in ("あ", "い", "う", "え", "お"):
        check(f"插行后原行 ID 稳定 {jp!r}", after.get(jp) == before.get(jp),
              f"{before.get(jp)} -> {after.get(jp)}")
    check("新行分配到独立未用 ID",
          any(r["jp"] == "う?" and r["id"] == "[Verse 1]:L02b" for r in meta["lines"]))
    check("插行后无派生 ID", meta["derived_id_count"] == 0)

    # 2. Reorder: swap first and third lines within a section.
    d = copy.deepcopy(_mini())
    sec = d["lyric_sections"][0][1]
    sec[0], sec[2] = sec[2], sec[0]
    _, meta = _load(d)
    ids = _ids_by_jp(meta)
    check("换序后 ID 跟随内容（あ 仍 L01）", ids.get("あ") == "[Verse 1]:L01",
          ids.get("あ"))
    check("换序后 ID 跟随内容（う 仍 L03）", ids.get("う") == "[Verse 1]:L03",
          ids.get("う"))

    # 3. Cross-section move: pull a line out of [Verse 1] into [Chorus].
    d = copy.deepcopy(_mini())
    moved = d["lyric_sections"][0][1].pop(2)  # jp う, id [Verse 1]:L03
    d["lyric_sections"][1][1].append(moved)
    _, meta = _load(d)
    r = next(r for r in meta["lines"] if r["jp"] == "う")
    check("跨段移动后 ID 不变", r["id"] == "[Verse 1]:L03",
          f"id={r['id']} section={r['section']}")
    check("跨段移动后 section 跟随新位置", r["section"] == "[Chorus]",
          f"section={r['section']}")
    check("核验元数据随 ID 跟随原行",
          d["verification"]["lines"].get("[Verse 1]:L03") == "已核验")

    # 4. Text correction: fix the jp text of a line, keep the ID.
    d = copy.deepcopy(_mini())
    d["lyric_sections"][0][1][1]["jp"] = "イ"  # corrected glyph
    _, meta = _load(d)
    r = next(r for r in meta["lines"] if r["id"] == "[Verse 1]:L02")
    check("文字纠错后 ID 不变", r["jp"] == "イ" and r["id"] == "[Verse 1]:L02",
          f"jp={r['jp']} id={r['id']}")
    check("文字纠错后核验状态仍跟随该 ID",
          d["verification"]["lines"].get("[Verse 1]:L02") == "已核验")

    # 5. Duplicate-ID guard: reusing an existing ID must be caught as an error.
    d = copy.deepcopy(_mini())
    d["lyric_sections"][0][1].insert(
        0, {"id": "[Verse 1]:L01", "jp": "重", "romaji": "重", "zh": "重"})
    _, meta = _load(d)
    _, errs = check_ids(meta["lines"], d["verification"])
    check("重复 ID 被 check_ids 记为 error", any("重复" in e for e in errs),
          str(errs))

    # 6. Real-data sanity: 群青 repeated-refrain occurrences carry independent IDs.
    gunjou = argv[0] if argv else r"E:\song-study\YOASOBI_群青\data.json"
    if os.path.isfile(gunjou):
        _, gm = _load(json.load(open(gunjou, encoding="utf-8")))
        ref_ids = [r["id"] for r in gm["lines"] if r.get("jp") == "知らず知らず隠してた"]
        check("重复副歌每次出现使用独立 ID", len(ref_ids) == len(set(ref_ids)) == 3,
              f"ids={ref_ids}")
        check("群青全行 ID 无重复",
              len({r['id'] for r in gm['lines']}) == len(gm['lines']))
        check("群青无派生 ID", gm["derived_id_count"] == 0,
              f"derived={gm['derived_id_count']}")

    print()
    if failures:
        print(f"FAIL: {len(failures)} failed -> {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
