from fastapi import FastAPI, UploadFile, File, Query
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import time
import cv2
import numpy as np
from utils.image_processing import preprocess_image, match_template, save_templates, crop_captcha, load_templates
# from routes.player_pool import router as player_pool_router
# from routes.apply_code import router as apply_code_router
# from routes.payment import router as payment_router
# from routes.master_data import router as master_data_router
# from routes.generate_coupon import router as generate_coupon_router  # ✅
# from db.database import database

import asyncio
import socket

app = FastAPI()
start_time = time.time()

# สมมุติว่า database เป็นออบเจกต์เชื่อมต่อ DB ที่คุณมีอยู่แล้ว
# เช่น: from database import database

# async def is_internet_connected(host="8.8.8.8", port=53, timeout=3):
#     try:
#         socket.setdefaulttimeout(timeout)
#         socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
#         return True
#     except socket.error:
#         return False

@app.on_event("startup")
async def startup():
    print("🔄 Loading templates at startup...")
    load_templates()
    print("✅ Templates loaded into memory")

#     if await is_internet_connected():
#         try:
#             await database.connect()
#             print("✅ Database connected")
#         except Exception as e:
#             print(f"❌ Database connection failed: {e}")
#     else:
#         print("❌ No internet connection. Skipping database connection.")

# @app.on_event("shutdown")
# async def shutdown():
#     try:
#         await database.disconnect()
#         print("🔻 Database disconnected")
#     except Exception as e:
#         print(f"⚠️ Database disconnection error: {e}")

@app.post("/api/reload-templates")
def reload_templates():
    load_templates()
    return {"message": "Templates reloaded"}

@app.post("/api/add-template")
async def add_template(
    label: str = Query(..., min_length=4, max_length=4, regex="^[a-zA-Z0-9]{4}$"),
    file: UploadFile = File(...)
):
    image_bytes = await file.read()
    file_bytes = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return JSONResponse(status_code=400, content={"error": "Invalid image file."})

    char_images = crop_captcha(img, num_chars=4)

    if len(label) != len(char_images):
        return JSONResponse(status_code=400, content={"error": "Label length does not match cropped characters count."})

    saved_files = save_templates(label, char_images)
    load_templates()

    return {"message": "Templates saved.", "files": saved_files}

@app.post("/api/ocr")
async def ocr(file: UploadFile = File(...)):
    image_bytes = await file.read()
    file_bytes = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return JSONResponse(status_code=400, content={"error": "Invalid image file."})

    chars = crop_captcha(img, num_chars=4)

    result_text = ""
    confidences = []

    for i, char_img in enumerate(chars):
        # print(f"\n--- Matching character #{i+1} ---")
        label, conf = match_template(char_img)
        result_text += label
        confidences.append(conf)

    avg_confidence = round(sum(confidences) / len(confidences), 0)

    return {
        "text": result_text,
        "confidence": int(avg_confidence)
    }


@app.get("/")
def read_root():
    return {"status": "ok"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/debug/templates")
def debug_templates():
    from utils.image_processing import templates
    return {
        "labels": list(templates.keys()),
        "total_images": sum(len(v) for v in templates.values())
    }





# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=[
#         "http://localhost:5100",
#         "https://typescript-telegram-auto-forword-production.up.railway.app",
#         "https://typescript-telegram-auto-forword.onrender.com"
#     ],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
# app.mount("/static/generated_coupons", StaticFiles(directory="generated_coupons"), name="generated_coupons")

# app.include_router(payment_router)
# app.include_router(generate_coupon_router, prefix="/api")
# app.include_router(player_pool_router, prefix="/api")
# app.include_router(apply_code_router, prefix="/api")
# app.include_router(master_data_router, prefix="/api")

