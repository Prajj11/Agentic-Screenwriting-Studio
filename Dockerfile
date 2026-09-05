# ── Stage 1: Build Frontend ─────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install

COPY frontend/ ./
ENV STATIC_EXPORT=true
ENV NODE_ENV=production
RUN npm run build

# ── Stage 2: Backend & Runtime ──────────────────────
FROM python:3.11-slim

# Install system dependencies including ffmpeg for video/audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r ./backend/requirements.txt

# Copy backend code
COPY backend/ ./backend/

# Copy compiled frontend into backend/static for serving
COPY --from=frontend-builder /app/frontend/out ./backend/static

# Environment settings
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

WORKDIR /app/backend

EXPOSE 8000

# Antideploy injects PORT at runtime
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
