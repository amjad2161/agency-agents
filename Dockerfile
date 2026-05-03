# JARVIS BRAINIAC — Dockerfile
FROM python:3.11-slim

LABEL maintainer="Amjad Mobarsham"
LABEL version="28.0"
LABEL description="JARVIS BRAINIAC — Supreme AI Agent"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create data directories
RUN mkdir -p /app/data /app/logs /app/.jarvis

# Expose ports
EXPOSE 5000 8000 8777

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "from runtime.agency.jarvis_brain import get_brain; b = get_brain(); r = b.route('test'); print('OK')" || exit 1

# Default command
CMD ["python", "jarvis_bootstrap.py"]
