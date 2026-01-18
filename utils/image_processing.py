import os
import cv2
import numpy as np
from dotenv import load_dotenv
from typing import List, Tuple, Optional, Dict

# ---------------- Environment ----------------
load_dotenv()

# ---------------- Constants ----------------
SUPPORTED_SITES = ["thai_789bet", "thai_jun88k36", "f168", "mk8"]

ROOT_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "captcha_templates")
os.makedirs(ROOT_TEMPLATE_DIR, exist_ok=True)

# templates[site][label] = [img, img, ...]
templates: Dict[str, Dict[str, List[np.ndarray]]] = {}

# ---------------- Helpers ----------------
def preprocess_image(img: np.ndarray, size=(30, 50)) -> np.ndarray:
    """Grayscale + resize + blur + binary threshold"""
    if len(img.shape) == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(img, size, interpolation=cv2.INTER_AREA)
    blurred = cv2.GaussianBlur(resized, (3, 3), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary

def _ensure_site_dirs():
    for s in SUPPORTED_SITES:
        path = os.path.join(ROOT_TEMPLATE_DIR, s)
        os.makedirs(path, exist_ok=True)

# ---------------- Load Templates ----------------
def load_templates(site: Optional[str] = None):
    """Load templates into memory (all or single site)"""
    _ensure_site_dirs()
    for s in SUPPORTED_SITES:
        templates.setdefault(s, {})

    sites_to_load = [site] if site else SUPPORTED_SITES
    print("🔄 Loading templates from local folder...")

    for s in sites_to_load:
        site_dir = os.path.join(ROOT_TEMPLATE_DIR, s)
        files = [f for f in os.listdir(site_dir) if f.endswith(".png")]
        templates[s] = {}
        for filename in files:
            label = filename.split("_")[0]
            path = os.path.join(site_dir, filename)
            img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                img = preprocess_image(img)
                templates[s].setdefault(label, []).append(img)

    total = sum(len(v) for site_map in templates.values() for v in site_map.values())
    site_counts = {s: sum(len(v) for v in templates.get(s, {}).values()) for s in SUPPORTED_SITES}
    print(f"✅ Loaded {total} templates across sites: {site_counts}")

# ---------------- Crop Captcha ----------------
def crop_captcha(img: np.ndarray, num_chars: int = 4) -> List[np.ndarray]:
    """Split captcha image horizontally"""
    if len(img.shape) == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    height, width = img.shape
    char_width = width // num_chars
    os.makedirs("cropped_debug", exist_ok=True)
    chars = []
    for i in range(num_chars):
        x_start = i * char_width
        char_img = img[0:height, x_start:x_start + char_width]
        cv2.imwrite(f"cropped_debug/char_{i}.png", char_img)
        chars.append(preprocess_image(char_img))
    return chars

# ---------------- Match Template ----------------
def match_template(site: str, img_char: np.ndarray) -> Tuple[Optional[str], float]:
    """Return best matching label and confidence"""
    site = site.lower()
    if site not in SUPPORTED_SITES:
        return "?", 0.0

    img_char = preprocess_image(img_char)
    best_label = None
    best_score = float("inf")

    site_templates = templates.get(site, {})
    if not site_templates:
        return "?", 0.0

    for label, template_list in site_templates.items():
        scores = []
        for template_img in template_list:
            try:
                res = cv2.matchTemplate(img_char, template_img, cv2.TM_SQDIFF_NORMED)
                min_val, _, _, _ = cv2.minMaxLoc(res)
                scores.append(min_val)
            except Exception:
                continue
        if scores:
            score = min(scores)
            if score < best_score:
                best_score = score
                best_label = label

    conf = max(0.0, min(100.0, (1.0 - best_score) * 100.0))
    return (best_label if best_label else "?"), conf

# ---------------- Save Templates ----------------
def save_templates(site: str, label: str, char_images: List[np.ndarray]) -> List[str]:
    """Save images and update memory templates"""
    site = site.lower()
    if site not in SUPPORTED_SITES:
        raise ValueError("unsupported site")

    site_dir = os.path.join(ROOT_TEMPLATE_DIR, site)
    os.makedirs(site_dir, exist_ok=True)

    saved_files = []

    templates.setdefault(site, {})

    if len(label) != len(char_images):
        raise ValueError(f"Label length ({len(label)}) does not match number of chars ({len(char_images)})")

    for i, char_img in enumerate(char_images):
        char_label = label[i]

        # ensure key exists
        templates[site].setdefault(char_label, [])

        processed_img = preprocess_image(char_img)

        existing = [f for f in os.listdir(site_dir) if f.startswith(f"{char_label}_") and f.endswith(".png")]
        filename = f"{char_label}_{len(existing)}.png"
        filepath = os.path.join(site_dir, filename)

        cv2.imwrite(filepath, processed_img)
        saved_files.append(filename)

        templates[site][char_label].append(processed_img)

    print(f"💾 Saved and added {len(saved_files)} templates for site '{site}'")
    return saved_files


# ---------------- Summary Helper ----------------
def get_template_summary() -> Dict[str, int]:
    """Return total templates count per site"""
    summary = {}
    for site, mapping in templates.items():
        summary[site] = sum(len(v) for v in mapping.values())
    summary["_total"] = sum(summary.values())
    return summary
