"""Cut the card parts out of the green-screen sheet (ArtSource/ui/card_parts_sheet.jpg).

Writes transparent PNGs to Assets/Art/Sprites: card_job_banner.png, card_attack.png and
card_defence.png. Run from TCGClient/:

    uv run --no-project --with pillow --with numpy --with scipy python Tools/cut_card_parts.py

The key works on how much greener than red and blue a pixel is, so the screen goes but the
banner's vines (a darker, less saturated green) stay. Each part is the largest shape inside a
rough box, so the labels under the parts and anything poking in from a neighbour are dropped.
"""
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
SHEET = ROOT / "ArtSource" / "ui" / "card_parts_sheet.jpg"
OUT = ROOT / "Assets" / "Art" / "Sprites"

# Rough boxes (x0, y0, x1, y1) on the 2000x1116 sheet; each holds one part.
PARTS = {
    "card_job_banner": (100, 0, 1960, 545),
    "card_attack": (60, 490, 640, 1045),
    "card_defence": (1280, 560, 1710, 1045),
}
KEY_FULL = 110  # greenness (g - max(r, b)) at which a pixel is fully screen
KEY_NONE = 55   # greenness at which a pixel is fully kept
PAD = 4         # transparent margin kept round each trimmed part


def key(rgb: np.ndarray) -> np.ndarray:
    """Alpha from greenness, with a soft ramp between KEY_NONE and KEY_FULL."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    greenness = g - np.maximum(r, b)
    alpha = 1.0 - np.clip((greenness - KEY_NONE) / (KEY_FULL - KEY_NONE), 0.0, 1.0)
    # Smooth JPEG noise on the edge a little, without growing the shape.
    return np.minimum(alpha, ndimage.gaussian_filter(alpha, 0.7))


def despill(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Pull the green out of edge pixels (the fringe), leaving the inside of the art alone."""
    edge = ndimage.binary_dilation(alpha < 0.98, iterations=3)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    limit = np.maximum(r, b) + 8.0
    out = rgb.copy()
    out[..., 1] = np.where(edge & (g > limit), limit, g)
    return out


def largest_shape(alpha: np.ndarray) -> np.ndarray:
    """The largest connected opaque shape, as a mask (drops labels and strays)."""
    labels, count = ndimage.label(alpha > 0.5)
    if count == 0:
        return np.zeros_like(alpha, dtype=bool)
    sizes = ndimage.sum(np.ones_like(alpha), labels, index=range(1, count + 1))
    main = labels == (int(np.argmax(sizes)) + 1)
    # Keep the soft edge that belongs to it: everything within a few pixels of the shape.
    return ndimage.binary_dilation(ndimage.binary_fill_holes(main), iterations=3)


def bleed(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Fill fully transparent pixels with the nearest kept colour.

    Their colour is invisible but still in the file: left as the sheet's, it would carry the
    green screen and bits of neighbouring parts (the sword's pommel under the banner), which show
    in viewers that ignore alpha and can bleed in when the sprite is filtered or mipmapped.
    """
    _, (iy, ix) = ndimage.distance_transform_edt(alpha <= 0.0, return_indices=True)
    return rgb[iy, ix]


def cut(sheet: np.ndarray, box: tuple[int, int, int, int]) -> Image.Image:
    x0, y0, x1, y1 = box
    rgb = sheet[y0:y1, x0:x1].astype(np.float32)
    alpha = key(rgb)
    alpha = np.where(largest_shape(alpha), alpha, 0.0)
    rgb = bleed(despill(rgb, alpha), alpha)
    ys, xs = np.nonzero(alpha > 0.02)
    top, bottom = max(ys.min() - PAD, 0), min(ys.max() + PAD + 1, alpha.shape[0])
    left, right = max(xs.min() - PAD, 0), min(xs.max() + PAD + 1, alpha.shape[1])
    rgba = np.dstack([rgb, alpha * 255.0])[top:bottom, left:right]
    return Image.fromarray(np.clip(rgba, 0, 255).astype(np.uint8), "RGBA")


def main():
    sheet = np.asarray(Image.open(SHEET).convert("RGB"))
    OUT.mkdir(parents=True, exist_ok=True)
    for name, box in PARTS.items():
        part = cut(sheet, box)
        part.save(OUT / f"{name}.png")
        print(f"{name}.png  {part.width}x{part.height}")


if __name__ == "__main__":
    main()
