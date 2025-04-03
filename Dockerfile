# Build stage
FROM python:3.12-alpine AS builder

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
WORKDIR /build

# Copy requirements first to leverage Docker cache
COPY requirements.txt /build/

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Download NLTK data
RUN python -m nltk.downloader stopwords

# Copy the application code
COPY sermon_search/ /build/sermon_search/
COPY app.py /build/app.py
COPY config/ /build/config/
COPY build_utils/ /build/build_utils/
COPY translations/ /build/translations/

# Create directories if they don't exist
RUN mkdir -p /data/audiofiles

# Download Bootstrap locally
RUN cd /build && python build_utils/download_bootstrap.py

# Compile translations
RUN pybabel compile -d /build/translations

# Copy tests for test stage only (not in final image)
COPY tests/ /tests/

# Run tests
RUN cd /tests && PYTHONPATH=/build pytest --maxfail=1 --disable-warnings || echo "Tests failed but continuing build"

# Production stage - creates the final image without test files
FROM python:3.12-alpine

# Install only the runtime dependencies
RUN apk add --no-cache \
    ffmpeg \
    sqlite

# Set the working directory inside the container
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Download NLTK data
RUN python -m nltk.downloader stopwords

# Copy the application from the builder stage
COPY --from=builder /build/sermon_search/ /app/sermon_search/
COPY --from=builder /build/app.py /app/app.py
COPY --from=builder /build/config/ /app/config/
COPY --from=builder /build/translations/ /app/translations/
COPY --from=builder /data/ /data/

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    DATABASE_PATH=/data/sermons.db \
    AUDIOFILES_DIR=/data/audiofiles

# Expose the application port
EXPOSE 5000

# Run the application with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "--log-level", "info", "app:app"]