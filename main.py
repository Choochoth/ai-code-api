# main.py
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Path, Form
from pathlib import Path as FilePath
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import List
import time
import cv2
import numpy as np
import os
import json
import random

from utils.image_processing import (
    match_template,
    save_templates,
    crop_captcha,
    load_templates,
    get_template_summary,
    SUPPORTED_SITES,
)
from utils.order_package import submit_payment


# ===============================
# 📁 Paths
# ===============================
DATA_FILE = FilePath("data/poll_targets.json")

# ===============================
# 📦 Models
# ===============================
class PollTargetIn(BaseModel):
    channelId: str
    messageId: int


# ===============================
# 🚀 App
# ===============================
app = FastAPI()
start_time = time.time()


# ===============================
# 🔄 Startup
# ===============================
@app.on_event("startup")
async def startup():
    print("🔄 Loading templates at startup...")
    load_templates()
    print("✅ Templates loaded into memory")


# ===============================
# 🔧 Helpers
# ===============================
def validate_site(site: str):
    return site.lower() in SUPPORTED_SITES


# ===============================
# 🔁 Reload Templates
# ===============================
@app.post("/api/reload-templates")
def reload_all_templates():
    load_templates()
    return {
        "message": "All templates reloaded.",
        "summary": get_template_summary()
    }


# ===============================
# ➕ Add Template
# ===============================
@app.post("/api/{site}/add-template")
async def add_template(
    site: str = Path(...),
    label: str = Query(..., min_length=4, max_length=4),
    file: UploadFile = File(...)
):
    site = site.lower()
    if not validate_site(site):
        return JSONResponse(
            status_code=400,
            content={"error": "unsupported site", "supported": SUPPORTED_SITES},
        )

    image_bytes = await file.read()
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise HTTPException(400, "Invalid image")

    chars = crop_captcha(img, num_chars=4)
    if len(chars) != len(label):
        raise HTTPException(400, "Label length mismatch")

    saved = save_templates(site, label, chars)
    # ✅ สำคัญมาก
    # load_templates(site)

    return {
        "message": "Templates saved",
        "saved": saved,
        "summary": get_template_summary(),
    }

# ===============================
# ➕ clear Template
# ===============================
@app.post("/api/{site}/clear-templates")
def clear_templates(site: str):
    site = site.lower()
    if not validate_site(site):
        raise HTTPException(400, "unsupported site")

    site_dir = os.path.join("captcha_templates", site)

    deleted = 0
    for f in os.listdir(site_dir):
        if f.endswith(".png"):
            os.remove(os.path.join(site_dir, f))
            deleted += 1

    # 🔥 sync memory
    load_templates(site)

    return {
        "message": "cleared",
        "deleted": deleted,
        "summary": get_template_summary()
    }

# ===============================
# 🔍 OCR
# ===============================
@app.post("/api/{site}/ocr")
async def ocr(
    site: str = Path(...),
    file: UploadFile = File(...)
):
    site = site.lower()
    if not validate_site(site):
        raise HTTPException(400, "unsupported site")

    img = cv2.imdecode(
        np.frombuffer(await file.read(), np.uint8),
        cv2.IMREAD_GRAYSCALE,
    )

    chars = crop_captcha(img, num_chars=4)
    text = ""
    confs = []

    for c in chars:
        label, conf = match_template(site, c)
        text += label or "?"
        confs.append(conf)

    return {
        "text": text,
        "confidence": int(sum(confs) / len(confs)) if confs else 0,
        "site": site,
    }


# ===============================
# 📡 GET poll-targets
# ===============================
@app.get("/api/poll-targets")
def get_poll_targets():
    if not DATA_FILE.exists():
        return []

    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            raise ValueError("poll_targets.json must be array")

        random.shuffle(data)  # 🔀 random ลำดับ array

        return data

    except Exception as e:
        raise HTTPException(500, f"Invalid poll_targets.json: {e}")


# ===============================
# 🧠 INTERNAL sync logic
# ===============================
def _poll_update_sync(payload: PollTargetIn):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    if DATA_FILE.exists():
        with DATA_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("poll_targets.json must be array")
    else:
        data = []

    updated = False
    for item in data:
        if item.get("channelId") == payload.channelId:
            item["messageId"] = payload.messageId
            updated = True
            break

    if not updated:
        data.append({
            "channelId": payload.channelId,
            "messageId": payload.messageId,
        })

    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    return {
        "status": "ok",
        "updated": updated,
        "channelId": payload.channelId,
        "messageId": payload.messageId,
        "total": len(data),
    }


# ===============================
# ✨ POST poll-update (ASYNC SAFE)
# ===============================
@app.post("/api/poll-update")
async def poll_update(payload: PollTargetIn):
    try:
        return await run_in_threadpool(_poll_update_sync, payload)
    except Exception as e:
        raise HTTPException(500, str(e))


# ===============================
# ❤️ Health
# ===============================
@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/health")
def health():
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - start_time, 2),
    }


# ===============================
# 🌐 CORS
# ===============================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===============================
# 📦 Packages
# ===============================
@app.get("/api/packages")
def get_packages(limit: int = 100, offset: int = 0):
    path = "data/package.json"
    if not os.path.exists(path):
        raise HTTPException(404, "package.json not found")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    packages = data.get("package", {}).get("package_data", [])
    return {
        "package": {"package_data": packages[offset: offset + limit]},
        "meta": {
            "total": len(packages),
            "limit": limit,
            "offset": offset,
        },
    }


# ===============================
# 💰 Submit Order
# ===============================
@app.post("/api/submit-order")
async def api_submit_order(
    package_id: str = Form(...),
    package: str = Form(...),
    price: float = Form(...),
    site: str = Form(...),
    user: str = Form(...),
    slip: UploadFile = File(...),
    notifyTelegram: bool = Form(False),
    telegramId: str = Form(None),
):
    return await submit_payment(
        package_id=package_id,
        package=package,
        price=price,
        site=site,
        user=user,
        slip=slip,
        notifyTelegram=notifyTelegram,
        telegramId=telegramId,
    )
