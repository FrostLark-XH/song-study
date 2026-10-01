"""Visual Critic — 8 programmatic checks + deterministic parameter nudge.

The critic reads the object model + spec metadata, not rendered pixels (this
model cannot see images). It separates mechanical FAILs — provable structure
defects with a deterministic nudge — from semantic WARNs that need the
director's judgment. Final aesthetic quality is still decided by human eyes on
the montage.

Checks (1–6, 8 are mechanical; 7 is a semantic WARN):
  1. page similarity         — adjacent pages near-identical → FAIL
  2. motif over-repetition   — one type >50% or ≥3 same-type pages in a row
  3. visual climax exists    — max-energy page intensity must exceed median
  4. template feel           — spec params with ~zero variance → FAIL
  5. meaningless whitespace  — sparse page with no localized anchor → FAIL
  6. over-decoration         — low-energy page out-decorates the average chorus
  7. font↔song personality   — WARN heuristic, no auto-fix
  8. emotionalCurve on-slide — Pearson(intensity, energy) < 0.5 → FAIL

`nudge_specs` applies a bounded, deterministic, seed-free transform (fixed
offsets, clamps) — never random — then the build re-renders once and stops.
"""

from collections import Counter

import numpy as np

from scripts.pptx_layouts import SLIDE_W_EMU, SLIDE_H_EMU, BOTTOM_MARGIN_EMU

# The paper texture — present on every page, constant, full-canvas. It's the
# substrate, not the brushwork, so it's excluded from the "contentful motif"
# signal. Section-level atmosphere (gradient_field/soft_haze/light_band) IS
# contentful: it varies per section and carries the composition's color weight.
_FULL_CANVAS = {"paper_grain"}


# ── Per-page feature extraction ───────────────────────────────────────────────

def _contentful(specs):
    return [s for s in specs if s["type"] not in _FULL_CANVAS]


def _geom_sig(spec):
    """Geometry signature: type + binned position/size/rotation/opacity.

    Bins are coarse enough that a relationship transform (which moves a stroke
    by ~0.1–0.2 or shifts opacity by ~0.15) registers as a *different* page,
    while an identical page (same type, same placement) collapses to one bin.
    """
    return (
        spec.get("type", ""),
        round(spec.get("x", 0.5), 1),
        round(spec.get("y", 0.5), 1),
        round(spec.get("width", 0.4), 1),
        round(spec.get("height", 0.1), 1),
        round(spec.get("angle", 0.0) / 15.0),
        round(spec.get("opacity", 1.0), 1),
    )


def _intensity(specs, max_fs=0.0):
    """Motif area×opacity + a font-size factor (bigger lyric = more weight)."""
    total = 0.0
    for s in specs:
        total += max(0.0, s.get("width", 0.0)) * max(0.0, s.get("height", 0.0)) * s.get("opacity", 0.0)
    return total + (max_fs / 64.0) * 0.30


def _slide_stats(slide):
    """Text coverage (textbox area / slide area) and max non-footer font size."""
    safe_bottom = SLIDE_H_EMU - BOTTOM_MARGIN_EMU
    slide_area = SLIDE_W_EMU * SLIDE_H_EMU
    area = 0.0
    max_fs = 0.0
    for shape in slide.shapes:
        if not getattr(shape, "has_text_frame", False):
            continue
        if not shape.text_frame.text.strip():
            continue
        if shape.top >= safe_bottom:
            continue  # footer lives in the bottom margin by design
        area += shape.width * shape.height
        for p in shape.text_frame.paragraphs:
            for r in p.runs:
                if r.font.size is not None:
                    max_fs = max(max_fs, r.font.size.pt)
    return area / slide_area, max_fs


def _extract(pages, resolved_specs, prs):
    feats = []
    for i, (_s, arch, _g, energy, _d, _sl) in enumerate(pages):
        specs = resolved_specs[i] if i < len(resolved_specs) else []
        cov, max_fs = _slide_stats(prs.slides[i + 1])
        contentful = _contentful(specs)
        hist = Counter(s["type"] for s in contentful)
        geom = Counter(_geom_sig(s) for s in contentful)
        dominant = geom.most_common(1)[0][0] if geom else None
        feats.append({
            "arch": arch, "energy": energy, "specs": specs,
            "hist": hist, "geom": geom, "dominant": dominant,
            "cov": cov, "max_fs": max_fs,
            "intensity": _intensity(specs, max_fs),
            "anchor": bool(contentful),
        })
    return feats


# ── The 8 checks ──────────────────────────────────────────────────────────────

