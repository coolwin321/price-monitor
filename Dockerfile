FROM python:3.11-bookworm

# Install system deps for Playwright Chromium
RUN apt-get update && apt-get install -y \
    wget \
    fonts-freefont-ttf \
    fonts-noto-color-emoji \
    fonts-unifont \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright + Chromium (without --with-deps since we installed them above)
RUN pip install playwright playwright-stealth && \
    playwright install chromium

COPY . .

EXPOSE ${PORT:-5000}

CMD ["python", "app.py"]
