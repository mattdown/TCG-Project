"""Bake the client's placeholder sprites from the mockup's SVG shapes (docs/client-design.md).

Writes PNGs to Assets/Art/Generated. Run from TCGClient/:

    uv run --with pillow python Tools/make_placeholder_sprites.py

Sprites are drawn at 4 texture pixels per canvas pixel so cards stay sharp when inspected
at 2x. White sprites are tinted in Unity; the stat icons are baked in their final colours.
"""
import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "Assets" / "Art" / "Generated"
SCALE = 4  # texture px per canvas px
SS = 4  # supersampling for anti-aliasing

NAVY = "#0E1733"
ASPECTS = {  # aspect_N: (colour, light, dark)
    1: ("#F0533A", "#FFC2A8", "#7E1E10"),
    2: ("#2F86E8", "#B8E0FF", "#0F3A75"),
    3: ("#43B04F", "#C9F2B6", "#145A22"),
    4: ("#F5B52E", "#FFF0B0", "#7A4A05"),
    5: ("#9152E0", "#E2C8FF", "#3A1670"),
    6: ("#22BCC9", "#C2F6F8", "#0A5560"),
}


# --- a tiny SVG path flattener (M L H V C S A Z, absolute and relative)

def path_points(d: str, steps: int = 24) -> list[list[tuple[float, float]]]:
    tokens = re.findall(r"[MmLlHhVvCcSsAaZz]|-?\d*\.?\d+(?:e-?\d+)?", d)
    subpaths, pts = [], []
    x = y = sx = sy = 0.0
    last_ctrl = None
    cmd = None
    i = 0

    def num():
        nonlocal i
        v = float(tokens[i])
        i += 1
        return v

    while i < len(tokens):
        if re.match(r"[A-Za-z]", tokens[i]):
            cmd = tokens[i]
            i += 1
            if cmd in "Zz":
                if pts:
                    subpaths.append(pts)
                pts, x, y, last_ctrl = [], sx, sy, None
                continue
        rel = cmd.islower()
        c = cmd.upper()
        ox, oy = (x, y) if rel else (0.0, 0.0)
        if c == "M":
            if pts:
                subpaths.append(pts)
            x, y = ox + num(), oy + num()
            sx, sy = x, y
            pts = [(x, y)]
            cmd = "l" if rel else "L"
            last_ctrl = None
        elif c == "L":
            x, y = ox + num(), oy + num()
            pts.append((x, y))
            last_ctrl = None
        elif c == "H":
            x = ox + num()
            pts.append((x, y))
            last_ctrl = None
        elif c == "V":
            y = (y if rel else 0.0) + num()
            pts.append((x, y))
            last_ctrl = None
        elif c in "CS":
            if c == "C":
                x1, y1 = ox + num(), oy + num()
            else:
                x1, y1 = (2 * x - last_ctrl[0], 2 * y - last_ctrl[1]) if last_ctrl else (x, y)
            x2, y2 = ox + num(), oy + num()
            ex, ey = ox + num(), oy + num()
            for k in range(1, steps + 1):
                t = k / steps
                mt = 1 - t
                pts.append((mt**3 * x + 3 * mt**2 * t * x1 + 3 * mt * t**2 * x2 + t**3 * ex,
                            mt**3 * y + 3 * mt**2 * t * y1 + 3 * mt * t**2 * y2 + t**3 * ey))
            last_ctrl = (x2, y2)
            x, y = ex, ey
        elif c == "A":
            rx, ry, rot, large, sweep = num(), num(), num(), num(), num()
            ex, ey = ox + num(), oy + num()
            pts.extend(arc_points(x, y, rx, ry, rot, int(large), int(sweep), ex, ey, steps))
            x, y = ex, ey
            last_ctrl = None
    if pts:
        subpaths.append(pts)
    return subpaths


