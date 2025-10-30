import os
import cv2
import numpy as np
import json
from utils.image_processing import preprocess_image, match_template, load_templates, template_dir

# โหลด templates
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

def is_bad_template(img):
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

# ✅ วนตรวจทุกไฟล์ในทุกโฟลเดอร์ย่อย
for root, dirs, files in os.walk(template_dir):
    for filename in files:
        if not filename.endswith(".png"):
            continue

        filepath = os.path.join(root, filename)
        label = filename.split("_")[0]

        img = cv2.imread(filepath, cv2.IMREAD_GRAYSCALE)
        if img is None:
            log_data.append({"filename": filename, "reason": "cannot read image"})
            continue

        img = preprocess_image(img)
        reason, value = is_bad_template(img)

        if reason:
            print(f"🗑️ {filepath} | {reason}: {value}")
            os.remove(filepath)
            log_data.append({
                "filename": filepath,
                "reason": reason,
                reason.split()[0]: value
            })
            continue

        predicted_label, confidence = match_template(img)

        if predicted_label != label or confidence < MIN_CONFIDENCE:
            print(f"🗑️ {filepath} | predict: {predicted_label} ({confidence:.1f}%) != label {label}")
            os.remove(filepath)
            log_data.append({
                "filename": filepath,
                "reason": "confidence too low" if confidence < MIN_CONFIDENCE else "wrong label",
                "predicted": predicted_label,
                "confidence": round(confidence, 2),
                "label": label
            })
        else:
            print(f"✅ {filepath} | ok ({confidence:.1f}%)")

# เขียน log
with open(LOG_PATH, "w", encoding="utf-8") as f:
    json.dump(log_data, f, indent=2, ensure_ascii=False)

print(f"\n🎯 เสร็จสิ้น — บันทึก log ที่ {LOG_PATH}")
