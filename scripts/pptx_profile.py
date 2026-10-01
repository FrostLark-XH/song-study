"""SongVisualProfile — per-song visual identity + 8 layout archetypes + rhythm.

The director model: build_profile() consumes a data.json `visual_profile` block
(the "director's note" written by Claude during song analysis) and falls back to
a mood-derived default when absent. Archetype selection is data-driven — each
emotionalCurve entry carries its own `arch` — never a hardcoded section→layout
map. L1–L8 are a toolbox of composition capabilities, not templates.
"""

from scripts.pptx_palette import resolve_theme, palette_for_dark_bg, THEME_PRESETS
from scripts.pptx_fonts import resolve_all
from scripts.pptx_motifs import normalize_spec

# ── Expanded geometry (larger effective visual area) ─────────────────────────
# Old: right safe area 85%, bottom margin 0.55in. New: 92% / 0.4in, tighter
# left margin, so lyrics claim more of the slide.

SLIDE_W_IN = 13.333
SLIDE_H_IN = 7.5
RIGHT_SAFE_FRACTION = 0.92
LEFT_MARGIN_IN = 1.0
BOTTOM_MARGIN_IN = 0.4

GEOMETRY = {
    "slide_w_in": SLIDE_W_IN,
    "slide_h_in": SLIDE_H_IN,
    "right_safe_fraction": RIGHT_SAFE_FRACTION,
    "left_margin_in": LEFT_MARGIN_IN,
    "bottom_margin_in": BOTTOM_MARGIN_IN,
}

# ── 8 layout archetypes (the toolbox) ─────────────────────────────────────────

ARCHETYPES = [
    {"id": "L1", "name": "Editorial Left",    "desc": "左对齐顶部起排，经典编辑式"},
    {"id": "L2", "name": "Centered Title",    "desc": "居中大字强调，副歌高潮"},
    {"id": "L3", "name": "Asymmetric Right",  "desc": "右对齐，不对称张力"},
    {"id": "L4", "name": "Indent + Drop Cap", "desc": "左缩进 + 首行大字，章节感"},
    {"id": "L5", "name": "Two-Column Stagger","desc": "错位两列，节奏断裂"},
    {"id": "L6", "name": "Ghost Full",        "desc": "巨型 ghost text 主导，极简"},
    {"id": "L7", "name": "Framed Quote",      "desc": "居中金句 + 琥珀短划线"},
    {"id": "L8", "name": "Outro Fade",        "desc": "文字缩小下沉，渐隐收束"},
]

ARCHETYPE_BY_ID = {a["id"]: a for a in ARCHETYPES}

# ── Director field defaults (fallback when data.json has no visual_profile) ──

_DEFAULT_DIRECTOR = {
    "mood": "neutral",
    "energy": 0.5,
    "darkness": 0.3,
    "warmth": 0.4,
    "drama": 0.5,
    "nostalgia": 0.5,
    "density": 0.55,
    "keywords": [],
    "imagery": "",
    "typographyDirection": "mincho",
    "paletteDirection": "paper",
    "compositionDirection": "editorial",
    "textureDirection": "soft_grain",
    "accentPresence": 0.0,
    "dynamicRange": 0.3,
    "visualMotifs": ["vertical_rule", "number"],
}

# typographyDirection → font role (resolved from CANDIDATES in pptx_fonts.py)
_TYPO_FONT_ROLE = {
    "mincho": "jp",
    "gothic": "gothic",
    "sans": "gothic",
    "mono": "mono",
}


def _derive_energy(section_name: str) -> tuple[float, float]:
    """Fallback (energy, darkness) for a section from its structural role."""
    s = (section_name or "").lower()
    if "intro" in s:
        return 0.15, 0.10
    if "outro" in s or "coda" in s or "ending" in s:
        return 0.20, 0.25
    if "verse" in s:
        return 0.40, 0.30
    if "pre" in s:
        return 0.55, 0.35
    if "bridge" in s:
        return 0.60, 0.65  # dark inversion point
    if "final" in s and "chorus" in s:
        return 0.90, 0.35
    if "chorus" in s or "hook" in s or "refrain" in s:
        return 0.75, 0.30
    return 0.45, 0.30


def _derive_default_arch(section_name: str, verse_index: int) -> str:
    """Fallback archetype for a section when no director curve is provided.

    This is a *default*, not a rule — the real director writes an explicit arch
    per section in visual_profile.emotionalCurve. Only a safety net.
    """
    s = (section_name or "").lower()
    if "intro" in s:
        return "L6"
    if "verse" in s:
        return "L1" if verse_index == 0 else "L4"
    if "pre" in s:
        return "L3"
    if "bridge" in s:
        return "L7"
    if "final" in s and "chorus" in s:
        return "L2"
    if "chorus" in s or "hook" in s or "refrain" in s:
        return "L2"
    if "outro" in s or "post" in s or "coda" in s or "ending" in s:
        return "L8"
    return "L1"


def _extract_artist(d: dict) -> str:
    info = {row[0]: row[1] for row in d.get("info_rows", [])}
    return info.get("演唱者", info.get("作曲", info.get("歌手", "")))


