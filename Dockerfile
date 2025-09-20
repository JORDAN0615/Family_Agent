FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/*

# 安裝 uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && cp /root/.local/bin/uv /usr/local/bin/uv \
    && chmod +x /usr/local/bin/uv

# 複製源代碼
COPY app app/
COPY pyproject.toml README.md ./
COPY .env.example /app/.env

# 在這裡建立 .venv
RUN uv venv .venv \
  && . .venv/bin/activate \
  && uv pip install --no-cache -e .

# 設定環境變數
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV ENVIRONMENT=production

# 使用環境變數控制啟動方式
CMD . .venv/bin/activate && \
    if [ "$ENVIRONMENT" = "development" ]; then \
        exec uvicorn app.main:app --reload --host 0.0.0.0 --port ${PORT}; \
    else \
        exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}; \
    fi