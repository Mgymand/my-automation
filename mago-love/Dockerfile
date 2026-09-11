# 孫LOVE (Cloud Run / 任意のコンテナ環境用)
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1 TRUST_PROXY=1
CMD exec gunicorn -w 2 -t 120 -b 0.0.0.0:${PORT:-8080} app:app
