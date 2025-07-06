FROM python:3.10-slim

# Set working directory
WORKDIR /usr/app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libffi-dev \
    libssl-dev \
    pkg-config \
    libxml2-dev \
    libxmlsec1-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies (single installation to avoid conflicts)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/usr/app

# Create data directories
RUN mkdir -p /usr/app/data/raw /usr/app/data/silver /usr/app/data/gold

# Default command
CMD ["bash"]
