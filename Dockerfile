# ============================
# Stage 1: Build dependencies
# ============================
FROM python:3.11-slim AS builder
WORKDIR /app

# ติดตั้ง dependencies สำหรับ build
RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

# คัดลอก requirements และติดตั้ง Python packages ลง prefix /install
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================
# Stage 2: Runtime
# ============================
FROM python:3.11-slim
WORKDIR /app

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV ENV=production

# ติดตั้ง runtime system dependencies
RUN apt-get update && apt-get install -y ffmpeg libsm6 libxext6 curl && rm -rf /var/lib/apt/lists/*

# คัดลอก Python packages จาก builder
COPY --from=builder /install /usr/local

# คัดลอก source code ทั้งหมด
COPY . .

# คัดลอก captcha_templates เข้า container
COPY captcha_templates /app/

# เปิด port 8080
EXPOSE 8080

# Healthcheck Railway
HEALTHCHECK CMD curl --fail http://localhost:${PORT:-8080}/ || exit 1

# ใช้ shell command ให้ expand PORT
CMD sh -c "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"

