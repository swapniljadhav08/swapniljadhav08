#!/usr/bin/env python3
"""
generate_portrait.py - photo -> particle portrait -> terminal-style GitHub banner.

Pipeline (fully deterministic, fixed RNG seeds):
  1. Load the ORIGINAL photograph with Pillow and crop head + upper torso.
  2. Grayscale, percentile contrast stretch, local-contrast (unsharp) boost.
  3. Build an importance map from luminance ("ink"), Sobel-style edge strength,
     a face-weighting ellipse, a background mask and a soft border fade.
  4. Place particles with weighted centroidal Voronoi stippling (Lloyd relaxation).
     The result is blue-noise: dense where the image is dark or has edges, sparse
     where it is bright, with no clumping and no random noise inside the face.
  5. Size/colour every particle from the local tone of the photo.
  6. Emit a compact SVG (one stroked path per colour/size group, round caps),
     SMIL opacity/translate animation on staggered groups, static fallback.
  7. Rasterise previews (cairosvg, or system librsvg as a fallback).

Usage:
    python generate_portrait.py                # writes profile.svg + previews
    python generate_portrait.py --particles 9000 --out profile-lite.svg
"""
from __future__ import annotations

import argparse
import ctypes
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parent

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
CFG = dict(
    photo=ROOT / "assets" / "original-photo.jpg",
    # crop of the source photo (pixels of the 1600x1600 original)
    crop_cx=801,          # horizontal centre of the crop
    crop_y0=172,          # top edge of the crop (head top is ~y=222)
    crop_w=1250,          # crop width; height follows the frame aspect ratio
    # face ellipse in source pixels (used to emphasise the face over the suit)
    face_cx=795, face_cy=585, face_rx=300, face_ry=360,
    torso_weight=0.42,    # relative particle density far from the face
    particles=14000,
    bg_particles=240,
    lloyd_iters=14,
    seed=20260417,
    supersample=2,
)

# Banner geometry (viewBox 1440 x 720)
W, H = 1440, 720
MARGIN = 32
BAR_H = 52
GAP = 20
LEFT_W = 580                         # 42.2 % of the 1376 usable width
CONTENT_Y = BAR_H + 24               # 76
CONTENT_H = H - CONTENT_Y - 32       # 612
RIGHT_X = MARGIN + LEFT_W + GAP      # 632
RIGHT_W = W - MARGIN - RIGHT_X       # 776  (56.4 %)
FRAME_PAD = 14
INNER_W = LEFT_W - 2 * FRAME_PAD     # 552
INNER_H = CONTENT_H - 2 * FRAME_PAD  # 584

# Palette
C = dict(
    bg="#F4F7FB", panel="#FBFDFF", text="#101B32", text2="#526783",
    cyan="#06B6D4", cyan_text="#0891B2", line="#D3E1EE", leader="#AFC0D2",
    indigo="#2E1065", dviolet="#4C1D95", purple="#5B21B6", bright="#7C3AED",
    light="#A78BFA",
)
# tone bins: (min tone, colour, base opacity, pulse-min opacity)
BINS = [
    (0.80, C["indigo"], 0.95, 0.70),
    (0.60, C["dviolet"], 0.93, 0.62),
    (0.42, C["purple"], 0.90, 0.55),
    (0.24, C["bright"], 0.85, 0.45),
    (0.00, C["light"], 0.80, 0.35),
]
MONO = "ui-monospace, 'SF Mono', SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', 'Liberation Mono', monospace"
CW = 0.602  # monospace advance in em (DejaVu/Menlo = widest common case)

INFO = [
    ("Email", "sm2021jadhav@gmail.com"),
    ("Subject", "Swapnil Jadhav"),
    ("Role", "Full Stack Developer"),
    ("Origin", "Kolhapur, Maharashtra, India"),
    ("Education", "B.Tech · CSBS"),
    ("Status", "Building + Learning + Shipping"),
    ("ToolChain", "Git, Docker, VS Code, Figma"),
    ("Core.Lang", "JavaScript, TypeScript, Python"),
    ("Core.Frontend", "React, Next.js, Tailwind"),
    ("Core.Backend", "Node.js, Express, FastAPI"),
    ("Core.Database", "PostgreSQL, MongoDB, Redis"),
    ("Core.Infra", "Cloudflare, Docker, GitHub"),
]
LINKS = [
    ("Grid.Portfolio", "swapniljadhav.workers.dev"),
    ("Grid.LinkedIn", "swapniljadhav26"),
    ("Grid.GitHub", "@swapniljadhav08"),
]


