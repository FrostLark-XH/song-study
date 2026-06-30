"""7-layer mood-driven poster background generation via numpy/scipy + Pillow.

Pipeline (all vectorized, ~260ms target):
  Layer 0: Directional gradient canvas       (100% coverage)
  Layer 1: Large watercolor wash blobs       (40-70% opacity)
  Layer 2: Mid-scale pigment texture         (25-40% opacity)
  Layer 3: Fine washi fiber texture          (5-10% opacity)
  Layer 4: Atmospheric light pool            (screen blend, 15-25%)
  Layer 5: Soft vignette                     (max 5-10% darkening)
  Layer 6: Surface unification               (blur + micro-contrast)

5 mood presets (warm/cool/dark/dreamy/neutral), auto-detected from HSL.
Backward-compat: generate_paper_background() wraps mood="neutral".
"""

import numpy as np
from io import BytesIO
from PIL import Image, ImageFilter
from scipy.ndimage import zoom, gaussian_filter
import colorsys


W, H = 1920, 1080
_DEFAULT_BASE = "C5CDD4"


# ── Color utilities ────────────────────────────────────────────────────────────

def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _rgb_array(hex_str: str) -> np.ndarray:
    """3-element float array [R, G, B] in 0-255."""
    return np.array(_hex_to_rgb(hex_str), dtype=np.float32)


def _hsl_shift(rgb: np.ndarray, dh: float = 0.0, ds: float = 0.0, dl: float = 0.0) -> np.ndarray:
    """Shift HSL of an RGB color, return new RGB array."""
    r, g, b = rgb / 255.0
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    h = (h + dh) % 1.0
    l = max(0.0, min(1.0, l + dl))
    s = max(0.0, min(1.0, s + ds))
    nr, ng, nb = colorsys.hls_to_rgb(h, l, s)
    return np.array([nr, ng, nb], dtype=np.float32) * 255.0


def _detect_mood(hex_str: str) -> str:
    """Auto-detect mood from base color HSL."""
    r, g, b = _hex_to_rgb(hex_str)
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    if s < 0.08:
        return "neutral"
    if l < 0.25:
        return "dark"
    if 0.05 <= h < 0.15 or h >= 0.92:  # red zone
        return "warm"
    if 0.15 <= h < 0.45:  # green-yellow
        return "warm"
    if 0.45 <= h < 0.70:  # cyan-blue
        return "cool"
    if 0.70 <= h < 0.92:  # blue-magenta
        return "dreamy"
    return "neutral"


# ── Blend modes ────────────────────────────────────────────────────────────────

def _blend_alpha(base: np.ndarray, overlay: np.ndarray, alpha: float) -> np.ndarray:
    """Linear alpha composite overlay onto base. Both in 0-255 float."""
    return base * (1.0 - alpha) + overlay * alpha


def _blend_screen(base: np.ndarray, light: np.ndarray, alpha: float) -> np.ndarray:
    """Screen blend: 1 - (1-base)*(1-light)."""
    bn = base / 255.0
    ln = light / 255.0
    result = 1.0 - (1.0 - bn) * (1.0 - ln)
    blended = base * (1.0 - alpha) + result * 255.0 * alpha
    return blended


def _blend_multiply(base: np.ndarray, dark: np.ndarray, alpha: float) -> np.ndarray:
    """Multiply blend for darkening."""
    bn = base / 255.0
    dn = dark / 255.0
    result = bn * dn
    blended = base * (1.0 - alpha) + result * 255.0 * alpha
    return blended


# ── Noise generator ────────────────────────────────────────────────────────────

def _seeded_value_noise(rng: np.random.Generator, shape: tuple, freq: int) -> np.ndarray:
    """Value noise at given frequency via cubic-interpolated zoom."""
    small = rng.uniform(0, 1, size=(freq + 1, freq + 1)).astype(np.float32)
    h_ratio = shape[0] / small.shape[0]
    w_ratio = shape[1] / small.shape[1]
    return zoom(small, (h_ratio, w_ratio), order=3)


