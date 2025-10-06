import os
import cv2
import numpy as np
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
ENV = os.getenv("ENV", "development")
USE_GCS = ENV == "production"

template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "captcha_templates")
templates = {}

if USE_GCS:
    from google.cloud import storage
    GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
    gcs_client = storage.Client()
    gcs_bucket = gcs_client.bucket(GCS_BUCKET_NAME)

def preprocess_image(img, size=(30, 50)):
    resized = cv2.resize(img, size)
    blurred = cv2.GaussianBlur(resized, (3, 3), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary

def load_templates():
    templates.clear()
    if USE_GCS:
        print("🔄 Loading templates from GCS...")
        blobs = gcs_bucket.list_blobs()
        for blob in blobs:
            if blob.name.endswith(".png"):
                label = blob.name.split("_")[0]
                img_bytes = blob.download_as_bytes()
                img_array = np.frombuffer(img_bytes, np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    img = preprocess_image(img)
                    templates.setdefault(label, []).append(img)
    else:
        print("🔄 Loading templates from local folder...")
        print(f"📂 Template directory: {template_dir}")

        if not os.path.exists(template_dir):
            print("⚠️ Template directory not found, creating...")
            os.makedirs(template_dir)

        files = [f for f in os.listdir(template_dir) if f.endswith(".png")]
        print(f"📦 Found {len(files)} PNG files in template_dir")

        for filename in files:
            label = filename.split("_")[0]
            path = os.path.join(template_dir, filename)
            img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                img = preprocess_image(img)
                templates.setdefault(label, []).append(img)
            else:
                print(f"❌ Failed to load image: {path}")

    print(f"✅ Loaded {sum(len(v) for v in templates.values())} templates for {len(templates)} labels.")

def crop_captcha(img, num_chars=4):
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

def match_template(img_char):
    img_char = preprocess_image(img_char)
    best_label = None
    best_score = float('inf')
    label_scores = {}

    for label, template_list in templates.items():
        min_scores = []
        for template_img in template_list:
            res = cv2.matchTemplate(img_char, template_img, cv2.TM_SQDIFF_NORMED)
            min_val, _, _, _ = cv2.minMaxLoc(res)
            min_scores.append(min_val)

        if min_scores:
            best_score_for_label = min(min_scores)
            label_scores[label] = best_score_for_label
            if best_score_for_label < best_score:
                best_score = best_score_for_label
                best_label = label

    # sorted_scores = sorted(label_scores.items(), key=lambda x: x[1])
    # print("Top 1 match:")
    # for label, score in sorted_scores[:1]:
        # confidence = max(0.0, min(100.0, (1.0 - score) * 100.0))
        # print(f"  {label}: {confidence:.0f}%")

    best_confidence = max(0.0, min(100.0, (1.0 - best_score) * 100.0))
    return best_label if best_label is not None else "?", best_confidence

def save_templates(label, char_images):
    saved_files = []
    for i, char_img in enumerate(char_images):
        char_label = label[i]
        filename = f"{char_label}_{len(templates.get(char_label, []))}.png"
        processed_img = preprocess_image(char_img)

        if USE_GCS:
            _, img_encoded = cv2.imencode('.png', processed_img)
            blob = gcs_bucket.blob(filename)
            blob.upload_from_string(img_encoded.tobytes(), content_type="image/png")
        else:
            if not os.path.exists(template_dir):
                os.makedirs(template_dir)
            filepath = os.path.join(template_dir, filename)
            cv2.imwrite(filepath, processed_img)

        saved_files.append(filename)
    return saved_files

# def save_templates(label, char_images):
#     saved_files = []
#     for i, char_img in enumerate(char_images):
#         char_label = label[i]
#         processed_img = preprocess_image(char_img)

#         if not os.path.exists(template_dir):
#             os.makedirs(template_dir)

#         # นับจากไฟล์ในโฟลเดอร์
#         existing_files = [f for f in os.listdir(template_dir) if f.startswith(f"{char_label}_")]
#         index = len(existing_files)
#         filename = f"{char_label}_{index}.png"

#         filepath = os.path.join(template_dir, filename)
#         cv2.imwrite(filepath, processed_img)

#         saved_files.append(filename)
#     return saved_files

#     #     if USE_GCS:
#     #         # นับจาก GCS bucket
#     #         blobs = list(gcs_bucket.list_blobs(prefix=f"{char_label}_"))
#     #         index = len(blobs)
#     #         filename = f"{char_label}_{index}.png"

#     #         _, img_encoded = cv2.imencode('.png', processed_img)
#     #         blob = gcs_bucket.blob(filename)
#     #         blob.upload_from_string(img_encoded.tobytes(), content_type="image/png")
#     #     else:
#     #         if not os.path.exists(template_dir):
#     #             os.makedirs(template_dir)

#     #         # นับจากไฟล์ในโฟลเดอร์
#     #         existing_files = [f for f in os.listdir(template_dir) if f.startswith(f"{char_label}_")]
#     #         index = len(existing_files)
#     #         filename = f"{char_label}_{index}.png"

#     #         filepath = os.path.join(template_dir, filename)
#     #         cv2.imwrite(filepath, processed_img)

#     #     saved_files.append(filename)
#     # return saved_files
