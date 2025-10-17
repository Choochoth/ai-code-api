# ============================
# 🏗️ Stage 1: Build dependencies
# ============================
FROM python:3.11-slim AS builder

# Set work directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install dependencies to a temp directory
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt


# ============================
# 🚀 Stage 2: Runtime environment
# ============================
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV ENV=production
ENV PORT=8000

WORKDIR /app

# Install runtime system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg libsm6 libxext6 curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy project files
COPY . .

# Healthcheck (Railway ใช้ตรวจว่าสร้างสำเร็จหรือไม่)
HEALTHCHECK CMD curl --fail http://localhost:8000/health || exit 1

# Expose the app port
EXPOSE 8000

# Start FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
