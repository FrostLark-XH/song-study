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