def _multi_octave_noise(rng: np.random.Generator, shape: tuple,
                         octaves: int = 4, base_freq: int = 4,
                         persistence: float = 0.5) -> np.ndarray:
    """Summed octave noise, normalized to [0, 1]."""
    result = np.zeros(shape, dtype=np.float32)
    amp = 1.0
    freq = base_freq
    max_val = 0.0
    for _ in range(octaves):
        result += _seeded_value_noise(rng, shape, freq) * amp
        max_val += amp
        amp *= persistence
        freq *= 2
    result /= max_val
    return result


# ── Mood parameter tables ──────────────────────────────────────────────────────

_MOOD_GRADIENT = {
    "warm":    {"angle": 135, "stop_shift": [0.0, 0.04, 0.08], "alpha": 0.6},
    "cool":    {"angle": 180, "stop_shift": [0.0, 0.03, 0.07], "alpha": 0.7},
    "dark":    {"angle": 0,   "stop_shift": [0.0, -0.04, -0.10], "alpha": 0.5},
    "dreamy":  {"angle": 45,  "stop_shift": [0.0, 0.05, 0.10], "alpha": 0.55},
    "neutral": {"angle": 0,   "stop_shift": [0.0, 0.02, 0.04], "alpha": 0.3},
}

_MOOD_WASH = {
    "warm":    {"opacity": 0.55, "hue_shift": 0.02, "sat_boost": 0.08, "count": 5,
                "sigma": 160, "q4": 40},
    "cool":    {"opacity": 0.50, "hue_shift": -0.03, "sat_boost": 0.05, "count": 5,
                "sigma": 140, "q4": 35},
    "dark":    {"opacity": 0.60, "hue_shift": 0.01, "sat_boost": -0.05, "count": 4,
                "sigma": 180, "q4": 45},
    "dreamy":  {"opacity": 0.45, "hue_shift": 0.06, "sat_boost": 0.12, "count": 6,
                "sigma": 150, "q4": 38},
    "neutral": {"opacity": 0.40, "hue_shift": 0.0, "sat_boost": 0.0, "count": 4,
                "sigma": 120, "q4": 30},
}

_MOOD_PIGMENT = {
    "warm":    {"opacity": 0.30, "freq": 6, "octaves": 3, "contrast": 1.8},
    "cool":    {"opacity": 0.28, "freq": 7, "octaves": 4, "contrast": 1.6},
    "dark":    {"opacity": 0.35, "freq": 5, "octaves": 3, "contrast": 2.0},
    "dreamy":  {"opacity": 0.25, "freq": 8, "octaves": 4, "contrast": 1.4},
    "neutral": {"opacity": 0.22, "freq": 6, "octaves": 3, "contrast": 1.5},
}

_MOOD_FIBER = {
    "warm":    {"opacity": 0.07, "angle": 0,   "aspect": 8.0, "sigma": 1.2},
    "cool":    {"opacity": 0.06, "angle": 90,  "aspect": 6.0, "sigma": 1.0},
    "dark":    {"opacity": 0.08, "angle": 0,   "aspect": 10.0, "sigma": 1.5},
    "dreamy":  {"opacity": 0.05, "angle": 45,  "aspect": 7.0, "sigma": 0.8},
    "neutral": {"opacity": 0.05, "angle": 0,   "aspect": 6.0, "sigma": 1.0},
}

_MOOD_LIGHT = {
    "warm":    {"opacity": 0.20, "cx": 0.70, "cy": 0.65, "rx": 0.55, "ry": 0.40,
                "color": np.array([255.0, 245.0, 220.0])},
    "cool":    {"opacity": 0.18, "cx": 0.50, "cy": 0.25, "rx": 0.60, "ry": 0.45,
                "color": np.array([235.0, 245.0, 255.0])},
    "dark":    {"opacity": 0.22, "cx": 0.50, "cy": 0.50, "rx": 0.35, "ry": 0.35,
                "color": np.array([255.0, 240.0, 210.0])},
    "dreamy":  {"opacity": 0.15, "cx": 0.45, "cy": 0.35, "rx": 0.50, "ry": 0.42,
                "color": np.array([245.0, 230.0, 255.0])},
    "neutral": {"opacity": 0.12, "cx": 0.50, "cy": 0.40, "rx": 0.45, "ry": 0.38,
                "color": np.array([248.0, 248.0, 248.0])},
}

