FROM node:22-alpine AS web

WORKDIR /web
COPY web-next/package.json web-next/package-lock.json ./
RUN npm ci
COPY web-next/ ./
RUN npm run build


FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

COPY --from=web /web/dist ./web-next/dist

ENV LIRA_DATA_DIR=/data \
    LIRA_LLM=auto

VOLUME ["/data"]
EXPOSE 8010

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
