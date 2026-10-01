#!/usr/bin/env python3
"""Unified data.json loader + normalizer for song-study.

Single source of truth that MD / DOCX / PPTX all consume, so the three outputs
can't drift. Two jobs, both concentrated here instead of re-implemented per
builder:

1. **Legacy adaptation** — map old field shapes onto the current schema
   (vocab_rows→vocab_table, tuple grammar_points/culture_notes/singing_tips→
   dict/string forms). New builders only ever read the current shapes.
2. **Line records** — expose persisted per-line IDs. New songs carry an
   explicit `id` on every lyric line; frozen baselines (bare 2/3-tuples) get a
   *derived* position-based ID flagged `derived=True` so validation warns
   rather than errors. This module never re-derives IDs for songs that already
   have them.
"""

import hashlib
import json

VALID_LANGUAGES = ("ja", "en", "zh", "mixed")


def load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def detect_language(d: dict):
    """Return ``(language, explicit)``.

    The explicit ``language`` field wins; ``mixed`` maps to the JP three-column
    path (jp/romaji/zh). Bare-tuple column count is the legacy fallback and is
    flagged ``explicit=False`` so validation can nudge migration. An explicit
    value outside the supported set is *not* silently remapped — the loader
    stays alive on the JP path so ``validate_schema`` can report it as an error,
    but the ``explicit`` flag preserves the fact that the field was present.
    """
    lang = d.get("language")
    if lang is not None:
        l = str(lang).strip().lower()
        if l in ("ja", "mixed"):
            return "ja", True
        if l == "en":
            return "en", True
        if l == "zh":
            return "zh", True
        return "ja", True  # unsupported explicit value — validate_schema errors
    ls = d.get("lyric_sections", [])
    if ls and ls[0][1] and isinstance(ls[0][1][0], (list, tuple)):
        return ("ja" if len(ls[0][1][0]) == 3 else "en"), False
    return "ja", False


def adapt_legacy(d: dict) -> dict:
    """Map old field shapes onto the current schema in place. Idempotent."""
    if d.get("vocab_rows") and not d.get("vocab_table"):
        d["vocab_table"] = d["vocab_rows"]

    gps = d.get("grammar_points")
    if gps and isinstance(gps[0], (list, tuple)):
        d["grammar_points"] = [
            {"name": g[0], "analysis": g[1] if len(g) > 1 else ""} for g in gps
        ]

    cns = d.get("culture_notes")
    if cns and isinstance(cns[0], (list, tuple)):
        d["culture_notes"] = [
            (f"{c[0]}：{c[1]}" if len(c) > 1 else str(c[0])) for c in cns
        ]

    sts = d.get("singing_tips")
    if sts and isinstance(sts[0], (list, tuple)):
        d["singing_tips"] = [
            {"name": s[0], "problem": s[1] if len(s) > 1 else "",
             "solution": s[2] if len(s) > 2 else ""} for s in sts
        ]
    return d


def compute_fingerprint(line_records: list) -> str:
    """SHA-256 (first 16 hex) of the normalized lyric text in order.

    Covers jp/romaji/zh (or en/zh) so that *any* text edit — original, reading,
    or translation — changes the fingerprint and flags the relevant verification
    as stale. Position/size-only changes (visual_profile, bg_color) do not touch
    it.
    """
    parts = []
    for r in line_records:
        jp = (r.get("jp") or r.get("en") or "").strip()
        rm = r.get("romaji") or ""
        zh = r.get("zh") or ""
        parts.append(f"{jp}\t{rm}\t{zh}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def _line_tuple(ln, language: str):
    """Return (renderer_tuple, id_or_None, derived)."""
    if isinstance(ln, dict):
        if language == "en":
            return [ln.get("en", ""), ln.get("zh", "")], ln.get("id"), False
        return [ln.get("jp", ""), ln.get("romaji", ""), ln.get("zh", "")], \
            ln.get("id"), False
    return list(ln), None, True


def load_song(path: str) -> tuple[dict, dict]:
    """Return (data, meta).

    `data` keeps the raw top-level keys (after legacy adaptation) so validation
    can still see structural breaks. `meta["sections"]` carries the normalized
    2/3-tuple form the renderers consume, and `meta["lines"]` the persisted line
    IDs — so renderers never need to know about dict-form lines.
    """
    d = adapt_legacy(load(path))
    language, language_explicit = detect_language(d)

    sections, line_records = [], []
    derived_count = 0
    for sec in d.get("lyric_sections", []):
        if not isinstance(sec, (list, tuple)) or len(sec) != 2:
            continue  # structural break — validate_schema reports it as an error
        sname, lines = sec
        if not isinstance(lines, list):
            continue
        out_lines = []
        for idx, ln in enumerate(lines):
            tup, lid, derived = _line_tuple(ln, language)
            out_lines.append(tup)
            if lid is None:
                lid = f"{sname}:L{idx + 1:02d}"
                derived = True
            if derived:
                derived_count += 1
            rec = {"section": sname, "id": lid, "derived": derived}
            if language == "en":
                rec["en"], rec["zh"] = tup[0], tup[1]
            else:
                rec["jp"], rec["romaji"], rec["zh"] = tup
            line_records.append(rec)
        sections.append([sname, out_lines])

    meta = {
        "language": language,
        "language_explicit": language_explicit,
        "sections": sections,
        "lines": line_records,
        "derived_id_count": derived_count,
        "fingerprint": compute_fingerprint(line_records),
    }
    return d, meta
