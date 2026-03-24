import os
import cv2
import numpy as np
import uuid
from dotenv import load_dotenv
from typing import List, Tuple, Optional, Dict

# ---------------- Environment ----------------
load_dotenv()

# ---------------- Constants ----------------
SUPPORTED_SITES = ["thai_789bet", "thai_jun88k36", "f168", "mk8"]

ROOT_TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "captcha_templates"
)
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
    _, binary = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    return binary


def _ensure_site_dirs():
    for s in SUPPORTED_SITES:
        path = os.path.join(ROOT_TEMPLATE_DIR, s)
        os.makedirs(path, exist_ok=True)


# ---------------- Load Templates ----------------
def load_templates(site: Optional[str] = None):
    """Load templates into memory (all or single site)"""
    _ensure_site_dirs()

    if site:
        sites_to_load = [site]
    else:
        sites_to_load = SUPPORTED_SITES

    print("🔄 Loading templates from disk...")

    for s in sites_to_load:
        site_dir = os.path.join(ROOT_TEMPLATE_DIR, s)
        templates[s] = {}

        if not os.path.exists(site_dir):
            continue

        files = [f for f in os.listdir(site_dir) if f.endswith(".png")]

        for filename in files:
            try:
                label = filename.split("_")[0]
                path = os.path.join(site_dir, filename)

                img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
                if img is None:
                    continue

                img = preprocess_image(img)
                templates[s].setdefault(label, []).append(img)

            except Exception:
                continue

    total = sum(
        len(v) for site_map in templates.values() for v in site_map.values()
    )
    site_counts = {
        s: sum(len(v) for v in templates.get(s, {}).values())
        for s in SUPPORTED_SITES
    }

    print(f"✅ Loaded {total} templates: {site_counts}")


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

        # debug
        cv2.imwrite(f"cropped_debug/char_{i}.png", char_img)

        chars.append(preprocess_image(char_img))

    return chars


# ---------------- Duplicate Check ----------------
def is_duplicate(img: np.ndarray, existing_list: List[np.ndarray], threshold=0.02):
    """Check if image is too similar to existing templates"""
    for t in existing_list:
        try:
            res = cv2.matchTemplate(img, t, cv2.TM_SQDIFF_NORMED)
            min_val, _, _, _ = cv2.minMaxLoc(res)
            if min_val < threshold:
                return True
        except Exception:
            continue
    return False


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
                res = cv2.matchTemplate(
                    img_char, template_img, cv2.TM_SQDIFF_NORMED
                )
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
    """Save templates safely (no overwrite + deduplicate optional)"""
    site = site.lower()

    if site not in SUPPORTED_SITES:
        raise ValueError("unsupported site")

    site_dir = os.path.join(ROOT_TEMPLATE_DIR, site)
    os.makedirs(site_dir, exist_ok=True)

    saved_files = []

    if len(label) != len(char_images):
        raise ValueError(
            f"Label length ({len(label)}) does not match chars ({len(char_images)})"
        )

    for i, char_img in enumerate(char_images):
        char_label = label[i]
        processed_img = preprocess_image(char_img)

        # 🔥 check duplicate (optional but recommended)
        existing_templates = templates.get(site, {}).get(char_label, [])
        if existing_templates and is_duplicate(processed_img, existing_templates):
            print(f"⚠️ Skip duplicate: {char_label}")
            continue

        filename = f"{char_label}_{uuid.uuid4().hex}.png"
        filepath = os.path.join(site_dir, filename)

        # 🔒 atomic write
        tmp_path = filepath + ".tmp.png"

        if not cv2.imwrite(tmp_path, processed_img):
            raise RuntimeError("Failed to write image")

        os.replace(tmp_path, filepath)
        saved_files.append(filename)

    print(f"💾 Saved {len(saved_files)} templates for '{site}'")

    return saved_files


# ---------------- Summary ----------------
def get_template_summary() -> Dict[str, int]:
    """Return template count per site"""
    summary = {}

    for site, mapping in templates.items():
        summary[site] = sum(len(v) for v in mapping.values())

    summary["_total"] = sum(summary.values())
    return summary