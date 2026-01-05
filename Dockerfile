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

# Run with Gunicorn
CMD gunicorn app:app --bind 0.0.0.0:$PORT