# --------------------------------------------------------------------------
# Image -> importance maps
# --------------------------------------------------------------------------
def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def load_crop(cfg):
    img = Image.open(cfg["photo"]).convert("RGB")
    s = INNER_W / cfg["crop_w"]
    crop_h = int(round(INNER_H / s))
    x0 = int(round(cfg["crop_cx"] - cfg["crop_w"] / 2))
    box = (x0, cfg["crop_y0"], x0 + cfg["crop_w"], cfg["crop_y0"] + crop_h)
    if box[0] < 0 or box[1] < 0 or box[2] > img.width or box[3] > img.height:
        raise SystemExit(f"crop box {box} falls outside the {img.size} photo")
    ss = cfg["supersample"]
    crop = img.crop(box).resize((INNER_W * ss, INNER_H * ss), Image.LANCZOS)
    return crop, box, s


def build_maps(crop, box, s, cfg):
    ss = cfg["supersample"]
    gray = np.asarray(crop.convert("L"), np.float32) / 255.0
    lo, hi = np.percentile(gray, (0.5, 99.5))
    g = np.clip((gray - lo) / (hi - lo), 0, 1)

    # gradient / edge strength
    gs = ndi.gaussian_filter(g, 1.2)
    gy, gx = np.gradient(gs)
    mag = np.hypot(gx, gy)

    # background = bright, flat region connected to the top/left/right border
    flat = (ndi.gaussian_filter(mag, 2.0) < 0.0042) & (gs > 0.55)
    lab, _ = ndi.label(flat)
    border = set(np.unique(lab[0, :])) | set(np.unique(lab[:, 0])) | set(np.unique(lab[:, -1]))
    border.discard(0)
    bg = np.isin(lab, list(border))
    bg = ndi.binary_opening(bg, iterations=2)
    bgm = ndi.gaussian_filter(bg.astype(np.float32), 3.0)

    # local contrast boost + tone
    lc = np.clip(g + 1.25 * (g - ndi.gaussian_filter(g, 10)), 0, 1)
    ink = np.clip(1.12 * (1.0 - lc) ** 0.82, 0, 1)
    ink_eff = ink * (1.0 - 0.97 * bgm)

    # edge strength, normalised on the subject
    ref = np.percentile(mag[bgm < 0.5], 99)
    e = np.clip(mag / ref, 0, 1) ** 0.8
    e = ndi.gaussian_filter(e, 0.8)

    hh, ww = g.shape
    yy, xx = np.mgrid[0:hh, 0:ww].astype(np.float32)

    # face emphasis: ellipse centre in working-grid coordinates
    fx = (cfg["face_cx"] - box[0]) * s * ss
    fy = (cfg["face_cy"] - box[1]) * s * ss
    frx, fry = cfg["face_rx"] * s * ss, cfg["face_ry"] * s * ss
    d2 = ((xx - fx) / frx) ** 2 + ((yy - fy) / fry) ** 2
    tw = cfg["torso_weight"]
    fw = tw + (1 - tw) * np.exp(-0.5 * d2 / 1.2 ** 2)

    # soft fade at the left / right / bottom border of the frame
    fade = (
        smoothstep(0, 0.06 * ww, xx - 14 * ss)
        * smoothstep(0, 0.06 * ww, ww - xx - 14 * ss)
        * smoothstep(0, 0.12 * hh, hh - yy - 12 * ss)
    )

    rho = fw * (1.00 * ink_eff + 0.60 * e * (1 - 0.35 * bgm)) + 0.012 * (1 - bgm)
    rho = rho * fade
    tone = ndi.gaussian_filter(ink * (1 - bgm), 1.5)
    return dict(rho=rho.astype(np.float64), tone=tone, e=e, bgm=bgm, fade=fade, g=g)


