# Use the official Ubuntu 22.04 base image
FROM ubuntu:22.04

# Install Python 3.9, pip, and other required packages
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3.9 \
    python3-pip \
    ffmpeg \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install Flask
RUN pip3 install --upgrade pip && pip3 install Flask Flask-Babel

# Set the working directory inside the container
WORKDIR /app

# Copy the application files into the container
COPY app.py /app/
COPY templates /app/templates
COPY translations /app/translations

# Compile translations using pybabel
RUN pybabel compile -d translations

# Expose port 5000 (Flask default)
EXPOSE 5000

ENV SERMON_API_TOKEN="58cb3ced-c710-4bd2-9d6b-81aef1757ee1"

# Set the default command to run your Flask app
CMD ["python3", "app.py"]
