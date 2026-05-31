FROM python:3.12-slim

WORKDIR /app

# System deps for OpenCV (Debian Bookworm compatible)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    libglx0 \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Model cache dir
RUN mkdir -p /tmp/models

# Default env
ENV HOST=0.0.0.0
ENV PORT=8080
ENV DEV_MODE=false

EXPOSE 8080

CMD ["python", "-u", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--timeout-keep-alive", "120"]
