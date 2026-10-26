FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# SQLite lives on a mounted volume.
RUN mkdir -p /data
ENV DB_PATH=/data/scoreboard.db

EXPOSE 8200

# Single worker: keeps the asyncio registration lock authoritative and SQLite
# happy. Plenty for a lab scoreboard.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200", "--workers", "1"]
