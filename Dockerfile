FROM python:3.11-slim

# Install system deps for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright + Chromium
RUN pip install playwright playwright-stealth && \
    playwright install --with-deps chromium

COPY . .

EXPOSE ${PORT:-5000}

CMD ["python", "app.py"]
