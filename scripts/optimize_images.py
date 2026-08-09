"""Build compact WebP derivatives for the static question images."""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "static" / "images"
OUTPUT_ROOT = ROOT / "static" / "optimized_images"
SUPPORTED_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".png", ".webp"}
MAX_EDGE = 2000
WEBP_QUALITY = 84


def optimize_image(source: Path) -> bool:
    relative_path = source.relative_to(SOURCE_ROOT)
    target = (OUTPUT_ROOT / relative_path).with_suffix(relative_path.suffix + ".webp")
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
        return False

    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened)
        image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)

        if "A" in image.getbands() or "transparency" in image.info:
            image = image.convert("RGBA")
        else:
            image = image.convert("RGB")

        image.save(target, "WEBP", quality=WEBP_QUALITY, method=6)

    return True


def main() -> None:
    if not SOURCE_ROOT.is_dir():
        raise SystemExit(f"Image directory not found: {SOURCE_ROOT}")

    generated = 0
    failures = []
    for source in sorted(SOURCE_ROOT.rglob("*")):
        if not source.is_file() or source.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        try:
            generated += int(optimize_image(source))
        except Exception as error:  # Keep one malformed upload from breaking a deploy.
            failures.append(f"{source}: {error}")

    print(f"Optimized {generated} image(s) into {OUTPUT_ROOT}")
    if failures:
        print(f"Skipped {len(failures)} image(s):")
        for failure in failures:
            print(f"- {failure}")


if __name__ == "__main__":
    main()
