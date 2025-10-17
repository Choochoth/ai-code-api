# ============================
# Stage 1: Build dependencies
# ============================
FROM python:3.11-slim AS builder
WORKDIR /app

RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================
# Stage 2: Runtime
# ============================
FROM python:3.11-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV ENV=production

RUN apt-get update && apt-get install -y ffmpeg libsm6 libxext6 curl && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY . .

# เปิด port 8080 (Railway จะ override environment variable PORT)
EXPOSE 8080

# Healthcheck dynamic port
HEALTHCHECK CMD sh -c 'curl --fail http://localhost:${PORT:-8080}/health || exit 1'

# ใช้ python main.py ให้อ่าน PORT จาก environment
CMD ["python", "main.py"]
