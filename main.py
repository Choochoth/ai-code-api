#main.py
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Path, Form
from pathlib import Path as FilePath
from fastapi.responses import JSONResponse
from pydantic import BaseModel
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

DATA_FILE = FilePath("data/poll_targets.json")

class PollTargetIn(BaseModel):
    channelId: str
    messageId: int
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
    # load_templates(site)  # reload only that site

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

@app.get("/api/poll-targets")
def get_poll_targets():
    if not DATA_FILE.exists():
        raise HTTPException(status_code=404, detail="poll_targets.json not found")

    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            raise HTTPException(
                status_code=500,
                detail="poll_targets.json must be an array"
            )

        return data

    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Invalid JSON format: {e}"
        )

@app.post("/api/poll-update")
def poll_update(payload: PollTargetIn):
    # 🔒 ensure folder exists
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    # 🔄 load existing data
    if DATA_FILE.exists():
        try:
            with DATA_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("poll_targets.json must be an array")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Invalid poll_targets.json: {e}")
    else:
        data = []

    # 🔁 update or insert
    updated = False
    for item in data:
        if item.get("channelId") == payload.channelId:
            item["messageId"] = payload.messageId
            updated = True
            break

    if not updated:
        data.append(
            {
                "channelId": payload.channelId,
                "messageId": payload.messageId,
            }
        )

    # 💾 write back
    try:
        with DATA_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cannot write poll_targets.json: {e}")

    return {
        "status": "ok",
        "updated": updated,
        "channelId": payload.channelId,
        "messageId": payload.messageId,
        "total": len(data),
    }

# ---------------- Health ----------------
@app.get("/")
def read_root():
    return {"status": "ok"}

@app.get("/health")
def health_get():
    uptime = round(time.time() - start_time, 2)
    return {"status": "ok", "uptime_seconds": uptime}




# ---------------- CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- Packages ----------------
@app.get("/api/packages")
def get_packages(limit: int = 100, offset: int = 0):
    file_path = os.path.join("data", "package.json")
    if not os.path.exists(file_path):
        return JSONResponse({"error": "package.json not found"}, status_code=404)
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    package_data = data.get("package", {}).get("package_data", [])
    sliced = package_data[offset: offset+limit]
    return {
        "package": {"package_data": sliced},
        "meta": {"total": len(package_data), "limit": limit, "offset": offset}
    }

# ---------------- Submit Order ----------------
@app.post("/api/submit-order")
async def api_submit_order(
    package_id: str = Form(...),
    package: str = Form(...),
    price: float = Form(...),
    site: str = Form(...),
    user: str = Form(...),
    slip: UploadFile = File(...),
    notifyTelegram: bool = Form(False),
    telegramId: str = Form(None)
):
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