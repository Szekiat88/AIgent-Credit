"""
PDF OCR layer.  Converts every page of a scanned-image PDF to plain text
using Tesseract 5.  Results are cached on disk so re-runs are instant.
"""

import hashlib
import json
import os
import re
import subprocess

_TESSERACT_PATHS = [
    "/opt/homebrew/bin/tesseract",
    "/usr/local/bin/tesseract",
    "tesseract",
]

_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".ocr_cache")


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------

def _tesseract_bin() -> str:
    for p in _TESSERACT_PATHS:
        try:
            subprocess.run([p, "--version"], capture_output=True, check=True)
            return p
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    raise RuntimeError(
        "tesseract not found.  Install with: brew install tesseract"
    )


def _pdf_hash(pdf_path: str) -> str:
    h = hashlib.md5()
    with open(pdf_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_path(pdf_path: str) -> str:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    return os.path.join(_CACHE_DIR, _pdf_hash(pdf_path) + ".json")


def _load_cache(pdf_path: str):
    cp = _cache_path(pdf_path)
    if os.path.exists(cp):
        with open(cp, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _save_cache(pdf_path: str, pages: list):
    cp = _cache_path(pdf_path)
    with open(cp, "w", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False)


# ---------------------------------------------------------------------------
# OCR one page image
# ---------------------------------------------------------------------------

def _ocr_image(img, tess_bin: str) -> str:
    """Run tesseract on a PIL image and return text."""
    import tempfile
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = tess_bin
    # PSM 6 = uniform block of text; good for financial report pages
    custom_config = r"--oem 3 --psm 6 -l eng"
    return pytesseract.image_to_string(img, config=custom_config)


def _preprocess(img):
    """Grayscale + mild sharpening; keeps numbers legible for Tesseract."""
    from PIL import ImageFilter, ImageOps
    img = img.convert("L")          # greyscale
    img = ImageOps.autocontrast(img)
    img = img.filter(ImageFilter.SHARPEN)
    return img


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def extract_pages(pdf_path: str, dpi: int = 300, verbose: bool = True) -> list[dict]:
    """
    Return a list of dicts, one per page:
        {"page": 1, "text": "...raw OCR text..."}

    Results are cached by PDF content hash.
    """
    cached = _load_cache(pdf_path)
    if cached is not None:
        if verbose:
            print(f"[OCR] Using cached text for {os.path.basename(pdf_path)} "
                  f"({len(cached)} pages)")
        return cached

    tess_bin = _tesseract_bin()

    try:
        from pdf2image import convert_from_path
    except ImportError:
        raise RuntimeError("pdf2image not installed.  Run: pip install pdf2image")

    if verbose:
        print(f"[OCR] Converting {os.path.basename(pdf_path)} to images at {dpi} dpi …")

    images = convert_from_path(pdf_path, dpi=dpi)
    pages = []
    for i, img in enumerate(images, start=1):
        if verbose:
            print(f"[OCR]   page {i}/{len(images)}", end="\r", flush=True)
        processed = _preprocess(img)
        text = _ocr_image(processed, tess_bin)
        pages.append({"page": i, "text": text})

    if verbose:
        print(f"\n[OCR] Done — {len(pages)} pages extracted.")

    _save_cache(pdf_path, pages)
    return pages


def full_text(pages: list[dict]) -> str:
    """Concatenate all page texts with page markers."""
    parts = []
    for p in pages:
        parts.append(f"\n<<PAGE {p['page']}>>\n{p['text']}")
    return "\n".join(parts)


def clean(text: str) -> str:
    """Collapse whitespace and fix common OCR artefacts."""
    # common digit/letter confusions in number context
    text = re.sub(r'(?<=\d)O(?=\d)', '0', text)   # 1O23 → 1023
    text = re.sub(r'(?<=\d)l(?=\d)', '1', text)   # 1l23 → 1123
    text = re.sub(r'(?<=\d)I(?=\d)', '1', text)
    text = re.sub(r'(?<=[,(] )O', '0', text)
    # collapse runs of spaces / CR
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
