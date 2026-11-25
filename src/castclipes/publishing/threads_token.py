"""Renovação e persistência local do token de longa duração do Threads."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

REFRESH_URL = "https://graph.threads.net/refresh_access_token"
REFRESH_BEFORE = timedelta(days=15)


class ThreadsTokenManager:
    def __init__(self, initial_token: str, path: Path, client: httpx.Client) -> None:
        self._path = path
        self._client = client
        self._initial_token = initial_token
        self._initial_fingerprint = hashlib.sha256(initial_token.encode()).hexdigest()
        self.token = initial_token
        self._expires_at: datetime | None = None
        if path.exists():
            self._load()

    def refresh_if_due(self, now: datetime | None = None) -> bool:
        """Renova no primeiro uso e depois 15 dias antes da validade terminar."""
        if not self.token:
            raise RuntimeError("THREADS_ACCESS_TOKEN não foi configurado")
        now = now or datetime.now(UTC)
        if self._expires_at is not None and now < self._expires_at - REFRESH_BEFORE:
            return False

        try:
            response = self._client.get(
                REFRESH_URL,
                params={"grant_type": "th_refresh_token", "access_token": self.token},
            )
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Falha de rede ao renovar token do Threads ({type(exc).__name__})"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("Threads retornou uma resposta inválida ao renovar o token") from exc
        if response.status_code >= 400 or not isinstance(payload, dict) or payload.get("error"):
            error = payload.get("error") if isinstance(payload, dict) else None
            message = error.get("message") if isinstance(error, dict) else None
            raise RuntimeError(
                f"Threads recusou a renovação do token (HTTP {response.status_code}): "
                f"{message or 'resposta inválida'}"
            )

        new_token = payload.get("access_token")
        expires_in = payload.get("expires_in")
        if (
            not isinstance(new_token, str) or not new_token
            or not isinstance(expires_in, (int, float)) or expires_in <= 0
        ):
            raise RuntimeError("Threads não retornou token e validade ao renovar")

        self.token = new_token
        self._expires_at = now + timedelta(seconds=expires_in)
        self._save()
        logger.info("Token do Threads renovado; validade até %s", self._expires_at.isoformat())
        return True

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("estado inválido")
            if (
                data.get("initial_fingerprint")
                and data["initial_fingerprint"] != self._initial_fingerprint
            ):
                # Um novo token no .env substitui o token salvo após revogação/expiração.
                return
            token = data["access_token"]
            expires_at = datetime.fromisoformat(data["expires_at"])
            if not isinstance(token, str) or not token:
                raise ValueError("token vazio")
            self.token = token
            self._expires_at = expires_at.astimezone(UTC)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError(
                f"Não foi possível ler o estado do token do Threads em {self._path}"
            ) from exc

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps({
                "access_token": self.token,
                "expires_at": self._expires_at.isoformat(),
                "initial_fingerprint": self._initial_fingerprint,
            }),
            encoding="utf-8",
        )
        try:
            os.chmod(temp_path, 0o600)
        except OSError:  # Windows usa ACLs e não implementa permissões POSIX.
            pass
        temp_path.replace(self._path)
