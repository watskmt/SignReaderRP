FROM python:3.10-slim

WORKDIR /app

# PaddleOCR に必要なシステムライブラリ
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libgl1-mesa-glx \
    libgles2 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# PaddleOCR モデルを事前ダウンロード（ビルド時に取得してコンテナ起動を高速化）
RUN python -c "from paddleocr import PaddleOCR; PaddleOCR(use_gpu=False, lang='japan', show_log=False)" || true

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main_optimized:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
