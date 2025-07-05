FROM python:3.10-slim

# Set working directory
WORKDIR /usr/app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install additional dependencies for dbt and Spark
RUN pip install --no-cache-dir \
    dbt-core==1.5.1 \
    dbt-spark==1.5.1 \
    dbt-postgres==1.5.1 \
    streamlit==1.25.0 \
    altair==5.0.1 \
    pyarrow==12.0.1 \
    boto3==1.28.3 \
    s3fs==2023.6.0

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/usr/app

# Create data directories
RUN mkdir -p /usr/app/data/raw /usr/app/data/silver /usr/app/data/gold

# Default command
CMD ["bash"]
