# Dockerfile
FROM python:3.9-slim-buster 
# 這一行是關鍵 (將註解獨立成一行)

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=7860 
EXPOSE 7860

CMD ["gunicorn", "--bind", "0.0.0.0:7860", "app:app"]