def _default_visual_profile(d: dict) -> dict:
    """Build a fallback director profile from mood + section structure.

    paletteDirection inherits the legacy mood key when it names a known preset,
    so old songs keep their look. emotionalCurve is derived from section roles.
    """
    vp = dict(_DEFAULT_DIRECTOR)
    mood = d.get("mood")
    vp["mood"] = mood
    if mood in THEME_PRESETS:
        vp["paletteDirection"] = mood

    curve = []
    verse_index = 0
    for sname, lines in d.get("lyric_sections", []):
        if not lines:
            continue
        energy, darkness = _derive_energy(sname)
        arch = _derive_default_arch(sname, verse_index)
        curve.append({"section": sname, "energy": energy,
                      "darkness": darkness, "arch": arch})
        if "verse" in (sname or "").lower():
            verse_index += 1
    vp["emotionalCurve"] = curve
    return vp


def _motif_types(raw) -> list[str]:
    """Normalize visualMotifs to a list of type strings.

    Accepts both the object form (``[{"type", "reason"}, ...]`` — the director's
    documented note) and the legacy string form (``["circle", "number"]``), so
    old songs keep building while new songs carry a per-motif reason.
    """
    if not raw:
        return []
    types = []
    for m in raw:
        if isinstance(m, dict):
            t = m.get("type")
            if t:
                types.append(t)
        elif isinstance(m, str) and m.strip():
            types.append(m.strip())
    return types


def _motif_reasons(raw) -> dict[str, str]:
    """Collect ``{type: reason}`` from object-form motifs for the review report."""
    out = {}
    if raw:
        for m in raw:
            if isinstance(m, dict) and m.get("type"):
                out[m["type"]] = m.get("reason", "")
    return out


def _type_spec(typo: str, drama: float, energy: float) -> dict:
    """Typography spec — weight/tracking/size-span/crop from song personality.

    Gothic/sans fonts become bold + tight-tracked under high drama/energy;
    size_span widens the font-size contrast for dramatic songs; allow_crop lets
    aggressive songs bleed decorative elements past the safe edge. Calm mincho
    songs keep the default (so 白日 stays untouched).
    """
    aggressive = typo in ("gothic", "sans")
    return {
        "bold": aggressive and (drama >= 0.55 or energy >= 0.6),
        "tracking": -0.7 if (aggressive and energy >= 0.7) else 0.0,
        "size_span": 1.0 + 0.30 * drama,
        "allow_crop": aggressive and (drama >= 0.7 or energy >= 0.7),
        "aggressive": aggressive,
    }


def _song_seed(d: dict) -> int:
    """Deterministic per-song seed from the title, for motif spec defaults."""
    import zlib
    title = str(d.get("title", "song"))
    return zlib.crc32(title.encode("utf-8")) & 0x7FFFFFFF


def _normalize_assets(raw_assets, seed: int) -> dict:
    """Normalize a visual_assets block into {direction, base, sections, warnings}.

    Each spec is validated/filled via normalize_spec; unknown-type or non-dict
    entries are skipped and recorded in `warnings` (surfaced in the build report).
    `sections` stays keyed by the exact lyric-section name so the per-page resolver
    can look it up; sections absent from the director's note simply yield no extra
    specs (no auto-fill).
    """
    empty = {"direction": "", "base": [], "sections": {}, "warnings": []}
    if not isinstance(raw_assets, dict):
        return empty

    warnings: list[str] = []

    def norm_list(specs) -> list:
        out = []
        for s in (specs or []):
            n = normalize_spec(s, seed)
            if n is None:
                warnings.append(f"visual_assets: 跳过非法 spec {s!r}")
            else:
                out.append(n)
        return out

    base = norm_list(raw_assets.get("base", []))
    sections = {}
    raw_sections = raw_assets.get("sections")
    if isinstance(raw_sections, dict):
        for name, specs in raw_sections.items():
            sections[name] = norm_list(specs)

    return {
        "direction": raw_assets.get("direction", ""),
        "base": base,
        "sections": sections,
        "warnings": warnings,
    }


def resolve_page_specs(assets: dict | None, section_name: str) -> list[dict]:
    """Return the ordered motif specs for one page: base + that section's specs."""
    if not isinstance(assets, dict):
        return []
    base = assets.get("base", []) or []
    sections = assets.get("sections", {}) or {}
    extra = sections.get(section_name, []) or []
    return base + extra


# ── Page Composition Intent (intra-section page variation) ────────────────────

ROLES = {"introduce", "continue", "build", "pause", "contrast", "resolve", "peak"}
RELATIONSHIPS = {"support", "lead", "cross", "frame", "divide", "recede", "expand"}


