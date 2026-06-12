"""Image utilities: download, cache, and decorate player photos."""
from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter

from src.utils.config import config


def _photo_path(player_id: str) -> Path:
    return config.player_photo_cache / f"{player_id}.jpg"


def cached_photo_exists(player_id: str) -> bool:
    return _photo_path(player_id).exists()


def fetch_photo(url: str, player_id: str, timeout: int = 10) -> Path | None:
    """Download and cache a player photo. Returns local path or None on failure."""
    if not url:
        return None
    target = _photo_path(player_id)
    if target.exists():
        return target
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        img.save(target, "JPEG", quality=88)
        return target
    except Exception:
        return None


def process_photo(
    src_path: str | Path,
    out_path: str | Path,
    size: tuple[int, int] = (300, 300),
    rounded: bool = True,
    add_shadow: bool = True,
) -> Path:
    """Crop to square, optionally add rounded corners and shadow."""
    img = Image.open(src_path).convert("RGBA")
    # center crop to square
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    img = img.resize(size, Image.LANCZOS)

    if rounded:
        mask = Image.new("L", size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size[0], size[1]), fill=255)
        out = Image.new("RGBA", size, (0, 0, 0, 0))
        out.paste(img, (0, 0), mask)
        img = out

    if add_shadow:
        shadow = Image.new("RGBA", (size[0] + 20, size[1] + 20), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.ellipse(
            (10, 10, size[0] + 10, size[1] + 10), fill=(0, 0, 0, 110)
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(8))
        canvas = Image.new("RGBA", shadow.size, (0, 0, 0, 0))
        canvas.paste(shadow, (0, 0), shadow)
        if rounded:
            canvas.paste(img, (10, 10), img)
        else:
            canvas.paste(img, (10, 10))
        canvas.convert("RGB").save(out_path, "JPEG", quality=92)
    else:
        img.convert("RGB").save(out_path, "JPEG", quality=92)

    return Path(out_path)


def player_id_from_name(name: str) -> str:
    return hashlib.md5(name.lower().encode("utf-8")).hexdigest()[:12]
