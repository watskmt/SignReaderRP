"""
ImageStorageService — OCR画像をサーバーのディスクに保存する。
上限(デフォルト5GB)を超えたら古いものから削除する。
"""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

MAX_BYTES = int(settings.IMAGE_STORAGE_MAX_GB * 1024 ** 3)
STORAGE_PATH = Path(settings.IMAGE_STORAGE_PATH)


class ImageStorageService:
    def __init__(self) -> None:
        STORAGE_PATH.mkdir(parents=True, exist_ok=True)

    def save_frame(self, frame_b64: str, filename: str) -> Optional[str]:
        """
        base64画像をJPEGとしてディスクに保存する。
        上限超過時は古いファイルから削除する。
        失敗しても None を返すのみ（OCR処理は継続）。
        """
        try:
            image_bytes = base64.b64decode(frame_b64)
            self._ensure_quota(len(image_bytes))
            file_path = STORAGE_PATH / filename
            file_path.write_bytes(image_bytes)
            url = f"/images/{filename}"
            logger.info("Image saved: %s", file_path)
            return url
        except Exception as exc:
            logger.warning("Image save failed (OCR続行): %s", exc)
            return None

    def _ensure_quota(self, incoming_bytes: int) -> None:
        """容量上限を超える場合は古いファイルから削除する。"""
        files = sorted(
            STORAGE_PATH.glob("*.jpg"),
            key=lambda p: p.stat().st_mtime,
        )
        total = sum(p.stat().st_size for p in files)

        for f in files:
            if total + incoming_bytes <= MAX_BYTES:
                break
            size = f.stat().st_size
            f.unlink()
            total -= size
            logger.info("Quota: deleted old image %s", f.name)

    def get_usage_gb(self) -> float:
        try:
            total = sum(p.stat().st_size for p in STORAGE_PATH.glob("*.jpg"))
            return round(total / 1024 ** 3, 2)
        except Exception:
            return 0.0
