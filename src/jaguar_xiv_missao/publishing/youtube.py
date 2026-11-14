"""Publicação via YouTube Data API v3 (videos.insert, upload resumível)."""

from __future__ import annotations

import logging
from pathlib import Path

from ..config import Settings
from ..models import PublishResult, RenderedClip
from .base import Publisher

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",  # necessário para definir a thumbnail
]


def load_credentials(client_secrets: Path, token_file: Path):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), SCOPES)
        creds = flow.run_local_server(port=0)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


class YouTubePublisher:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._service = None

    def _youtube(self):
        if self._service is None:
            from googleapiclient.discovery import build

            creds = load_credentials(
                self._s.youtube_client_secrets_file, self._s.youtube_token_file
            )
            self._service = build("youtube", "v3", credentials=creds)
        return self._service

    def publish(self, clip: RenderedClip) -> PublishResult:
        from googleapiclient.http import MediaFileUpload

        meta = clip.metadata
        if meta is None:
            raise ValueError("RenderedClip sem metadata")
        body = {
            "snippet": {
                "title": meta.title,
                "description": meta.description,
                "tags": list(meta.tags),
                "categoryId": self._s.youtube_category_id,
                "defaultLanguage": "pt-BR",
                "defaultAudioLanguage": "pt-BR",
            },
            "status": {
                "privacyStatus": self._s.youtube_privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }
        media = MediaFileUpload(str(clip.path), chunksize=8 * 1024 * 1024, resumable=True)
        request = self._youtube().videos().insert(
            part="snippet,status", body=body, media_body=media
        )
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info("Upload %.0f%%", status.progress() * 100)
        video_id = response["id"]
        if clip.thumbnail_path:
            self._youtube().thumbnails().set(
                videoId=video_id, media_body=MediaFileUpload(str(clip.thumbnail_path))
            ).execute()
        return PublishResult(video_id, f"https://www.youtube.com/watch?v={video_id}")


class DryRunPublisher:
    """Não envia nada; só registra o que seria publicado."""

    def publish(self, clip: RenderedClip) -> PublishResult:
        meta = clip.metadata
        logger.info("[dry-run] %s\n%s\ntags=%s", meta.title if meta else "?", clip.path, meta.tags if meta else "")
        return PublishResult(None, None, dry_run=True)


def create_publisher(settings: Settings) -> Publisher:
    """Simple Factory conforme PUBLISH_MODE."""
    if settings.publish_mode == "youtube":
        return YouTubePublisher(settings)
    return DryRunPublisher()