def _normalize_page_intents(raw) -> tuple[dict, list[str]]:
    """Normalize visual_assets.pageIntents into {section: [intent, ...]}.

    Validates role/relationship against the enums (illegal values fall back to
    ``continue``/``recede`` and record a warning). focus/reason default to "".
    The list length is *not* forced to match the section's page count — the
    resolver clamps by index instead (deterministic, not a rotation).
    """
    warnings: list[str] = []
    out: dict = {}
    if not isinstance(raw, dict):
        return out, warnings
    for name, lst in raw.items():
        if not isinstance(lst, list):
            continue
        norm = []
        for item in lst:
            if not isinstance(item, dict):
                continue
            role = item.get("role", "continue")
            if role not in ROLES:
                warnings.append(f"pageIntents: 非法 role {role!r} → continue")
                role = "continue"
            rel = item.get("relationship", "recede")
            if rel not in RELATIONSHIPS:
                warnings.append(f"pageIntents: 非法 relationship {rel!r} → recede")
                rel = "recede"
            norm.append({"role": role, "relationship": rel,
                         "focus": str(item.get("focus", "")),
                         "reason": str(item.get("reason", ""))})
        out[name] = norm
    return out, warnings


def resolve_page_intent(assets: dict | None, section_name: str, page_index: int) -> dict | None:
    """Return the single intent for one page, clamping index to the last entry.

    Returns None when the section has no pageIntents (old-song fallback → all
    roles/relationships inherit, no geometry transform).
    """
    intents = (assets or {}).get("pageIntents", {}) or {}
    lst = intents.get(section_name) or []
    if not lst:
        return None
    return lst[min(page_index, len(lst) - 1)]


def build_profile(d: dict) -> dict:
    """Build a SongVisualProfile from a parsed data.json.

    Consumes an explicit `visual_profile` block if present (director's note),
    else a mood-derived fallback. Returns a flat dict with the original palette/
    font/geometry plus the director fields (mood…visualMotifs).
    """
    title = d.get("title", "song").replace("歌曲学习：", "")
    artist = _extract_artist(d)

    # 1. Director note (explicit) or mood-derived default
    raw = d.get("visual_profile")
    if raw is None:
        vp = _default_visual_profile(d)
    else:
        vp = dict(_DEFAULT_DIRECTOR)
        vp.update(raw)
        if not vp.get("emotionalCurve"):
            vp["emotionalCurve"] = _default_visual_profile(d)["emotionalCurve"]

    # 2. Palette: paletteDirection (if a known preset) > legacy mood > bg_color
    pal_dir = vp.get("paletteDirection")
    mood_key = pal_dir if pal_dir in THEME_PRESETS else d.get("mood")
    bg_color = d.get("bg_color")
    bg, pal = resolve_theme(mood_key, bg_color)
    accent = pal.get("ACCENT", "C49A5C")

    # director override: 强调色 (accent) 是导演决策，可偏离预设的灰金琥珀
    if vp.get("accent"):
        accent = str(vp["accent"]).lstrip("#")
        pal["ACCENT"] = accent

    dark_bg = "1C1E1F"
    dark_pal = palette_for_dark_bg(dark_bg)
    if vp.get("accent"):
        dark_pal["ACCENT"] = str(vp["accent"]).lstrip("#")

    # 3. Fonts: typographyDirection overrides the JP body font role
    fonts = resolve_all(verbose=True)
    typo = vp.get("typographyDirection", "mincho")
    body_role = _TYPO_FONT_ROLE.get(typo, "jp")
    if body_role != "jp":
        from scripts.pptx_fonts import resolve_font
        fonts["jp"] = resolve_font(body_role, verbose=True)

    # 4. Procedural visual assets (director's executable spec layer)
    assets = _normalize_assets(d.get("visual_assets"), _song_seed(d))
    page_intents, intent_warnings = _normalize_page_intents(
        (d.get("visual_assets") or {}).get("pageIntents"))
    assets["pageIntents"] = page_intents
    assets["warnings"].extend(intent_warnings)

    return {
        "title": title,
        "artist": artist,
        "mood_key": mood_key,
        "bg": bg,
        "palette": pal,
        "dark_bg": dark_bg,
        "dark_palette": dark_pal,
        "accent": accent,
        "font": fonts,
        "geometry": dict(GEOMETRY),
        # director fields
        "mood": vp.get("mood"),
        "energy": vp.get("energy", 0.5),
        "darkness": vp.get("darkness", 0.3),
        "warmth": vp.get("warmth", 0.4),
        "drama": vp.get("drama", 0.5),
        "nostalgia": vp.get("nostalgia", 0.5),
        "density": vp.get("density", 0.55),
        "keywords": vp.get("keywords", []),
        "imagery": vp.get("imagery", ""),
        "emotionalCurve": vp.get("emotionalCurve", []),
        "typographyDirection": typo,
        "type_spec": _type_spec(typo, vp.get("drama", 0.5), vp.get("energy", 0.5)),
        "paletteDirection": pal_dir,
        "compositionDirection": vp.get("compositionDirection", "editorial"),
        "textureDirection": vp.get("textureDirection", "soft_grain"),
        "accentPresence": vp.get("accentPresence", 0.0),
        "dynamicRange": vp.get("dynamicRange", 0.3),
        "visualMotifs": _motif_types(vp.get("visualMotifs", [])),
        "visualMotifReasons": _motif_reasons(vp.get("visualMotifs", [])),
        # procedural engine
        "visual_assets": assets,
        "asset_warnings": assets["warnings"],
    }
