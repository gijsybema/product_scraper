# Start from a small official Python base image
FROM python:3.11-slim

# Prevents Python from writing .pyc files and buffers (better logs)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create app directory
WORKDIR /app

# (Common) psycopg2 can require system libs. Install minimal build deps.
# If you use psycopg2-binary in requirements.txt, this is often unnecessary,
# but leaving it in avoids painful build failures.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

# Install dependencies first (better Docker layer caching)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy project files
COPY src /app/src
COPY scripts /app/scripts

# Default command (daily). In ECS you can override this per schedule.
CMD ["python", "scripts/test_db_connection.py"]