# --------------------------------------------------------------------------
# Weighted centroidal Voronoi stippling
# --------------------------------------------------------------------------
def stipple(rho, n, iters, rng):
    hh, ww = rho.shape
    cdf = np.cumsum(rho.ravel())
    cdf /= cdf[-1]
    idx = np.searchsorted(cdf, rng.random(n))
    idx = np.clip(idx, 0, rho.size - 1)
    pts = np.stack([idx % ww, idx // ww], 1).astype(np.float64)
    pts += rng.random((n, 2)) - 0.5

    ys, xs = np.mgrid[0:hh, 0:ww]
    grid = np.stack([xs.ravel(), ys.ravel()], 1).astype(np.float64)
    wflat = rho.ravel()
    wx, wy = wflat * grid[:, 0], wflat * grid[:, 1]
    for _ in range(iters):
        _, nearest = cKDTree(pts).query(grid, workers=-1)
        sw = np.bincount(nearest, weights=wflat, minlength=n)
        sx = np.bincount(nearest, weights=wx, minlength=n)
        sy = np.bincount(nearest, weights=wy, minlength=n)
        ok = sw > 1e-12
        pts[ok, 0] = sx[ok] / sw[ok]
        pts[ok, 1] = sy[ok] / sw[ok]
    pts[:, 0] = np.clip(pts[:, 0], 0, ww - 1)
    pts[:, 1] = np.clip(pts[:, 1], 0, hh - 1)
    return pts


def build_particles(cfg, debug_dir=None):
    crop, box, s = load_crop(cfg)
    maps = build_maps(crop, box, s, cfg)
    ss = cfg["supersample"]
    rng = np.random.default_rng(cfg["seed"])

    pts = stipple(maps["rho"], cfg["particles"], cfg["lloyd_iters"], rng)
    ix = np.clip(pts[:, 0].astype(int), 0, maps["rho"].shape[1] - 1)
    iy = np.clip(pts[:, 1].astype(int), 0, maps["rho"].shape[0] - 1)
    tone = maps["tone"][iy, ix]
    e = maps["e"][iy, ix]
    r = 0.62 + 0.95 * np.clip(tone, 0, 1) ** 0.9 + 0.35 * e
    px, py = pts[:, 0] / ss, pts[:, 1] / ss
    col = np.full(len(px), len(BINS) - 1)
    for i, (tmin, *_rest) in reversed(list(enumerate(BINS))):
        col[tone >= tmin] = i
    main = dict(x=px, y=py, r=np.clip(r, 0.6, 1.95), col=col)

    # atmosphere: a few tiny, faint particles in the background only
    halo = ndi.gaussian_filter((maps["bgm"] < 0.5).astype(np.float32), 22)
    rho_bg = (maps["bgm"] ** 3) * (0.04 + halo) * maps["fade"]
    rng2 = np.random.default_rng(cfg["seed"] + 1)
    bpts = stipple(rho_bg.astype(np.float64), cfg["bg_particles"], 5, rng2)
    bg = dict(x=bpts[:, 0] / ss, y=bpts[:, 1] / ss,
              r=0.55 + 0.35 * rng2.random(len(bpts)))

    if debug_dir:
        debug_dir = Path(debug_dir)
        debug_dir.mkdir(parents=True, exist_ok=True)
        for k in ("rho", "tone", "e", "bgm"):
            a = maps[k] / (maps[k].max() or 1)
            Image.fromarray((255 * (1 - a)).astype(np.uint8)).save(debug_dir / f"map_{k}.png")
        crop.save(debug_dir / "crop.png")
    return main, bg, dict(box=box, scale=s, maps=maps)


# --------------------------------------------------------------------------
# SVG output
# --------------------------------------------------------------------------
def fnum(v10: int) -> str:
    """int tenths -> shortest SVG number ('.5', '-.3', '12', '3.7')."""
    sign = "-" if v10 < 0 else ""
    v10 = abs(v10)
    whole, frac = divmod(v10, 10)
    if frac == 0:
        return f"{sign}{whole}"
    return f"{sign}{whole if whole else ''}.{frac}"


def path_for(points10) -> str:
    """Relative-coordinate zero-length segments; round caps turn them into dots."""
    out, px, py = [], 0, 0
    for x, y in points10:
        out.append(f"m{fnum(x - px)} {fnum(y - py)}h0" if out else f"M{fnum(x)} {fnum(y)}h0")
        px, py = x, y
    return "".join(out)


NSUB = 96          # random particle subsets; each flies in along its own vector
LOOP = 14.0        # seconds per cycle: scatter -> assemble -> hold/breathe -> disperse
KT = [0.0, None, None, 0.52, 0.80, 1.0]            # key times (1,2 get a per-subset delay)
SPLINES = "0 0 1 1;.16 .84 .3 1;.45 0 .55 1;.45 0 .55 1;.5 0 .75 .2"


def subset_params(seed):
    rng = np.random.default_rng(seed)
    ang = rng.uniform(0, 2 * np.pi, NSUB)
    rad = 70 + 190 * rng.random(NSUB) ** 0.7
    vec = np.stack([rad * np.cos(ang), rad * np.sin(ang)], 1)
    delay = rng.random(NSUB) * 0.07
    breathe = rng.uniform(-0.8, 0.8, (NSUB, 2))
    return vec, delay, breathe


def keyframes(k, vec, delay, breathe):
    d = delay[k]
    kt = [0.0, d, d + 0.26, 0.52, 0.80, 1.0]
    sx, sy = vec[k]
    bx, by = breathe[k]
    vals = [(sx, sy), (sx, sy), (0, 0), (bx, by), (0, 0), (sx, sy)]
    ops = [0.3, 0.3, 1.0, 0.62, 1.0, 0.3]
    return kt, vals, ops


def frame_state(k, u, vec, delay, breathe):
    """Approximate (smoothstep) state of subset k at loop fraction u - used for --frame checks."""
    kt, vals, ops = keyframes(k, vec, delay, breathe)
    for a in range(5):
        if kt[a] <= u <= kt[a + 1]:
            t = (u - kt[a]) / max(kt[a + 1] - kt[a], 1e-9)
            t = 0 if a == 0 else t * t * (3 - 2 * t)
            lerp = lambda p, q: p + (q - p) * t
            return (lerp(vals[a][0], vals[a + 1][0]), lerp(vals[a][1], vals[a + 1][1]),
                    lerp(ops[a], ops[a + 1]))
    return 0, 0, 1


def particle_markup(main, bg, ox, oy, animate=True, indent="  ", frame=None):
    vec, delay, breathe = subset_params(CFG["seed"] + 3)
    rng = np.random.default_rng(CFG["seed"] + 2)
    sub = rng.integers(0, NSUB, len(main["x"]))
    xs = np.round((main["x"] + ox) * 10).astype(int)
    ys = np.round((main["y"] + oy) * 10).astype(int)
    rb = np.clip(np.round((main["r"] - 0.6) / 0.27).astype(int), 0, 5)  # 6 size classes
    out = [f'{indent}<g id="portrait">']
    for k in range(NSUB):
        selk = sub == k
        if not selk.any():
            continue
        attrs = ""
        if frame is not None:
            fx_, fy_, fo_ = frame_state(k, frame / LOOP, vec, delay, breathe)
            attrs = f' transform="translate({fx_:.1f} {fy_:.1f})" opacity="{fo_:.2f}"'
        out.append(f'{indent}  <g{attrs}>')
        for ci, (_t, colr, base, _lo) in enumerate(BINS):
            for sz in np.unique(rb[selk & (main["col"] == ci)]):
                m = selk & (main["col"] == ci) & (rb == sz)
                order = np.lexsort((xs[m], ys[m]))
                pts = list(zip(xs[m][order], ys[m][order]))
                width = round(2 * (0.6 + 0.27 * sz), 2)
                out.append(f'{indent}    <path fill="none" stroke="{colr}" stroke-opacity="{base}" '
                           f'stroke-linecap="round" stroke-width="{width:g}" d="{path_for(pts)}"/>')
        if animate and frame is None:
            kt, vals, ops = keyframes(k, vec, delay, breathe)
            ktxt = ";".join(f"{v:.3f}".rstrip("0").rstrip(".") for v in kt)
            vtxt = ";".join(f"{a:.1f} {b:.1f}" for a, b in vals)
            otxt = ";".join(f"{o:g}" for o in ops)
            common = f'keyTimes="{ktxt}" calcMode="spline" keySplines="{SPLINES}" dur="{LOOP:g}s" repeatCount="indefinite"'
            out.append(f'{indent}    <animateTransform attributeName="transform" type="translate" values="{vtxt}" {common}/>')
            out.append(f'{indent}    <animate attributeName="opacity" values="{otxt}" {common}/>')
        out.append(f"{indent}  </g>")
    out.append(f"{indent}</g>")

    # atmosphere (fades with the loop, drifts a little)
    bx = np.round((bg["x"] + ox) * 10).astype(int)
    by = np.round((bg["y"] + oy) * 10).astype(int)
    out.append(f'{indent}<g id="atmosphere" fill="none" stroke="{C["light"]}" stroke-linecap="round" opacity=".38">')
    for w in (1.1, 1.5):
        m = (bg["r"] < 0.72) if w == 1.1 else (bg["r"] >= 0.72)
        order = np.lexsort((bx[m], by[m]))
        out.append(f'{indent}  <path stroke-width="{w}" d="{path_for(list(zip(bx[m][order], by[m][order])))}"/>')
    if animate and frame is None:
        out.append(f'{indent}  <animate attributeName="opacity" values=".38;.16;.38" dur="7s" repeatCount="indefinite"/>')
        out.append(f'{indent}  <animateTransform attributeName="transform" type="translate" values="0 0;1.5 -1;0 0" dur="9s" repeatCount="indefinite"/>')
    out.append(f"{indent}</g>")
    return "\n".join(out)


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text_w(s, size):
    return len(s) * CW * size


def row(label, value, y, size, vcol, rx0, rx1):
    lw, vw = text_w(label, size), text_w(value, size)
    lx1 = rx0 + lw + 12
    vx0 = rx1 - vw - 12
    leader = ""
    if vx0 - lx1 > 16:
        leader = (f'<line x1="{lx1:.1f}" y1="{y - 5}" x2="{vx0:.1f}" y2="{y - 5}" stroke="{C["leader"]}" '
                  f'stroke-width="1.6" stroke-linecap="round" stroke-dasharray="0.1 6"/>')
    return (f'<text x="{rx0}" y="{y}" fill="{C["cyan_text"]}" font-size="{size}" font-weight="600">{esc(label)}</text>\n'
            f'    {leader}\n'
            f'    <text x="{rx1}" y="{y}" fill="{vcol}" font-size="{size}" font-weight="700" text-anchor="end">{esc(value)}</text>')


def build_svg(main, bg, animate=True, frame=None):
    fx, fy = MARGIN, CONTENT_Y
    ox, oy = fx + FRAME_PAD, fy + FRAME_PAD
    size = 19
    rx0, rx1 = RIGHT_X + 30, RIGHT_X + RIGHT_W - 30
    title = "swapnil@developer: ~ % ./profile.sh --live"
    blink = (f'<animate attributeName="fill-opacity" values="1;1;0;0" keyTimes="0;.5;.5;1" '
             f'calcMode="discrete" dur="1.2s" repeatCount="indefinite"/>') if animate else ""

    L = []
    a = L.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
      f'role="img" aria-labelledby="t d" font-family="{MONO}">')
    a('  <title id="t">Swapnil Jadhav – Full Stack Developer</title>')
    a('  <desc id="d">Terminal-style profile banner: particle portrait of Swapnil Jadhav and a system info panel.</desc>')
    a('  <defs>')
    a(f'    <linearGradient id="frame" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{C["cyan"]}"/>'
      f'<stop offset=".5" stop-color="#67E8F9"/><stop offset="1" stop-color="{C["cyan"]}"/></linearGradient>')
    a(f'    <clipPath id="outer"><rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="22"/></clipPath>')
    a(f'    <clipPath id="pf"><rect x="{MARGIN + 2}" y="{CONTENT_Y + 2}" width="{LEFT_W - 4}" height="{CONTENT_H - 4}" rx="14"/></clipPath>')
    a('  </defs>')
    a(f'  <rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="22" fill="{C["bg"]}"/>')
    a(f'  <g clip-path="url(#outer)"><rect x="0" y="0" width="{W}" height="{BAR_H}" fill="#EAF0F7"/></g>')
    a(f'  <line x1="1" y1="{BAR_H}" x2="{W - 1}" y2="{BAR_H}" stroke="{C["line"]}" stroke-width="1.2"/>')
    for cx, col in ((36, "#FF5F57"), (60, "#FEBC2E"), (84, "#28C840")):
        a(f'  <circle cx="{cx}" cy="{BAR_H // 2}" r="6.5" fill="{col}"/>')
    a(f'  <text x="116" y="{BAR_H // 2 + 6}" font-size="17" fill="{C["text2"]}">'
      f'<tspan fill="{C["cyan_text"]}" font-weight="700">swapnil@developer</tspan>'
      f'<tspan>: ~ %</tspan><tspan dx="10.2" fill="{C["text"]}" font-weight="600">./profile.sh --live</tspan>'
      f'<tspan fill="{C["cyan_text"]}" font-weight="700" dx="8">▌{blink}</tspan></text>')

    # left frame
    a(f'  <rect x="{fx}" y="{fy}" width="{LEFT_W}" height="{CONTENT_H}" rx="16" fill="#F8FAFC" '
      f'stroke="url(#frame)" stroke-width="1.6"/>')
    a('  <g clip-path="url(#pf)">')
    a(particle_markup(main, bg, ox, oy, animate, frame=frame))
    a('  </g>')

    # right panel
    a(f'  <rect x="{RIGHT_X}" y="{CONTENT_Y}" width="{RIGHT_W}" height="{CONTENT_H}" rx="16" fill="{C["panel"]}" '
      f'stroke="{C["line"]}" stroke-width="1.2"/>')
    hy = CONTENT_Y + 46
    a(f'  <text x="{rx0}" y="{hy}" font-size="21" font-weight="700" fill="{C["cyan_text"]}" letter-spacing="1.6">SYSTEM.INFO</text>')
    live_x = rx1
    pulse = ('<animate attributeName="opacity" values="1;.35;1" dur="1.8s" repeatCount="indefinite"/>' if animate else "")
    a(f'  <circle cx="{live_x - 64}" cy="{hy - 7}" r="5.5" fill="#10B981">{pulse}</circle>')
    a(f'  <text x="{live_x}" y="{hy}" font-size="17" font-weight="700" fill="{C["text"]}" text-anchor="end" letter-spacing="1.8">LIVE</text>')
    a(f'  <line x1="{rx0}" y1="{hy + 18}" x2="{rx1}" y2="{hy + 18}" stroke="{C["line"]}" stroke-width="1.2"/>')

    y = hy + 18 + 40
    pitch = 30
    a('  <g>')
    for lab, val in INFO:
        a("    " + row(lab, val, y, size, C["text"], rx0, rx1))
        y += pitch
    a('  </g>')
    sep = y - pitch + 21
    a(f'  <line x1="{rx0}" y1="{sep}" x2="{rx1}" y2="{sep}" stroke="{C["line"]}" stroke-width="1.2"/>')
    y = sep + 36
    a('  <g>')
    for lab, val in LINKS:
        a("    " + row(lab, val, y, size, C["purple"], rx0, rx1))
        y += pitch
    a('  </g>')
    py = CONTENT_Y + CONTENT_H - 26
    a(f'  <text x="{rx0}" y="{py}" font-size="16" fill="{C["text2"]}">'
      f'<tspan fill="{C["cyan_text"]}" font-weight="700">▸</tspan> More about me &amp; projects below in README</text>')

    # outer border on top
    a(f'  <rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="22" fill="none" stroke="url(#frame)" stroke-width="2"/>')
    a('</svg>')
    return "\n".join(L) + "\n"


def build_portrait_svg(main, bg, animate=False):
    pad = 0
    inner = particle_markup(main, bg, pad, pad, animate)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{INNER_W}" height="{INNER_H}" '
            f'viewBox="0 0 {INNER_W} {INNER_H}"><rect width="{INNER_W}" height="{INNER_H}" fill="#F8FAFC"/>\n'
            f'{inner}\n</svg>\n')


