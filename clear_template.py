import os
import cv2
import numpy as np
import json
from utils.image_processing import preprocess_image, match_template, load_templates, ROOT_TEMPLATE_DIR, SUPPORTED_SITES

# โหลด templates เข้าหน่วยความจำ
load_templates()

# ==================== CONFIG ====================
MIN_CONFIDENCE = 80.0
MIN_BLACK_RATIO = 0.10
MAX_BLACK_RATIO = 0.85
MIN_CONTOURS = 1
MAX_CONTOURS = 3
LOG_PATH = "cleared_templates_log.json"
# ================================================

log_data = []

def is_bad_template(img: np.ndarray):
    """ตรวจสอบลักษณะของภาพที่อาจจะใช้ไม่ได้"""
    black_ratio = np.count_nonzero(img == 0) / img.size
    if black_ratio < MIN_BLACK_RATIO:
        return "black_ratio too low", black_ratio
    if black_ratio > MAX_BLACK_RATIO:
        return "black_ratio too high", black_ratio

    contours, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if len(contours) < MIN_CONTOURS:
        return "too few contours", len(contours)
    if len(contours) > MAX_CONTOURS:
        return "too many contours", len(contours)

    return None, None

# ✅ วนตรวจทุก site ใน template directory
for site in SUPPORTED_SITES:
    site_dir = os.path.join(ROOT_TEMPLATE_DIR, site)
    if not os.path.exists(site_dir):
        continue

    print(f"\n🔍 ตรวจสอบเทมเพลตของไซต์: {site}")
    for filename in os.listdir(site_dir):
        if not filename.endswith(".png"):
            continue

        filepath = os.path.join(site_dir, filename)
        label = filename.split("_")[0]

        img = cv2.imread(filepath, cv2.IMREAD_GRAYSCALE)
        if img is None:
            log_data.append({
                "filename": filepath,
                "site": site,
                "reason": "cannot read image"
            })
            continue

        img = preprocess_image(img)
        reason, value = is_bad_template(img)

        if reason:
            print(f"🗑️ {filepath} | {reason}: {value}")
            os.remove(filepath)
            log_data.append({
                "filename": filepath,
                "site": site,
                "reason": reason,
                "value": value
            })
            continue

        # ตรวจสอบการ match กับ templates ปัจจุบัน
        predicted_label, confidence = match_template(site, img)

        if predicted_label != label or confidence < MIN_CONFIDENCE:
            reason_text = "confidence too low" if confidence < MIN_CONFIDENCE else "wrong label"
            print(f"🗑️ {filepath} | predict: {predicted_label} ({confidence:.1f}%) != label {label}")
            os.remove(filepath)
            log_data.append({
                "filename": filepath,
                "site": site,
                "reason": reason_text,
                "predicted": predicted_label,
                "confidence": round(confidence, 2),
                "label": label
            })
        else:
            print(f"✅ {filepath} | OK ({confidence:.1f}%)")

# เขียน log ลงไฟล์
with open(LOG_PATH, "w", encoding="utf-8") as f:
    json.dump(log_data, f, indent=2, ensure_ascii=False)

print(f"\n🎯 เสร็จสิ้น — บันทึก log ที่ {LOG_PATH}")