def _check_similarity(feats):
    n = len(feats)
    if n < 2:
        return "PASS", "page similarity: too few pages to compare"
    similar = 0
    for a, b in zip(feats, feats[1:]):
        if a["arch"] != b["arch"]:
            continue
        keys = set(a["geom"]) | set(b["geom"])
        if keys:
            dot = sum(a["geom"].get(k, 0) * b["geom"].get(k, 0) for k in keys)
            na = sum(v * v for v in a["geom"].values()) ** 0.5
            nb = sum(v * v for v in b["geom"].values()) ** 0.5
            cos = dot / (na * nb + 1e-9) if na and nb else 1.0
        else:
            cos = 1.0
        if cos > 0.85 and abs(a["cov"] - b["cov"]) < 0.15:
            similar += 1
    frac = similar / (n - 1)
    ok = frac <= 0.6
    return ("PASS" if ok else "FAIL",
            f"page similarity: {similar}/{n-1} adjacent pairs near-identical ({frac:.0%})")


def _check_repetition(feats):
    all_hist = Counter()
    for f in feats:
        all_hist.update(f["hist"])
    total = sum(all_hist.values())
    if total == 0:
        return "PASS", "motif repetition: no contentful motifs"
    top_type, top_n = all_hist.most_common(1)[0]
    dom_frac = top_n / total
    # consecutive run of the same (type + geometry) signature — only truly
    # identical pages chain, not pages that merely share a motif type
    run = best = 1
    prev = None
    for f in feats:
        cur = f["dominant"]
        if cur is not None and cur == prev:
            run += 1
        else:
            run = 1
        best = max(best, run)
        prev = cur
    ok = dom_frac <= 0.5 and best < 3
    msg = (f"motif repetition: '{top_type}' {dom_frac:.0%} of contentful motifs, "
           f"longest same-geometry run {best}")
    return ("PASS" if ok else "FAIL", msg)


def _check_climax(feats):
    if len(feats) < 2:
        return "PASS", "visual climax: too few pages"
    energies = [f["energy"] for f in feats]
    i_max = int(np.argmax(energies))
    intensities = [f["intensity"] for f in feats]
    med = float(np.median(intensities))
    peak = intensities[i_max]
    ok = peak > med
    return ("PASS" if ok else "FAIL",
            f"visual climax: peak-energy page intensity {peak:.3f} vs median {med:.3f}")


def _check_template(feats):
    specs = [s for f in feats for s in f["specs"]]
    if len(specs) < 3:
        return "PASS", "template feel: too few specs"
    for key in ("x", "y", "width", "height", "angle", "opacity"):
        vals = np.array([float(s.get(key, 0.0)) for s in specs])
        if vals.std() > 0.03:
            return "PASS", "template feel: params vary"
    return "FAIL", "template feel: spec params have ~zero variance"


def _check_whitespace(feats):
    for f in feats:
        if f["anchor"]:
            continue
        if f["energy"] < 0.45 and f["cov"] < 0.30:
            return "FAIL", (f"whitespace: sparse page (cov {f['cov']:.0%}, "
                            f"energy {f['energy']:.2f}) has no localized anchor")
        if f["energy"] >= 0.6 and f["cov"] < 0.45:
            return "FAIL", (f"whitespace: sparse chorus (cov {f['cov']:.0%}, "
                            f"energy {f['energy']:.2f}) has no localized anchor")
    return "PASS", "whitespace: content coverage vs anchors balanced"


def _check_overdecoration(feats):
    chorus = [f for f in feats if f["energy"] >= 0.65]
    if not chorus:
        return "PASS", "over-decoration: no chorus to compare against"
    # Visual weight = area × opacity, so a faint large ghost doesn't read as
    # heavy decoration the way a saturated block does.
    def weight(specs):
        return sum(s["width"] * s["height"] * s.get("opacity", 0.0)
                   for s in _contentful(specs))
    avg_chorus = float(np.mean([weight(f["specs"]) for f in chorus]))
    for f in feats:
        if f["energy"] < 0.45:
            w = weight(f["specs"])
            if w > avg_chorus + 0.05:
                return "FAIL", (f"over-decoration: low-energy page weight {w:.3f} "
                                f"exceeds chorus avg {avg_chorus:.3f}")
    return "PASS", f"over-decoration: low-energy pages ≤ chorus avg ({avg_chorus:.3f})"


