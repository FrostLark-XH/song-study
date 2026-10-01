"""Procedural motif library — 15 parameterized visual primitives + compositor.

The "Procedural Visual Engine": each motif is a function that turns one
parameterized spec (type/color/opacity/x/y/width/height/angle/roughness/
density/blur/seed) into a full-canvas RGBA layer. Layers are composited
(alpha / screen / multiply / overlay) onto a base background. Nothing here is
random: every motif is fully determined by its seed, and every spec is written
by the Visual Director in data.json `visual_assets` — the engine only renders,
it never invents decoration.
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import gaussian_filter, zoom

W, H = 1920, 1080

MOTIF_TYPES = {
    "dry_brush", "wet_brush", "paint_smear", "irregular_color_block",
    "soft_haze", "light_band", "paper_grain", "ink_bleed", "broken_line",
    "geometric_grid", "halftone", "oversized_glyph", "rough_edge",
    "blur_blob", "gradient_field",
}

# Natural blend for each primitive: light-emitting motifs screen, darkening ones
# multiply, texture overlays, the rest plain alpha. A spec may override via
# `blend`.
DEFAULT_BLEND = {
    "soft_haze": "screen", "light_band": "screen", "gradient_field": "screen",
    "paper_grain": "overlay", "ink_bleed": "multiply",
    "dry_brush": "alpha", "wet_brush": "alpha", "paint_smear": "alpha",
    "irregular_color_block": "alpha", "broken_line": "alpha",
    "geometric_grid": "alpha", "halftone": "alpha",
    "oversized_glyph": "alpha", "rough_edge": "alpha", "blur_blob": "alpha",
}

_DEFAULTS = {"opacity": 0.5, "roughness": 0.4, "density": 0.5, "blur": 0.0}

_MESH_CACHE = {}


def _mesh():
    if "m" not in _MESH_CACHE:
        ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
        _MESH_CACHE["m"] = (xs, ys)
    return _MESH_CACHE["m"]


def _hex_rgb(hex_str: str):
    h = hex_str.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _rgb_float(hex_str: str) -> np.ndarray:
    return np.array(_hex_rgb(hex_str), dtype=np.float32)


def _norm_hex(hex_str) -> str:
    h = str(hex_str).lstrip("#")
    if len(h) != 6 or any(c not in "0123456789abcdefABCDEF" for c in h):
        return "808080"
    return h.upper()


def _noise(rng: np.random.Generator, shape, freq: int) -> np.ndarray:
    small = rng.uniform(0, 1, size=(freq + 1, freq + 1)).astype(np.float32)
    return zoom(small, (shape[0] / small.shape[0], shape[1] / small.shape[1]),
                order=3)


def _octaves(rng, shape, octaves=3, base=6, persistence=0.5) -> np.ndarray:
    result = np.zeros(shape, dtype=np.float32)
    amp, freq, total = 1.0, base, 0.0
    for _ in range(octaves):
        result += _noise(rng, shape, freq) * amp
        total += amp
        amp *= persistence
        freq *= 2
    return result / total


def _layer(color: np.ndarray, mask: np.ndarray, opacity: float,
           rgb_override: np.ndarray | None = None) -> np.ndarray:
    """Pack a constant color + coverage mask into an RGBA layer (0-255 float).

    Alpha = mask * opacity; RGB = color (spatially constant unless overridden).
    """
    mask = np.clip(mask, 0.0, 1.0).astype(np.float32)
    a = mask * opacity * 255.0
    if rgb_override is None:
        rgb = np.broadcast_to(color[None, None, :],
                              (mask.shape[0], mask.shape[1], 3)).astype(np.float32)
    else:
        rgb = rgb_override.astype(np.float32)
    return np.dstack([rgb, a])


# ── Renderers ────────────────────────────────────────────────────────────────

def _dry_brush(spec, rng):
    """N thin parallel streaks (density) with perlin-broken edges (roughness)."""
    xs, ys = _mesh()
    color = _rgb_float(spec["color"])
    n = max(2, int(3 + spec["density"] * 8))
    cx, cy = spec["x"] * W, spec["y"] * H
    half_w, half_h = spec["width"] * W * 0.5, spec["height"] * H * 0.5
    base_ang = np.radians(spec["angle"])
    rough = spec["roughness"]
    noise = _octaves(rng, (H // 4, W // 4), octaves=3, base=6, persistence=0.5)
    noise = zoom(noise, (4, 4), order=2)[:H, :W].astype(np.float32)
    mask = np.zeros((H, W), np.float32)
    for _ in range(n):
        jx = rng.uniform(-1, 1) * half_w * 0.7
        jy = rng.uniform(-1, 1) * half_h * 0.5
        ang = base_ang + rng.uniform(-1, 1) * 0.10 * rough
        xr = (xs - (cx + jx)) * np.cos(ang) + (ys - (cy + jy)) * np.sin(ang)
        yr = -(xs - (cx + jx)) * np.sin(ang) + (ys - (cy + jy)) * np.cos(ang)
        sx = half_w * (0.5 + 0.5 * rng.uniform())
        sy = half_h * (0.5 + 0.5 * rng.uniform())
        g = np.exp(-(xr / sx) ** 2 * 0.5) * np.exp(-(yr / sy) ** 2 * 4.0)
        g = g * (1.0 - rough * 0.6 + rough * 0.6 * noise)
        mask += np.clip(g, 0.0, None)
    return _layer(color, np.clip(mask / max(1.0, n * 0.5), 0, 1), spec["opacity"])


def _wet_brush(spec, rng):
    """One wide soft stroke; blur softens it, roughness pools pigment at edges."""
    xs, ys = _mesh()
    color = _rgb_float(spec["color"])
    cx, cy = spec["x"] * W, spec["y"] * H
    half_w, half_h = spec["width"] * W * 0.5, spec["height"] * H * 0.5
    ang = np.radians(spec["angle"])
    xr = (xs - cx) * np.cos(ang) + (ys - cy) * np.sin(ang)
    yr = -(xs - cx) * np.sin(ang) + (ys - cy) * np.cos(ang)
    core = np.exp(-(xr / half_w) ** 2 * 0.6) * np.exp(-(yr / half_h) ** 2 * 2.0)
    core = gaussian_filter(core, sigma=2.0 + spec["blur"] * 6.0)
    edge = gaussian_filter(np.abs(np.gradient(core, axis=1))
                           + np.abs(np.gradient(core, axis=0)), sigma=3.0)
    mask = np.clip(core + edge * 0.5 * (1.0 - spec["roughness"]), 0, 1)
    return _layer(color, mask, spec["opacity"])


def _paint_smear(spec, rng):
    """Elongated color dragged along its angle; roughness displaces the drag."""
    xs, ys = _mesh()
    color = _rgb_float(spec["color"])
    cx, cy = spec["x"] * W, spec["y"] * H
    half_w, half_h = spec["width"] * W * 0.5, spec["height"] * H * 0.5
    ang = np.radians(spec["angle"])
    noise = _octaves(rng, (H // 4, W // 4), octaves=3, base=5, persistence=0.55)
    noise = zoom(noise, (4, 4), order=2)[:H, :W].astype(np.float32)
    xr = (xs - cx) * np.cos(ang) + (ys - cy) * np.sin(ang)
    yr = -(xs - cx) * np.sin(ang) + (ys - cy) * np.cos(ang)
    drag = (noise - 0.5) * spec["roughness"] * half_w * 0.8
    core = np.exp(-((xr + drag) / half_w) ** 2 * 0.7) * np.exp(-(yr / half_h) ** 2 * 2.0)
    mask = np.clip(gaussian_filter(core, sigma=1.5 + spec["blur"] * 4.0), 0, 1)
    return _layer(color, mask, spec["opacity"])


def _irregular_color_block(spec, rng):
    """Flat block whose boundary is displaced by noise (roughness)."""
    xs, ys = _mesh()
    color = _rgb_float(spec["color"])
    cx, cy = spec["x"] * W, spec["y"] * H
    half_w, half_h = spec["width"] * W * 0.5, spec["height"] * H * 0.5
    ang = np.radians(spec["angle"])
    noise = _octaves(rng, (H // 4, W // 4), octaves=3, base=5, persistence=0.5)
    noise = zoom(noise, (4, 4), order=2)[:H, :W].astype(np.float32)
    xr = (xs - cx) * np.cos(ang) + (ys - cy) * np.sin(ang)
    yr = -(xs - cx) * np.sin(ang) + (ys - cy) * np.cos(ang)
    d = np.abs(xr) / half_w + np.abs(yr) / half_h
    boundary = 1.0 + spec["roughness"] * (noise - 0.5) * 0.8
    mask = np.clip((boundary - d) * 4.0, 0, 1)
    return _layer(color, gaussian_filter(mask, sigma=0.5 + spec["blur"] * 2.0),
                  spec["opacity"])


def _soft_haze(spec, rng):
    """Large radial soft color wash (screen)."""
    xs, ys = _mesh()
    color = _rgb_float(spec["color"])
    cx, cy = spec["x"] * W, spec["y"] * H
    rx, ry = spec["width"] * W * 0.5, spec["height"] * H * 0.5
    d = ((xs - cx) / rx) ** 2 + ((ys - cy) / ry) ** 2
    mask = gaussian_filter(np.exp(-d * 1.5), sigma=3.0 + spec["blur"] * 8.0)
    return _layer(color, mask, spec["opacity"])


def _light_band(spec, rng):
    """Diagonal light band whose brightness climbs along its rise axis."""
    xs, ys = _mesh()
    color = _rgb_float(spec["color"])
    ang = np.radians(spec["angle"] if spec["angle"] else -45)
    proj = xs * np.cos(ang) + ys * np.sin(ang)
    proj = (proj - proj.min()) / (proj.max() - proj.min() + 1e-6)
    center = spec["x"]
    band_w = max(spec["width"] * 0.5 + 0.05, 0.05)
    band = np.exp(-((proj - center) / band_w) ** 2)
    rise = 0.3 + 0.7 * proj
    mask = gaussian_filter(band * rise, sigma=2.0 + spec["blur"] * 6.0)
    return _layer(color, mask, spec["opacity"])


def _paper_grain(spec, rng):
    """Full-canvas fine neutral grain (overlay); roughness sets amplitude."""
    noise = _octaves(rng, (H // 4, W // 4), octaves=3,
                     base=max(3, 3 + int(spec["density"] * 8)), persistence=0.5)
    noise = zoom(noise, (4, 4), order=2)[:H, :W].astype(np.float32)
    noise = (noise - 0.5) * 2.0
    amp = spec["roughness"] * 255.0 * 0.5
    gray = np.clip(128.0 + noise * amp, 0, 255)
    rgb = np.stack([gray, gray, gray], axis=-1)
    return _layer(_rgb_float(spec["color"]), np.ones((H, W), np.float32),
                  spec["opacity"], rgb_override=rgb)


def _ink_bleed(spec, rng):
    """Dark feathered blot with an irregular spreading edge (multiply)."""
    xs, ys = _mesh()
    color = _rgb_float(spec["color"])
    cx, cy = spec["x"] * W, spec["y"] * H
    rx, ry = spec["width"] * W * 0.5, spec["height"] * H * 0.5
    noise = _octaves(rng, (H // 4, W // 4), octaves=4, base=4, persistence=0.6)
    noise = zoom(noise, (4, 4), order=2)[:H, :W].astype(np.float32)
    d = ((xs - cx) / rx) ** 2 + ((ys - cy) / ry) ** 2
    spread = 1.0 + spec["roughness"] * (noise - 0.5) * 1.5
    mask = np.clip((spread - d) * 3.0, 0, 1)
    return _layer(color, gaussian_filter(mask, sigma=1.0 + spec["blur"] * 4.0),
                  spec["opacity"])


def _broken_line(spec, rng):
    """A dashed line along angle; roughness jitters position, density sets dash."""
    xs, ys = _mesh()
    color = _rgb_float(spec["color"])
    cx, cy = spec["x"] * W, spec["y"] * H
    half_w, half_h = spec["width"] * W * 0.5, spec["height"] * H * 0.5
    ang = np.radians(spec["angle"])
    xr = (xs - cx) * np.cos(ang) + (ys - cy) * np.sin(ang)
    yr = -(xs - cx) * np.sin(ang) + (ys - cy) * np.cos(ang)
    if spec["roughness"] > 0:
        noise = zoom(_noise(rng, (H // 4, W // 4), freq=8), (4, 4), order=2)[:H, :W]
        yr = yr + (noise - 0.5) * spec["roughness"] * half_h * 2.0
    thickness = half_h * 0.5 + 1.0
    line = np.exp(-(yr / thickness) ** 2)
    n_dash = int(4 + spec["density"] * 12)
    period = (half_w * 2) / max(n_dash, 1)
    dash = (np.sin(xr / period * np.pi) > 0).astype(np.float32)
    return _layer(color, np.clip(line * dash, 0, 1), spec["opacity"])


def _geometric_grid(spec, rng):
    """Thin grid lines inside the bbox; density inverts to finer spacing."""
    xs, ys = _mesh()
    color = _rgb_float(spec["color"])
    cx, cy = spec["x"] * W, spec["y"] * H
    half_w, half_h = spec["width"] * W * 0.5, spec["height"] * H * 0.5
    spacing = max(6, int((1.0 - spec["density"]) * 200 + 20))
    v = (xs % spacing < 2).astype(np.float32)
    h = (ys % spacing < 2).astype(np.float32)
    in_box = (xs >= cx - half_w) & (xs <= cx + half_w) & (ys >= cy - half_h) & (ys <= cy + half_h)
    return _layer(color, np.clip(v + h, 0, 1) * in_box, spec["opacity"])


def _halftone(spec, rng):
    """Offset dot matrix (screen); density inverts to finer dot spacing."""
    xs, ys = _mesh()
    color = _rgb_float(spec["color"])
    cx, cy = spec["x"] * W, spec["y"] * H
    half_w, half_h = spec["width"] * W * 0.5, spec["height"] * H * 0.5
    spacing = max(4, int((1.0 - spec["density"]) * 40 + 6))
    dx = (xs % spacing) - spacing / 2
    dy = (ys % spacing) - spacing / 2
    r_dot = spacing * 0.35 * (0.5 + 0.5 * spec["roughness"])
    mask = np.clip((r_dot - np.sqrt(dx ** 2 + dy ** 2)) / max(r_dot, 1.0), 0, 1)
    in_box = (xs >= cx - half_w) & (xs <= cx + half_w) & (ys >= cy - half_h) & (ys <= cy + half_h)
    return _layer(color, mask * in_box, spec["opacity"])


def _oversized_glyph(spec, rng):
    """Render a big glyph into the raster via PIL, so it takes blur/mask freely."""
    text = spec.get("text") or spec.get("glyph") or ""
    if not text:
        return np.zeros((H, W, 4), np.float32)
    from scripts.pptx_fonts import resolve_font_file
    fp = resolve_font_file(spec.get("font_role", "jp"))
    if not fp:
        return np.zeros((H, W, 4), np.float32)
    target_h = max(20, int(spec["height"] * H))
    try:
        font = ImageFont.truetype(fp, target_h)
    except Exception:
        return np.zeros((H, W, 4), np.float32)
    r, g, b = _hex_rgb(spec["color"])
    alpha = int(np.clip(spec["opacity"], 0, 1) * 255)
    bbox = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = int(target_h * 0.3)
    local = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(local).text((pad - bbox[0], pad - bbox[1]), text, font=font,
                               fill=(r, g, b, alpha))
    if spec["blur"] > 0:
        local = local.filter(ImageFilter.GaussianBlur(spec["blur"] * 6))
    arr = np.asarray(local).astype(np.float32)
    cx, cy = int(spec["x"] * W), int(spec["y"] * H)
    layer = np.zeros((H, W, 4), np.float32)
    x0, y0 = cx - arr.shape[1] // 2, cy - arr.shape[0] // 2
    sx0, sy0 = max(0, -x0), max(0, -y0)
    sx1, sy1 = min(arr.shape[1], W - x0), min(arr.shape[0], H - y0)
    if sx1 > sx0 and sy1 > sy0:
        layer[y0 + sy0:y0 + sy1, x0 + sx0:x0 + sx1] = arr[sy0:sy1, sx0:sx1]
    return layer


def _rough_edge(spec, rng):
    """A rough-edged band along a horizontal line (angle unused; x/y position)."""
    xs, ys = _mesh()
    color = _rgb_float(spec["color"])
    cx, cy = spec["x"] * W, spec["y"] * H
    half_w, half_h = spec["width"] * W * 0.5, spec["height"] * H * 0.5 + 2
    noise = zoom(_noise(rng, (H // 4, W // 4), freq=10), (4, 4), order=2)[:H, :W]
    jitter = (noise - 0.5) * spec["roughness"] * spec["height"] * H
    edge = np.exp(-((ys - (cy + jitter)) / half_h) ** 2)
    in_box = (xs >= cx - half_w) & (xs <= cx + half_w)
    return _layer(color, np.clip(edge * in_box, 0, 1), spec["opacity"])


def _blur_blob(spec, rng):
    """Small soft color blot."""
    xs, ys = _mesh()
    color = _rgb_float(spec["color"])
    cx, cy = spec["x"] * W, spec["y"] * H
    rx, ry = max(4, spec["width"] * W * 0.5), max(4, spec["height"] * H * 0.5)
    d = ((xs - cx) / rx) ** 2 + ((ys - cy) / ry) ** 2
    mask = gaussian_filter(np.exp(-d * 2.0), sigma=1.0 + spec["blur"] * 5.0)
    return _layer(color, mask, spec["opacity"])


def _gradient_field(spec, rng):
    """Soft directional color ramp (screen) along `angle`."""
    xs, ys = _mesh()
    color = _rgb_float(spec["color"])
    ang = np.radians(spec["angle"])
    proj = (xs * np.cos(ang) + ys * np.sin(ang)) / (W * 1.5)
    t = np.clip(proj - (0.5 - spec["width"]), 0, 1)
    mask = gaussian_filter(t, sigma=3.0 + spec["blur"] * 8.0)
    return _layer(color, mask, spec["opacity"])


_RENDERERS = {
    "dry_brush": _dry_brush, "wet_brush": _wet_brush, "paint_smear": _paint_smear,
    "irregular_color_block": _irregular_color_block, "soft_haze": _soft_haze,
    "light_band": _light_band, "paper_grain": _paper_grain, "ink_bleed": _ink_bleed,
    "broken_line": _broken_line, "geometric_grid": _geometric_grid,
    "halftone": _halftone, "oversized_glyph": _oversized_glyph,
    "rough_edge": _rough_edge, "blur_blob": _blur_blob,
    "gradient_field": _gradient_field,
}


# ── Spec normalization + dispatch + compositing ──────────────────────────────

def normalize_spec(spec, default_seed: int) -> dict | None:
    """Validate and fill defaults for one motif spec; None if the type is unknown."""
    if not isinstance(spec, dict):
        return None
    t = spec.get("type")
    if t not in MOTIF_TYPES:
        return None
    out = dict(spec)
    out["type"] = t
    out["color"] = _norm_hex(spec.get("color", "808080"))
    for k in ("opacity", "roughness", "density", "blur"):
        out[k] = float(np.clip(spec.get(k, _DEFAULTS[k]), 0.0, 1.0))
    out["x"] = float(np.clip(spec.get("x", 0.5), 0.0, 1.0))
    out["y"] = float(np.clip(spec.get("y", 0.5), 0.0, 1.0))
    out["width"] = float(np.clip(spec.get("width", 0.4), 0.01, 1.0))
    out["height"] = float(np.clip(spec.get("height", 0.1), 0.01, 1.0))
    out["angle"] = float(spec.get("angle", 0.0))
    out["seed"] = int(spec.get("seed", default_seed))
    out["blend"] = spec.get("blend", DEFAULT_BLEND.get(t, "alpha"))
    out["reason"] = spec.get("reason", "")
    if t == "oversized_glyph":
        out["text"] = spec.get("text") or spec.get("glyph") or ""
        out["font_role"] = spec.get("font_role", "jp")
    return out


def render_motif(spec: dict) -> np.ndarray:
    """Render one normalized spec into a full-canvas RGBA layer (H,W,4)."""
    return _RENDERERS[spec["type"]](spec, np.random.default_rng(spec["seed"]))


def composite_layer(base: np.ndarray, layer: np.ndarray, blend: str = "alpha") -> np.ndarray:
    a = layer[:, :, 3:4] / 255.0
    c = layer[:, :, :3]
    if blend == "screen":
        r = 255.0 - (255.0 - base) * (255.0 - c) / 255.0
        return base * (1 - a) + r * a
    if blend == "multiply":
        return base * (1 - a) + (base * c / 255.0) * a
    if blend == "overlay":
        bn, cn = base / 255.0, c / 255.0
        r = np.where(bn < 0.5, 2.0 * bn * cn, 1.0 - 2.0 * (1 - bn) * (1 - cn)) * 255.0
        return base * (1 - a) + r * a
    return base * (1 - a) + c * a


def composite_motifs(base_rgb: np.ndarray, specs: list[dict]) -> np.ndarray:
    """Composite ordered motif specs over a base RGB canvas (H,W,3)."""
    out = np.asarray(base_rgb, dtype=np.float32)
    for spec in specs:
        out = composite_layer(out, render_motif(spec), spec.get("blend", "alpha"))
    return np.clip(out, 0, 255)
