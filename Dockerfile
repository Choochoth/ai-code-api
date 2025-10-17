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
ENV PORT=8000  
# Railway จะ override ให้เอง

RUN apt-get update && apt-get install -y ffmpeg libsm6 libxext6 curl && rm -rf /var/lib/apt/lists/*
COPY --from=builder /install /usr/local
COPY . .

# ✅ ใช้ dynamic port สำหรับ healthcheck
HEALTHCHECK CMD curl --fail http://localhost:${PORT}/health || exit 1

EXPOSE 8000

# ✅ ใช้ dynamic port runtime (สำคัญ!)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