def _check_font_personality(profile):
    typo = profile.get("typographyDirection", "mincho")
    dyn = profile.get("dynamicRange", 0.3)
    curve = profile.get("emotionalCurve", [])
    energies = [c.get("energy", 0.5) for c in curve] or [0.5]
    max_e = max(energies)
    if max_e >= 0.7 and typo in ("mincho",) and dyn < 0.3:
        return "WARN", "font↔song: calm mincho on a high-energy song (字体偏安静)"
    if max_e < 0.4 and typo in ("gothic", "sans"):
        return "WARN", "font↔song: aggressive gothic on a calm song (攻击性字体)"
    return "PASS", f"font↔song: '{typo}' fits (max energy {max_e:.2f}, dyn {dyn:.2f})"


def _check_curve(feats):
    if len(feats) < 3:
        return "PASS", "emotionalCurve: too few pages for correlation"
    energies = np.array([f["energy"] for f in feats], dtype=float)
    intensities = np.array([f["intensity"] for f in feats], dtype=float)
    if energies.std() < 1e-6 or intensities.std() < 1e-6:
        return "PASS", "emotionalCurve: flat energy/intensity (no signal)"
    r = float(np.corrcoef(energies, intensities)[0, 1])
    ok = r >= 0.5
    return ("PASS" if ok else "FAIL", f"emotionalCurve: Pearson(intensity, energy) r={r:.2f}")


_CHECKS = [
    ("similarity", _check_similarity),
    ("repetition", _check_repetition),
    ("climax", _check_climax),
    ("template", _check_template),
    ("whitespace", _check_whitespace),
    ("overdecoration", _check_overdecoration),
    ("font_personality", _check_font_personality),
    ("curve", _check_curve),
]


# ── Deterministic nudge ───────────────────────────────────────────────────────

def nudge_specs(resolved_specs, pages, failures):
    """Apply a bounded, deterministic transform to the resolved specs.

    Fixed offsets and clamps only — no randomness, no seed. Returns a deep copy
    so the original director spec is never mutated. The build re-renders once
    with this, then stops regardless of the second critique.
    """
    import copy
    out = copy.deepcopy(resolved_specs)
    energies = [p[3] for p in pages]

    if "climax" in failures or "curve" in failures:
        i_max = int(np.argmax(energies))
        for spec in out[i_max]:
            spec["opacity"] = round(min(1.0, spec["opacity"] + 0.15), 2)

    if "repetition" in failures:
        seen = {}
        for specs in out:
            for spec in specs:
                t = spec["type"]
                k = seen.get(t, 0)
                seen[t] = k + 1
                if k > 0:
                    spec["angle"] = spec.get("angle", 0.0) + 12.0 * (k % 3)
                    spec["x"] = round(min(1.0, spec.get("x", 0.5) + 0.07 * (k % 2)), 2)

    if "overdecoration" in failures:
        for i, (specs, e) in enumerate(zip(out, energies)):
            if e < 0.45:
                for spec in specs:
                    if spec["type"] not in _FULL_CANVAS:
                        spec["opacity"] = round(max(0.0, spec["opacity"] - 0.15), 2)

    if "whitespace" in failures:
        for specs in out:
            for spec in specs:
                if spec["type"] in ("light_band", "soft_haze", "gradient_field"):
                    spec["opacity"] = round(min(1.0, spec["opacity"] + 0.12), 2)

    return out


# ── Orchestrator ──────────────────────────────────────────────────────────────

def critique(pages, resolved_specs, profile, prs):
    """Run all 8 checks; print a report; return (ok, failures, report_lines).

    `resolved_specs` is a list (parallel to `pages`) of per-page spec lists.
    Returns ok=False if any mechanical check fails; semantic WARNs do not flip
    `ok`. The engine-mode gate is left to the caller (build_pptx) — here we just
    report, and a deck with no contentful specs still yields mechanical PASS on
    the motif-dependent checks via their empty-guards.
    """
    feats = _extract(pages, resolved_specs, prs)

    lines = []
    failures = set()
    for key, fn in _CHECKS:
        if key == "font_personality":
            verdict, msg = fn(profile)
        else:
            verdict, msg = fn(feats)
        if verdict == "FAIL":
            failures.add(key)
        lines.append(f"  [{verdict:4s}] {msg}")

    # strength curve for the report (readable, not a decision)
    energies = [f["energy"] for f in feats]
    intensities = [f["intensity"] for f in feats]
    lines.append(f"  strength: energies {[round(e, 2) for e in energies]}")
    lines.append(f"           intensity {[round(i, 2) for i in intensities]}")

    ok = not failures

    print(f"\n{'='*60}")
    print(f"  VISUAL CRITIC")
    print(f"{'='*60}")
    for ln in lines:
        print(ln)
    print(f"  result: {'PASS' if ok else 'FAIL'} "
          f"({'机械 FAIL' if failures else '无机械问题'})")
    print(f"{'='*60}\n")
    return ok, failures, lines
