import os
import httpx
import json
import shutil
import uuid
from fastapi import UploadFile, Form
from fastapi.responses import JSONResponse

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ADMIN = os.getenv("CHANNEL_ADMIN")
CHANNEL_CODE = os.getenv("CHANNEL_CODE")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def mask_username(username: str) -> str:
    """ซ่อน username บางส่วน"""
    if len(username) <= 5:
        return username
    return username[:3] + "*" * (len(username) - 5) + username[-2:]


async def send_photo(chat_id: str, caption: str, file_path: str, buttons: list = None):
    url = f"{TELEGRAM_API_URL}/sendPhoto"
    with open(file_path, "rb") as f:
        content = f.read()

    files = {"photo": (os.path.basename(file_path), content, "image/jpeg")}
    data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}

    if buttons:
        data["reply_markup"] = json.dumps({
            "inline_keyboard": [[
                {"text": b["text"], "callback_data": b["callback_data"][:64]} for b in buttons
            ]]
        })

    async with httpx.AsyncClient() as client:
        response = await client.post(url, data=data, files=files)
        response.raise_for_status()


async def send_message(chat_id: str, message: str):
    url = f"{TELEGRAM_API_URL}/sendMessage"
    data = {"chat_id": chat_id, "text": message}
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=data)
        response.raise_for_status()


async def submit_payment(
    package_id: str = Form(...),
    package: str = Form(...),
    price: float = Form(...),
    site: str = Form(...),
    user: str = Form(...),  # JSON string [{"name":"xxx","count":1},...]
    slip: UploadFile = Form(...),
    notifyTelegram: bool = Form(False),
    telegramId: str = Form(None)
):
    try:
        users = json.loads(user)
        if not isinstance(users, list) or not all("name" in u and "count" in u for u in users):
            return JSONResponse({"status": "error", "message": "user format invalid"}, status_code=400)
    except Exception:
        return JSONResponse({"status": "error", "message": "user JSON invalid"}, status_code=400)

    # total_codes = sum(u["count"] for u in users)
    # ✅ TODO: เช็คกับ package limit ถ้ามี data จาก package.json

    # บันทึกไฟล์สลิป
    upload_folder = "./uploads/slip"
    os.makedirs(upload_folder, exist_ok=True)
    file_ext = os.path.splitext(slip.filename)[1].lower()
    if file_ext not in [".jpg", ".jpeg", ".png", ".gif"]:
        return JSONResponse({"status": "error", "message": "file type not supported"}, status_code=400)

    saved_filename = f"{uuid.uuid4()}{file_ext}"
    saved_filepath = os.path.join(upload_folder, saved_filename)
    with open(saved_filepath, "wb") as buffer:
        shutil.copyfileobj(slip.file, buffer)

    # ข้อความ Telegram
    user_str = ", ".join(f"{u['name']}({u['count']})" for u in users)
    caption_main = (
        f"\U0001F9FE มีผู้ส่งสลิปชำระเงิน\n"
        f"📦 รหัส: {package_id}\n"
        f"\U0001F4E6 แพ็กเกจ: {package}\n"
        f"\U0001F4B0 ราคา: {price} บาท\n"
        f"🌐 ไซต์: {site}\n"
        f"\U0001F464 ยูสเซอร์: {user_str}"
    )

    caption_status = (
        f"⏳ สถานะรอตรวจสอบ\n"
        f"📦 รหัส: {package_id}\n"
        f"📦 แพ็กเกจ: {package}\n"
        f"💰 ราคา: {price} บาท\n"
        f"🌐 ไซต์: {site}\n"
        f"👤 ยูสเซอร์: {mask_username(user_str)}"
    )

    # ส่ง Admin / Channel
    try:
        if TELEGRAM_BOT_TOKEN and CHANNEL_ADMIN:
            admin_ids = [chat.strip() for chat in CHANNEL_ADMIN.split(",") if chat.strip()]
            for chat_id in admin_ids:
                try:
                    await send_photo(chat_id, caption_main, saved_filepath)
                except Exception as e:
                    print(f"⚠️ ส่ง Admin ไม่สำเร็จ {chat_id}: {e}")

        if TELEGRAM_BOT_TOKEN and CHANNEL_CODE:
            await send_message(CHANNEL_CODE, caption_status)

    except Exception as e:
        print("⚠️ ส่ง Telegram channel failed:", e)

    # ส่งไป user ถ้าขอแจ้งเตือน
    if notifyTelegram and telegramId:
        try:
            await send_photo(telegramId, caption_main, saved_filepath)
        except Exception as e:
            print("⚠️ ส่ง Telegram user failed:", e)

    return JSONResponse({"status": "success", "message": "ข้อมูลถูกส่งเรียบร้อยแล้ว"})
