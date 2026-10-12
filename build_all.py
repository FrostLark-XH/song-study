#!/usr/bin/env python3
"""One-shot generator: MD + DOCX from a single data.json (PPTX opt-in).

Default build emits MD + DOCX. Pass --pptx to also build the editable PPTX
deck, or --preview to emit a representative-page PPTX preview instead of the
full deck. All builders consume the same scripts.dataload.load_song() result,
so the outputs share one normalized data contract. Canonical paths:
  - MD   : <song_dir>/<dir_name>.md
  - DOCX : <song_dir>/<dir_name>.docx
  - PPTX : <song_dir>/<title>.pptx   (title as build_pptx derives it)
"""

import sys
import os

sys.stdout.reconfigure(encoding="utf-8")

from build_md import build_md
from build_docx import build_docx
from build_pptx import build_pptx


def _canonical_paths(json_path):
    from scripts.dataload import load
    d = load(json_path)
    title = d.get("title", "song").replace("歌曲学习：", "")
    dirpath = os.path.dirname(json_path) or "."
    dirname = os.path.basename(os.path.normpath(dirpath))
    return {
        "md": os.path.join(dirpath, dirname + ".md"),
        "docx": os.path.join(dirpath, dirname + ".docx"),
        "pptx": os.path.join(dirpath, title + ".pptx"),
    }


def build_all(json_path, preview=False, include_pptx=False):
    paths = _canonical_paths(json_path)
    if preview:
        # Never replace the complete deck with a representative-page preview.
        p = paths["pptx"]
        folder = os.path.join(os.path.dirname(p), "_preview")
        target = os.path.join(folder, os.path.splitext(os.path.basename(p))[0] + "_preview.pptx")
        build_pptx(json_path, target, preview=True)
        return {"pptx": target}
    jobs = [
        ("md", lambda: build_md(json_path, paths["md"])),
        ("docx", lambda: build_docx(json_path, paths["docx"])),
    ]
    if include_pptx:
        jobs.append(("pptx", lambda: build_pptx(json_path, paths["pptx"], preview=False)))
    results = {}
    for fmt, run in jobs:
        try:
            run()
            results[fmt] = "OK"
        except SystemExit as e:
            results[fmt] = "OK" if not e.code else "FAIL（数据校验 errors）"
        except Exception as e:
            results[fmt] = f"FAIL（{e}）"

    ok = [f for f, s in results.items() if s == "OK"]
    fail = [f for f, s in results.items() if s != "OK"]
    print(f"[build_all] 成功: {', '.join(ok) or '无'}   失败: {', '.join(fail) or '无'}")
    for f, s in results.items():
        if s != "OK":
            print(f"[build_all] {f}: {s}（保留旧文件，未被覆盖）")
    if fail:
        sys.exit(1)
    return paths


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
            songs.append(dj)
    return songs


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python build_all.py <json_data_file> [--pptx] [--preview]")
        print("  or: python build_all.py --all [--pptx] [--preview]")
        print("  Default: MD + DOCX. --pptx adds the editable PPTX deck.")
        print("  --preview emits a representative-page PPTX preview (implies PPTX).")
        sys.exit(1)

    args = sys.argv[1:]
    preview = "--preview" in args
    include_pptx = "--pptx" in args or preview
    args = [a for a in args if a not in ("--preview", "--pptx")]

    if args[0] == "--all":
        root = os.environ.get("SONG_STUDY_DATA", r"E:\song-study")
        for json_path in _discover_songs(root):
            try:
                print(f"\n=== {json_path} ===")
                build_all(json_path, preview=preview, include_pptx=include_pptx)
            except Exception as e:
                print(f"FAIL: {json_path} -> {e}")
    else:
        build_all(args[0], preview=preview, include_pptx=include_pptx)
