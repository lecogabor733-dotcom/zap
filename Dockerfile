FROM python:3.12-slim

# ffmpeg = MP3 mode + merging 1080p video and audio into MP4
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD gunicorn server:app --bind 0.0.0.0:${PORT:-10000} --timeout 300 --workers 2 --threads 4
