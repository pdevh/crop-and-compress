from pathlib import Path
from PIL import Image

def process_image(path: Path, crop: tuple[int, int, int, int] | None, 
                  scale_pct: int, max_dim: int, format_str: str, 
                  quality: int, output_dir: Path | None, replace_original: bool) -> Path:
    img = Image.open(path)
    img.load()
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    # crop
    if crop:
        w, h = img.size
        c = (max(0, crop[0]), max(0, crop[1]),
             min(w, crop[2]), min(h, crop[3]))
        img = img.crop(c)

    # scale %
    scale = scale_pct / 100.0
    if scale < 1.0:
        nw = max(1, int(img.size[0] * scale))
        nh = max(1, int(img.size[1] * scale))
        img = img.resize((nw, nh), Image.LANCZOS)

    # max long-edge
    if maxdim := max_dim:
        if maxdim > 0:
            w, h = img.size
            if max(w, h) > maxdim:
                ratio = maxdim / max(w, h)
                img = img.resize(
                    (max(1, int(w * ratio)), max(1, int(h * ratio))),
                    Image.LANCZOS
                )

    # Determine output extension
    ext = path.suffix.lower()
    if format_str == "PNG":
        ext = ".png"
    elif format_str == "JPEG":
        ext = ".jpg"
    elif format_str == "WebP":
        ext = ".webp"
    
    # Determine output path
    if replace_original:
        out_path = path.with_suffix(ext)
    else:
        out_path = output_dir / path.with_suffix(ext).name
        
        # Resolve name collisions
        base = out_path.stem
        suffix = out_path.suffix
        counter = 2
        while out_path.exists():
            out_path = out_path.with_name(f"{base}_{counter}{suffix}")
            counter += 1

    # Perform the actual save
    if ext == ".png":
        img.save(out_path, "PNG", optimize=True)
    elif ext in (".jpg", ".jpeg"):
        # If image has alpha and we are saving to JPEG, convert to RGB with white background
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)
            img = bg
        img.save(out_path, "JPEG", quality=quality, optimize=True)
    elif ext == ".webp":
        img.save(out_path, "WebP", quality=quality, method=4)
    else:
        img.save(out_path)

    return out_path
