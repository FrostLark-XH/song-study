"""Font resolver with graceful fallback for lyric cards.

The old code hard-coded fonts that may not exist on the target machine
(Yu Mincho Demibold, Adobe Caslon Pro) — PowerPoint then silently falls back
to a system default, wrecking the design. This module maps a *role* to an
ordered list of (family_name, [font-file substrings]) and returns the first
family whose font file is present in C:\\Windows\\Fonts, so the embedded
family name is always a real installed font.
"""

import os
import subprocess
from functools import lru_cache

FONT_DIR = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")

# role -> ordered candidates: (family_name, [lowercase file-name substrings])
CANDIDATES = {
    "jp": [
        ("Yu Mincho Demibold", ["yumindb", "yumindemibold", "yumindemib", "yumincho-demibold"]),
        ("Yu Mincho", ["yumincho", "yumin"]),
        ("MS Mincho", ["msmincho"]),
        ("Noto Serif CJK JP", ["notoserifcjkjp", "notoserifcjk"]),
    ],
    "gothic": [
        ("Meiryo", ["meiryo"]),
        ("Yu Gothic UI", ["yugothu", "yugothicui", "yu gothic ui"]),
        ("MS Gothic", ["msgothic"]),
        ("Noto Sans CJK JP", ["notosanscjkjp", "notosanscjk"]),
    ],
    "mono": [
        ("Courier New", ["cour"]),
        ("Consolas", ["consola"]),
        ("DejaVu Sans Mono", ["dejavusansmono.ttf"]),
    ],
    "furigana": [
        ("MS Gothic", ["msgothic"]),
        ("Noto Sans CJK JP", ["notosanscjkjp", "notosanscjk"]),
        ("Meiryo", ["meiryo"]),
    ],
    "romaji": [
        ("Courier New", ["cour"]),
        ("Consolas", ["consola"]),
        ("DejaVu Sans Mono", ["dejavusansmono.ttf"]),
    ],
    "cn": [
        ("Noto Serif CJK SC", ["notoserifcjk", "noto serif cjk"]),
        ("Source Han Serif SC", ["sourcehanserif", "source han serif"]),
        ("SimSun", ["simsun"]),
        ("Microsoft YaHei", ["msyh"]),
        ("Noto Sans CJK SC", ["notosanscjksc", "notosanscjk"]),
    ],
    "en": [
        ("Adobe Caslon Pro Semibold", ["acaslonpro-semibold", "acaslonpro_semibold"]),
        ("Georgia", ["georgia"]),
        ("Times New Roman", ["times"]),
        ("DejaVu Serif", ["dejavuserif.ttf"]),
    ],
}


@lru_cache(maxsize=1)
def _font_inventory():
    """Actual installed families and paths; never pretend a missing font exists."""
    rows = []
    try:
        result = subprocess.run(["fc-list", "--format", "%{family}\t%{file}\n"],
                                capture_output=True, text=True, timeout=15, check=True)
        for line in result.stdout.splitlines():
            if "\t" in line:
                families, path = line.split("\t", 1)
                rows.extend((f.strip(), path) for f in families.split(","))
    except (OSError, subprocess.SubprocessError):
        pass
    for directory in (FONT_DIR, os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts")):
        if os.path.isdir(directory):
            rows.extend(("", os.path.join(directory, f)) for f in sorted(os.listdir(directory)))
    return tuple(rows)


def _resolve(role):
    if role not in CANDIDATES:
        raise ValueError(f"Unknown font role: {role}")
    inventory = _font_inventory()
    for family, subs in CANDIDATES[role]:
        # Exact families take precedence over filename matching for TTC collections.
        for name, path in inventory:
            if name.casefold() == family.casefold():
                return family, path
        for name, path in inventory:
            if not name and any(sub in os.path.basename(path).lower() for sub in subs):
                return family, path
    raise RuntimeError(f"No installed font for {role}. Install Noto CJK JP/SC or Windows CJK fonts.")


def resolve_font(role, verbose=True):
    family, _ = _resolve(role)
    if verbose:
        print(f"  [font] {role}: {family}")
    return family


def resolve_all(verbose=True):
    return {role: resolve_font(role, verbose) for role in CANDIDATES}


def resolve_font_file(role):
    return _resolve(role)[1]