_MOOD_VIGNETTE = {
    "warm":    {"strength": 0.07, "falloff": 2.2},
    "cool":    {"strength": 0.06, "falloff": 2.5},
    "dark":    {"strength": 0.10, "falloff": 2.0},
    "dreamy":  {"strength": 0.05, "falloff": 2.8},
    "neutral": {"strength": 0.05, "falloff": 2.5},
}


# ── Layer generators ───────────────────────────────────────────────────────────

def _gradient_canvas(base_color: str, mood: str) -> np.ndarray:
    """Layer 0: Directional gradient from base color to bright/dark variants."""
    cfg = _MOOD_GRADIENT.get(mood, _MOOD_GRADIENT["neutral"])
    base_rgb = _rgb_array(base_color)

    angle_rad = np.radians(cfg["angle"])
    dx, dy = np.cos(angle_rad), -np.sin(angle_rad)

    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    t = (xs * dx + ys * dy) / (W * abs(dx) + H * abs(dy) + 1e-8)
    t = np.clip(t, 0.0, 1.0)

    stops = cfg["stop_shift"]
    c0 = _hsl_shift(base_rgb, dl=stops[0])
    c1 = _hsl_shift(base_rgb, dl=stops[1])
    c2 = _hsl_shift(base_rgb, dl=stops[2])

    # Quadratic gradient: c0(t=0) → c1(t=0.5) → c2(t=1)
    canvas = np.zeros((H, W, 3), dtype=np.float32)
    for ch in range(3):
        c0_ch, c1_ch, c2_ch = float(c0[ch]), float(c1[ch]), float(c2[ch])
        a = 2.0 * c0_ch - 4.0 * c1_ch + 2.0 * c2_ch
        b = -3.0 * c0_ch + 4.0 * c1_ch - c2_ch
        c = c0_ch
        canvas[:, :, ch] = a * t * t + b * t + c

    return np.clip(canvas, 0, 255)


def _color_wash_layer(rng: np.random.Generator, base_color: str, mood: str) -> np.ndarray:
    """Layer 1: Large soft watercolor wash blobs with hue variations."""
    cfg = _MOOD_WASH.get(mood, _MOOD_WASH["neutral"])
    base_rgb = _rgb_array(base_color)
    q4_h, q4_w = H // 4, W // 4

    canvas = np.zeros((q4_h, q4_w), dtype=np.float32)

    for _ in range(cfg["count"]):
        cx = rng.uniform(0, q4_w)
        cy = rng.uniform(0, q4_h)
        amp = rng.uniform(30, 80)
        sy, sx = np.mgrid[0:q4_h, 0:q4_w].astype(np.float32)
        dist2 = ((sx - cx) ** 2 + (sy - cy) ** 2) / (q4_w * q4_h) * (
            rng.uniform(2.0, 8.0))
        blob = amp * np.exp(-dist2)
        canvas += blob

    canvas = gaussian_filter(canvas, sigma=cfg["q4"] / 4.0)
    canvas = np.clip(canvas, -60, 60)

    canvas = zoom(canvas, (4.0, 4.0), order=3)
    if canvas.shape[0] > H:
        canvas = canvas[:H, :]
    if canvas.shape[1] > W:
        canvas = canvas[:, :W]
    if canvas.shape[0] < H or canvas.shape[1] < W:
        canvas = np.pad(canvas, ((0, H - canvas.shape[0]), (0, W - canvas.shape[1])))

    shifted = _hsl_shift(base_rgb, dh=cfg["hue_shift"], ds=cfg["sat_boost"])
    result = np.zeros((H, W, 3), dtype=np.float32)
    for ch in range(3):
        result[:, :, ch] = float(shifted[ch]) + canvas

    return np.clip(result, 0, 255)


