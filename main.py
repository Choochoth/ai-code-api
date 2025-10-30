from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Path, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict
import time
import cv2
import numpy as np
import os
import json

from utils.image_processing import (
    match_template,
    save_templates,
    crop_captcha,
    load_templates,
    get_template_summary,
    SUPPORTED_SITES,
)
from utils.order_package import submit_payment  # import ฟังก์ชัน

# ---------------- FastAPI App ----------------
app = FastAPI()
start_time = time.time()

# ---------------- Startup ----------------
@app.on_event("startup")
async def startup():
    print("🔄 Loading templates at startup...")
    load_templates()
    print("✅ Templates loaded into memory")

# ---------------- Helpers ----------------
def validate_site(site: str):
    return site.lower() in SUPPORTED_SITES

# ---------------- Reload Templates ----------------
@app.post("/api/reload-templates")
def reload_all_templates():
    load_templates()  # reload all sites
    return {"message": "All templates reloaded.", "summary": get_template_summary()}

# ---------------- Add Template ----------------
@app.post("/api/{site}/add-template")
async def add_template(
    site: str = Path(..., description="site name (thai_789bet, thai_jun88k36, thai_f168)"),
    label: str = Query(..., min_length=4, max_length=4),
    file: UploadFile = File(...),
):
    site = site.lower()
    if not validate_site(site):
        return JSONResponse(status_code=400, content={"error": "unsupported site", "supported": SUPPORTED_SITES})

    # Validate label rules
    if site in ("thai_jun88k36", "thai_789bet"):
        if not label.isalnum() or not label.upper() == label:
            return JSONResponse(
                status_code=400,
                content={"error": "label must be uppercase A-Z and 0-9 for this site"}
            )
    elif site == "thai_f168":
        if not label.isalnum():
            return JSONResponse(
                status_code=400,
                content={"error": "label must be A-Z, a-z or 0-9 for f168"}
            )

    # Decode image
    image_bytes = await file.read()
    file_bytes = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return JSONResponse(status_code=400, content={"error": "Invalid image file."})

    # Split and save
    char_images = crop_captcha(img, num_chars=4)
    if len(label) != len(char_images):
        return JSONResponse(status_code=400, content={"error": "Label length does not match cropped chars."})

    saved_files = save_templates(site, label, char_images)
    load_templates(site)  # reload only that site

    return {"message": "Templates saved.", "saved": saved_files, "summary": get_template_summary()}

# ---------------- OCR Endpoint ----------------
@app.post("/api/{site}/ocr")
async def ocr(
    site: str = Path(..., description="site name (thai_789bet, thai_jun88k36, thai_f168)"),
    file: UploadFile = File(...),
):
    site = site.lower()
    if not validate_site(site):
        return JSONResponse(status_code=400, content={"error": "unsupported site", "supported": SUPPORTED_SITES})

    image_bytes = await file.read()
    file_bytes = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return JSONResponse(status_code=400, content={"error": "Invalid image file."})

    chars = crop_captcha(img, num_chars=4)
    result_text = ""
    confidences = []

    for char_img in chars:
        label, conf = match_template(site, char_img)
        result_text += (label if label is not None else "?")
        confidences.append(conf)

    avg_confidence = round(sum(confidences) / len(confidences), 0) if confidences else 0

    return {"text": result_text, "confidence": int(avg_confidence), "site": site}

# ---------------- Debug Templates ----------------
@app.get("/debug/templates")
def debug_templates():
    return get_template_summary()

@app.get("/debug/templates/{site}")
def debug_templates_site(site: str = Path(..., description="site name (thai_789bet, thai_jun88k36, thai_f168)")):
    site = site.lower()
    if not validate_site(site):
        return JSONResponse(status_code=400, content={"error": "unsupported site", "supported": SUPPORTED_SITES})
    from utils.image_processing import templates
    mapping = templates.get(site, {})
    return {"site": site, "labels": list(mapping.keys()), "total_images": sum(len(v) for v in mapping.values())}

# ---------------- Health ----------------
@app.get("/")
def read_root():
    return {"status": "ok"}

@app.get("/health")
def health_get():
    uptime = round(time.time() - start_time, 2)
    return {"status": "ok", "uptime_seconds": uptime}



app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/packages")
async def get_packages(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    file_path = os.path.join("data", "package.json")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="package.json not found")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # อ่านค่าหลัก
        free_package = data.get("free_package", {})
        day_package = data.get("day_package", {})
        package = data.get("package", {})

        # รองรับ limit / offset เฉพาะ package_data
        package_data = package.get("package_data", [])
        sliced = package_data[offset: offset + limit]

        return {
            "free_package": free_package,
            "day_package": day_package,
            "package": {
                "package_title": package.get("package_title"),
                "package_desc": package.get("package_desc"),
                "package_data": sliced
            },
            "meta": {
                "total": len(package_data),
                "limit": limit,
                "offset": offset
            }
        }

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid JSON format in package.json")

@app.post("/api/submit-order")
async def submit_order(
    package_id: str = Form(...),
    package: str = Form(...),
    price: float = Form(...),
    site: str = Form(...),
    user: str = Form(...),
    slip: UploadFile = File(...),
    notifyTelegram: bool = Form(False),
    telegramId: str = Form(None)
):
    # เรียกฟังก์ชัน submit_payment จาก utils/order_package
    return await submit_payment(
        package_id=package_id,
        package=package,
        price=price,
        site=site,
        user=user,
        slip=slip,
        notifyTelegram=notifyTelegram,
        telegramId=telegramId
    )