# --------------------------------------------------------------------------
# Rasterising previews (cairosvg, else system librsvg through ctypes)
# --------------------------------------------------------------------------
def rasterize(svg_path: Path, png_path: Path, width: int) -> bool:
    try:
        import cairosvg  # type: ignore
        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path), output_width=width)
        return True
    except Exception:
        pass
    try:
        cairo = ctypes.CDLL("libcairo.so.2")
        rsvg = ctypes.CDLL("librsvg-2.so.2")

        class Dim(ctypes.Structure):
            _fields_ = [("width", ctypes.c_int), ("height", ctypes.c_int),
                        ("em", ctypes.c_double), ("ex", ctypes.c_double)]
        rsvg.rsvg_handle_new_from_file.restype = ctypes.c_void_p
        rsvg.rsvg_handle_new_from_file.argtypes = [ctypes.c_char_p, ctypes.c_void_p]
        rsvg.rsvg_handle_get_dimensions.argtypes = [ctypes.c_void_p, ctypes.POINTER(Dim)]
        rsvg.rsvg_handle_render_cairo.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        cairo.cairo_image_surface_create.restype = ctypes.c_void_p
        cairo.cairo_image_surface_create.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
        cairo.cairo_create.restype = ctypes.c_void_p
        cairo.cairo_create.argtypes = [ctypes.c_void_p]
        cairo.cairo_scale.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_double]
        cairo.cairo_surface_write_to_png.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        h = rsvg.rsvg_handle_new_from_file(str(svg_path).encode(), None)
        if not h:
            return False
        d = Dim()
        rsvg.rsvg_handle_get_dimensions(h, ctypes.byref(d))
        k = width / d.width
        surf = cairo.cairo_image_surface_create(0, int(round(d.width * k)), int(round(d.height * k)))
        cr = cairo.cairo_create(surf)
        cairo.cairo_scale(cr, k, k)
        rsvg.rsvg_handle_render_cairo(h, cr)
        cairo.cairo_surface_write_to_png(surf, str(png_path).encode())
        return True
    except Exception:
        return False


