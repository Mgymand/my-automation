# 営業クラウド (Cloud Run用)
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run は $PORT で待ち受ける必要がある
ENV PYTHONUNBUFFERED=1
CMD exec gunicorn -w 2 -t 120 -b 0.0.0.0:${PORT:-8080} app:app
