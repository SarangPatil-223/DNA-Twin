"""Image lab: how image data survives DNA storage.

Two ways to put an image into DNA:
  file   — store the original PNG/JPEG bytes. Compact, but one wrong bit inside the compressed
           stream usually makes the whole image undecodable (all-or-nothing).
  pixels — store raw 8-bit pixels (optionally downscaled / grayscale). Larger, but a wrong byte
           is one wrong pixel, so quality degrades gracefully and PSNR/SSIM stay meaningful.

Quality is measured with PSNR and SSIM against the original pixels at the same resolution.
The pixel header (width, height, channels) is kept out-of-band with the manifest, so a damaged
header does not stop reconstruction.
"""

from __future__ import annotations

import base64
import io
import shutil
import struct

import numpy as np
from PIL import Image, UnidentifiedImageError

PIXEL_MAGIC = b"DTPX"
_HDR = struct.Struct(">4sHHB")
MODES = ("file", "pixels", "pixels_gray")


def load(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img.load()
    return img


def _normalize(img: Image.Image, gray: bool, max_side: int | None) -> Image.Image:
    img = img.convert("L" if gray else "RGB")
    if max_side and max(img.size) > max_side:
        img = img.copy()
        img.thumbnail((max_side, max_side))
    return img


def prepare(data: bytes, mode: str = "pixels", max_side: int | None = 256) -> tuple[bytes, dict]:
    """Return (bytes to encode, info). info is the out-of-band description needed to rebuild."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    img = load(data)
    if mode == "file":
        ref = _normalize(img, False, None)
        return data, {"mode": mode, "width": ref.width, "height": ref.height, "channels": 3, "format": img.format}
    norm = _normalize(img, mode == "pixels_gray", max_side)
    arr = np.asarray(norm, dtype=np.uint8)
    c = 1 if arr.ndim == 2 else arr.shape[2]
    payload = _HDR.pack(PIXEL_MAGIC, norm.width, norm.height, c) + arr.tobytes()
    return payload, {"mode": mode, "width": norm.width, "height": norm.height, "channels": c, "format": "RAW"}


def reference_pixels(data: bytes, info: dict) -> np.ndarray:
    """Original pixels prepared exactly as `prepare` did (same thumbnail step), so an exact
    recovery scores SSIM 1.0."""
    img = load(data)
    gray = info["channels"] == 1
    img = _normalize(img, gray, None if info["mode"] == "file" else max(info["width"], info["height"]))
    if img.size != (info["width"], info["height"]):
        img = img.resize((info["width"], info["height"]), Image.BILINEAR)
    return np.asarray(img, dtype=np.uint8)


def reconstruct(recovered: bytes | None, info: dict) -> tuple[np.ndarray | None, str]:
    if recovered is None:
        return None, "no bytes recovered"
    if info["mode"] == "file":
        try:
            img = _normalize(load(recovered), False, None)
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
            return None, f"compressed image could not be decoded: {type(exc).__name__}"
        if img.size != (info["width"], info["height"]):
            return None, "decoded image has the wrong size"
        return np.asarray(img, dtype=np.uint8), "decoded"
    w, h, c = info["width"], info["height"], info["channels"]
    n = w * h * c
    body = recovered[_HDR.size : _HDR.size + n].ljust(n, b"\x00")
    arr = np.frombuffer(body, dtype=np.uint8)
    return (arr.reshape(h, w) if c == 1 else arr.reshape(h, w, c)), "rebuilt from raw pixels"


def lost_pixel_mask(info: dict, lost_ranges: list[tuple[int, int]], payload_offset: int) -> np.ndarray | None:
    """Mask of pixels whose bytes were zero-filled. `payload_offset` = where the pixel payload
    starts inside the container (container header length)."""
    if info["mode"] == "file":
        return None
    w, h, c = info["width"], info["height"], info["channels"]
    flat = np.zeros(w * h * c, dtype=bool)
    start = payload_offset + _HDR.size
    for a, b in lost_ranges:
        a, b = max(a - start, 0), min(b - start, flat.size)
        if b > a:
            flat[a:b] = True
    m = flat.reshape(h, w, c).any(axis=2) if c > 1 else flat.reshape(h, w)
    return m


def conceal(arr: np.ndarray, mask: np.ndarray | None, passes: int = 60) -> np.ndarray:
    """Error concealment: fill lost pixels by repeated averaging of known 4-neighbours
    (a simple diffusion inpainting). Known pixels are never changed."""
    if mask is None or not mask.any():
        return arr
    img = arr.astype(np.float32)
    if img.ndim == 2:
        img = img[..., None]
    known = ~mask
    fill = img.copy()
    mean = img[known].mean(axis=0) if known.any() else np.full(img.shape[2], 128.0)
    fill[mask] = mean
    for _ in range(passes):
        p = np.pad(fill, ((1, 1), (1, 1), (0, 0)), mode="edge")
        avg = (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]) / 4.0
        fill[mask] = avg[mask]
    out = np.clip(fill, 0, 255).astype(np.uint8)
    return out[..., 0] if arr.ndim == 2 else out


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))
    return float("inf") if mse == 0 else 10 * np.log10(255.0**2 / mse)


def ssim(a: np.ndarray, b: np.ndarray) -> float:
    from skimage.metrics import structural_similarity

    if min(a.shape[:2]) < 7:
        return 1.0 if np.array_equal(a, b) else 0.0
    return float(structural_similarity(a, b, channel_axis=2 if a.ndim == 3 else None, data_range=255))


def quality(ref: np.ndarray, got: np.ndarray | None) -> dict:
    if got is None or got.shape != ref.shape:
        return {"psnr_db": None, "ssim": None, "pixel_accuracy": 0.0, "decodable": False}
    p = psnr(ref, got)
    return {"psnr_db": None if p == float("inf") else round(float(p), 2), "psnr_infinite": bool(p == float("inf")),
            "ssim": round(ssim(ref, got), 4), "pixel_accuracy": float(np.mean(ref == got)), "decodable": True}


def to_png_b64(arr: np.ndarray | None) -> str | None:
    if arr is None:
        return None
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def diff_heatmap(ref: np.ndarray, got: np.ndarray | None) -> np.ndarray | None:
    if got is None or got.shape != ref.shape:
        return None
    d = np.abs(ref.astype(np.int16) - got.astype(np.int16))
    if d.ndim == 3:
        d = d.max(axis=2)
    d = (d.astype(np.float32) / 255.0) ** 0.5
    heat = np.zeros((*d.shape, 3), dtype=np.uint8)
    heat[..., 0] = (d * 255).astype(np.uint8)
    heat[..., 1] = (d * 90).astype(np.uint8)
    heat[..., 2] = (40 * (1 - d)).astype(np.uint8)
    return heat


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def ocr(arr: np.ndarray | None) -> str:
    if arr is None or not ocr_available():
        return ""
    import pytesseract

    try:
        return pytesseract.image_to_string(Image.fromarray(arr)).strip()
    except Exception:  # tesseract errors must never break retrieval
        return ""
