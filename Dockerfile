# Base Image: Python 3.11 Slim (Debian Bookworm - Stable)
FROM python:3.11-slim-bookworm

# Environment Variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HEADLESS=true

# Install System Dependencies (Chromium)
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    libnss3 \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Work Directory
WORKDIR /app

# Install Python Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy App Code
COPY . .

# Expose Port (Render uses 10000 by default but passes PORT env var)
EXPOSE 10000

# Run with Gunicorn using Xvfb (Virtual Screen)
# Resolution 1920x1080x24 to mimic real desktop
CMD xvfb-run --auto-servernum --server-args="-screen 0 1920x1080x24" gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120
