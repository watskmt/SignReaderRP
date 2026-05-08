FROM python:3.10-slim

WORKDIR /app

# PaddleOCR に必要なシステムライブラリ
RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libgl1 \
    libgles2 \
    curl \
    >/dev/null 2>&1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# PaddleOCR モデルを事前ダウンロード
RUN mkdir -p /root/.paddleocr/whl/det/ml /root/.paddleocr/whl/rec/japan /root/.paddleocr/whl/cls && \
    # 検出モデル
    curl -fL "https://paddleocr.bj.bcebos.com/PP-OCRv3/multilingual/Multilingual_PP-OCRv3_det_infer.tar" \
         -o /tmp/det.tar && tar -xf /tmp/det.tar -C /root/.paddleocr/whl/det/ml && rm /tmp/det.tar && \
    # 認識モデル（日本語）
    curl -fL "https://paddleocr.bj.bcebos.com/PP-OCRv4/multilingual/japan_PP-OCRv4_rec_infer.tar" \
         -o /tmp/rec.tar && tar -xf /tmp/rec.tar -C /root/.paddleocr/whl/rec/japan && rm /tmp/rec.tar && \
    # 方向分類モデル
    curl -fL "https://paddleocr.bj.bcebos.com/dygraph_v2.0/ch/ch_ppocr_mobile_v2.0_cls_infer.tar" \
         -o /tmp/cls.tar && tar -xf /tmp/cls.tar -C /root/.paddleocr/whl/cls && rm /tmp/cls.tar

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main_optimized:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
