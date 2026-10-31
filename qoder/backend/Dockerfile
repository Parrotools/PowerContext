FROM python:3.11-slim

WORKDIR /app

# Install build dependencies for sqlite-vec (native extension)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create data directory for SQLite database
RUN mkdir -p /app/data

EXPOSE 8000

# Seed sample data on first startup, then launch the server
CMD python seed_sample.py && uvicorn app.main:app --host 0.0.0.0 --port 8000
