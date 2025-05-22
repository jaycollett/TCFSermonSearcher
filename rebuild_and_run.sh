#!/bin/bash
set -e

# Configuration
IMAGE_NAME="tcf-sermon-searcher"
CONTAINER_NAME="tcf-sermon-searcher"
PORT=5022
# Use data directory relative to the script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$SCRIPT_DIR/data"

# Ensure data directory exists
mkdir -p "$DATA_DIR/audiofiles"

echo "=== TCF Sermon Searcher Docker Management Script ==="
echo "This script will:"
echo "  1. Stop any running container"
echo "  2. Remove the container if it exists"
echo "  3. Remove the image if it exists"
echo "  4. Build a new image"
echo "  5. Start a new container with proper volume mappings"
echo ""
echo "Data will be stored in: $DATA_DIR"
echo "Application will be available at: http://localhost:$PORT"
echo ""

# Stop and remove any existing container
echo "Stopping container if running..."
docker stop $CONTAINER_NAME 2>/dev/null || true
echo "Removing container if it exists..."
docker rm $CONTAINER_NAME 2>/dev/null || true

# Remove existing image
echo "Removing image if it exists..."
docker rmi $IMAGE_NAME 2>/dev/null || true

# Build the new image
echo "Building new image..."
docker build -t $IMAGE_NAME .

# Run the container with proper volume mappings
echo "Starting container..."
docker run -d \
  --name $CONTAINER_NAME \
  -p $PORT:5000 \
  -v "$DATA_DIR:/data" \
  -e FLASK_ENV=development \
  -e FLASK_DEBUG=1 \
  -e SERMON_API_TOKEN=ABC123ABC123 \
  -e DATABASE_PATH=/data/sermons.db \
  -e AUDIOFILES_DIR=/data/audiofiles \
  --restart unless-stopped \
  $IMAGE_NAME

echo ""
echo "=== Container started successfully ==="
echo "You can view the application at: http://localhost:$PORT"
echo "Container logs: docker logs $CONTAINER_NAME"
echo "Stop container: docker stop $CONTAINER_NAME"
echo "Restart container: docker restart $CONTAINER_NAME"