def arc_points(x1, y1, rx, ry, rot, large, sweep, x2, y2, steps):
    """SVG endpoint arc → points (implementation notes F.6.5)."""
    phi = math.radians(rot)
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = x1p**2 / rx**2 + y1p**2 / ry**2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx**2 * ry**2 - rx**2 * y1p**2 - ry**2 * x1p**2
    den = rx**2 * y1p**2 + ry**2 * x1p**2
    co = math.sqrt(max(0.0, num / den)) * (-1 if large == sweep else 1)
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx = cp * cxp - sp * cyp + (x1 + x2) / 2
    cy = sp * cxp + cp * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi
    out = []
    for k in range(1, steps + 1):
        t = t1 + dt * k / steps
        out.append((cx + rx * math.cos(t) * cp - ry * math.sin(t) * sp,
                    cy + rx * math.cos(t) * sp + ry * math.sin(t) * cp))
    return out


def circle(cx, cy, r):
    return f"M{cx - r} {cy}A{r} {r} 0 1 1 {cx + r} {cy}A{r} {r} 0 1 1 {cx - r} {cy}Z"


def rrect(x, y, w, h, r):
    return (f"M{x + r} {y}H{x + w - r}A{r} {r} 0 0 1 {x + w} {y + r}V{y + h - r}"
            f"A{r} {r} 0 0 1 {x + w - r} {y + h}H{x + r}A{r} {r} 0 0 1 {x} {y + h - r}"
            f"V{y + r}A{r} {r} 0 0 1 {x + r} {y}Z")


class Canvas:
    """Draws SVG-style shapes into a supersampled RGBA image."""

    def __init__(self, view_x, view_y, view_w, view_h, px_per_unit):
        self.vx, self.vy, self.k = view_x, view_y, px_per_unit * SS
        self.size = (round(view_w * px_per_unit), round(view_h * px_per_unit))
        self.img = Image.new("RGBA", (self.size[0] * SS, self.size[1] * SS), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.img)
        self.transform = lambda p: p

    def _map(self, p):
        x, y = self.transform(p)
        return ((x - self.vx) * self.k, (y - self.vy) * self.k)

    def shape(self, d, fill=None, stroke=None, width=0.0, closed_stroke=True):
        for sub in path_points(d):
            pts = [self._map(p) for p in sub]
            if fill and len(pts) > 2:
                self.draw.polygon(pts, fill=fill)
            if stroke and width:
                w = max(1, round(width * self.k))
                line = pts + [pts[0]] if closed_stroke and len(pts) > 2 else pts
                self.draw.line(line, fill=stroke, width=w, joint="curve")
                r = w / 2
                for p in (line[0], line[-1]):
                    self.draw.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=stroke)

    def save(self, name):
        OUT.mkdir(parents=True, exist_ok=True)
        self.img.resize(self.size, Image.LANCZOS).save(OUT / f"{name}.png")


def rounded_slice():
    """White rounded rect for 9-slicing: corner radius 16 canvas px."""
    c = Canvas(0, 0, 40, 40, SCALE)
    c.shape(rrect(0, 0, 40, 40, 16), fill="white")
    c.save("rounded")


def glow():
    """Soft white halo around a rounded rect, 9-sliced behind glowing cards."""
    pad, r = 24, 16
    size = 2 * pad + 40
    img = Image.new("L", (size * SCALE, size * SCALE), 0)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([pad * SCALE, pad * SCALE, (size - pad) * SCALE, (size - pad) * SCALE],
                        radius=r * SCALE, fill=255)
    img = img.filter(ImageFilter.GaussianBlur(7 * SCALE))
    out = Image.new("RGBA", img.size, (255, 255, 255, 0))
    out.putalpha(img)
    OUT.mkdir(parents=True, exist_ok=True)
    out.save(OUT / "glow.png")


HEX = "M12 1.5l9.5 5.7v11.6L12 24.5l-9.5-5.7V7.2z"


def gem():
    k = SCALE * 1.5  # the card's cost gem is 36x39 for a 24x26 view box
    c = Canvas(0, 0, 24, 26, k)
    c.shape(HEX, fill="white")
    c.save("gem_fill")
    c = Canvas(0, 0, 24, 26, k)
    c.shape(HEX, stroke="white", width=2.2)
    c.save("gem_rim")
    c = Canvas(0, 0, 24, 26, k)
    c.shape("M12 4.5l6.5 3.8", stroke="white", width=1.8, closed_stroke=False)
    c.save("gem_shine")


