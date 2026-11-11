FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY affiliate_bot ./affiliate_bot
ENV DATA_DIR=/var/data PYTHONUNBUFFERED=1
VOLUME ["/var/data"]
# 既定: 常駐スケジューラ（毎時 publish/metrics/checks、06:00 JST に学習・レポート・計画、月曜 07:00 に週次）
CMD ["python", "-m", "affiliate_bot", "loop"]
