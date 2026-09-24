FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt
COPY requirements-model.txt .
RUN pip install --no-cache-dir -r requirements-model.txt
COPY web_server.py web_processor.py model_setup.py entrypoint.py ./
COPY web ./web
RUN mkdir -p /app/model /app/web_data

EXPOSE 8000
CMD ["python", "entrypoint.py"]
