"""
DriveService — Google Drive への画像アップロードと容量管理。
テキスト検出済みフレームのみ保存し、上限(デフォルト20GB)を超えたら古いものから削除する。

認証: Workload Identity Federation (ADC) を使用。
  GOOGLE_APPLICATION_CREDENTIALS に WIF 認証情報設定ファイルのパスを指定する。
  設定ファイルは秘密鍵を含まず、トークン取得方法を記述した JSON。
  google.auth.default() が自動的に読み込む。
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
MAX_BYTES = int(settings.GOOGLE_DRIVE_MAX_GB * 1024 ** 3)


class DriveService:
    def __init__(self) -> None:
        self._service = None

    def _get_service(self):
        if self._service is None:
            import google.auth
            from googleapiclient.discovery import build

            # Workload Identity Federation (ADC)
            # GOOGLE_APPLICATION_CREDENTIALS に WIF 設定ファイルを指定すると
            # google.auth.default() が自動的に外部トークンを取得・更新する
            creds, _ = google.auth.default(scopes=DRIVE_SCOPES)
            self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return self._service

    def upload_frame(self, frame_b64: str, filename: str) -> Optional[str]:
        """
        base64画像をJPEGとしてDriveフォルダにアップロードする。
        容量超過時は古いファイルを削除してから保存する。
        アップロードに失敗しても例外を上げず None を返す（OCR処理を止めないため）。
        """
        if not settings.GOOGLE_DRIVE_ENABLED or not settings.GOOGLE_DRIVE_FOLDER_ID:
            return None

        try:
            image_bytes = base64.b64decode(frame_b64)
            self._ensure_quota(len(image_bytes))
            file_id = self._upload(image_bytes, filename)
            self._make_public(file_id)
            url = f"https://drive.google.com/file/d/{file_id}/view"
            logger.info("Drive upload OK: %s", url)
            return url
        except Exception as exc:
            logger.warning("Drive upload failed (OCR続行): %s", exc)
            return None

    def _upload(self, image_bytes: bytes, filename: str) -> str:
        from googleapiclient.http import MediaIoBaseUpload

        svc = self._get_service()
        metadata = {
            "name": filename,
            "parents": [settings.GOOGLE_DRIVE_FOLDER_ID],
        }
        media = MediaIoBaseUpload(io.BytesIO(image_bytes), mimetype="image/jpeg")
        f = svc.files().create(body=metadata, media_body=media, fields="id").execute()
        return f["id"]

    def _make_public(self, file_id: str) -> None:
        svc = self._get_service()
        svc.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()

    def _ensure_quota(self, incoming_bytes: int) -> None:
        """フォルダ内の合計サイズを確認し、上限を超える場合は古いファイルから削除する。"""
        svc = self._get_service()
        files = []
        page_token = None
        while True:
            resp = svc.files().list(
                q=f"'{settings.GOOGLE_DRIVE_FOLDER_ID}' in parents and trashed=false",
                fields="nextPageToken, files(id, size, createdTime)",
                orderBy="createdTime asc",
                pageSize=1000,
                pageToken=page_token,
            ).execute()
            files.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        total = sum(int(f.get("size", 0)) for f in files)

        for f in files:
            if total + incoming_bytes <= MAX_BYTES:
                break
            svc.files().delete(fileId=f["id"]).execute()
            total -= int(f.get("size", 0))
            logger.info("Drive quota: deleted old file %s", f["id"])

    def get_usage_gb(self) -> float:
        """現在のフォルダ使用量(GB)を返す。"""
        if not settings.GOOGLE_DRIVE_ENABLED or not settings.GOOGLE_DRIVE_FOLDER_ID:
            return 0.0
        try:
            svc = self._get_service()
            resp = svc.files().list(
                q=f"'{settings.GOOGLE_DRIVE_FOLDER_ID}' in parents and trashed=false",
                fields="files(size)",
                pageSize=1000,
            ).execute()
            total = sum(int(f.get("size", 0)) for f in resp.get("files", []))
            return round(total / 1024 ** 3, 2)
        except Exception as exc:
            logger.warning("Drive usage check failed: %s", exc)
            return 0.0