def heart():
    c = Canvas(0, 0, 24, 22, SCALE * 1.5)
    c.shape("M12 20.5S2 14.5 2 8a5 5 0 0 1 10-1.5A5 5 0 0 1 22 8c0 6.5-10 12.5-10 12.5z",
            fill="#E8364F", stroke=NAVY, width=1.8)
    c.save("heart")


def crown():
    c = Canvas(0, 0, 24, 20, SCALE * 1.0)
    c.shape("M2 17h20l-2-12-5 5-3-8-3 8-5-5z", fill="#FFC93C", stroke=NAVY, width=2.3)
    c.save("crown")


def sword():
    """The power icon: a sword through an orange circle, rotated 45 degrees. View box -12..56."""
    c = Canvas(-12, -12, 68, 68, SCALE)
    a = math.radians(45)

    def rot(p):
        x, y = p[0] - 22, p[1] - 22
        return (22 + x * math.cos(a) - y * math.sin(a), 22 + x * math.sin(a) + y * math.cos(a))

    c.transform = rot
    c.shape("M18.5 -2L22 -8l3.5 6v32h-7z", fill="#E4EAF4", stroke=NAVY, width=1.8)
    c.shape("M22 -5v10", stroke="white", width=1.4, closed_stroke=False)
    c.shape(rrect(12, 29.5, 20, 4.5, 2.2), fill="#FFC93C", stroke=NAVY, width=1.8)
    c.shape(rrect(20, 34, 4, 6, 0.01), fill="#7A4A05", stroke=NAVY, width=1.8)
    c.shape(circle(22, 41.5, 2.2), fill="#FFC93C", stroke=NAVY, width=1.8)
    c.shape(circle(22, 19, 10.5), fill="#F08A24", stroke=NAVY, width=1.8)
    c.save("sword")


ARTS = {
    "knight": [("M18 60c0-14 6-25 14-25s14 11 14 25z", True), ("M23 30v-8a9 10 0 0 1 18 0v8z", True),
               ("M32 12c3-6 10-7 13-4-5 0-8 2-9 6", True), ("M47 56l7-30", False), (circle(21, 47, 8), True)],
    "beast": [("M14 12l12 11h12l12-11 1 19c0 14-9 27-19 27S13 45 13 31z", True), ("M26 44l6 6 6-6", False)],
    "mage": [("M19 60l5-22h16l5 22z", True), (circle(32, 32, 7), True), ("M32 4l12 23H20z", True),
             ("M50 60l2-36", False), (circle(52, 20, 5), "white")],
    "golem": [(rrect(17, 28, 30, 30, 6), True), (rrect(23, 10, 18, 16, 4), True), (rrect(6, 30, 10, 22, 4), True),
              (rrect(48, 30, 10, 22, 4), True), ("M28 18h8", False)],
}


def art():
    """Card art per aspect and silhouette: radial glow, ground shadow, white-outlined figure."""
    w, h = 138, 92
    for n, (col, light, dark) in ASPECTS.items():
        bg = radial(w, h, light, col, dark)
        shadow = Image.new("L", bg.size, 0)
        ImageDraw.Draw(shadow).ellipse([34 * SCALE, (h - 26) * SCALE, (w - 34) * SCALE, (h - 14) * SCALE],
                                       fill=round(255 * 0.35))
        bg.paste(Image.new("RGBA", bg.size, NAVY), (0, 0), shadow)
        for name, parts in ARTS.items():
            c = Canvas(0, 0, 64, 64, SCALE * 70 / 64)
            for d, filled in parts:
                fill = "white" if filled == "white" else (dark if filled else None)
                c.shape(d, fill=fill, stroke="white", width=2.5, closed_stroke=filled is not False)
            fig = c.img.resize(c.size, Image.LANCZOS)
            out = bg.copy()
            out.alpha_composite(fig, (36 * SCALE, 12 * SCALE))
            out.save(OUT / f"art_{n}_{name}.png")


