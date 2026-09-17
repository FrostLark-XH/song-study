"""Unified low-saturation color palette for lyric card PPT.

Paper-textured, film-like, quiet, artistic — NOT business/cartoon/high-saturation.

Text colors adapt to the background: same hue direction, different lightness depths
calibrated for WCAG contrast ratios. This keeps text from blending into the paper.
"""

from pptx.dml.color import RGBColor


def rgb(hex_str: str) -> RGBColor:
    return RGBColor.from_string(hex_str)


# ── Default palette (for #C5CDD4 background) ──────────────────────────────────

TEXT_JP = "1A1D24"          # Deep ink (always near-black, max contrast)
TEXT_FURIGANA = "444444"
TEXT_ROMAJI = "7A8088"
TEXT_CN = "9A9288"
TEXT_SECTION = "B0A89E"
ACCENT_AMBER = "C49A5C"


# ── WCAG 2.0 contrast ─────────────────────────────────────────────────────────

def _luminance(hex_str: str) -> float:
    """Relative luminance per WCAG 2.0 sRGB formula."""
    r = int(hex_str[0:2], 16) / 255
    g = int(hex_str[2:4], 16) / 255
    b = int(hex_str[4:6], 16) / 255
    r = r / 12.92 if r <= 0.03928 else ((r + 0.055) / 1.055) ** 2.4
    g = g / 12.92 if g <= 0.03928 else ((g + 0.055) / 1.055) ** 2.4
    b = b / 12.92 if b <= 0.03928 else ((b + 0.055) / 1.055) ** 2.4
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    l1 = _luminance(fg)
    l2 = _luminance(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def _darker_for_contrast(bg_hex: str, target_cr: float) -> str:
    """Blend background toward black until target contrast ratio is met.

    Preserves the background's warm/cool character in the result.
    """
    bg_r = int(bg_hex[0:2], 16)
    bg_g = int(bg_hex[2:4], 16)
    bg_b = int(bg_hex[4:6], 16)

    lo, hi = 0.0, 1.0
    best = "000000"
    for _ in range(30):
        mid = (lo + hi) / 2
        r = int(bg_r * (1 - mid))
        g = int(bg_g * (1 - mid))
        b = int(bg_b * (1 - mid))
        h = f"{r:02x}{g:02x}{b:02x}"
        if contrast_ratio(h, bg_hex) >= target_cr:
            best = h
            hi = mid
        else:
            lo = mid
    return best


def palette_for_bg(bg_hex: str) -> dict[str, str]:
    """Return text palette adapted to a background color.

    TEXT_JP stays near-black for maximum legibility. Other levels are
    progressively lighter, each targeting a WCAG contrast floor:
      furigana ≥ 7:1, romaji ≥ 4.5:1, CN ≥ 3:1, section ≥ 2:1.
    """
    return {
        "TEXT_JP": "1A1D24",
        "TEXT_FURIGANA": _darker_for_contrast(bg_hex, 7.0),
        "TEXT_ROMAJI": _darker_for_contrast(bg_hex, 4.5),
        "TEXT_CN": _darker_for_contrast(bg_hex, 3.0),
        "TEXT_SECTION": _darker_for_contrast(bg_hex, 2.0),
    }


# ── Mood-based theme presets ──────────────────────────────────────────────────
# Each preset is a complete color system calibrated for a song mood.
# Users pick a mood key instead of hand-picking a bg_color hex.

THEME_PRESETS: dict[str, dict[str, str]] = {
    "moon_white": {
        "label": "月白",
        "desc": "清新/电子/轻快 — 冷灰蓝底，安静克制",
        "bg": "C5CDD4",
        "text_jp": "1A1D24",
        "text_furigana": "4A4E54",
        "text_romaji": "7A8088",
        "text_cn": "9A9288",
        "text_section": "B0A89E",
        "text_footer": "8A8480",
    },
    "warm_rice": {
        "label": "暖米",
        "desc": "温暖/治愈/民谣 — 暖米底，柔和亲近",
        "bg": "C8B8B0",
        "text_jp": "1E1A18",
        "text_furigana": "4E4844",
        "text_romaji": "807870",
        "text_cn": "9A8E84",
        "text_section": "B0A498",
        "text_footer": "8A8078",
    },
    "dark_ink": {
        "label": "暗墨",
        "desc": "暗黑/戏剧/摇滚 — 深灰底，强烈对比",
        "bg": "9E9790",
        "text_jp": "0E0D0C",
        "text_furigana": "383430",
        "text_romaji": "6A625C",
        "text_cn": "8A827A",
        "text_section": "A09890",
        "text_footer": "706860",
    },
    "faded_leaf": {
        "label": "朽葉",
        "desc": "复古/爵士/怀旧 — 茶褐底，旧纸温暖",
        "bg": "C4B8A8",
        "text_jp": "1C1814",
        "text_furigana": "4C4640",
        "text_romaji": "7E7670",
        "text_cn": "988E84",
        "text_section": "AEA498",
        "text_footer": "887E76",
    },
    "mist_purple": {
        "label": "紫苑",
        "desc": "悲伤/抒情/慢歌 — 灰紫底，沉静内敛",
        "bg": "B0AAB5",
        "text_jp": "18161C",
        "text_furigana": "44414A",
        "text_romaji": "746E7A",
        "text_cn": "928A94",
        "text_section": "A8A0AA",
        "text_footer": "827A84",
    },
}


def resolve_theme(mood_key: str | None, bg_color: str | None) -> tuple[str, dict[str, str]]:
    """Resolve mood key or bg_color to a complete theme palette.

    Priority: mood_key > bg_color. If mood_key matches a preset, use it.
    Otherwise adapt from bg_color via palette_for_bg(). Falls back to moon_white.

    Returns (resolved_bg_hex, text_palette_dict).
    """
    if mood_key and mood_key in THEME_PRESETS:
        preset = THEME_PRESETS[mood_key]
        return preset["bg"], {
            "TEXT_JP": preset["text_jp"],
            "TEXT_FURIGANA": preset["text_furigana"],
            "TEXT_ROMAJI": preset["text_romaji"],
            "TEXT_CN": preset["text_cn"],
            "TEXT_SECTION": preset["text_section"],
            "TEXT_FOOTER": preset["text_footer"],
        }
    if mood_key:
        bg = mood_key.lstrip("#")
    elif bg_color:
        bg = bg_color.lstrip("#")
    else:
        bg = "C5CDD4"
    pal = palette_for_bg(bg)
    pal["TEXT_FOOTER"] = _darker_for_contrast(bg, 3.0)
    return bg, pal
