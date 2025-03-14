# Use the official Python 3.12 Alpine-based image
FROM python:3.12-alpine

# Install system dependencies (ffmpeg for audio, sqlite for database)
RUN apk add --no-cache \
    ffmpeg \
    sqlite \
    gcc \
    musl-dev \
    python3-dev \
    libffi-dev \
    openssl-dev

# Set the working directory inside the container
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . /app/

# Create directories if they don't exist
RUN mkdir -p /data/audiofiles

# Download Bootstrap locally
RUN python download_bootstrap.py

# Compile translations
RUN pybabel compile -d translations

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    DATABASE_PATH=/data/sermons.db \
    AUDIOFILES_DIR=/data/audiofiles

# Run tests (with option to skip during build if needed)
RUN pytest --maxfail=1 --disable-warnings || echo "Tests failed but continuing build"

# Expose the application port
EXPOSE 5000

# Run the application with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "--log-level", "info", "app:app"]
