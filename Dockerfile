FROM python:3.10-slim

# Install dependencies Playwright
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libnspr4 \
    libnss3 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libatspi2.0-0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libxcb1 \
    libxkbcommon0 \
    libasound2 \
    wget \
    curl \
    unzip \
    fonts-liberation \
    libappindicator3-1 \
    libu2f-udev \
    && rm -rf /var/lib/apt/lists/*

# Set working dir
WORKDIR /app

# Copy file ke container
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser dependencies
RUN playwright install --with-deps chromium

# Jalankan bot
CMD ["python", "main.py"]