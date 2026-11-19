"""Cliente HTTP mínimo da Graph API da Meta (Facebook, Instagram e Threads).

POST/GET com nova tentativa em erro de rede e 5xx; erro da API vira `GraphError` com a
mensagem da Meta. O `httpx.Client` e o `sleep` são injetáveis (testes usam MockTransport).
"""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

RETRIES = 3
TIMEOUT = httpx.Timeout(120.0, connect=30.0)
UPLOAD_TIMEOUT = httpx.Timeout(600.0, connect=30.0)


class GraphError(RuntimeError):
    """Resposta de erro da Graph API (o texto traz a mensagem da Meta)."""


class GraphClient:
    def __init__(
        self, token: str, client: httpx.Client | None = None, sleep=time.sleep
    ) -> None:
        self.token = token
        self._client = client or httpx.Client(timeout=TIMEOUT)
        self._sleep = sleep

    def post(
        self,
        url: str,
        data: dict[str, str] | None = None,
        files: dict | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        auth_in_body: bool = True,
        timeout: httpx.Timeout | None = None,
    ) -> dict:
        body = dict(data or {})
        if auth_in_body:
            body["access_token"] = self.token

        def send() -> httpx.Response:
            if content is not None:
                return self._client.post(
                    url, content=content, headers=headers, timeout=timeout or TIMEOUT
                )
            return self._client.post(
                url, data=body, files=files, headers=headers, timeout=timeout or TIMEOUT
            )

        return self._parse(self._retrying(send))

    def get(self, url: str, params: dict[str, str] | None = None) -> dict:
        query = {**(params or {}), "access_token": self.token}
        return self._parse(self._retrying(lambda: self._client.get(url, params=query)))

    # ---------- partes ----------
    def _retrying(self, send) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(1, RETRIES + 1):
            try:
                response = send()
            except httpx.TransportError as exc:
                last = exc
            else:
                if response.status_code < 500:
                    return response
                last = GraphError(f"HTTP {response.status_code}: {response.text[:300]}")
            if attempt < RETRIES:
                wait = 2**attempt
                logger.warning("Graph API falhou (%s); tentando de novo em %ds", last, wait)
                self._sleep(wait)
        raise GraphError(f"Graph API indisponível após {RETRIES} tentativas: {last}")

    @staticmethod
    def _parse(response: httpx.Response) -> dict:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        if response.status_code >= 400 or "error" in payload:
            error = payload.get("error")
            message = (error.get("message") if isinstance(error, dict) else None) or response.text[:300]
            raise GraphError(f"Graph API {response.status_code}: {message}")
        if payload.get("success") is False:
            raise GraphError(f"Graph API recusou o envio: {payload}")
        return payload