def _pigment_texture_layer(rng: np.random.Generator, base_color: str, mood: str) -> np.ndarray:
    """Layer 2: Gradient-magnitude edge mottle from multi-octave noise."""
    cfg = _MOOD_PIGMENT.get(mood, _MOOD_PIGMENT["neutral"])
    base_rgb = _rgb_array(base_color)
    q4_h, q4_w = H // 4, W // 4

    noise = _multi_octave_noise(rng, (q4_h, q4_w),
                                octaves=cfg["octaves"],
                                base_freq=cfg["freq"],
                                persistence=0.55)
    noise = (noise - 0.5) * cfg["contrast"]
    noise = zoom(noise, (4.0, 4.0), order=2)
    noise = noise[:H, :W] if noise.shape[0] > H else np.pad(noise, ((0, H - noise.shape[0]), (0, 0)))
    noise = noise[:, :W] if noise.shape[1] > W else np.pad(noise, ((0, 0), (0, W - noise.shape[1])))

    result = np.zeros((H, W, 3), dtype=np.float32)
    for ch in range(3):
        result[:, :, ch] = float(base_rgb[ch]) + noise * 25.0

    return np.clip(result, 0, 255)


def _fiber_grain_layer(rng: np.random.Generator, mood: str) -> np.ndarray:
    """Layer 3: Anisotropic directional washi fiber streaks."""
    cfg = _MOOD_FIBER.get(mood, _MOOD_FIBER["neutral"])
    angle_rad = np.radians(cfg["angle"])

    q4_h, q4_w = H // 4, W // 4
    noise = _seeded_value_noise(rng, (q4_h, q4_w), freq=8)

    # Directional blur via stretched gaussian
    sx = cfg["aspect"] * abs(np.cos(angle_rad)) + 1.0 * abs(np.sin(angle_rad))
    sy = cfg["aspect"] * abs(np.sin(angle_rad)) + 1.0 * abs(np.cos(angle_rad))
    noise = gaussian_filter(noise, sigma=(sy * cfg["sigma"] * 0.5, sx * cfg["sigma"] * 0.5))
    noise = (noise - 0.5) * 2.0
    noise = zoom(noise, (4.0, 4.0), order=2)
    noise = noise[:H, :W] if noise.shape[0] > H else np.pad(noise, ((0, H - noise.shape[0]), (0, 0)))
    noise = noise[:, :W] if noise.shape[1] > W else np.pad(noise, ((0, 0), (0, W - noise.shape[1])))

    # 128 ± noise*opacity*255
    base = np.full((H, W), 128.0, dtype=np.float32)
    result = (base + noise * cfg["opacity"] * 255.0)

    rgb = np.stack([result, result, result], axis=-1)
    return np.clip(rgb, 0, 255)


def _light_pool_layer(base_color: str, mood: str) -> np.ndarray:
    """Layer 4: Elliptical light pool via screen blend."""
    cfg = _MOOD_LIGHT.get(mood, _MOOD_LIGHT["neutral"])
    light_color = cfg["color"]

    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    nx = (xs / W - cfg["cx"]) / cfg["rx"]
    ny = (ys / H - cfg["cy"]) / cfg["ry"]
    dist = np.sqrt(nx * nx + ny * ny)
    falloff = np.exp(-dist * dist * 2.5)

    result = np.zeros((H, W, 3), dtype=np.float32)
    for ch in range(3):
        result[:, :, ch] = float(light_color[ch]) * falloff

    return np.clip(result, 0, 255)


def _vignette_layer(mood: str) -> np.ndarray:
    """Layer 5: Power-curve corner darkening (non-symmetric, subtle)."""
    cfg = _MOOD_VIGNETTE.get(mood, _MOOD_VIGNETTE["neutral"])

    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    nx = (xs / W - 0.5) * 2.0
    ny = (ys / H - 0.5) * 2.0
    r = np.sqrt(nx * nx + ny * ny)
    r = np.clip(r / np.sqrt(2.0), 0.0, 1.0)

    v = r ** cfg["falloff"]
    v = v * cfg["strength"]

    result = np.zeros((H, W, 3), dtype=np.float32)
    for ch in range(3):
        result[:, :, ch] = 255.0 * (1.0 - v)

    return result