def main_cli():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--photo", type=Path, default=CFG["photo"])
    ap.add_argument("--out", type=Path, default=ROOT / "profile.svg")
    ap.add_argument("--particles", type=int, default=CFG["particles"])
    ap.add_argument("--iters", type=int, default=CFG["lloyd_iters"])
    ap.add_argument("--no-animate", action="store_true", help="write a fully static SVG")
    ap.add_argument("--no-preview", action="store_true")
    ap.add_argument("--frame", type=float, help="write a static preview of the banner at this time (s) of the loop")
    ap.add_argument("--debug-dir", type=Path)
    a = ap.parse_args()

    cfg = dict(CFG, photo=a.photo, particles=a.particles, lloyd_iters=a.iters)
    main, bg, _info = build_particles(cfg, a.debug_dir)
    if a.frame is not None:
        f = a.out.with_suffix(".frame.svg")
        f.write_text(build_svg(main, bg, animate=False, frame=a.frame), encoding="utf-8")
        ok = rasterize(f, a.out.with_suffix(".frame.png"), W)
        print("frame", a.frame, "->", f.with_suffix(".png") if ok else "(no rasterizer)")
        return 0
    svg = build_svg(main, bg, animate=not a.no_animate)
    a.out.write_text(svg, encoding="utf-8")
    print(f"wrote {a.out}  ({len(svg) / 1024:.0f} KB, {len(main['x'])} particles + {len(bg['x'])} atmosphere)")

    if not a.no_preview:
        assets = ROOT / "assets"
        assets.mkdir(exist_ok=True)
        tmp = assets / "_portrait-static.svg"
        tmp.write_text(build_portrait_svg(main, bg, animate=False), encoding="utf-8")
        ok1 = rasterize(tmp, assets / "portrait-preview.png", INNER_W * 2)
        tmp.unlink()
        static = a.out.with_name("_static_tmp.svg")
        static.write_text(build_svg(main, bg, animate=False), encoding="utf-8")
        ok2 = rasterize(static, assets / "banner-preview.png", W)
        static.unlink()
        print("previews:", "ok" if ok1 and ok2 else "skipped (install cairosvg to enable)")


if __name__ == "__main__":
    sys.exit(main_cli())
