FROM python:3.13-slim

# Install system dependencies for Chromium/Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libcups2 \
    libxkbcommon0 \
    libgtk-3-0 \
    libxshmfence1 \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium browser
RUN playwright install chromium

# Copy app files
COPY api.py whatsapp_sender.py form.html cbd-logo.jpg ./

# Persistent volumes for session data and logs
VOLUME ["/app/whatsapp_session", "/app/logs"]

EXPOSE 8000

CMD ["python", "api.py"]