def _surface_unify(img_np: np.ndarray) -> np.ndarray:
    """Layer 6: Gaussian blur + micro-contrast for unified film-like finish."""
    # 1/4 res blur for speed
    q4_h, q4_w = H // 4, W // 4
    small = np.zeros((q4_h, q4_w, 3), dtype=np.float32)
    for ch in range(3):
        ch_data = img_np[:, :, ch].reshape(H // 4, 4, W // 4, 4).mean(axis=(1, 3))
        small[:, :, ch] = ch_data

    for ch in range(3):
        small[:, :, ch] = gaussian_filter(small[:, :, ch], sigma=2.5)

    blurred = np.zeros_like(img_np)
    for ch in range(3):
        ch_up = zoom(small[:, :, ch], (4.0, 4.0), order=3)
        blurred[:, :, ch] = ch_up[:H, :W] if ch_up.shape[0] > H else np.pad(
            ch_up, ((0, H - ch_up.shape[0]), (0, 0)))[:, :W] if ch_up.shape[1] > W else np.pad(
            ch_up, ((0, 0), (0, W - ch_up.shape[1])))

    # Blend 15% of blurred layer for micro-contrast
    result = img_np * 0.85 + blurred * 0.15
    return np.clip(result, 0, 255)


# ── Orchestrator ───────────────────────────────────────────────────────────────

def _rgb_to_bytes(rgb_np: np.ndarray) -> bytes:
    """Convert numpy RGB array to PNG bytes."""
    img = Image.fromarray(np.clip(rgb_np, 0, 255).astype(np.uint8), mode="RGB")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def generate_mood_background(seed: int = 42, base_color: str = _DEFAULT_BASE,
                              mood: str | None = None) -> BytesIO:
    """Generate mood-driven poster background as in-memory PNG.

    7-layer pipeline:
      0. Directional gradient canvas
      1. Large watercolor wash blobs
      2. Mid-scale pigment edge texture
      3. Fine anisotropic washi fiber grain
      4. Atmospheric light pool (screen blend)
      5. Soft power-curve vignette
      6. Surface unification (blur + micro-contrast)

    Args:
        seed: Deterministic seed for reproducibility.
        base_color: Hex color string (e.g. "C0C4CC") for the paper base.
        mood: One of warm/cool/dark/dreamy/neutral. Auto-detected if None.

    Returns:
        BytesIO buffer containing a 1920×1080 PNG, position at 0.
    """
    if mood is None:
        mood = _detect_mood(base_color)

    rng = np.random.default_rng(seed)

    # Layer 0: Gradient canvas
    canvas = _gradient_canvas(base_color, mood)

    # Layer 1: Watercolor wash
    wash = _color_wash_layer(rng, base_color, mood)
    wash_opacity = _MOOD_WASH[mood]["opacity"]
    canvas = _blend_alpha(canvas, wash, wash_opacity)

    # Layer 2: Pigment texture
    pigment = _pigment_texture_layer(rng, base_color, mood)
    pigment_opacity = _MOOD_PIGMENT[mood]["opacity"]
    canvas = _blend_alpha(canvas, pigment, pigment_opacity)

    # Layer 3: Fiber grain (overlay blend — 128 is transparent)
    fiber = _fiber_grain_layer(rng, mood)
    fiber_opacity = _MOOD_FIBER[mood]["opacity"]
    fn = fiber / 255.0
    bn = canvas / 255.0
    overlay = np.where(bn < 0.5, 2.0 * bn * fn, 1.0 - 2.0 * (1.0 - bn) * (1.0 - fn))
    canvas = (canvas * (1.0 - fiber_opacity) + overlay * 255.0 * fiber_opacity)

    # Layer 4: Light pool (screen blend)
    light = _light_pool_layer(base_color, mood)
    light_opacity = _MOOD_LIGHT[mood]["opacity"]
    canvas = _blend_screen(canvas, light, light_opacity)

    # Layer 5: Vignette (multiply blend)
    vignette = _vignette_layer(mood)
    canvas = _blend_multiply(canvas, vignette, 1.0)

    # Layer 6: Surface unification
    canvas = _surface_unify(canvas)

    img = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8), mode="RGB")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def generate_paper_background(seed: int = 42, base_color: str = _DEFAULT_BASE) -> BytesIO:
    """Backward-compatible wrapper: neutral mood, layers 0/3/5/6 only."""
    return generate_mood_background(seed=seed, base_color=base_color, mood="neutral")