def radial(w, h, c0, c1, c2):
    """CSS radial-gradient(circle at 50% 45%, c0 0%, c1 50%, c2 100%), farthest-corner."""
    W, H = w * SCALE, h * SCALE
    cx, cy = W * 0.5, H * 0.45
    R = math.hypot(max(cx, W - cx), max(cy, H - cy))
    cols = [tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in (c0, c1, c2)]
    img = Image.new("RGBA", (W, H))
    px = img.load()
    for y in range(H):
        for x in range(W):
            t = min(1.0, math.hypot(x - cx, y - cy) / R)
            a, b, u = (cols[0], cols[1], t / 0.5) if t < 0.5 else (cols[1], cols[2], (t - 0.5) / 0.5)
            px[x, y] = tuple(round(a[i] + (b[i] - a[i]) * u) for i in range(3)) + (255,)
    return img


def field():
    """Checkerboard tile (two 44 px squares a side) and the navy fade at the top and bottom."""
    tile = Image.new("RGBA", (88, 88), "#5E9C57")
    d = ImageDraw.Draw(tile)
    d.rectangle([44, 0, 87, 43], fill="#5A9753")
    d.rectangle([0, 44, 43, 87], fill="#5A9753")
    tile.save(OUT / "field_tile.png")
    stops = [(0, 0.95), (0.08, 0.55), (0.18, 0), (0.62, 0), (0.78, 0.7), (1, 0.95)]
    fade = Image.new("RGBA", (4, 720))
    for y in range(720):
        t = y / 719
        for (t0, a0), (t1, a1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                a = a0 + (a1 - a0) * (t - t0) / (t1 - t0)
                break
        for x in range(4):
            fade.putpixel((x, y), (22, 32, 61, round(a * 255)))
    fade.save(OUT / "field_fade.png")


def interaction():
    """Drag feedback: zone outline, arrow dots and head, target ring, VP stripes, dashed gem."""
    c = Canvas(0, 0, 40, 40, SCALE)
    c.shape(rrect(1.5, 1.5, 37, 37, 14.5), stroke="white", width=3)
    c.save("ring")
    c = Canvas(0, 0, 16, 16, SCALE)
    c.shape(circle(8, 8, 7.5), fill="white")
    c.save("dot")
    c = Canvas(0, 0, 64, 64, SCALE)
    c.shape(circle(32, 32, 29), stroke="white", width=4)
    c.save("target_ring")
    c = Canvas(-2, -2, 36, 36, SCALE)  # points along +x, tip at (32, 16)
    c.shape("M32 16L4 2L9 16L4 30Z", fill="white", stroke=NAVY, width=3)
    c.save("arrow_head")
    tile = Image.new("RGBA", (40, 40), "#FFC93C")
    d = ImageDraw.Draw(tile)
    for k in range(-2, 3):  # 135 degree stripes, 10 px period at 4 px per canvas px
        o = k * 40
        d.polygon([(o, 40), (o + 20, 40), (o + 60, 0), (o + 40, 0)], fill="#F5B52E")
    tile.save(OUT / "stripes.png")
    c = Canvas(0, 0, 24, 26, SCALE * 26 / 24)
    pts = path_points(HEX)[0]
    pts = pts + [pts[0]]
    dash, on, t = 3.0, True, 0.0
    for a, b in zip(pts, pts[1:]):
        seg = math.dist(a, b)
        pos = 0.0
        while pos < seg:
            run = min(dash - t, seg - pos)
            if on:
                p0 = (a[0] + (b[0] - a[0]) * pos / seg, a[1] + (b[1] - a[1]) * pos / seg)
                p1 = (a[0] + (b[0] - a[0]) * (pos + run) / seg, a[1] + (b[1] - a[1]) * (pos + run) / seg)
                c.shape(f"M{p0[0]} {p0[1]}L{p1[0]} {p1[1]}", stroke="white", width=2.2, closed_stroke=False)
            pos += run
            t += run
            if t >= dash:
                t, on = 0.0, not on
    c.save("gem_dashed")


if __name__ == "__main__":
    rounded_slice()
    glow()
    gem()
    heart()
    crown()
    sword()
    field()
    art()
    interaction()
    print(f"wrote {len(list(OUT.glob('*.png')))} sprites to {OUT}")
